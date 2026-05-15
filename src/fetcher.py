"""News fetcher: RSS/Atom feeds + Hacker News Algolia API.

Reliable AI news sources that work from server environments:
  - Hacker News (via Algolia search API, no key needed)
  - arXiv cs.AI / cs.LG / cs.CL  (official API, no key)
  - RSS feeds with browser-like headers (best-effort)
"""

import re
import logging
import requests
import xml.etree.ElementTree as ET
import yaml
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from time import sleep
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

_ATOM = "http://www.w3.org/2005/Atom"
_CONTENT = "http://purl.org/rss/1.0/modules/content/"

# Mimic a modern browser to bypass basic bot detection on RSS endpoints
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
}

_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)


# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────

def load_config(config_path: str = "config/sources.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    date_str = date_str.strip()
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            raw = date_str[:len(fmt)]
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return None


def _get(url: str, retries: int = 3, **kwargs) -> Optional[requests.Response]:
    """GET with simple retry / back-off."""
    for attempt in range(retries):
        try:
            r = _SESSION.get(url, timeout=15, **kwargs)
            if r.status_code == 429:
                sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if attempt < retries - 1:
                sleep(2 ** attempt)
            else:
                logger.warning(f"HTTP error for {url}: {e}")
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Hacker News via Algolia API  (no API key, very reliable from servers)
# ──────────────────────────────────────────────────────────────────────────────

_HN_QUERIES = [
    "AI LLM GPT Claude Gemini",
    "artificial intelligence machine learning deep learning",
    "OpenAI Anthropic Google DeepMind Meta AI",
]

def fetch_hackernews(hours_lookback: int = 24, max_items: int = 20) -> List[Dict]:
    """Fetch AI-related HN stories via Algolia search (past N hours)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)
    seen: set = set()
    items: List[Dict] = []

    for query in _HN_QUERIES:
        if len(items) >= max_items:
            break
        url = (
            "https://hn.algolia.com/api/v1/search"
            f"?tags=story&query={requests.utils.quote(query)}"
            f"&hitsPerPage=20&numericFilters=created_at_i>"
            f"{int(cutoff.timestamp())}"
        )
        resp = _get(url)
        if resp is None:
            continue
        for hit in resp.json().get("hits", []):
            title = hit.get("title", "")
            if not title or title in seen:
                continue
            seen.add(title)
            pub_date = datetime.fromtimestamp(
                hit.get("created_at_i", 0), tz=timezone.utc
            )
            items.append({
                "title": title,
                "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                "summary": "",
                "published": pub_date.isoformat(),
                "source": "Hacker News",
                "language": "en",
            })
            if len(items) >= max_items:
                break

    logger.info(f"  [HN Algolia] {len(items)} items")
    return items


# ──────────────────────────────────────────────────────────────────────────────
# arXiv API  (official JSON/Atom API, no key, reliable from servers)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_arxiv(hours_lookback: int = 48, max_items: int = 15) -> List[Dict]:
    """Fetch recent AI/ML papers from arXiv (cs.AI + cs.LG + cs.CL)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)
    # Use Atom API
    url = (
        "https://export.arxiv.org/api/query"
        "?search_query=cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL"
        "&sortBy=submittedDate&sortOrder=descending"
        f"&max_results={max_items * 2}"
    )
    resp = _get(url)
    if resp is None:
        logger.warning("[arXiv] fetch failed")
        return []

    items = []
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        logger.warning(f"[arXiv] XML parse error: {e}")
        return []

    for entry in root.findall(f"{{{_ATOM}}}entry"):
        title_el = entry.find(f"{{{_ATOM}}}title")
        title = _strip_html(title_el.text or "").replace("\n", " ").strip() if title_el is not None else ""

        link_el = entry.find(f"{{{_ATOM}}}link[@rel='alternate']")
        if link_el is None:
            link_el = entry.find(f"{{{_ATOM}}}link")
        link = link_el.get("href", "") if link_el is not None else ""

        pub_str = ""
        pub_el = entry.find(f"{{{_ATOM}}}published")
        if pub_el is not None and pub_el.text:
            pub_str = pub_el.text
        pub_date = _parse_date(pub_str)

        if pub_date and pub_date < cutoff:
            continue

        summary_el = entry.find(f"{{{_ATOM}}}summary")
        summary = _strip_html(summary_el.text or "")[:400] if summary_el is not None else ""

        # Author(s)
        authors = [
            a.find(f"{{{_ATOM}}}name").text
            for a in entry.findall(f"{{{_ATOM}}}author")
            if a.find(f"{{{_ATOM}}}name") is not None
        ]
        author_str = ", ".join(authors[:3])
        if len(authors) > 3:
            author_str += " 等"

        items.append({
            "title": title,
            "url": link,
            "summary": f"作者：{author_str}。{summary}" if author_str else summary,
            "published": pub_date.isoformat() if pub_date else "",
            "source": "arXiv",
            "language": "en",
        })
        if len(items) >= max_items:
            break

    logger.info(f"  [arXiv] {len(items)} items")
    return items


