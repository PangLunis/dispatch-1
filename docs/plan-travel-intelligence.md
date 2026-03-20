# Travel Intelligence Pipeline

**Status**: Draft v3 (post-review round 2)
**Score**: 8.2/10 → revised
**Depends on**: Structured Facts (9/10, implemented), Reminders (v6, implemented), Flight Tracker, Places API

## Overview

When a travel fact is created (manually or via nightly extraction), the system automatically creates reminders at key moments throughout the trip. When each reminder fires, a skill fetches live contextual data and texts the traveler.

```
fact.created (travel) ──► Auto-create reminders at key moments
                              │
                              ├─ T-24h: airline check-in (per leg)
                              ├─ T-4h/T-6h: pre-departure (adaptive)
                              ├─ T-1h: gate/delay update (delta-only)
                              ├─ On landing (actual, via FlightAware poll)
                              ├─ Each morning of trip (8am destination local)
                              ├─ Check-out / last morning (merged)
                              └─ T-4h/T-6h: pre-return (adaptive)
                              │
                         ┌────┴────────────────────────────┐
                         │  CONTINUOUS: Flight status watch │
                         │  Cancellation/major delay alert  │
                         └─────────────────────────────────┘

reminder.due ──► Ephemeral agent ──► Fetch live data ──► SMS to contact
```

## Key Moments (Travel)

### 📋 Pre-Trip

| When | What to fetch | Why |
|------|--------------|-----|
| **T-1 week (international only)** | Passport expiry check (need 6+ months), visa requirements for destination, currency exchange rate | Catch trip-blocking issues early |
| **T-1 day** | Multi-day weather forecast for full trip (packing summary: "bring umbrella, rain on days 3-4"), hotel check-in time + directions from airport, rental car confirmation if applicable | Pack right, plan arrival |

### ✈️ Pre-Departure (each leg)

| When | What to fetch | Why |
|------|--------------|-----|
| **T-24h before first leg per departure day** | Airline check-in link (static lookup by IATA code), seat assignment confirmation. **Same-airline connecting legs share one check-in** — don't send duplicate reminders | Most valuable single reminder — don't miss check-in window |
| **T-evening-before (for flights before 8 AM)** | Same as T-Xh but fired at 8 PM the night before | Red-eye/early morning — don't wake them at 2 AM |
| **T-Xh before departure (adaptive)** | Flight status/delays, drive time to airport (Google Maps), weather at origin | **Adaptive timing**: T-6h international, T-4h major domestic hub, T-2h small regional. See Adaptive Timing section for full logic including quiet hours |
| **T-1h before departure** | Gate assignment, delay updates, boarding time. **Delta-only**: suppress or send one-liner if nothing changed since T-Xh | Last-minute gate changes |

### 🔗 Layovers (multi-leg flights)

| When | What to fetch | Why |
|------|--------------|-----|
| **On landing at connection** | Next gate + terminal (from FlightAware), estimated walk time (rough estimate by airport size: small=5min, medium=10min, large=15min, mega-hub=20min), layover duration countdown | Don't miss connection |

### 🛬 On Landing (destination)

