"""Load and validate config.yml."""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# Instagram usernames: letters, digits, "." and "_", up to 30 characters.
HANDLE_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    handles: list[str]
    site_title: str = "Instagram feeds"
    posts_per_handle: int = 6
    max_items_per_feed: int = 30
    combined_feed_items: int = 100
    mirror_images: bool = True
    delay_seconds: tuple[float, float] = (5.0, 15.0)


def validate_handles(handles) -> list[str]:
    if not isinstance(handles, list) or not handles:
        raise ConfigError("'handles' must be a non-empty list of usernames")
    cleaned = []
    for h in handles:
        h = str(h).strip().lstrip("@").lower()
        if not HANDLE_RE.match(h):
            raise ConfigError(f"invalid Instagram username: {h!r}")
        if h not in cleaned:
            cleaned.append(h)
    return cleaned


def _positive_int(raw: dict, key: str, default: int) -> int:
    value = raw.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ConfigError(f"'{key}' must be a positive whole number")
    return value


def load(path: Path) -> Config:
    try:
        raw = yaml.safe_load(Path(path).read_text()) or {}
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    if not isinstance(raw, dict):
        raise ConfigError("config must be a mapping of settings")

    delay = raw.get("delay_seconds", [5, 15])
    if (
        not isinstance(delay, list)
        or len(delay) != 2
        or not all(isinstance(d, (int, float)) and d >= 0 for d in delay)
        or delay[0] > delay[1]
    ):
        raise ConfigError("'delay_seconds' must be [min, max] with 0 <= min <= max")

    return Config(
        handles=validate_handles(raw.get("handles")),
        site_title=str(raw.get("site_title", Config.site_title)),
        posts_per_handle=_positive_int(raw, "posts_per_handle", Config.posts_per_handle),
        max_items_per_feed=_positive_int(raw, "max_items_per_feed", Config.max_items_per_feed),
        combined_feed_items=_positive_int(raw, "combined_feed_items", Config.combined_feed_items),
        mirror_images=bool(raw.get("mirror_images", True)),
        delay_seconds=(float(delay[0]), float(delay[1])),
    )
