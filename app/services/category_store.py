from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CATEGORIES_PATH = DATA_DIR / "categories.json"


def _ensure_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CATEGORIES_PATH.exists():
        CATEGORIES_PATH.write_text(json.dumps({}, ensure_ascii=False, indent=2), encoding="utf-8")


def load_categories() -> Dict[str, str]:
    _ensure_store()
    try:
        return json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_categories(categories: Dict[str, str]) -> None:
    _ensure_store()
    CATEGORIES_PATH.write_text(json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8")


def get_user_category(merchant: str) -> str | None:
    categories = load_categories()
    return categories.get(merchant)


def set_user_category(merchant: str, category: str) -> None:
    categories = load_categories()
    categories[merchant] = category
    save_categories(categories)
