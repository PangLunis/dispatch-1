---
name: dj-buyer
description: Search and purchase DJ tracks from Bandcamp, Beatport, and Amazon Music using scrapling. Trigger words - dj, track, buy track, search track, bandcamp, beatport, amazon music, purchase music, dj buyer, find track.
---

# DJ Buyer

Search for and purchase DJ tracks across Bandcamp, Beatport, and Amazon Music.

**Project**: `~/code/dj-buyer/`
**Run all commands with**: `cd ~/code/dj-buyer && uv run dj-buyer <command>`

## Search Workflow

### Pre-search: Check if already purchased

**ALWAYS check the purchases database before searching or buying a track.** This avoids duplicate purchases.

```bash
cd ~/code/dj-buyer && sqlite3 state.db "
SELECT t.artist, t.title, p.platform, p.price, p.purchased_at, p.download_path
FROM purchases p JOIN tracks t ON p.track_id = t.id
WHERE lower(t.artist) LIKE lower('%ARTIST%') AND lower(t.title) LIKE lower('%TITLE%');
"
```

Also check if the track file already exists in the library:
```bash
ls ~/Music/dj-buyer/*ARTIST*TITLE* 2>/dev/null
```

If the track is already purchased, skip searching and buying — just report that it's already owned.

### Reporting results

**ALWAYS show the source platform for every track result.** When presenting search results or cost estimates, include the platform name (Bandcamp, Beatport, or Amazon) next to each price. Example format:

```
✅ Artist - Title: $1.49 (Beatport)
✅ Artist - Title: $1.29 (Amazon)
✅ Artist - Title: $0.00 (Bandcamp, name-your-price)
❌ Artist - Title: NOT FOUND
```

This helps the user understand where each track will be purchased from and compare options.

### Search all platforms

**Always search ALL 3 platforms, then rerank by price and similarity to find the best deal.**

```bash
cd ~/code/dj-buyer && uv run dj-buyer search-bandcamp "Artist" "Title" --json
cd ~/code/dj-buyer && uv run dj-buyer search-beatport "Artist" "Title" --json
cd ~/code/dj-buyer && uv run dj-buyer search-amazon "Artist" "Title" --json
```

Or search all at once: `cd ~/code/dj-buyer && uv run dj-buyer search "Artist" "Title"`

### How to Rerank Results

After collecting results from all 3 platforms:

1. **Filter**: Drop anything with similarity < 0.7
2. **Verify**: For similarity 0.7-0.9, manually check artist+title match
3. **Cover detection**: Bandcamp is indie/electronic-focused. When searching mainstream artists, results are frequently covers by different artists with misleadingly high title similarity (0.7+). If the Bandcamp result artist doesn't match the search artist, skip it even if title similarity is high. Prefer Beatport or Amazon for major-label tracks.
4. **Platform preference**: Always prefer Bandcamp or Beatport over Amazon. Only use Amazon if the track doesn't exist on either Bandcamp or Beatport.
5. **Price rank** (within preferred platforms): Bandcamp name-your-price ($0) > Bandcamp minimum ($1) > Beatport MP3 ($1.49) > Beatport WAV ($2.49)
6. **DJ quality tiebreak**: If prices are close, prefer Beatport (best metadata + artwork)
7. **Amazon fallback**: Only purchase from Amazon ($1.29) when the track is unavailable on both Bandcamp and Beatport

See `search/bandcamp.md`, `search/beatport.md`, `search/amazon.md` for platform-specific matching guidance.

### Fallback: Web search for NOT FOUND tracks

**If a track returns NOT FOUND from all 3 platform scrapers, do a web search before giving up.** The scrapers sometimes miss tracks that exist — Amazon's digital music search in particular often returns irrelevant products (supplements, books) instead of music results.

Fallback steps:
1. **Web search**: `WebSearch` for `"Artist" "Title" buy MP3 download`
2. **Check results for known platforms**:
   - `music.amazon.com/tracks/BXXXXXXXXX` → Amazon ASIN exists, purchasable at ~$1.29
   - `beatport.com/track/...` → Beatport link, $1.49
   - `bandcamp.com` links → Bandcamp, check price on page
   - `music.apple.com` → Apple Music/iTunes, note as alternative
