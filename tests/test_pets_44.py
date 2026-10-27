# -*- coding: utf-8 -*-
from research.pets_social_sources import fetch_public_telegram_preview


class _Response:
    status_code = 200
    content = b"<html>fixture</html>"
    text = '''
    <div class="tgme_widget_message" data-post="demo_channel/42">
      <time datetime="2026-10-26T10:00:00+00:00"></time>
      <div class="tgme_widget_message_text">  Useful   thought   about a dog. </div>
      <a class="tgme_widget_message_photo_wrap"></a>
    </div>'''


class _Session:
    def get(self, url, **kwargs):
        assert url == "https://t.me/s/demo_channel"
        assert kwargs["timeout"] == 20
        return _Response()


def test_public_preview_returns_short_metadata_only():
    records, diagnostic = fetch_public_telegram_preview("demo_channel", session=_Session())
    assert diagnostic["retrieval_status"] == "success"
    assert diagnostic["posts_returned"] == 1
    assert records == [{
        "platform": "telegram", "source_name": "demo_channel",
        "post_url": "https://t.me/demo_channel/42", "published_at": "2026-10-26T10:00:00+00:00",
        "text_excerpt": "Useful thought about a dog.", "text_available": True,
        "image_available": True, "topic": "unclassified", "retrieval_status": "success",
    }]


def test_public_preview_rejects_unbounded_collection():
    try:
        fetch_public_telegram_preview("demo_channel", limit=11, session=_Session())
    except ValueError as exc:
        assert "1..10" in str(exc)
    else:
        raise AssertionError("bounded limit must be enforced")
