---
name: cooking
description: Find recipes online (NYT Cooking, web) and order ingredients via Instacart. Use when asked about recipes, meal planning, grocery shopping, or ordering ingredients.
---

# Cooking Skill

Find recipes and order ingredients through Instacart.

## Part A: Finding Recipes

### NYT Cooking (cooking.nytimes.com)

NYT Cooking requires a subscription. Use Chrome profile 1 (owner's account — see config.local.yaml) which has access.

```bash
# Open NYT Cooking
~/.claude/skills/chrome-control/scripts/chrome -p 1 open "https://cooking.nytimes.com"

# Search for a recipe
~/.claude/skills/chrome-control/scripts/chrome -p 1 navigate <tab_id> "https://cooking.nytimes.com/search?q=<search_term>"
```

**Workflow:**
1. Open NYT Cooking on profile 1
2. If login modal appears, click "Log in" - should auto-authenticate with Google
3. Search for recipe or browse categories
4. Click on recipe to view full details
5. Scroll down to see "INGREDIENTS" and "PREPARATION" sections
6. Extract ingredients list for Instacart ordering

**Tips:**
- Use `chrome read <tab_id>` to find clickable elements
- Use `chrome text <tab_id>` to extract page content
- Screenshots help verify you're on the right page

### Other Recipe Sources

- **Web Search**: Use WebSearch tool for general recipe queries
- **WebFetch**: Fetch recipe content from any URL

## Part B: Instacart Grocery Ordering

### Common Pantry Staples (Skip by Default)

**DO NOT add these items to cart automatically** - most kitchens already have them.

#### Always Skip:
| Item | Variations |
|------|------------|
| **Salt** | Table salt, kosher salt, sea salt |
| **Black pepper** | Ground black pepper, peppercorns |
| **Sugar** | White/granulated sugar |
| **Flour** | All-purpose flour |

#### Usually Skip:
| Item | Notes |
|------|-------|
| **Vegetable/canola oil** | Basic cooking oils |
| **Olive oil** | Basic olive oil (not specialty/finishing oils) |
| **Butter** | Unsalted or salted |
| **Common spices** | Garam masala, turmeric, cumin, paprika, cayenne, chili powder, cinnamon, oregano, basil, thyme |

#### Ask First (might have, might not):
| Item | Why ask |
|------|---------|
| **Fresh aromatics** | Onion, garlic, ginger, shallots - often in kitchen but may be out |
| **Lemons/limes** | Common but perishable |
| **Eggs** | Staple but people run out |
| **Milk/cream** | May or may not have |

#### DO Add (usually need to buy):
- Fresh meat, poultry, seafood
- Specialty produce (specific vegetables for recipe)
- Canned goods (tomatoes, beans, coconut milk)
- Fresh herbs (cilantro, basil, parsley)
- Yogurt, sour cream
- Cheese (unless basic like parmesan)

**IMPORTANT: Always clearly communicate what you skipped!**

**Workflow:**
1. Parse recipe ingredients
2. Identify items from "Always Skip" and "Usually Skip" lists
3. Add everything else to cart
4. **Clearly tell the user what was skipped** so they can add if needed

**Example message (ALWAYS include this):**
```
Added 8 items to cart at Roche Bros ($52.30):
✓ Ground beef, American cheese, hamburger buns...

SKIPPED (assuming you have):
• Kosher salt
• Black pepper
• Sugar
• Olive oil

Need any of these? Just ask and I'll add them.
```

### Account & Login

Instacart account: owner's email (use Chrome profile 1, see config.local.yaml)

**Login Flow:**
1. Go to https://www.instacart.com/login
2. Enter owner's email (from config.local.yaml owner.email)
3. Click Continue
4. Check Gmail (profile 1) for 6-digit verification code
5. Enter code to complete login

```bash
# Navigate to login
~/.claude/skills/chrome-control/scripts/chrome -p 1 navigate <tab_id> "https://www.instacart.com/login"

# Find and enter email (use owner.email from config.local.yaml)
~/.claude/skills/chrome-control/scripts/chrome -p 1 read <tab_id> | grep -i "textbox"
~/.claude/skills/chrome-control/scripts/chrome -p 1 type <tab_id> <ref> "<owner_email>"

# Click continue and check Gmail for code
~/.claude/skills/chrome-control/scripts/chrome -p 1 focus <gmail_tab_id>
~/.claude/skills/chrome-control/scripts/chrome -p 1 read <gmail_tab_id> | grep -i "instacart.*code"
```

### Store Selection

Default store: **Roche Bros.** (Watertown area)

```bash
# Go to Roche Bros store
~/.claude/skills/chrome-control/scripts/chrome -p 1 navigate <tab_id> "https://www.instacart.com/store/roche-bros"
```

### Adding Items to Cart

#### FASTEST Method: Serialized Tabs + Parallel JS Clicks (~22s for 6 items)

**Performance:** 16x faster than sequential approach (22s vs 360s for 6 items)

**Strategy:**
1. Open tabs ONE AT A TIME (serialized) - avoids Chrome extension overload
2. Wait for pages to load (~3s)
3. Click Add buttons in PARALLEL using JS
4. Verify cart and report

**Complete Implementation:**
```bash
#!/bin/bash
CHROME="~/.claude/skills/chrome-control/scripts/chrome -p 1"
ITEMS=("chicken+thighs" "napa+cabbage" "carrot" "snow+peas" "bean+sprouts" "scallions")
TABS=()

# Step 1: Open tabs ONE AT A TIME (serialized to avoid extension overload)
echo "Opening tabs..."
for item in "${ITEMS[@]}"; do
  result=$($CHROME open "https://www.instacart.com/store/roche-bros/s?k=$item" 2>&1)
  tab_id=$(echo "$result" | grep -o "tab [0-9]*" | grep -o "[0-9]*")
  TABS+=($tab_id)
done

# Step 2: Wait for pages to load
sleep 3

# Step 3: Click Add buttons in PARALLEL using JS with aria-label selector
JS='(() => {
  const btn = [...document.querySelectorAll("button")].find(b =>
    (b.getAttribute("aria-label") || "").includes("Add 1")
  );
  if (btn) { btn.click(); return {ok:1}; }
  return {ok:0};
})()'

for tab in "${TABS[@]}"; do
  $CHROME js $tab "$JS" 2>/dev/null &
done
wait

# Step 4: Open cart and screenshot
$CHROME click ${TABS[0]} ref_26  # Click "View Cart" button
sleep 2
$CHROME screenshot ${TABS[0]}

# Step 5: Close worker tabs (keep one for cart view)
for tab in "${TABS[@]:1}"; do
  $CHROME close $tab
done
```

**CRITICAL: Use aria-label for Add buttons**
```javascript
// WRONG - innerText doesn't contain full text:
btn.textContent.includes("Add 1")  // Returns false!

// CORRECT - product name is in aria-label:
btn.getAttribute("aria-label").includes("Add 1")  // Returns true!
```

**Why serialized tab opens?**
Opening 6+ tabs simultaneously overwhelms the Chrome extension connection, causing timeouts. Opening one at a time takes ~14s total but is 100% reliable.

#### OPTIMIZED Method: Direct URL + JS (Fastest, Recommended)

**Use direct search URLs instead of clicking through UI.** This is faster and more reliable.

**Search URL Pattern:**
```
https://www.instacart.com/store/roche-bros/s?k=<search_term>
```

**Example:**
```bash
# Navigate directly to search results for "ground beef"
~/.claude/skills/chrome-control/scripts/chrome -p 1 navigate <tab_id> "https://www.instacart.com/store/roche-bros/s?k=ground+beef"
```

**Programmatic Add to Cart via JS:**
```bash
# After navigating to search results, use JS to find and click the first Add button
~/.claude/skills/chrome-control/scripts/chrome -p 1 js <tab_id> "
(() => {
  // Find all Add buttons
  const addBtns = [...document.querySelectorAll('button')].filter(b =>
    b.textContent.includes('Add') && !b.textContent.includes('Added')
  );
  if (addBtns.length > 0) {
    addBtns[0].click();
    return {success: true, clicked: addBtns[0].textContent};
  }
  return {success: false, error: 'No Add button found'};
})()
"
```

**Parse Search Results via JS:**
```bash
# Get structured list of search results with names and prices
~/.claude/skills/chrome-control/scripts/chrome -p 1 js <tab_id> "
(() => {
  const items = [];
  // Product cards typically have price and name
  document.querySelectorAll('[data-testid=\"product-card\"], [class*=\"ProductCard\"]').forEach(card => {
    const name = card.querySelector('[class*=\"name\"], [data-testid=\"product-name\"]')?.textContent;
    const price = card.querySelector('[class*=\"price\"]')?.textContent;
    if (name) items.push({name: name.trim(), price: price?.trim()});
  });
  // Fallback: look for any item listings
  if (items.length === 0) {
    const text = document.body.innerText;
    const matches = text.match(/\\$\\d+\\.\\d{2}/g);
    return {fallback: true, prices: matches?.slice(0, 10)};
  }
  return items.slice(0, 10);
})()
"
```

**Complete Optimized Subagent Prompt:**
```
You are a grocery shopping subagent. Add "{item}" to Instacart cart.

Tab ID: {tab_id}
Chrome: ~/.claude/skills/chrome-control/scripts/chrome -p 1

Steps:
1. Navigate directly: navigate {tab_id} "https://www.instacart.com/store/roche-bros/s?k={item_url_encoded}"
2. Wait 2 seconds for results
3. Use JS to click first Add button:
   js {tab_id} "document.querySelector('button[class*=\"add\"], button').click()"
4. Verify cart count increased via: read {tab_id} | grep "Items in cart"

Report success/failure.
```

#### Method 2: UI Search (Fallback)

Use this if direct URL doesn't work:

```bash
# 1. Click search box (ref_13)
~/.claude/skills/chrome-control/scripts/chrome -p 1 click <tab_id> ref_13

# 2. Type search term
~/.claude/skills/chrome-control/scripts/chrome -p 1 type <tab_id> ref_13 "sesame oil"

# 3. Click autocomplete suggestion link (NOT textbox)
~/.claude/skills/chrome-control/scripts/chrome -p 1 read <tab_id> | grep -i "<search_term>"
~/.claude/skills/chrome-control/scripts/chrome -p 1 click <tab_id> ref_16

# 4. Click Add button
~/.claude/skills/chrome-control/scripts/chrome -p 1 read <tab_id> | grep -i "add.*<item_name>"
~/.claude/skills/chrome-control/scripts/chrome -p 1 click <tab_id> <ref>
```

#### Method 2: Category Navigation (Alternative)

Use this if search isn't finding what you need:

```bash
# List category elements
~/.claude/skills/chrome-control/scripts/chrome -p 1 read <tab_id> | grep -i "<category_name>"

# Click on category
~/.claude/skills/chrome-control/scripts/chrome -p 1 click <tab_id> <ref>

# Find and add items
~/.claude/skills/chrome-control/scripts/chrome -p 1 read <tab_id> | grep -i "add.*<item_name>"
~/.claude/skills/chrome-control/scripts/chrome -p 1 click <tab_id> <ref>
```

**Main Categories:**
| Category | Items |
|----------|-------|
| Produce > Fresh Vegetables | Onions, garlic, scallions, cucumbers, tomatoes |
| Produce > Leafy Greens | Lettuce, spinach, kale |
| Dairy & Eggs > Cheese | American cheese, cheddar, etc. |
| Meat & Seafood | Ground beef, chicken, etc. |
| Bakery > Buns & Rolls | Hamburger buns, hot dog buns |
| Condiments & Sauces | Mayo, ketchup, soy sauce |
| Condiments & Sauces > Asian Sauces | Soy sauce, teriyaki |
| Oils, Vinegars & Spices > Vinegar | White vinegar, apple cider vinegar |
| Oils, Vinegars & Spices > Cooking Oils > Sesame Oil | Sesame oil |
| Baking Essentials > Sugars | Turbinado sugar, brown sugar |

**Direct Category URLs:**
```
https://www.instacart.com/store/roche-bros/collections/produce
https://www.instacart.com/store/roche-bros/collections/dairy-eggs
https://www.instacart.com/store/roche-bros/collections/meat-seafood
https://www.instacart.com/store/roche-bros/collections/bakery
https://www.instacart.com/store/roche-bros/collections/condiments-sauces
https://www.instacart.com/store/roche-bros/collections/oils-vinegars-spices
https://www.instacart.com/store/roche-bros/collections/baking-essentials
```

### Viewing Cart

```bash
# Find and click cart button
~/.claude/skills/chrome-control/scripts/chrome -p 1 read <tab_id> | grep -i "cart"
~/.claude/skills/chrome-control/scripts/chrome -p 1 click <tab_id> <ref>  # Usually ref_25 or similar "View Cart"
```

Cart appears as a sidebar panel on the right side of the page.

### Parsing Prices via JavaScript (Preferred Method)

**Use `chrome js` to extract structured price data directly from the DOM.** This is more reliable than text parsing.

#### Cart Items with Prices (on store page with cart open)
```bash
# Get all cart items with names and prices as JSON
~/.claude/skills/chrome-control/scripts/chrome -p 1 js <tab_id> "
(() => {
  const items = [];
  // Cart items have a specific structure - find item containers
  document.querySelectorAll('[data-testid=\"cart-item\"], [class*=\"CartItem\"]').forEach(el => {
    const name = el.querySelector('[class*=\"ItemName\"], [data-testid=\"item-name\"]')?.textContent?.trim();
    const price = el.querySelector('[class*=\"price\"], [data-testid=\"item-price\"]')?.textContent?.trim();
    if (name && price) items.push({name, price});
  });
  // Fallback: look for price patterns in cart sidebar
  if (items.length === 0) {
    const cartText = document.querySelector('[class*=\"cart\"], [data-testid=\"cart\"]')?.textContent || '';
    const priceMatch = cartText.match(/\\$[\\d.]+/g);
    return {fallback: true, prices: priceMatch};
  }
  return items;
})()
"
```

#### Cart Total from Checkout Button
```bash
# Get cart total from the checkout button text
~/.claude/skills/chrome-control/scripts/chrome -p 1 js <tab_id> "
(() => {
  const btn = document.querySelector('button[class*=\"checkout\"], [data-testid=\"go-to-checkout\"], button');
  const allBtns = [...document.querySelectorAll('button')];
  const checkoutBtn = allBtns.find(b => b.textContent.includes('checkout'));
  const text = checkoutBtn?.textContent || '';
  const match = text.match(/\\$([\d.]+)/);
  return match ? {total: match[1], raw: text} : {raw: text};
})()
"
```

#### Checkout Page Summary
```bash
# Get full price breakdown from checkout page
~/.claude/skills/chrome-control/scripts/chrome -p 1 js <tab_id> "
(() => {
  const text = document.body.innerText;
  const lines = text.split('\\n');
  const summaryIdx = lines.findIndex(l => l.includes('Summary'));
  if (summaryIdx === -1) return {error: 'Summary not found'};

  const summaryLines = lines.slice(summaryIdx, summaryIdx + 20);
  const itemCount = summaryLines.find(l => /\\d+ items?/.test(l));
  const prices = summaryLines.filter(l => /^\\$[\\d.]+$/.test(l.trim()));
  const freeDelivery = summaryLines.some(l => l.includes('FREE'));

  return {
    itemCount: itemCount?.match(/(\\d+)/)?.[1],
    itemSubtotal: prices[0],
    serviceFee: summaryLines.find(l => l.includes('Service fee')) ? prices[1] : null,
    total: prices[prices.length - 1],
    freeDelivery
  };
})()
"
```

#### Alternative: Accessibility Tree Parsing
```bash
# Use chrome read which returns the accessibility tree
~/.claude/skills/chrome-control/scripts/chrome -p 1 read <tab_id> | grep -E "checkout.*\\$|\\$[0-9]+\\.[0-9]+"
```

**When reporting prices to user, include:**
1. Items subtotal (from cart or "N items" line)
2. Delivery fee (FREE with Instacart+ or actual cost)
3. Service fee
4. Final subtotal

Example message format:
```
Checkout ready:
• Items (10): $36.22
• Delivery: FREE (Instacart+)
• Service fee: $2.49
• Total: $38.71
```

### Checkout (REQUIRES EXPLICIT PERMISSION)

**NEVER checkout without explicit permission.** This involves payment.

**Required before checkout:**
1. ✅ User approved the recipe (Step A)
2. ✅ User approved the ingredient list (Step B)
3. ✅ User saw cart screenshot with price (Step C)
4. ✅ User explicitly said to checkout with specific delivery time

**Checkout process (only after all approvals):**
1. Click "Go to checkout" in cart panel
2. Verify delivery address
3. Select delivery time user specified
4. Confirm payment method
5. Place order
6. Screenshot confirmation and send to user

## Complete Workflow (Multi-Step Approval Process)

**User asks: "Find a recipe for tacos and order ingredients"**

### Step A: Find Recipe & Get Approval

1. Search NYT Cooking or web for recipes
2. **Screenshot the recipe page** - NYT Cooking looks nice and shows photo + ratings
3. Send screenshot + brief description to user
4. **WAIT for user to approve a recipe before continuing**

```bash
# Screenshot the recipe search results or recipe page
~/.claude/skills/chrome-control/scripts/chrome -p 1 screenshot <tab_id>
# Send screenshot to user via iMessage
```

```
[RECIPE SCREENSHOT from NYT Cooking]

Found: Korean Cheeseburgers with Sesame-Cucumber Pickles
⭐ 2,343 ratings | 25 min | by Kay Chun

Want this one, or should I find alternatives?
```

### Step B: Show Ingredients & Curate Together

1. Extract full ingredients list from chosen recipe
2. Organize by SKIP vs ADD categories
3. **Present to user for review/modifications**

```
KOREAN CHEESEBURGERS - Ingredients:

WILL ADD TO CART:
• 1.5 lb ground beef
• 4 slices American cheese
• 4 hamburger buns
• 2 Persian cucumbers
• 2 tbsp scallions
• 1/4 cup soy sauce
• 2.5 tsp sesame oil
• 1/2 cup mayo

SKIPPING (assuming you have):
• Kosher salt
• Black pepper
• 2 tbsp sugar
• 2 tsp white vinegar

Want me to add/remove anything? Say "add the sugar" or "skip the mayo"
```

4. **WAIT for user approval before adding to cart**

### Step C: Add to Cart & Show Summary

1. Open Instacart, login if needed
2. **Use optimized parallel approach:**
   - Open tabs ONE AT A TIME (serialized) with direct search URLs
   - Wait 3s for pages to load
   - Click Add buttons in PARALLEL via JS (aria-label selector)
3. Click "View Cart" button to open cart sidebar
4. Screenshot the page (shows cart sidebar with items + prices)
5. **VERIFY cart against grocery list** - cross-check each item
6. **Send to user: screenshot + item list + skipped items reminder**

**Cart Verification Checklist (MANDATORY — do this BEFORE sending cart to user):**
```
# After adding items, ALWAYS verify:
1. Count items in cart vs items in grocery list
2. For each cart item, match to original ingredient
3. QUANTITY/VOLUME CHECK: Compare the product size (oz, ct, lb) × quantity
   in cart against the recipe's required amount. Examples:
   - Recipe needs 8 cups broth → 2x 32oz = 64oz = 8 cups ✅
   - Recipe needs 8 cups broth → 2x 16.9oz = 33.8oz ≈ 4 cups ❌ (short!)
   - Recipe needs 3 lemons → 3 ct ✅
   Common pitfalls:
   - Broth/stock: cartons vary wildly (16oz, 32oz, 48oz) — always do the math
   - Spices: small containers may not cover recipe amount
   - Produce by weight: verify package weight covers what recipe needs
4. Note any items that couldn't be found
5. Remind user what was SKIPPED (assumed in kitchen)
6. Present the cross-check to the user so they can verify before checkout
```

**Example message format:**
```
[CART SCREENSHOT - showing sidebar with items]

Cart ready at Roche Bros (6 items, $41.85):
✓ Napa Cabbage - $5.07
✓ Green Onions (Scallions) - $1.99
✓ Chicken Thighs - $11.88
✓ Bean Sprouts - $3.99
✓ Snow Peas - $8.99
✓ Carrots - $3.72

Subtotal: $41.85
Service fee: $2.93
Delivery: FREE (Instacart+)
Total: $44.78

SKIPPED (assuming you have):
• Canola/vegetable oil
• Soy sauce (light & dark)
• Oyster sauce
• Sesame oil
• Sugar, salt, pepper
• Garlic, ginger

Need any skipped items? Delivery: Tomorrow 2pm-6pm
```

7. **WAIT for explicit checkout approval with delivery time**

### Step D: Checkout (ONLY with explicit approval)

**NEVER checkout until user says something like:**
- "Yes, checkout for tomorrow morning"
- "Place the order for 6pm delivery"
- "Go ahead and order it"

Then:
1. Click "Go to checkout"
2. Verify/select delivery time user specified
3. Confirm payment method
4. Place order
5. Send confirmation with order details

## Troubleshooting

**Login modal won't close:** Try clicking outside it or pressing Escape
**Search suggestions not appearing:** Make sure you clicked the textbox first, then type
**Search not returning results:** Click the autocomplete suggestion link, don't just press Enter
**Can't find item:** Try different search terms or use category navigation
**404 error on cart URL:** Click the cart icon in the header instead

## Chrome Control Reference

```bash
~/.claude/skills/chrome-control/scripts/chrome -p 1 tabs           # List all tabs
~/.claude/skills/chrome-control/scripts/chrome -p 1 open <url>     # Open new tab
~/.claude/skills/chrome-control/scripts/chrome -p 1 focus <tab_id> # Focus tab
~/.claude/skills/chrome-control/scripts/chrome -p 1 read <tab_id>  # Get interactive elements
~/.claude/skills/chrome-control/scripts/chrome -p 1 click <tab_id> <ref>  # Click element
~/.claude/skills/chrome-control/scripts/chrome -p 1 type <tab_id> <ref> "text"  # Type text
~/.claude/skills/chrome-control/scripts/chrome -p 1 key <tab_id> Enter  # Press key
~/.claude/skills/chrome-control/scripts/chrome -p 1 screenshot <tab_id>  # Take screenshot
~/.claude/skills/chrome-control/scripts/chrome -p 1 scroll <tab_id> down 3  # Scroll
```
