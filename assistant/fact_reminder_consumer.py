"""
Fact → Reminder Consumer: watches facts topic, creates reminders for temporal facts.

When a fact.created or fact.updated event arrives with temporal bounds (starts_at/ends_at),
this consumer creates a set of reminders at key moments. Each reminder, when fired,
produces a task.requested event that spawns an ephemeral agent to fetch live data and
send a travel intelligence message.

Designed for travel facts first, extensible to events, visitors, appointments, etc.
"""

import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

STATE_DIR = Path.home() / "dispatch" / "state"
DB_PATH = STATE_DIR / "bus.db"

# ─── Static lookup tables ──────────────────────────────────────

CHECKIN_URLS = {
    "B6": "https://www.jetblue.com/check-in",
    "UA": "https://www.united.com/en/us/check-in",
    "AA": "https://www.aa.com/check-in",
    "DL": "https://www.delta.com/check-in",
    "WN": "https://www.southwest.com/air/check-in/",
    "AS": "https://www.alaskaair.com/check-in",
    "NK": "https://www.spirit.com/check-in",
    "F9": "https://www.flyfrontier.com/check-in/",
    "HA": "https://www.hawaiianairlines.com/check-in",
    "SY": "https://www.suncountry.com/check-in",
}

# IATA code → IANA timezone (common US airports + major international)
AIRPORT_TIMEZONES = {
    # US East
    "BOS": "America/New_York", "JFK": "America/New_York", "LGA": "America/New_York",
    "EWR": "America/New_York", "PHL": "America/New_York", "IAD": "America/New_York",
    "DCA": "America/New_York", "BWI": "America/New_York", "ATL": "America/New_York",
    "CLT": "America/New_York", "MIA": "America/New_York", "FLL": "America/New_York",
    "MCO": "America/New_York", "TPA": "America/New_York", "PIT": "America/New_York",
    "RDU": "America/New_York", "BUF": "America/New_York", "PVD": "America/New_York",
    # US Central
    "ORD": "America/Chicago", "MDW": "America/Chicago", "DFW": "America/Chicago",
    "IAH": "America/Chicago", "HOU": "America/Chicago", "MSP": "America/Chicago",
    "STL": "America/Chicago", "MCI": "America/Chicago", "AUS": "America/Chicago",
    "SAT": "America/Chicago", "MSY": "America/Chicago", "MEM": "America/Chicago",
    "BNA": "America/Chicago", "IND": "America/Chicago", "MKE": "America/Chicago",
    "CLE": "America/Chicago", "DTW": "America/New_York", "CVG": "America/New_York",
    # US Mountain
    "DEN": "America/Denver", "SLC": "America/Denver", "PHX": "America/Phoenix",
    "ABQ": "America/Denver", "BOI": "America/Boise",
    # US Pacific
    "SFO": "America/Los_Angeles", "LAX": "America/Los_Angeles",
    "SJC": "America/Los_Angeles", "OAK": "America/Los_Angeles",
    "SEA": "America/Los_Angeles", "PDX": "America/Los_Angeles",
    "SAN": "America/Los_Angeles", "SMF": "America/Los_Angeles",
    "BUR": "America/Los_Angeles", "LGB": "America/Los_Angeles",
    # Hawaii / Alaska
    "HNL": "Pacific/Honolulu", "OGG": "Pacific/Honolulu",
    "ANC": "America/Anchorage",
    # International (common)
    "LHR": "Europe/London", "CDG": "Europe/Paris", "FRA": "Europe/Berlin",
    "AMS": "Europe/Amsterdam", "MAD": "Europe/Madrid", "FCO": "Europe/Rome",
    "NRT": "Asia/Tokyo", "HND": "Asia/Tokyo", "ICN": "Asia/Seoul",
    "PEK": "Asia/Shanghai", "PVG": "Asia/Shanghai", "HKG": "Asia/Hong_Kong",
    "SIN": "Asia/Singapore", "BKK": "Asia/Bangkok",
    "SYD": "Australia/Sydney", "MEL": "Australia/Melbourne",
    "YYZ": "America/Toronto", "YVR": "America/Vancouver",
    "MEX": "America/Mexico_City", "CUN": "America/Cancun",
    "GRU": "America/Sao_Paulo", "EZE": "America/Argentina/Buenos_Aires",
    "DXB": "Asia/Dubai", "DOH": "Asia/Qatar",
}

MAJOR_HUBS = {"JFK", "LAX", "ORD", "ATL", "SFO", "DFW", "DEN", "EWR", "LHR", "CDG"}


# ─── Timing helpers ──────────────────────────────────────────

