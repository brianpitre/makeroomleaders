# Workflow: Scrape & Mirror Website Locally

## Objective
Create and maintain a fully local static copy of `https://makeroomleaders.com/` in `site/` for offline design iteration without touching WordPress.

## Required Inputs
- Internet access to `makeroomleaders.com`
- Python 3 with: `requests`, `beautifulsoup4`, `lxml`, `cssutils`
  - Install: `pip3 install requests beautifulsoup4 lxml cssutils`

## Pages Scraped
| URL | Local output |
|-----|--------------|
| `/` | `site/index.html` |
| `/whiteboard-sessions/` | `site/whiteboard-sessions/index.html` |
| `/cohort/` | `site/cohort/index.html` |
| `/international-events/` | `site/international-events/index.html` |
| `/other-events/` | `site/other-events/index.html` |
| `/about/` | `site/about/index.html` |
| `/resources/` | `site/resources/index.html` |
| `/sponsors/` | `site/sponsors/index.html` |

## Execution Steps

### Full scrape (first time or after site update)
```bash
python3 tools/scrape_single_site.py --force
```

### Incremental scrape (skip cached files)
```bash
python3 tools/scrape_single_site.py
```

### Pages only (verify HTML, skip asset download)
```bash
python3 tools/scrape_single_site.py --pages-only
```

### After running: verify
1. Check `.tmp/scrape_log.json` — look for `"status": "error"` entries
2. Start local server: `cd site && python3 -m http.server 8080`
3. Open `http://localhost:8080` — verify homepage renders with styles and fonts
4. Click each nav link — verify all 8 pages load correctly
5. Check browser DevTools console for any 404 errors on assets

## Design Change Guide

### The single most important file for design
`site/assets/css/global-styles.css` — extracted from WordPress inline styles. Contains:
- CSS custom properties (color palette, spacing)
- `@font-face` declarations for all 4 fonts
- Typography scale

**Edit this file for site-wide color/font/spacing changes.**

### Design change map
| What to change | File |
|----------------|------|
| Color palette | `site/assets/css/global-styles.css` → CSS custom properties |
| Font family | `site/assets/css/global-styles.css` → `@font-face` + `font-family` vars |
| Font sizes / weights | `site/assets/css/global-styles.css` → typography section |
| Button styles | `site/assets/css/blocks/button.css` (or inline style in page HTML) |
| Navigation / header | Inline `<style>` block in page `<head>` + `global-styles.css` |
| Hero section | `site/index.html` → hero group block |
| Page section content | Individual `site/<page>/index.html` files |
| Add new section | Edit relevant `site/<page>/index.html` |
| Reorder sections | Edit relevant `site/<page>/index.html` |

### Design iteration cycle
1. Edit the target file
2. Refresh `http://localhost:8080/<page>/`
3. Iterate until satisfied
4. Record changes in `site/CHANGES.md` to preserve them if re-scraping

## Known Constraints

- **Smart Slider 3 animations**: The carousel renders its first slide as a static fallback. Full slider JS is downloaded but may not fully initialize in the static context. This is expected.
- **Cloudflare email obfuscation**: Links using `/cdn-cgi/l/email-protection` will appear broken. Cloudflare's script decodes them client-side — this works on the live site but not in the static copy.
- **`data:` URI SVGs**: Smart Slider uses base64-encoded SVG data URIs for nav arrows. These are already embedded and work fine.
- **WordPress admin bar**: Stripped from the static copy automatically.
- **Login-walled pages**: Cannot be scraped. Only public pages are included.
- **Re-scraping overwrites**: A `--force` re-scrape will overwrite all files in `site/`. Document local design changes in `site/CHANGES.md` first.

## Self-Improvement Notes
_Update this section when you discover new constraints or better approaches._

- **2026-03-17**: Initial scrape successful. 91 assets (89 ok, 2 harmless data: URI false-positives that were subsequently filtered). `global-styles.css` extraction works correctly.
