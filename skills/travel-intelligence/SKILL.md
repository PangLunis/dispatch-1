---
name: travel-intelligence
description: Travel intelligence pipeline — proactive trip messages at key moments. Covers flight status, weather, airport info, gate updates, check-in reminders, landing intel, daily morning briefings. Triggers on travel, trip, flight, weather, airport, hotel, packing.
---

# Travel Intelligence Pipeline

Fact-driven proactive messages delivered at key trip moments. Each message is assembled from live data (flights, weather, places, facts) and injected into the contact's **foreground session** — never sent as standalone SMS.

---

## Message Templates

### 1. Check-in Reminder (T-24h before departure)

> ✈️ **Check-in open for {airline} {flight_number}**
> {origin_code} → {dest_code} · {depart_date} · {depart_time}
> Seat {seat} · Conf {booking_ref}
> 👉 {check_in_url}

**Data sources:**
- `~/dispatch/scripts/fact list --contact "{contact}" --json` — pull `legs[]` for flight, seat, booking_ref
- Check-in URL from static lookup (see [Airline Check-in URLs](#airline-check-in-urls))

**Fallback:** If seat or booking_ref missing, omit those lines. Always send the check-in link.

---

### 2. Packing Weather (T-1 day, morning)

> 🧳 **Packing weather for {dest_city}**
> {day1}: {icon} {high}°/{low}°F — {summary}
> {day2}: {icon} {high}°/{low}°F — {summary}
> {day3}: {icon} {high}°/{low}°F — {summary}
> 💡 {packing_tip}

**Data sources:**
- `~/.claude/skills/weather/scripts/weather` — 3-day forecast for destination coords
- Generate packing tip from forecast (e.g., "Pack layers — 30°F swing" or "Rain gear for Thursday")

**Fallback:** If weather unavailable, send: "Couldn't pull forecast for {dest_city} — check weather.gov before packing."

---

### 3. Pre-departure (T-Xh, X = drive_time + 2h buffer for domestic, +3h international)

> 🚗 **Leave by {leave_by_time} for {origin_airport}**
> Drive: ~{drive_minutes} min via {route_summary}
> Flight: {airline} {flight_number} departs {depart_time} from {terminal}/{gate}
> Status: {flight_status} · {delay_info_or_"On time"}

**Data sources:**
- `uv run ~/.claude/skills/flight-tracker/scripts/track.py {flight} --json` — status, gate, terminal, delay
- Drive time: Google Maps (coming soon) — use fact-stored estimate as fallback
- `~/dispatch/scripts/fact list --contact "{contact}" --json` — origin address, airport

**Fallback:** If drive time unavailable, omit drive line and say "Head to {origin_airport} — {airline} {flight_number} departs {depart_time}." If flight status unavailable, omit status line.

**Leave-by calculation:** `leave_by = depart_time - drive_minutes - buffer` where buffer = 120 min domestic, 180 min international.

---

### 4. Gate Update (T-1h, delta-only)

> 🔄 **Gate change: {airline} {flight_number} now Gate {new_gate}** ({terminal})

Or if delay:

> ⏱️ **{airline} {flight_number} delayed {delay_minutes} min — new depart {new_depart_time}** · Gate {gate}

**Data sources:**
- `uv run ~/.claude/skills/flight-tracker/scripts/track.py {flight} --json`

**Delta-only rule:** Compare current gate/time against last-sent values. If nothing changed, **suppress entirely** — do not send a "no changes" message. If only minor delay (<10 min), send a single line.

---

### 5. Flight Cancellation

> 🚨 **{airline} {flight_number} CANCELLED**
> Was: {origin_code} → {dest_code} at {original_depart_time}
> 📞 {airline} rebooking: {airline_phone}
> 👉 {airline_manage_booking_url}

**Data sources:**
- `uv run ~/.claude/skills/flight-tracker/scripts/track.py {flight} --json`
- Airline phone/URL from static lookup

**Behavior:** Send immediately on detection, regardless of quiet hours. This is the one exception.

---

### 6. On Landing

> 🛬 **Welcome to {dest_city}!**
> Local time: {local_time} ({tz_name}, {tz_delta} from home)
> Weather: {icon} {temp}°F — {summary}
> 🏨 {hotel_name} — {hotel_address}
> 🍽️ Nearby: {restaurant_1}, {restaurant_2}, {restaurant_3}

**Data sources:**
- `~/.claude/skills/weather/scripts/weather` — current conditions at destination
- `~/dispatch/scripts/fact list --contact "{contact}" --json` — hotel name/address
- `goplaces nearby --location "{lat},{lng}" --type restaurant --json` — top 3 nearby restaurants
- Time zone delta: compute from origin and destination tz

**Fallback:** Omit any section whose data source fails. At minimum send the welcome line + local time.

---

### 7. Daily Morning Intel (each morning at destination)

> ☀️ **{dest_city} · {day_of_week} {date}**
> {icon} {high}°/{low}°F — {summary}
> 📅 {agenda_or_"No plans on file"}
> 💡 {tip_of_the_day}

**Data sources:**
- `~/.claude/skills/weather/scripts/weather` — today's forecast
- `~/dispatch/scripts/fact list --contact "{contact}" --json` — any stored agenda items
- Tip: contextual (e.g., "Hotel checkout is at {checkout_time}" on last full day)

**Frequency cap:** Daily for first 7 days, then every-other-day for longer trips.

**Fallback:** If weather fails, send "Good morning from {dest_city}!" with whatever data is available.

---

### 8. Check-out / Last Morning (merged)

> 🏨 **Last day in {dest_city} — checkout by {checkout_time}**
> {icon} {temp}°F — {summary}
> ✈️ {airline} {flight_number} departs {depart_time} · leave by {leave_by_time}
> 🧳 Don't forget: chargers, toiletries, safe contents

**Data sources:** Combination of weather, flight tracker, and facts (checkout time, return flight).

**Fallback:** If return flight unknown, omit flight line. Always include checkout reminder.

---

## Tool Reference

| Tool | Command | Notes |
|------|---------|-------|
| **Weather** | `~/.claude/skills/weather/scripts/weather` | Open-Meteo based, coming soon |
| **Flight status** | `uv run ~/.claude/skills/flight-tracker/scripts/track.py {flight} --json` | Returns gate, terminal, delay, status |
| **Places** | `goplaces nearby --location "{lat},{lng}" --type restaurant --json` | Google Places via CLI |
| **Facts** | `~/dispatch/scripts/fact list --contact "{contact}" --json` | Contact trip facts |
| **Drive time** | Google Maps API | Coming soon — use stored estimate as fallback |

### Airline Check-in URLs

| Code | Airline | Check-in URL |
|------|---------|-------------|
| B6 | JetBlue | jetblue.com/check-in |
| UA | United | united.com/en/us/check-in |
| AA | American | aa.com/check-in |
| DL | Delta | delta.com/check-in |
| WN | Southwest | southwest.com/air/check-in/ |
| AS | Alaska | alaskaair.com/check-in |
| NK | Spirit | spirit.com/check-in |
| F9 | Frontier | flyfrontier.com/check-in |
| HA | Hawaiian | hawaiianairlines.com/check-in |
| SY | Sun Country | suncountry.com/check-in |

For international carriers, search `{airline_name} online check-in` at send time.

---

## Fact Schema Reference

Trip data lives in the contact's fact store. Expected structure:

```json
{
  "trip": {
    "destination": "Austin, TX",
    "dest_coords": "30.2672,-97.7431",
    "dest_tz": "America/Chicago",
    "dates": "2026-03-20 to 2026-03-24",
    "purpose": "SXSW"
  },
  "legs": [
    {
      "direction": "outbound",
      "airline": "B6",
      "flight_number": "B6 1234",
      "origin": "BOS",
      "destination": "AUS",
      "depart_time": "2026-03-20T08:30-05:00",
      "arrive_time": "2026-03-20T12:15-06:00",
      "seat": "12A",
      "booking_ref": "XYZABC",
      "class": "economy"
    },
    {
      "direction": "return",
      "airline": "B6",
      "flight_number": "B6 5678",
      "origin": "AUS",
      "destination": "BOS",
      "depart_time": "2026-03-24T17:00-06:00",
      "arrive_time": "2026-03-24T23:30-05:00",
      "seat": "14F",
      "booking_ref": "XYZABC",
      "class": "economy"
    }
  ],
  "hotel": {
    "name": "Hotel San José",
    "address": "1316 S Congress Ave, Austin, TX 78704",
    "coords": "30.2490,-97.7488",
    "check_in": "15:00",
    "check_out": "11:00",
    "confirmation": "HSJ-98765"
  },
  "home": {
    "address": "123 Main St, Somerville, MA",
    "airport": "BOS",
    "drive_minutes_to_airport": 25,
    "tz": "America/New_York"
  }
}
```

Fields are optional. The pipeline sends whatever it can assemble — partial data beats no data.

---

## Key Principles

1. **Session-injected, not standalone.** Messages are injected into the contact's foreground session via `inject-prompt`. The user can reply conversationally to update facts (e.g., "actually I'm in seat 14C now").

2. **Delta-only at T-1h.** Gate update messages suppress entirely if nothing changed. No "everything looks good!" noise.

3. **Always send partial data.** If weather API is down but flight data works, send what you have. Never skip a moment because one source failed.

4. **Leave-by time in pre-departure.** Always compute: `departure_time - drive_time - buffer`. Buffer = 2h domestic, 3h international.

5. **Time zone delta on landing.** Show the offset from home so the user can mentally adjust ("3h behind home").

6. **Frequency cap on daily intel.** Days 1-7: daily. Day 8+: every other day. Prevents fatigue on long trips.

7. **Quiet hours: 11 PM - 6 AM local time.** Queue messages and deliver at 6 AM. Exception: flight cancellations send immediately.

8. **Facts are conversational.** The user can text trip details naturally ("flying B6 1234 on Thursday, seat 12A") and the session stores them as structured facts for the pipeline to consume.

9. **Self-review before sending.** Before sending any travel intel message, re-read it and check:
   - Is it under 5 lines? If not, cut the least important line.
   - Does every line contain actionable info? Remove fluff ("have a great flight!" = fluff).
   - Are times in the contact's local timezone?
   - No duplicate info from a previous alert?
   If the message fails self-review, revise and re-check once.

10. **No dedicated CLIs.** Use existing skills (flight-tracker, chrome-control, webfetch, places) to fetch weather, drive times, and other data. No weather CLI or drive-time CLI needed — just search the web.
