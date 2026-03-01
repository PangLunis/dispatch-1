---
name: html-reports
description: Create HTML reports, explainers, and dashboards with consistent dark theme styling. Use when generating HTML output for sharing via iMessage or sven-pages. Trigger words - report, explainer, dashboard, html, visualize.
---

# HTML Reports

Generate consistent, hermetic HTML reports with tight padding and dark theme.

## Style Guidelines

**ALWAYS use these principles:**

- **Tight padding**: 8-12px, never gaudy spacing
- **Dark theme**: `#0d1117` background, `#c9d1d9` text
- **Small fonts**: 12-13px body, 16px h1, 12px h2
- **Compact cards**: 1px borders, 4-6px border-radius
- **Inline styles**: No external CSS, fully hermetic

## Base Template

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{TITLE}}</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;padding:12px;line-height:1.3;font-size:13px}
h1{font-size:16px;color:#58a6ff;margin-bottom:8px;border-bottom:1px solid #30363d;padding-bottom:6px}
h2{font-size:12px;color:#8b949e;margin:10px 0 4px;text-transform:uppercase;letter-spacing:0.5px}
.section{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:8px;margin-bottom:8px}
.badge{display:inline-block;font-size:9px;font-weight:600;padding:1px 4px;border-radius:3px;margin-left:4px;vertical-align:middle}
.new{background:#1f6feb;color:#fff}
.fix{background:#238636;color:#fff}
.warn{background:#d29922;color:#000}
code{background:#21262d;padding:1px 4px;border-radius:2px;font-size:11px;color:#79c0ff}
ul{margin:4px 0 0 12px}
li{margin:2px 0}
.highlight{border-left:2px solid #58a6ff;padding-left:8px;margin:4px 0;font-size:12px;color:#8b949e}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{padding:4px 6px;text-align:left;border-bottom:1px solid #30363d}
th{color:#8b949e;font-weight:500}
</style>
</head>
<body>
<h1>{{TITLE}}</h1>
{{CONTENT}}
</body>
</html>
```

## Color Palette

| Use | Color | Hex |
|-----|-------|-----|
| Background | Dark | `#0d1117` |
| Card bg | Slightly lighter | `#161b22` |
| Border | Subtle | `#30363d` |
| Text | Light gray | `#c9d1d9` |
| Muted | Gray | `#8b949e` |
| Link/accent | Blue | `#58a6ff` |
| Code | Light blue | `#79c0ff` |
| Success | Green | `#238636` |
| New | Blue | `#1f6feb` |
| Warning | Yellow | `#d29922` |

## Badge Classes

```html
<span class="badge new">NEW</span>
<span class="badge fix">FIX</span>
<span class="badge warn">WARN</span>
```

## Section Cards

```html
<div class="section">
<h2>Section Title<span class="badge new">NEW</span></h2>
<p>Description text</p>
<ul>
<li>Item 1</li>
<li>Item 2</li>
</ul>
<div class="highlight">Important callout</div>
</div>
```

## Sending Reports

```bash
# Via iMessage
~/.claude/skills/sms-assistant/scripts/send-sms "chat_id" --file report.html

# Via sven-pages (permanent URL)
~/.claude/skills/sven-pages/scripts/publish ./report-folder --public
```

## Examples

### Status Dashboard
- System metrics with tables
- Color-coded status badges
- Compact card layout

### Feature Explainer
- Per-feature sections
- Code snippets in monospace
- Flow diagrams with arrows

### Diff Summary
- Changed files list
- Before/after comparisons
- Commit info footer
