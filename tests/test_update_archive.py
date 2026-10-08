"""Offline tests: no credentials, live API, or third-party packages required."""
import copy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from scripts import update_archive as updater

DID = "did:plc:archiveowner"
PROFILE = {"did": DID, "handle": "test.bsky.social", "displayName": "日本語テスト"}


def entry(key, text="検索テスト ☀️", created="2026-10-03T15:01:00Z", *, author=DID, reply=False, repost=False):
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": created, "langs": ["ja"]}
    if reply:
        record["reply"] = {key: {"uri": f"at://{DID}/app.bsky.feed.post/parent", "cid": "parent-cid"} for key in ("root", "parent")}
    result = {"post": {"uri": f"at://{author}/app.bsky.feed.post/{key}", "cid": "cid-" + key, "author": {"did": author}, "record": record}}
    if repost:
        result["reason"] = {"$type": "app.bsky.feed.defs#reasonRepost"}
    return result


class FakeAPI:
    def __init__(self, pages, profile=None):
        self.pages = iter(pages)
        self.profile = profile or PROFILE
        self.calls = []

    def __call__(self, method, params):
        self.calls.append((method, params.copy()))
        if method.endswith("getProfile"):
            return self.profile
        page = next(self.pages)
        if isinstance(page, Exception):
            raise page
        return copy.deepcopy(page)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = Path(self.directory.name) / "config.json"
        self.config.write_text(json.dumps({"handle": "test.bsky.social"}), encoding="utf-8")
        self.output = Path(self.directory.name) / "archive.json"

    def run_update(self, pages, **kwargs):
        return updater.update(self.config, self.output, get=FakeAPI(pages), sleep=lambda _: None, **kwargs)

    def seed(self):
        return self.run_update([{"feed": [entry("old", created="2025-01-01T00:00:00Z")]}])

    def test_paginated_import_unicode_replies_duplicates_and_reposts(self):
        first = entry("first", reply=True)
        first["post"]["embed"] = {"$type": "app.bsky.embed.images#view", "images": [{"alt": "日本語の画像", "fullsize": "https://example.com/image.jpg"}]}
        first["post"]["record"]["facets"] = [{"index": {"byteStart": 0, "byteEnd": 15}, "features": [{"$type": "app.bsky.richtext.facet#link", "uri": "https://example.com"}]}]
        first["post"]["record"]["embed"] = {"$type": "app.bsky.embed.images", "images": [{"alt": "日本語の画像", "image": {"ref": {"$link": "blob-cid"}}}]}
        api = FakeAPI([
            {"feed": [first, entry("repost", repost=True), entry("foreign", author="did:plc:other")], "cursor": "page2"},
            {"feed": [], "cursor": "page3"},
            {"feed": [first, entry("old", created="2020-01-01T00:00:00Z")]},
        ])
        data = updater.update(self.config, self.output, get=api, sleep=lambda _: None)
        self.assertEqual(len(data["posts"]), 2)
        self.assertIn("reply", data["posts"][0]["record"])
        self.assertEqual(data["posts"][0]["record"], first["post"]["record"])
        self.assertEqual(data["posts"][0]["embed"], first["post"]["embed"])
        self.assertIn("検索テスト", self.output.read_text(encoding="utf-8"))
        self.assertIn(f"/profile/{DID}/post/first", data["posts"][0]["url"])
        self.assertEqual(api.calls[-1][1]["cursor"], "page3")
        self.assertEqual(api.calls[1][1]["filter"], "posts_with_replies")
        self.assertEqual(api.calls[1][1]["includePins"], "false")

    def test_updates_are_idempotent_and_keep_unavailable_posts(self):
        self.seed()
        pages = [{"feed": [entry("new")] }]
        self.run_update(pages)
        data = self.run_update(pages)
        self.assertEqual([p["uri"].split("/")[-1] for p in data["posts"]], ["new", "old"])
        self.run_update([{"feed": []}])
        self.assertEqual(len(updater.load_archive(self.output)["posts"]), 2)

    def test_failure_on_later_page_preserves_exact_original_bytes(self):
        self.seed()
        before = self.output.read_bytes()
        with self.assertRaises(updater.ArchiveError):
            self.run_update([{"feed": [entry("new")], "cursor": "more"}, updater.ArchiveError("API failed")])
        self.assertEqual(self.output.read_bytes(), before)

    def test_invalid_pages_records_and_cursor_loops_never_replace_archive(self):
        self.seed()
        before = self.output.read_bytes()
        invalid = entry("invalid"); invalid["post"]["record"]["createdAt"] = "not a date"
        cases = [
            [{"feed": [], "cursor": "same"}, {"feed": [], "cursor": "same"}],
            [{"unexpected": []}], [{"feed": [invalid]}],
            [{"feed": [], "cursor": 123}], [{"feed": [None]}],
        ]
        for pages in cases:
            with self.subTest(pages=pages), self.assertRaises(updater.ArchiveError):
                self.run_update(pages)
            self.assertEqual(self.output.read_bytes(), before)

    def test_identity_mismatch_and_corruption_preserve_existing_file(self):
        self.seed(); before = self.output.read_bytes()
        other = FakeAPI([], {"did": "did:plc:other", "handle": "other.bsky.social"})
        with self.assertRaises(updater.ArchiveError):
            updater.update(self.config, self.output, get=other)
        self.assertEqual(self.output.read_bytes(), before)
        for bad in (b"broken JSON", b'{"version": 2, "posts": []}'):
            self.output.write_bytes(bad)
            with self.assertRaises(updater.ArchiveError):
                self.run_update([{"feed": []}])
            self.assertEqual(self.output.read_bytes(), bad)

    def test_handle_change_same_did_is_allowed(self):
        self.seed()
        data = updater.update(self.config, self.output, get=FakeAPI([{"feed": []}], {**PROFILE, "handle": "new.example.com"}))
        self.assertEqual(data["account"]["handle"], "new.example.com")

    def test_dry_run_and_failed_atomic_replace(self):
        self.seed(); before = self.output.read_bytes()
        self.run_update([{"feed": [entry("new")]}], dry_run=True)
        self.assertEqual(self.output.read_bytes(), before)
        with patch.object(updater.os, "replace", side_effect=OSError("disk error")), self.assertRaises(OSError):
            self.run_update([{"feed": [entry("new")]}])
        self.assertEqual(self.output.read_bytes(), before)
        self.assertEqual(list(self.output.parent.glob(".archive-*.tmp")), [])

    def test_first_import_failure_leaves_no_partial_archive(self):
        with self.assertRaises(updater.ArchiveError):
            self.run_update([{"feed": [entry("first")], "cursor": "more"}, updater.ArchiveError("failure")])
        self.assertFalse(self.output.exists())


