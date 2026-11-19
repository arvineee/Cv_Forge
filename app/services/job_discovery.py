"""RSS/Atom job-feed ingestion with explicit source approval.

Approved sources come from two places:

* Admin -> Job sources (the ``job_feed_sources`` table). Adding an active
  source approves its hostname automatically. This is the day-to-day way.
* The legacy JOB_FEEDS_JSON / JOB_FEED_ALLOWED_DOMAINS environment variables,
  still honoured so existing deployments keep working.

Only HTTPS feeds on an approved host are fetched. The importer does not scrape
job-board HTML, follow redirects, or accept non-public IP addresses.
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

from app.models import db, JobOpportunity, JobFeedSource

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


def ensure_schema():
    """Create the job_feed_sources table if a deployment predates it.

    ``create(checkfirst=True)`` only ever creates a missing table, so this is
    safe to call on every request and removes the manual-migration step.
    """
    try:
        JobFeedSource.__table__.create(bind=db.engine, checkfirst=True)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Could not ensure job_feed_sources table: %s", exc)


def normalize_feed_url(url):
    """Return a cleaned HTTPS URL, or raise ValueError with a readable reason."""
    url = (url or "").strip()
    if not url:
        raise ValueError("Enter the feed URL.")
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Only secure https:// feed URLs are accepted.")
    if not parsed.hostname or "." not in parsed.hostname:
        raise ValueError("That does not look like a valid web address.")
    if parsed.username or parsed.password:
        raise ValueError("Remove the username/password from the URL.")
    return url[:1000]


def _env_feed_config():
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


def _load_feed_config():
    """Merged list of (feed dicts, allowed hosts) from the database and .env.

    Each feed dict carries an optional ``source_id`` so the importer can record
    the outcome on the admin page. Database sources win over .env duplicates.
    """
    ensure_schema()
    env_feeds, allowed = _env_feed_config()
    feeds, seen = [], set()
    for src in JobFeedSource.query.filter_by(is_active=True).order_by(JobFeedSource.id).all():
        feeds.append({"source_id": src.id, "name": src.name, "url": src.url, "country": src.country,
                      "location": src.location, "employment_type": src.employment_type})
        seen.add(src.url)
        if src.host:
            allowed.add(src.host)
    for item in env_feeds:
        if str(item.get("url") or "").strip() not in seen:
            feeds.append(item)
    return feeds, allowed


def import_env_sources():
    """One-click migration of .env feeds into the database. Returns count added."""
    ensure_schema()
    env_feeds, _ = _env_feed_config()
    added = 0
    for item in env_feeds:
        try:
            url = normalize_feed_url(str(item.get("url") or ""))
        except ValueError:
            continue
        if JobFeedSource.query.filter_by(url=url).first():
            continue
        db.session.add(JobFeedSource(
            name=str(item.get("name") or urlparse(url).hostname)[:120], url=url,
            country=str(item.get("country") or "Kenya")[:80],
            location=(str(item.get("location") or "")[:180] or None),
            employment_type=(str(item.get("employment_type") or "")[:60] or None)))
        added += 1
    db.session.commit()
    return added


def _fetch_feed_entries(feed_url):
    """Download and parse one feed. Raises ValueError with a readable reason."""
    response = requests.get(feed_url, timeout=(5, 15), headers={"User-Agent": "CVForgeJobDiscovery/1.0 (+https://cvforge.site)"}, allow_redirects=False, stream=True)
    if response.status_code in (301, 302, 303, 307, 308):
        raise ValueError("The feed redirects elsewhere. Paste the final feed address instead.")
    if response.status_code != 200:
        raise ValueError(f"Feed returned HTTP {response.status_code}")
    chunks, total = [], 0
    for chunk in response.iter_content(16384):
        total += len(chunk)
        if total > 2_000_000:
            raise ValueError("Feed exceeds 2 MB limit")
        chunks.append(chunk)
    try:
        root = ET.fromstring(b"".join(chunks))
    except ET.ParseError:
        raise ValueError("That address did not return a valid RSS/Atom feed.")
    return [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() in ("item", "entry")]


def check_feed(url):
    """Dry-run a feed for the admin page: nothing is saved."""
    try:
        url = normalize_feed_url(url)
    except ValueError as exc:
        return {"ok": False, "message": str(exc), "count": 0, "samples": []}
    host = (urlparse(url).hostname or "").lower()
    # The host is being approved by the admin, so only the network checks apply.
    if not _allowed_feed_url(url, {host}):
        return {"ok": False, "count": 0, "samples": [],
                "message": "The address could not be reached safely (it must be public HTTPS)."}
    try:
        entries = _fetch_feed_entries(url)
    except (ValueError, requests.RequestException) as exc:
        return {"ok": False, "message": str(exc) if isinstance(exc, ValueError) else "Could not connect to that address.", "count": 0, "samples": []}
    samples = [t for t in (_tag_text(e, ["title"]) for e in entries[:3]) if t]
    if not entries:
        return {"ok": False, "message": "The feed loaded but contains no job entries.", "count": 0, "samples": []}
    return {"ok": True, "message": f"Feed looks good: {len(entries)} listings found.", "count": len(entries), "samples": samples}


def sync_job_feeds():
    """Fetch approved feeds and upsert listings; returns aggregate counts."""
    feeds, allowed_domains = _load_feed_config()
    result = {"feeds": len(feeds), "fetched": 0, "created": 0, "updated": 0, "deactivated": 0, "skipped": 0, "errors": 0}
    if not feeds:
        return result
    if not allowed_domains:
        log.error("Job feed sync disabled: no approved feed domains")
        result["errors"] = len(feeds)
        return result

    def record(feed, status, message, count=0):
        source_id = feed.get("source_id")
        if not source_id:
            return
        src = db.session.get(JobFeedSource, source_id)
        if src:
            src.last_synced_at = datetime.utcnow()
            src.last_status = status
            src.last_message = (message or "")[:300]
            src.last_entry_count = count
            db.session.commit()

    for feed in feeds:
        feed_url = str(feed.get("url") or "").strip()
        source_name = str(feed.get("name") or "Verified source").strip()[:120]
        if not _allowed_feed_url(feed_url, allowed_domains):
            log.warning("Skipping job feed outside HTTPS allow-list: %s", source_name)
            result["skipped"] += 1
            record(feed, "blocked", "Blocked: address is not public HTTPS or its host is not approved.")
            continue
        try:
            sync_started_at = datetime.utcnow()
            entries = _fetch_feed_entries(feed_url)
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
            record(feed, "ok", f"Synced {len(entries)} listings.", len(entries))
        except Exception as exc:
            db.session.rollback()
            log.warning("Job feed sync failed for %s: %s", source_name, exc)
            result["errors"] += 1
            record(feed, "error", str(exc) if isinstance(exc, ValueError) else "Could not fetch this feed.")
    return result
