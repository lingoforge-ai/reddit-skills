from .client import Fetcher, get_fetcher  # noqa: F401
from .records import comment_record, post_record, user_record


def _normalize_subreddits(subreddits):
    """Accept 'IELTS', 'r/IELTS', ' IELTS,TOEFL ' → ['IELTS', 'TOEFL']."""
    if not subreddits:
        return []
    if isinstance(subreddits, str):
        subreddits = subreddits.split(",")
    return [s.strip().lstrip("r/").strip() for s in subreddits if s.strip()]


def _fetch_comments(fetcher, post, limit, sort):
    """Fetch top comments for a post."""
    if not limit or not post.get("permalink"):
        return []
    _, comments = fetcher.post(post["permalink"], comment_limit=limit, comment_sort=sort)
    return comments


def search_posts(
    query: str,
    *,
    fetcher: Fetcher,
    subreddits=None,
    limit: int = 25,
    sort: str = "relevance",
    time_filter: str = "all",
    fetch_comments: bool = False,
    comment_limit: int = 3,
    comment_sort: str = "top",
) -> list[dict]:
    """Keyword search across all of Reddit or specific subreddits."""
    subs = _normalize_subreddits(subreddits)
    records = []

    if subs:
        per_sub = max(1, limit) if limit else 25
        for sub in subs:
            raw_posts = fetcher.search(
                query=query, subreddit=sub, limit=per_sub, sort=sort, time_filter=time_filter
            )
            for post in raw_posts[:per_sub]:
                records.append(post_record(post))
                if fetch_comments:
                    for comment in _fetch_comments(fetcher, post, comment_limit, comment_sort):
                        records.append(comment_record(post, comment))
        return records

    raw_posts = fetcher.search(query=query, limit=limit, sort=sort, time_filter=time_filter)
    for post in raw_posts[:limit]:
        records.append(post_record(post))
        if fetch_comments:
            for comment in _fetch_comments(fetcher, post, comment_limit, comment_sort):
                records.append(comment_record(post, comment))
    return records


def list_subreddit(
    name: str,
    *,
    fetcher: Fetcher,
    sort: str = "hot",
    limit: int = 25,
    time_filter: str = "all",
    fetch_comments: bool = False,
    comment_limit: int = 3,
    comment_sort: str = "top",
) -> list[dict]:
    """Browse a subreddit's listing."""
    records = []
    raw_posts = fetcher.subreddit_listing(name=name, sort=sort, limit=limit, time_filter=time_filter)
    for post in raw_posts[:limit]:
        records.append(post_record(post))
        if fetch_comments:
            for comment in _fetch_comments(fetcher, post, comment_limit, comment_sort):
                records.append(comment_record(post, comment))
    return records


def get_post(
    permalink_or_id: str,
    *,
    fetcher: Fetcher,
    comment_limit: int = 10,
    comment_sort: str = "top",
) -> list[dict]:
    """Fetch a single post and its comment tree."""
    post, comments = fetcher.post(permalink_or_id, comment_limit=comment_limit, comment_sort=comment_sort)
    records = [post_record(post)]
    for comment in comments:
        records.append(comment_record(post, comment))
    return records


def get_user(
    name: str,
    *,
    fetcher: Fetcher,
    section: str = "overview",
    limit: int = 25,
    sort: str = "new",
) -> list[dict]:
    """Fetch a user's profile section."""
    raw_items = fetcher.user(name, section=section, limit=limit, sort=sort)
    return [user_record(item) for item in raw_items[:limit]]
