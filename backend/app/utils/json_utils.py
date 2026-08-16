import json
from pathlib import Path
def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle: return json.load(handle)
def save_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle: json.dump(data, handle, ensure_ascii=False, indent=2)
