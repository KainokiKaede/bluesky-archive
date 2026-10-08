import test from "node:test";
import assert from "node:assert/strict";
import { jstDay, jstTime, selectPosts, highlightParts, safeURL, route, originalURL } from "../site/search.mjs";

const post = (key, text, createdAt, reply = false) => ({
  uri: `at://did:plc:test/app.bsky.feed.post/${key}`,
  record: { text, createdAt, ...(reply ? { reply: { parent: {} } } : {}) },
});
const posts = [
  post("a", "今日は検索テストです。🦋", "2026-09-30T14:59:00Z"),
  post("b", "返信の検索テストも見つかる", "2026-09-30T15:00:00Z", true),
  post("c", "検索のテスト", "2026-10-02T00:00:00Z"),
];

test("Japanese substring search returns every exact match, including replies", () => {
  assert.deepEqual(selectPosts(posts, { q: "検索テスト" }).map(p => p.uri.split("/").at(-1)), ["b", "a"]);
  assert.equal(selectPosts(posts, { q: "🦋" }).length, 1);
  assert.equal(selectPosts(posts, { q: "不存在" }).length, 0);
  assert.equal(selectPosts(posts, { q: "" }).length, 3);
});
test("search covers the entire collection beyond the first displayed page", () => {
  const many = Array.from({ length: 120 }, (_, i) => post(String(i), i % 2 ? "検索テスト" : "別の投稿", "2026-10-01T00:00:00Z"));
  assert.equal(selectPosts(many, { q: "検索テスト" }).length, 60);
});
test("JST date boundaries, month filters, replies, ordering, and permalinks", () => {
  assert.equal(jstDay(posts[0].record.createdAt), "2026-09-30");
  assert.equal(jstDay(posts[1].record.createdAt), "2026-10-01");
  assert.equal(jstTime(posts[1].record.createdAt), "00:00");
  assert.equal(selectPosts(posts, { month: "2026-10" }).length, 2);
  assert.equal(selectPosts(posts, { day: "2026-10-01" }).length, 1);
  assert.equal(selectPosts(posts, { kind: "replies" }).length, 1);
  assert.equal(selectPosts(posts, { kind: "posts" }).length, 2);
  assert.equal(selectPosts(posts, { post: "a" })[0], posts[0]);
  assert.equal(selectPosts(posts, { order: "oldest" })[0], posts[0]);
});
test("highlights preserve original Unicode, repeated matches and literal punctuation", () => {
  for (const [text, q, count] of [["🦋検索テスト / 検索テスト", "検索テスト", 2], ["<script>.*</script>", ".*", 1], ["😀😀", "😀", 2], ["a+b a+b", "a+b", 2], ["日本語", "", 0]]) {
    const parts = highlightParts(text, q);
    assert.equal(parts.map(p => p.text).join(""), text);
    assert.equal(parts.filter(p => p.match).length, count);
  }
  assert.equal(selectPosts([post("x", "Test", "2026-01-01T00:00:00Z")], { q: "test" }).length, 0);
});
test("unsafe URLs are rejected and routes round-trip Japanese text", () => {
  for (const url of ["javascript:alert(1)", "data:text/html,bad", "/relative", undefined, "file:///tmp/test"]) assert.equal(safeURL(url), null);
  assert.equal(safeURL("https://example.com"), "https://example.com/");
  assert.equal(new URLSearchParams(route({ q: "検索テスト & #" }).slice(1)).get("q"), "検索テスト & #");
  assert.equal(originalURL("at://did:plc:test/app.bsky.feed.post/123"), "https://bsky.app/profile/did%3Aplc%3Atest/post/123");
  assert.equal(originalURL("javascript:alert(1)"), null);
});
