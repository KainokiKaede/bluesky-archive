#!/usr/bin/env python3
"""Archive one public Bluesky author feed. Python 3.11+, standard library only."""

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API = "https://public.api.bsky.app/xrpc/"
POST_TYPE = "app.bsky.feed.post"
POST_URI = re.compile(r"^at://(did:[^/]+)/app\.bsky\.feed\.post/([A-Za-z0-9._~:-]+)$")


class ArchiveError(Exception):
    """An incomplete or unsafe update; do not save it."""


def timestamp(value):
    if not isinstance(value, str):
        raise ArchiveError("Missing or invalid post timestamp.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("timezone required")
        return result.astimezone(timezone.utc)
    except ValueError as exc:
        raise ArchiveError(f"Invalid timestamp: {value!r}") from exc


def retry_delay(headers, attempt):
    value = headers.get("Retry-After", "") if headers else ""
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            seconds = 2 ** (attempt + 1)
    return max(0, min(seconds, 60))


def api_get(method, params, *, opener=urlopen, sleep=time.sleep):
    request = Request(API + method + "?" + urlencode(params), headers={
        "Accept": "application/json",
        "User-Agent": "personal-bluesky-archive/1.0",
    })
    for attempt in range(4):
        headers = None
        try:
            with opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict) or "error" in payload:
                raise ArchiveError(f"{method}: invalid API response.")
            return payload
        except HTTPError as exc:
            exc.close()
            if exc.code != 429 and not 500 <= exc.code <= 599:
                raise ArchiveError(f"{method}: HTTP {exc.code}. Check your handle and public account access.") from exc
            headers = exc.headers
            reason = f"HTTP {exc.code}"
        except (URLError, TimeoutError, OSError, HTTPException, UnicodeDecodeError, json.JSONDecodeError) as exc:
            reason = str(exc)
        if attempt == 3:
            raise ArchiveError(f"{method}: failed after 4 attempts ({reason}).")
        delay = retry_delay(headers, attempt)
        print(f"Temporary API failure ({reason}); retrying in {delay:g}s.", file=sys.stderr)
        sleep(delay)
    raise AssertionError("unreachable")


def validate_post(post, did):
    if not isinstance(post, dict):
        raise ArchiveError("Invalid post object.")
    match = POST_URI.fullmatch(post.get("uri", "")) if isinstance(post.get("uri"), str) else None
    if not match or match[1] != did:
        raise ArchiveError("Post URI does not belong to this account.")
    record = post.get("record")
    if not isinstance(record, dict) or record.get("$type") != POST_TYPE or not isinstance(record.get("text"), str):
        raise ArchiveError("Post record is missing its type or text.")
    timestamp(record.get("createdAt"))
    if not isinstance(post.get("cid"), str) or not post["cid"]:
        raise ArchiveError("Post CID is missing.")
    if "reply" in record:
        reply = record["reply"]
        if not isinstance(reply, dict) or any(
            not isinstance(reply.get(key), dict) or not isinstance(reply[key].get("uri"), str)
            for key in ("root", "parent")
        ):
            raise ArchiveError("Invalid reply metadata.")
    return match


def load_archive(path):
    if not path.exists():
        return {"version": 1, "account": None, "updated_at": None, "posts": []}
    try:
        archive = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ArchiveError("Existing archive is unreadable. Restore it from Git history; it was not changed.") from exc
    if not isinstance(archive, dict) or archive.get("version") != 1 or not isinstance(archive.get("posts"), list):
        raise ArchiveError("Existing archive has an unsupported or invalid format.")
    account = archive.get("account")
    if account is None:
        if archive["posts"]:
            raise ArchiveError("Existing archive has posts but no account identity.")
    elif not isinstance(account, dict) or not isinstance(account.get("did"), str) or not account["did"].startswith("did:"):
        raise ArchiveError("Existing archive has an invalid account identity.")
    seen = set()
    for post in archive["posts"]:
        validate_post(post, account["did"])
        if post["uri"] in seen:
            raise ArchiveError("Existing archive contains duplicate URIs. Restore a valid version first.")
        seen.add(post["uri"])
    return archive


