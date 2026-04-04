"""Tools for searching and reading PensionPro help center articles."""

import json
from importlib import resources
from typing import Any


def _load_articles() -> list[dict[str, Any]]:
    """Load bundled help articles from the data directory."""
    data_file = resources.files("pension_pro_mcp.data").joinpath("help_articles.json")
    content = data_file.read_text(encoding="utf-8")
    return json.loads(content).get("articles", [])


# Load once at module import
_ARTICLES = _load_articles()


def search_help(keyword: str, section: str | None = None) -> list[dict[str, Any]]:
    """Search help articles by keyword, optionally filtered by section.

    Returns matching articles with title, section, URL, and a snippet.
    """
    keyword = keyword.lower()
    results = []
    for article in _ARTICLES:
        if section and article["section"].lower() != section.lower():
            continue
        if keyword in article["title"].lower() or keyword in article["body"].lower():
            # Extract a snippet around the first match in the body
            body_lower = article["body"].lower()
            idx = body_lower.find(keyword)
            if idx >= 0:
                start = max(0, idx - 100)
                end = min(len(article["body"]), idx + len(keyword) + 100)
                snippet = article["body"][start:end].strip()
                if start > 0:
                    snippet = "..." + snippet
                if end < len(article["body"]):
                    snippet = snippet + "..."
            else:
                snippet = article["body"][:200].strip() + "..."

            results.append({
                "id": article["id"],
                "title": article["title"],
                "section": article["section"],
                "url": article["url"],
                "snippet": snippet,
            })
    return results


def get_help_article(article_id: int) -> dict[str, Any]:
    """Get the full content of a help article by ID."""
    for article in _ARTICLES:
        if article["id"] == article_id:
            return {
                "id": article["id"],
                "title": article["title"],
                "section": article["section"],
                "url": article["url"],
                "body": article["body"],
                "updated_at": article["updated_at"],
            }
    return {"error": f"Article not found: {article_id}"}


def list_help_sections() -> list[dict[str, Any]]:
    """List all available help sections with article counts."""
    sections: dict[str, int] = {}
    for article in _ARTICLES:
        sections[article["section"]] = sections.get(article["section"], 0) + 1
    return [{"section": name, "article_count": count} for name, count in sorted(sections.items())]