def _parse_dt(s: str) -> datetime:
    """Parse ISO datetime string or date-only string to UTC datetime."""
    if not s:
        raise ValueError("Empty datetime string")
    # Handle date-only strings like "2026-03-29"
    if len(s) == 10 and re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return datetime.fromisoformat(s + "T00:00:00+00:00")
    # Handle ISO datetime with timezone
    s = s.replace('Z', '+00:00')
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_leg_time(time_str: str) -> datetime | None:
    """Parse a leg departs/arrives time string. Returns UTC datetime or None."""
    if not time_str:
        return None
    try:
        return _parse_dt(time_str)
    except Exception:
        # Try to extract datetime from strings like "B6 0933 BOS→SFO 1:59PM EDT Mar 29"
        log.warning(f"Could not parse leg time: {time_str}")
        return None


def _to_utc_iso(dt: datetime) -> str:
    """Convert datetime to UTC ISO string."""
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _apply_quiet_hours(fire_time: datetime, local_tz: ZoneInfo) -> datetime:
    """Shift fire_time out of quiet hours (11 PM – 6 AM local time).

    Converts to local time for the check, shifts to 8 PM previous evening if needed,
    then converts back to UTC.
    """
    local_fire = fire_time.astimezone(local_tz)
    if local_fire.hour >= 23 or local_fire.hour < 6:
        # Shift to 8 PM the previous evening (or same day if after 11 PM)
        if local_fire.hour < 6:
            shifted = local_fire.replace(hour=20, minute=0, second=0, microsecond=0) - timedelta(days=1)
        else:
            shifted = local_fire.replace(hour=20, minute=0, second=0, microsecond=0)
        return shifted.astimezone(timezone.utc)
    return fire_time


def compute_fire_time(departure_time: datetime, airport: str | None = None,
                      international: bool = False) -> datetime:
    """Compute adaptive pre-departure alert time with quiet hours.

    All quiet hours checks are done in the departure airport's local timezone.
    """
    if international:
        offset_hours = 6
    elif airport and airport in MAJOR_HUBS:
        offset_hours = 4
    else:
        offset_hours = 4  # Default to 4h for domestic

    # Determine local timezone for quiet hours
    local_tz = ZoneInfo(AIRPORT_TIMEZONES.get(airport or "", "America/New_York"))
    local_departure = departure_time.astimezone(local_tz)

    fire_time = departure_time - timedelta(hours=offset_hours)

    # Early morning flights (before 8 AM local): fire at 8 PM evening before
    if local_departure.hour < 8:
        evening_before = (local_departure - timedelta(days=1)).replace(
            hour=20, minute=0, second=0, microsecond=0
        )
        return evening_before.astimezone(timezone.utc)

    # Apply quiet hours in local timezone
    return _apply_quiet_hours(fire_time, local_tz)


def compute_checkin_fire_time(departure_time: datetime,
                              airport: str | None = None) -> datetime:
    """T-24h with quiet hours handling in departure airport's local timezone."""
    local_tz = ZoneInfo(AIRPORT_TIMEZONES.get(airport or "", "America/New_York"))
    fire_time = departure_time - timedelta(hours=24)
    return _apply_quiet_hours(fire_time, local_tz)


# ─── Leg extraction from fact details ─────────────────────────

def _extract_legs(fact: dict) -> list[dict]:
    """Extract flight legs from a fact, handling both structured and unstructured formats.

    Returns a list of leg dicts with keys: flight, airline, from, to, departs, arrives,
    seat, booking_ref, class.
    """
    details = fact.get("details")
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except json.JSONDecodeError:
            details = {}
    if not isinstance(details, dict):
        details = {}

    # If details already has structured legs[], use them
    if "legs" in details and isinstance(details["legs"], list):
        return details["legs"]

    # Otherwise, try to extract from unstructured fields
    legs = []

    # Parse outbound_flight like "B6 0933 BOS→SFO 1:59PM EDT Mar 29"
    for key, direction in [("outbound_flight", "outbound"), ("return_flight", "return")]:
        flight_str = details.get(key, "")
        if not flight_str:
            continue

        leg = {"direction": direction}

        # Extract flight number (e.g., "B6 0933")
        flight_match = re.match(r'([A-Z0-9]{2})\s*(\d{3,4})', flight_str)
        if flight_match:
            leg["airline"] = flight_match.group(1)
            leg["flight"] = f"{flight_match.group(1)} {flight_match.group(2)}"

        # Extract route (e.g., "BOS→SFO" or "BOS->SFO")
        route_match = re.search(r'([A-Z]{3})\s*[→\->]+\s*([A-Z]{3})', flight_str)
        if route_match:
            leg["from"] = route_match.group(1)
            leg["to"] = route_match.group(2)

        # Extract time and date (e.g., "1:59PM EDT Mar 29")
        time_match = re.search(
            r'(\d{1,2}:\d{2}\s*(?:AM|PM))\s+([A-Z]{2,4})\s+(\w+\s+\d{1,2})',
            flight_str, re.IGNORECASE
        )
        if time_match:
            time_part = time_match.group(1)
            tz_abbr = time_match.group(2)
            date_part = time_match.group(3)
            # Store the raw time string; we'll parse it with fact dates
            leg["_raw_time"] = f"{date_part} {time_part} {tz_abbr}"

        # Copy class/seat/booking from details
        if details.get("class"):
            leg["class"] = details["class"]

        legs.append(leg)

    return legs


