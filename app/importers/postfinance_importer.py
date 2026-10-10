import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, List

from app.importers.pdf_importer import extract_text_from_pdf
from app.models.transaction import Transaction


DATE_RE = re.compile(r"(?<!\d)(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)(?!\d)")
VALID_DATE_SPAN_RE = re.compile(
    r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])\.(?:0?[1-9]|1[0-2])(?:\.\d{2,4})?(?!\d)"
)
FULL_DATE_SPAN_RE = re.compile(
    r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])\.(?:0?[1-9]|1[0-2])\.\d{2,4}(?!\d)"
)
DATE_LINE_RE = re.compile(r"^\s*\d{1,2}\.\d{1,2}(?:\.\d{2,4})?(?:\s|$)")
AMOUNT_RE = re.compile(
    r"(?<![\d.])(?P<value>[+-]?(?:\d{1,3}(?:[' \u00a0]\d{3})+|\d+)[.,]\d{2})(?!\d)"
)
CURRENCY_RE = re.compile(r"\b(?:CHF|SFR\.?|EUR|USD)\b", re.IGNORECASE)
LOCATION_RE = re.compile(r"^[A-ZÄÖÜÀ-ÿ][A-ZÄÖÜÀ-ÿ' -]+\s+\([A-Z]{2}\)$", re.IGNORECASE)

EXECUTING_BANK_MARKERS = (
    "VALIANT BANK",
    "UBS SWITZERLAND",
    "UBS",
    "BERNER KANTONALBANK",
    "MIGROS BANK",
    "POSTFINANCE",
    "ZÜRCHER KANTONALBANK",
    "ZUERCHER KANTONALBANK",
    "RAIFFEISEN",
    "CREDIT SUISSE",
    "BEKB",
)

SKIP_BLOCK_WORDS = (
    "KONTOSTAND",
    "SALDO",
    "ÜBERTRAG",
    "UEBERTRAG",
    "TOTAL",
    "SUMME",
    "SEITE",
    "PAGE",
)

DESCRIPTORS = (
    "DIENSTLEISTUNG VOM",
    "GELD EMPFANGEN VOM",
    "GELD SENDEN VOM",
    "WARENRUECKGABE VOM",
    "WARENRÜCKGABE VOM",
    "KAUF/DIENSTLEISTUNG VOM",
    "KAUF / DIENSTLEISTUNG VOM",
    "KAUCF/DIENSTLEISTUNG",
    "KAUCF/DIENSTLEISTUNG VOM",
    "KAUF/DIENSOTLEISTUNG",
    "TWINT KAUCF/DIENSTLEISTUNG",
    "TWINT KAUF/DIENSTLEISTUNG",
    "TWINT KAUF/DIENSTLEISTUNG VOM",
    "TWINT KAUF",
    "TWINT GELD EMPFANGEN VOM",
    "TWINT GELD SENDEN VOM",
    "TWINT GELD EMPFANGEN",
    "TWINT GELD SENDEN",
    "APPLE PAY",
    "LASTSCHRIFT",
    "GUTSCHRIFT",
    "BETRAG IN KONTOWÄHRUNG",
    "BETRAG IN KONTOWAEHRUNG",
)

METHODS = (
    ("TWINT", "TWINT"),
    ("APPLE PAY", "Apple Pay"),
    ("APPLEPAY", "Apple Pay"),
    ("KARTENZAHLUNG", "Card"),
    ("CARD PAYMENT", "Card"),
    ("LASTSCHRIFT", "Direct debit"),
    ("DIRECT DEBIT", "Direct debit"),
    ("DAUERAUFTRAG", "Standing order"),
    ("STANDING ORDER", "Standing order"),
    ("BANKÜBERWEISUNG", "Transfer"),
    ("BANKUEBERWEISUNG", "Transfer"),
    ("BANK TRANSFER", "Transfer"),
    ("ÜBERWEISUNG", "Transfer"),
    ("UEBERWEISUNG", "Transfer"),
    ("BARGELDBEZUG", "Cash withdrawal"),
    ("CASH WITHDRAWAL", "Cash withdrawal"),
    ("LOHN", "Salary"),
    ("GEHALT", "Salary"),
    ("GUTSCHRIFT", "Salary"),
    ("SALARY", "Salary"),
    ("AUFTRAG CH-DD", "Direct debit"),
    ("BASISLASTSCHRIFT", "Direct debit"),
)


