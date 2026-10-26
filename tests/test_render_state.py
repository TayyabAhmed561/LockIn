"""Offline tests: no network, Instagram is replaced by a fake fetcher."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import pytest

import generate_feeds
from igfeed import config, fetch, state
from igfeed.state import FeedState, Post

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
SITE = "https://example.github.io/ig-rss/"


def make_post(i: int, caption: str = "", **kw) -> Post:
    return Post(
        shortcode=f"SC{i}",
        date=T0 + timedelta(hours=i),
        caption=caption or f"Post number {i}\nsecond line & <stuff>",
        image_url=f"https://cdn.example/{i}.jpg",
        **kw,
    )


@pytest.fixture
def cfg_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.yml"
    path.write_text(
        "handles: [alpha, beta]\n"
        "site_title: Test feeds\n"
        "posts_per_handle: 3\n"
        "max_items_per_feed: 4\n"
        "mirror_images: false\n"
        "delay_seconds: [0, 0]\n"
    )
    return path


def run(cfg_file: Path, out: Path, fetcher, *extra: str) -> int:
    args = generate_feeds.parse_args(
        ["--config", str(cfg_file), "--out", str(out), "--site-url", SITE, *extra]
    )
    return generate_feeds.run(args, fetcher=fetcher, sleep=lambda _s: None)


def fake_fetcher(posts_by_handle: dict, errors: dict | None = None, calls: list | None = None):
    errors = errors or {}

    def fetcher(_loader, handle, limit):
        if calls is not None:
            calls.append(handle)
        if handle in errors:
            return errors[handle]
        return fetch.FetchResult(handle, full_name=handle.title(), posts=posts_by_handle.get(handle, [])[:limit])

    return fetcher


@pytest.fixture(autouse=True)
def no_real_loader(monkeypatch):
    monkeypatch.setattr(fetch, "make_loader", lambda: object())


def test_merge_dedupes_sorts_and_caps():
    prev = FeedState("alpha", posts=[make_post(1), make_post(2, media_path="media/alpha/SC2.jpg")])
    fresh = [make_post(2), make_post(3), make_post(4)]
    merged = state.merge(prev, fresh, max_items=3)
    assert [p.shortcode for p in merged.posts] == ["SC4", "SC3", "SC2"]
    assert merged.posts[2].media_path == "media/alpha/SC2.jpg"  # kept from the earlier run


def test_feeds_are_valid_rss(cfg_file, tmp_path):
    out = tmp_path / "public"
    posts = {"alpha": [make_post(3), make_post(2), make_post(1)], "beta": [make_post(10, is_video=True)]}
    assert run(cfg_file, out, fake_fetcher(posts)) == 0

    parsed = feedparser.parse((out / "feeds/alpha.xml").read_bytes())
    assert not parsed.bozo, parsed.get("bozo_exception")
    assert parsed.feed.title == "Alpha (@alpha) · Instagram"
    first = parsed.entries[0]
    assert first.title == "Post number 3"
    assert first.link == "https://www.instagram.com/p/SC3/"
    assert first.id == "https://www.instagram.com/p/SC3/"
    assert first.published_parsed[:4] == (2026, 10, 1, 15)
    html = first.content[0].value
    assert 'src="https://cdn.example/3.jpg"' in html
    assert "second line &amp; &lt;stuff&gt;" in html  # caption is escaped, not injected

    combined = feedparser.parse((out / "feeds/all.xml").read_bytes())
    assert not combined.bozo
    assert [e.title.split(":")[0] for e in combined.entries] == ["@beta", "@alpha", "@alpha", "@alpha"]
    assert "Watch on Instagram" in combined.entries[0].content[0].value

    index = (out / "index.html").read_text()
    assert SITE + "feeds/alpha.xml" in index and SITE + "feeds/all.xml" in index


def test_failed_fetch_keeps_previous_posts(cfg_file, tmp_path):
    out = tmp_path / "public"
    run(cfg_file, out, fake_fetcher({"alpha": [make_post(1)], "beta": [make_post(2)]}))

    errors = {"alpha": fetch.FetchResult("alpha", error="ProfileNotExistsException: gone")}
    assert run(cfg_file, out, fake_fetcher({"beta": [make_post(3)]}, errors)) == 0

    alpha = feedparser.parse((out / "feeds/alpha.xml").read_bytes())
    assert [e.link for e in alpha.entries] == ["https://www.instagram.com/p/SC1/"]
    saved = state.load("alpha", out, None, session=None)
    assert saved.last_error.startswith("ProfileNotExists") and saved.last_success is not None
    beta = feedparser.parse((out / "feeds/beta.xml").read_bytes())
    assert len(beta.entries) == 2


def test_block_stops_remaining_handles(cfg_file, tmp_path):
    calls = []
    errors = {"alpha": fetch.FetchResult("alpha", error="blocked by Instagram: 429", blocked=True)}
    code = run(cfg_file, tmp_path / "public", fake_fetcher({}, errors, calls))
    assert calls == ["alpha"]  # beta was never requested
    assert code == 1  # nothing to show at all
    beta = state.load("beta", tmp_path / "public", None, session=None)
    assert beta.last_error.startswith("skipped")


def test_dry_run_writes_nothing(cfg_file, tmp_path, capsys):
    out = tmp_path / "public"
    assert run(cfg_file, out, fake_fetcher({"alpha": [make_post(1)]}), "--dry-run") == 0
    assert not out.exists()
    assert "https://www.instagram.com/p/SC1/" in capsys.readouterr().out


def test_title_fallbacks():
    from igfeed.render import entry_title

    assert entry_title(make_post(1, caption="\n\n  Hello  \nworld")) == "Hello"
    assert entry_title(make_post(1, caption="x" * 300)).endswith("…")
    no_caption = make_post(1, is_video=True)
    no_caption.caption = ""
    assert entry_title(no_caption).startswith("Video ·")


@pytest.mark.parametrize("bad", ["handles: []", "handles: ['bad handle!']", "handles: [a]\ndelay_seconds: [9, 1]"])
def test_config_rejects_bad_values(tmp_path, bad):
    path = tmp_path / "c.yml"
    path.write_text(bad)
    with pytest.raises(config.ConfigError):
        config.load(path)


def test_shipped_config_is_valid():
    cfg = config.load(Path(__file__).parent.parent / "config.yml")
    assert cfg.handles and cfg.posts_per_handle <= 12
