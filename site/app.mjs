import { jstDay, jstTime, postKey, route, selectPosts, highlightParts, safeURL, originalURL } from "./search.mjs";

const $ = id => document.getElementById(id);
const PAGE_SIZE = 50;
let archive, selected = [], shown = 0, query = "", lastDay = "";

function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}
function link(label, href, className = "") {
  const node = element("a", className, label);
  if (href?.startsWith("#")) node.href = href;
  else if (safeURL(href)) { node.href = safeURL(href); node.rel = "noopener noreferrer"; }
  return node;
}
function state() {
  const params = Object.fromEntries(new URLSearchParams(location.hash.slice(1)));
  return { ...params, kind: ["posts", "replies"].includes(params.kind) ? params.kind : "all", order: params.order === "oldest" ? "oldest" : "newest" };
}
function setRoute(values) {
  const next = route(values);
  if (location.hash === next || (!location.hash && next === "#")) render();
  else location.hash = next;
}
function highlighted(text) {
  const node = element("p", "post-text");
  for (const part of highlightParts(text, query)) {
    node.append(part.match ? element("mark", "", part.text) : document.createTextNode(part.text));
  }
  return node;
}
function embeds(container, embed, postURL, depth = 0) {
  if (!embed || depth > 2) return;
  if (Array.isArray(embed.images)) {
    const grid = element("div", "images");
    for (const item of embed.images) {
      const source = safeURL(item.thumb) || safeURL(item.fullsize);
      if (!source) continue;
      const a = link("", safeURL(item.fullsize) || source);
      const img = element("img");
      img.src = source; img.alt = item.alt || ""; img.loading = "lazy"; img.decoding = "async";
      img.addEventListener("error", () => { a.replaceChildren(element("span", "media-note", "Image unavailable · open original image")); });
      a.append(img); grid.append(a);
    }
    container.append(grid);
  }
  if (embed.external && safeURL(embed.external.uri)) {
    const external = embed.external;
    const card = link("", external.uri, "card");
    card.append(element("strong", "", external.title || external.uri));
    if (external.description) card.append(element("p", "", external.description));
    card.append(element("small", "", new URL(external.uri).hostname));
    container.append(card);
  }
  if (embed.record) {
    // recordWithMedia wraps a record view one level deeper.
    const record = embed.record.record || embed.record;
    if (record.value && typeof record.value.text === "string") {
      const card = element("div", "card quote");
      card.append(element("strong", "", record.author?.displayName || record.author?.handle || "Quoted post"));
      card.append(element("p", "", record.value.text));
      if (originalURL(record.uri)) card.append(link("View quoted post ↗", originalURL(record.uri)));
      container.append(card);
    } else if (record.uri) container.append(link("View quoted post ↗", originalURL(record.uri), "media-note"));
  }
  if (embed.media) embeds(container, embed.media, postURL, depth + 1);
  if (embed.$type === "app.bsky.embed.video#view") container.append(link("Watch video on Bluesky ↗", postURL, "media-note"));
}
function postCard(post) {
  const card = element("article", "post");
  card.id = `post-${postKey(post)}`;
  const record = post.record;
  const meta = element("div", "post-meta");
  const time = element("time", "", `${jstDay(record.createdAt)} · ${jstTime(record.createdAt)} JST`);
  time.dateTime = record.createdAt;
  meta.append(time);
  if (record.reply) meta.append(element("span", "badge", "↳ Reply"));
  card.append(meta, highlighted(record.text));
  embeds(card, post.embed, post.url);
  const links = element("div", "post-links");
  links.append(link("Permalink", route({ post: postKey(post) })), link("View on Bluesky ↗", post.url));
  if (record.reply?.parent?.uri) links.append(link("Replying to ↗", originalURL(record.reply.parent.uri)));
  // Rich-text facets use UTF-8 byte offsets; preserve them in JSON and expose
  // their destinations separately so Japanese/emoji text is never sliced wrong.
  const destinations = new Set();
  for (const facet of record.facets || []) for (const feature of facet.features || []) {
    if (feature.$type === "app.bsky.richtext.facet#link" && safeURL(feature.uri)) destinations.add(feature.uri);
  }
  for (const uri of destinations) links.append(link(new URL(uri).hostname + " ↗", uri));
  card.append(links);
  return card;
}
function appendPage() {
  const end = Math.min(shown + PAGE_SIZE, selected.length);
  const fragment = document.createDocumentFragment();
  for (const post of selected.slice(shown, end)) {
    const day = jstDay(post.record.createdAt);
    if (day !== lastDay) {
      const heading = element("h3", "day-heading");
      heading.append(link(day, route({ day })));
      fragment.append(heading); lastDay = day;
    }
    fragment.append(postCard(post));
  }
  $("posts").append(fragment); shown = end;
  $("more").hidden = shown >= selected.length;
  $("more").textContent = `Show more posts (${selected.length - shown} remaining)`;
  $("status").textContent = `${selected.length.toLocaleString()} ${query ? "matching posts" : "posts"} · ${shown.toLocaleString()} shown · Japan Standard Time`;
}
function navigation(current) {
  const months = new Map(), days = new Map();
  for (const post of archive.posts) {
    const day = jstDay(post.record.createdAt), month = day.slice(0, 7);
    months.set(month, (months.get(month) || 0) + 1);
    days.set(day, (days.get(day) || 0) + 1);
  }
  const activeMonth = current.day?.slice(0, 7) || current.month;
  $("months").replaceChildren();
  for (const [month, count] of [...months].sort((a, b) => b[0].localeCompare(a[0]))) {
    const a = link(month, route({ month }), "month");
    a.append(element("span", "count", count.toLocaleString()));
    if (activeMonth === month) a.setAttribute("aria-current", "page");
    $("months").append(a);
  }
  if (!months.size) $("months").append(element("p", "muted", "No archived months yet."));
  $("days").replaceChildren(); $("days").hidden = !activeMonth;
  if (activeMonth) {
    $("days").append(link("Whole month", route({ month: activeMonth })));
    for (const [day, count] of [...days].sort()) if (day.startsWith(activeMonth)) {
      const a = link(day.slice(-2), route({ day }));
      a.title = `${day}: ${count} posts`; a.setAttribute("aria-label", a.title);
      if (day === current.day) a.setAttribute("aria-current", "date");
      $("days").append(a);
    }
  }
}
function render() {
  if (!archive) return;
  const current = state(); query = current.q || "";
  $("query").value = query; $("kind").value = current.kind; $("order").value = current.order;
  $("view-label").textContent = query ? "SEARCH RESULTS" : "THE TIMELINE";
  $("heading").textContent = current.post ? "Archived post" : query ? `“${query}”` : current.day || current.month || "All posts";
  navigation(current);
  selected = selectPosts(archive.posts, current); shown = 0; lastDay = "";
  $("posts").replaceChildren(); appendPage();
  if (!selected.length) {
    const message = !archive.account ? "Your archive is ready. Set your handle in config.json and run the GitHub Actions workflow to import your posts." : !archive.posts.length ? "The import completed, but no public posts were available for this account." : "No posts found. Try a shorter exact phrase, or choose All posts to reset your filters.";
    $("posts").append(element("p", "notice", message));
  }
}

