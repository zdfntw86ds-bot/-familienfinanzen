from __future__ import annotations

from typing import Dict

KEYWORD_CATEGORIES: Dict[str, str] = {
    "coop": "Lebensmittel",
    "migros": "Lebensmittel",
    "denner": "Lebensmittel",
    "aldi": "Lebensmittel",
    "mensa": "Essen",
    "apple": "Technik",
    "parkingpay": "Auto",
    "hotel": "Reisen",
}


def categorize(merchant: str) -> str:
    merchant_lower = merchant.lower()
    for keyword, category in KEYWORD_CATEGORIES.items():
        if keyword in merchant_lower:
            return category
    return "Unbekannt"
