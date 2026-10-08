// Shared by the browser and the dependency-free Node tests.
const dayFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit",
});
const timeFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Tokyo", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

export function jstDay(value) {
  const parts = Object.fromEntries(dayFormatter.formatToParts(new Date(value)).map(p => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function jstTime(value) { return timeFormatter.format(new Date(value)); }
export function postKey(post) { return post.uri.slice(post.uri.lastIndexOf("/") + 1); }
export function route(values = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value) params.set(key, value);
  return "#" + params.toString();
}

export function selectPosts(posts, { q = "", month = "", day = "", post = "", kind = "all", order = "newest" } = {}) {
  // Literal substring matching: no tokenizer, word boundaries, regex, or network.
  // Case-sensitive by design, so matching and highlighting use identical offsets.
  const selected = posts.filter(p => {
    const date = jstDay(p.record.createdAt);
    return (!q || p.record.text.includes(q)) && (!month || date.startsWith(month)) &&
      (!day || date === day) && (!post || postKey(p) === post) &&
      (kind === "all" || (kind === "replies" ? Boolean(p.record.reply) : !p.record.reply));
  });
  selected.sort((a, b) => new Date(b.record.createdAt) - new Date(a.record.createdAt) || b.uri.localeCompare(a.uri));
  return order === "oldest" ? selected.reverse() : selected;
}

export function highlightParts(text, query) {
  if (!query) return [{ text, match: false }];
  const parts = [];
  let start = 0, index;
  while ((index = text.indexOf(query, start)) !== -1) {
    if (index > start) parts.push({ text: text.slice(start, index), match: false });
    parts.push({ text: text.slice(index, index + query.length), match: true });
    start = index + query.length;
  }
  if (start < text.length) parts.push({ text: text.slice(start), match: false });
  return parts;
}

export function safeURL(value) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}

export function originalURL(uri) {
  const match = /^at:\/\/(did:[^/]+)\/app\.bsky\.feed\.post\/([A-Za-z0-9._~:-]+)$/.exec(uri);
  return match ? `https://bsky.app/profile/${encodeURIComponent(match[1])}/post/${encodeURIComponent(match[2])}` : null;
}