def _resolve_leg_datetime(leg: dict, fact: dict) -> tuple[datetime | None, datetime | None]:
    """Resolve departure and arrival datetimes for a leg.

    Returns (departs_utc, arrives_utc).
    """
    # Try structured departs/arrives first
    departs = _parse_leg_time(leg.get("departs", ""))
    arrives = _parse_leg_time(leg.get("arrives", ""))

    if departs:
        return departs, arrives

    # Try raw time parsing
    raw_time = leg.get("_raw_time")
    if raw_time:
        try:
            # Parse "Mar 29 1:59PM EDT" style
            from_airport = leg.get("from", "")
            tz_name = AIRPORT_TIMEZONES.get(from_airport, "America/New_York")
            tz = ZoneInfo(tz_name)

            # Extract year from fact
            starts_at = fact.get("starts_at", "")
            year = 2026  # Default
            if starts_at and len(starts_at) >= 4:
                year = int(starts_at[:4])

            # Parse the time
            for fmt in ["%b %d %I:%M%p", "%b %d %I:%M %p"]:
                try:
                    parsed = datetime.strptime(raw_time.split()[0] + " " + raw_time.split()[1] + " " + raw_time.split()[2], fmt)
                    departs = parsed.replace(year=year, tzinfo=tz)
                    return departs.astimezone(timezone.utc), None
                except (ValueError, IndexError):
                    continue

            # Simpler attempt: just use month/day + time
            parts = raw_time.split()
            if len(parts) >= 3:
                month_day = f"{parts[0]} {parts[1]}"
                time_part = parts[2]
                for fmt in ["%b %d %I:%M%p", "%b %d %I:%M %p"]:
                    try:
                        parsed = datetime.strptime(f"{month_day} {time_part}", fmt)
                        departs = parsed.replace(year=year, tzinfo=tz)
                        return departs.astimezone(timezone.utc), None
                    except ValueError:
                        continue
        except Exception as e:
            log.warning(f"Failed to parse raw leg time '{raw_time}': {e}")

    # Fall back to fact starts_at/ends_at for outbound/return
    direction = leg.get("direction", "")
    if direction == "outbound" and fact.get("starts_at"):
        dt = _parse_dt(fact["starts_at"])
        # Default to noon if date-only
        if dt.hour == 0 and dt.minute == 0:
            from_airport = leg.get("from", "")
            tz = ZoneInfo(AIRPORT_TIMEZONES.get(from_airport, "America/New_York"))
            dt = dt.replace(hour=12, tzinfo=tz).astimezone(timezone.utc)
        return dt, None
    elif direction == "return" and fact.get("ends_at"):
        dt = _parse_dt(fact["ends_at"])
        if dt.hour == 0 and dt.minute == 0:
            from_airport = leg.get("from", "")
            tz = ZoneInfo(AIRPORT_TIMEZONES.get(from_airport, "America/New_York"))
            dt = dt.replace(hour=12, tzinfo=tz).astimezone(timezone.utc)
        return dt, None

    return None, None


# ─── Contact resolution ────────────────────────────────────────

def _resolve_contact_chat_id(contact_name: str) -> str | None:
    """Resolve a contact name to a chat_id by looking up the registry."""
    registry_path = STATE_DIR / "sessions.json"
    if not registry_path.exists():
        return None
    try:
        registry = json.loads(registry_path.read_text())
        # Search registry for matching contact name
        for chat_id, info in registry.items():
            if isinstance(info, dict) and info.get("contact_name", "").lower() == contact_name.lower():
                return chat_id
    except (json.JSONDecodeError, Exception) as e:
        log.warning(f"Failed to read session registry: {e}")
    return None


# ─── Agent prompt builders ────────────────────────────────────

def _build_checkin_prompt(fact: dict, leg: dict, contact: str, chat_id: str) -> str:
    airline = leg.get("airline", "")
    flight = leg.get("flight", "")
    origin = leg.get("from", "")
    dest = leg.get("to", "")
    seat = leg.get("seat", "")
    booking_ref = leg.get("booking_ref", "")
    flight_class = leg.get("class", "")
    checkin_url = CHECKIN_URLS.get(airline, "")
    departs, _ = _resolve_leg_datetime(leg, fact)
    depart_str = departs.strftime("%A %b %d at %I:%M %p %Z") if departs else "scheduled time"

    return f"""TRAVEL INTELLIGENCE TASK: check-in (T-24h)

CONTEXT:
Fact #{fact.get('id', '?')}: {contact} flying {origin}→{dest}, {flight}, {depart_str}
Contact chat_id: {chat_id}

GATHER:
1. Flight status: `uv run ~/.claude/skills/flight-tracker/scripts/track.py {flight.replace(' ', '-')} --json` — check if still on time
2. Pull seat/booking from context if available: seat={seat}, class={flight_class}, booking={booking_ref}

COMPOSE:
✅ Check-in opens now for {flight} {origin}→{dest} (tomorrow {depart_str})
Check in: {checkin_url or f"search '{airline} online check-in'"}
{"Seat " + seat + " (" + flight_class + ")" if seat else "Check seat assignment after check-in"}
{"Booking ref: " + booking_ref if booking_ref else ""}

SELF-REVIEW:
- Max 4 lines. Every line actionable.
- Include the check-in URL (most important piece).
- Remove any empty/blank lines from missing data.

SEND:
Send this message to the group chat using:
~/.claude/skills/sms-assistant/scripts/send-sms "{chat_id}" "your composed message"

FALLBACK:
If flight-tracker fails, still send the check-in reminder with the URL. Never skip check-in."""


