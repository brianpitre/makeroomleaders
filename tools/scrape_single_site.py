#!/usr/bin/env python3
"""
scrape_single_site.py
WAT Framework Tool — Phase C (Asset Execution)

Mirrors https://makeroomleaders.com/ as a fully local static site in site/.
Rewrites all internal URLs to relative paths so the site works offline.

Usage:
    python tools/scrape_single_site.py              # full scrape
    python tools/scrape_single_site.py --force      # re-download everything
    python tools/scrape_single_site.py --pages-only # fetch HTML only
    python tools/scrape_single_site.py --assets-only# download assets, skip page fetch
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "https://makeroomleaders.com"
BASE_DIR = Path(__file__).parent.parent  # project root
SITE_DIR = BASE_DIR / "site"
TMP_DIR  = BASE_DIR / ".tmp"
LOG_FILE = TMP_DIR / "scrape_log.json"

PAGES = [
    ("",                    "index"),
    ("/whiteboard-sessions/", "whiteboard-sessions"),
    ("/cohort/",             "cohort"),
    ("/international-events/", "international-events"),
    ("/other-events/",       "other-events"),
    ("/about/",              "about"),
    ("/resources/",          "resources"),
    ("/sponsors/",           "sponsors"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log_entries = []

def log(status, url, local_path="", note=""):
    entry = {"status": status, "url": url, "local": str(local_path), "note": note}
    log_entries.append(entry)
    symbol = {"ok": "✓", "skip": "–", "error": "✗", "info": "i"}.get(status, "?")
    print(f"  [{symbol}] {status:5} {url[:80]}")

def save_log():
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w") as f:
        json.dump(log_entries, f, indent=2)

# ---------------------------------------------------------------------------
# Asset manifest  {absolute_url: local_path}
# ---------------------------------------------------------------------------

asset_manifest = {}  # str -> Path

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def is_internal(url):
    if url.startswith("data:"):
        return False
    parsed = urlparse(url)
    return parsed.netloc in ("", "makeroomleaders.com", "www.makeroomleaders.com")

def absolute(url, page_url):
    return urljoin(page_url, url)

def url_to_local_asset_path(url):
    """Map an absolute internal asset URL to a local path under site/assets/."""
    parsed = urlparse(url)
    path = unquote(parsed.path)

    if "/wp-content/uploads/" in path:
        filename = Path(path).name
        return SITE_DIR / "assets" / "images" / filename

    if "/wp-content/themes/" in path and "/fonts/" in path:
        filename = Path(path).name
        family = Path(path).parent.name
        return SITE_DIR / "assets" / "fonts" / family / filename

    if "/wp-content/themes/" in path:
        # theme CSS or other theme assets
        rel = path.split("/wp-content/themes/", 1)[1]
        return SITE_DIR / "assets" / "theme" / rel.lstrip("/")

    if "/wp-content/plugins/smart-slider-3/" in path:
        rel = path.split("/wp-content/plugins/smart-slider-3/", 1)[1]
        return SITE_DIR / "assets" / "js" / "smart-slider" / rel.lstrip("/")

    if "/wp-content/plugins/" in path:
        rel = path.split("/wp-content/plugins/", 1)[1]
        return SITE_DIR / "assets" / "js" / "plugins" / rel.lstrip("/")

    if "/wp-includes/css/" in path:
        rel = path.split("/wp-includes/css/", 1)[1]
        return SITE_DIR / "assets" / "css" / rel.lstrip("/")

    if "/wp-includes/js/" in path:
        rel = path.split("/wp-includes/js/", 1)[1]
        return SITE_DIR / "assets" / "js" / "wp-includes" / rel.lstrip("/")

    if "/wp-includes/" in path:
        rel = path.split("/wp-includes/", 1)[1]
        return SITE_DIR / "assets" / "wp-includes" / rel.lstrip("/")

    # fallback: mirror path structure
    clean = path.lstrip("/")
    return SITE_DIR / "assets" / "misc" / clean

def relative_path(from_file, to_file):
    """Compute a relative path from from_file to to_file (both Path objects)."""
    return Path(os.path.relpath(to_file, from_file.parent))

# ---------------------------------------------------------------------------
# Fetch helper
# ---------------------------------------------------------------------------

def fetch(url, timeout=15, retries=2):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
            resp.raise_for_status()
            return resp
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                raise e

# ---------------------------------------------------------------------------
# Phase A — Fetch pages
# ---------------------------------------------------------------------------

def fetch_pages(force=False):
    print("\n=== Phase A: Fetching pages ===")
    raw_pages = {}
    for path, slug in PAGES:
        url = BASE_URL + path
        raw_file = TMP_DIR / f"raw_{slug}.html"
        if raw_file.exists() and not force:
            log("skip", url, raw_file, "cached")
            raw_pages[slug] = raw_file.read_text(encoding="utf-8")
            continue
        try:
            resp = fetch(url)
            TMP_DIR.mkdir(parents=True, exist_ok=True)
            raw_file.write_bytes(resp.content)
            log("ok", url, raw_file)
            raw_pages[slug] = resp.text
        except Exception as e:
            log("error", url, note=str(e))
    return raw_pages

# ---------------------------------------------------------------------------
# Phase B — Discover assets
# ---------------------------------------------------------------------------

def discover_assets(raw_pages):
    print("\n=== Phase B: Discovering assets ===")
    for slug, html in raw_pages.items():
        page_url = BASE_URL + ("/" if slug == "index" else f"/{slug}/")
        soup = BeautifulSoup(html, "lxml")

        # CSS link tags
        for tag in soup.find_all("link", rel=lambda r: r and "stylesheet" in r):
            href = tag.get("href", "")
            if href:
                abs_url = absolute(href, page_url)
                if is_internal(abs_url):
                    local = url_to_local_asset_path(abs_url)
                    asset_manifest[abs_url] = local

        # script tags
        for tag in soup.find_all("script", src=True):
            src = tag["src"]
            abs_url = absolute(src, page_url)
            if is_internal(abs_url):
                local = url_to_local_asset_path(abs_url)
                asset_manifest[abs_url] = local

        # img tags (src + srcset)
        for tag in soup.find_all("img"):
            src = tag.get("src", "")
            if src:
                abs_url = absolute(src, page_url)
                if is_internal(abs_url):
                    asset_manifest[abs_url] = url_to_local_asset_path(abs_url)
            srcset = tag.get("srcset", "")
            for part in srcset.split(","):
                part = part.strip().split()[0] if part.strip() else ""
                if part:
                    abs_url = absolute(part, page_url)
                    if is_internal(abs_url):
                        asset_manifest[abs_url] = url_to_local_asset_path(abs_url)

        # inline style url() references
        for style_tag in soup.find_all("style"):
            _collect_css_urls(style_tag.string or "", page_url)

    print(f"  Found {len(asset_manifest)} unique assets")

def _collect_css_urls(css_text, base_url):
    for match in re.finditer(r'url\(["\']?(https?://[^"\')\s]+|/[^"\')\s]+)["\']?\)', css_text):
        url = match.group(1)
        abs_url = absolute(url, base_url)
        if is_internal(abs_url):
            asset_manifest[abs_url] = url_to_local_asset_path(abs_url)

# ---------------------------------------------------------------------------
# Phase C — Download assets
# ---------------------------------------------------------------------------

def download_assets(force=False):
    print(f"\n=== Phase C: Downloading {len(asset_manifest)} assets ===")
    global_styles_saved = False

    for url, local_path in asset_manifest.items():
        if local_path.exists() and not force:
            log("skip", url, local_path, "cached")
            continue
        try:
            resp = fetch(url)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(resp.content)
            log("ok", url, local_path)

            # If it's a CSS file, scan it for more url() references and rewrite them
            if local_path.suffix.lower() == ".css":
                _process_css_file(local_path, url)

        except Exception as e:
            log("error", url, local_path, str(e))

def _process_css_file(css_path, css_url):
    """Scan a downloaded CSS file for url() references, download them, rewrite to relative paths."""
    try:
        css_text = css_path.read_text(encoding="utf-8", errors="replace")
        modified = css_text

        def replace_url(match):
            raw = match.group(1).strip("'\"")
            abs_url = absolute(raw, css_url)
            if not is_internal(abs_url):
                return match.group(0)
            local = url_to_local_asset_path(abs_url)
            asset_manifest[abs_url] = local
            if not local.exists():
                try:
                    resp = fetch(abs_url)
                    local.parent.mkdir(parents=True, exist_ok=True)
                    local.write_bytes(resp.content)
                    log("ok", abs_url, local, "from css")
                except Exception as e:
                    log("error", abs_url, local, str(e))
                    return match.group(0)
            rel = relative_path(css_path, local)
            return f"url('{rel}')"

        modified = re.sub(r'url\((["\']?[^)]+["\']?)\)', replace_url, modified)
        if modified != css_text:
            css_path.write_text(modified, encoding="utf-8")
    except Exception as e:
        log("error", str(css_path), note=f"CSS processing failed: {e}")

# ---------------------------------------------------------------------------
# Phase D — Extract global-styles inline block
# ---------------------------------------------------------------------------

GLOBAL_STYLES_CSS = SITE_DIR / "assets" / "css" / "global-styles.css"
_global_styles_content = None

def extract_global_styles(html, page_url):
    """
    Find the WordPress global styles <style id="global-styles-inline-css"> block,
    save it as a shared CSS file (once), and return the style tag for removal.
    """
    global _global_styles_content
    soup = BeautifulSoup(html, "lxml")
    style_tag = soup.find("style", id="global-styles-inline-css")
    if not style_tag:
        # Also try the wp-block-library or any large inline style
        style_tag = soup.find("style", id=lambda x: x and "global" in x.lower())
    if style_tag and _global_styles_content is None:
        css_text = style_tag.string or ""
        # Rewrite url() refs in the CSS to point to local assets
        css_text = _rewrite_css_urls(css_text, page_url, GLOBAL_STYLES_CSS)
        GLOBAL_STYLES_CSS.parent.mkdir(parents=True, exist_ok=True)
        GLOBAL_STYLES_CSS.write_text(css_text, encoding="utf-8")
        _global_styles_content = css_text
        log("ok", "global-styles extracted", GLOBAL_STYLES_CSS)
    return style_tag

def _rewrite_css_urls(css_text, base_url, css_local_path):
    def replace(match):
        raw = match.group(1).strip("'\"")
        if raw.startswith("data:"):
            return match.group(0)
        abs_url = absolute(raw, base_url)
        if not is_internal(abs_url):
            return match.group(0)
        local = url_to_local_asset_path(abs_url)
        asset_manifest[abs_url] = local
        if not local.exists():
            try:
                resp = fetch(abs_url)
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(resp.content)
                log("ok", abs_url, local, "from inline css")
            except Exception as e:
                log("error", abs_url, note=str(e))
                return match.group(0)
        rel = relative_path(css_local_path, local)
        return f"url('{rel}')"

    return re.sub(r'url\((["\']?[^)]+["\']?)\)', replace, css_text)

# ---------------------------------------------------------------------------
# Phase D — Rewrite and save HTML pages
# ---------------------------------------------------------------------------

def rewrite_and_save_pages(raw_pages):
    print("\n=== Phase D: Rewriting and saving pages ===")

    # Determine output path for each slug
    slug_to_output = {}
    for path, slug in PAGES:
        if slug == "index":
            slug_to_output[slug] = SITE_DIR / "index.html"
        else:
            slug_to_output[slug] = SITE_DIR / slug / "index.html"

    # Internal URL slug mapping
    slug_map = {
        BASE_URL + "/": "index",
        BASE_URL:        "index",
    }
    for path, slug in PAGES:
        if slug != "index":
            slug_map[BASE_URL + path] = slug
            slug_map[BASE_URL + path.rstrip("/")] = slug

    for slug, html in raw_pages.items():
        page_url = BASE_URL + ("/" if slug == "index" else f"/{slug}/")
        out_path = slug_to_output[slug]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        depth = 0 if slug == "index" else 1

        soup = BeautifulSoup(html, "lxml")

        # 1. Extract & replace global-styles inline block
        gs_tag = extract_global_styles(html, page_url)
        if gs_tag:
            new_link = soup.new_tag("link", rel="stylesheet",
                                    href=("assets/css/global-styles.css" if depth == 0
                                          else "../assets/css/global-styles.css"))
            gs_tag.replace_with(new_link)

        # 2. Rewrite <link rel="stylesheet"> tags
        for tag in soup.find_all("link", rel=lambda r: r and "stylesheet" in r):
            href = tag.get("href", "")
            if not href:
                continue
            abs_url = absolute(href, page_url)
            if is_internal(abs_url) and abs_url in asset_manifest:
                local = asset_manifest[abs_url]
                tag["href"] = str(relative_path(out_path, local))

        # 3. Rewrite <script src> tags
        for tag in soup.find_all("script", src=True):
            src = tag["src"]
            abs_url = absolute(src, page_url)
            if is_internal(abs_url) and abs_url in asset_manifest:
                local = asset_manifest[abs_url]
                tag["src"] = str(relative_path(out_path, local))

        # 4. Rewrite <img> src and srcset
        for tag in soup.find_all("img"):
            src = tag.get("src", "")
            if src:
                abs_url = absolute(src, page_url)
                if is_internal(abs_url) and abs_url in asset_manifest:
                    tag["src"] = str(relative_path(out_path, asset_manifest[abs_url]))
            srcset = tag.get("srcset", "")
            if srcset:
                new_parts = []
                for part in srcset.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    pieces = part.split()
                    url_part = pieces[0]
                    descriptor = pieces[1] if len(pieces) > 1 else ""
                    abs_url = absolute(url_part, page_url)
                    if is_internal(abs_url) and abs_url in asset_manifest:
                        local_rel = str(relative_path(out_path, asset_manifest[abs_url]))
                        new_parts.append(f"{local_rel} {descriptor}".strip())
                    else:
                        new_parts.append(part)
                tag["srcset"] = ", ".join(new_parts)

        # 5. Rewrite internal <a href> links
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            abs_url = absolute(href, page_url)
            if not is_internal(abs_url):
                continue
            parsed = urlparse(abs_url)
            clean = parsed.scheme + "://" + parsed.netloc + parsed.path
            clean_slash = clean.rstrip("/") + "/"
            clean_noslash = clean.rstrip("/")
            target_slug = (slug_map.get(clean_slash)
                           or slug_map.get(clean_noslash)
                           or slug_map.get(clean))
            if target_slug:
                target_out = slug_to_output[target_slug]
                tag["href"] = str(relative_path(out_path, target_out))
            # else leave as-is (e.g. anchor links, wp-admin, external)

        # 6. Rewrite remaining inline style url() references
        for style_tag in soup.find_all("style"):
            if style_tag.string:
                rewritten = _rewrite_css_urls(style_tag.string, page_url, out_path)
                style_tag.string.replace_with(rewritten)

        # 7. Rewrite Smart Slider 3 inline JSON image URLs
        for script_tag in soup.find_all("script"):
            if script_tag.string and "makeroomleaders.com" in (script_tag.string or ""):
                rewritten = re.sub(
                    r'(https://(?:www\.)?makeroomleaders\.com)(/wp-content/uploads/[^"\'\\]+)',
                    lambda m: _rewrite_ss3_url(m, out_path),
                    script_tag.string
                )
                script_tag.string.replace_with(rewritten)

        # 8. Strip WordPress admin/meta noise
        for tag in soup.find_all("link", rel=lambda r: r and any(
                x in (r if isinstance(r, list) else [r])
                for x in ["EditURI", "wlwmanifest", "shortlink"])):
            tag.decompose()
        for tag in soup.find_all("meta", attrs={"name": "generator"}):
            tag.decompose()

        # Write final HTML
        out_path.write_text(str(soup), encoding="utf-8")
        log("ok", page_url, out_path)

def _rewrite_ss3_url(match, out_path):
    full_url = match.group(1) + match.group(2)
    if full_url in asset_manifest:
        local = asset_manifest[full_url]
        rel = str(relative_path(out_path, local))
        return rel
    return full_url

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape makeroomleaders.com to a local static site")
    parser.add_argument("--force",       action="store_true", help="Re-download everything")
    parser.add_argument("--pages-only",  action="store_true", help="Only fetch HTML pages")
    parser.add_argument("--assets-only", action="store_true", help="Skip page fetch, download assets only")
    args = parser.parse_args()

    print(f"Target: {BASE_URL}")
    print(f"Output: {SITE_DIR}")

    raw_pages = {}

    if not args.assets_only:
        raw_pages = fetch_pages(force=args.force)

    if not raw_pages and not args.pages_only:
        # Load from cache for assets-only mode
        for _, slug in PAGES:
            raw_file = TMP_DIR / f"raw_{slug}.html"
            if raw_file.exists():
                raw_pages[slug] = raw_file.read_text(encoding="utf-8")
            else:
                print(f"  WARNING: No cached HTML for {slug} — run without --assets-only first")

    if raw_pages:
        discover_assets(raw_pages)

    if not args.pages_only:
        download_assets(force=args.force)

    if raw_pages and not args.pages_only and not args.assets_only:
        rewrite_and_save_pages(raw_pages)

    save_log()

    errors = [e for e in log_entries if e["status"] == "error"]
    print(f"\n=== Done ===")
    print(f"  Total assets: {len(asset_manifest)}")
    print(f"  Errors: {len(errors)}")
    if errors:
        print("\n  Failed downloads:")
        for e in errors:
            print(f"    {e['url']} — {e['note']}")
    print(f"\n  Log saved to: {LOG_FILE}")
    print(f"  Preview:  cd {SITE_DIR} && python3 -m http.server 8080")

if __name__ == "__main__":
    main()