3. **Direct Amazon Music lookup**: If web search finds an Amazon Music ASIN (e.g. `B0D5L6L2XH`), navigate directly to `https://www.amazon.com/dp/ASIN` — the scraper's keyword search often fails but the product page exists
4. **Beatport low-similarity matches**: If Beatport returns the right artist + right title but low similarity (e.g. 0.6) because of suffixes like "(Extended Mix)" or "(Original Mix)", it's likely the correct track. Verify manually and accept it.

**Never report a track as NOT FOUND without trying the web search fallback first.**

## Bandcamp Purchase — Step-by-Step Chrome Commands

**No CLI command for this.** Drive Chrome directly using the chrome-control skill. The UI changes frequently so adapt as needed — take screenshots and read page text to understand what you're looking at.

**Payment**: PayPal account ($(security find-generic-password -s "assistant" -a "email" -w)) linked to Privacy.com Mastercard. Direct card payment does NOT work (Spreedly rejects Privacy.com BINs).

**Billing address**: 02135 (Brighton, MA)

### CSP Warning

Bandcamp and PayPal both have strict CSP. Normal `chrome js`, `chrome click`, `chrome read`, `chrome find` all fail. You MUST use these CSP-bypass commands:

| Command | Use for | Notes |
|---------|---------|-------|
| `chrome iframe-click <tab> <selector>` | Click elements via CSS selector or `text:XXX` | Returns `{'success': True}` or `{}` if not found |
| `chrome insert-text <tab> <text>` | Type into focused input | Must click/focus first |
| `chrome click-by-name <tab> <name>` | Click by accessible name | Uses accessibility API, best for buttons |
| `chrome text <tab>` | Read page text | Works despite CSP |
| `chrome html <tab>` | Get full page HTML | Works despite CSP |
| `chrome screenshot <tab>` | Take screenshot | For debugging |
| `chrome key <tab> <key>` | Send keypress (Tab, Return, etc) | Works despite CSP |

For native `<select>` dropdowns (like city selector), none of the above work. Use `debugger-eval` via direct socket:

```python
import json, socket, glob
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect(glob.glob("/tmp/chrome_control_*.sock")[0])
sock.settimeout(30)
code = """
var sel = document.querySelector('select[name="city"]');
sel.value = sel.options[1].value;
sel.dispatchEvent(new Event('change', {bubbles: true}));
'done'
"""
sock.sendall(json.dumps({"command": "debugger_eval", "params": {"tabId": TAB_ID, "code": code}}).encode())
data = b""
while b"\n" not in data:
    data += sock.recv(65536)
sock.close()
```

### Step 1: Open track page

```bash
chrome open "<bandcamp_url>"
# Returns tab ID, e.g. "Opened tab 1234567: https://..."
```

Wait 5-6 seconds for page load. Dismiss cookie banner if present:
```bash
chrome iframe-click <tab> "text:Accept all"
```

### Step 2: Click "Buy Digital Track"

```bash
chrome iframe-click <tab> "text:Buy Digital Track"
```

If it returns `{}`, retry after 2 seconds. May also try `chrome click-by-name <tab> "Buy Digital Track"`.

This opens a purchase dialog/modal/sidebar (UI varies).

### Step 3: Set price (optional, for name-your-price)

If the track is name-your-price and you want to set a custom amount:
```bash
chrome iframe-click <tab> "#userPrice"      # or input[name='userPrice']
chrome key <tab> "a" "meta"                 # Select all
chrome insert-text <tab> "1.00"             # Type price
chrome key <tab> "Tab"                      # Tab out to update
```

### Step 4: Navigate to checkout

Look for "Check out" or "Check out now" button. Use `chrome text` or `chrome screenshot` to see what's on screen.

```bash
chrome iframe-click <tab> "#sidecartCheckout"           # Cart sidebar link
# OR
chrome iframe-click <tab> "text:Check out now"          # Modal button
# OR
chrome iframe-click <tab> "text:Check out with PayPal"  # Direct PayPal option
```

**WARNING**: `click-by-name "Check out"` often hits a StaticText node instead of the actual link/button. Prefer `iframe-click` with CSS selectors or `text:` selectors.

### Step 5: Fill billing info

On the checkout/billing page, fill ZIP code and select city:

