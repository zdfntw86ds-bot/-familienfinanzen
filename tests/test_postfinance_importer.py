import unittest
from datetime import date
from decimal import Decimal

from app.importers.postfinance_importer import parse_postfinance_text


class PostFinanceImporterTests(unittest.TestCase):
    def test_extracts_counterparties_and_ignores_running_balance(self):
        text = """
        08.08.2026 LASTSCHRIFT 5 026.45 08.08.26 983.52
        UBS SWITZERLAND AG
        BAHNHOFSTRASSE 45
        CH953000520666367102P
        SWISSCARD AECS GMBH
        POSTFACH 227
        8810 HORGEN
        09.08.2026 GUTSCHRIFT 6 439.85 09.08.26 7 423.37
        CH4709000000312969412
        FINANZVERWALTUNG KANTON BERN
        10.08.2026 APPLE PAY 15.20 10.08.26 7 408.17
        KARTEN NR. XXXX2642
        MIGROS BERN BAHNHOF (4530)
        BERN (CH)
        """

        transactions = parse_postfinance_text(text)

        self.assertEqual(len(transactions), 3)
        self.assertEqual(transactions[0].merchant_original, "SWISSCARD AECS GMBH")
        self.assertEqual(transactions[0].amount, Decimal("5026.45"))
        self.assertEqual(transactions[0].transaction_type, "Expense")
        self.assertEqual(transactions[1].merchant_original, "FINANZVERWALTUNG KANTON BERN")
        self.assertEqual(transactions[1].amount, Decimal("6439.85"))
        self.assertEqual(transactions[1].transaction_type, "Income")
        self.assertEqual(transactions[2].merchant_original, "MIGROS BERN BAHNHOF (4530)")

    def test_splits_cash_withdrawal_fee_booking(self):
        text = """
        28.06.26 BARGELDBEZUG VOM 27.06.2026 189.10 27.06.26
        EUR 200.00 ZUM KURS VON
        0.9455
        KARTEN NR. XXXX2642
        BEKB ZOLLIKOFEN II
        ZOLLIKOFEN (CH)
        PREIS FÜR 5.00 28.06.26
        BARGELDBEZUG AM BANCOMAT
        IM INLAND VOM 27.06.2026
        KARTEN NR. XXXX2642
        BEKB ZOLLIKOFEN II
        ZOLLIKOFEN (CH)
        """

        transactions = parse_postfinance_text(text)

        self.assertEqual(len(transactions), 2)
        self.assertEqual([transaction.amount for transaction in transactions], [Decimal("189.10"), Decimal("5.00")])
        self.assertEqual(transactions[0].transaction_type, "Expense")
        self.assertEqual(transactions[1].transaction_type, "Fee")

    def test_parses_multiline_bookings_and_ignores_statement_lines(self):
        text = """
        PostFinance Kontoauszug
        Buchungsdatum Beschreibung Betrag
        03.06.2026 TWINT KAUF -24.90 03.06.2026
        COOP-1931 ZOLLIKOFEN
        05.06.2026 APPLE PAY -18,40 05.06.2026
        MIGROS BERN ZÄHRINGER
        10.06.2026 LASTSCHRIFT -1'234.50 10.06.2026
        VISECA PAYMENT SERVICES AG
        30.06.2026 Kontostand 2'000.00 CHF
        Seite 1 von 1
        """

        transactions = parse_postfinance_text(text, source_file="postfinance_june.pdf")

        self.assertEqual(len(transactions), 3)
        self.assertEqual(
            [(tx.date, tx.merchant_original, tx.amount) for tx in transactions],
            [
                (date(2026, 6, 3), "COOP-1931 ZOLLIKOFEN", Decimal("-24.90")),
                (date(2026, 6, 5), "MIGROS BERN ZÄHRINGER", Decimal("-18.40")),
                (date(2026, 6, 10), "VISECA PAYMENT SERVICES AG", Decimal("-1234.50")),
            ],
        )
        self.assertEqual(transactions[0].payment_method, "TWINT")
        self.assertEqual(transactions[1].payment_method, "Apple Pay")
        self.assertEqual(transactions[2].payment_method, "Direct debit")
        self.assertEqual(transactions[0].raw_description, "03.06.2026 TWINT KAUF -24.90 03.06.2026\nCOOP-1931 ZOLLIKOFEN")

    def test_parses_date_description_and_amount_on_one_line(self):
        transactions = parse_postfinance_text("12.08.2026 TWINT KAUF COOP-1931 ZOLLIKOFEN -9.90 CHF")

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].merchant_original, "COOP-1931 ZOLLIKOFEN")
        self.assertEqual(transactions[0].amount, Decimal("-9.90"))


if __name__ == "__main__":
    unittest.main()