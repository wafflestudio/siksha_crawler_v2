import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


STATE_DIR = Path(".crawler_state")


def _meta_key(meta: Dict[str, str]) -> str:
    return json.dumps(meta, ensure_ascii=False, sort_keys=True)


def _meals_digest(meals: List[Dict[str, Any]]) -> str:
    payload = json.dumps(meals, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def payload_key(payload: Dict[str, Any]) -> str:
    """Return the state-tracking key for a given payload."""
    return _meta_key({
        "restaurant": payload["restaurant"],
        "date": payload["date"],
        "type": payload["type"],
    })


def load_state(source: str) -> Dict[str, str]:
    path = STATE_DIR / f"{source}.json"
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        return {}

    return {str(k): str(v) for k, v in data.items()}


def save_state(source: str, state: Dict[str, str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{source}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def plan_sync(
    source: str,
    current_payloads: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, str], Dict[str, int]]:
    """Compute which payloads differ from the previously saved state.

    Returns ``(to_send, previous_state, new_state, stats)``.  State is **not**
    persisted here.  The caller must call ``save_state(source, committed_state)``
    after processing the returned payloads, omitting keys for any sends that
    failed so that those entries are retried on the next run.
    """
    previous_state = load_state(source)
    current_state: Dict[str, str] = {}
    to_send: List[Dict[str, Any]] = []

    for payload in current_payloads:
        key = payload_key(payload)
        digest = _meals_digest(payload.get("meals", []))

        current_state[key] = digest
        if previous_state.get(key) != digest:
            to_send.append(payload)

    # Only compute deletions when the current crawl produced at least one
    # payload.  An empty result almost always means a parse failure (e.g. the
    # source page changed its structure), not that every restaurant closed.
    # Skipping deletions in that case prevents a transient scrape error from
    # wiping all previously-known menus on the backend.
    deleted_keys: set = set()
    if current_payloads:
        deleted_keys = set(previous_state.keys()) - set(current_state.keys())
        for key in deleted_keys:
            meta = json.loads(key)
            to_send.append(
                {
                    "restaurant": meta["restaurant"],
                    "date": meta["date"],
                    "type": meta["type"],
                    "meals": [],
                }
            )

    stats = {
        "current": len(current_payloads),
        "changed": len(to_send),
        "unchanged": len(current_payloads) - (len(to_send) - len(deleted_keys)),
        "deleted": len(deleted_keys),
    }
    return to_send, previous_state, current_state, stats