```bash
chrome iframe-click <tab> "input[id*='zip']"    # Focus ZIP input
chrome key <tab> "a" "meta"                      # Select all
chrome insert-text <tab> "02135"                 # Type ZIP
chrome key <tab> "Tab"                           # Tab out
```

Wait 2-3 seconds for the city dropdown to populate, then set city via debugger_eval (see socket code above). Look for a `<select>` with city options containing "Boston".

### Step 6: Proceed to PayPal

```bash
chrome iframe-click <tab> "text:Proceed to PayPal"
# OR
chrome click-by-name <tab> "Proceed to PayPal"
```

Wait 8-10 seconds for PayPal redirect.

### Step 7: PayPal login (if needed)

Check `chrome text <tab>` — if PayPal shows "Complete Purchase" or "Pay Now", you're already logged in (skip to Step 8).

If PayPal asks for login:
1. Enter email: `chrome iframe-click <tab> "input[type='email']"` → `chrome insert-text <tab> "$(security find-generic-password -s "assistant" -a "email" -w)"` → click Next
2. PayPal will send OTP via SMS to shortcode `70924`. Read it from Messages.app:
   ```sql
   sqlite3 "file:$HOME/Library/Messages/chat.db?mode=ro" \
     "SELECT text FROM message WHERE handle_id IN (SELECT ROWID FROM handle WHERE id LIKE '%70924%') ORDER BY date DESC LIMIT 1;"
   ```
3. Enter OTP code and submit

### Step 8: Complete purchase

```bash
chrome click-by-name <tab> "Complete Purchase"
# OR try: "Pay Now", "Agree & Pay", "Continue"
```

Wait 10-15 seconds for redirect back to Bandcamp.

### Step 9: Download MP3 V0

After purchase, get the download URL from the Bandcamp confirmation email:

```bash
# Search for latest Bandcamp receipt email
~/.local/bin/gws gmail users messages list --params '{"q": "from:bandcamp subject:Thank", "maxResults": 1, "userId": "me"}'

# Get the message body (extract text/plain part, base64 decode)
~/.local/bin/gws gmail users messages get --params '{"userId": "me", "id": "<MSG_ID>", "format": "full"}'
```

The email body contains a download URL like:
```
https://bandcamp.com/download?from=receipt&payment_id=XXXXX&sig=XXXXX
```

Open it in Chrome, get the HTML, and extract the direct download link:

```bash
chrome open "<download_url>"
# Wait 5 seconds
chrome html <tab>
# Parse HTML for: https://p*.bcbits.com/download/track/*/mp3-v0/*
```

The `<select id="format-type">` has options. MP3 V0 (`value="mp3-v0"`) is the first/default option.

Download via curl:
```bash
mkdir -p ~/Music/dj-buyer
curl -L -o ~/Music/dj-buyer/"Artist - Title.mp3" "<direct_bcbits_url>"
```

**Always download MP3 V0** — highest quality VBR MP3.

Verify the file:
```bash
file ~/Music/dj-buyer/"Artist - Title.mp3"
# Should show: Audio file with ID3 version 2.3.0, contains: MPEG ADTS, layer III
```

Close the Chrome tabs when done.

## Beatport Purchase — Step-by-Step Chrome Commands

**No CLI command for this.** Drive Chrome directly using the chrome-control skill. Beatport has NO CSP issues — `chrome js` works fine.

**Payment**: PayPal (selected by default at checkout). Privacy.com card also works directly with Beatport.

**Credentials**: Stored in macOS Keychain:
```bash
security find-generic-password -a "sven" -s "beatport-email" -w
security find-generic-password -a "sven" -s "beatport-password" -w
```

### Step 1: Open track page

```bash
chrome open "<beatport_url>"
# Returns tab ID, e.g. "Opened tab 1234567: https://..."
```

Wait 3-4 seconds for page load.

### Step 2: Add to cart

The price button's accessible name includes the price and track info. Use `click-by-name` with just the price:

```bash
chrome click-by-name <tab> "$1.49"
# OR for WAV: chrome click-by-name <tab> "$2.49"
```

If there are multiple format options, click the one you want (MP3 is default/cheaper).

### Step 3: Go to cart

```bash
chrome navigate <tab> "https://www.beatport.com/cart"
```

