from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CATEGORIES_PATH = DATA_DIR / "categories.json"
CUSTOM_CATEGORIES_PATH = DATA_DIR / "custom_categories.json"


def _ensure_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CATEGORIES_PATH.exists():
        CATEGORIES_PATH.write_text(json.dumps({}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not CUSTOM_CATEGORIES_PATH.exists():
        CUSTOM_CATEGORIES_PATH.write_text(json.dumps([], ensure_ascii=False, indent=2), encoding="utf-8")


def load_categories() -> Dict[str, str]:
    _ensure_store()
    try:
        return json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_categories(categories: Dict[str, str]) -> None:
    _ensure_store()
    CATEGORIES_PATH.write_text(json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8")


def load_custom_categories() -> list[str]:
    _ensure_store()
    try:
        return json.loads(CUSTOM_CATEGORIES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_custom_categories(categories: list[str]) -> None:
    _ensure_store()
    CUSTOM_CATEGORIES_PATH.write_text(json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8")


def add_custom_category(category: str) -> str:
    normalized = category.strip()
    if not normalized:
        return normalized

    existing = load_custom_categories()
    for existing_category in existing:
        if existing_category.lower() == normalized.lower():
            return existing_category

    updated = sorted(existing + [normalized], key=lambda item: item.lower())
    save_custom_categories(updated)
    return normalized


def rename_custom_category(old_category: str, new_category: str) -> int:
    existing = load_custom_categories()
    normalized_new = new_category.strip()
    if not normalized_new:
        return 0

    for existing_category in existing:
        if existing_category.lower() == normalized_new.lower():
            return 0

    updated = [normalized_new if c == old_category else c for c in existing]
    save_custom_categories(sorted(updated, key=lambda item: item.lower()))

    categories = load_categories()
    updated_rules = 0
    for merchant, category in list(categories.items()):
        if category == old_category:
            categories[merchant] = normalized_new
            updated_rules += 1
    save_categories(categories)
    return updated_rules


def delete_custom_category(category: str, replacement: str | None = None) -> int:
    existing = load_custom_categories()
    updated = [c for c in existing if c != category]
    save_custom_categories(sorted(updated, key=lambda item: item.lower()))

    categories = load_categories()
    updated_rules = 0
    for merchant, cat in list(categories.items()):
        if cat == category:
            if replacement is None or replacement == "Unbekannt":
                del categories[merchant]
            else:
                categories[merchant] = replacement
            updated_rules += 1
    save_categories(categories)
    return updated_rules


def merge_category(source: str, target: str) -> int:
    existing = load_custom_categories()
    updated = [c for c in existing if c != source]
    save_custom_categories(sorted(updated, key=lambda item: item.lower()))

    categories = load_categories()
    updated_rules = 0
    for merchant, cat in list(categories.items()):
        if cat == source:
            categories[merchant] = target
            updated_rules += 1
    save_categories(categories)
    return updated_rules


def get_user_category(merchant: str) -> str | None:
    categories = load_categories()
    return categories.get(merchant)


def set_user_category(merchant: str, category: str) -> None:
    categories = load_categories()
    categories[merchant] = category
    save_categories(categories)
