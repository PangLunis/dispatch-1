#!/usr/bin/env node
'use strict';

/**
 * Deals Skill - Main CLI
 *
 * Usage:
 *   node deals.cjs search "Canon EOS R8"                  # Search all stores
 *   node deals.cjs search "Canon EOS R8" --store bestbuy  # Specific store
 *   node deals.cjs search "Canon EOS R8" --json            # JSON output
 *   node deals.cjs search "Canon EOS R8" --top 3           # Limit results
 *
 *   node deals.cjs watch "Canon EOS R8" --target 1100      # Add to watchlist
 *   node deals.cjs list                                     # Show watchlist
 *   node deals.cjs check                                    # Check watchlist prices
 *   node deals.cjs unwatch 3                                # Remove by ID
 *   node deals.cjs history "Canon EOS R8"                   # Price history
 *   node deals.cjs analyze "Canon EOS R8"                   # Deal analysis
 *
 *   node deals.cjs cron                                     # Automated check + alerts
 *   node deals.cjs health                                   # Store health status
 */

// Auto-load secrets.env for API keys (Best Buy, etc.)
const fs = require('fs');
const path = require('path');
const secretsPath = path.join(process.env.HOME || '', '.claude', 'secrets.env');
if (fs.existsSync(secretsPath)) {
  const lines = fs.readFileSync(secretsPath, 'utf8').split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx > 0) {
      const key = trimmed.substring(0, eqIdx).trim();
      let val = trimmed.substring(eqIdx + 1).trim();
      // Strip surrounding quotes
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
        val = val.slice(1, -1);
      }
      if (!process.env[key]) process.env[key] = val;
    }
  }
}

const stores = require('./lib/stores.cjs');
const scraper = require('./lib/scraper.cjs');
const httpScraper = require('./lib/http-scraper.cjs');
const cache = require('./lib/cache.cjs');
const db = require('./lib/db.cjs');
const alerts = require('./lib/alerts.cjs');
const utils = require('./lib/utils.cjs');
const reddit = require('./lib/reddit.cjs');
const reviewSources = require('./lib/review-sources.cjs');

// Stores that use Playwright (everything else uses HTTP or API)
// Home Depot moved to GraphQL in http-scraper.cjs -- no longer needs Playwright
const PLAYWRIGHT_STORES = new Set(['target', 'bhphoto', 'ebay']);
// Stores handled by http-scraper.cjs
const HTTP_STORE_KEYS = new Set(httpScraper.getHttpStoreKeys());

// Stores NOT expected to carry certain product categories (suppress false selector rot)
const STORE_CATEGORY_EXCLUSIONS = {
  apple: new Set(['appliance', 'microwave', 'coffee', 'vacuum', 'hvac', 'outdoor', 'powertools', 'tv', 'camera', 'printer']),
  microcenter: new Set(['appliance', 'microwave', 'coffee', 'vacuum', 'hvac', 'outdoor', 'powertools']),
  bhphoto: new Set(['appliance', 'microwave', 'coffee', 'vacuum', 'hvac', 'outdoor', 'powertools']),
  newegg: new Set(['appliance', 'coffee', 'vacuum', 'hvac', 'outdoor', 'powertools']),
  ebay: new Set([]), // eBay sells everything
};

// ============================================================
// SEARCH (parallel 3-tier architecture)
// ============================================================