class HTTPTests(unittest.TestCase):
    def test_temporary_errors_and_rate_limit_retry(self):
        for error in (HTTPError("url", 503, "unavailable", {}, None), HTTPError("url", 429, "limited", {"Retry-After": "7"}, None), URLError("offline"), TimeoutError("timeout")):
            with self.subTest(error=error):
                delays = []
                with patch.object(updater, "urlopen") as unused:
                    # Pass the transport explicitly; there are no real requests.
                    responses = iter([error, io.BytesIO('{"text":"日本語"}'.encode())])
                    def opener(*args, **kwargs):
                        result = next(responses)
                        if isinstance(result, Exception): raise result
                        return result
                    self.assertEqual(updater.api_get("test", {}, opener=opener, sleep=delays.append)["text"], "日本語")
                    self.assertEqual(len(delays), 1)
                    unused.assert_not_called()
                if getattr(error, "code", None) == 429:
                    self.assertEqual(delays, [7])

    def test_retry_exhaustion_and_permanent_failure(self):
        for code, attempts in ((503, 4), (400, 1)):
            calls = []
            def opener(*args, **kwargs):
                calls.append(1)
                raise HTTPError("url", code, "failure", {}, None)
            with self.assertRaises(updater.ArchiveError):
                updater.api_get("test", {}, opener=opener, sleep=lambda _: None)
            self.assertEqual(len(calls), attempts)

    def test_truncated_json_retries(self):
        replies = iter([b'{"bad":', b'{"feed":[]}'])
        self.assertEqual(updater.api_get("test", {}, opener=lambda *a, **kw: io.BytesIO(next(replies)), sleep=lambda _: None), {"feed": []})

    def test_retry_after_http_date_and_timestamp_offsets(self):
        self.assertEqual(updater.retry_delay({"Retry-After": "Wed, 01 Jan 2020 00:00:00 GMT"}, 0), 0)
        self.assertEqual(updater.retry_delay({"Retry-After": "99999"}, 0), 60)
        self.assertEqual(updater.timestamp("2026-10-04T00:00:00+09:00"), datetime(2026, 10, 3, 15, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