| When | What to fetch | Why |
|------|--------------|-----|
| **Actual landing (poll FlightAware)** | Weather at destination (current + today's forecast), drive time to hotel (Google Maps), time zone delta ("3 hours behind home"), local transit option if known city (e.g., "BART to downtown: ~$10, 30 min") | Immediately actionable off the plane. See On-Landing Trigger section for polling spec |

### 🚨 Flight Status Watch (continuous)

| When | What to fetch | Why |
|------|--------------|-----|
| **Cancellation detected** | Alternative flights on same route within 24h (FlightAware search), airline rebooking phone number | **Safety-critical**: immediate notification. Poll FlightAware every 15 min starting T-24h. On cancellation, fire immediately regardless of quiet hours |
| **Major delay (>1h) detected** | Updated departure time, downstream impact (connection risk, hotel check-in), revised drive time to airport | Allows re-planning. Only alert on first detection + if delay changes by >30 min |

### 🌤️ Daily Trip Intelligence

| When | What to fetch | Why |
|------|--------------|-----|
| **Each morning 8 AM destination local** | Weather forecast (high/low, precip %), things to do nearby (Google Places, if hotel known), sunrise/sunset. **Last morning is merged with check-out** (see below). Cap at 7 consecutive days, then every-other-day for longer trips | Daily planning |

### 🏨 Hotel Check-out (merged with last daily)

On the final morning, the daily intelligence message is **merged** with check-out logistics into a single message. No separate check-out reminder fires.

| When | What to fetch | Why |
|------|--------------|-----|
| **Last morning 8 AM** | Check-out time (from fact details, default "11 AM"), luggage storage note, return flight status + check-in link if T-24h hasn't fired yet, drive time to airport, weather at home | Combined daily + departure planning in one message |

### ✈️ Pre-Return

| When | What to fetch | Why |
|------|--------------|-----|
| **T-24h before return** | Check-in reminder for return flight (if not already covered by check-out morning) | Same high-value moment as outbound. Dedup: if check-out morning already included check-in link, skip this |
| **T-Xh before return (adaptive)** | Flight status, drive time to return airport, weather at home | Know what you're coming back to |

### ❌ Removed: Post-Trip Summary

_Previously had "welcome back with trip summary" on landing at home. Removed — low value, slight annoyance risk when tired. Weather at home is covered by pre-return T-Xh alert._

## Key Moments (Non-Travel Fact Types)

### 🎉 Events (concerts, dinners, meetings)

| When | What to fetch | Why |
|------|--------------|-----|
| **T-2h before event** (casual) / **T-4h** (formal/unfamiliar venue) | Weather, drive time to venue (Google Maps), parking info nearby (Google Places) | Adaptive: casual dinner=T-2h, concert/formal=T-4h |
| **T-30min before event** | Final traffic check. **Delta-only**: suppress if nothing changed since earlier alert | Last-minute route changes only |

### 🏠 Visitors Coming to Stay

| When | What to fetch | Why |
|------|--------------|-----|
| **Day before arrival** | Weather forecast for their visit, local restaurant recs, things to do | Prepare for guests |
| **Morning of arrival** | Guest's flight status (if known), weather | Day-of prep |

### 📦 Deliveries / Shipments

| When | What to fetch | Why |
|------|--------------|-----|
| **Delivery day morning** | Tracking status, estimated delivery window | Be available |

### 🎂 Birthdays / Anniversaries

| When | What to fetch | Why |
|------|--------------|-----|
| **T-3 days** | Gift ideas based on known preferences, restaurant availability | Plan ahead |
| **Day of** | Reminder to send message/call | Don't forget |

### 🏥 Appointments (doctor, dentist, etc.)

| When | What to fetch | Why |
|------|--------------|-----|
| **T-1 day** | Reminder + traffic estimate, any prep instructions | Don't miss it |
| **T-1h** | Traffic/transit to location | Leave on time |

### 🚗 Rental Car

| When | What to fetch | Why |
|------|--------------|-----|
| **Pickup time - 1h** | Directions to rental counter, confirmation number | Don't miss pickup |
| **Return time - 2h** | Gas station nearby, drive time to return location, return instructions | Avoid late fees |

## Design Principles

### Foreground Session Injection
Travel intelligence messages are **injected into the contact's foreground session** (target=fg), not sent as standalone SMS. This enables:

1. **Conversational fact updates**: User replies "actually staying at Hotel Zetta" → session updates fact details, re-computes drive times, adjusts daily intel
2. **Ad-hoc requests**: User replies "find a dinner spot near the hotel for Saturday" → session uses Places API with hotel location from the fact
3. **Fact creation from replies**: User replies "meeting at Salesforce Tower 2pm Monday" → session creates a new event fact with auto-reminders
4. **Context awareness**: Session already has facts in CLAUDE.md, so it understands the full trip context

The session formats the intelligence as a natural message and sends it, then stays ready for follow-up. If the user doesn't reply, no action needed.

### Adaptive Timing
```python
def compute_fire_time(departure_time, fact_type, airport=None, international=False):
    """Compute when to fire a pre-departure alert."""
    # Base offset by context
    if international:
        offset_hours = 6
    elif airport in MAJOR_HUBS:  # JFK, LAX, ORD, ATL, SFO, DFW, DEN
        offset_hours = 4
    else:
        offset_hours = 2

    fire_time = departure_time - timedelta(hours=offset_hours)

    # Quiet hours: 11 PM – 6 AM → shift to 8 PM previous evening
    if fire_time.hour >= 23 or fire_time.hour < 6:
        fire_time = fire_time.replace(hour=20, minute=0) - timedelta(days=1 if fire_time.hour < 6 else 0)

    # Early morning flights (before 8 AM): fire at 8 PM evening before
    if departure_time.hour < 8:
        fire_time = (departure_time - timedelta(days=1)).replace(hour=20, minute=0)

    return fire_time


def compute_checkin_fire_time(departure_time):
    """T-24h with quiet hours handling."""
    fire_time = departure_time - timedelta(hours=24)
    # Apply same quiet hours logic
    if fire_time.hour >= 23 or fire_time.hour < 6:
        fire_time = fire_time.replace(hour=20, minute=0) - timedelta(days=1 if fire_time.hour < 6 else 0)
    return fire_time
```

### Delta-Only Suppression
For follow-up alerts (T-1h after T-4h, T-30min after T-2h):
- Agent stores previous alert data in a lightweight state file: `~/dispatch/state/travel-intel/{fact_id}-{moment}.json`
- Compare current data to what was sent in the previous alert
- If nothing material changed (same gate, same status, similar weather): send one-liner "✈️ Still on time, Gate B15"
- If something changed: send full update highlighting the change with "⚠️" prefix
- If previous state file missing (first alert or state lost): send full message

### Multi-Leg Flight Support
Facts with multi-leg flights store `legs[]` in details:
```json
{
  "destination": "San Francisco",
  "origin": "Boston",
  "legs": [
    {
      "flight": "B6 0933",
      "airline": "B6",
      "from": "BOS",
      "to": "SFO",
      "departs": "2026-03-29T13:59",
      "arrives": "2026-03-29T17:54",
      "class": "Business",
      "seat": "4A",
      "booking_ref": "ABCDEF"
    },
    {
      "flight": "B6 0434",
      "airline": "B6",
      "from": "SFO",
      "to": "BOS",
      "departs": "2026-04-03T09:00",
      "arrives": "2026-04-03T17:45",
      "class": "Business",
      "seat": "4F",
      "booking_ref": "ABCDEF"
    }
  ],
  "hotel": {
    "name": "Hotel Nikko",
    "address": "222 Mason St, San Francisco, CA",
    "check_in": "15:00",
    "check_out": "11:00"
  }
}
```

**Per-leg reminder rules:**
- Each leg gets its own pre-departure (T-Xh, T-1h) and on-landing moments
- **Check-in dedup**: Same-airline legs departing same day share one T-24h reminder (airlines check in all legs at once)
- Layover legs (mid-trip connections) get connection intelligence instead of full on-landing
- Daily intel uses the hotel location for the current segment of the trip

### Airline Check-In URL Lookup
Static mapping from IATA code to check-in URL (not fetched dynamically):
```python
CHECKIN_URLS = {
    "B6": "https://www.jetblue.com/check-in",
    "UA": "https://www.united.com/en/us/check-in",
    "AA": "https://www.aa.com/check-in",
    "DL": "https://www.delta.com/check-in",
    "WN": "https://www.southwest.com/air/check-in/",
    "AS": "https://www.alaskaair.com/check-in",
    "NK": "https://www.spirit.com/check-in",
    "F9": "https://www.flyfrontier.com/check-in/",
    # ... extensible
}
```

### On-Landing Trigger Mechanism
Don't use scheduled arrival time (unreliable with delays). Instead:
1. Starting at scheduled_arrival - 30 min, poll FlightAware every 5 min
2. When status changes to "landed", fire the on-landing agent
3. Timeout: if no "landed" status after scheduled_arrival + 2h, fire anyway with whatever data is available
4. Implementation: a `landing-watch` reminder with 5-min cron fires during the window; the agent checks flight status and only sends the SMS when landed (or on timeout)
5. **API budget**: ~6 calls/leg/landing window (30 min typical). For a 3-leg trip: ~18 calls total. Well within FlightAware's free scraping budget.

### Error Handling & Fallback Policy

Each agent prompt includes explicit fallback behavior:

| Data source | On failure | Fallback |
|------------|-----------|----------|
| **Weather (Open-Meteo)** | API timeout or error | Skip weather line, note "weather unavailable" |
| **Flight status (FlightAware)** | Scrape fails or blocked | Use scheduled time, note "unable to verify live status — check airline app" |
| **Drive time (Google Maps)** | API error or quota | Omit drive time line, include airport name only |
| **Google Places** | API error | Omit "things to do" section from daily intel |

**Policy**: Always send the message with whatever data is available. Never skip an entire reminder because one data source failed. Partial is better than nothing.

**Retry**: If ALL data sources fail (total agent failure), retry once after 5 min. If second attempt fails, send minimal message: "✈️ Your flight B6 0933 BOS→SFO departs at 1:59 PM. Check airline app for latest status."

### Timezone Scheduling for Daily Intel

Daily 8 AM destination-local reminders require timezone-aware scheduling:

```python
def schedule_daily_intel(fact, leg_arriving_at_destination):
    """Schedule daily morning reminders in the destination timezone."""
    dest_airport = leg_arriving_at_destination["to"]
    dest_tz = AIRPORT_TIMEZONES[dest_airport]  # e.g., "America/Los_Angeles"

    trip_start = parse_date(fact["starts_at"])
    trip_end = parse_date(fact["ends_at"])

    # Skip day 1 (covered by on-landing), start from day 2
    current_day = trip_start + timedelta(days=1)
    while current_day <= trip_end:
        # 8 AM in destination timezone, converted to UTC for reminder storage
        local_8am = dest_tz.localize(datetime.combine(current_day, time(8, 0)))
        utc_fire = local_8am.astimezone(timezone.utc)

        is_last_day = (current_day == trip_end)
        template = "daily-checkout" if is_last_day else "daily-intel"

        create_reminder(fact_id, template, fire_at_utc=utc_fire,
                       metadata={"day_number": (current_day - trip_start).days + 1,
                                 "is_last_day": is_last_day,
                                 "dest_tz": str(dest_tz)})
        current_day += timedelta(days=1)
```

Airport timezone lookup via a static table (IATA code → IANA timezone). ~400 airports covers all commercial flights.

## Architecture

### Phase 1: Fact Consumer → Reminder Creator

A new bus consumer watches the `facts` topic for `fact.created` and `fact.updated` events with temporal bounds. It creates reminders using the generalized event mode.

```python
# New file: ~/dispatch/assistant/fact_reminder_consumer.py

class FactReminderConsumer:
    """Watches facts topic, creates/updates reminders for temporal facts."""

    TEMPLATES = {
        "travel": [
            # Per-leg moments
            {"offset_hours": -24, "anchor": "leg.departs", "per_leg": True,
             "dedup": "same_airline_same_day",
             "title": "check-in-{leg}", "prompt_template": "checkin"},
            {"anchor": "leg.departs", "per_leg": True,
             "adaptive": True,
             "title": "pre-departure-{leg}", "prompt_template": "pre_departure"},
            {"offset_hours": -1, "anchor": "leg.departs", "per_leg": True,
             "delta_only": True,
             "title": "gate-update-{leg}", "prompt_template": "gate_update"},
            {"anchor": "leg.arrives", "per_leg": True,
             "poll_landing": True,
             "title": "on-landing-{leg}", "prompt_template": "on_landing"},
            # Continuous flight watch
            {"anchor": "leg.departs", "per_leg": True,
             "offset_hours": -24, "continuous_until": "leg.arrives",
             "poll_interval_min": 15,
             "title": "flight-watch-{leg}", "prompt_template": "flight_watch"},
            # Daily intel
            {"time": "08:00", "tz": "destination", "recurring_daily": True,
             "skip_day_1": True, "merge_last_day_checkout": True,
             "title": "daily-intel", "prompt_template": "daily_intel"},
        ],
    }
```

### Phase 2: Reminder → Agent Execution

When a reminder fires, it produces a `task.requested` event. The existing task consumer spawns an ephemeral agent. The agent uses its existing skills (chrome-control, webfetch, flight-tracker, places, etc.) to fetch live data — **no dedicated weather or drive-time CLIs needed**. The agent can look up weather, drive times, and other data on the web just like a human would.

**Agent prompt structure** — each prompt has 4 sections:

```
TRAVEL INTELLIGENCE TASK: {moment_type}

CONTEXT:
  Fact ID, leg details, contact, what moment this is

GATHER:
  What data to look up (flight status, weather, drive time, etc.)
  Agent uses its existing tools — flight-tracker CLI, web search, chrome, etc.

COMPOSE:
  Message template with placeholders. Keep it to 3-5 bullet points max.

SELF-REVIEW:
  Before sending, re-read the composed message and check:
  1. Is it under 5 lines? If not, cut the least important line.
  2. Does every line contain actionable info? Remove fluff.
  3. Are times in the contact's local timezone?
  4. No duplicate info from a previous alert (delta-only check)?
  If the message fails self-review, revise and re-check once.

SEND:
  Inject into foreground session (or send-sms if no session active)

FALLBACK:
  If a data source fails, send partial. Never skip the entire message.
  Minimum viable message: emoji + flight + departure time + "check airline app"
```

**Example prompt (pre-departure T-4h):**

```json
{
  "topic": "tasks",
  "type": "task.requested",
  "key": "+16175551234",
  "payload": {
    "task_id": "travel-intel-14-predep-leg0",
    "title": "Pre-departure intel: B6 0933 BOS→SFO",
    "requested_by": "+16175551234",
    "notify": false,
    "timeout_minutes": 5,
    "execution": {
      "mode": "agent",
      "prompt": "TRAVEL INTELLIGENCE TASK: pre-departure (T-4h)\n\nCONTEXT:\nFact #14: Nikhil Thorat flying BOS→SFO, B6 0933, 1:59 PM EDT today\nContact: +16175551234\n\nGATHER:\n1. Flight status: `uv run ~/.claude/skills/flight-tracker/scripts/track.py B6-0933 --json` → gate, delays, status\n2. Weather at BOS: search web for 'Boston weather now'\n3. Drive time to Logan: search web for 'drive time to Logan airport from Boston now'\n\nCOMPOSE:\n✈️ BOS→SFO in 4 hours (B6 0933, 1:59 PM)\n• Flight: {status}, Gate {gate}\n• Leave by {depart_time - drive_time - 90min buffer} — {drive_time} drive\n• Weather: {temp}°F, {conditions}\n\nSELF-REVIEW:\n- Max 4-5 lines. Every line must be actionable.\n- 'Leave by X' is the key insight — compute it from drive time + 90 min airport buffer.\n- Times in EDT (contact's home timezone).\n- If nothing is different from what they already know, make it even shorter.\n\nSEND:\nInject into foreground session for +16175551234. If no session, use send-sms.\n\nFALLBACK:\nIf flight-tracker fails: '✈️ B6 0933 BOS→SFO departs 1:59 PM. Check JetBlue app for gate info.'"
    }
  }
}
```

### Data Sources

The agent fetches data using its existing skills and web access. No dedicated CLIs needed:

| Data needed | How agent gets it |
|------------|------------------|
| Flight status, gate, delays | `uv run ~/.claude/skills/flight-tracker/scripts/track.py {flight} --json` |
| Weather (current + forecast) | Web search ("SF weather today") or Open-Meteo API via webfetch |
| Drive time to airport | Web search ("drive time Boston to Logan airport") or Google Maps via chrome |
| Nearby places/restaurants | `goplaces nearby --location "{lat},{lng}" --type restaurant` |
| Airline check-in URL | Static lookup in travel-intelligence SKILL.md |
| Airport timezone | Static lookup in travel-intelligence SKILL.md |

**Data source reliability:**
- ✅ **Reliable**: FlightAware (flight-tracker CLI), web weather, Google Places
- ✅ **Reliable (static)**: Airline check-in URLs, airport timezones
- ⚠️ **Best-effort**: Drive time (depends on web search quality), TSA waits
- 🚫 **Not fetchable**: Baggage carousel, upgrade pricing — agent says "check airline app"

## Reminder Lifecycle Management

### On fact.created
- Create all reminders for the trip (per-leg, with dedup)
- Tag each reminder with `fact_id` + `template_name` + `leg_index` in metadata
- Start flight status watch (continuous polling reminders)

### On fact.updated
- If dates changed: cancel old reminders, create new ones
- If details changed (new hotel, different flights): update reminder prompts
- If legs added/removed: reconcile reminder set

### On fact.expired
- Cancel all unfired reminders associated with this fact
- Stop flight status watch

### Idempotency
- Use `fact_id` + `template_name` + `leg_index` as reminder dedup key
- Re-creating reminders for same fact replaces existing ones
- Check-in dedup: same-airline legs on same departure day → single T-24h reminder keyed by `fact_id` + `checkin` + `departure_date`

## Message Count Budget

For a **typical 5-day domestic round-trip** (2 legs, no layover):

| Moment | Count | Notes |
|--------|-------|-------|
| T-1 day packing | 1 | |
| T-24h check-in (outbound) | 1 | |
| T-4h pre-departure | 1 | |
| T-1h gate update | 0-1 | Delta-only, often suppressed |
| On landing | 1 | |
| Daily mornings (days 2-4) | 3 | Day 1 = on-landing, day 5 = checkout |
| Check-out / last morning | 1 | Merged with daily |
| T-24h check-in (return) | 0-1 | Deduped if check-out morning covered it |
| T-4h pre-return | 1 | |
| T-1h gate update (return) | 0-1 | Delta-only |
| Flight cancellation/delay | 0 | Hopefully! |
| **Total** | **9-12** | **~2/day average** |

For a **3-leg trip with layover** (BOS→ORD→SFO, return SFO→BOS):
- Adds: 1 layover connection msg, 1 extra pre-departure (ORD→SFO), 1 extra on-landing (ORD)
- Check-in: still 1 (same airline, same day)
- **Total**: ~12-15 messages. Acceptable.

## Example SMS Messages

**Check-in (T-24h):**
> ✅ Check-in opens now for B6 0933 BOS→SFO (tomorrow 1:59 PM)
> Check in: jetblue.com/check-in
> Seat 4A (window, Business)

**Pre-departure (T-4h):**
> ✈️ BOS→SFO in 4 hours (B6 0933, 1:59 PM)
> • Flight: On time, Gate B15
> • Leave by 10:00 AM — 22 min drive (light traffic)
> • Weather in Boston: 45°F, partly cloudy

**Gate update (T-1h, delta-only — something changed):**
> ⚠️ Gate changed: B15 → B22. Flight still on time.

**Gate update (T-1h, delta-only — nothing changed):**
> ✈️ Still on time, Gate B15. Boarding ~1:30 PM.

**Flight cancellation (immediate):**
> 🚨 B6 0933 BOS→SFO CANCELLED
> • Next JetBlue BOS→SFO: B6 0937 at 5:30 PM (seats available)
> • JetBlue rebooking: 1-800-538-2583
> • Check jetblue.com for rebooking options

**On landing:**
> 🛬 Welcome to San Francisco!
> • 62°F, sunny (high 68°F today)
> • Drive to Hotel Nikko: 25 min via 101
> • You're now 3 hours behind Boston (6:54 PM → 3:54 PM here)
> • BART to downtown: ~$10, 30 min (alternative to driving)

**Daily morning (day 2):**
> 🌤️ SF Day 2 — Tuesday Mar 31
> • 65°F / 52°F, 10% rain
> • Near Hotel Nikko: Tartine Bakery (0.3 mi, ⭐4.7), SFMOMA (0.5 mi)

**Packing weather (T-1 day):**
> 🧳 SF trip weather (Mar 29 – Apr 3):
> • Highs 62-68°F, Lows 48-54°F
> • Rain on days 3-4 (40-60%) — bring umbrella
> • Hotel Nikko check-in: 3:00 PM

**Check-out / last morning (merged):**
> 🏨 Last day in SF — check out by 11 AM
> • B6 0434 SFO→BOS at 9:00 AM
> • ✅ Check in now: jetblue.com/check-in
> • Leave for SFO by 6:30 AM — 25 min drive
> • Weather in Boston: 38°F, rain tonight

## Implicit Trip Enrichment (Nightly)

During an active trip (starts_at ≤ today ≤ ends_at), the nightly fact extraction gets **trip-aware context** so it picks up implicit details from daily conversation.

### How It Works

1. `consolidate_facts.py` already scans today's messages per contact
2. **NEW**: Before extraction, query facts table for active travel facts for this contact
3. If active trip exists, inject trip-aware context into the extraction prompt:

```
ACTIVE TRIP CONTEXT:
This contact is currently on a trip to San Francisco (fact #14, Mar 29 – Apr 3).
Known details: Hotel Nikko (222 Mason St), flights B6 0933/B6 0434, Business class.

When you see implicit trip details in today's messages, extract them as updates to fact #14.
Look for: hotel changes, restaurant/venue discoveries, schedule additions, transportation
changes, trip date changes, people met, local preferences learned.

Use "updated_facts" with existing_fact_id=#14 to enrich the details field.
Use "new_facts" for new events/activities that deserve their own fact.
```

### Categories of Implicit Extractions

| What user says | Extraction | Action |
|---------------|-----------|--------|
| "checking into Hotel Zetta" | Hotel name → geocode → update details.hotel | Update fact, recompute drive times in daily intel |
| "grabbed dinner at Tartine, amazing" | New fact: type=recommendation, details={name, location, rating} | Stored for future trip recs + CLAUDE.md |
| "meeting Sam at Salesforce Tower 2pm Mon" | New fact: type=event, starts_at=Mon 2pm, details={venue, contact} | Auto-creates T-2h reminder |
| "flight delayed 45 min" | Update leg status in fact details | Reconcile downstream reminders (on-landing, connections) |
| "renting a car from Hertz at SFO" | New fact: type=rental_car, details={company, location, linked_trip=#14} | Creates pickup/return reminders |
| "extending through Sunday" | Update fact ends_at, add new daily intel reminders | Reconcile reminder set |
| "the BART is way easier than driving" | New fact: type=preference, details={domain: "transport", value: "prefers BART in SF"} | Future trip recs |
| "coffee with Sarah from Google" | New fact: type=contact_met, details={name, company, context} | Contact memory enrichment |

### Immediate vs. Nightly Enrichment

Some updates need to happen **immediately** (via the foreground session), not wait for nightly:

| Update type | Timing | Why |
|------------|--------|-----|
| Flight delay/cancellation | **Immediate** (session detects and acts) | Safety-critical, can't wait for nightly |
| Trip date change | **Immediate** (reminders need reconciliation) | Downstream reminders affected |
| Hotel change | **Nightly OK** (next daily intel uses it) | Not time-sensitive |
| Restaurant rec | **Nightly OK** (stored for future use) | Informational only |
| New event/meeting | **Immediate** (needs reminder creation) | Time-sensitive if event is tomorrow |
| Preference learned | **Nightly OK** | Long-term memory |

The foreground session handles immediate updates by calling `fact update` or `fact save` directly when it detects time-sensitive changes in conversation. The nightly pass catches everything else.

### Extraction Prompt Enhancement

Add to `consolidate_facts.py`'s extraction prompt when active trip exists:

```python
def build_trip_aware_context(contact: str) -> str:
    """If contact has an active trip, build trip-aware extraction context."""
    active_trips = get_active_travel_facts(contact)
    if not active_trips:
        return ""

    trip = active_trips[0]  # Primary active trip
    details = trip.get("details", {})

    context = f"""
ACTIVE TRIP CONTEXT:
This contact is currently on a trip (fact #{trip['id']}).
Summary: {trip['summary']}
Dates: {trip['starts_at']} to {trip['ends_at']}
"""
    if details.get("hotel"):
        context += f"Hotel: {details['hotel'].get('name', 'unknown')}\n"
    if details.get("legs"):
        for i, leg in enumerate(details["legs"]):
            context += f"Leg {i}: {leg.get('flight', '?')} {leg.get('from')}→{leg.get('to')}\n"

    context += """
Look for implicit trip details in today's messages:
- Hotel mentions (checking in, moving to different hotel)
- Restaurant/venue discoveries (good places, recommendations)
- Schedule additions (meetings, dinners, activities with times)
- Transportation changes (delays, cancellations, rental cars)
- Trip date changes (extending, cutting short)
- People met (names, companies, context)
- Local preferences (transport modes, neighborhoods, tips)

For trip detail updates: use "updated_facts" with existing_fact_id={trip_id}.
For new events/activities: use "new_facts" with appropriate fact_type.
"""
    return context
```

## Implementation Plan

| Phase | What | Effort | Depends on |
|-------|------|--------|------------|
| **1a** | Extend fact details schema for `legs[]` with airline, seat, booking_ref fields | Small | Nothing |
| **1b** | Static data tables in travel-intelligence SKILL.md (check-in URLs, airport timezones) | Small | Nothing |
| **2** | FactReminderConsumer (bus consumer) with adaptive timing + quiet hours | Medium | 1a, 1b |
| **3** | Agent prompt templates per moment (with self-review step) | Medium | 2 |
| **4** | Delta-only suppression (state files + comparison logic) | Medium | 3 |
| **5** | On-landing polling mechanism | Medium | 2 |
| **6** | Flight status watch (cancellation/major delay alerting) | Medium | 2 |
| **7** | Reminder lifecycle (update/cancel on fact changes) | Medium | 2 |
| **8** | Non-travel fact types (events, visitors, rental car, appointments) | Medium | 2 |
| **9** | Implicit trip enrichment in nightly extraction (trip-aware context) | Small-Medium | Structured Facts (done) |

Phases 1a/1b are parallel and small. Phase 2 is the core consumer. Phases 3-8 build on top. Phase 6 (flight cancellation) should be prioritized as safety-critical. Phase 9 can start independently.

**No dedicated weather or drive-time CLIs needed.** The ephemeral agent uses its existing skills (chrome-control, webfetch, flight-tracker, places) to fetch data on the fly.

## Deferred / Future

- Hotel lookup from email confirmations (Gmail integration)
- Airline upgrade monitoring between booking and departure
- Delay compensation auto-filing (EU flights, 3+ hour delays)
- Rebooking intelligence on cancellation (show alternative routes, not just same airline)
- Smart home integration on return ("thermostat set to X, arriving in 2 hours")
- Currency exchange rates for international trips
- Restaurant reservations near hotel via OpenTable
- Jet lag tips for long-haul international travel
- Group travel coordination (multiple travelers, same trip)
- Multi-city trip support (different hotels per segment, location-aware daily intel)
- Lounge access lookup based on credit card benefits
- "Leave by X" with calendar integration (check if meetings before departure)
