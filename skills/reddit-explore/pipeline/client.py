import importlib.util
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import requests


PUBLIC_BASE = "https://www.reddit.com"
OAUTH_BASE = "https://oauth.reddit.com"

# --- Browser DOM extraction -------------------------------------------------
# Reddit's .json endpoints now return 403 even for logged-in sessions, so the
# browser strategy scrapes the shreddit DOM instead: `shreddit-post` /
# `shreddit-comment` custom elements carry every field as attributes, and
# search results live inside `search-telemetry-tracker[data-thingid]` cards.

_SEARCH_RESULTS_JS = """() => {
    const seen = new Set();
    const out = [];
    for (const t of document.querySelectorAll('search-telemetry-tracker[data-thingid]')) {
        const thingid = t.getAttribute('data-thingid') || '';
        if (!thingid.startsWith('t3_') || seen.has(thingid)) continue;
        const link = t.querySelector('a[href*="/comments/"]');
        if (!link) continue;
        seen.add(thingid);
        const titleEl = t.querySelector('a[id^="search-post-title"], h2 a') || link;
        out.push({
            id: thingid.slice(3),
            title: (titleEl.textContent || '').trim(),
            permalink: link.getAttribute('href'),
        });
    }
    return out;
}"""

_POST_PAGE_JS = """(commentLimit) => {
    const p = document.querySelector('shreddit-post');
    const bodyEl = p
        ? p.querySelector('[id$="-post-rtjson-content"], [data-testid="post-content"], div.md')
        : null;
    const post = p ? {
        id: (p.getAttribute('id') || '').replace(/^t3_/, ''),
        title: p.getAttribute('post-title') || document.title || '',
        author: p.getAttribute('author') || '',
        score: parseInt(p.getAttribute('score') || '0', 10) || 0,
        permalink: p.getAttribute('permalink') || location.pathname,
        subreddit: (p.getAttribute('subreddit-name') || '').replace(/^r\\//, ''),
        url: p.getAttribute('content-href') || '',
        selftext: bodyEl ? bodyEl.innerText.trim() : '',
    } : null;
    const comments = Array.from(document.querySelectorAll('shreddit-comment'))
        .slice(0, commentLimit || 0)
        .map(c => {
            const body = c.querySelector('[id$="-comment-rtjson-content"]');
            return {
                id: (c.getAttribute('thingid') || '').replace(/^t1_/, ''),
                body: (body ? body.innerText : c.innerText || '').trim(),
                author: c.getAttribute('author') || '',
                score: parseInt(c.getAttribute('score') || '0', 10) || 0,
                permalink: c.getAttribute('permalink') || '',
            };
        });
    return {post, comments};
}"""

_LISTING_RESULTS_JS = """() => Array.from(document.querySelectorAll('shreddit-post')).map(p => ({
    id: (p.getAttribute('id') || '').replace(/^t3_/, ''),
    title: p.getAttribute('post-title') || '',
    author: p.getAttribute('author') || '',
    score: parseInt(p.getAttribute('score') || '0', 10) || 0,
    permalink: p.getAttribute('permalink') || '',
    subreddit: (p.getAttribute('subreddit-name') || '').replace(/^r\\//, ''),
    url: p.getAttribute('content-href') || '',
    selftext: '',
}))"""


def _subreddit_from_permalink(permalink: str) -> str:
    parts = [p for p in (permalink or "").split("/") if p]
    if "r" in parts:
        idx = parts.index("r")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def _load_auth():
    """Load the reddit-auth pipeline module from the sibling skill directory."""
    auth_path = Path(__file__).resolve().parent.parent.parent / "reddit-auth" / "pipeline" / "auth.py"
    spec = importlib.util.spec_from_file_location("reddit_auth_pipeline_auth", auth_path)
    auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(auth)
    return auth


