import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import interactor


# --- normalize_thing_id tests ---

def test_normalize_post_id_from_url():
    assert interactor.normalize_thing_id(
        "https://www.reddit.com/r/test/comments/abc123/title_here/", "post"
    ) == "t3_abc123"


def test_normalize_post_id_from_permalink():
    assert interactor.normalize_thing_id("/r/test/comments/abc123/title/", "post") == "t3_abc123"


def test_normalize_post_id_bare():
    assert interactor.normalize_thing_id("abc123", "post") == "t3_abc123"


def test_normalize_post_id_already_prefixed():
    assert interactor.normalize_thing_id("t3_abc123", "post") == "t3_abc123"


def test_normalize_comment_id_from_url():
    assert interactor.normalize_thing_id(
        "https://www.reddit.com/r/test/comments/abc123/title/def456/", "comment"
    ) == "t1_def456"


def test_normalize_comment_id_bare():
    assert interactor.normalize_thing_id("def456", "comment") == "t1_def456"


def test_normalize_comment_id_already_prefixed():
    assert interactor.normalize_thing_id("t1_def456", "comment") == "t1_def456"


def test_normalize_cross_kind_prefix_preserved():
    assert interactor.normalize_thing_id("t1_abc123", "post") == "t1_abc123"
    assert interactor.normalize_thing_id("t3_abc123", "comment") == "t3_abc123"


def test_normalize_comment_id_from_url_without_title_slug():
    assert interactor.normalize_thing_id(
        "/r/test/comments/abc123/def456/", "comment"
    ) == "t1_def456"


# --- detect_kind tests ---

def test_detect_kind_t1_prefix():
    assert interactor.detect_kind("t1_abc123") == "comment"


def test_detect_kind_t3_prefix():
    assert interactor.detect_kind("t3_abc123") == "post"


def test_detect_kind_bare_id_defaults_to_post():
    assert interactor.detect_kind("abc123") == "post"


def test_detect_kind_standard_comment_url():
    assert interactor.detect_kind(
        "https://www.reddit.com/r/test/comments/abc123/title/def456/"
    ) == "comment"


def test_detect_kind_post_url():
    assert interactor.detect_kind(
        "https://www.reddit.com/r/test/comments/abc123/title/"
    ) == "post"


# --- Interactor method tests ---

def _make_fake_session(responses):
    """Build a fake session whose page.evaluate returns canned responses by URL."""
    class FakePage:
        def evaluate(self, script, arg=None):
            url = arg[0] if isinstance(arg, list) else ""
            for pattern, body in responses:
                if pattern in url:
                    return {"ok": True, "status": 200, "body": body}
            return {"ok": True, "status": 200, "body": "{}"}

    class FakeSession:
        page = FakePage()

        def close(self):
            pass

    return FakeSession()


def test_comment(monkeypatch):
    session = _make_fake_session([
        ("/api/me.json", '{"name": "testuser", "modhash": "abc"}'),
        ("/api/comment", '{"json": {"data": {"things": [{"data": {"id": "c1", "permalink": "/r/test/comments/abc/title/c1"}}]}}}'),
    ])
    i = interactor.Interactor(session)
    result = i.comment("t3_abc", "Hello world")
    assert result["comment_id"] == "c1"
    assert "permalink" in result


def test_reply(monkeypatch):
    session = _make_fake_session([
        ("/api/me.json", '{"name": "testuser", "modhash": "abc"}'),
        ("/api/comment", '{"json": {"data": {"things": [{"data": {"id": "c2", "permalink": "/r/test/comments/abc/title/c2"}}]}}}'),
    ])
    i = interactor.Interactor(session)
    result = i.reply("t1_c1", "Reply text")
    assert result["comment_id"] == "c2"


def test_reply_rejects_non_t1_prefix():
    session = _make_fake_session([])
    i = interactor.Interactor(session)
    with pytest.raises(ValueError, match="reply expects a comment fullname"):
        i.reply("t3_abc", "text")


def test_vote(monkeypatch):
    session = _make_fake_session([
        ("/api/me.json", '{"name": "testuser", "modhash": "abc"}'),
        ("/api/vote", '{"json": {}}'),
    ])
    i = interactor.Interactor(session)
    result = i.vote("t3_abc", 1)
    assert result["action"] == "vote"
    assert result["direction"] == 1


def test_vote_detects_api_error():
    session = _make_fake_session([
        ("/api/me.json", '{"name": "testuser", "modhash": "abc"}'),
        ("/api/vote", '{"json": {"errors": [["RATELIMIT", "you are doing that too much"]]}}'),
    ])
    i = interactor.Interactor(session)
    with pytest.raises(RuntimeError, match="Reddit rejected vote"):
        i.vote("t3_abc", 1)


def test_save(monkeypatch):
    session = _make_fake_session([
        ("/api/me.json", '{"name": "testuser", "modhash": "abc"}'),
        ("/api/save", '{"json": {}}'),
    ])
    i = interactor.Interactor(session)
    result = i.save("t3_abc")
    assert result["action"] == "save"
    assert result["thing_id"] == "t3_abc"


def test_save_detects_api_error():
    session = _make_fake_session([
        ("/api/me.json", '{"name": "testuser", "modhash": "abc"}'),
        ("/api/save", '{"json": {"errors": [["FORBIDDEN", "not allowed"]]}}'),
    ])
    i = interactor.Interactor(session)
    with pytest.raises(RuntimeError, match="Reddit rejected save"):
        i.save("t3_abc")


def test_unsave(monkeypatch):
    session = _make_fake_session([
        ("/api/me.json", '{"name": "testuser", "modhash": "abc"}'),
        ("/api/unsave", '{"json": {}}'),
    ])
    i = interactor.Interactor(session)
    result = i.unsave("t3_abc")
    assert result["action"] == "unsave"
    assert result["thing_id"] == "t3_abc"


def test_unsave_detects_api_error():
    session = _make_fake_session([
        ("/api/me.json", '{"name": "testuser", "modhash": "abc"}'),
        ("/api/unsave", '{"json": {"errors": [["NOTFOUND", "thing not found"]]}}'),
    ])
    i = interactor.Interactor(session)
    with pytest.raises(RuntimeError, match="Reddit rejected unsave"):
        i.unsave("t3_abc")


def test_post_json_raises_on_non_json_response():
    class FakePage:
        def evaluate(self, script, arg=None):
            return {"ok": True, "status": 200, "body": "<html>Server Error</html>"}

    class FakeSession:
        page = FakePage()

        def close(self):
            pass

    i = interactor.Interactor(FakeSession())
    i._modhash = "abc"
    with pytest.raises(RuntimeError, match="non-JSON response"):
        i._post_json("/api/vote", {"id": "t3_abc", "dir": "1"})