def _build_packing_weather_prompt(fact: dict, contact: str, chat_id: str) -> str:
    details = fact.get("details") or {}
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except json.JSONDecodeError:
            details = {}

    dest = details.get("destination", "destination")
    starts = fact.get("starts_at", "")
    ends = fact.get("ends_at", "")
    hotel = details.get("hotel", {})
    hotel_name = hotel.get("name", "") if isinstance(hotel, dict) else str(hotel)

    return f"""TRAVEL INTELLIGENCE TASK: packing weather (T-1 day)

CONTEXT:
Fact #{fact.get('id', '?')}: {contact} trip to {dest} ({starts} to {ends})
Contact chat_id: {chat_id}
Hotel: {hotel_name or "not specified yet"}

GATHER:
1. Weather forecast for {dest} for the trip dates ({starts} to {ends}):
   Search the web for "{dest} weather forecast this week" using webfetch or chrome
2. Compute packing tip from the forecast (rain gear, layers, umbrella, etc.)

COMPOSE:
🧳 {dest} trip weather ({starts} to {ends}):
• [day-by-day highs/lows and conditions, 1 line per day or summary]
• [packing tip based on forecast]
{"• Hotel " + hotel_name + " check-in: " + (hotel.get("check_in", "3:00 PM") if isinstance(hotel, dict) else "3:00 PM") if hotel_name else ""}

SELF-REVIEW:
- Max 5 lines total. Summarize multi-day forecast into 2-3 lines.
- Include ONE actionable packing tip.
- Remove hotel line if no hotel on file.

SEND:
Send this message to the group chat using:
~/.claude/skills/sms-assistant/scripts/send-sms "{chat_id}" "your composed message"

FALLBACK:
If weather unavailable: "🧳 Couldn't pull forecast for {dest} — check weather.com before packing."
If partial data: send what you have. Partial > nothing."""


def _build_predeparture_prompt(fact: dict, leg: dict, contact: str, chat_id: str) -> str:
    airline = leg.get("airline", "")
    flight = leg.get("flight", "")
    origin = leg.get("from", "")
    dest = leg.get("to", "")
    departs, _ = _resolve_leg_datetime(leg, fact)
    depart_str = departs.strftime("%I:%M %p") if departs else "scheduled time"

    return f"""TRAVEL INTELLIGENCE TASK: pre-departure (T-4h)

CONTEXT:
Fact #{fact.get('id', '?')}: {contact} flying {origin}→{dest}, {flight}, departs {depart_str}
Contact chat_id: {chat_id}

GATHER:
1. Flight status: `uv run ~/.claude/skills/flight-tracker/scripts/track.py {flight.replace(' ', '-')} --json` — gate, delays, status
2. Weather at {origin}: search web for "{origin} airport weather now"
3. Drive time: search web for "drive time to {origin} airport now" (or use 25 min default for BOS)

COMPOSE:
✈️ {origin}→{dest} in ~4 hours ({flight}, {depart_str})
• Flight: [status], Gate [gate]
• Leave by [departure - drive_time - 90min buffer] — [drive_time] drive
• Weather: [temp]°F, [conditions]

SELF-REVIEW:
- Max 4 lines. "Leave by X" is the KEY insight — compute it.
- Times in the traveler's local timezone.
- If flight delayed, lead with that. If on time, keep it short.

SEND:
Send this message to the group chat using:
~/.claude/skills/sms-assistant/scripts/send-sms "{chat_id}" "your composed message"

FALLBACK:
If flight-tracker fails: "✈️ {flight} {origin}→{dest} departs {depart_str}. Check airline app for gate info."
If drive time unavailable, omit that line."""


