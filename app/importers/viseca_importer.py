import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List

from app.models.transaction import Transaction
from app.importers.pdf_importer import extract_text_from_pdf


DATE_FORMATS = ["%d.%m.%Y", "%d.%m.%y", "%d.%m."]


def _normalize_amount(amount_str: str) -> Decimal:
    s = amount_str.strip()
    # Remove non-numeric thousands separators (apostrophes, spaces)
    s = s.replace("'", "").replace(" ", "")
    # Replace comma with dot for decimal point
    s = s.replace(",", ".")
    # Remove trailing currency markers if any
    s = re.sub(r"[A-Za-z\.]+$", "", s).strip()
    try:
        return Decimal(s)
    except InvalidOperation:
        # Fallback: try to extract numeric part
        m = re.search(r"[+-]?[0-9]+(?:\.[0-9]{2})?", s)
        if m:
            return Decimal(m.group(0))
        raise


def _parse_date(datestr: str):
    datestr = datestr.strip()
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(datestr, fmt)
            # If format had no year ("%d.%m."), assume current year
            if fmt == "%d.%m.":
                dt = dt.replace(year=datetime.now().year)
            return dt.date()
        except ValueError:
            continue
    # As a last resort, try to find a dd.mm.yyyy pattern inside the string
    m = re.search(r"(\d{1,2}\.\d{1,2}\.\d{2,4})", datestr)
    if m:
        return _parse_date(m.group(1))
    raise ValueError(f"Unrecognized date format: {datestr}")


TRANSACTION_RE = re.compile(
    r"^\s*(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)\s+(.+?)\s+([+-]?[0-9'\.,\s]+)\s*(?:CHF|SFr\.|EUR|€)?\s*$",
    re.IGNORECASE,
)


def parse_viseca_text(text: str) -> List[Transaction]:
    """Parse extracted Viseca statement text and return a list of Transaction objects.

    The parser splits text into lines, skips headers/totals/page numbers and lines
    containing keywords like 'Übertrag', and attempts to match transaction lines.
    Transaction lines are expected to start with a date and end with an amount.
    """
    transactions: List[Transaction] = []
    lines = text.splitlines()

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        # Skip obvious non-transaction lines
        skip_keywords = ["übertrag", "seite", "summe", "total", "saldo", "konto", "page"]
        if any(k in line.lower() for k in skip_keywords):
            continue

        m = TRANSACTION_RE.match(line)
        if not m:
            # not a transaction line
            continue

        date_str, merchant, amount_str = m.group(1, 2, 3)
        try:
            dt = _parse_date(date_str)
            amt = _normalize_amount(amount_str)
        except Exception:
            # can't parse this line reliably, skip
            continue

        tx = Transaction(date=dt, merchant_original=merchant.strip(), amount=amt)
        transactions.append(tx)
        # For now print each parsed transaction
        print(tx)

    return transactions


if __name__ == "__main__":
    sample = """
01.07.2026 SOME SHOP ZURICH 45.90 CHF
02.07.2026 OTHER STORE 1'234,50 CHF
Übertrag vom Vormonat
Seite 1 von 2
    """
    parse_viseca_text(sample)


def is_viseca_text(text: str) -> bool:
    """Very small heuristic to detect Viseca statements from extracted text."""
    if not text:
        return False
    lower = text.lower()
    indicators = ["viseca", "kartenabrechnung", "kreditkarte", "karte", "viseca ag", "viseca card"]
    return any(ind in lower for ind in indicators)


def parse_viseca_pdf(path: str | Path) -> List[Transaction]:
    """Extract text from a PDF, detect Viseca statements and parse transactions.

    Prints every parsed Transaction to the terminal and returns the list.
    """
    print(f"DEBUG: parse_viseca_pdf called with path={path}")
    text = extract_text_from_pdf(path)
    print(f"DEBUG: parse_viseca_pdf: extracted text length={len(text or '')}")
    if not text:
        print(f"No text extracted from {path}")
        # still return empty list
        return []

    # Always parse the extracted text (filename-based importer selection handles detection)
    txs = parse_viseca_text(text)
    # parse_viseca_text already prints each transaction; return for further use
    return txs
