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
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    previous_state = load_state(source)
    current_state: Dict[str, str] = {}
    to_send: List[Dict[str, Any]] = []

    for payload in current_payloads:
        meta = {
            "restaurant": payload["restaurant"],
            "date": payload["date"],
            "type": payload["type"],
        }
        key = _meta_key(meta)
        digest = _meals_digest(payload.get("meals", []))

        current_state[key] = digest
        if previous_state.get(key) != digest:
            to_send.append(payload)

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

    save_state(source, current_state)
    stats = {
        "current": len(current_payloads),
        "changed": len(to_send),
        "unchanged": len(current_payloads) - (len(to_send) - len(deleted_keys)),
        "deleted": len(deleted_keys),
    }
    return to_send, stats