def _build_gate_update_prompt(fact: dict, leg: dict, contact: str, chat_id: str) -> str:
    flight = leg.get("flight", "")
    origin = leg.get("from", "")
    dest = leg.get("to", "")

    return f"""TRAVEL INTELLIGENCE TASK: gate update (T-1h, delta-only)

CONTEXT:
Fact #{fact.get('id', '?')}: {contact} flying {origin}→{dest}, {flight}
Contact chat_id: {chat_id}

GATHER:
1. Flight status: `uv run ~/.claude/skills/flight-tracker/scripts/track.py {flight.replace(' ', '-')} --json` — gate, delays, status
2. Check state file at ~/dispatch/state/travel-intel/fact{fact.get('id', '0')}-predep-{origin}{dest}.json for previous alert data

COMPOSE (delta-only):
- If gate changed: "⚠️ Gate changed: [old] → [new]. Flight [status]."
- If delay >10 min: "⏱️ {flight} delayed [X] min — new depart [time]. Gate [gate]."
- If nothing material changed: "✈️ Still on time, Gate [gate]. Boarding ~[time]."
- If everything same as previous alert: SUPPRESS — do not send any message.

SELF-REVIEW:
- Max 2 lines. This is a delta update, not a full briefing.
- Only send if something changed OR this is a reassuring confirmation.

SEND:
Send this message to the group chat using:
~/.claude/skills/sms-assistant/scripts/send-sms "{chat_id}" "your composed message"
Save current gate/status to ~/dispatch/state/travel-intel/fact{fact.get('id', '0')}-gate-{origin}{dest}.json for next delta check.

FALLBACK:
If flight-tracker fails, skip this update entirely — don't send noise."""


def _build_onlanding_prompt(fact: dict, leg: dict, contact: str, chat_id: str) -> str:
    details = fact.get("details") or {}
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except json.JSONDecodeError:
            details = {}

    dest = leg.get("to", "")
    dest_city = details.get("destination", dest)
    origin = leg.get("from", "")
    hotel = details.get("hotel", {})
    hotel_name = hotel.get("name", "") if isinstance(hotel, dict) else str(hotel)
    origin_tz = AIRPORT_TIMEZONES.get(origin, "America/New_York")
    dest_tz = AIRPORT_TIMEZONES.get(dest, "America/Los_Angeles")

    return f"""TRAVEL INTELLIGENCE TASK: on-landing

CONTEXT:
Fact #{fact.get('id', '?')}: {contact} landed at {dest} ({dest_city})
Contact chat_id: {chat_id}
Home timezone: {origin_tz}
Destination timezone: {dest_tz}
Hotel: {hotel_name or "not specified"}

GATHER:
1. Current weather at {dest_city}: search web for "{dest_city} weather now"
2. Time zone delta: compute hours between {origin_tz} and {dest_tz}
3. {"Drive time to " + hotel_name + ": search web" if hotel_name else "Transit options: search 'getting from " + dest + " airport to downtown'"}

COMPOSE:
🛬 Welcome to {dest_city}!
• [temp]°F, [conditions]
• {"Drive to " + hotel_name + ": ~[X] min" if hotel_name else "[transit tip]"}
• You're now [X] hours [behind/ahead of] home
• [one local tip: BART/subway/transit or restaurant]

SELF-REVIEW:
- Max 5 lines. Actionable info only.
- Time zone delta is important for jet lag awareness.
- Hotel directions are priority if hotel is known.

SEND:
Send this message to the group chat using:
~/.claude/skills/sms-assistant/scripts/send-sms "{chat_id}" "your composed message"

FALLBACK:
At minimum: "🛬 Welcome to {dest_city}! Local time is [time] ({dest_tz})."
Send whatever data you can get."""


