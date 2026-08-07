from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class Transaction:
    date: date
    merchant_original: str
    amount: Decimal

    def __str__(self) -> str:
        return f"Transaction(date={self.date}, merchant='{self.merchant_original}', amount={self.amount})"