Wait 2-3 seconds for cart page load.

### Step 4: Checkout

```bash
chrome iframe-click <tab> "text:Checkout"
```

**NOTE**: `click-by-name "Checkout"` may hit the cell/container instead of the actual button. Use `iframe-click` with `text:Checkout` for reliability.

PayPal is selected by default. Wait 8-10 seconds for PayPal to load.

### Step 5: PayPal (usually auto-logged in)

Check `chrome text <tab>` to see the PayPal state:

- If it shows "Review Order" or "Complete Purchase" → already logged in
- If it asks for login → follow the PayPal login steps from the Bandcamp section above

```bash
chrome click-by-name <tab> "Review Order"
# Wait 3-5 seconds
chrome click-by-name <tab> "Complete Purchase"
# OR: "Pay Now", "Agree & Pay"
```

Wait 10-15 seconds for redirect back to Beatport "Thank You" page.

### Step 6: Download MP3

Navigate to the downloads library:

```bash
chrome navigate <tab> "https://www.beatport.com/library/downloads"
```

Wait 3-4 seconds for page load. Then trigger the download via JS (Beatport has no CSP):

```bash
chrome js <tab> "document.querySelectorAll('.download-actions')[1].querySelector('button').click()"
```

**Why `[1]`?** Index `[0]` is the "Download All" header row. Index `[1]` is the first actual track. For multiple tracks, increment the index.

The file downloads to `~/Downloads/`. Move it to the music directory:

```bash
mkdir -p ~/Music/dj-buyer
mv ~/Downloads/"Artist - Title.mp3" ~/Music/dj-buyer/
```