def _build_daily_intel_prompt(fact: dict, day_number: int, date_str: str,
                              is_last_day: bool, contact: str, chat_id: str) -> str:
    details = fact.get("details") or {}
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except json.JSONDecodeError:
            details = {}

    dest_city = details.get("destination", "destination")
    hotel = details.get("hotel", {})
    hotel_name = hotel.get("name", "") if isinstance(hotel, dict) else str(hotel)

    if is_last_day:
        # Merged checkout + daily
        legs = _extract_legs(fact)
        return_leg = None
        for leg in legs:
            if leg.get("direction") == "return":
                return_leg = leg
                break

        return_info = ""
        if return_leg:
            flight = return_leg.get("flight", "")
            departs, _ = _resolve_leg_datetime(return_leg, fact)
            depart_str = departs.strftime("%I:%M %p") if departs else "check itinerary"
            checkin_url = CHECKIN_URLS.get(return_leg.get("airline", ""), "")
            return_info = f"""
Return flight: {flight} departs {depart_str}
Check-in URL: {checkin_url}"""

        checkout_time = "11:00 AM"
        if isinstance(hotel, dict) and hotel.get("check_out"):
            checkout_time = hotel["check_out"]

        return f"""TRAVEL INTELLIGENCE TASK: check-out / last morning (merged)

CONTEXT:
Fact #{fact.get('id', '?')}: {contact} last day in {dest_city} (day {day_number})
Date: {date_str}
Contact chat_id: {chat_id}
Hotel: {hotel_name or "not specified"}
Checkout time: {checkout_time}
{return_info}

GATHER:
1. Weather at {dest_city}: search web for "{dest_city} weather today"
2. Return flight status (if applicable): `uv run ~/.claude/skills/flight-tracker/scripts/track.py [flight] --json`
3. Drive time to airport: search web

COMPOSE:
🏨 Last day in {dest_city} — check out by {checkout_time}
• [weather]
• [return flight info + check-in link if within 24h]
• Leave for airport by [computed time]
• 🧳 Don't forget: chargers, toiletries

SELF-REVIEW:
- Max 5 lines. Merge checkout + flight info naturally.
- Include check-in link if T-24h hasn't fired yet for return.
- "Leave by X" is critical for return flights.

SEND:
Send this message to the group chat using:
~/.claude/skills/sms-assistant/scripts/send-sms "{chat_id}" "your composed message"

FALLBACK:
At minimum: "🏨 Last day in {dest_city} — check out by {checkout_time}. Safe travels home!\""""

    else:
        return f"""TRAVEL INTELLIGENCE TASK: daily morning intel (day {day_number})

CONTEXT:
Fact #{fact.get('id', '?')}: {contact} in {dest_city}, day {day_number}
Date: {date_str}
Contact chat_id: {chat_id}
Hotel: {hotel_name or "not specified"}

GATHER:
1. Weather forecast for {dest_city} today: search web for "{dest_city} weather today"
2. {"Nearby places: search for restaurants/attractions near " + hotel_name if hotel_name else "Things to do in " + dest_city + " today"}

COMPOSE:
🌤️ {dest_city} Day {day_number} — {date_str}
• [high]°/[low]°F, [conditions] [☔ if rain expected]
• {"Near " + hotel_name + ": " if hotel_name else ""}[2-3 nearby suggestions]

SELF-REVIEW:
- Max 3 lines. Quick morning glance.
- Include umbrella reminder if rain >40%.
- Suggestions should be specific and nearby, not generic.

SEND:
Send this message to the group chat using:
~/.claude/skills/sms-assistant/scripts/send-sms "{chat_id}" "your composed message"

FALLBACK:
If weather fails: "Good morning from {dest_city}! ☀️"
If places fail: just send weather."""


# ─── Core consumer logic ──────────────────────────────────────

def handle_fact_event(records: list) -> None:
    """Process fact.created and fact.updated events, creating/updating reminders.

    This is the action function registered with the ConsumerRunner.
    """
    from assistant.reminders import (
        reminders_lock, load_reminders, save_reminders, create_reminder,
    )

    for record in records:
        try:
            payload = record.payload
            if not isinstance(payload, dict):
                log.warning(f"FactReminderConsumer: non-dict payload, skipping")
                continue

            fact_type = payload.get("fact_type", "")
            fact_id = payload.get("fact_id")
            contact = payload.get("contact", "")

            if not fact_id:
                log.warning("FactReminderConsumer: missing fact_id, skipping")
                continue

            # Only process temporal fact types
            if fact_type == "travel":
                _handle_travel_fact(record, payload)
            elif fact_type == "event":
                _handle_event_fact(record, payload)
            else:
                log.debug(f"FactReminderConsumer: skipping non-temporal fact type: {fact_type}")

        except Exception as e:
            log.error(f"FactReminderConsumer: error processing fact event: {e}", exc_info=True)


def _get_full_fact(fact_id: int) -> dict | None:
    """Read the full fact from the database."""
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
        conn.close()
        if row:
            return dict(row)
        return None
    except Exception as e:
        log.error(f"FactReminderConsumer: failed to read fact {fact_id}: {e}")
        return None


def _cancel_existing_reminders(fact_id: int, data: dict) -> int:
    """Cancel all existing reminders for a given fact_id. Returns count cancelled."""
    prefix = f"travel-intel-{fact_id}-"
    original = len(data["reminders"])
    data["reminders"] = [
        r for r in data["reminders"]
        if not r.get("title", "").startswith(prefix)
    ]
    cancelled = original - len(data["reminders"])
    if cancelled:
        log.info(f"FactReminderConsumer: cancelled {cancelled} existing reminders for fact {fact_id}")
    return cancelled


