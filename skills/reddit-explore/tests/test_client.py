import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.client import Fetcher, _POST_PAGE_JS


class FakeItem(SimpleNamespace):
    pass


class FakeReddit:
    def __init__(self, submissions=None, comments=None):
        self._submissions = submissions or []
        self._comments = comments or []
        self.searched = []
        self.browsed = []

    def subreddit(self, name):
        class Sub:
            def __init__(_self, name, outer):
                _self.name = name
                _self._outer = outer

            def search(_self, query, sort=None, time_filter=None, limit=None):
                _self._outer.searched.append((_self.name, query, limit))
                return _self._outer._submissions[:limit]

            def hot(_self, limit=None):
                _self._outer.browsed.append((_self.name, "hot", limit))
                return _self._outer._submissions[:limit]

            def top(_self, limit=None, time_filter=None):
                _self._outer.browsed.append((_self.name, "top", time_filter))
                return _self._outer._submissions[:limit]

        return Sub(name, self)

    def submission(self, id):
        if not self._submissions:
            return None
        return self._submissions[0]

    def redditor(self, name):
        class Listing:
            def __init__(_self, items):
                _self._items = items

            def new(_self, limit=None):
                return _self._items[:limit]

            def hot(_self, limit=None):
                return list(reversed(_self._items[:limit]))

        return SimpleNamespace(
            overview=Listing(self._submissions + self._comments),
            submissions=Listing(self._submissions),
            comments=Listing(self._comments),
        )


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, headers=None, responses=None):
        self.headers = headers or {}
        self._responses = responses or []
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if self._responses:
            return FakeResponse(self._responses.pop(0))
        raise RuntimeError(f"Unexpected request: {url} {params}")


class FakePage:
    def __init__(self, responses):
        self._responses = responses
        self.visits = []

    def goto(self, url, **kwargs):
        self.visits.append(url)

    def evaluate(self, js, args=None):
        if args is None:
            return True
        assert js == _POST_PAGE_JS
        return self._responses


class FakeBrowserSession:
    def __init__(self, page):
        self.page = page

    def close(self):
        pass


def test_fetcher_from_existing_praw():
    fake = FakeReddit([])
    fetcher = Fetcher.from_existing(fake)
    assert fetcher.strategy == "praw"


def test_fetcher_from_existing_public():
    fake = FakeSession()
    fetcher = Fetcher.from_existing(fake)
    assert fetcher.strategy == "public"


def test_fetcher_from_existing_bearer():
    fake = FakeSession(headers={"Authorization": "Bearer token"})
    fetcher = Fetcher.from_existing(fake)
    assert fetcher.strategy == "bearer"


def test_fetcher_search_delegates_to_praw():
    class Fake:
        def subreddit(self, name):
            class Sub:
                def search(self, **kwargs):
                    return [{"id": "p1"}]
            return Sub()

    fetcher = Fetcher.from_existing(Fake())
    result = fetcher.search("test", limit=1)
    assert result == [{"id": "p1"}]


def test_subreddit_listing_praw_tolerates_dict_fakes():
    posts = [{"id": "p1", "title": "T", "subreddit": "test"}]
    fake = FakeReddit(submissions=posts)
    fetcher = Fetcher.from_existing(fake)
    result = fetcher.subreddit_listing("test", sort="hot", limit=1)
    assert result == posts


def test_post_praw_tolerates_dict_fakes():
    post = {"id": "p1", "title": "Title", "selftext": "text", "subreddit": "test"}
    comments = [{"id": "c1", "body": "b1"}, {"id": "c2", "body": "b2"}]
    post_with_comments = {**post, "comments": comments}
    fake = FakeReddit(submissions=[post_with_comments])
    fetcher = Fetcher.from_existing(fake)
    returned_post, returned_comments = fetcher.post("p1", comment_limit=2)
    assert returned_post["id"] == "p1"
    assert returned_post["title"] == "Title"
    assert returned_comments == comments


@pytest.mark.parametrize("section,sort,expected", [
    ("overview", "new", [("t3", "p1"), ("t1", "c1")]),
    ("overview", "hot", [("t1", "c1"), ("t3", "p1")]),
    ("submitted", "new", [("t3", "p1")]),
    ("comments", "new", [("t1", "c1")]),
])
def test_user_praw_delegates_to_listing_methods(section, sort, expected):
    post = FakeItem(
        id="p1",
        title="Post",
        selftext="hello",
        subreddit="test",
        author="a1",
        score=5,
        url="https://example.com",
        permalink="/r/test/comments/p1/t/",
    )
    comment = FakeItem(
        id="c1",
        body="comment",
        author="a2",
        score=2,
        subreddit="test",
        link_id="t3_p1",
        permalink="/r/test/comments/p1/t/c1",
    )
    fake = FakeReddit(submissions=[post], comments=[comment])
    fetcher = Fetcher.from_existing(fake)
    result = fetcher.user("testuser", section=section, sort=sort, limit=10)
    assert [(r["kind"], r["data"]["id"]) for r in result] == expected