Beatport downloads are **320kbps CBR MP3** (their standard format, not VBR like Bandcamp's V0).

Verify the file:
```bash
file ~/Music/dj-buyer/"Artist - Title.mp3"
# Should show: Audio file with ID3 version 2.3.0, contains: MPEG ADTS, layer III
```

Close the Chrome tabs when done.

## Amazon Purchase — Step-by-Step

**Only use Amazon as a fallback** when the track isn't available on Bandcamp or Beatport. Amazon is $1.29/track, 256kbps VBR MP3.

**Credentials**: Stored in macOS Keychain:
```bash
# Email: $(security find-generic-password -s "assistant" -a "email" -w)
security find-generic-password -s "amazon-password" -w
```

**Payment**: Privacy.com Mastercard (ending 8061, exp 02/2032). Billing address: 1 Eastburn St, Brighton MA 02135.

### Pre-flight checks

1. **Clear the Amazon cart first** — navigate to `https://www.amazon.com/gp/cart/view.html` and delete any items. Stale cart items can hijack the MP3 purchase flow into standard checkout, causing card declines and account holds.
2. **Price guardrail** — any purchase over $10 should STOP and ask for confirmation. Single tracks are $1-2. Anything higher means something is wrong (cart contamination, wrong product, etc).

### Step 1: Search and open track

Search Amazon Digital Music for the track:
```bash
chrome navigate <tab> "https://www.amazon.com/s?k=ARTIST+TITLE&i=digital-music"
```

Find the product link via JS:
```bash
chrome js <tab> "document.querySelector('a[href*=\"/dp/B\"]')?.href"
```

Navigate to the product page (Amazon Music player view):
```bash
chrome navigate <tab> "https://www.amazon.com/dp/<ASIN>"
```

### Step 2: Sign in (if needed)

If header shows "Hello, sign in":

```bash
# Click account on sign-in page, then enter password
chrome read <tab>  # Find password textbox ref
chrome type <tab> <ref> "<password_from_keychain>"
chrome click <tab> <sign_in_button_ref>
```

**NOTE**: `click-by-name "Sign in"` may hit the heading text, not the submit button. Use `chrome js` with `document.querySelector('#signInSubmit').click()` as fallback.

Amazon may ask for phone number ("Keep hackers out") — click "Not now" to skip.

### Step 3: Purchase via Purchase Options menu

```bash
chrome click-by-name <tab> "Purchase Options"
# Wait 1 second for dropdown
chrome click-by-name <tab> "MP3 Music"
# Wait 3 seconds — redirects to "Review MP3 purchase" page
```

This shows: track name, artist, **Order total: $1.29**, and two buy buttons:
- "Buy MP3 Album - Pay Now" (album-level)
- "BUY MP3 SONG - PAY NOW" (song-level)

### Step 4: Confirm purchase

```bash
chrome click-by-name <tab> "Buy MP3 Album - Pay Now"
# or for single song:
chrome click-by-name <tab> "Buy MP3 Song - Pay Now"
```

If the billing address error appears ("There was a problem with this order"):
```bash
chrome click-by-name <tab> "Continue"
```
This usually processes the payment on the second attempt.

Wait 5 seconds. Success page shows: **"Thank you for shopping with us"** with **"Download"** button.

### Step 5: Download MP3

Click the Download button on the confirmation page:
```bash
chrome click-by-name <tab> "Download"
```

Or navigate to purchase history:
```bash
chrome navigate <tab> "https://www.amazon.com/gp/dmusic/purchases"
```

Amazon provides 256kbps VBR MP3 files. Downloaded to `~/Downloads/`.

```bash
mv ~/Downloads/"*.mp3" ~/Music/dj-buyer/"Artist - Title.mp3"
```

### Payment method management

The Privacy.com card may get removed during account holds. To re-add:

1. Navigate to wallet: `https://www.amazon.com/cpe/yourpayments/wallet`
2. Click "Add a payment method" → "Add a credit or debit card"
3. **Card form is in a cross-origin secure iframe** — cannot be filled via `chrome js` or `chrome type`
4. **Use `axctl` to fill the form fields**:
```bash
CARD_NUM=$(security find-generic-password -s "privacy-card-number" -w)
CARD_CVV=$(security find-generic-password -s "privacy-card-cvv" -w)

# Fill text fields
axctl type "Google Chrome" --title "Card number" "$CARD_NUM"
axctl type "Google Chrome" --title "Name on card" "Sven Thorat"
axctl type "Google Chrome" --role AXTextField --index 4 "$CARD_CVV"  # CVV (unnamed field)
```
5. **Expiration dropdowns require precise coordinate clicking**:
```bash
# Get dropdown positions via axctl
axctl get "Google Chrome" --title "Expiration date" AXPosition  # Month dropdown
axctl get "Google Chrome" --role AXPopUpButton --index 6 AXPosition  # Year dropdown

# Click to open dropdown, then find and click the right menu item
cliclick c:<center_x>,<center_y>  # Open dropdown
axctl search "Google Chrome" --role AXMenuItem  # Find items with positions
axctl get "Google Chrome" --role AXMenuItem --index <N> AXPosition  # Get exact position
cliclick c:<item_center_x>,<item_center_y>  # Click the menu item
```
6. Click "Add your card" button (use `axctl get` for position, `cliclick` to click)
7. **Set billing address**: Edit card → "Choose or add a billing address" → use 1 Eastburn St address → Save

### Amazon account hold recovery

If the account goes on hold ("Account on hold temporarily"):
1. Go to `https://account-status.amazon.com/`
2. Submit verification — upload Privacy.com statement screenshot showing the card
3. Wait ~5 hours for review (they say 24hrs but it's usually faster)
4. **Root cause**: Privacy.com virtual cards trigger Amazon's fraud detection, especially for digital purchases. Failed transactions re-trigger holds.
5. After hold is lifted, you must re-add the payment card and billing address (they get wiped)

## Scrapling Architecture

- **`Fetcher`**: HTTP-only with TLS fingerprinting. Used for search. Access HTML via `response.html_content` (NOT `.text`).

**CRITICAL: Use `response.html_content` not `response.text`.** Scrapling's `Fetcher` returns empty string for `.text` but the actual HTML is in `.html_content` (decoded from `.body` bytes).

## Payment

**Primary**: PayPal account ($(security find-generic-password -s "assistant" -a "email" -w)) linked to Privacy.com Mastercard. Used for Bandcamp.

**Backup**: Privacy.com virtual card details in macOS Keychain:
```bash
security find-generic-password -a "sven" -s "privacy-card-number" -w
security find-generic-password -a "sven" -s "privacy-card-exp" -w    # MM/YY format
security find-generic-password -a "sven" -s "privacy-card-cvv" -w
```

**Note**: Privacy.com card works directly with Beatport/Amazon but NOT with Bandcamp's Spreedly processor (BIN rejection).

## Spotify Integration

The daemon watches a Spotify playlist for new tracks and auto-searches all platforms.

```bash
cd ~/code/dj-buyer && uv run dj-buyer list-tracks <playlist_id>
cd ~/code/dj-buyer && uv run dj-buyer poll
cd ~/code/dj-buyer && uv run dj-buyer auth   # Re-auth if token expired
```

Current playlist: `162TAg29u887r6VksnVf5d` (configured in `config.toml`)

Current playlist: `162TAg29u887r6VksnVf5d` — "pmtest2" (configured in `config.toml`)

### Spotify Track Metadata

All metadata available via Spotify API for a track. Use `sp.track(track_id)` to get:

**Track-level fields:**
| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `name` | string | "Breaker" | Track title |
| `id` | string | "4scsWxtNAeT4kW52xOJdCg" | Spotify track ID |
| `uri` | string | "spotify:track:..." | Spotify URI |
| `duration_ms` | int | 168857 | Duration in milliseconds |
| `popularity` | int | 32 | 0-100, based on recent plays |
| `explicit` | bool | false | Explicit content flag |
| `disc_number` | int | 1 | Disc number |
| `track_number` | int | 5 | Track number on album |
| `is_local` | bool | false | Local file flag |
| `preview_url` | string/null | null | 30s preview MP3 (often null now) |
| `external_ids.isrc` | string | "QZTGW2407468" | ISRC code (international standard recording code) |
| `external_urls.spotify` | string | "https://open.spotify.com/track/..." | Spotify web URL |

**Artist fields** (via `sp.artist(artist_id)`):
| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `name` | string | "LYNY" | Artist name |
| `id` | string | "7xqIp1044Z2vd9v9ZphjLa" | Spotify artist ID |
| `genres` | list[str] | ["bass music"] | Genre tags (can be empty) |
| `popularity` | int | 56 | 0-100 |
| `followers.total` | int | 38007 | Follower count |
| `images` | list | [{url, width, height}] | 640px, 320px, 160px |

**Album fields** (via `sp.album(album_id)`):
| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `name` | string | "Noise To Dance To" | Album title |
| `album_type` | string | "album" | "album", "single", "compilation" |
| `release_date` | string | "2025-10-17" | Release date |
| `release_date_precision` | string | "day" | "year", "month", or "day" |
| `total_tracks` | int | 12 | Number of tracks |
| `label` | string | "Noxious Recordings" | Record label |
| `popularity` | int | 43 | 0-100 |
| `external_ids.upc` | string | "663918559468" | UPC barcode |
| `copyrights` | list | [{text, type}] | C = copyright, P = phonogram |
| `images` | list | [{url, width, height}] | 640px, 300px, 64px album art |
| `genres` | list[str] | [] | Album genres (usually empty, use artist genres) |

### Working Spotify API Endpoints

| Endpoint | Method | Notes |
|----------|--------|-------|
| `sp.track(id)` | GET track | Full track metadata |
| `sp.tracks([ids])` | GET tracks (batch) | Up to 50 track IDs at once |
| `sp.artist(id)` | GET artist | Artist metadata + genres + followers |
| `sp.artist_top_tracks(id)` | GET top tracks | Top 10 tracks by popularity |
| `sp.artist_albums(id)` | GET discography | All albums/singles/compilations |
| `sp.album(id)` | GET album | Full album metadata + copyrights + label |
| `sp.album_tracks(id)` | GET album tracks | Track listing for an album |
| `sp.search(q, type)` | Search | Types: track, artist, album, playlist |
| `sp.playlist(id)` | GET playlist | Playlist name, tracks, owner |
| `sp.current_user_saved_tracks()` | Library | User's liked songs |
| `sp.me()` | Current user | User profile (premium status, country) |

### Deprecated/Blocked Spotify Endpoints (403/404)

These endpoints are no longer available for most apps:

| Endpoint | Status | Notes |
|----------|--------|-------|
| `sp.audio_features(ids)` | **403** | BPM, key, energy, danceability — deprecated Nov 2024 |
| `sp.audio_analysis(id)` | **403** | Detailed beat/bar/section analysis — deprecated Nov 2024 |
| `sp.recommendations(seed_tracks)` | **404** | Track recommendations — removed |
| `sp.artist_related_artists(id)` | **404** | Similar artists — removed |
| `sp.current_user_recently_played()` | **403** | Needs `user-read-recently-played` scope (not in our auth) |
| `sp.current_user_top_tracks()` | **403** | Needs `user-top-read` scope (not in our auth) |


### Recco Beats API (BPM, Key, Energy — Spotify Replacement)

Free API at `api.reccobeats.com` — no auth needed. Accepts Spotify track IDs and returns the audio features Spotify deprecated.

**Track metadata:**
```bash
curl -s "https://api.reccobeats.com/v1/track?ids=SPOTIFY_ID1,SPOTIFY_ID2"
```
Returns: trackTitle, artists, durationMs, ISRC, EAN, UPC, popularity, availableCountries

**Audio features (BPM, key, energy, etc.):**
```bash
curl -s "https://api.reccobeats.com/v1/audio-features?ids=SPOTIFY_ID1,SPOTIFY_ID2"
```

Returns per track:
| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `tempo` | float | 139.986 | BPM |
| `key` | int | 1 | Pitch class (0=C, 1=C#/Db, 2=D, ..., 11=B) |
| `mode` | int | 1 | 0=minor, 1=major |
| `energy` | float | 0.967 | 0.0-1.0, intensity/activity |
| `danceability` | float | 0.706 | 0.0-1.0, how danceable |
| `valence` | float | 0.939 | 0.0-1.0, musical positiveness |
| `acousticness` | float | 0.567 | 0.0-1.0, acoustic confidence |
| `instrumentalness` | float | 0.00983 | 0.0-1.0, no vocals confidence |
| `liveness` | float | 0.204 | 0.0-1.0, live audience presence |
| `loudness` | float | -3.888 | dB, overall loudness |
| `speechiness` | float | 0.214 | 0.0-1.0, spoken words presence |

**Batch limit**: 50 IDs per request. No API key needed. Results in `content` array.

**Key mapping**: 0=C, 1=C#/Db, 2=D, 3=D#/Eb, 4=E, 5=F, 6=F#/Gb, 7=G, 8=G#/Ab, 9=A, 10=A#/Bb, 11=B. Combine with `mode` for full key (e.g. key=1, mode=1 → C# major).


### Spotify Token Management

**Token storage**: Access token, refresh token, and expiry are in `~/code/dj-buyer/state.db` (table: `spotify_auth`). Refresh token is also backed up to macOS Keychain under service `spotify-refresh-token`, account `dj-buyer`.

**Auto-refresh**: `get_spotify_client()` automatically refreshes the access token when it's within 5 minutes of expiry using the stored refresh token. No manual intervention needed.

**Token health check**: Before running Spotify operations in background/ephemeral tasks, validate the token first. The re-auth flow requires manual SMS URL exchange which breaks in background contexts (exit code 144 / SIGTERM timeout). If the token is expired and refresh fails, proactively notify admin via SMS with the re-auth URL rather than silently failing. Don't attempt full re-auth in background tasks.

**Refresh token recovery from keychain**:
```bash
security find-generic-password -a "dj-buyer" -s "spotify-refresh-token" -w
```

### Spotify Re-auth Flow (when refresh token is revoked)

The redirect URI registered in the Spotify app is `http://127.0.0.1:5432/api/spotify_callback` (shared with playlist-manager, same client_id `43d9bf46f34d48bb80cc23803c8db2a8`). **CRITICAL: Must use `127.0.0.1` not `localhost` — Spotify checks exact URI match.**

When the refresh token is revoked and you need fresh auth:

1. Generate the auth URL and send it to the admin via SMS:
   ```bash
   cd ~/code/dj-buyer && uv run python -c "
   from src.dj_buyer.config import Config
   from src.dj_buyer.spotify.auth import get_auth_url
   print(get_auth_url(Config.load()))
   "
   ```
2. Admin opens URL on their phone browser and logs into Spotify
3. After authorizing, Spotify redirects to `http://127.0.0.1:5432/api/spotify_callback?code=XXX` which won't load on phone
4. Admin copies the full redirect URL from their phone's address bar and pastes it back via SMS
5. Extract the `code=` parameter and exchange it for tokens:
   ```bash
   CLIENT_SECRET=$(cd ~/code/dj-buyer && uv run python -c "from src.dj_buyer.config import get_spotify_secret; print(get_spotify_secret())")
   CREDS=$(echo -n "43d9bf46f34d48bb80cc23803c8db2a8:$CLIENT_SECRET" | base64)
   curl -s -X POST "https://accounts.spotify.com/api/token" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -H "Authorization: Basic $CREDS" \
     -d "grant_type=authorization_code&code=AUTH_CODE&redirect_uri=http://127.0.0.1:5432/api/spotify_callback"
   ```
6. Save tokens to state.db and keychain:
   ```bash
   EXPIRES_AT=$(($(date +%s) + 3600))
   sqlite3 ~/code/dj-buyer/state.db "DELETE FROM spotify_auth; INSERT INTO spotify_auth (access_token, refresh_token, expires_at) VALUES ('ACCESS_TOKEN', 'REFRESH_TOKEN', $EXPIRES_AT);"
   security add-generic-password -a "dj-buyer" -s "spotify-refresh-token" -w "REFRESH_TOKEN" -U
   ```

**Important**: The refresh token doesn't expire on its own — only if the user revokes access or the app credentials change. Once you have it, auto-refresh handles everything.

## Price Safety Guardrail

**CRITICAL: Before completing ANY purchase, verify the total is under $10.** Single DJ tracks cost $0-$2.49 typically. If the checkout total exceeds $10, STOP immediately and ask the admin for confirmation before proceeding. This catches:
- Cart items from other sessions leaking into the purchase flow
- Wrong product selected (album instead of track, physical instead of digital)
- Currency/pricing errors
- Accidental duplicate purchases

**Never auto-confirm a purchase over $10.** Even if the user asked you to buy a specific track, if the checkout shows >$10, something is wrong.

## Known Issues

- **Bandcamp UI changes frequently** — the purchase flow (modal vs sidebar, button labels, etc.) changes without notice. Always use `chrome text`/`chrome screenshot` to see what's on screen and adapt.
- **`click-by-name` sometimes hits StaticText nodes** — if a button click doesn't trigger navigation, try `iframe-click` with CSS selector or `text:` selector instead.
- **`iframe-click` is timing-sensitive** — if it returns `{}`, wait 2 seconds and retry.
- **Privacy.com BIN rejection** — direct card payment on Bandcamp doesn't work. Must use PayPal.
- **PayPal hCaptcha** — headless browsers (StealthyFetcher/Playwright) trigger bot detection. Must use real Chrome.
- **Native `<select>` dropdowns** — can't be set via CDP keyboard or iframe-click. Must use debugger_eval socket.
- **Beatport download button** — `click-by-name "Download All"` clicks the container, not the button. Must use `chrome js` to target `.download-actions` button directly.
- **Amazon cross-origin card form** — the "Add a credit or debit card" modal uses a cross-origin secure iframe. Cannot fill via `chrome js`, `chrome type`, or `chrome key`. Must use `axctl` (macOS accessibility API) to set text field values and `cliclick` with precise `axctl`-derived coordinates for dropdown menus.
- **Amazon `#signInSubmit` button** — `click-by-name "Sign in"` hits the heading text, not the submit button. Use `chrome js` with `document.querySelector('#signInSubmit').click()`.
- **Amazon account holds** — Privacy.com virtual cards trigger Amazon's fraud detection. Failed transactions re-trigger holds. See "Amazon account hold recovery" section for resolution steps.
- **Amazon cart contamination** — existing items in the Amazon cart can redirect the Amazon Music "Buy MP3" flow to standard checkout with inflated totals. Always clear the cart before purchasing music (see pre-flight checks).
- **Amazon billing address** — after re-adding the Privacy.com card, you must also set the billing address via Edit card → "Choose or add a billing address". Without it, purchases fail with "billing address must match your country of purchase".

## Config

`~/code/dj-buyer/config.toml`:
- `search.max_price = 15.00` — skip anything over this
- `search.min_similarity = 0.7` — minimum fuzzy match score
- `search.platforms = ["beatport", "bandcamp", "amazon"]`
- `search.preferred_format = "mp3"`