_EMPTY_LINES = {"", "-", ":"}
BOOKING_START_LABELS = (
    "TWINT",
    "APPLE PAY",
    "APPLEPAY",
    "LASTSCHRIFT",
    "DAUERAUFTRAG",
    "STANDING ORDER",
    "KAUF/DIENSTLEISTUNG",
    "KAUF / DIENSTLEISTUNG",
    "KAUCF/DIENSTLEISTUNG",
    "KAUF/DIENSOTLEISTUNG",
    "TWINT KAUCF/DIENSTLEISTUNG",
    "GUTSCHRIFT",
    "BARGELDBEZUG",
    "CASH WITHDRAWAL",
    "ÜBERWEISUNG",
    "UEBERWEISUNG",
    "BANKÜBERWEISUNG",
    "BANKUEBERWEISUNG",
    "LOHN",
    "GEHALT",
    "SALARY",
    "AUFTRAG",
    "BASISLASTSCHRIFT",
    "PREIS FÜR",
    "PREIS FÜR",
)


def _normalise_lines(text: str) -> list[str]:
    return [re.sub(r"[ \t]+", " ", line.replace("\u00a0", " ")).strip() for line in text.splitlines()]


def _is_booking_start(line: str) -> bool:
    upper = line.upper()
    if any(word in upper for word in SKIP_BLOCK_WORDS):
        return False
    if not DATE_RE.search(line) or not AMOUNT_RE.search(line):
        return False
    return any(upper.startswith(label) or label in upper for label in BOOKING_START_LABELS)


def _detect_booking_blocks(lines: list[str]) -> list[list[str]]:
    """Stage 1: identify complete date-led booking blocks."""
    block: list[str] = []
    blocks: list[list[str]] = []
    for line in lines:
        if _is_booking_start(line):
            if block:
                blocks.append(block)
            block = [line]
        elif block:
            block.append(line)
    if block:
        blocks.append(block)
    return blocks


def _parse_date(block: list[str]):
    match = FULL_DATE_SPAN_RE.search(block[0]) or VALID_DATE_SPAN_RE.search(block[0])
    if not match:
        raise ValueError("Booking has no date")
    value = match.group(0)
    for date_format in ("%d.%m.%Y", "%d.%m.%y", "%d.%m."):
        try:
            parsed = datetime.strptime(value, date_format)
            if date_format == "%d.%m.":
                parsed = parsed.replace(year=datetime.now().year)
            return parsed.date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized booking date: {value}")


def _amount_from_block(block: list[str]) -> Decimal:
    candidates: list[str] = []
    for line in block:
        upper = line.upper()
        if any(word in upper for word in SKIP_BLOCK_WORDS):
            continue
        date_spans = [date_match.span() for date_match in FULL_DATE_SPAN_RE.finditer(line)]
        for match in AMOUNT_RE.finditer(line):
            value = match.group("value")
            if any(start <= match.start() and match.end() <= end for start, end in date_spans):
                continue
            candidates.append(value)

    if not candidates:
        raise ValueError("Booking has no amount")

    # The first decimal value belongs to the booking. Later values are often
    # the running account balance printed at the end of the block.
    value = candidates[0]
    normalised = value.replace("'", "").replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        return Decimal(normalised)
    except InvalidOperation as exc:
        raise ValueError(f"Unrecognized booking amount: {value}") from exc


