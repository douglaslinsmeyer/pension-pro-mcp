#!/usr/bin/env python3
"""Scrape PensionPro help center articles via the Zendesk API.

Fetches all articles from the Features category and outputs a structured
JSON file for bundling with the MCP server.

Usage:
    python scripts/scrape_docs.py

Output:
    src/pension_pro_mcp/data/help_articles.json
"""

import html
import json
import re
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "https://support.pensionpro.com/api/v2/help_center/en-us"
FEATURES_CATEGORY_ID = 200330905
OUTPUT_PATH = Path(__file__).parent.parent / "src" / "pension_pro_mcp" / "data" / "help_articles.json"

# Rate limit: be polite to the Zendesk API
REQUEST_DELAY = 0.5


def strip_html(text: str) -> str:
    """Convert HTML to plain text, preserving structure."""
    # Replace common block elements with newlines
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</(?:p|div|h[1-6]|li|tr|blockquote)>", "\n", text)
    text = re.sub(r"<(?:p|div|h[1-6]|blockquote)[^>]*>", "\n", text)

    # List items get a bullet
    text = re.sub(r"<li[^>]*>", "  - ", text)

    # Table cells get a separator
    text = re.sub(r"<td[^>]*>", " | ", text)
    text = re.sub(r"<tr[^>]*>", "\n", text)

    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)

    # Decode HTML entities
    text = html.unescape(text)

    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def fetch_json(client: httpx.Client, url: str) -> dict:
    """Fetch JSON from URL with rate limiting."""
    time.sleep(REQUEST_DELAY)
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def fetch_all_pages(client: httpx.Client, url: str, key: str) -> list:
    """Fetch all pages of a paginated Zendesk API response."""
    results = []
    while url:
        data = fetch_json(client, url)
        results.extend(data.get(key, []))
        url = data.get("next_page")
    return results


def main() -> None:
    print(f"Fetching articles from PensionPro help center...")

    with httpx.Client(timeout=30.0) as client:
        # Step 1: Get all sections in the Features category
        sections_url = f"{BASE_URL}/categories/{FEATURES_CATEGORY_ID}/sections.json"
        sections = fetch_all_pages(client, sections_url, "sections")
        print(f"  Found {len(sections)} sections")

        # Step 2: For each section, get all articles
        all_articles = []
        for section in sections:
            section_id = section["id"]
            section_name = section["name"]
            articles_url = f"{BASE_URL}/sections/{section_id}/articles.json"
            articles = fetch_all_pages(client, articles_url, "articles")
            print(f"  {section_name}: {len(articles)} articles")

            for article in articles:
                body_html = article.get("body") or ""
                all_articles.append({
                    "id": article["id"],
                    "title": article["title"],
                    "section": section_name,
                    "url": article["html_url"],
                    "body": strip_html(body_html),
                    "updated_at": article["updated_at"],
                })

    # Step 3: Write output
    output = {
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "https://support.pensionpro.com/hc/en-us/categories/200330905-Features",
        "article_count": len(all_articles),
        "articles": all_articles,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {len(all_articles)} articles to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
