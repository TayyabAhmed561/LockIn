# Instagram → RSS

Turns public Instagram pages into RSS feeds for NetNewsWire (or any RSS reader), with **no Instagram login**. A GitHub Actions job runs twice a day and publishes the feeds on GitHub Pages for free.

> **Read this first: reliability.** Instagram blocks most logged-out requests. In a test from a home connection on 2026-10-26, the very first request came back `401 "Please wait a few minutes before you try again."` GitHub's servers get blocked even more often. When that happens this project keeps serving the last good feed and shows the error on the index page. It does not try to get around blocks. Feeds may update rarely or never. See [If feeds never update](#if-feeds-never-update).

## How it works

```
GitHub Actions (7 am & 7 pm)                   GitHub Pages (public website)
┌──────────────────────────────────┐           ┌──────────────────────────────┐
│ generate_feeds.py                │  deploy   │ /feeds/<page>.xml            │ ← NetNewsWire
│  1. load last run's posts (site) │ ────────▶ │ /feeds/all.xml               │   (Mac + iPhone)
│  2. ask Instagram for new posts  │           │ /media/… (copied images)     │
│  3. merge, copy images, write XML│           │ /index.html (status page)    │
└──────────────────────────────────┘           └──────────────────────────────┘
```

- **No login code exists**, so your personal account can't be affected.
- Requests are kept low: one request per page, a 5–15 s random pause between pages, no retries. Everything stops for the run at the first sign of a block.
- If a page fails, its feed keeps the posts from earlier runs, so it never goes empty.
- Only regular feed posts are covered. Stories and DMs need a logged-in account.

## Project layout

```
.github/workflows/main.yml   schedule + build + deploy to GitHub Pages
config.yml                   ← the file you edit: which pages to follow, etc.
generate_feeds.py            the program the workflow runs
igfeed/                      fetch (Instagram), state (memory), media (images), render (RSS)
tests/                       offline tests (no network)
requirements.txt             Python libraries the program needs
```

## Setup, step by step

You need a free [GitHub account](https://github.com/signup). Commands below go in the macOS **Terminal** app.

### 1. Pick your pages

Open `config.yml` and replace the example usernames under `handles:` with the pages you want. Use the name from the profile URL: `instagram.com/blogto` → `blogto`. Fewer pages mean fewer blocks; 10 or fewer is a good limit.

### 2. (Optional) Test on your Mac

```bash
cd ~/LockIn
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q                                 # offline tests, should all pass
.venv/bin/python generate_feeds.py --handle blogto --dry-run   # one real request
```

`--dry-run` prints posts without writing files. A `blocked by Instagram` warning means Instagram refused the request (see the warning above), not that your setup is wrong.

### 3. Create the GitHub repository

1. Go to <https://github.com/new>.
2. Name it, for example `ig-rss`. Choose **Public** (free GitHub Pages needs a public repo). Don't add a README, .gitignore or license.
3. Click **Create repository** and leave the page open.

### 4. Push the code

Replace `YOUR-USERNAME` below with your GitHub username:

```bash
cd ~/LockIn
git add .
git commit -m "Instagram RSS feeds"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/ig-rss.git
git push -u origin main
```

If Git asks for a password, it wants a **token**, not your GitHub password. The easiest fix is `brew install gh`, then `gh auth login` (pick GitHub.com → HTTPS → log in with a web browser), then run `git push -u origin main` again.

### 5. Turn on GitHub Pages

In the repo on github.com: **Settings → Pages → Build and deployment → Source: GitHub Actions**. Do this before the first run, or the workflow fails at "Configure GitHub Pages".

### 6. Run it once by hand

**Actions** tab → **Build RSS feeds** (left side) → **Run workflow** → **Run workflow**. Wait for both `build` and `deploy` to turn green, about 1–2 minutes. Click into `build` → **Generate feeds** to see which pages worked.

If `build` fails with *"No posts available for any handle"*, every page was blocked on a first run with nothing saved yet. The scheduled runs will keep trying.

### 7. Get your feed links

Open `https://YOUR-USERNAME.github.io/ig-rss/`. The page lists every feed URL and when it last updated:

- One page: `https://YOUR-USERNAME.github.io/ig-rss/feeds/blogto.xml`
- Everything together: `https://YOUR-USERNAME.github.io/ig-rss/feeds/all.xml`

### 8. Add them to NetNewsWire

- **Mac:** File → New Web Feed… (⌘N) → paste a feed URL → Add.
- **iPhone:** tap **+** → **Add Web Feed** → paste the URL → Add.
- To add each feed only once, use an **iCloud** account in NetNewsWire on both devices so subscriptions sync.

After that it runs on its own at about 7 am and 7 pm Toronto time. GitHub's scheduler can start runs late, sometimes by an hour.

## Changing things later

- **Add or remove a page:** edit `config.yml` on github.com (pencil icon → *Commit changes*). It takes effect on the next run, or run it by hand from the Actions tab.
- **Change the schedule:** edit the `cron:` line in `.github/workflows/main.yml`. Times are in UTC. [crontab.guru](https://crontab.guru) helps.
- **Images:** `mirror_images: true` copies each post's image into the site, because Instagram's image links stop working after a few days. Set it to `false` to link to Instagram's copy instead.

## Things to know

- **The site is public.** Anyone with the URL can see your list of pages and the copied images. Search engines are asked not to index it (`robots.txt`), but it isn't secret. Free GitHub Pages doesn't support private sites.
- **Copied images belong to their owners.** Mirroring republishes them on your public site. Keep it for personal reading, or set `mirror_images: false`.
- **Instagram's terms** don't allow automated collection. This tool keeps volume very low and is meant for personal use.
- **60-day pause.** GitHub stops scheduled workflows in public repos after 60 days with no commits. You'll get an email; re-enable it from the Actions tab, or make any small commit.
- **Videos and albums** show the cover image with a link to watch or see the rest on Instagram.

## If feeds never update

Check the index page's "Last successful fetch" column. If it stays at `never` or keeps showing `blocked by Instagram`, logged-out access isn't working from GitHub's servers. Options, most reliable first:

1. **Instagram's official API ("Business Discovery").** You'd create a separate Instagram professional account (not your personal one) linked to a Facebook Page and a Meta developer app. It can then read public posts from other business and creator accounts, which most news and sports pages are. It's free, allowed by Meta, and doesn't get blocked. Setup takes about 30–60 minutes, and this project's `fetch.py` would be swapped for an API call.
2. **A paid Instagram-to-RSS service.** These run the scraping on their own infrastructure.
3. **Lower the load:** fewer handles, and keep `posts_per_handle` at 12 or less.

## Running the tests

```bash
.venv/bin/pytest -q
```