def _clean_description_line(line: str) -> str:
    cleaned = VALID_DATE_SPAN_RE.sub("", line)
    cleaned = AMOUNT_RE.sub("", cleaned)
    cleaned = CURRENCY_RE.sub("", cleaned)
    cleaned = re.sub(r"\bCH[A-Z0-9]{15,}\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:VOM\s+)?(?:P|O|C|Y)\s+", "", cleaned.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"^VOM\s*", "", cleaned.strip(), flags=re.IGNORECASE)
    return cleaned.strip(" -:+")


def _is_technical_line(candidate: str) -> bool:
    upper = candidate.upper().strip()
    if not upper or upper in _EMPTY_LINES:
        return True
    if upper in {"VOM", "AN", "VON", "P", "O", "C", "Y", "ED", "65600"}:
        return True
    if upper.startswith(("KARTEN NR", "IBAN", "KONTONUMMER", "SENDER REFERENZ", "REFERENZ", "TRANSAKTIONS-ID", "ID-NR", "MITTEIL", "MESSAGE", "MEMO", "POLICE", "AN TELEFON-NR", "VON TELEFON-NR", "ZAHLUNGSEMPFÄNGER", "POSTFACH", "DIVISION", "PERSONENVERKEHR", "BITTE ÜBERPRÜFEN SIE DEN KONTOAUSZUG", "FREUNDLICHE GRÜSSE POSTFINANCE", "/FOR/", "VALUTA")):
        return True
    if upper.startswith(("DAUERAUFTRAG", "BASISLASTSCHRIFT", "BETRAG IN KONTOWÄHRUNG", "BETRAG IN KONTOWAEHRUNG")):
        return True
    if re.fullmatch(r"CH[A-Z0-9]+", upper):
        return True
    if re.fullmatch(r"[A-ZÄÖÜ]", upper):
        return True
    if re.fullmatch(r"\d{4}\s+[A-ZÄÖÜ]+(?:\s+\d+)?", upper):
        return True
    if re.fullmatch(r"[A-ZÄÖÜ][A-ZÄÖÜ .'-]+\s+\d+[A-Z]?", upper):
        return True
    if re.fullmatch(r"\+?\d[\d ]+", upper):
        return True
    if re.fullmatch(r"\d{3,}[A-Z0-9-]*", upper):
        return True
    if LOCATION_RE.fullmatch(candidate):
        return True
    if any(word in upper for word in SKIP_BLOCK_WORDS):
        return True
    return False


def _merchant_groups(block: list[str], preserve_single_word: bool) -> list[str]:
    groups: list[str] = []
    current: list[str] = []
    method_labels = {label for label, _ in METHODS}
    for line in block:
        candidate = _clean_description_line(line)
        upper = candidate.upper()
        changed = True
        while changed and candidate:
            changed = False
            for descriptor in DESCRIPTORS:
                if upper.startswith(descriptor):
                    candidate = candidate[len(descriptor):].strip(" -:+")
                    upper = candidate.upper()
                    changed = True
                    break
        if upper in method_labels or upper in {"KAUF", "PAYMENT", "BUCHUNG", "BELASTUNG", "BESCHREIBUNG"}:
            candidate = ""
        single_word_location = not preserve_single_word and re.fullmatch(r"[A-ZÄÖÜÀ-Ý]{4,}", candidate) is not None
        if single_word_location or _is_technical_line(candidate):
            if current:
                groups.append(" ".join(current))
                current = []
            continue
        current.append(candidate)
    if current:
        groups.append(" ".join(current))
    return groups


def _merchant_from_block(block: list[str], payment_method: str, description: str) -> str:
    upper = description.upper()
    counterparty_booking = payment_method in {"Direct debit", "Standing order", "Transfer", "Salary"} or any(
        word in upper for word in ("GUTSCHRIFT", "GELD EMPFANGEN", "GELD SENDEN", "AUFTRAG")
    )
    groups = _merchant_groups(block, preserve_single_word=True)
    if not groups:
        return "Unknown"

    if payment_method == "Direct debit":
        payees = [
            group for group in groups
            if not any(marker in group.upper() for marker in EXECUTING_BANK_MARKERS)
        ]
        return (payees or groups)[0]
    meaningful = [group for group in groups if len(group.split()) > 1 or any(char in group for char in ("&", "/", "-", ","))]
    if payment_method in {"Salary", "TWINT"}:
        return (meaningful or groups)[0]
    if not counterparty_booking:
        return groups[0]

    return (meaningful or groups)[-1]



