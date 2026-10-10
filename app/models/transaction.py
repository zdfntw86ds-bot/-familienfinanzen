from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class Transaction:
    date: date
    merchant_original: str
    amount: Decimal
    category: Optional[str] = None
    source_file: Optional[str] = None
    raw_description: Optional[str] = None
    payment_method: Optional[str] = None
    transaction_type: Optional[str] = None

    @property
    def merchant(self) -> str:
        return self.merchant_original

    def __str__(self) -> str:
        return f"Transaction(date={self.date}, merchant='{self.merchant_original}', amount={self.amount})"