def collect(archive, handle, *, get=api_get, sleep=time.sleep):
    profile = get("app.bsky.actor.getProfile", {"actor": handle})
    did = profile.get("did")
    if not isinstance(did, str) or not did.startswith("did:") or not isinstance(profile.get("handle"), str):
        raise ArchiveError("API profile has no valid account identity.")
    if archive["account"] and archive["account"]["did"] != did:
        raise ArchiveError("This handle resolves to a different account. Use a separate repository for a different account.")
    merged = {post["uri"]: post for post in archive["posts"]}
    previous_count = len(merged)
    cursor = None
    seen_cursors = set()
    page_number = 0
    while True:
        params = {"actor": did, "limit": 100, "filter": "posts_with_replies", "includePins": "false"}
        if cursor:
            params["cursor"] = cursor
        page = get("app.bsky.feed.getAuthorFeed", params)
        if not isinstance(page.get("feed"), list):
            raise ArchiveError("API page is missing its feed; aborting the entire update.")
        for item in page["feed"]:
            if not isinstance(item, dict):
                raise ArchiveError("Invalid feed entry.")
            reason = item.get("reason")
            if isinstance(reason, dict) and reason.get("$type") == "app.bsky.feed.defs#reasonRepost":
                continue  # Includes reposts of the author's own posts.
            view = item.get("post")
            if not isinstance(view, dict) or not isinstance(view.get("author"), dict):
                raise ArchiveError("Feed entry has no post or author.")
            if view["author"].get("did") != did:
                continue  # Never archive someone else's posts.
            match = validate_post(view, did)
            saved = {
                "uri": view["uri"], "cid": view["cid"],
                "url": f"https://bsky.app/profile/{quote(did, safe=':')}/post/{quote(match[2], safe='')}",
                "record": view["record"],
            }
            # Keep both the original record (facets, blobs, replies, languages,
            # embeds) and the hydrated embed (image URLs, cards, quoted posts).
            if isinstance(view.get("embed"), dict):
                saved["embed"] = view["embed"]
            elif "embed" in merged.get(view["uri"], {}):
                saved["embed"] = merged[view["uri"]]["embed"]
            merged[view["uri"]] = saved
        page_number += 1
        print(f"Fetched page {page_number}; {len(merged)} unique archived posts.")
        cursor = page.get("cursor")
        if cursor is None or cursor == "":
            break
        if not isinstance(cursor, str) or cursor in seen_cursors:
            raise ArchiveError("API returned an invalid or repeated cursor; aborting the entire update.")
        seen_cursors.add(cursor)
        sleep(0.15)
    result = {
        "version": 1,
        "account": {key: profile[key] for key in ("did", "handle", "displayName", "description", "avatar") if key in profile},
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "posts": sorted(merged.values(), key=lambda post: (timestamp(post["record"]["createdAt"]), post["uri"]), reverse=True),
    }
    print(f"Complete: {len(merged) - previous_count} new posts; {len(merged)} total; {page_number} pages.")
    return result


def atomic_save(path, archive):
    payload = json.dumps(archive, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".archive-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def update(config_path, archive_path, *, dry_run=False, get=api_get, sleep=time.sleep):
    config = json.loads(config_path.read_text(encoding="utf-8"))
    handle = config.get("handle", "") if isinstance(config, dict) else ""
    if not isinstance(handle, str):
        raise ArchiveError("config.json: handle must be a string.")
    handle = handle.strip().removeprefix("@")
    if not handle or "YOUR_HANDLE" in handle or "/" in handle or any(c.isspace() for c in handle):
        raise ArchiveError("Edit config.json: replace YOUR_HANDLE.bsky.social with your Bluesky handle (no profile URL).")
    archive = collect(load_archive(archive_path), handle, get=get, sleep=sleep)
    if not dry_run:
        atomic_save(archive_path, archive)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--output", type=Path, default=ROOT / "site/data/archive.json")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and validate everything without saving.")
    args = parser.parse_args()
    try:
        update(args.config, args.output, dry_run=args.dry_run)
    except (ArchiveError, OSError, ValueError) as exc:
        print(f"Update failed: {exc}\nThe previous archive was not replaced.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
