import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.scraper import scrape


class FakeFetcher:
    def __init__(self, posts=None, comments=None):
        self._posts = posts or []
        self._comments = comments or []
        self.search_calls = []
        self.post_calls = []

    def search(self, query, **kwargs):
        self.search_calls.append((query, kwargs))
        return self._posts

    def post(self, permalink_or_id, **kwargs):
        self.post_calls.append((permalink_or_id, kwargs))
        return (self._posts[0], self._comments) if self._posts else ({}, [])

    def close(self):
        pass


class FakeExplorer:
    def __init__(self, records):
        self._records = records
        self.calls = []

    def search_posts(self, idea, *, fetcher, **kwargs):
        self.calls.append((idea, kwargs))
        if fetcher is not None:
            fetcher.search(idea, **kwargs)
        return self._records


def _patch_scraper(monkeypatch, records, fetcher=None):
    from pipeline import scraper

    def fake_load_explorer():
        return FakeExplorer(records)

    def fake_load_client():
        class FakeClient:
            @staticmethod
            def get_fetcher():
                return fetcher or FakeFetcher()

            class Fetcher:
                @staticmethod
                def from_existing(client):
                    return fetcher or FakeFetcher()

        return FakeClient()

    monkeypatch.setattr(scraper, "_load_explorer", fake_load_explorer)
    monkeypatch.setattr(scraper, "_load_client", fake_load_client)


def test_scrape_returns_records(monkeypatch):
    records = [
        {"is_comment": True, "title": "Best app for X?", "text": "I need this"},
        {"is_comment": False, "title": "Best app for X?", "text": "Looking for ..."},
    ]
    _patch_scraper(monkeypatch, records)
    result = scrape("app for X", {"subreddits": 1, "posts_per_subreddit": 1})
    assert len(result) == 2
    assert result[0]["is_comment"] is True
    assert result[1]["is_comment"] is False


def test_scrape_targets_specific_subreddits(monkeypatch):
    records = [
        {"is_comment": False, "title": "IELTS speaking practice"},
        {"is_comment": False, "title": "IELTS speaking practice"},
    ]
    fetcher = FakeFetcher()
    explorer = FakeExplorer(records)

    from pipeline import scraper

    def fake_load_explorer():
        return explorer

    monkeypatch.setattr(scraper, "_load_explorer", fake_load_explorer)
    monkeypatch.setattr(scraper, "_load_client", lambda: type(
        "FakeClient", (), {"get_fetcher": lambda: fetcher, "Fetcher": type(
            "Fetcher", (), {"from_existing": classmethod(lambda cls, client: fetcher)}
        )}
    )())

    result = scrape(
        "AI IELTS grading",
        {"posts_per_subreddit": 5},
        client=object(),
        subreddits="IELTS,TOEFL",
    )
    assert len(result) == 2
    assert len(explorer.calls) == 1
    assert explorer.calls[0][1]["subreddits"] == "IELTS,TOEFL"


def test_scrape_without_subreddits_searches_all(monkeypatch):
    records = [{"is_comment": False, "title": "test"}]
    fetcher = FakeFetcher()
    explorer = FakeExplorer(records)

    from pipeline import scraper

    def fake_load_explorer():
        return explorer

    monkeypatch.setattr(scraper, "_load_explorer", fake_load_explorer)
    monkeypatch.setattr(scraper, "_load_client", lambda: type(
        "FakeClient", (), {"get_fetcher": lambda: fetcher, "Fetcher": type(
            "Fetcher", (), {"from_existing": classmethod(lambda cls, client: fetcher)}
        )}
    )())

    scrape("test idea", {"subreddits": 1, "posts_per_subreddit": 1}, client=object())
    assert len(explorer.calls) == 1
    assert explorer.calls[0][1]["subreddits"] is None


@pytest.mark.parametrize("loader_name,module_name", [
    ("_load_explore_package", "reddit_explore_pipeline"),
    ("_load_explorer", "reddit_explore_pipeline.explorer"),
    ("_load_client", "reddit_explore_pipeline.client"),
])
def test_failed_module_load_cleans_registration_and_can_retry(monkeypatch, tmp_path, loader_name, module_name):
    from pipeline import scraper

    for name in ("reddit_explore_pipeline", "reddit_explore_pipeline.explorer", "reddit_explore_pipeline.client"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(scraper, "_explore_package_dir", lambda: tmp_path)
    for filename in ("__init__.py", "explorer.py", "client.py"):
        (tmp_path / filename).write_text("")
    target = tmp_path / {"_load_explore_package": "__init__.py", "_load_explorer": "explorer.py", "_load_client": "client.py"}[loader_name]
    target.write_text('raise RuntimeError("failed import")\n')
    loader = getattr(scraper, loader_name)
    try:
        with pytest.raises(RuntimeError, match="failed import"):
            loader()
        assert module_name not in sys.modules
        target.write_text('ready = True\n')
        loaded = loader()
        assert loaded.ready
        assert sys.modules[module_name] is loaded
        assert loader() is loaded
    finally:
        for name in ("reddit_explore_pipeline", "reddit_explore_pipeline.explorer", "reddit_explore_pipeline.client"):
            sys.modules.pop(name, None)