def _payment_method(description: str) -> str:
    upper = description.upper()
    if "AUSLAND" in upper or "FOREIGN" in upper:
        return "Foreign payment"
    for label, method in METHODS:
        if label in upper:
            return method
    if "KAUF/DIENSTLEISTUNG" in upper or "CARD" in upper:
        return "Card"
    return "Unknown"


def _transaction_type(description: str, amount: Decimal, payment_method: str) -> str:
    upper = description.upper()
    if any(word in upper for word in ("GEBÜHR", "GEBUEHR", "FEE", "KOMMISSION", "PREIS FÜR", "PREIS FUER")):
        return "Fee"
    if payment_method == "Salary":
        return "Income"
    if payment_method == "Direct debit":
        return "Expense"
    if payment_method == "Standing order":
        return "Transfer"
    if payment_method == "Transfer":
        return "Transfer"
    if payment_method == "Card" or payment_method == "Apple Pay":
        return "Expense"
    if payment_method == "Cash withdrawal":
        return "Expense"
    if payment_method == "TWINT":
        if "GELD EMPFANGEN" in upper:
            return "Income"
        if "GELD SENDEN" in upper:
            return "Transfer"
        return "Expense"
    if any(word in upper for word in ("GELD SENDEN", "DAUERAUFTRAG", "STANDING ORDER", "ÜBERWEISUNG", "UEBERWEISUNG")):
        return "Transfer"
    if any(word in upper for word in ("GELD EMPFANGEN", "GUTSCHRIFT", "GEHALT", "LOHN", "SALARY")):
        return "Income"
    if any(word in upper for word in ("LASTSCHRIFT", "KAUF/DIENSTLEISTUNG", "APPLE PAY", "TWINT KAUF", "KARTENZAHLUNG", "BASISLASTSCHRIFT")):
        return "Expense"
    if amount > 0 and payment_method == "Salary":
        return "Income"
    if amount < 0:
        return "Expense"
    return "Unknown"


def _transaction_from_block(block: list[str], source_file: str | None = None) -> Transaction | None:
    """Stage 2: extract all transaction fields from one complete block."""
    raw_description = "\n".join(line for line in block if line)
    try:
        booking_date = _parse_date(block)
        amount = _amount_from_block(block)
    except ValueError:
        return None

    payment_method = _payment_method(raw_description)
    return Transaction(
        date=booking_date,
        merchant_original=_merchant_from_block(block, payment_method, raw_description),
        amount=amount,
        source_file=source_file,
        raw_description=raw_description,
        payment_method=payment_method,
        transaction_type=_transaction_type(raw_description, amount, payment_method),
    )


def parse_postfinance_text(text: str, source_file: str | None = None) -> List[Transaction]:
    lines = _normalise_lines(text)
    blocks = _detect_booking_blocks(lines)
    for index, block in enumerate(blocks[:20], start=1):
        print(f"Detected booking block {index}:")
        print("\n".join(block))
        print()
    transactions: List[Transaction] = []
    for block in blocks:
        transaction = _transaction_from_block(block, source_file=source_file)
        if transaction is not None:
            transactions.append(transaction)
    return transactions


def parse_postfinance_pdf(path: str | Path) -> List[Transaction]:
    text = extract_text_from_pdf(path)
    transactions = parse_postfinance_text(text, source_file=Path(path).name) if text else []
    for transaction in transactions[:20]:
        print(f"Date: {transaction.date}")
        print(f"Merchant: {transaction.merchant_original}")
        print(f"Amount: {transaction.amount}")
        print(f"Payment method: {transaction.payment_method}")
        print(f"Transaction type: {transaction.transaction_type}")
        print()
    print(f"Total parsed transaction count: {len(transactions)}")
    return transactions
