"""podcast:chapters JSON with chapter images and links."""

import json
import shutil
from pathlib import Path
from typing import Any

from mutagen.id3 import APIC, WXXX

from app.auth.feed_tokens import _resolve_feed_id
from app.auth.middleware import _is_token_protected_endpoint
from app.extensions import db
from app.feeds import generate_feed_xml
from app.models import Feed, Post
from app.routes.post_routes import post_bp
from app.runtime_config import config as runtime_config
from podcast_processor.chapter_reader import Chapter
from podcast_processor.chapter_writer import write_chapters

DATA = Path(__file__).parent / "data" / "count_0_99.mp3"
PNG = b"\x89PNG\r\n\x1a\n" + b"1" * 40


def _processed_mp3(tmp_path: Path) -> Path:
    path = tmp_path / "processed.mp3"
    shutil.copyfile(DATA, path)
    write_chapters(
        str(path),
        [
            Chapter(
                "a",
                "Intro",
                0,
                10_000,
                sub_frames=[
                    APIC(encoding=3, mime="image/png", type=0, desc="", data=PNG),
                    WXXX(encoding=3, desc="", url="https://retro.example/intro"),
                ],
            ),
            Chapter("b", "Thema", 10_000, 40_000),
        ],
    )
    return path


def _setup(app: Any, tmp_path: Path) -> tuple[Any, int]:
    app.testing = True
    app.register_blueprint(post_bp)
    with app.app_context():
        feed = Feed(
            title="RK",
            rss_url="http://example.com/rk-ch",
            image_url="http://example.com/rk.png",
        )
        db.session.add(feed)
        db.session.commit()
        db.session.add_all(
            [
                Post(
                    feed_id=feed.id,
                    guid="with",
                    title="With",
                    download_url="http://example.com/with.mp3",
                    whitelisted=True,
                    processed_audio_path=str(_processed_mp3(tmp_path)),
                ),
                Post(
                    feed_id=feed.id,
                    guid="plain",
                    title="Plain",
                    download_url="http://example.com/plain.mp3",
                    whitelisted=True,
                    processed_audio_path=str(DATA),
                ),
            ]
        )
        db.session.commit()
        return app.test_client(), feed.id


def test_chapters_json_matches_processed_file(app: Any, tmp_path: Path) -> None:
    client, _ = _setup(app, tmp_path)

    response = client.get("/post/with/chapters.json", base_url="http://podly.local")
    image = client.get("/post/with/chapter-images/0")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/json+chapters")
    document = json.loads(response.get_data(as_text=True))
    assert document["version"] == "1.2.0"
    assert document["chapters"] == [
        {
            "startTime": 0.0,
            "title": "Intro",
            "endTime": 10.0,
            "img": "http://podly.local/post/with/chapter-images/0",
            "url": "https://retro.example/intro",
        },
        {"startTime": 10.0, "title": "Thema", "endTime": 40.0},
    ]
    assert image.status_code == 200
    assert image.headers["Content-Type"] == "image/png"
    assert image.data == PNG


def test_missing_chapters_or_images_are_404(app: Any, tmp_path: Path) -> None:
    client, _ = _setup(app, tmp_path)

    assert client.get("/post/plain/chapters.json").status_code == 404
    assert client.get("/post/with/chapter-images/1").status_code == 404
    assert client.get("/post/with/chapter-images/9").status_code == 404
    assert client.get("/post/nope/chapters.json").status_code == 404


def test_feed_lists_chapters_only_for_files_with_chapters(
    app: Any, tmp_path: Path
) -> None:
    _, feed_id = _setup(app, tmp_path)
    with app.app_context():
        original = getattr(runtime_config, "autoprocess_on_download", False)
        runtime_config.autoprocess_on_download = False
        try:
            feed = db.session.get(Feed, feed_id)
            assert feed is not None
            with app.test_request_context(base_url="http://podly.local"):
                xml = str(generate_feed_xml(feed))
        finally:
            runtime_config.autoprocess_on_download = original

    assert xml.count("<podcast:chapters") == 1
    assert (
        '<podcast:chapters url="http://podly.local/post/with/chapters.json" '
        'type="application/json+chapters"' in xml
    )


def test_chapter_routes_use_feed_token_auth(app: Any, tmp_path: Path) -> None:
    _, feed_id = _setup(app, tmp_path)
    assert _is_token_protected_endpoint("/post/with/chapters.json")
    assert _is_token_protected_endpoint("/post/with/chapter-images/0")
    with app.app_context():
        assert _resolve_feed_id("/post/with/chapters.json") == feed_id
        assert _resolve_feed_id("/post/with/chapter-images/3") == feed_id


def test_chapter_routes_hide_unwhitelisted_posts(app: Any, tmp_path: Path) -> None:
    client, _ = _setup(app, tmp_path)
    with app.app_context():
        post = Post.query.filter_by(guid="with").first()
        assert post is not None
        post.whitelisted = False
        db.session.commit()

    assert client.get("/post/with/chapters.json").status_code == 404
    assert client.get("/post/with/chapter-images/0").status_code == 404
