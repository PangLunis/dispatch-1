---
name: vacation-house
description: Track ski house search in Vermont. Criteria, websites, properties, timing strategy. Use when discussing vacation home buying.
---

# Vacation House Search

Nikhil & Caro are looking to buy a ski house in the next 1-2 years.

## Search Criteria

| Requirement | Details |
|-------------|---------|
| **Bedrooms** | 3+ minimum |
| **Bathrooms** | 3+ full minimum |
| **Land** | 10+ acres minimum |
| **Water** | Pond or lake frontage (huge bonus) |
| **Location** | **Vermont ONLY** |
| **Ski access** | Max 45 min to a ski mountain. **Killington is the #1 priority mountain.** |
| **Property type** | Houses only — **NO vacant land, lots, or land-only listings** |
| **Setting** | Rural, dark skies (no main streets) |

## Caroline's Aesthetic (THE VIBE)

Caroline has specific taste. Properties MUST match this vibe:

### Interior Requirements
- **Log cabin / rustic construction** - exposed beams, post-and-beam, hand-hewn wood
- **Warm natural materials** - wood floors, stone fireplaces, quality hardwoods
- **Vaulted/cathedral ceilings** - open, dramatic feel
- **Character** - not cookie-cutter, unique details welcome

### Exterior/Setting Requirements
- **Mountain views** - Green Mountains, Adirondacks, etc.
- **Water features** - lake frontage, pond, waterfall, stream
- **"Wild" feel** - private, nature-immersed, adventurous character
- **Dark skies** - rural enough to see stars

### Reference Properties (Caroline's Picks)
These are the gold standard - match this energy:

1. **187 East Hill Rd, Woodbury VT** - $1.25M
   - LOG HOME with exotic hardwoods (Brazilian cherry, mahogany)
   - 218 ACRES with WATERFALL + trail system
   - Private dock + beach on Woodbury Lake
   - "Wild" energy - this is the unicorn benchmark

2. **206 Conway Rd, Starksboro VT** - $726.5K
   - Post-and-beam log home, 28ft vaulted ceilings
   - 30 acres with 1-acre spring-fed pond
   - Guest cabin + 3 fire pits + pavilion
   - Views of Adirondacks, Green Mtns, Lake Champlain
   - Only 2 baths (below minimum) but perfect vibe

## Best Search Websites

