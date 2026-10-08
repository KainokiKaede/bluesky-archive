# Personal Bluesky archive

A small, Twilog-like archive for **one public Bluesky account**:

**Bluesky public API → GitHub Actions → JSON in Git → GitHub Pages**

Vanilla HTML/CSS/JavaScript, one Python script, no database, no package installation, no Bluesky credentials. It includes replies, excludes reposts (including self-reposts), and shows every date in Japan Standard Time. Japanese full-text search runs entirely in your browser, with literal substring matching and highlighted results. Search `検索テスト` to find every archived post containing those exact characters.

## Set it up, step by step

You need a GitHub account and your public Bluesky handle. No paid plan is needed when you use a **public** repository and the included standard GitHub-hosted runner. Both the repository's data and the website will be public. See [GitHub Pages availability](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) and [free standard runners for public repositories](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

### 1. Create the repository and upload these files

On GitHub, select **+ → New repository**. Name it **`bluesky-archive`**, select **Public**, enable **Add a README file**, and create it. Keep the default branch (usually `main`).

In the repository, choose **Add file → Upload files**. Upload the contents of this project, preserving this structure at the repository's top level:

```text
bluesky-archive/
├── .github/workflows/archive.yml
├── .gitignore
├── config.json
├── README.md
├── scripts/update_archive.py
├── site/
│   ├── .nojekyll
│   ├── index.html
│   ├── styles.css
│   ├── app.mjs
│   ├── search.mjs
│   └── data/archive.json
└── tests/
    ├── test_update_archive.py
    └── search.test.mjs
```

Upload the **contents**, not an extra enclosing folder or an unextracted ZIP. Commit the files to your default branch. If GitHub's upload page rejects an existing README, skip our README during upload and replace it using the file editor afterward.

**Do not miss `.github/workflows/archive.yml`.** Folders beginning with a dot may be hidden on your computer (on macOS, Command+Shift+Period toggles hidden files). If it did not upload, use **Add file → Create new file**, enter `.github/workflows/archive.yml` as the filename, paste the contents of the provided workflow, and commit. You can create `.gitignore` and the empty `site/.nojekyll` the same way; `.nojekyll` is optional with this workflow. Confirm that `config.json`, `scripts`, `site`, `tests`, and `.github` are visible at the repository root on GitHub.

The upload may start a workflow before setup is finished. A failed run at this point is harmless; finish the following steps and run it again.

### 2. Enter your Bluesky handle

Open **`config.json`** on GitHub, click the pencil icon, and replace the placeholder:

```json
{
  "handle": "yourname.bsky.social"
}
```

Use your actual handle, including its domain. A custom handle such as `you.example.com` also works. Do not enter your display name, password, app password, or a profile URL. A leading `@` is accepted but unnecessary. Keep the quotation marks and commit the edit.

This is the only required configuration file. Your display name and profile description are retrieved automatically. If your handle changes later, update this same field; the archive checks your permanent account ID (DID) to prevent mixing two accounts. Use a separate repository for a different account.

### 3. Allow GitHub Actions to run and commit

In your repository, open **Settings → Actions → General**:

1. Under **Actions permissions**, ensure GitHub Actions is enabled and GitHub's own `actions/*` actions are allowed. A personal repository can use **Allow all actions and reusable workflows**.
2. Under **Workflow permissions**, select **Read and write permissions**, then **Save** if available. The included workflow also explicitly requests `contents: write` for the update job.
3. If your repository has branch rules requiring pull requests or restricting pushes, allow this workflow to update the default branch or use a fresh personal repository without those rules. No branch rules are needed for this archive.

You do **not** need to create any repository secrets, personal access tokens, or Bluesky credentials. GitHub supplies the workflow's repository token automatically. You do not need to enable permission to create or approve pull requests.

### 4. Enable GitHub Pages