def _handle_travel_fact(record, payload: dict) -> None:
    """Create reminders for a travel fact."""
    from assistant.reminders import (
        reminders_lock, load_reminders, save_reminders, create_reminder,
    )

    fact_id = payload["fact_id"]
    contact = payload.get("contact", "")
    event_type = record.type  # fact.created or fact.updated

    # Read full fact from DB for complete details
    fact = _get_full_fact(fact_id)
    if not fact:
        log.error(f"FactReminderConsumer: fact {fact_id} not found in DB")
        return

    # Resolve contact to chat_id
    chat_id = _resolve_contact_chat_id(contact)
    if not chat_id:
        # Try if contact is already a chat_id
        if contact.startswith("+") or re.match(r'^[0-9a-f]{32}$', contact):
            chat_id = contact
        else:
            log.error(f"FactReminderConsumer: cannot resolve contact '{contact}' to chat_id")
            return

    # Extract legs
    legs = _extract_legs(fact)
    if not legs:
        log.warning(f"FactReminderConsumer: no flight legs found in fact {fact_id}")

    now = datetime.now(timezone.utc)
    reminders_to_create = []

    # Ensure state dir for travel intel exists
    intel_state_dir = STATE_DIR / "travel-intel"
    intel_state_dir.mkdir(parents=True, exist_ok=True)

    # ── Per-leg reminders ──
    checkin_dedup = set()  # (airline, date) for dedup

    for i, leg in enumerate(legs):
        departs, arrives = _resolve_leg_datetime(leg, fact)
        if not departs:
            log.warning(f"FactReminderConsumer: could not resolve departure time for leg {i}")
            continue

        # Skip past legs
        if departs < now:
            log.info(f"FactReminderConsumer: skipping past leg {i} (departs {departs})")
            continue

        airline = leg.get("airline", "")
        flight = leg.get("flight", f"leg-{i}")
        origin = leg.get("from", "")
        dest = leg.get("to", "")
        tag = f"{origin}{dest}"

        # 1. Check-in (T-24h) with dedup for same-airline same-day
        dedup_key = (airline, departs.date().isoformat())
        if dedup_key not in checkin_dedup:
            checkin_dedup.add(dedup_key)
            checkin_time = compute_checkin_fire_time(departs, airport=origin)
            if checkin_time > now:
                prompt = _build_checkin_prompt(fact, leg, contact, chat_id)
                reminders_to_create.append({
                    "title": f"travel-intel-{fact_id}-checkin-{tag}",
                    "fire_at": _to_utc_iso(checkin_time),
                    "prompt": prompt,
                    "chat_id": chat_id,
                })

        # 2. Pre-departure (adaptive T-Xh)
        predep_time = compute_fire_time(departs, airport=origin)
        if predep_time > now:
            prompt = _build_predeparture_prompt(fact, leg, contact, chat_id)
            reminders_to_create.append({
                "title": f"travel-intel-{fact_id}-predep-{tag}",
                "fire_at": _to_utc_iso(predep_time),
                "prompt": prompt,
                "chat_id": chat_id,
            })

        # 3. Gate update (T-1h) — delta-only
        gate_time = departs - timedelta(hours=1)
        if gate_time > now:
            prompt = _build_gate_update_prompt(fact, leg, contact, chat_id)
            reminders_to_create.append({
                "title": f"travel-intel-{fact_id}-gate-{tag}",
                "fire_at": _to_utc_iso(gate_time),
                "prompt": prompt,
                "chat_id": chat_id,
            })

        # 4. On-landing (scheduled arrival + 15min buffer for taxiing)
        if arrives:
            land_time = arrives + timedelta(minutes=15)
        else:
            # Estimate: departs + 5-6 hours for cross-country
            land_time = departs + timedelta(hours=6)

        if land_time > now:
            prompt = _build_onlanding_prompt(fact, leg, contact, chat_id)
            reminders_to_create.append({
                "title": f"travel-intel-{fact_id}-landing-{tag}",
                "fire_at": _to_utc_iso(land_time),
                "prompt": prompt,
                "chat_id": chat_id,
            })

    # ── Packing weather (T-1 day before trip start) ──
    if fact.get("starts_at"):
        trip_start = _parse_dt(fact["starts_at"])
        # Find the first leg's departure for accurate timing
        first_departs = trip_start
        if legs:
            fd, _ = _resolve_leg_datetime(legs[0], fact)
            if fd:
                first_departs = fd

        packing_time = (first_departs - timedelta(days=1)).replace(
            hour=20, minute=0, second=0, microsecond=0
        )
        # Adjust to origin timezone evening
        if legs and legs[0].get("from"):
            origin_tz = AIRPORT_TIMEZONES.get(legs[0]["from"], "America/New_York")
            packing_time = datetime.combine(
                (first_departs - timedelta(days=1)).date(),
                datetime.min.time().replace(hour=20),
                tzinfo=ZoneInfo(origin_tz),
            ).astimezone(timezone.utc)

        if packing_time > now:
            prompt = _build_packing_weather_prompt(fact, contact, chat_id)
            reminders_to_create.append({
                "title": f"travel-intel-{fact_id}-packing",
                "fire_at": _to_utc_iso(packing_time),
                "prompt": prompt,
                "chat_id": chat_id,
            })

    # ── Daily morning intel ──
    if fact.get("starts_at") and fact.get("ends_at"):
        trip_start = _parse_dt(fact["starts_at"])
        trip_end = _parse_dt(fact["ends_at"])

        # Determine destination timezone
        dest_tz_name = "America/Los_Angeles"  # Default
        if legs:
            # Use first outbound leg's destination
            for leg in legs:
                if leg.get("to"):
                    dest_tz_name = AIRPORT_TIMEZONES.get(leg["to"], dest_tz_name)
                    break

        dest_tz = ZoneInfo(dest_tz_name)

        # Start from day 2 (day 1 = travel day, covered by on-landing)
        current_day = trip_start.date() + timedelta(days=1)
        end_date = trip_end.date()
        day_number = 2

        while current_day <= end_date:
            # 8 AM in destination timezone → UTC
            local_8am = datetime.combine(current_day, datetime.min.time().replace(hour=8),
                                         tzinfo=dest_tz)
            utc_fire = local_8am.astimezone(timezone.utc)

            if utc_fire > now:
                is_last_day = (current_day == end_date)
                date_str = current_day.strftime("%A %b %d")

                # Frequency cap: daily for first 7 days, every-other-day after
                if day_number <= 7 or day_number % 2 == 0:
                    prompt = _build_daily_intel_prompt(
                        fact, day_number, date_str, is_last_day, contact, chat_id
                    )
                    reminders_to_create.append({
                        "title": f"travel-intel-{fact_id}-daily-d{day_number}",
                        "fire_at": _to_utc_iso(utc_fire),
                        "prompt": prompt,
                        "chat_id": chat_id,
                    })

            current_day += timedelta(days=1)
            day_number += 1

    # ── Write all reminders ──
    if not reminders_to_create:
        log.info(f"FactReminderConsumer: no future reminders needed for fact {fact_id}")
        return

    with reminders_lock():
        data = load_reminders()

        # On update, cancel existing reminders for this fact first
        if event_type == "fact.updated":
            _cancel_existing_reminders(fact_id, data)
        else:
            # Even on create, cancel any dupes (idempotency)
            _cancel_existing_reminders(fact_id, data)

        created_count = 0
        for r in reminders_to_create:
            reminder = create_reminder(
                title=r["title"],
                schedule_type="once",
                schedule_value=r["fire_at"],
                event={
                    "topic": "tasks",
                    "type": "task.requested",
                    "payload": {
                        "task_id": r["title"],
                        "title": r["title"],
                        "requested_by": r["chat_id"],
                        "notify": False,
                        "timeout_minutes": 5,
                        "execution": {
                            "mode": "agent",
                            "prompt": r["prompt"],
                        },
                    },
                    "key": r["chat_id"],
                },
            )
            data["reminders"].append(reminder)
            created_count += 1
            log.info(f"FactReminderConsumer: created reminder '{r['title']}' fires at {r['fire_at']}")

        save_reminders(data)
        log.info(f"FactReminderConsumer: created {created_count} reminders for travel fact {fact_id}")


