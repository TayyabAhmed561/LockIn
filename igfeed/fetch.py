"""Anonymous (logged-out) fetching of public Instagram profiles via Instaloader.

There is deliberately no login code here, so no real account can be affected.
"""
import itertools
import logging
from dataclasses import dataclass, field
from datetime import timezone

import instaloader
from instaloader import exceptions as ie

from .state import Post

log = logging.getLogger(__name__)

# Errors that mean Instagram is refusing anonymous requests from this IP right now.
# When we see one we stop for the whole run instead of digging the hole deeper.
BLOCKING_ERRORS = (
    ie.ConnectionException,  # includes 429 Too Many Requests and 401 "please wait"
    ie.LoginRequiredException,
    ie.QueryReturnedBadRequestException,
)

# Errors that only concern this one handle.
HANDLE_ERRORS = (
    ie.ProfileNotExistsException,
    ie.PrivateProfileNotFollowedException,
)


@dataclass
class FetchResult:
    handle: str
    full_name: str = ""
    posts: list[Post] = field(default_factory=list)
    error: str | None = None
    blocked: bool = False


def make_loader() -> instaloader.Instaloader:
    return instaloader.Instaloader(
        quiet=True,
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        max_connection_attempts=1,  # never retry into a block
        request_timeout=30.0,
    )


def _to_post(p: instaloader.Post) -> Post:
    # Only fields present in the profile's post list are read, so this costs no extra requests.
    return Post(
        shortcode=p.shortcode,
        date=p.date_utc.replace(tzinfo=timezone.utc),
        caption=p.caption or "",
        image_url=p.url,
        is_video=p.is_video,
        is_album=p.typename == "GraphSidecar",
    )


def fetch_profile(loader: instaloader.Instaloader, handle: str, limit: int) -> FetchResult:
    try:
        profile = instaloader.Profile.from_username(loader.context, handle)
        if profile.is_private:
            return FetchResult(handle, error="profile is private")
        posts = [_to_post(p) for p in itertools.islice(profile.get_posts(), limit)]
        return FetchResult(handle, full_name=profile.full_name or "", posts=posts)
    except HANDLE_ERRORS as e:
        return FetchResult(handle, error=f"{type(e).__name__}: {e}")
    except BLOCKING_ERRORS as e:
        return FetchResult(handle, error=f"blocked by Instagram: {e}", blocked=True)
    except Exception as e:  # Instagram changes its responses often; keep other handles going.
        log.debug("unexpected error for @%s", handle, exc_info=True)
        return FetchResult(handle, error=f"{type(e).__name__}: {e}")
