#!/usr/bin/env python3
"""Generate RSS feeds for public Instagram profiles listed in config.yml (no login)."""
import argparse
import logging
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from igfeed import config, fetch, media, render, state

log = logging.getLogger("igfeed")


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path("config.yml"))
    p.add_argument("--out", type=Path, default=Path("public"),
                   help="output directory; previous state is also read from here")
    p.add_argument("--site-url", default="http://localhost:8000/",
                   help="public base URL the output directory is served from")
    p.add_argument("--previous-site",
                   help="base URL of the currently deployed site, to restore earlier posts and images")
    p.add_argument("--handle", action="append",
                   help="only process this username (repeatable); overrides config.yml")
    p.add_argument("--no-fetch", action="store_true",
                   help="don't contact Instagram; re-render from previous state")
    p.add_argument("--dry-run", action="store_true", help="fetch and print posts, write nothing")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def _base_url(url: str) -> str:
    return url.rstrip("/") + "/"


def run(args: argparse.Namespace, fetcher=fetch.fetch_profile, sleep=time.sleep) -> int:
    cfg = config.load(args.config)
    handles = config.validate_handles(args.handle) if args.handle else cfg.handles
    site_url = _base_url(args.site_url)
    previous_site = _base_url(args.previous_site) if args.previous_site else None
    now = datetime.now(timezone.utc)
    session = requests.Session()

    loader = None if args.no_fetch else fetch.make_loader()
    blocked = False
    fetched_count = 0
    feeds = []

    for handle in handles:
        feed = state.load(handle, args.out, previous_site, session)

        if loader is not None and not blocked:
            if fetched_count:
                sleep(random.uniform(*cfg.delay_seconds))
            result = fetcher(loader, handle, cfg.posts_per_handle)
            fetched_count += 1
            if result.error:
                log.warning("@%s: %s", handle, result.error)
                feed.last_error = result.error
                if result.blocked:
                    blocked = True
                    log.warning("Instagram is refusing requests; skipping remaining handles this run")
            else:
                log.info("@%s: fetched %d posts", handle, len(result.posts))
                feed = state.merge(feed, result.posts, cfg.max_items_per_feed)
                feed.full_name = result.full_name or feed.full_name
                feed.last_success, feed.last_error = now, None
        elif blocked:
            feed.last_error = "skipped: Instagram was refusing requests earlier in this run"

        if args.dry_run:
            for p in feed.posts:
                print(f"@{handle}  {p.date:%Y-%m-%d %H:%M}  {p.url}  {render.entry_title(p)}")
            feeds.append(feed)
            continue

        if cfg.mirror_images:
            media.mirror(feed, args.out, previous_site, session)
        else:
            for p in feed.posts:
                p.media_path = None
        state.save(feed, args.out)
        render.write_feed(feed, args.out, site_url)
        feeds.append(feed)

    if not args.dry_run:
        render.write_combined(feeds, args.out, site_url, cfg)
        render.write_index(feeds, args.out, site_url, cfg, now)
        log.info("Wrote %d feeds to %s", len(feeds) + 1, args.out)

    if not any(f.posts for f in feeds) and any(f.last_error for f in feeds):
        log.error("No posts available for any handle; nothing useful to publish")
        return 1
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    # Instaloader logs every request at INFO via its own context; keep our output readable.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    try:
        return run(args)
    except config.ConfigError as e:
        log.error("config error: %s", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