# ──────────────────────────────────────────────────────────────────────────────
# Generic RSS / Atom feed parser
# ──────────────────────────────────────────────────────────────────────────────

def _find_text(elem: ET.Element, *tags: str) -> str:
    for tag in tags:
        child = elem.find(tag)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _parse_rss_channel(root: ET.Element, source: dict, cutoff: datetime, max_items: int) -> List[Dict]:
    items = []
    channel = root.find("channel") or root
    for entry in channel.findall("item"):
        title = _strip_html(_find_text(entry, "title"))
        link = _find_text(entry, "link")
        pub_str = _find_text(entry, "pubDate", "{http://purl.org/dc/elements/1.1/}date")
        pub_date = _parse_date(pub_str)
        if pub_date and pub_date < cutoff:
            continue
        raw_desc = (
            _find_text(entry, f"{{{_CONTENT}}}encoded")
            or _find_text(entry, "description")
        )
        summary = _strip_html(raw_desc)[:500]
        items.append({
            "title": title,
            "url": link,
            "summary": summary,
            "published": pub_date.isoformat() if pub_date else "",
            "source": source["name"],
            "language": source.get("language", "en"),
        })
        if len(items) >= max_items:
            break
    return items


def _parse_atom_feed(root: ET.Element, source: dict, cutoff: datetime, max_items: int) -> List[Dict]:
    items = []
    for entry in root.findall(f"{{{_ATOM}}}entry"):
        title_el = entry.find(f"{{{_ATOM}}}title")
        title = _strip_html(title_el.text or "") if title_el is not None else ""
        link_el = entry.find(f"{{{_ATOM}}}link[@rel='alternate']") or entry.find(f"{{{_ATOM}}}link")
        link = link_el.get("href", "") if link_el is not None else ""
        pub_str = (
            _find_text(entry, f"{{{_ATOM}}}published")
            or _find_text(entry, f"{{{_ATOM}}}updated")
        )
        pub_date = _parse_date(pub_str)
        if pub_date and pub_date < cutoff:
            continue
        summary_el = entry.find(f"{{{_ATOM}}}summary") or entry.find(f"{{{_ATOM}}}content")
        summary = _strip_html(summary_el.text or "" if summary_el is not None else "")[:500]
        items.append({
            "title": title,
            "url": link,
            "summary": summary,
            "published": pub_date.isoformat() if pub_date else "",
            "source": source["name"],
            "language": source.get("language", "en"),
        })
        if len(items) >= max_items:
            break
    return items


def fetch_feed(source: dict, hours_lookback: int = 24, max_items: int = 10) -> List[Dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)
    resp = _get(source["url"])
    if resp is None:
        return []
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        logger.warning(f"[{source['name']}] XML parse error: {e}")
        return []

    tag = root.tag
    if "rss" in tag.lower() or root.tag == "rss":
        return _parse_rss_channel(root, source, cutoff, max_items)
    elif _ATOM in tag:
        return _parse_atom_feed(root, source, cutoff, max_items)
    else:
        items = _parse_rss_channel(root, source, cutoff, max_items)
        return items or _parse_atom_feed(root, source, cutoff, max_items)


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────

def fetch_all(config_path: str = "config/sources.yaml") -> List[Dict]:
    """Fetch from all configured sources + HN + arXiv, deduplicated."""
    config = load_config(config_path)
    settings = config.get("settings", {})
    hours_lookback = settings.get("hours_lookback", 24)
    max_items = settings.get("max_items_per_source", 10)

    all_items: List[Dict] = []
    seen: set = set()

    def _add(items: List[Dict]) -> None:
        for item in items:
            key = re.sub(r"\s+", " ", item["title"].lower().strip())
            if key and key not in seen:
                seen.add(key)
                all_items.append(item)

    # 1. Hacker News (most reliable from CI servers)
    logger.info("Fetching [Hacker News Algolia] ...")
    _add(fetch_hackernews(hours_lookback=hours_lookback, max_items=20))

    # 2. arXiv papers (lookback 48h to catch more papers)
    logger.info("Fetching [arXiv] ...")
    _add(fetch_arxiv(hours_lookback=max(hours_lookback, 48), max_items=15))

    # 3. RSS / Atom feeds from config
    for source in config.get("sources", []):
        logger.info(f"Fetching [{source['name']}] ...")
        items = fetch_feed(source, hours_lookback, max_items)
        _add(items)
        logger.info(f"  -> {len(items)} items (total so far: {len(all_items)})")

    logger.info(f"Fetch complete. {len(all_items)} unique items.")
    return all_items