$("search-form").addEventListener("submit", event => {
  event.preventDefault();
  // A new search always covers the entire archive, not just the visible month.
  setRoute({ q: $("query").value, order: $("order").value });
});
for (const key of ["kind", "order"]) $(key).addEventListener("change", () => setRoute({ ...state(), [key]: $(key).value }));
$("more").addEventListener("click", appendPage);
document.querySelector(".skip").addEventListener("click", event => {
  event.preventDefault(); $("content").focus(); $("content").scrollIntoView();
});
window.addEventListener("hashchange", render);
if (matchMedia("(max-width: 620px)").matches) $("archive-nav").open = false;

async function init() {
  try {
    const response = await fetch("data/archive.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    archive = await response.json();
    if (archive.version !== 1 || !Array.isArray(archive.posts)) throw new Error("Unsupported archive format");
    if (archive.account) {
      const account = archive.account;
      $("owner").textContent = account.displayName || account.handle;
      $("profile-link").hidden = false;
      $("profile-link").textContent = `@${account.handle}`;
      $("profile-link").href = `https://bsky.app/profile/${encodeURIComponent(account.did)}`;
      $("description").textContent = account.description || "A personal collection of posts and conversations.";
      document.title = `${account.displayName || account.handle} · Bluesky archive`;
    }
    $("total").textContent = `${archive.posts.length.toLocaleString()} archived posts & replies`;
    if (archive.updated_at) $("updated").textContent = `Last successful sync: ${jstDay(archive.updated_at)} ${jstTime(archive.updated_at)} JST`;
    render();
  } catch (error) {
    archive = null; $("more").hidden = true;
    $("status").textContent = "Archive could not be loaded.";
    $("posts").replaceChildren(element("p", "notice", `Please reload or check that data/archive.json was deployed. For a local preview, start the web server described in the README. (${error.message})`));
  }
}
init();
