import importlib.util
import json
import time
import urllib.parse
from pathlib import Path


PUBLIC_BASE = "https://www.reddit.com"


def _load_auth():
    auth_path = Path(__file__).resolve().parent.parent.parent / "reddit-auth" / "pipeline" / "auth.py"
    spec = importlib.util.spec_from_file_location("reddit_auth_pipeline_auth", auth_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def normalize_thing_id(value: str, kind: str) -> str:
    """Normalize a URL, permalink, or bare ID into a Reddit fullname.

    kind is "post" (→ t3_) or "comment" (→ t1_).
    """
    value = value.strip()
    prefix = "t3_" if kind == "post" else "t1_"

    if value.startswith(("t3_", "t1_")):
        return value

    if value.startswith("http") or value.startswith("/r/"):
        parts = [p for p in value.split("/") if p]
        if "comments" in parts:
            idx = parts.index("comments")
            if kind == "post" and idx + 1 < len(parts):
                return f"t3_{parts[idx + 1]}"
            if kind == "comment" and idx + 3 < len(parts):
                return f"t1_{parts[idx + 3]}"
            if kind == "comment" and idx + 2 < len(parts):
                return f"t1_{parts[idx + 2]}"

    return f"{prefix}{value}"


def detect_kind(value: str) -> str:
    """Detect whether a URL/ID refers to a post or a comment.

    Returns "post" or "comment".
    """
    value = value.strip()
    if value.startswith("t1_"):
        return "comment"
    if value.startswith("t3_"):
        return "post"
    parts = [p for p in value.split("/") if p]
    if "comments" in parts:
        idx = parts.index("comments")
        if idx + 3 < len(parts):
            return "comment"
    return "post"


class Interactor:
    def __init__(self, session):
        self._session = session
        self._modhash = None

    @classmethod
    def create(cls, headless: bool = False):
        auth = _load_auth()
        session = auth.ensure_authenticated_page(headless=headless)
        return cls(session)

    def _fetch_modhash(self):
        page = self._session.page
        result = page.evaluate(
            """
            async ([url, timeout_ms]) => {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), timeout_ms);
                try {
                    const res = await fetch(url, {
                        signal: controller.signal,
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                    });
                    const text = await res.text();
                    return {ok: res.ok, status: res.status, body: text};
                } catch (err) {
                    return {ok: false, error: err.toString()};
                } finally {
                    clearTimeout(timer);
                }
            }
            """,
            [f"{PUBLIC_BASE}/api/me.json", 10000],
        )
        if not result.get("ok"):
            raise RuntimeError(f"Could not fetch user profile: {result}")
        data = json.loads(result["body"])
        me = data.get("data", data)
        self._modhash = me.get("modhash") or ""
        if not me.get("name"):
            raise RuntimeError("Not logged in")

    def _post_json(self, path: str, payload: dict) -> dict:
        if self._modhash is None:
            self._fetch_modhash()

        body = urllib.parse.urlencode({**payload, "api_type": "json", "uh": self._modhash})
        page = self._session.page

        time.sleep(0.5)
        result = page.evaluate(
            """
            async ([url, body, timeout_ms]) => {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), timeout_ms);
                try {
                    const res = await fetch(url, {
                        method: 'POST',
                        signal: controller.signal,
                        credentials: 'include',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                        body,
                    });
                    const text = await res.text();
                    return {ok: res.ok, status: res.status, body: text};
                } catch (err) {
                    return {ok: false, error: err.toString()};
                } finally {
                    clearTimeout(timer);
                }
            }
            """,
            [f"{PUBLIC_BASE}{path}", body, 30000],
        )
        if not result.get("ok"):
            raise RuntimeError(f"Reddit POST failed: {result.get('status')} {result.get('body', '')[:200]}")
        try:
            return json.loads(result["body"])
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Reddit returned non-JSON response: {result['body'][:200]}") from exc

    def comment(self, thing_id: str, text: str) -> dict:
        data = self._post_json("/api/comment", {"thing_id": thing_id, "text": text})
        things = data.get("json", {}).get("data", {}).get("things", [])
        if not things:
            errors = data.get("json", {}).get("errors", [])
            if errors:
                raise RuntimeError(f"Reddit rejected comment: {errors}")
            raise RuntimeError("Comment returned no things")
        comment_data = things[0].get("data", {})
        return {
            "comment_id": comment_data.get("id", ""),
            "permalink": comment_data.get("permalink", ""),
        }

    def reply(self, comment_id: str, text: str) -> dict:
        if not comment_id.startswith("t1_"):
            raise ValueError(f"reply expects a comment fullname (t1_), got: {comment_id}")
        return self.comment(comment_id, text)

    def _check_errors(self, data: dict, action: str) -> None:
        errors = data.get("json", {}).get("errors", [])
        if errors:
            raise RuntimeError(f"Reddit rejected {action}: {errors}")

    def vote(self, thing_id: str, direction: int) -> dict:
        data = self._post_json("/api/vote", {"id": thing_id, "dir": str(direction)})
        self._check_errors(data, "vote")
        return {"action": "vote", "thing_id": thing_id, "direction": direction}

    def save(self, thing_id: str) -> dict:
        data = self._post_json("/api/save", {"id": thing_id})
        self._check_errors(data, "save")
        return {"action": "save", "thing_id": thing_id}

    def unsave(self, thing_id: str) -> dict:
        data = self._post_json("/api/unsave", {"id": thing_id})
        self._check_errors(data, "unsave")
        return {"action": "unsave", "thing_id": thing_id}

    def close(self) -> None:
        if self._session:
            self._session.close()