### Regional Specialists
- **[Coldwell Banker Lifestyles](https://www.thecblife.com)** - Covers VT/NH/ME ski + waterfront
- **[LakeHomes.com Vermont](https://www.lakehomes.com/vermont)** - Vermont lakes specifically
- **[NH Lakes Realty](https://www.nhlakesrealty.com)** - New Hampshire lakes specialist
- **[Hickok & Boardman](https://www.hickokandboardman.com)** - VT waterfront land
- **[Badger Peabody & Smith](https://www.badgerpeabodysmith.com)** - NH/VT/ME coverage
- **[Lakes Region ME/NH](https://www.lakesregionmenh.com)** - Maine/NH lakes region

### MLS & Broader Platforms
- **[PrimeMLS](https://primemls.com)** - The actual NH/VT MLS
- **[Redfin waterfront filter](https://www.redfin.com/state/Vermont/waterfront)** - Good filtering options
- **[Zillow](https://www.zillow.com)** - Good for price history/comps

## Timing Strategy

| Season | Pros | Cons |
|--------|------|------|
| **Spring (Mar-May)** | Most inventory, can see property thaw | More competition |
| **Fall (Sep-Nov)** | Sellers motivated before winter | Less inventory |
| **Mud Season (April)** | Fewer lookers, potential deals | Roads can be rough |
| **Winter** | See heating costs/snow clearing | Limited inventory, hard to tour land |

**Recommendation**: Start actively looking spring 2027 for a fall 2027 close, or fall 2026 if something perfect comes up.

## Area Notes

### Vermont (ONLY state searched)
- **Killington/Okemo area** — **Primary target.** Strong short-term rental market, closest to Boston
- **Sugarbush/Mad River Valley** — More affordable entry, authentic VT vibe, good rentals
- **Stowe** — Most prestigious, strong appreciation, $$$ premium
- **Northeast Kingdom** — Most affordable, more remote, less rental income potential

### Ski Mountain Priority
**Killington is the #1 ski mountain.** Always list Killington distance first. The scraper enriches every listing with driving distances to 9 VT mountains:
1. Killington (always first)
2. Sugarbush
3. Stowe
4. Okemo
5. Stratton
6. Mount Snow
7. Jay Peak
8. Burke Mountain
9. Mad River Glen

**Ski distances must NEVER be "unknown".** The `enrich_ski_distances()` function uses `goplaces directions --from "addr1" --to "addr2" --mode drive --json` as a fallback when the main enrichment pipeline doesn't produce ski data. Requires `GOOGLE_PLACES_API_KEY` env var (read from keychain: `security find-generic-password -s google-api-key -w`).

## Properties of Interest

### Currently Tracking

| Property | Price | Beds/Baths | Acres | Water | Status | Notes |
|----------|-------|------------|-------|-------|--------|-------|
| 206 Conway Rd, Starksboro VT | $726,500 | 3/2 | 30.43 | 1-acre pond | Active | Beautiful but only 2 baths (below minimum) |

### Viewed / Passed

(none yet)

### Purchased

(none yet)

## Budget Notes

(To be discussed - what's the target range?)

## Short-Term Rental Strategy

Many buyers offset costs with seasonal rentals. Consider:
- Killington and Mount Snow have active STR markets
- Check local zoning before buying (some towns restrict Airbnb)
- A property manager typically takes 20-30%
- Peak rental: ski season (Dec-Mar) and fall foliage (Sep-Oct)

---

## Listing Enrichment Workflow

When you need detailed property info (water source, septic, heating, etc.) that isn't in the basic API:

### 1. Fetch Full Listing Text
```bash
# Get raw listing text from Redfin/Zillow
~/.claude/skills/vacation-house/scripts/listing-details "https://www.redfin.com/..."

# Or get structured JSON with basic field extraction
~/.claude/skills/vacation-house/scripts/listing-details --json "https://www.redfin.com/..."
```

### 2. Agent Parses Text
The CLI returns raw listing text. As an agent, you should extract:

| Field | Look For |
|-------|----------|
| **Water Source** | "well", "city water", "public water", "municipal" |
| **Sewer** | "septic", "city sewer", "public sewer" |
| **Heating** | "forced air", "baseboard", "radiant", "oil", "propane", "wood stove" |
| **Year Built** | "Built 1985", "Year built: 1985" |
| **Days on Market** | "45 days on Redfin", "Listed 2 months ago" |
| **Price History** | Previous sale prices, price reductions |
| **HOA** | Monthly/yearly fees |
| **Lot Features** | "pond", "stream", "frontage", "views", "trail" |

### 3. Update Listing in D1
```bash
# Update listing with enriched data
curl -X PATCH "https://plot-listings-api.nicklaudethorat.workers.dev/listings/<id>" \
  -H "Content-Type: application/json" \
  -d '{"water_source": "well", "sewer": "septic", "heating": "propane forced air"}'
```

### Example Agent Workflow
```
User: "tell me more about 156 W Lake Rd"

1. listing-details "https://www.redfin.com/VT/Wilmington/156-W-Lake-Rd..."
2. Parse text for water/septic/heating/year built
3. PATCH to listings API with enriched fields
4. Reply with findings
```

---

## Redfin CLI Tool

Custom CLI that extracts cookies from Chrome to bypass Redfin's bot protection.

### Commands

```bash
# Search for a property by address
redfin search "206 Conway Road, Starksboro VT"

# Get property details (beds, baths, sqft, lot size, taxes)
redfin details <property_id>

# Get Google Street View image
redfin streetview "address" --save /tmp/streetview.jpg

# Get aerial/satellite view
redfin aerial "address" --save /tmp/aerial.jpg --zoom 17
```

### How it works

1. Redfin blocks direct API access (403 Forbidden)
2. CLI finds open Redfin tab in Chrome (or opens one)
3. Extracts cookies including AWS WAF token
4. Uses cookies to authenticate API requests
5. Returns property data from Redfin's stingray API

---

## Sending Listings to Users

**CRITICAL: When sharing listing images with users via SMS/iMessage:**
- **DO NOT** use Chrome screenshots
- **DO** download listing images directly via `curl` and attach them
- Listing photos are available at `image_url` in unified-search JSON output
- Download to `/tmp/` and attach via `send-sms --image`

**ALWAYS include these in listing messages:**

1. **Driving distance from home:**
   - Home: **7 Eastburn St, Brighton, MA** (hardcoded)
   - JSON: `drive_from_home` → `miles`, `hours`, `minutes`
   - Format: `🚗 Xhr Ymin (Z mi) from Brighton`

2. **Driving distance to ski mountains:**
   - JSON: `ski_driving` → array of `{name, drive_miles, drive_minutes}`
   - Format: `⛷️ 28min to Burke, 36min to Cannon`

3. **Listing URL:**
   - JSON: `url` field
   - ALWAYS include clickable link so user can see full listing

Example listing message format:
```
GRAFTON VT - $599K
5 bed / 3 bath / 3,000 sqft
🚗 2hr 32min (117 mi) from Brighton
⛷️ 35min to Stratton, 40min to Okemo
🔗 zillow.com/homedetails/...
```

Example workflow:
```bash
# Run unified search (driving distances included automatically)
~/.claude/skills/vacation-house/scripts/unified-search search --max-price 1500000 --json --top 10

# Download listing image
curl -o /tmp/listing.jpg "https://photos.zillowstatic.com/fp/..."

# Send with attachment
~/.claude/skills/sms-assistant/scripts/send-sms --image /tmp/listing.jpg "chat_id" "message"
```

### Note on data sources

- Active listings show current price and status
- Properties not on market show public records data (last sale price, tax records)
- Street View often unavailable for rural roads

---

## Property Deep-Dive Workflow

When asked to dig deeper on a specific property, follow this workflow:

### 1. Get Aerial/Satellite Imagery
```bash
~/.claude/skills/vacation-house/scripts/redfin aerial "ADDRESS" --save /tmp/property-aerial.jpg
```

### 2. Try Street View (often unavailable for rural)
```bash
~/.claude/skills/vacation-house/scripts/redfin streetview "ADDRESS" --save /tmp/property-street.jpg
```

### 3. Scrape Full Listing Details via Chrome
```bash
# Open listing in Chrome
~/.claude/skills/chrome-control/scripts/chrome open "ZILLOW_URL"

# Get tab ID from output, then extract text
~/.claude/skills/chrome-control/scripts/chrome text <TAB_ID>
```

### 4. Key Data Points to Extract
- **Price history** - when listed, price changes, previous sales
- **Days on market** - long DOM = negotiation opportunity
- **Previous sale price** - compare to current ask (big markup = red flag)
- **Tax assessment** - often much lower than asking
- **Renovations mentioned** - justify price increase?
- **Lot details** - acreage, features, frontage
- **Year built** - newer = less maintenance
- **HOA fees** - if applicable
- **Heating type** - propane/oil costs add up

### 5. Send Findings
Format as a summary with:
- Aerial photo attachment
- "The Good" - positive features
- "The Numbers" - price, taxes, DOM, price history
- "Flags" - concerns, negotiation leverage

### Example Deep-Dive Message:
```
🔍 THE DIRT ON [PROPERTY]:

**The Good:**
• [acreage] acres with [features]
• Built [year]
• [notable features]

**The Numbers:**
• Listed [date] - [X] days on market
• Sold for $[X] in [year]
• Now asking $[X] ([%] markup)
• Zestimate: $[X]
• Taxes: ~$[X]/year

**Flags:**
• [negotiation leverage]
• [concerns]
```

---

## Search Session Archives

**IMPORTANT: Every search session MUST be saved to `~/Documents/vacation-houses/{YYYY-MM-DD}/`**

### Directory Structure
```
~/Documents/vacation-houses/
├── favorites.md               # MASTER favorites list (persists across sessions)
├── 2026-02-15/
│   └── search-results.md      # All properties from this session
├── 2026-02-16/
│   └── ...
```

### Favorites File (~/Documents/vacation-houses/favorites.md)
**IMPORTANT:** When Nikhil or Caroline say they like a property, IMMEDIATELY add it to `~/Documents/vacation-houses/favorites.md`

This is the master list of all properties they've expressed interest in, across all search sessions. Add properties here whenever they say things like:
- "I like this one"
- "This is the best"
- "Add this to favorites"
- "#2 is my favorite"
- etc.

### Required Fields for Each Property
Every listing saved must include:
1. **Address** - full address
2. **Price** - current asking price
3. **Beds/Baths/Sqft/Acres**
4. **Drive time from Brighton** - from 7 Eastburn St
5. **Drive time to nearest ski mountains**
6. **Days on market** - how long it's been listed
7. **Listing URL** - clickable link
8. **Notes** - why it matches/doesn't match the vibe

### Example search-results.md format:
```markdown
# Vacation House Search - 2026-02-15

## Properties Found

### 1. 1970 E Hubbardton Rd, Castleton VT
- **Price:** $949,000
- **Beds/Baths:** 4/3
- **Sqft:** 3,003 | **Acres:** 34
- **Drive from Brighton:** 2hr 30min
- **Ski:** ~30min to Killington
- **Days on Market:** 45
- **Link:** zillow.com/homedetails/...
- **Notes:** 1880 farmhouse, vineyard, 5 barns, pond, brook. CAROLINE FAVORITE.
```

---

## Nightly Scraper Pipeline

Runs as a **2am ET reminder** via the dispatch daemon's reminder system (NOT a LaunchAgent). The scraper **only collects data** — the skill handles presentation, publishing, and notification.

### Architecture: Scraper vs Skill

**Scraper** (`nightly-scraper` CLI) — data collection only:
- Discovery, dedupe, enrichment (scrapling), refinement (AI scoring), verification
- Outputs JSON with all listing data
- Archives to `~/Documents/vacation-houses/{date}/`

**Skill** (this document) — presentation and delivery:
- Generate HTML report from scraper JSON
- Publish to sven-pages for visual browsing
- Send SMS with summary + link to report
- The scraper should NOT format SMS or publish pages

### Pipeline Steps
1. **DISCOVERY**: `unified-search` across 6 VT sources: Redfin, Zillow, Hickok & Boardman, Coldwell Banker, **Ski Country Real Estate** (Killington specialist), **LandSearch VT** (houses with acreage). Houses only — Redfin uses `property-type=house`, Zillow filters out land/manufactured, Ski Country filters by beds/baths, LandSearch uses `type=house`.
2. **DEDUPE**: Compares against Cloudflare D1 database — skips already-seen listings
3. **ENRICHMENT**: Scrapling (webfetch) scrapes each listing page for detailed property info (acres, construction style, water features, year built, heating). Google Places API checks nearby POIs (fire stations, airports). **Use scrapling for all scraping — never claude CLI web search.**
3b. **PARCEL ENRICHMENT**: For each listing with lat/lon, fetch VCGI parcel data from `vcgi-cache-proxy.nicklaudethorat.workers.dev/parcel?lat=X&lng=Y`. Stores parcel geometry (GeoJSON polygon), assessed values (land + improvement), official acreage, SPAN, owner, town. Used for map overlays in the HTML report.
4. **REFINEMENT**: Each new listing scored 1-10 by Claude Opus (via `claude -p --model opus`) against:
   - **CRITICAL**: The refinement step reconstructs the listing dict from the AI response. ALL original fields (lat, lon, sqft, year_built, heating, VCGI parcel data) MUST be explicitly carried over — they are NOT automatically preserved.
   - Hard requirements (beds, baths, acres, ski proximity)
   - Caroline's vibe criteria (log cabin, rustic, water, views, character)
   - Similarity to the 2 favorite properties
5. **VERIFICATION**: Re-scrapes listing URL and cross-checks enriched data against source text to catch hallucinations. Downgrades score by 2 if verification fails.
6. **ARCHIVE**: All results saved to `~/Documents/vacation-houses/{date}/nightly-scraper-results.md`

### "Good to Know" Enrichment

Every listing gets nearby POI checks via Google Places:
- **Fire stations** — proximity is GOOD for rural properties (safety), but being right next to one is bad (noise/sirens)
- **Airports** — nearby airports are bad (noise), regional airports are neutral info
- **Town info** — construction style, year built, heating type, water source from listing scrape

### Publishing Results (sven-pages + frontend skill)

**Instead of cramming results into SMS, publish a beautiful visual HTML report.**

Use the **bus dashboard design pattern** — the same warm papery aesthetic from the Dispatch Bus dashboard:

**Design System (MUST follow):**
- **Typography**: Space Grotesk (sans-serif) + JetBrains Mono (monospace) via Google Fonts
- **Color palette**: Warm papery `#f7f5f2` base, sepia-tinted grays, single accent `#c2410c` (signal orange)
- **CSS variables**: `--ink`, `--ink-secondary`, `--ink-tertiary`, `--surface-0/1/2`, `--signal-orange/green/red/blue`
- **Stats strip**: Large numbers (36px) with 1px grid dividers
- **Section titles**: 11px uppercase, `letter-spacing: 1.5px`, muted color with bottom border
- **Callout boxes**: Left-border accent + soft background tint
- **Staggered entry animations**: `fadeSlideUp` with delay classes
- **Mobile-responsive**: Breakpoints at 768px and 400px. Must include `<meta name="viewport" content="width=device-width, initial-scale=1.0">`. Stack maps vertically on mobile, smaller fonts, tighter padding.
- **Coordinates**: Pipeline outputs `lat` and `lon` (NOT `lng`). HTML JS should check `l.lat && (l.lon || l.lng)` and use `l.lon || l.lng` for MapLibre longitude.

**Report must include:**
1. Header with title + date window (JetBrains Mono)
2. **Executive summary** — lead with what matters: "No unicorns today" or "1 amazing find." Write 2-3 sentences about the best listings in plain language, not pipeline metrics. Do NOT show verification counts, enrichment rates, or pipeline internals at the top. The reader wants to know: "did we find a house?"
3. Stats strip — user-facing metrics only: Must-See count, Worth a Look count, Interesting count, Total Scanned, States
4. **Best find callout** — highlight the single best listing with a link to jump to its card
5. **Featured listing cards** for enriched properties, each with:
   - **Photo carousel** (10 photos from Redfin `bigphoto` URLs, swipeable with touch support)
   - Score circle badge (color-coded: green 5+, blue 4, amber 3, red 1-2)
   - Verification status tag
   - Address as deep link to listing URL
   - **Cross-reference links row** below address: small inline links to search for the property on major real estate sites. Always include Redfin, Zillow, and Google Maps. Format: `<div class="card-xref">` with pipe-separated links like `Redfin | Zillow | Google Maps`. Generate URLs by encoding the address:
     - Redfin: `https://www.redfin.com/search#query={encoded_address}`
     - Zillow: `https://www.zillow.com/homes/{encoded_address_with_dashes}_rb/`
     - Google Maps: `https://www.google.com/maps/search/{encoded_address}`
     - If the listing source IS Redfin or Zillow, use the actual listing URL for that site instead of a search URL
   - Price in JetBrains Mono + signal orange
   - Meta row: beds, baths, sqft, acres, drive time, ski distance
   - Tags: construction style, water features, acreage, vibe match
   - **Parcel & Terrain Maps** (two side-by-side MapLibre GL maps per listing):
     - **Satellite + Parcel Overlay**: ESRI satellite imagery with VCGI parcel boundary polygon in blue
     - **Terrain Map**: AWS Terrarium terrain tiles with parcel boundary
     - **Use static tile images, NOT interactive MapLibre maps.** WebGL context limit (~16) is exceeded when rendering 40+ maps on one page. Static `<img>` tiles work everywhere including mobile.
     - Satellite tiles: `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}` (direct, not via proxy — proxy returns HTML without `/tile/` prefix)
     - OSM tiles: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`
     - Parcel data from VCGI via `vcgi-cache-proxy.nicklaudethorat.workers.dev`
     - Use `tileXY(lat, lon, zoom)` to convert coordinates to tile indices
   - **VCGI Parcel Info Row**: Assessed value (land + improvement), official acreage, SPAN, owner
   - Description paragraph
   - Good to Know (max 3 items)
   - Flags callout (red-tinted)
5. Quick reference table of ALL listings (sortable by score)
6. Score distribution bar chart
7. Footer with source info

**Photo scraping**: Fetch Redfin listing HTML via webfetch, extract `bigphoto` URLs with `grep -oE 'https://ssl\.cdn-redfin\.com/photo/.*/bigphoto/[^"]+' | sort -u | head -20`

**Parcel + Terrain Maps** (via MapLibre GL JS):
- Include MapLibre GL JS v4 (`unpkg.com/maplibre-gl@4.1.2`) in HTML `<head>`
- For each listing with `vcgi_geometry`, render TWO side-by-side map containers (200px height each):
  1. **Satellite + Parcel**: ESRI satellite tiles via `sven-plot-proxy.nicklaudethorat.workers.dev/satellite/{z}/{y}/{x}`
  2. **Terrain + Parcel**: AWS Terrarium terrain tiles via `sven-plot-proxy.nicklaudethorat.workers.dev/terrain/{z}/{x}/{y}.png`
- Add parcel boundary as GeoJSON source with fill (#3b82f6, opacity 0.2) and line (#3b82f6, width 2)
- Auto-fit bounds to parcel geometry with padding
- Show VCGI info below maps: assessed value, official acreage, SPAN
4. Publish to sven-pages:
   ```bash
   ~/.claude/skills/sven-pages/scripts/publish ./report-folder --name vacation-scraper-YYYY-MM-DD --public
   ```
4. SMS just sends a short summary + link:
   ```
   🏡 3 new listings today (top score: 8/10)
   ⭐ 187 East Hill Rd, Woodbury VT — $1.25M — 8/10
   🔹 206 Conway Rd, Starksboro VT — $727K — 7/10
   🔹 338 Percy Rd, Stark NH — $700K — 6/10

   Full report: https://sven-pages-worker.nicklaudethorat.workers.dev/vacation-scraper-2026-03-15/
   ```

### Model Policy

**ALL AI calls in the scraper MUST use opus.** Never haiku, never sonnet.
- Enrichment parsing: `claude -p ... --model opus`
- Refinement scoring: `claude -p ... --model opus`
- Verification: `claude -p ... --model opus`

### SMS Format Requirements

Every listing in SMS MUST include:
- Address + price
- Clickable listing URL (right below address, not buried)
- Ski distances (show "unknown" if not available, never omit)
- Score and vibe match
- Drive from Brighton
- NEVER truncate with "and X more" — link to full report instead

### Manual Run
```bash
# Full pipeline with SMS notification
~/.claude/skills/vacation-house/scripts/nightly-scraper --notify

# Dry run (no D1 sync, no SMS)
~/.claude/skills/vacation-house/scripts/nightly-scraper --dry-run

# Custom score threshold
~/.claude/skills/vacation-house/scripts/nightly-scraper --notify --min-score 7

# JSON output
~/.claude/skills/vacation-house/scripts/nightly-scraper --json
```

### Scheduling
Runs via the **dispatch daemon reminder system** at 2am ET daily (same batch as consolidation, skillify, bug finder). **NEVER create a LaunchAgent for this** — always use reminders.

```bash
# Check reminder status
claude-assistant remind list

# The reminder fires an agent-mode task that:
# 1. Runs the scraper CLI
# 2. Builds a beautiful HTML report (bus dashboard design)
# 3. Publishes to sven-pages
# 4. Sends SMS summary + link to the group chat
```

---

*Last updated: 2026-03-15*
