import re
import logging
import feedparser
import yaml
from datetime import datetime, timezone, timedelta
from typing import List, Dict

logger = logging.getLogger(__name__)


def load_config(config_path: str = "config/sources.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def fetch_feed(source: dict, hours_lookback: int = 24, max_items: int = 10) -> List[Dict]:
    """Fetch recent news items from a single RSS feed."""
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)

    try:
        feed = feedparser.parse(source["url"])
        for entry in feed.entries:
            # Parse publish date
            pub_date = None
            for attr in ("published_parsed", "updated_parsed"):
                t = getattr(entry, attr, None)
                if t:
                    pub_date = datetime(*t[:6], tzinfo=timezone.utc)
                    break

            if pub_date and pub_date < cutoff:
                continue

            summary = _strip_html(
                getattr(entry, "summary", None) or getattr(entry, "description", None) or ""
            )[:500]

            items.append({
                "title": _strip_html(getattr(entry, "title", "")),
                "url": getattr(entry, "link", ""),
                "summary": summary,
                "published": pub_date.isoformat() if pub_date else "",
                "source": source["name"],
                "language": source.get("language", "en"),
            })

            if len(items) >= max_items:
                break

    except Exception as e:
        logger.warning(f"Failed to fetch [{source['name']}]: {e}")

    return items


def fetch_all(config_path: str = "config/sources.yaml") -> List[Dict]:
    """Fetch news from all configured sources and return deduplicated list."""
    config = load_config(config_path)
    settings = config.get("settings", {})
    hours_lookback = settings.get("hours_lookback", 24)
    max_items = settings.get("max_items_per_source", 10)

    all_items: List[Dict] = []
    seen_titles: set = set()

    for source in config.get("sources", []):
        logger.info(f"Fetching [{source['name']}] ...")
        items = fetch_feed(source, hours_lookback, max_items)
        # Deduplicate by normalised title
        for item in items:
            key = re.sub(r"\s+", " ", item["title"].lower().strip())
            if key not in seen_titles:
                seen_titles.add(key)
                all_items.append(item)
        logger.info(f"  -> {len(items)} items (total so far: {len(all_items)})")

    logger.info(f"Fetch complete. {len(all_items)} unique items.")
    return all_items