class Fetcher:
    """Uniform Reddit JSON fetcher across all auth strategies."""

    def __init__(self, strategy: str, client):
        self.strategy = strategy
        self._client = client
        # post_id -> (post_dict, comments_list); hydrated once per page visit.
        self._post_cache: dict = {}

    @classmethod
    def from_existing(cls, client) -> "Fetcher":
        """Wrap an already-open reddit-auth client (Session, requests.Session, or praw.Reddit)."""
        if hasattr(client, "page"):
            return cls("browser", client)
        if hasattr(client, "headers") and client.headers.get("Authorization"):
            return cls("bearer", client)
        if hasattr(client, "subreddit"):
            return cls("praw", client)
        return cls("public", client)

    @classmethod
    def create(cls) -> "Fetcher":
        """Create a new Fetcher from the active auth strategy."""
        auth = _load_auth()
        strategy = auth.resolve_strategy()

        if strategy == "browser":
            session = auth.ensure_authenticated_page()
            return cls("browser", session)

        if strategy == "bearer":
            token = auth.bearer_token()
            if not token:
                raise RuntimeError("No bearer token could be parsed from REDDIT_CLIENT_SECRET")
            session = requests.Session()
            session.headers.update({
                "Authorization": f"Bearer {token}",
                "User-Agent": auth.user_agent(),
            })
            return cls("bearer", session)

        if strategy == "praw":
            try:
                from praw import Reddit
            except ImportError as exc:
                raise RuntimeError("praw not installed") from exc
            return cls("praw", auth.get_client("praw"))

        session = requests.Session()
        session.headers.update({"User-Agent": auth.user_agent()})
        return cls("public", session)

    def _browser_fetch(self, path: str, params: Optional[dict] = None) -> dict:
        page = self._client.page
        return _load_auth().fetch_json(page, PUBLIC_BASE, f"{path}.json", params)

    # -- Browser DOM scraping -------------------------------------------------

    def _dom_goto(self, url: str, timeout: int = 30000) -> None:
        self._client.page.goto(url, wait_until="load", timeout=timeout)

    def _dom_wait_content(self, timeout_s: float = 15.0) -> bool:
        """Poll until a shreddit page has rendered post/comment/search content."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._client.page.evaluate(
                "() => document.querySelectorAll("
                "'shreddit-post, shreddit-comment, search-telemetry-tracker[data-thingid]'"
                ").length > 0"
            ):
                return True
            time.sleep(0.5)
        return False

    def _dom_post_page(self, permalink_or_id: str, comment_limit: int = 0):
        """Visit a comments page once; cache post + comments by post id."""
        post_id = self._normalize_post_id(permalink_or_id)
        cached = self._post_cache.get(post_id)
        if cached and len(cached[1]) >= comment_limit:
            return cached[0], cached[1][:comment_limit] if comment_limit else cached[1]

        if permalink_or_id.startswith("/"):
            url = f"{PUBLIC_BASE}{permalink_or_id}"
        elif permalink_or_id.startswith("http"):
            url = permalink_or_id
        else:
            url = f"{PUBLIC_BASE}/comments/{post_id}/"
        self._dom_goto(url)
        self._dom_wait_content()
        data = self._client.page.evaluate(_POST_PAGE_JS, comment_limit or 0)
        post = data.get("post") or {}
        post.setdefault("id", post_id)
        comments = data.get("comments") or []
        self._post_cache[post_id] = (post, comments)
        return post, comments[:comment_limit] if comment_limit else comments

    def _requests_get(self, url: str, params: Optional[dict] = None, timeout: int = 15) -> dict:
        response = self._client.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def _extract_children(self, data: dict) -> list[dict]:
        """Extract data children from a Reddit listing or mixed listing."""
        if isinstance(data, list):
            return data
        children = data.get("data", {}).get("children", [])
        return [child.get("data", child) if isinstance(child, dict) else child for child in children]

    @staticmethod
    def _extract_user_items(data) -> list[dict]:
        """Return user listing children with their kind wrappers intact."""
        if isinstance(data, list):
            return data
        return data.get("data", {}).get("children", [])

    def search(self, query, *, subreddit=None, limit=25, sort="relevance", time_filter="all") -> list[dict]:
        """Return raw post dicts for a search query."""
        if self.strategy == "praw":
            sub_name = subreddit or "all"
            subs = self._client.subreddit(sub_name)
            results = subs.search(query=query, sort=sort, time_filter=time_filter, limit=limit)
            return [s if isinstance(s, dict) else {
                "id": s.id, "title": s.title, "selftext": s.selftext, "subreddit": str(s.subreddit),
                "author": str(s.author), "score": s.score, "url": s.url, "permalink": s.permalink,
            } for s in results]

        if self.strategy == "browser":
            search_path = f"/r/{subreddit}/search/" if subreddit else "/search/"
            qs = urllib.parse.urlencode({
                "q": query, "type": "link", "sort": sort, "t": time_filter,
                **({"restrict_sr": "1"} if subreddit else {}),
            })
            page = self._client.page
            self._dom_goto(f"{PUBLIC_BASE}{search_path}?{qs}")
            self._dom_wait_content()
            # Results lazy-load on scroll — keep scrolling until enough cards
            # render or the feed stops growing.
            results = []
            stagnant = 0
            while len(results) < limit and stagnant < 3:
                before = len(results)
                page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)
                results = page.evaluate(_SEARCH_RESULTS_JS)
                stagnant = stagnant + 1 if len(results) <= before else 0
            posts = [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "permalink": r["permalink"],
                    "subreddit": _subreddit_from_permalink(r["permalink"]),
                    "author": "",
                    "score": 0,
                    "url": urllib.parse.urljoin(PUBLIC_BASE, r["permalink"]),
                }
                for r in results[:limit]
            ]
            # Hydrate each post from its comments page — fills selftext/author/
            # score and primes the comment cache for `post()` calls.
            for p in posts:
                try:
                    full, _ = self._dom_post_page(p["permalink"], comment_limit=3)
                    p.update(full)
                except Exception:
                    continue
                time.sleep(0.8)
            return posts

        search_path = f"/r/{subreddit}/search" if subreddit else "/r/all/search"
        base = OAUTH_BASE if self.strategy == "bearer" else PUBLIC_BASE
        data = self._requests_get(
            f"{base}{search_path}.json",
            params={"q": query, "sort": sort, "t": time_filter, "limit": min(limit, 100)},
        )
        return self._extract_children(data)

    def subreddit_listing(self, name, *, sort="hot", limit=25, time_filter="all") -> list[dict]:
        """Return raw post dicts for a subreddit listing."""
        if sort == "rising":
            sort = "hot"

        if self.strategy == "praw":
            sub = self._client.subreddit(name)
            method = getattr(sub, sort, sub.hot)
            kwargs = {"limit": limit}
            if sort == "top" and time_filter:
                kwargs["time_filter"] = time_filter
            results = method(**kwargs)
            return [s if isinstance(s, dict) else {
                "id": s.id, "title": s.title, "selftext": s.selftext, "subreddit": str(s.subreddit),
                "author": str(s.author), "score": s.score, "url": s.url, "permalink": s.permalink,
            } for s in results]

        if self.strategy == "browser":
            qs = f"?t={time_filter}" if sort in ("top", "controversial") else ""
            page = self._client.page
            self._dom_goto(f"{PUBLIC_BASE}/r/{name}/{sort}/{qs}")
            self._dom_wait_content()
            stagnant = 0
            results = []
            while len(results) < limit and stagnant < 3:
                before = len(results)
                page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)
                results = page.evaluate(_LISTING_RESULTS_JS)
                stagnant = stagnant + 1 if len(results) <= before else 0
            return results[:limit]

        base = OAUTH_BASE if self.strategy == "bearer" else PUBLIC_BASE
        params = {"limit": min(limit, 100)}
        if time_filter and sort in ("top", "controversial"):
            params["t"] = time_filter
        data = self._requests_get(f"{base}/r/{name}/{sort}.json", params=params)
        return self._extract_children(data)

    def post(self, permalink_or_id, *, comment_limit=0, comment_sort="top") -> tuple[dict, list[dict]]:
        """Return (post_dict, comments_list). comment_limit=0 skips comments."""
        post_id = self._normalize_post_id(permalink_or_id)

        if self.strategy == "praw":
            submission = self._client.submission(id=post_id)
            if isinstance(submission, dict):
                post = submission
            else:
                post = {"id": submission.id, "title": submission.title, "selftext": submission.selftext,
                        "subreddit": str(submission.subreddit), "author": str(submission.author),
                        "score": submission.score, "url": submission.url, "permalink": submission.permalink}
            comments = []
            if comment_limit:
                if isinstance(submission, dict):
                    raw_comments = submission.get("comments", [])
                else:
                    submission.comments.replace_more(limit=0)
                    raw_comments = submission.comments.list()
                for c in raw_comments[:comment_limit]:
                    comments.append(c if isinstance(c, dict) else {
                        "id": c.id, "body": c.body, "author": str(c.author),
                        "score": c.score, "permalink": c.permalink,
                    })
            return post, comments

        def _extract_post(info):
            posts = self._extract_children(info)
            if not posts:
                raise LookupError(f"Could not fetch post {post_id}")
            return posts[0]

        if self.strategy == "browser":
            return self._dom_post_page(permalink_or_id, comment_limit=comment_limit)

        base = OAUTH_BASE if self.strategy == "bearer" else PUBLIC_BASE
        info = self._requests_get(f"{base}/api/info.json", params={"id": f"t3_{post_id}"})
        post = _extract_post(info)
        comments = []
        if comment_limit:
            subreddit = self._subreddit_name(post)
            data = self._requests_get(f"{base}/r/{subreddit}/comments/{post_id}/title.json",
                                      params={"limit": comment_limit, "sort": comment_sort})
            if isinstance(data, list) and len(data) >= 2:
                comments = self._extract_children(data[1])[:comment_limit]
        return post, comments

    def user(self, name, *, section="overview", limit=25, sort="new") -> list[dict]:
        """Return raw item dicts for a user profile section."""
        praw_section = section
        if section == "overview":
            section = "submitted"

        if self.strategy == "praw":
            redditor = self._client.redditor(name)
            if praw_section == "overview":
                listing = redditor.overview
            elif praw_section == "submitted":
                listing = redditor.submissions
            elif praw_section == "comments":
                listing = redditor.comments
            else:
                listing = redditor.overview
            sort_attr = sort if sort in ("new", "hot", "top", "controversial") else "hot"
            items = getattr(listing, sort_attr)(limit=limit)
            result = []
            for item in items:
                if hasattr(item, "link_id"):
                    # comment
                    result.append({"kind": "t1", "data": {
                        "id": item.id, "link_id": item.link_id, "subreddit": str(item.subreddit),
                        "body": item.body, "author": str(item.author), "score": item.score,
                        "link_title": getattr(item, "link_title", ""), "permalink": item.permalink,
                    }})
                else:
                    result.append({"kind": "t3", "data": {
                        "id": item.id, "title": item.title, "selftext": item.selftext,
                        "subreddit": str(item.subreddit), "author": str(item.author),
                        "score": item.score, "url": item.url, "permalink": item.permalink,
                    }})
            return result

        if self.strategy == "browser":
            data = self._browser_fetch(f"/user/{name}/{section}", {"limit": min(limit, 100), "sort": sort})
            return self._extract_user_items(data)

        base = OAUTH_BASE if self.strategy == "bearer" else PUBLIC_BASE
        data = self._requests_get(f"{base}/user/{name}/{section}.json",
                                  params={"limit": min(limit, 100), "sort": sort})
        return self._extract_user_items(data)

    def close(self) -> None:
        if hasattr(self._client, "close"):
            self._client.close()

    @staticmethod
    def _normalize_post_id(value: str) -> str:
        """Accept full URL, permalink, or id (with or without t3_ prefix)."""
        value = value.strip()
        if value.startswith("http"):
            # extract id from url like .../comments/ID/...
            parts = [p for p in value.split("/") if p]
            if "comments" in parts:
                idx = parts.index("comments")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
        parts = [p for p in value.split("/") if p]
        if parts and parts[0].lower() == "r":
            if "comments" in parts:
                idx = parts.index("comments")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
        return value.removeprefix("t3_")

    @staticmethod
    def _subreddit_name(post: dict) -> str:
        """Return a URL-safe subreddit display name from a post dict."""
        sub = post.get("subreddit") or ""
        if sub.startswith("r/"):
            sub = sub[2:]
        if sub:
            return sub
        permalink = post.get("permalink") or ""
        parts = [p for p in permalink.split("/") if p]
        if "r" in parts:
            idx = parts.index("r")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        raise LookupError("Could not determine subreddit for post")


def get_fetcher() -> Fetcher:
    return Fetcher.create()