Open **Settings → Pages**. Under **Build and deployment → Source**, select **GitHub Actions**. Do not add a suggested Pages workflow: this project already includes one. [Official setup instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

This project publishes the `site/` folder. It does not use branch-based Pages publishing, a `docs/` folder, or a `gh-pages` branch. Updates and deployment happen in the same workflow because commits made by `GITHUB_TOKEN` do not trigger a separate Pages build.

### 5. Run the initial historical import

1. Open the repository's **Actions** tab.
2. If GitHub displays an enable-workflows notice, enable workflows.
3. Select **Update and publish archive** on the left.
4. Click **Run workflow**, choose the **default branch** (usually `main`), then click the green **Run workflow** button.
5. Open the new run. Wait until both **update** and **deploy** have green check marks. Large histories take longer.

The first run follows the API's pagination until there is no next cursor. It imports all posts the public author-feed API makes available, including replies. The **Fetch all available posts and merge safely** step reports page counts and the number of unique posts. The result is committed to `site/data/archive.json`, then published.

There is no special import switch. Initial import, manual updates, and daily updates use the same safe process. Re-running does not duplicate posts.

### 6. Manually test an update and search

Optionally publish a Bluesky post containing `検索テスト`. Allow a little time for Bluesky's public API to index it. Run **Update and publish archive → Run workflow** again.

After the run succeeds:

- Reload the Pages site and check that the post appears with its date and time in **JST**.
- Search for **`検索テスト`**. Matching text should be highlighted, including matches inside longer sentences and in replies. Search submits with Enter or the Search button.
- Open a month, then one of its numbered days. Replies carry a **Reply** label; **Replies only** shows just replies.
- Click **Permalink** to open one archived post; **View on Bluesky** opens the original.
- Run the workflow once more. Posts should remain unique. The last successful sync time updates even when no new posts were found.

A new search covers **the whole archive**, even if you were viewing one month. Matching is literal and case-sensitive; it does not stem words, ignore spaces, or normalize character width. The searched content is your post text, not image alt text, linked articles, or quoted authors' text. **Show more posts** reveals additional results, 50 at a time; search always checks all loaded posts.

### 7. Confirm the daily schedule works

The included schedule requests an update each day at **09:23 JST (00:23 UTC)**. You do not need to keep your computer on.

After the next scheduled time, open **Actions → Update and publish archive** and look for a run with event **schedule**, then check for green **update** and **deploy** jobs. Confirm the website's **Last successful sync** date advanced. You can also inspect the bot's **Update Bluesky archive** commit and `updated_at` in the JSON.

GitHub schedules can run late or occasionally be skipped; this is not an exact-time service. Schedules run only from the default branch and can be disabled after 60 days without repository activity. If disabled, open the workflow and choose **Enable workflow**, then run it manually. Check the Actions history periodically. [GitHub schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

To change the time, edit the cron line in `.github/workflows/archive.yml`. It uses UTC; JST is UTC plus nine hours.

### 8. Open your archive

For a repository named `bluesky-archive`, the usual address is:

```text
https://YOUR_GITHUB_USERNAME.github.io/bluesky-archive/
```

Replace the username with your GitHub username. A different repository name changes the last path component. If your repository is named exactly `YOUR_GITHUB_USERNAME.github.io`, the site lives at the domain root instead. **Settings → Pages** and the successful deployment show the exact address. Initial publishing can take a few minutes.

### 9. If something fails

Open **Actions → the failed run → the red job → the red step** to read the error. After fixing a setting, start a **new Run workflow** from the default branch so it uses the latest files.

| Symptom | What to do |
| --- | --- |
| Workflow is missing / no Run workflow button | Check `.github/workflows/archive.yml` exists on the default branch; enable Actions; refresh the page. Make sure files are not inside another enclosing folder. |
| Placeholder / invalid handle error, HTTP 400 or 404 during fetch | Correct `config.json` and make sure the account and its posts are publicly accessible without logging in. |
| HTTP 429, 5xx, timeout or temporary network error | The script retries four times per request. If it still fails, wait and start a new run. The prior JSON and deployed website remain intact. |
| Different-account error | The handle resolves to a different DID. Correct it; do not mix accounts. A changed handle for the same DID is accepted. |
| Commit fails with 403 / protected branch error | Check Actions write permissions and branch rules in step 3. Organization policies may override repository settings. |
| Push rejected because the branch changed during import | Start a new run. It checks out the latest archive and merges again; it never force-pushes. |
| Configure Pages / deployment fails | Set Pages Source to **GitHub Actions**; verify the repository is public. Check the `github-pages` environment permits the default branch. The archive may already be committed even though deployment failed; run again after fixing settings. |
| Website gives 404 | Confirm both jobs succeeded, use the exact URL in Settings → Pages, include the repository path, and wait a few minutes. |
| Site says archive could not be loaded | Reload; check `site/data/archive.json` exists and is valid JSON. Do not open `index.html` with `file://`; use the local server below. |
| No search results | Try a shorter exact phrase with matching case/spacing. Confirm the post text exists in the JSON and the latest sync succeeded. Choose All posts to clear filters. |
| Posts are missing | Inspect the fetch log and run again after API indexing catches up. Deleted, restricted, or API-unavailable posts cannot be imported. Reposts are intentionally excluded. |
| Archive JSON is corrupt | Use the file's GitHub **History** to recover a valid previous version. The updater refuses to replace an invalid archive automatically. Do not erase your only backup. |
| Schedule stopped | Check for an enable-workflow notice and confirm the workflow is on the default branch. See step 7. |
| Import exceeds the 60-minute job timeout | Raise `timeout-minutes` for the update job and retry, or run locally and commit the result. Very large archives may eventually need a sharded format. Partial imports are never committed. |

## How it works and what is preserved

- `scripts/update_archive.py` uses only Python 3.11+ standard-library modules. It calls the unauthenticated Bluesky AppView: `app.bsky.actor.getProfile` and `app.bsky.feed.getAuthorFeed` with `posts_with_replies`, 100 entries per page, and pins disabled. [Official author-feed API definition](https://github.com/bluesky-social/atproto/blob/main/lexicons/app/bsky/feed/getAuthorFeed.json).
- **Every run traverses all available pages.** This is deliberately simpler than cursor checkpoints or stopping at the first known post. It recovers missed/backfilled posts on later runs, handles long gaps, and refreshes metadata. It makes roughly one request per 100 feed entries plus the profile request; a short pause between pages and retries reduce request pressure.
- Posts are keyed by their permanent AT URI. Repeated pages cannot create duplicates. Only the configured author's own posts are kept. Replies are identified by `record.reply`; quote posts are retained as authored posts.
- `site/data/archive.json` contains a format version, the account's DID/profile, the last successful sync timestamp, and posts sorted newest first. Each post stores its URI, CID, original Bluesky URL, original `record`, and hydrated `embed` when available. This preserves Unicode text, original timestamp/offset, reply parent/root references, languages, facets and links, image blob references/alt text/dimensions, card metadata, and quote/video metadata supplied by the API. UTC timestamps stay portable; the browser explicitly displays JST.
- All API pages must succeed before any save. Network errors, malformed records, repeated cursors, account mismatches, and corrupt existing JSON abort the update. A temporary file is flushed and atomically replaces the archive only when complete. The workflow commits and publishes only after success, serializes its runs, and never force-pushes.
- **Previously archived posts are retained even if later deleted or unavailable on Bluesky.** Posts deleted before the first import cannot be recovered. This is an archive, not a deletion mirror. To remove a post, delete it from Bluesky and remove its entry from the JSON; prior copies may still exist in Git history. Disable the workflow first if you need to stop collection.
- Image/video bytes and linked web pages are **not downloaded**. Image URLs, original blobs and useful metadata are preserved; image previews depend on the remote host remaining available. Videos link to Bluesky. Export the JSON or clone the repository for a portable copy of the text archive.
- The site downloads one JSON file and searches it locally with JavaScript `includes`. No external search service, analytics, framework, fonts, or build system are needed. Text and highlights are created using DOM text nodes, and media/link URLs are limited to HTTP(S). The complete JSON must fit browser memory; for very large archives, initial loading/search will become slower and GitHub's file/site limits will apply.

## Optional: run and preview locally

From this project's folder, with Python 3.11 or later installed:

```sh
# Set your handle in config.json first.
python3 scripts/update_archive.py

# Or fetch/validate without modifying the file:
python3 scripts/update_archive.py --dry-run

# Preview the static site; leave this running while you browse.
python3 -m http.server 8000 --bind 127.0.0.1 --directory site
```

Open [http://localhost:8000](http://localhost:8000). Stop the server with Control+C. Before import, the site displays an honest empty state. A local run updates files locally; commit and push them to your GitHub repository to publish. Avoid running two local updaters against the same file at once.

Run the offline regression tests (Python 3.11+ and Node.js 20+; Node is only needed for tests):

```sh
python3 -m unittest discover -s tests -v
node --test tests/search.test.mjs
node --check site/app.mjs
```

Tests cover pagination, duplicate prevention, replies/reposts, Japanese and emoji preservation, retries, cursor loops, corrupt archives, identity checks, failed writes, search beyond the first results page, highlighting, URL safety, and JST date boundaries. These checks also run before each GitHub update.
