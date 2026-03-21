---
name: frontend
description: Use when building React/Next.js components, dashboards, admin panels, apps, or any web interface. Trigger words - react, frontend, ui, dashboard, component, interface, web app, polish, audit, design review.
---

# Frontend Development

Build frontend interfaces with craft and consistency.

## The Impeccable Loop

Every UI task follows this quality loop:

1. **Build** — initial implementation
2. **/audit** — find issues (a11y, perf, responsive, anti-patterns)
3. **/critique** — UX review (hierarchy, clarity, emotional resonance)
4. **Fix** — use `/normalize`, `/harden`, `/optimize`, `/colorize` as needed
5. **/polish** — final pre-ship pass
6. **Repeat** — until audit comes back clean

This loop is non-negotiable. Ship nothing without running it.

## Before Building: Read the Design Principles

**Read `./impeccable/frontend-design/SKILL.md` before writing any UI code.**

It contains:
- Design direction (bold aesthetic choices)
- Typography, color, layout, motion guidelines
- The "AI Slop Test" — does it look AI-generated?
- Explicit anti-patterns to avoid (Inter font, purple gradients, cards-in-cards, bounce easing, etc.)

Reference docs in `./impeccable/frontend-design/reference/`:
- typography.md — scales, pairing, font loading
- color-and-contrast.md — OKLCH, tinted neutrals, dark mode
- spatial-design.md — grids, rhythm, container queries
- motion-design.md — easing, staggering, reduced motion
- interaction-design.md — forms, focus, loading patterns
- responsive-design.md — mobile-first, fluid design
- ux-writing.md — labels, errors, empty states

## Visual Language (This System)

For THIS system's specific look, read `./interface-design/SKILL.md`:
- Manrope font (NOT Inter)
- Cream background `#f5f3f0` (NOT white, NOT dark)
- No shadows, sharp corners (`border-radius: 0`)
- Orange accent `#ea580c` — ONE accent only
- Reference: https://interface-design.dev

## Impeccable Commands

| Command | Purpose |
|---------|---------|
| `/audit` | Find issues: a11y, perf, theming, responsive, anti-patterns |
| `/critique` | UX design review: hierarchy, clarity, emotional resonance |
| `/normalize` | Align with design system standards |
| `/polish` | Final pre-ship quality pass |
| `/distill` | Strip to essence, remove complexity |
| `/clarify` | Improve unclear UX copy |
| `/optimize` | Performance improvements |
| `/harden` | Error handling, i18n, edge cases |
| `/animate` | Add purposeful motion |
| `/colorize` | Introduce strategic color |
| `/bolder` | Amplify boring designs |
| `/quieter` | Tone down overly bold designs |
| `/delight` | Add moments of joy |
| `/extract` | Pull into reusable components |
| `/adapt` | Adapt for different devices |
| `/onboard` | Design onboarding flows |
| `/teach-impeccable` | Gather design context for new projects |

Each command's full instructions are in `./impeccable/{command}/SKILL.md`.

## The Process

1. **Read** `./impeccable/frontend-design/SKILL.md` completely
2. **Read** `./interface-design/SKILL.md` for this system's visual language
3. **Explore the domain** — produce 4 outputs:
   - Domain: 5+ concepts from the product's world
   - Color world: 5+ colors that exist naturally in this domain
   - Signature: One element unique to this product
   - Defaults: 3 obvious choices to reject
4. **Propose direction** — reference all 4 explorations
5. **Get confirmation** — "Does this direction feel right?"
6. **Build** — apply principles
7. **Run the loop** — audit → critique → fix → polish → repeat
8. **Self-check** — swap test, squint test, signature test, token test

## Supporting References

### UI/UX Pro Max — Design Intelligence Database

Read `./ui-ux-pro-max/SKILL.md` for comprehensive design guidance. Contains:
- **99 UX guidelines** (prioritized: accessibility → touch → performance → layout → animation → forms → navigation → charts)
- **161 color palettes** by product type (SaaS, dashboard, fintech, healthcare, etc.)
- **57 font pairings** with Google Fonts recommendations
- **50+ design styles** (glassmorphism, minimalism, brutalism, dark mode, etc.)
- **25 chart types** with library recommendations
- **161 product type patterns** with reasoning rules

Has a Python search CLI for querying the database:
```bash
uv run ~/.claude/skills/frontend/ui-ux-pro-max/scripts/search.py "<query>" --domain <domain>
# Domains: product, style, color, typography, chart, ux, landing, google-fonts, react, web, prompt
# Example: uv run scripts/search.py "dark dashboard monitoring" --domain style
# Design system: uv run scripts/search.py "ops dashboard" --design-system
```

Key UX rules for dashboards/command centers:
- Contrast 4.5:1, keyboard nav, aria-labels (Priority 1: Accessibility)
- Min touch target 44x44px, loading feedback (Priority 2: Touch)
- Skeleton screens for >1s loads, virtualize 50+ item lists (Priority 3: Performance)
- Mobile-first breakpoints, no horizontal scroll (Priority 5: Layout)
- Chart legends always visible, tooltips on interact, accessible colors (Priority 10: Charts)

### Vercel React Best Practices

Read `./vercel-react/SKILL.md` and `./vercel-react/AGENTS.md` for React/Next.js code. 57 rules across 8 categories:
- Eliminating waterfalls
- Bundle size optimization
- Server-side performance

Individual rules in `./vercel-react/rules/`.

### Web Design Guidelines

Read `./web-design-guidelines/SKILL.md` for accessibility audits.

## The Test

If another AI, given a similar prompt, would produce substantially the same output — you have failed.

If you swapped your choices for the most common alternatives and the design didn't feel meaningfully different, you never made real choices.