def _post_payloads():
    post_data = {
        "id": "abc",
        "title": "Title",
        "selftext": "body",
        "subreddit": "test",
        "author": "op",
        "score": 10,
        "url": "https://example.com",
        "permalink": "/r/test/comments/abc/t/",
    }
    comment1 = {
        "id": "c1",
        "body": "b1",
        "author": "u1",
        "score": 1,
        "permalink": "/r/test/comments/abc/t/c1",
    }
    comment2 = {
        "id": "c2",
        "body": "b2",
        "author": "u2",
        "score": 2,
        "permalink": "/r/test/comments/abc/t/c2",
    }
    comment3 = {
        "id": "c3",
        "body": "b3",
        "author": "u3",
        "score": 3,
        "permalink": "/r/test/comments/abc/t/c3",
    }
    info_response = {
        "kind": "Listing",
        "data": {
            "children": [{"kind": "t3", "data": post_data}],
        },
    }
    comments_response = [
        {"kind": "Listing", "data": {"children": [{"kind": "t3", "data": post_data}]}},
        {"kind": "Listing", "data": {"children": [
            {"kind": "t1", "data": comment1},
            {"kind": "t1", "data": comment2},
            {"kind": "t1", "data": comment3},
        ]}},
    ]
    return post_data, info_response, comments_response, [comment1, comment2, comment3]


def test_post_public_fetches_info_then_comments():
    post_data, info_response, comments_response, all_comments = _post_payloads()
    session = FakeSession(responses=[info_response, comments_response])
    fetcher = Fetcher.from_existing(session)
    assert fetcher.strategy == "public"

    post, comments = fetcher.post("abc", comment_limit=2, comment_sort="top")
    assert post == post_data
    assert comments == all_comments[:2]
    assert session.calls[0][0] == "https://www.reddit.com/api/info.json"
    assert session.calls[0][1] == {"id": "t3_abc"}
    assert session.calls[1][0] == "https://www.reddit.com/r/test/comments/abc/title.json"
    assert session.calls[1][1] == {"limit": 2, "sort": "top"}


def test_post_bearer_fetches_info_then_comments():
    post_data, info_response, comments_response, all_comments = _post_payloads()
    session = FakeSession(
        headers={"Authorization": "Bearer token"},
        responses=[info_response, comments_response],
    )
    fetcher = Fetcher.from_existing(session)
    assert fetcher.strategy == "bearer"

    post, comments = fetcher.post("abc", comment_limit=2)
    assert post == post_data
    assert comments == all_comments[:2]
    assert session.calls[0][0] == "https://oauth.reddit.com/api/info.json"
    assert session.calls[1][0] == "https://oauth.reddit.com/r/test/comments/abc/title.json"


def test_post_public_no_comments_skips_comments_fetch():
    post_data, info_response, _, _ = _post_payloads()
    session = FakeSession(responses=[info_response])
    fetcher = Fetcher.from_existing(session)
    post, comments = fetcher.post("abc", comment_limit=0)
    assert post == post_data
    assert comments == []
    assert len(session.calls) == 1


def test_post_browser_fetches_dom_post_and_comments():
    post_data, info_response, comments_response, all_comments = _post_payloads()
    page = FakePage({"post": post_data, "comments": all_comments})
    session = FakeBrowserSession(page)
    fetcher = Fetcher.from_existing(session)
    assert fetcher.strategy == "browser"

    post, comments = fetcher.post("abc", comment_limit=2, comment_sort="top")
    assert post == post_data
    assert comments == all_comments[:2]


@pytest.mark.parametrize("limit", [0, 1, 2])
def test_browser_comment_limit_on_fresh_and_cached_results(limit):
    post_data, _, _, all_comments = _post_payloads()
    page = FakePage({"post": post_data, "comments": all_comments})
    fetcher = Fetcher.from_existing(FakeBrowserSession(page))
    assert fetcher.post("abc", comment_limit=limit) == (post_data, all_comments[:limit])
    assert fetcher.post("abc", comment_limit=limit) == (post_data, all_comments[:limit])
    assert len(page.visits) == 1


def test_browser_comment_sort_navigation_and_cache():
    post_data, _, _, comments = _post_payloads()
    page = FakePage({"post": post_data, "comments": comments})
    fetcher = Fetcher.from_existing(FakeBrowserSession(page))
    fetcher.post("abc", comment_limit=2, comment_sort="top")
    page._responses = {"post": post_data, "comments": list(reversed(comments))}
    assert fetcher.post("abc", comment_limit=2, comment_sort="new")[1] == list(reversed(comments))[:2]
    assert fetcher.post("abc", comment_limit=2, comment_sort="top")[1] == comments[:2]
    assert page.visits == [
        "https://www.reddit.com/comments/abc/?sort=top",
        "https://www.reddit.com/comments/abc/?sort=new",
    ]


@pytest.mark.parametrize("post", [None, {}])
def test_browser_missing_post_is_not_cached(post):
    page = FakePage({"post": post, "comments": []})
    fetcher = Fetcher.from_existing(FakeBrowserSession(page))
    with pytest.raises(LookupError, match="Could not fetch post abc"):
        fetcher.post("abc")
    assert fetcher._post_cache == {}
    page._responses = {"post": {"title": "Recovered"}, "comments": []}
    assert fetcher.post("abc")[0] == {"id": "abc", "title": "Recovered"}
