import importlib.util
import sys
from pathlib import Path


def _explore_package_dir():
    return Path(__file__).resolve().parent.parent.parent / "reddit-explore" / "pipeline"


def _load_explore_package():
    """Register reddit-explore's pipeline/ as a package so its relative imports resolve."""
    pkg_name = "reddit_explore_pipeline"
    pkg = sys.modules.get(pkg_name)
    if pkg is None:
        pkg_dir = _explore_package_dir()
        spec = importlib.util.spec_from_file_location(
            pkg_name,
            pkg_dir / "__init__.py",
            submodule_search_locations=[str(pkg_dir)],
        )
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[pkg_name] = pkg
        spec.loader.exec_module(pkg)
    return pkg


def _load_explorer():
    """Load the reddit-explore pipeline module from the sibling skill directory."""
    pkg = _load_explore_package()
    fullname = f"{pkg.__name__}.explorer"
    explorer = sys.modules.get(fullname)
    if explorer is None:
        explorer_path = _explore_package_dir() / "explorer.py"
        spec = importlib.util.spec_from_file_location(fullname, explorer_path)
        explorer = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = explorer
        spec.loader.exec_module(explorer)
    return explorer


def _load_client():
    """Load the reddit-explore client module."""
    pkg = _load_explore_package()
    fullname = f"{pkg.__name__}.client"
    client = sys.modules.get(fullname)
    if client is None:
        client_path = _explore_package_dir() / "client.py"
        spec = importlib.util.spec_from_file_location(fullname, client_path)
        client = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = client
        spec.loader.exec_module(client)
    return client


def scrape(idea, profile, client=None, subreddits=None):
    """Scrape Reddit for idea validation using reddit-explore's search primitive."""
    explorer = _load_explorer()
    client_mod = _load_client()

    fetcher = None
    close_after = False
    if client is not None:
        fetcher = client_mod.Fetcher.from_existing(client)
    else:
        fetcher = client_mod.get_fetcher()
        close_after = True

    try:
        limit = profile.get("subreddits", 5) * profile.get("posts_per_subreddit", 25)
        if subreddits:
            limit = profile.get("posts_per_subreddit", 25)
        records = explorer.search_posts(
            idea,
            fetcher=fetcher,
            subreddits=subreddits,
            limit=limit,
            sort="relevance",
            time_filter="all",
            fetch_comments=True,
            comment_limit=3,
        )
        return records
    finally:
        if close_after:
            fetcher.close()
