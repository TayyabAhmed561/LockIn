"""Per-handle feed state: the posts we have seen, persisted as JSON next to the feeds.

State is read back on the next run (from the local output directory, or from the
currently deployed site in CI) so a failed fetch never empties a feed.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests

log = logging.getLogger(__name__)


@dataclass
class Post:
    shortcode: str
    date: datetime  # timezone-aware UTC
    caption: str
    image_url: str  # Instagram CDN URL; expires after a few days
    is_video: bool = False
    is_album: bool = False
    media_path: str | None = None  # path of the mirrored image, relative to the site root

    @property
    def url(self) -> str:
        return f"https://www.instagram.com/p/{self.shortcode}/"

    def to_json(self) -> dict:
        return {
            "shortcode": self.shortcode,
            "date": self.date.isoformat(),
            "caption": self.caption,
            "image_url": self.image_url,
            "is_video": self.is_video,
            "is_album": self.is_album,
            "media_path": self.media_path,
        }

    @classmethod
    def from_json(cls, d: dict) -> "Post":
        return cls(
            shortcode=d["shortcode"],
            date=datetime.fromisoformat(d["date"]),
            caption=d.get("caption", ""),
            image_url=d.get("image_url", ""),
            is_video=d.get("is_video", False),
            is_album=d.get("is_album", False),
            media_path=d.get("media_path"),
        )


@dataclass
class FeedState:
    handle: str
    full_name: str = ""
    posts: list[Post] = field(default_factory=list)
    last_success: datetime | None = None
    last_error: str | None = None

    @property
    def profile_url(self) -> str:
        return f"https://www.instagram.com/{self.handle}/"

    def to_json(self) -> dict:
        return {
            "handle": self.handle,
            "full_name": self.full_name,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_error": self.last_error,
            "posts": [p.to_json() for p in self.posts],
        }

    @classmethod
    def from_json(cls, d: dict) -> "FeedState":
        last = d.get("last_success")
        return cls(
            handle=d["handle"],
            full_name=d.get("full_name", ""),
            posts=[Post.from_json(p) for p in d.get("posts", [])],
            last_success=datetime.fromisoformat(last) if last else None,
            last_error=d.get("last_error"),
        )


def state_path(handle: str) -> str:
    return f"state/{handle}.json"


def load(handle: str, out_dir: Path, previous_site: str | None, session: requests.Session) -> FeedState:
    """Previous state from the local output dir, else the deployed site, else empty."""
    local = out_dir / state_path(handle)
    try:
        if local.exists():
            return FeedState.from_json(json.loads(local.read_text()))
        if previous_site:
            resp = session.get(previous_site + state_path(handle), timeout=20)
            if resp.status_code == 200:
                return FeedState.from_json(resp.json())
            if resp.status_code != 404:
                log.warning("@%s: could not load previous state (HTTP %s)", handle, resp.status_code)
    except (OSError, ValueError, KeyError, requests.RequestException) as e:
        log.warning("@%s: ignoring unreadable previous state: %s", handle, e)
    return FeedState(handle=handle)


def merge(prev: FeedState, fetched: list[Post], max_items: int) -> FeedState:
    """Add newly fetched posts to the previous ones, newest first, capped at max_items."""
    by_code = {p.shortcode: p for p in prev.posts}
    for post in fetched:
        old = by_code.get(post.shortcode)
        if old and not post.media_path:
            post.media_path = old.media_path
        by_code[post.shortcode] = post
    posts = sorted(by_code.values(), key=lambda p: p.date, reverse=True)[:max_items]
    return FeedState(
        handle=prev.handle,
        full_name=prev.full_name,
        posts=posts,
        last_success=prev.last_success,
        last_error=prev.last_error,
    )


def save(feed: FeedState, out_dir: Path) -> None:
    path = out_dir / state_path(feed.handle)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(feed.to_json(), indent=2, ensure_ascii=False))
