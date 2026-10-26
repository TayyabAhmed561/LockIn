"""Mirror post images into the site so feeds keep working after Instagram's CDN links expire."""
import logging
import random
import time
from pathlib import Path

import requests

from .state import FeedState, Post

log = logging.getLogger(__name__)

EXTENSIONS = {"image/jpeg": ".jpg", "image/webp": ".webp", "image/png": ".png"}


def _download(session: requests.Session, url: str) -> tuple[bytes, str] | None:
    try:
        resp = session.get(url, timeout=30)
    except requests.RequestException as e:
        log.debug("download failed %s: %s", url, e)
        return None
    ctype = resp.headers.get("Content-Type", "").split(";")[0].strip()
    if resp.status_code != 200 or ctype not in EXTENSIONS:
        return None
    return resp.content, EXTENSIONS[ctype]


def _existing(media_dir: Path, shortcode: str) -> Path | None:
    return next(iter(sorted(media_dir.glob(f"{shortcode}.*"))), None)


def _mirror_post(post: Post, media_dir: Path, out_dir: Path, previous_site: str | None,
                 session: requests.Session, sleep) -> None:
    found = _existing(media_dir, post.shortcode)
    if found:
        post.media_path = found.relative_to(out_dir).as_posix()
        return

    # Restore an image mirrored on an earlier run, before trying Instagram's (maybe expired) URL.
    got = None
    if previous_site and post.media_path:
        got = _download(session, previous_site + post.media_path)
    if got is None and post.image_url:
        sleep(random.uniform(0.5, 1.5))
        got = _download(session, post.image_url)
    if got is None:
        post.media_path = None  # renderer falls back to the Instagram URL
        return

    data, ext = got
    path = media_dir / f"{post.shortcode}{ext}"
    path.write_bytes(data)
    post.media_path = path.relative_to(out_dir).as_posix()


def mirror(feed: FeedState, out_dir: Path, previous_site: str | None,
           session: requests.Session, sleep=time.sleep) -> None:
    media_dir = out_dir / "media" / feed.handle
    media_dir.mkdir(parents=True, exist_ok=True)
    for post in feed.posts:
        _mirror_post(post, media_dir, out_dir, previous_site, session, sleep)

    keep = {p.media_path for p in feed.posts if p.media_path}
    for f in media_dir.iterdir():
        if f.relative_to(out_dir).as_posix() not in keep:
            f.unlink()
