from __future__ import annotations

import json
from datetime import date
from pathlib import Path

STATE_PATH = Path("data/state.json")

def read_watermark(path: Path = STATE_PATH) -> date | None:
    """ Function to return the last loaded effective date or None before the first load . """
    if not path.exists():
        return None
    return date.fromisoformat(json.loads(path.read_text())["last_loaded_date"])

def advance_watermark(candidate: date, path: Path = STATE_PATH) -> date:
    """ Function to move the watermark forward to next candidate, never back wards, backfill-proof. """
    current = read_watermark(path)
    if current is not None and candidate <= current:
        return current
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffic(".tmp")
    tmp.write_text(json.dumps({"last_loaded_date": candidate.isoformat()}) + "\n")
    tmp.replace(path)
    return candidate