async function cmdSearch(query, opts) {
  const { store, json, top, category, maxPrice, minPrice } = opts;
  const limit = top || 10;
  const allResults = [];
  const errors = [];
  const softFailures = []; // stores that returned 0 results with no error
  const storeResultCounts = {}; // track result count per store for status line
  const t0 = Date.now();

  // Determine which stores to search
  let requestedKeys;
  if (store) {
    requestedKeys = store.split(',').map(s => s.trim().toLowerCase());
    const allValid = [...stores.getStoreKeys(), ...httpScraper.getHttpStoreKeys()];
    const invalid = requestedKeys.filter(k => !allValid.includes(k));
    if (invalid.length) console.error(`Unknown store(s): ${invalid.join(', ')}`);
    requestedKeys = requestedKeys.filter(k => allValid.includes(k));
  } else {
    requestedKeys = [...new Set([...stores.getStoreKeys(), ...httpScraper.getHttpStoreKeys()])];
  }

  // Filter out disabled stores
  requestedKeys = requestedKeys.filter(k => {
    if (db.isStoreDisabled(k)) {
      process.stderr.write(`  [${k}] Disabled (circuit breaker). Skipping.\n`);
      return false;
    }
    return true;
  });

  // Expand size queries to prevent stores from pre-filtering by exact size
  // (e.g., "42 inch monitor" -> "monitor" for store queries, keep original for filtering)
  const { searchQuery: effectiveQuery } = utils.expandSizeQuery(query);
  const queryExpanded = effectiveQuery !== query;
  // When expanded, search with BOTH queries to avoid losing results that only appear
  // with the original query (e.g., LG 45" appears for "240Hz gaming monitor 42 inch"
  // but not for "240Hz gaming monitor" on some stores)
  const searchQueries = queryExpanded ? [effectiveQuery, query] : [query];
  if (queryExpanded) {
    process.stderr.write(`  [query] Dual search: "${effectiveQuery}" + "${query}" (merged, size filter post-search)\n`);
  }

  // Check cache first (check both original and expanded queries)
  const cachedStores = new Set();
  for (const sq of searchQueries) {
    const cached = cache.getCachedAll(sq);
    if (cached.stores.length > 0) {
      const newStores = cached.stores.filter(s => !cachedStores.has(s));
      if (newStores.length > 0) {
        process.stderr.write(`  [Cache] Hit for ${newStores.length} store(s) [${sq === query ? 'original' : 'expanded'}]: ${newStores.join(', ')}\n`);
        // Only add results from stores we haven't already cached
        allResults.push(...cached.results.filter(r => !cachedStores.has(r.storeKey)));
        newStores.forEach(s => cachedStores.add(s));
      }
    }
  }
  if (cachedStores.size > 0) {
    requestedKeys = requestedKeys.filter(k => !cachedStores.has(k));
  }

  // --- Reddit community signal (fires in parallel with everything) ---
  const redditCategory = category || utils.guessCategory(query);
  const redditPromise = reddit.searchReddit(query, redditCategory)
    .catch(e => { process.stderr.write(`  [reddit] Error: ${e.message}\n`); return null; });

  if (requestedKeys.length === 0 && allResults.length > 0) {
    process.stderr.write('  [Cache] All stores cached, skipping fetch\n');
  } else if (requestedKeys.length > 0) {
    // ============================================
    // PARALLEL 3-TIER SEARCH
    // All tiers fire simultaneously
    // ============================================
    const tierPromises = [];
    const tierLabels = [];

    // Helper: dedup results by URL (or name+store if no URL)
    function dedup(results) {
      const seen = new Set();
      return results.filter(r => {
        const key = r.url || `${r.name}|${r.store}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
    }

    // --- TIER 0: Best Buy API ---
    // BB verification starts as soon as API returns, overlapping with other tiers
    let bbVerifyPromise = null;
    if (requestedKeys.includes('bestbuy') && stores.isApiStore('bestbuy')) {
      tierPromises.push((async () => {
        process.stderr.write('  [T0] Best Buy API...\n');
        // Search with all queries (original + expanded) and merge
        const allBbResults = [];
        for (const sq of searchQueries) {
          const r = await stores.getStore('bestbuy').apiSearch(sq, { limit, minPrice, maxPrice });
          allBbResults.push(...r);
        }
        const bbResults = dedup(allBbResults);
        db.storeSuccess('bestbuy');
        // Start verification immediately, overlapping with other tiers
        if (bbResults.length > 0) {
          process.stderr.write('  [T3] Verifying Best Buy prices (parallel)...\n');
          bbVerifyPromise = stores.verifyBestBuyPrices(bbResults, Math.min(8, bbResults.length))
            .catch(e => { process.stderr.write(`  [T3] BB verify failed: ${e.message}\n`); return bbResults; });
        }
        return { tier: 0, store: 'bestbuy', results: bbResults };
      })().catch(e => {
        db.storeFailure('bestbuy');
        return { tier: 0, store: 'bestbuy', results: [], error: e.message };
      }));
      tierLabels.push('bestbuy-api');
      requestedKeys = requestedKeys.filter(k => k !== 'bestbuy');
    }

    // --- TIER 1: HTTP stores (Amazon, Walmart, Newegg, Micro Center, eBay, Home Depot) ---
    const httpKeys = requestedKeys.filter(k => HTTP_STORE_KEYS.has(k));
    if (httpKeys.length > 0) {
      tierPromises.push((async () => {
        // Search with all queries and merge
        const allHttpResults = [];
        const allHttpErrors = [];
        for (const sq of searchQueries) {
          const { results: r, errors: e } = await httpScraper.searchAllHttp(sq, {
            stores: httpKeys,
            limit,
            minPrice,
            maxPrice,
          });
          allHttpResults.push(...r);
          allHttpErrors.push(...e);
        }
        const results = dedup(allHttpResults);
        const httpErrors = allHttpErrors;
        // Update store health -- zero results with no error is a soft failure
        // (likely selector rot: HTTP 200 but selectors no longer match)
        for (const key of httpKeys) {
          const hasResults = results.some(r => r.storeKey === key);
          const hasError = httpErrors.some(e => e.storeKey === key);
          if (hasResults) {
            db.storeSuccess(key);
          } else if (hasError) {
            db.storeFailure(key);
          } else {
            // Zero results, no error -- check if store is expected to carry this category
            const searchCat = redditCategory || utils.guessCategory(query);
            const excluded = searchCat && STORE_CATEGORY_EXCLUSIONS[key]?.has(searchCat);
            if (excluded) {
              process.stderr.write(`  [${key}] 0 results (expected -- store does not carry ${searchCat})\n`);
            } else {
              db.storeSoftFailure(key);
              softFailures.push(key);
              process.stderr.write(`  [${key}] 0 results (no error) -- possible selector rot\n`);
            }
          }
        }
        return { tier: 1, results, errors: httpErrors };
      })().catch(e => {
        return { tier: 1, results: [], errors: [{ store: 'HTTP batch', error: e.message }] };
      }));
      tierLabels.push('http-batch');
      requestedKeys = requestedKeys.filter(k => !HTTP_STORE_KEYS.has(k));
    }

    // --- TIER 2: Playwright stores (Target, B&H) ---
    const playwrightKeys = requestedKeys.filter(k => PLAYWRIGHT_STORES.has(k));
    if (playwrightKeys.length > 0) {
      tierPromises.push((async () => {
        process.stderr.write(`  [T2] Playwright: ${playwrightKeys.join(', ')}...\n`);
        const configs = playwrightKeys.map(k => {
          const config = stores.getStore(k);
          if (config) config._storeKey = k; // pass key through to avoid reverse lookup
          return { key: k, config };
        }).filter(c => c.config);
        // Search with all queries and merge
        let scrapeResults = [];
        for (const sq of searchQueries) {
          const r = await scraper.scrapeStores(sq, configs, { limit });
          scrapeResults.push(...r);
        }
        scrapeResults = dedup(scrapeResults);
        const results = [];
        const scrapeErrors = [];
        const seenKeys = new Set();
        for (const r of scrapeResults) {
          if (r._error) {
            db.storeFailure(r.storeKey);
            scrapeErrors.push({ store: r.store, storeKey: r.storeKey, error: r.error });
            seenKeys.add(r.storeKey);
          } else {
            results.push(r);
            seenKeys.add(r.storeKey);
          }
        }
        // Track successes and soft failures per store
        for (const key of playwrightKeys) {
          const hasResults = results.some(r => r.storeKey === key);
          const hasError = scrapeErrors.some(e => e.storeKey === key);
          if (hasResults) {
            db.storeSuccess(key);
          } else if (!hasError) {
            const searchCat = redditCategory || utils.guessCategory(query);
            const excluded = searchCat && STORE_CATEGORY_EXCLUSIONS[key]?.has(searchCat);
            if (excluded) {
              process.stderr.write(`  [${key}] 0 results (expected -- store does not carry ${searchCat})\n`);
            } else {
              db.storeSoftFailure(key);
              softFailures.push(key);
              process.stderr.write(`  [${key}] 0 results (Playwright, no error) -- possible selector rot\n`);
            }
          }
        }
        return { tier: 2, results, errors: scrapeErrors };
      })().catch(e => {
        return { tier: 2, results: [], errors: [{ store: 'Playwright batch', error: e.message }] };
      }));
      tierLabels.push('playwright-batch');
    }

    // Fire all tiers simultaneously
    const settled = await Promise.allSettled(tierPromises);

    // Collect results from all tiers
    for (let i = 0; i < settled.length; i++) {
      if (settled[i].status === 'fulfilled') {
        const outcome = settled[i].value;
        if (outcome.results) allResults.push(...outcome.results);
        if (outcome.errors) errors.push(...outcome.errors);
        if (outcome.error) errors.push({ store: outcome.store || 'Unknown', error: outcome.error });
      } else {
        errors.push({ store: tierLabels[i], error: settled[i].reason?.message || 'Unknown error' });
      }
    }

    // Await BB verification (was started in parallel with other tiers)
    if (bbVerifyPromise) {
      try {
        const verified = await bbVerifyPromise;
        // Replace BB API results in allResults with verified ones
        const bbSkus = new Set(verified.map(r => r.sku));
        for (let i = allResults.length - 1; i >= 0; i--) {
          if (allResults[i].storeKey === 'bestbuy' && bbSkus.has(allResults[i].sku)) {
            const updated = verified.find(v => v.sku === allResults[i].sku);
            if (updated) allResults[i] = updated;
          }
        }
      } catch (e) {
        process.stderr.write(`  [T3] BB verify failed: ${e.message}\n`);
      }
    }

    await scraper.closeBrowser();

    // Build per-store result counts for status line
    for (const r of allResults) {
      if (r.storeKey) storeResultCounts[r.storeKey] = (storeResultCounts[r.storeKey] || 0) + 1;
    }
    // Mark errored/soft-failed stores with 0
    for (const e of errors) {
      if (e.storeKey && !(e.storeKey in storeResultCounts)) storeResultCounts[e.storeKey] = 0;
    }
    for (const k of softFailures) {
      if (!(k in storeResultCounts)) storeResultCounts[k] = 0;
    }

    // Cache results by store (cache under all search queries for future lookups)
    const byStore = {};
    for (const r of allResults) {
      if (!r.storeKey) continue;
      if (!byStore[r.storeKey]) byStore[r.storeKey] = [];
      byStore[r.storeKey].push(r);
    }
    for (const [storeKey, results] of Object.entries(byStore)) {
      const source = results[0]?.source || 'http';
      const cacheType = source.includes('api') ? 'api' : source;
      for (const sq of searchQueries) {
        cache.setCache(sq, storeKey, results, cacheType);
      }
    }
  }

  // Await Reddit results (was fired in parallel with store searches)
  const redditSignal = await redditPromise;

  // Enrich results with additional data (Newegg reviews, CamelCamelCamel history)
  // Fire both in parallel for speed
  await Promise.allSettled([
    httpScraper.enrichNeweggReviews(allResults, 5),
    httpScraper.enrichWithCamelHistory(allResults, 3),
  ]);

  const elapsed = Date.now() - t0;

  // Guess category if not specified
  const cat = category || (allResults.length > 0 ? utils.guessCategory(query) : null);

  // Parse query intent EARLY so it is available for spec penalties
  const queryIntent = utils.parseQueryIntent(query);

  // Calculate deal scores
  for (const r of allResults) {
    // Merge API specs with name-extracted specs (name extraction fills gaps like wattage, capacity)
    const nameSpecs = utils.extractSpecsFromName(r.name);
    const apiSpecs = r.specs && Object.keys(r.specs).some(k => r.specs[k]) ? r.specs : {};
    const specs = { ...nameSpecs, ...apiSpecs };
    // Write merged specs back to result for display
    r.specs = specs;
    const scoreResult = utils.dealScore({
      price: r.price,
      originalPrice: r.originalPrice,
      reviewScore: r.reviewScore,
      reviewCount: r.reviewCount,
      category: r.category || cat,
      specs,
      name: r.name,
      storeKey: r.storeKey,
      source: r.source,
    });
    r.dealScore = scoreResult.score;
    r.qualityScore = scoreResult.quality;
    r.valueScore = scoreResult.value;
    r.scoreTag = scoreResult.tag;
    r.scoreComponents = scoreResult.components;

    // Apply query spec mismatch penalty (penalizes wrong refresh rate, size, resolution)
    const specPenalty = utils.querySpecPenalty(r.name, specs, queryIntent);
    if (specPenalty < 1.0) {
      r.dealScore = Math.round(r.dealScore * specPenalty);
      r.qualityScore = Math.round(r.qualityScore * specPenalty);
      r._specPenalty = specPenalty;
    }

    // Ranking boosts for standout deals so they don't sink below expensive low-value items
    if (r.scoreTag === 'Deal' || r.scoreTag === 'Deal/Refurb') {
      r.dealScore += 3;
      // Extra budget pick boost: cheap items with big discounts should rank well
      if (r.price && r.price < 250 && r.discountPercent >= 40) {
        r.dealScore += 3;
      }
    } else if (r.scoreTag === 'Sweet Spot' || r.scoreTag === 'Sweet Spot/Refurb') {
      r.dealScore += 2;
    }
  }

  // Sort by deal score (highest first)
  allResults.sort((a, b) => b.dealScore - a.dealScore);

  // Cross-store dedup: group by matchKey, keep best-scored per product
  const seen = new Set();
  const deduped = [];
  const alsoAt = {}; // matchKey -> [{ store, storeKey, price, url }]
  for (const r of allResults) {
    const key = utils.matchKey(r.name, r.price);
    if (!key) { deduped.push(r); continue; }
    if (seen.has(key)) {
      if (!alsoAt[key]) alsoAt[key] = [];
      // Only add if different store or meaningfully different price
      const isDupe = alsoAt[key].some(a => a.storeKey === r.storeKey && a.price === r.price);
      if (!isDupe) {
        alsoAt[key].push({ store: r.store, storeKey: r.storeKey, price: r.price, url: r.url });
      }
    } else {
      seen.add(key);
      deduped.push(r);
    }
  }
  // Attach "also at" info to deduped results
  // - Promote lowest price to headline if lower than current
  // - Collapse same-store entries into a price range
  // - Skip entries matching primary store+price
  for (const r of deduped) {
    const key = utils.matchKey(r.name, r.price);
    if (key && alsoAt[key]) {
      const others = alsoAt[key].filter(a => a.storeKey !== r.storeKey || a.price !== r.price);
      if (others.length === 0) continue;

      // Check if any "also at" has a lower price -- promote it
      const cheapest = others.reduce((min, a) => a.price < min.price ? a : min, { price: r.price });
      if (cheapest.price < r.price) {
        // Swap: current becomes an "also at", cheapest becomes headline
        const oldStore = r.store;
        const oldStoreKey = r.storeKey;
        const oldPrice = r.price;
        const oldUrl = r.url;
        r.price = cheapest.price;
        r.store = cheapest.store;
        r.storeKey = cheapest.storeKey;
        if (cheapest.url) r.url = cheapest.url;
        // Recalculate discount if we have originalPrice
        if (r.originalPrice && r.originalPrice > r.price) {
          const disc = utils.calcDiscount(r.price, r.originalPrice);
          r.discountPercent = disc.percent;
          r.discountAmount = disc.amount;
        }
        // Remove promoted entry from others, add old headline
        const remaining = others.filter(a => !(a.storeKey === cheapest.storeKey && a.price === cheapest.price));
        remaining.push({ store: oldStore, storeKey: oldStoreKey, price: oldPrice, url: oldUrl });
        others.length = 0;
        others.push(...remaining);
      }

      // Filter out entries from the same store as primary (after potential swap)
      // Same store at different price is not useful info for buyer
      const filteredOthers = others.filter(a => a.storeKey !== r.storeKey);

      // Collapse same-store entries into a range
      const byStore = {};
      for (const a of filteredOthers) {
        if (!byStore[a.storeKey]) byStore[a.storeKey] = { store: a.store, storeKey: a.storeKey, prices: [] };
        byStore[a.storeKey].prices.push(a.price);
      }
      r._alsoAt = Object.values(byStore).map(s => {
        const prices = s.prices.sort((a, b) => a - b);
        if (prices.length === 1) {
          return `${s.store} ${utils.formatPrice(prices[0])}`;
        }
        return `${s.store} ${utils.formatPrice(prices[0])}-${utils.formatPrice(prices[prices.length - 1])}`;
      });
    }
  }
  // ---- RELEVANCE FILTER (after dedup, before DB save) ----
  // queryIntent already parsed above (before scoring)
  let filteredCount = 0;
  const relevantResults = [];
  for (const r of deduped) {
    const check = utils.isIrrelevantProduct(r.name, queryIntent);
    if (check.rejected) {
      filteredCount++;
      process.stderr.write(`  [filter] Rejected: "${(r.name || '').substring(0, 120)}" (${check.reason})\n`);
    } else {
      // Apply relevance score as weighted blend into deal score
      r.dealScore = (r.dealScore * 0.7) + (check.relevanceScore * 30);
      relevantResults.push(r);
    }
  }
  // URL/SKU size validation: check if URL contains a different screen size than what the name says
  if (queryIntent.targetSize) {
    for (let i = relevantResults.length - 1; i >= 0; i--) {
      const r = relevantResults[i];
      if (!r.url) continue;
      // Samsung-style SKU in URL: qn50, qn55, qn65, un55, etc.
      const urlSizeMatch = r.url.match(/[qu]n(\d{2})/i);
      if (urlSizeMatch) {
        const urlSize = parseInt(urlSizeMatch[1]);
        const nameSpecs = utils.extractSpecsFromName(r.name);
        const nameSize = nameSpecs.screenSize ? Math.round(parseFloat(nameSpecs.screenSize)) : null;
        // If URL says different size than search AND name, it's a mismatch
        if (urlSize !== queryIntent.targetSize && nameSize && urlSize !== nameSize) {
          process.stderr.write(`  [filter] Rejected: "${(r.name || '').substring(0, 80)}" (url_size_mismatch: URL=${urlSize}" vs search=${queryIntent.targetSize}")\n`);
          relevantResults.splice(i, 1);
          filteredCount++;
        }
      }
    }
  }

  // Re-sort after relevance adjustment
  relevantResults.sort((a, b) => b.dealScore - a.dealScore);

  // ---- PRICE RANGE FILTER (user-specified --max-price / --min-price) ----
  if (maxPrice || minPrice) {
    const beforePriceFilter = relevantResults.length;
    for (let i = relevantResults.length - 1; i >= 0; i--) {
      const r = relevantResults[i];
      if (r.price && maxPrice && r.price > maxPrice) {
        filteredCount++;
        process.stderr.write(`  [filter] Rejected: "${(r.name || '').substring(0, 50)}" (over_max_price: $${r.price} > $${maxPrice})\n`);
        relevantResults.splice(i, 1);
      } else if (r.price && minPrice && r.price < minPrice) {
        filteredCount++;
        process.stderr.write(`  [filter] Rejected: "${(r.name || '').substring(0, 50)}" (under_min_price: $${r.price} < $${minPrice})\n`);
        relevantResults.splice(i, 1);
      }
    }
    if (relevantResults.length < beforePriceFilter) {
      process.stderr.write(`  [filter] Price range: removed ${beforePriceFilter - relevantResults.length} results outside $${minPrice || 0}-$${maxPrice || '∞'}\n`);
    }
  }

  // ---- PRICE OUTLIER FILTER (for specific product searches) ----
  // When searching for a specific product, remove results with prices wildly
  // different from the cluster (likely wrong product despite passing name filter)
  let outputResults = relevantResults;
  if (queryIntent.isSpecificSearch && relevantResults.length >= 3) {
    const prices = relevantResults.filter(r => r.price > 0).map(r => r.price).sort((a, b) => a - b);
    if (prices.length >= 3) {
      const median = prices[Math.floor(prices.length / 2)];
      // Remove results more than 3x or less than 1/3 of the median price
      const beforeCount = relevantResults.length;
      outputResults = relevantResults.filter(r => {
        if (!r.price) return true;
        const ratio = r.price / median;
        if (ratio > 3.0 || ratio < 0.33) {
          filteredCount++;
          process.stderr.write(`  [filter] Rejected: "${(r.name || '').substring(0, 50)}" (price_outlier: $${r.price} vs median $${median})\n`);
          return false;
        }
        return true;
      });
    }
  }

  // ---- STRICT / RELAXED CLASSIFICATION ----
  // Split results into exact matches and partial matches for display
  const strictResults = [];
  const relaxedResults = [];
  for (const r of outputResults) {
    const match = utils.classifyMatch(r.name, r.specs, queryIntent);
    r._matchClassification = match;
    if (match.strict) {
      strictResults.push(r);
    } else {
      relaxedResults.push(r);
    }
  }
  // Re-order: strict matches first, then relaxed (both sorted by score within group)
  outputResults = [...strictResults, ...relaxedResults];

  // Save prices to database (only relevant results, with match_key for precise history lookups)
  const priceRecords = relevantResults.filter(r => r.price).map(r => ({
    store: r.storeKey,
    price: r.price,
    originalPrice: r.originalPrice,
    discountPercent: r.discountPercent,
    discountAmount: r.discountAmount,
    productNameRaw: r.name,
    productUrl: r.url,
    sku: r.sku,
    reviewScore: r.reviewScore,
    reviewCount: r.reviewCount,
    source: r.source,
    matchKey: utils.matchKey(r.name, r.price),
    searchQuery: query,
  }));
  if (priceRecords.length > 0) {
    db.savePrices(priceRecords);
  }

  // Output
  if (json) {
    console.log(JSON.stringify({
      query,
      searchedAt: new Date().toISOString(),
      elapsedMs: elapsed,
      resultCount: allResults.length,
      errors: errors.length > 0 ? errors : undefined,
      results: outputResults,
    }, null, 2));
  } else {
    if (outputResults.length === 0) {
      console.log(`No results found for: ${query}`);
      if (errors.length > 0) {
        errors.forEach(e => console.log(`  ${e.store}: ${e.error}`));
      }
      return allResults;
    }

    // Store + brand diversity: cap per store AND per brand so results are varied
    // Tier-aware brand cap: allow 3 per brand if products span different price tiers
    const MAX_PER_STORE = 3;
    const MAX_PER_BRAND_BASE = 2;
    const MAX_PER_BRAND_TIERED = 3; // when products span distinct price tiers
    const storeCounts = {};
    const brandCounts = {};
    const brandPriceTiers = {}; // brand -> Set of tier labels
    const diverseResults = [];

    // Pre-compute price tier for each result (budget/mid/premium)
    function priceTier(price) {
      if (!price) return 'unknown';
      if (price < 300) return 'budget';
      if (price < 700) return 'mid';
      return 'premium';
    }

    // First pass: count price tiers per brand
    for (const r of outputResults) {
      const bm = (r.name || '').match(/\b(TCL|Samsung|LG|Sony|Hisense|Vizio|Insignia|Toshiba|Amazon|Sharp|Roku|Philips|Panasonic|Element|Bose|JBL|Sennheiser|Apple|Beats|Skullcandy|JLab|Jabra|Anker|Soundcore|Dell|HP|Lenovo|ASUS|Acer|MSI|Canon|Nikon|Fujifilm|Onkyo|Yamaha|Denon|Marantz|Klipsch|Sonos|Dyson|KitchenAid|Whirlpool|Logitech|Razer|Corsair)\b/i);
      if (bm) {
        const brand = bm[1].toLowerCase();
        if (!brandPriceTiers[brand]) brandPriceTiers[brand] = new Set();
        brandPriceTiers[brand].add(priceTier(r.price));
      }
    }

    for (const r of outputResults) {
      const storeKey = r.storeKey || r.store;
      storeCounts[storeKey] = (storeCounts[storeKey] || 0) + 1;
      if (storeCounts[storeKey] > MAX_PER_STORE) continue;
      // Extract brand for diversity cap
      const brandMatch = (r.name || '').match(/\b(TCL|Samsung|LG|Sony|Hisense|Vizio|Insignia|Toshiba|Amazon|Sharp|Roku|Philips|Panasonic|Element|Bose|JBL|Sennheiser|Apple|Beats|Skullcandy|JLab|Jabra|Anker|Soundcore|Dell|HP|Lenovo|ASUS|Acer|MSI|Canon|Nikon|Fujifilm|Onkyo|Yamaha|Denon|Marantz|Klipsch|Sonos|Dyson|KitchenAid|Whirlpool|Logitech|Razer|Corsair)\b/i);
      if (brandMatch) {
        const brand = brandMatch[1].toLowerCase();
        brandCounts[brand] = (brandCounts[brand] || 0) + 1;
        // Use higher cap if brand spans 2+ price tiers
        const cap = (brandPriceTiers[brand] && brandPriceTiers[brand].size >= 2)
          ? MAX_PER_BRAND_TIERED : MAX_PER_BRAND_BASE;
        if (brandCounts[brand] > cap) continue;
      }
      diverseResults.push(r);
    }

    // iMessage-friendly output with emojis and visual ranking
    const topResults = diverseResults.slice(0, limit);
    const lines = [];
    const storeSet = new Set(topResults.map(r => r.store));

    // Header with quick summary
    const allPrices = topResults.filter(r => r.price).map(r => r.price);
    const quickLowest = allPrices.length > 0 ? Math.min(...allPrices) : null;
    const quickHighest = allPrices.length > 0 ? Math.max(...allPrices) : null;
    // Header "Top pick" uses best value score (deal-focused), not just highest overall score
    const topPick = [...topResults].sort((a, b) => (b.valueScore || 0) - (a.valueScore || 0))[0] || topResults[0];
    const priceNote = (maxPrice || minPrice) ? ` (${minPrice ? utils.formatPrice(minPrice) + '-' : ''}${maxPrice ? 'under ' + utils.formatPrice(maxPrice) : ''})` : '';
    lines.push(`\uD83D\uDD0D ${query}${priceNote}`);
    if (quickLowest && topPick) {
      const topShort = (topPick.name || '').split(' ').slice(0, 5).join(' ').replace(/\b\.(\d)/g, '0.$1');
      const dealNote = topPick.discountPercent >= 10 ? `, ${topPick.discountPercent}% off` : '';
      lines.push(`${topResults.length} results, ${utils.formatPrice(quickLowest)}-${utils.formatPrice(quickHighest)}. Top deal: ${topShort} @ ${topPick.store}${dealNote}`);
    } else {
      lines.push(`${relevantResults.length} results from ${storeSet.size} stores${filteredCount > 0 ? ` (${filteredCount} filtered)` : ''}`);
    }
    lines.push('');

    // Track where the strict/relaxed boundary is for divider insertion
    const strictCount = topResults.filter(r => r._matchClassification && r._matchClassification.strict).length;
    let insertedDivider = false;

    topResults.forEach((r, i) => {
      const rank = i + 1;

      // Insert divider between strict and relaxed results
      if (!insertedDivider && strictCount > 0 && r._matchClassification && !r._matchClassification.strict) {
        lines.push('--- Other options (partial spec match) ---');
        lines.push('');
        insertedDivider = true;
      }

      // Build deal indicator emojis (only for noteworthy signals)
      let dealBadges = '';
      if (rank === 1) dealBadges += '\uD83D\uDC8E '; // 💎 best pick
      if (r.discountPercent > 0) dealBadges += utils.discountEmoji(r.discountPercent) + ' ';

      // Product name: try to show parsed specs for computers, otherwise truncate
      const computerSpecs = utils.extractComputerSpecs(r.name);
      let displayName;
      if (computerSpecs) {
        const brandMatch = (r.name || '').match(/\b(Apple|HP|Lenovo|ASUS|Dell|MSI|Acer)\b/i);
        const brandPrefix = brandMatch ? brandMatch[1] : '';
        const lineMatch = (r.name || '').match(/\b(Mac [Mm]ini|Mac [Ss]tudio|Mac [Pp]ro|iMac|MacBook\s*\w*)\b/);
        const productLine = lineMatch ? lineMatch[1] : '';
        if (brandPrefix && productLine) {
          displayName = `${brandPrefix} ${productLine}  ${computerSpecs}`;
        } else if (productLine) {
          displayName = `${productLine}  ${computerSpecs}`;
        } else {
          const shortName = r.name && r.name.length > 40
            ? r.name.substring(0, 37) + '...'
            : (r.name || 'Unknown');
          displayName = `${shortName}  [${computerSpecs}]`;
        }
      } else {
        displayName = r.name && r.name.length > 70
          ? r.name.substring(0, 67) + '...'
          : (r.name || 'Unknown');
      }

      // Surface refurbished/open box status if not already in display name or tag
      const nameLC = (r.name || '').toLowerCase();
      const isRefurb = /\b(refurbished|refurb|renewed|open[\s-]?box|pre-?owned)\b/i.test(nameLC);
      const tagHasRefurb = r.scoreTag && /refurb/i.test(r.scoreTag);
      const nameHasRefurb = /\b(refurbished|refurb|renewed|open[\s-]?box)\b/i.test(displayName.toLowerCase());
      if (isRefurb && !tagHasRefurb && !nameHasRefurb) {
        displayName += ' [Refurb]';
      }

      // Line 1: rank + deal badges + product name
      lines.push(`${rank}. ${dealBadges}${displayName}`);

      // Line 2: store + price + discount + dual scores + tag
      let priceLine = `   ${r.store}  ${utils.formatPrice(r.price)}`;
      if (r.originalPrice && r.discountPercent > 0) {
        // Flag suspected inflated MSRPs: budget/house brands with 40%+ discounts
        const budgetBrands = /\b(insignia|sansui|onn|element|westinghouse|hisense|tcl|toshiba|vizio)\b/i;
        const isBudgetBrand = budgetBrands.test(r.name || '');
        const msrpNote = (isBudgetBrand && r.discountPercent >= 40) ? ' MSRP' : '';
        priceLine += ` (was${msrpNote} ${utils.formatPrice(r.originalPrice)}, -${r.discountPercent}%)`;
      }
      if (r.qualityScore != null && r.valueScore != null) {
        priceLine += `  Q:${r.qualityScore} V:${r.valueScore}`;
        if (r.scoreTag) priceLine += ` [${r.scoreTag}]`;
      }
      if (r.weight) priceLine += `  ${r.weight} lbs`;
      lines.push(priceLine);

      // Line 3: reviews (only shown when reviews exist to reduce noise)
      if (r.reviewScore) {
        const rEmoji = utils.reviewEmoji(r.reviewScore);
        const rc = utils.formatReviewCount(r.reviewCount);
        lines.push(`   ${rEmoji} ${r.reviewScore.toFixed(1)} stars${rc ? ` (${rc} reviews)` : ''}`);
      }

      // Display specs line (category-aware)
      if (r.specs) {
        const dispParts = [];
        const isAppliance = /\b(microwave|oven|toaster|blender|air fryer|instant pot|food processor|dishwasher|refrigerator|washer|dryer|range|freezer)\b/i.test(r.name || '');
        if (isAppliance) {
          // Appliance specs: capacity, wattage, type, finish
          if (r.specs.capacity) {
            let cap = r.specs.capacity;
            if (cap.startsWith('.')) cap = '0' + cap;
            dispParts.push(cap);
          }
          if (r.specs.wattage) dispParts.push(r.specs.wattage);
          if (r.specs.applianceType) dispParts.push(r.specs.applianceType);
          if (r.specs.finish) dispParts.push(r.specs.finish);
        } else {
          // TV/monitor specs: panel type, resolution, refresh rate, screen size, HDR
          if (r.specs.panelType) dispParts.push(r.specs.panelType);
          else if (r.specs.displayType) dispParts.push(r.specs.displayType);
          if (r.specs.resolution) dispParts.push(r.specs.resolution);
          if (r.specs.refreshRate) dispParts.push(r.specs.refreshRate);
          if (r.specs.screenSizeExact) dispParts.push(`${r.specs.screenSizeExact}\u2033`);
          else if (r.specs.screenSize) dispParts.push(`${r.specs.screenSize}\u2033`);
          if (r.specs.hdr) dispParts.push(r.specs.hdr);
          if (r.specs.smartPlatform) dispParts.push(r.specs.smartPlatform);
        }
        if (dispParts.length > 0) {
          lines.push(`   ${dispParts.join(' | ')}`);
        }
      }

      // Dimensions line for all BB results (WxHxD)
      if (r.dimensions) {
        lines.push(`   ${r.dimensions}`);
      }

      // CamelCamelCamel price history (Amazon only)
      if (r._camelHistory) {
        const ch = r._camelHistory;
        let histLine = '   \uD83D\uDCC9 Price history:';
        if (ch.allTimeLow) histLine += ` Low ${utils.formatPrice(ch.allTimeLow)}`;
        if (ch.allTimeHigh) histLine += ` / High ${utils.formatPrice(ch.allTimeHigh)}`;
        if (ch.allTimeLow && r.price) {
          if (r.price <= ch.allTimeLow * 1.02) histLine += ' \u2B50 Near all-time low!';
          else {
            const aboveLow = Math.round(((r.price / ch.allTimeLow) - 1) * 100);
            if (aboveLow > 0) histLine += ` (${aboveLow}% above low)`;
          }
        }
        lines.push(histLine);
      }

      // Also at (cross-store dupes)
      if (r._alsoAt && r._alsoAt.length > 0) {
        const allSameStore = r._alsoAt.every(a => a.startsWith(r.store));
        const label = allSameStore ? 'Other listings' : 'Also at';
        lines.push(`   ${label}: ${r._alsoAt.join(', ')}`);
      }

      // URL on every result
      if (r.url) {
        lines.push(`   ${r.url}`);
      }

      // Deviation callout for relaxed matches
      if (r._matchClassification && !r._matchClassification.strict && r._matchClassification.deviations.length > 0) {
        lines.push(`   \u26A0\uFE0F ${r._matchClassification.deviations.join(', ')}`);
      }

      lines.push('');
    });

    // Footer (compact)
    const prices = topResults.filter(r => r.price).map(r => r.price);
    if (prices.length > 1) {
      const lowest = Math.min(...prices);
      const highest = Math.max(...prices);
      const lowestResult = topResults.find(r => r.price === lowest);
      const lowestLabel = lowestResult ? ` (${lowestResult.store})` : '';
      lines.push(`\uD83D\uDCB0 Lowest: ${utils.formatPrice(lowest)}${lowestLabel}  |  Range: ${utils.formatPrice(lowest)}-${utils.formatPrice(highest)}`);

      // Best value callout with reason (use highest VALUE score, not overall score)
      const bestValue = [...topResults].sort((a, b) => (b.valueScore || 0) - (a.valueScore || 0))[0];
      if (bestValue) {
        const bvSpecs = utils.extractComputerSpecs(bestValue.name);
        const shortBV = bvSpecs
          ? (bestValue.name || '').match(/\b(Mac [Mm]ini|Mac [Ss]tudio|Mac [Pp]ro|iMac|MacBook\s*\w*)\b/)?.[1] || (bestValue.name || '').split(' ').slice(0, 3).join(' ')
          : (bestValue.name || '').split(' ').slice(0, 5).join(' ').replace(/\b\.(\d)/g, '0.$1');
        // Build a reason string
        const reasons = [];
        if (bestValue.discountPercent >= 20) reasons.push(`${bestValue.discountPercent}% off`);
        else if (bestValue.discountPercent > 0) reasons.push(`${bestValue.discountPercent}% off`);
        if (bestValue.reviewScore >= 4.5 && bestValue.reviewCount >= 100) reasons.push(`${bestValue.reviewScore} stars`);
        const reasonStr = reasons.length > 0 ? ` (${reasons.join(', ')})` : '';
        lines.push(`\uD83D\uDC8E Best value: ${shortBV} @ ${bestValue.store}${reasonStr}`);
      }
    }

    // Thin results fallback - suggest widening range
    if (topResults.length <= 2 && (maxPrice || minPrice) && filteredCount > 5) {
      const wideLow = minPrice ? Math.round(minPrice * 0.7) : null;
      const wideHigh = maxPrice ? Math.round(maxPrice * 1.3) : null;
      const suggestion = wideLow && wideHigh ? `${utils.formatPrice(wideLow)}-${utils.formatPrice(wideHigh)}`
        : wideHigh ? `under ${utils.formatPrice(wideHigh)}` : `over ${utils.formatPrice(wideLow)}`;
      lines.push(`\u26A0\uFE0F Only ${topResults.length} result(s) in range. ${filteredCount} filtered. Try widening to ${suggestion}`);
    }

    // Market context note for thin results
    const marketNote = utils.getMarketContext(queryIntent, strictCount);
    if (marketNote) {
      lines.push(`\uD83D\uDCCB ${marketNote}`);
    }

    // Reddit community signal (validate relevance before showing)
    if (redditSignal && redditSignal.summary) {
      // Check if top post is actually relevant to the query
      const topPostTitle = (redditSignal.posts?.[0]?.title || '').toLowerCase();
      const queryLower = query.toLowerCase();
      // Extract size from query (e.g. "55" from "55 inch TV")
      const querySizeMatch = queryLower.match(/\b(\d{2,3})\s*(?:inch|in|")\b/);
      const querySize = querySizeMatch ? querySizeMatch[1] : null;
      // If query has a specific size, the post must mention that same size
      let sizeRelevant = true;
      if (querySize) {
        const postSizeMatch = topPostTitle.match(/\b(\d{2,3})\s*(?:inch|in|")\b/);
        if (postSizeMatch && postSizeMatch[1] !== querySize) sizeRelevant = false;
      }
      const queryWords = queryLower.split(/\s+/).filter(w => w.length > 2 && !/^\d+$/.test(w));
      const relevantWordCount = queryWords.filter(w => topPostTitle.includes(w)).length;
      const isRelevant = sizeRelevant && relevantWordCount >= Math.min(2, queryWords.length);

      if (isRelevant) {
        lines.push(`\uD83D\uDDE3\uFE0F Reddit: ${redditSignal.summary}`);
        if (redditSignal.topPostUrl) {
          lines.push(`   ${redditSignal.topPostUrl}`);
        }
      } else {
        // Show subreddit activity without the misleading link
        const subNames = [...new Set((redditSignal.posts || []).map(p => p.subreddit))].slice(0, 2);
        if (subNames.length > 0) {
          lines.push(`\uD83D\uDDE3\uFE0F Reddit: Discussions found on r/${subNames.join(', r/')} (no exact match for this search)`);
        }
      }
    }

    // Review sources for this category
    const reviewLinks = reviewSources.getReviewLinks(cat, 3);
    if (reviewLinks.length > 0) {
      lines.push(`\uD83D\uDCD6 Reviews: ${reviewLinks.join(' | ')}`);
    }

    // Store status line: show all stores with result counts
    if (Object.keys(storeResultCounts).length > 0) {
      const storeNames = { apple: 'Apple', bhphoto: 'B&H', homedepot: 'HD', ebay: 'eBay', walmart: 'Walmart', target: 'Target', microcenter: 'MC', newegg: 'Newegg', amazon: 'Amazon', bestbuy: 'BB' };
      const errorKeys = new Set(errors.map(e => e.storeKey).filter(Boolean));
      const statusParts = Object.entries(storeResultCounts).map(([k, count]) => {
        const name = storeNames[k] || k;
        if (errorKeys.has(k)) return `${name}(\u2717)`;
        if (count === 0) return `${name}(0)`;
        return `${name}(${count})`;
      });
      lines.push(`\uD83C\uDFEA Stores: ${statusParts.join(' | ')}`);
    }
    // Legend for scores and tags
    lines.push(`\uD83D\uDCCA Q=Quality V=Value | Tags: Sweet Spot=best of both, Deal=great value, Premium=high quality, Solid=good overall`);
    lines.push(`   \uD83D\uDD25=10%+ \uD83D\uDD25\uD83D\uDD25=25%+ \uD83D\uDD25\uD83D\uDD25\uD83D\uDD25=45%+ | "was MSRP" = manufacturer list price, actual street price may differ`);

    if (errors.length > 0) {
      errors.forEach(e => lines.push(`\u26A0\uFE0F ${e.store}: ${e.error}`));
    }

    console.log(lines.join('\n'));
  }

  return allResults;
}

// ============================================================
// WATCHLIST
// ============================================================

function cmdWatch(query, opts) {
  db.addWatch({
    query,
    targetPrice: opts.target || null,
    url: opts.url || null,
    store: opts.store || null,
    notifyContact: opts.notify || 'user@example.com',
    notes: opts.notes || null,
  });
  console.log(`Added to watchlist: ${query}`);
  if (opts.target) console.log(`  Target: ${utils.formatPrice(opts.target)}`);
  if (opts.store) console.log(`  Store: ${opts.store}`);
  if (opts.url) console.log(`  URL: ${opts.url}`);
}

function cmdList() {
  const items = db.listWatch();
  if (items.length === 0) {
    console.log('Watchlist is empty.');
    return;
  }

  console.log(`\n=== WATCHLIST (${items.length} items) ===\n`);
  for (const item of items) {
    console.log(`  [${item.id}] ${item.query}`);
    if (item.target_price) console.log(`      Target: ${utils.formatPrice(item.target_price)}`);
    if (item.store) console.log(`      Store: ${item.store}`);
    if (item.url) console.log(`      URL: ${item.url}`);
    if (item.notes) console.log(`      Notes: ${item.notes}`);
    console.log(`      Added: ${item.added_at.substring(0, 10)}`);
    console.log();
  }
}

function cmdUnwatch(idOrQuery) {
  const id = parseInt(idOrQuery);
  if (!isNaN(id)) {
    const result = db.removeWatch(id);
    console.log(result.changes > 0 ? `Removed watchlist item #${id}` : `No watchlist item with ID ${id}`);
  } else {
    const result = db.removeWatchByQuery(idOrQuery);
    console.log(result.changes > 0 ? `Removed ${result.changes} item(s) matching: ${idOrQuery}` : `No active items matching: ${idOrQuery}`);
  }
}

// ============================================================
// CHECK (watchlist prices)
// ============================================================

async function cmdCheck() {
  const items = db.listWatch();
  if (items.length === 0) {
    console.log('Watchlist is empty. Add items with: node deals.cjs watch "product" --target 500');
    return;
  }

  console.log(`\n=== CHECKING ${items.length} WATCHLIST ITEMS ===\n`);

  const queries = [...new Set(items.map(i => i.query))]; // unique queries

  // Run all watchlist queries in parallel (max concurrency 3 to avoid overwhelming stores)
  const CONCURRENCY = 3;
  const allProducts = [];
  for (let i = 0; i < queries.length; i += CONCURRENCY) {
    const batch = queries.slice(i, i + CONCURRENCY);
    const settled = await Promise.allSettled(
      batch.map(query => {
        console.log(`  Checking: ${query}`);
        return cmdSearch(query, { top: 3, json: false });
      })
    );
    for (const result of settled) {
      if (result.status === 'fulfilled' && result.value) {
        allProducts.push(...result.value);
      }
    }
  }

  // Process alerts
  const alertResult = alerts.processAlerts(allProducts);
  if (alertResult.sent > 0) {
    console.log(`\n  Sent ${alertResult.sent} alert(s)`);
  }
  if (alertResult.skipped > 0) {
    console.log(`  Skipped ${alertResult.skipped} alert(s) (daily cap or dedup)`);
  }
}

// ============================================================
// HISTORY
// ============================================================

function cmdHistory(query) {
  const history = db.getPriceHistory(query, 30);
  if (history.length === 0) {
    console.log(`No price history for: ${query}`);
    return;
  }

  console.log(`\n=== PRICE HISTORY: ${query} ===\n`);

  let currentDate = null;
  for (const row of history) {
    const date = row.checked_at.substring(0, 10);
    if (date !== currentDate) {
      currentDate = date;
      console.log(`  ${date}`);
    }
    let line = `    ${(row.store || '').padEnd(12)} ${utils.formatPrice(row.price)}`;
    if (row.original_price) line += `  (was ${utils.formatPrice(row.original_price)})`;
    if (row.discount_percent) line += `  ${row.discount_percent}% off`;
    line += `  [${row.checked_at.substring(11, 16)}]`;
    console.log(line);
  }

  const stats = db.getPriceStats(query);
  if (stats && stats.checks > 0) {
    console.log(`\n  Low: ${utils.formatPrice(stats.low)}  High: ${utils.formatPrice(stats.high)}  Avg: ${utils.formatPrice(stats.avg)}`);
    console.log(`  Checks: ${stats.checks}  Period: ${stats.first_check?.substring(0, 10)} to ${stats.last_check?.substring(0, 10)}`);
    if (stats.lowestStore) {
      console.log(`  All-time low: ${utils.formatPrice(stats.lowestStore.price)} at ${stats.lowestStore.store} (${stats.lowestStore.checked_at?.substring(0, 10)})`);
    }
  }
  console.log();
}

// ============================================================
// ANALYZE ("is this a good deal?")
// ============================================================

function cmdAnalyze(query) {
  const stats = db.getPriceStats(query);
  const latest = db.getLatestPrice(query);

  if (!stats || stats.checks === 0) {
    console.log(`No data for: ${query}`);
    console.log(`Run a search first: node deals.cjs search "${query}"`);
    return;
  }

  console.log(`\n=== DEAL ANALYSIS: ${query} ===\n`);

  if (latest) {
    console.log(`  Current:       ${utils.formatPrice(latest.price)} at ${latest.store} (as of ${latest.checked_at?.substring(0, 10)})`);
  }
  console.log(`  All-time low:  ${utils.formatPrice(stats.low)}${stats.lowestStore ? ` at ${stats.lowestStore.store} (${stats.lowestStore.checked_at?.substring(0, 10)})` : ''}`);
  console.log(`  All-time high: ${utils.formatPrice(stats.high)}`);
  console.log(`  Average:       ${utils.formatPrice(stats.avg)} across ${stats.checks} checks`);

  if (latest && stats.avg) {
    const pctVsAvg = Math.round((1 - latest.price / stats.avg) * 100);
    const diffFromLow = Math.round((latest.price - stats.low) * 100) / 100;

    console.log();
    if (pctVsAvg > 0) {
      console.log(`  Current price is ${pctVsAvg}% below average.`);
    } else if (pctVsAvg < 0) {
      console.log(`  Current price is ${Math.abs(pctVsAvg)}% above average.`);
    } else {
      console.log('  Current price is at the average.');
    }

    if (diffFromLow > 0) {
      console.log(`  ${utils.formatPrice(diffFromLow)} above the all-time low.`);
    } else {
      console.log('  This IS the all-time low!');
    }

    // Verdict
    console.log();
    if (stats.checks < 5) {
      console.log(`  Verdict: INSUFFICIENT DATA - only ${stats.checks} data points. Keep tracking.`);
    } else if (diffFromLow === 0) {
      console.log('  Verdict: BEST PRICE EVER - buy now if you need it.');
    } else if (pctVsAvg >= 15) {
      console.log('  Verdict: GREAT DEAL - significantly below average.');
    } else if (pctVsAvg >= 5) {
      console.log('  Verdict: DECENT DEAL - below average but not the lowest.');
    } else if (pctVsAvg >= -5) {
      console.log('  Verdict: AVERAGE - wait for a sale if you can.');
    } else {
      console.log('  Verdict: BAD TIME TO BUY - price is above average.');
    }
  }

  console.log();
}

// ============================================================
// CRON (automated daily check)
// ============================================================

async function cmdCron() {
  console.log(`=== Deals Cron Run: ${new Date().toISOString()} ===`);

  const items = db.listWatch();
  if (items.length === 0) {
    console.log('No watchlist items. Nothing to do.');
    return;
  }

  console.log(`Checking ${items.length} watchlist items...`);

  const allProducts = [];
  const queries = [...new Set(items.map(i => i.query))];

  // Build search tasks with per-query store filters
  const searchTasks = queries.map(query => {
    const storeKeys = items.filter(i => i.query === query && i.store).map(i => i.store);
    const storeOpt = storeKeys.length > 0 ? storeKeys.join(',') : undefined;
    return { query, storeOpt };
  });

  // Run in parallel batches of 3
  const CONCURRENCY = 3;
  for (let i = 0; i < searchTasks.length; i += CONCURRENCY) {
    const batch = searchTasks.slice(i, i + CONCURRENCY);
    const settled = await Promise.allSettled(
      batch.map(({ query, storeOpt }) => {
        process.stderr.write(`\nSearching: ${query}\n`);
        return cmdSearch(query, { store: storeOpt, top: 3, json: false });
      })
    );
    for (let j = 0; j < settled.length; j++) {
      if (settled[j].status === 'fulfilled' && settled[j].value) {
        allProducts.push(...settled[j].value);
      } else if (settled[j].status === 'rejected') {
        console.error(`Error checking ${batch[j].query}: ${settled[j].reason?.message || 'Unknown'}`);
      }
    }
  }

  // Process alerts
  const alertResult = alerts.processAlerts(allProducts);
  console.log(`\nAlerts: ${alertResult.sent} sent, ${alertResult.skipped} skipped`);
  if (alertResult.capped) console.log('Alert cap reached for today.');

  // Prune old price history (keep 90 days)
  const pruned = db.pruneOldHistory(90);
  if (pruned > 0) console.log(`Pruned ${pruned} old price history entries.`);

  // Clear expired cache
  cache.clearExpired();

  await scraper.closeBrowser();
  console.log(`Done: ${new Date().toISOString()}`);
}

// ============================================================
// HEALTH (store status)
// ============================================================

function cmdHealth() {
  const health = db.getStoreHealth();
  const allStoreKeys = stores.getStoreKeys();

  console.log('\n=== STORE HEALTH ===\n');
  console.log('  Store           Type   Status           Failures  Last Success');
  console.log('  --------------  -----  ---------------  --------  -------------------');

  for (const key of allStoreKeys) {
    const name = stores.getStoreName(key);
    const h = health.find(r => r.store === key);
    const isHttp = HTTP_STORE_KEYS.has(key);
    const type = stores.isApiStore(key) ? 'API' : (isHttp ? 'HTTP' : 'PW');
    const disabled = db.isStoreDisabled(key);

    let status = 'OK';
    if (disabled) status = 'DISABLED';
    else if (h && h.consecutive_failures > 0) status = `${h.consecutive_failures} failures`;

    const failures = h ? String(h.consecutive_failures) : '0';
    const lastSuccess = h && h.last_success_at ? h.last_success_at.substring(0, 19) : 'never';

    console.log(`  ${name.padEnd(16)}${type.padEnd(7)}${status.padEnd(17)}${failures.padEnd(10)}${lastSuccess}`);
  }
  console.log();
}

// ============================================================
// CLI ROUTER
// ============================================================

async function main() {
  const args = process.argv.slice(2);
  const cmd = args[0];

  if (!cmd) {
    printUsage();
    process.exit(0);
  }

  // Parse flags
  const flags = {};
  const positional = [];
  for (let i = 1; i < args.length; i++) {
    if (args[i].startsWith('--')) {
      const key = args[i].substring(2);
      if (i + 1 < args.length && !args[i + 1].startsWith('--')) {
        flags[key] = args[i + 1];
        i++;
      } else {
        flags[key] = true;
      }
    } else {
      positional.push(args[i]);
    }
  }

  try {
    switch (cmd) {
      case 'search':
      case 's':
        if (!positional[0]) { console.error('Usage: deals.cjs search "query"'); process.exit(1); }
        await cmdSearch(positional[0], {
          store: flags.store,
          json: !!flags.json,
          top: flags.top ? parseInt(flags.top) : undefined,
          category: flags.category,
          maxPrice: flags['max-price'] ? parseFloat(flags['max-price']) : undefined,
          minPrice: flags['min-price'] ? parseFloat(flags['min-price']) : undefined,
        });
        break;

      case 'watch':
      case 'w':
        if (!positional[0]) { console.error('Usage: deals.cjs watch "query" --target 500'); process.exit(1); }
        cmdWatch(positional[0], {
          target: flags.target ? parseFloat(flags.target) : undefined,
          url: flags.url,
          store: flags.store,
          notify: flags.notify,
          notes: flags.notes,
        });
        break;

      case 'list':
      case 'ls':
        cmdList();
        break;

      case 'unwatch':
      case 'rm':
        if (!positional[0]) { console.error('Usage: deals.cjs unwatch <id or query>'); process.exit(1); }
        cmdUnwatch(positional[0]);
        break;

      case 'check':
      case 'c':
        await cmdCheck();
        break;

      case 'history':
      case 'hist':
        if (!positional[0]) { console.error('Usage: deals.cjs history "query"'); process.exit(1); }
        cmdHistory(positional[0]);
        break;

      case 'analyze':
      case 'a':
        if (!positional[0]) { console.error('Usage: deals.cjs analyze "query"'); process.exit(1); }
        cmdAnalyze(positional[0]);
        break;

      case 'cron':
        await cmdCron();
        break;

      case 'health':
        cmdHealth();
        break;

      default:
        console.error(`Unknown command: ${cmd}`);
        printUsage();
        process.exit(1);
    }
  } catch (e) {
    console.error(`Error: ${e.message}`);
    process.exit(1);
  } finally {
    db.closeDb();
    await scraper.closeBrowser().catch(() => {});
  }
}

function printUsage() {
  console.log(`
Deals - Price Search & Tracking

Usage:
  node deals.cjs search "query"              Search all stores
  node deals.cjs search "query" --store bestbuy  Search specific store
  node deals.cjs search "query" --json       JSON output
  node deals.cjs search "query" --top 3      Limit results per store
  node deals.cjs search "query" --max-price 1000  Max price filter
  node deals.cjs search "query" --min-price 200   Min price filter

  node deals.cjs watch "query" --target 500  Add to watchlist
  node deals.cjs list                        Show watchlist
  node deals.cjs check                       Check watchlist prices
  node deals.cjs unwatch <id>                Remove from watchlist
  node deals.cjs history "query"             Price history
  node deals.cjs analyze "query"             Is this a good deal?

  node deals.cjs cron                        Automated check + alerts
  node deals.cjs health                      Store health status

Stores: ${stores.getStoreKeys().join(', ')}
`);
}

main();
