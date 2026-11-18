"""RSS/Atom job-feed ingestion with explicit source allow-listing.

Only operator-configured HTTPS feeds on JOB_FEED_ALLOWED_DOMAINS are fetched.
The importer does not scrape job-board HTML or follow redirects.
"""
import hashlib
import html
import ipaddress
import json
import logging
import socket
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests
from flask import current_app

from app.models import db, JobOpportunity

log = logging.getLogger(__name__)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        value = data.strip()
        if value:
            self.parts.append(value)


def _plain_text(value, limit=12000):
    parser = _TextExtractor()
    try:
        parser.feed(value or "")
        text = " ".join(parser.parts)
    except Exception:
        text = html.unescape(value or "")
    return " ".join(text.split())[:limit]


def _tag_text(element, names):
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return found.text.strip()
        # Namespace-agnostic fallback (RSS/Atom/DC fields).
        for child in element.iter():
            local = child.tag.rsplit("}", 1)[-1].lower()
            full = child.tag.lower()
            if (local == name.lower() or full.endswith("}" + name.lower()) or full.endswith(":" + name.lower())) and child.text:
                return child.text.strip()
    return ""


def _entry_link(entry):
    for child in entry:
        if child.tag.rsplit("}", 1)[-1].lower() == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text:
                return child.text.strip()
    return ""


def _parse_date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _allowed_feed_url(url, allowed_domains):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        return False
    if not any(host == domain or host.endswith("." + domain) for domain in allowed_domains):
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            return False
    except (OSError, ValueError):
        return False
    return True


def _load_feed_config():
    raw = current_app.config.get("JOB_FEEDS_JSON", "")
    allowed_raw = current_app.config.get("JOB_FEED_ALLOWED_DOMAINS", "")
    try:
        feeds = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        log.error("JOB_FEEDS_JSON is invalid JSON")
        return [], set()
    allowed = {part.strip().lower().lstrip(".") for part in allowed_raw.split(",") if part.strip()}
    if not isinstance(feeds, list):
        return [], allowed
    return [item for item in feeds if isinstance(item, dict)], allowed


def sync_job_feeds():
    """Fetch configured feeds and upsert listings; returns aggregate counts."""
    feeds, allowed_domains = _load_feed_config()
    result = {"feeds": len(feeds), "fetched": 0, "created": 0, "updated": 0, "deactivated": 0, "skipped": 0, "errors": 0}
    if not feeds:
        return result
    if not allowed_domains:
        log.error("Job feed sync disabled: JOB_FEED_ALLOWED_DOMAINS is empty")
        result["errors"] = len(feeds)
        return result

    for feed in feeds:
        feed_url = str(feed.get("url") or "").strip()
        source_name = str(feed.get("name") or "Verified source").strip()[:120]
        if not _allowed_feed_url(feed_url, allowed_domains):
            log.warning("Skipping job feed outside HTTPS allow-list: %s", source_name)
            result["skipped"] += 1
            continue
        try:
            sync_started_at = datetime.utcnow()
            response = requests.get(feed_url, timeout=(5, 15), headers={"User-Agent": "CVForgeJobDiscovery/1.0 (+https://cvforge.site)"}, allow_redirects=False, stream=True)
            if response.status_code != 200:
                raise ValueError(f"Feed returned HTTP {response.status_code}")
            chunks, total = [], 0
            for chunk in response.iter_content(16384):
                total += len(chunk)
                if total > 2_000_000:
                    raise ValueError("Feed exceeds 2 MB limit")
                chunks.append(chunk)
            root = ET.fromstring(b"".join(chunks))
            entries = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() in ("item", "entry")]
            result["fetched"] += len(entries)
            for entry in entries[:200]:
                title = _tag_text(entry, ["title"])
                link = _entry_link(entry)
                description = _tag_text(entry, ["description", "summary", "content:encoded", "content"])
                description = _plain_text(description)
                if not title or not link or not description:
                    result["skipped"] += 1
                    continue
                link_parsed = urlparse(link)
                if link_parsed.scheme not in ("https", "http") or not link_parsed.netloc:
                    result["skipped"] += 1
                    continue
                external_id = _tag_text(entry, ["guid", "id"]) or link
                digest = hashlib.sha256((source_name + "|" + external_id).encode("utf-8")).hexdigest()
                item = JobOpportunity.query.filter_by(external_key=digest).first()
                author = _tag_text(entry, ["name", "creator", "author"])
                published = _parse_date(_tag_text(entry, ["published", "pubDate", "updated", "date"]))
                values = dict(
                    title=title[:255], company_name=author[:180] or "See original listing",
                    description=description, url=link[:1000], source_name=source_name,
                    source_url=feed_url[:1000], country=str(feed.get("country") or "International")[:80],
                    location=str(feed.get("location") or "")[:180] or None,
                    employment_type=str(feed.get("employment_type") or "")[:60] or None,
                    published_at=published, is_active=True,
                    last_seen_at=datetime.utcnow(),
                )
                if item:
                    for key, value in values.items():
                        setattr(item, key, value)
                    result["updated"] += 1
                else:
                    db.session.add(JobOpportunity(external_key=digest, **values))
                    result["created"] += 1
            # A successfully fetched feed is the source of truth for its current
            # active set. Deactivate listings no longer present in the feed.
            stale_count = JobOpportunity.query.filter_by(source_url=feed_url, is_active=True).filter(
                JobOpportunity.last_seen_at < sync_started_at
            ).update({JobOpportunity.is_active: False}, synchronize_session=False)
            result["deactivated"] += stale_count
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            log.warning("Job feed sync failed for %s: %s", source_name, exc)
            result["errors"] += 1
    return result
