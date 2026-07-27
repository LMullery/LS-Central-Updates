#!/usr/bin/env python3
"""
LS Central release/hotfix RSS feed generator.

Scrapes the official LS Retail online help site for:
  1. Major/minor release notes (e.g. "LS Central 28.1 Release Notes")
  2. Per-version hotfix listings (e.g. "Hotfixes on LS Central version 28.1.x.x")

...and builds a single RSS 2.0 feed (feed.xml) from what it finds.

The hotfix pages are rendered client-side, so this uses Playwright
(headless Chromium) rather than a plain HTTP GET.

No external state is kept between runs - each run re-scrapes the
tracked versions and rebuilds the feed from scratch. Because the
source site keeps historical hotfix pages, entries don't need to be
"remembered" locally; RSS readers de-duplicate using the <guid> we
assign, which is stable across runs.
"""

import re
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin
from xml.sax.saxutils import escape

from playwright.sync_api import sync_playwright

BASE = "https://help.lscentral.lsretail.com"
RELEASE_NOTES_INDEX = f"{BASE}/Content/Release-Notes-LS-Central/Release-Notes-LS-Central.htm"
HOTFIXES_INDEX = f"{BASE}/Content/Hotfixes-And-Breaking-Changes.htm"

# How many of the most recent major/minor versions to pull hotfix pages for.
# The hotfix index lists every version back to 18.0; we don't need to
# re-scrape all of them every run.
VERSIONS_TO_TRACK = 3

# How many release-note pages (major/minor releases) to include.
RELEASES_TO_TRACK = 3

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 BC4-LSCentral-Feed-Bot/1.0"
)


def fetch_rendered(page, url):
    # The site embeds a support-chat widget that polls continuously, so it
    # never reaches "networkidle". Wait for the DOM instead, then give any
    # client-side rendering (the hotfix tables) a moment to finish.
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2000)
    return page.inner_text("body")


def find_links(page, url, href_pattern):
    """Return [(href, link_text)] for links on `url` whose href matches href_pattern."""
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2000)
    anchors = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(e => ({href: e.getAttribute('href'), text: e.innerText}))",
    )
    out = []
    seen = set()
    for a in anchors:
        href = a.get("href") or ""
        if href_pattern.search(href):
            full = urljoin(url, href)
            if full not in seen:
                seen.add(full)
                out.append((full, a.get("text", "").strip()))
    return out


def parse_release_note_page(text, url, title_hint):
    """Extract a short summary + release date from a release-notes page."""
    date_match = re.search(r"Released\s*-\s*([A-Za-z]+ \d{1,2},\s*\d{4})", text)
    pub_date = None
    if date_match:
        try:
            pub_date = datetime.strptime(date_match.group(1), "%B %d, %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            pub_date = None

    # Grab the "About This Release" blurb (up to "Quick links:", or the next
    # section heading if there is no quick-links block) as the description.
    about_match = re.search(
        r"About This Release\s*\n(.+?)(?:\nQuick links:|\n[A-Z][a-zA-Z ]+\n-{3,}|\Z)", text, re.S
    )
    summary = about_match.group(1).strip() if about_match else "See full release notes for details."
    summary = re.sub(r"\s+", " ", summary)[:500]

    title_match = re.search(r"^(LS[  ]Central [\d.]+ Release Notes)", text, re.M)
    title = title_match.group(1).replace(" ", " ") if title_match else title_hint

    return {
        "title": title,
        "link": url,
        "guid": f"release-{title}",
        "pub_date": pub_date or datetime.now(timezone.utc),
        "description": summary,
    }


def parse_hotfix_page(text, url, version_label):
    """Extract {category, name, date} entries from a rendered hotfix page."""
    entries = []
    category = None
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        m = re.match(r"^(.*?),\s*Release date\s+(.+)$", line)
        if m:
            name, date_str = m.group(1).strip(), m.group(2).strip()
            try:
                pub_date = datetime.strptime(date_str, "%B %d, %Y").replace(tzinfo=timezone.utc)
            except ValueError:
                pub_date = None
            entries.append(
                {
                    "title": f"LS Central {version_label} hotfix - {name} ({category or 'Uncategorised'})",
                    "link": url,
                    "guid": f"hotfix-{version_label}-{category}-{name}",
                    "pub_date": pub_date or datetime.now(timezone.utc),
                    "description": f"{category or 'Hotfix'} update {name}, released {date_str}.",
                }
            )
        elif line.lower().endswith("hotfixes") and "release date" not in line.lower():
            category = line
    return entries


def build_rss(items, feed_title, feed_link, feed_description):
    items_sorted = sorted(items, key=lambda i: i["pub_date"], reverse=True)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel>',
        f"<title>{escape(feed_title)}</title>",
        f"<link>{escape(feed_link)}</link>",
        f"<description>{escape(feed_description)}</description>",
        f"<lastBuildDate>{datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %z')}</lastBuildDate>",
    ]
    for item in items_sorted:
        parts.append(
            "<item>"
            f"<title>{escape(item['title'])}</title>"
            f"<link>{escape(item['link'])}</link>"
            f"<guid isPermaLink=\"false\">{escape(item['guid'])}</guid>"
            f"<pubDate>{item['pub_date'].strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>"
            f"<description>{escape(item['description'])}</description>"
            "</item>"
        )
    parts.append("</channel></rss>")
    return "\n".join(parts)


def main():
    all_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=USER_AGENT)

        # --- Major/minor release notes ---
        release_links = find_links(
            page, RELEASE_NOTES_INDEX, re.compile(r"LS-Central-[\d-]+-Release-Notes\.htm$")
        )[:RELEASES_TO_TRACK]

        for url, link_text in release_links:
            text = fetch_rendered(page, url)
            all_items.append(parse_release_note_page(text, url, link_text))

        # --- Hotfix pages, most recent N versions ---
        hotfix_links = find_links(page, HOTFIXES_INDEX, re.compile(r"/Content/Hotfixes/Hotfixes-[\d-]+\.htm$"))[
            :VERSIONS_TO_TRACK
        ]

        for url, link_text in hotfix_links:
            version_label = re.search(r"Hotfixes-([\d-]+)\.htm", url).group(1).replace("-", ".")
            text = fetch_rendered(page, url)
            all_items.extend(parse_hotfix_page(text, url, version_label))

        browser.close()

    if not all_items:
        print("No items scraped - aborting without overwriting feed.xml", file=sys.stderr)
        sys.exit(1)

    rss = build_rss(
        all_items,
        feed_title="LS Central Release Notes & Hotfixes (BC4 internal feed)",
        feed_link=RELEASE_NOTES_INDEX,
        feed_description=(
            "Unofficial feed generated from the official LS Retail online help site. "
            "Tracks the latest LS Central release notes and hotfixes for tracked versions."
        ),
    )

    with open("feed.xml", "w", encoding="utf-8") as f:
        f.write(rss)

    print(f"Wrote feed.xml with {len(all_items)} items")


if __name__ == "__main__":
    main()