def _handle_event_fact(record, payload: dict) -> None:
    """Create reminders for an event fact (concerts, dinners, meetings, etc.)."""
    from assistant.reminders import (
        reminders_lock, load_reminders, save_reminders, create_reminder,
    )

    fact_id = payload["fact_id"]
    contact = payload.get("contact", "")
    starts_at = payload.get("starts_at")

    if not starts_at:
        log.debug(f"FactReminderConsumer: event fact {fact_id} has no starts_at, skipping")
        return

    event_time = _parse_dt(starts_at)
    now = datetime.now(timezone.utc)

    if event_time < now:
        log.info(f"FactReminderConsumer: event fact {fact_id} is in the past, skipping")
        return

    # Resolve chat_id
    chat_id = _resolve_contact_chat_id(contact)
    if not chat_id:
        if contact.startswith("+") or re.match(r'^[0-9a-f]{32}$', contact):
            chat_id = contact
        else:
            log.error(f"FactReminderConsumer: cannot resolve contact '{contact}' for event fact {fact_id}")
            return

    summary = payload.get("summary", "Event")

    # T-2h reminder for events
    fire_time = event_time - timedelta(hours=2)
    if fire_time < now:
        fire_time = now + timedelta(minutes=5)  # Fire soon if <2h away

    prompt = f"""TASK: Event reminder for {contact}

Event: {summary}
Time: {event_time.strftime("%A %b %d at %I:%M %p")}
Contact chat_id: {chat_id}

GATHER:
1. Weather: search web for current weather at event location
2. Drive time: search web for drive time to event location

COMPOSE:
📅 Reminder: {summary}
• In ~2 hours
• [weather + drive time if found]

SEND:
Send this message using:
~/.claude/skills/sms-assistant/scripts/send-sms "{chat_id}" "your composed message"
"""

    with reminders_lock():
        data = load_reminders()
        _cancel_existing_reminders(fact_id, data)

        reminder = create_reminder(
            title=f"travel-intel-{fact_id}-event",
            schedule_type="once",
            schedule_value=_to_utc_iso(fire_time),
            event={
                "topic": "tasks",
                "type": "task.requested",
                "payload": {
                    "task_id": f"travel-intel-{fact_id}-event",
                    "title": f"Event reminder: {summary}",
                    "requested_by": chat_id,
                    "notify": False,
                    "timeout_minutes": 5,
                    "execution": {
                        "mode": "agent",
                        "prompt": prompt,
                    },
                },
                "key": chat_id,
            },
        )
        data["reminders"].append(reminder)
        save_reminders(data)
        log.info(f"FactReminderConsumer: created event reminder for fact {fact_id} at {_to_utc_iso(fire_time)}")
