"""Render feed state into RSS 2.0 files and a small index page."""
from datetime import datetime
from html import escape
from pathlib import Path

from feedgen.feed import FeedGenerator

from .config import Config
from .state import FeedState, Post

TITLE_LEN = 100


def entry_title(post: Post) -> str:
    first_line = next((line.strip() for line in post.caption.splitlines() if line.strip()), "")
    if not first_line:
        kind = "Video" if post.is_video else "Album" if post.is_album else "Photo"
        return f"{kind} · {post.date:%b %d, %Y}"
    if len(first_line) > TITLE_LEN:
        return first_line[: TITLE_LEN - 1].rstrip() + "…"
    return first_line


def _image_src(post: Post, site_url: str) -> str:
    return site_url + post.media_path if post.media_path else post.image_url


def _content_html(post: Post, site_url: str) -> str:
    url = escape(post.url)
    parts = [f'<p><a href="{url}"><img src="{escape(_image_src(post, site_url))}" alt=""></a></p>']
    if post.is_video:
        parts.append(f'<p><em>▶ Video. <a href="{url}">Watch on Instagram</a></em></p>')
    elif post.is_album:
        parts.append(f'<p><em>Album, first photo shown. <a href="{url}">See all on Instagram</a></em></p>')
    if post.caption:
        parts.append("<p>" + escape(post.caption).replace("\n", "<br>") + "</p>")
    parts.append(f'<p><a href="{url}">View on Instagram</a></p>')
    return "\n".join(parts)


def _build(title: str, link: str, self_url: str, description: str,
           entries: list[tuple[Post, str]], site_url: str) -> FeedGenerator:
    fg = FeedGenerator()
    fg.title(title)
    fg.link(href=link, rel="alternate")
    fg.link(href=self_url, rel="self")
    fg.description(description)
    fg.language("en")
    fg.generator("igfeed")
    for post, entry_title in entries:
        fe = fg.add_entry(order="append")
        fe.guid(post.url, permalink=True)
        fe.title(entry_title)
        fe.link(href=post.url)
        fe.published(post.date)
        fe.description(post.caption or entry_title)
        fe.content(_content_html(post, site_url), type="CDATA")
    return fg


def feed_path(handle: str) -> str:
    return f"feeds/{handle}.xml"


def write_feed(feed: FeedState, out_dir: Path, site_url: str) -> None:
    name = f"{feed.full_name} (@{feed.handle})" if feed.full_name else f"@{feed.handle}"
    fg = _build(
        title=f"{name} · Instagram",
        link=feed.profile_url,
        self_url=site_url + feed_path(feed.handle),
        description=f"Public Instagram posts from @{feed.handle}",
        entries=[(p, entry_title(p)) for p in feed.posts],
        site_url=site_url,
    )
    path = out_dir / feed_path(feed.handle)
    path.parent.mkdir(parents=True, exist_ok=True)
    fg.rss_file(str(path), pretty=True)


def write_combined(feeds: list[FeedState], out_dir: Path, site_url: str, cfg: Config) -> None:
    tagged = [(p, f"@{f.handle}: {entry_title(p)}") for f in feeds for p in f.posts]
    tagged.sort(key=lambda e: e[0].date, reverse=True)
    fg = _build(
        title=cfg.site_title,
        link=site_url,
        self_url=site_url + feed_path("all"),
        description="All tracked Instagram pages in one feed",
        entries=tagged[: cfg.combined_feed_items],
        site_url=site_url,
    )
    path = out_dir / feed_path("all")
    path.parent.mkdir(parents=True, exist_ok=True)
    fg.rss_file(str(path), pretty=True)


def write_index(feeds: list[FeedState], out_dir: Path, site_url: str, cfg: Config, now: datetime) -> None:
    rows = []
    for f in feeds:
        url = escape(site_url + feed_path(f.handle))
        ok = f"{f.last_success:%Y-%m-%d %H:%M} UTC" if f.last_success else "never"
        status = f'<span class="err">{escape(f.last_error)}</span>' if f.last_error else "ok"
        rows.append(
            f'<tr><td><a href="{escape(f.profile_url)}">@{escape(f.handle)}</a></td>'
            f'<td><a href="{url}">{url}</a></td><td>{len(f.posts)}</td><td>{ok}</td><td>{status}</td></tr>'
        )
    all_url = escape(site_url + feed_path("all"))
    title = escape(cfg.site_title)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{title}</title>
<link rel="alternate" type="application/rss+xml" title="{title}" href="{all_url}">
<style>
  body {{ font: 15px/1.5 -apple-system, system-ui, sans-serif; margin: 2rem auto; max-width: 60rem; padding: 0 1rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  td, th {{ border-bottom: 1px solid #8884; padding: .4rem; text-align: left; word-break: break-all; }}
  .err {{ color: #c0392b; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p>Combined feed: <a href="{all_url}">{all_url}</a></p>
<p>Copy any feed link into your RSS reader. Last build: {now:%Y-%m-%d %H:%M} UTC.</p>
<table>
<tr><th>Page</th><th>Feed URL</th><th>Posts</th><th>Last successful fetch</th><th>Last run</th></tr>
{chr(10).join(rows)}
</table>
</body>
</html>
"""
    (out_dir / "index.html").write_text(page)
    # Keep the site out of search engines; it is public but not meant to be found.
    (out_dir / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
