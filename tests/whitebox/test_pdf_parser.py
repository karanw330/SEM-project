"""
White-box unit tests for backend/pdf_parser.py

Units: parse_gpay_pdf(), extract_transactions_from_text(),
       format_merchant_name() (nested), parse_datetime_to_epoch()
Techniques: branch coverage, condition coverage, path coverage, loop testing.
"""

import io
from datetime import datetime

import pypdf
import pytest

import pdf_parser
from pdf_factory import build_text_pdf
from pdf_parser import extract_transactions_from_text as extract
from pdf_parser import parse_datetime_to_epoch


def block(date="13 Sep, 2026", time="01:59 PM", detail="Paid to Zomato", upi="111", amount="$250.00"):
    """One GPay statement entry as text lines (None = leave the line out)."""
    return [line for line in (date, time, detail, upi and "UPI Transaction ID: %s" % upi, amount) if line]


def text(*blocks):
    return "\n".join(line for b in blocks for line in b)


def epoch(s):
    return int(datetime.strptime(s, "%d %b %Y %I:%M %p").timestamp() * 1000)


# --------------------------------------------------------------------------
# parse_gpay_pdf(): branch coverage
# --------------------------------------------------------------------------

def _encrypted_pdf(password):
    writer = pypdf.PdfWriter(clone_from=pypdf.PdfReader(io.BytesIO(build_text_pdf(text(block()).split("\n")))))
    writer.encrypt(password, algorithm="RC4-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class TestParseGpayPdf:
    def test_wbu_p01_pypdf_missing(self, monkeypatch):
        """Branch `if pypdf is None` -> T"""
        monkeypatch.setattr(pdf_parser, "pypdf", None)
        with pytest.raises(RuntimeError, match="pypdf is not installed"):
            pdf_parser.parse_gpay_pdf(b"%PDF")

    def test_wbu_p02_corrupt_bytes(self):
        """PdfReader raises -> except branch -> ValueError"""
        with pytest.raises(ValueError, match="Invalid PDF file"):
            pdf_parser.parse_gpay_pdf(b"not a pdf at all")

    def test_wbu_p03_plain_pdf(self):
        """`if reader.is_encrypted` -> F; page loop runs once"""
        res = pdf_parser.parse_gpay_pdf(build_text_pdf(block()))
        assert res["total_extracted"] == 1
        assert res["transactions"][0]["account_name"] == "Zomato"
        assert "Paid to Zomato" in res["raw_text_snippet"]

    def test_wbu_p04_encrypted_without_password(self):
        """is_encrypted T, `if not password` T"""
        with pytest.raises(ValueError, match="password protected"):
            pdf_parser.parse_gpay_pdf(_encrypted_pdf("secret"))

    def test_wbu_p05_encrypted_wrong_password(self):
        """decrypt() returns 0 -> `if not decrypted` T"""
        with pytest.raises(ValueError, match="Incorrect PDF password"):
            pdf_parser.parse_gpay_pdf(_encrypted_pdf("secret"), password="wrong")

    def test_wbu_p06_encrypted_decrypt_raises(self, monkeypatch):
        """decrypt() raises -> inner except branch -> decrypted False"""
        def boom(self, pw):
            raise RuntimeError("crypto failure")
        monkeypatch.setattr(pypdf.PdfReader, "decrypt", boom)
        with pytest.raises(ValueError, match="Incorrect PDF password"):
            pdf_parser.parse_gpay_pdf(_encrypted_pdf("secret"), password="secret")

    def test_wbu_p07_encrypted_correct_password(self):
        """Full path through decryption to extraction"""
        res = pdf_parser.parse_gpay_pdf(_encrypted_pdf("secret"), password="secret")
        assert res["total_extracted"] == 1


# --------------------------------------------------------------------------
# extract_transactions_from_text(): paths, conditions, loops
# --------------------------------------------------------------------------

class TestExtractPaths:
    @pytest.mark.parametrize("detail, tx_type, merchant", [
        ("Paid to Zomato", "DEBIT", "Zomato"),
        ("Payment to Airtel", "DEBIT", "Airtel"),
        ("Received from Rahul", "CREDIT", "Rahul"),
        ("Cashback from GPay", "CREDIT", "GPay"),
        ("Refund from Amazon", "CREDIT", "Amazon"),
        ("Self transfer to HDFC", "DEBIT", "Self Transfer: HDFC"),
    ])
    def test_wbu_e01_detail_line_paths(self, detail, tx_type, merchant):
        """One path per detail regex (paid_to / rec_from / self_tx)."""
        [tx] = extract(text(block(detail=detail)))
        assert (tx["type"], tx["account_name"]) == (tx_type, merchant)

    def test_wbu_e02_merged_pdf_text_and_camel_case(self):
        """Un-spaced PDF text ('13Sep,2026', '01:59PM', 'PaidtoZomatoOnlineOrder')
        and format_merchant_name() splitting camelCase."""
        [tx] = extract("13Sep,2026\n01:59PM\nPaidtoZomatoOnlineOrder\nUPITransactionID:625679004115\n₹89")
        assert tx["account_name"] == "Zomato Online Order"
        assert tx["amount"] == 89.0
        assert tx["upi_id"] == "625679004115"
        assert tx["time_str"] == "01:59 PM"

    def test_wbu_e03_upi_suffix_present_and_absent(self):
        """`if upi_id:` -> T and F"""
        with_upi, without = extract(text(block(upi="555"), block(date="14 Sep, 2026", detail="Paid to Uber", upi=None)))
        assert with_upi["raw_message"] == "Paid to Zomato | UPI ID: 555"
        assert without["raw_message"] == "Paid to Uber"

    def test_wbu_e04_missing_time_defaults_to_noon(self):
        [tx] = extract(text(block(time=None)))
        assert tx["time_str"] == "12:00 PM"
        assert tx["timestamp"] == epoch("13 Sep 2026 12:00 PM")

    @pytest.mark.parametrize("amount_line, expected", [
        ("₹2,000", 2000.0),
        ("₹327.56", 327.56),
        ("$50.00", 50.0),
        ("Rs. 89", 89.0),
    ])
    def test_wbu_e05_amount_formats(self, amount_line, expected):
        [tx] = extract(text(block(amount=amount_line)))
        assert tx["amount"] == expected

    def test_wbu_e06_amount_value_error_branch(self):
        """'$,' matches the regex but float('') raises -> except ValueError: pass;
        the next amount line is then used (`amount_val == 0.0` still T)."""
        [tx] = extract(text(["13 Sep, 2026", "Paid to Zomato", "$,", "$75"]))
        assert tx["amount"] == 75.0


class TestExtractConditions:
    def test_wbu_c01_requires_amount_and_merchant(self):
        """Decision `amount_val > 0 and merchant_name`: (F,T), (T,F), (T,T)."""
        no_amount = text(block(amount=None))
        no_merchant = text(block(detail="Bill payment"))
        both = text(block())
        assert extract(no_amount) == []
        assert extract(no_merchant) == []
        assert len(extract(both)) == 1

    def test_wbu_c02_first_amount_and_first_merchant_win(self):
        """`amt_match and amount_val == 0.0` and `paid_m and not merchant_name` -> second operand F."""
        [tx] = extract(text(["13 Sep, 2026", "Paid to Zomato", "Received from Rahul", "$10", "$999"]))
        assert (tx["account_name"], tx["type"], tx["amount"]) == ("Zomato", "DEBIT", 10.0)

    @pytest.mark.parametrize("second, kept", [
        (dict(upi="111"), 1),                                   # same_upi T -> dropped
        (dict(upi="222"), 1),                                   # same amt+acc+time (same minute) -> dropped
        (dict(upi="222", amount="$251.00"), 2),                 # same_amt F -> kept
        (dict(upi="222", detail="Paid to Swiggy"), 2),          # same_acc F -> kept
        (dict(upi="222", time="01:59 AM"), 2),                  # same_time F -> kept
        (dict(upi=None), 1),                                    # no UPI, rest equal -> dropped
    ])
    def test_wbu_c03_in_pdf_duplicate_condition(self, second, kept):
        """Decision `same_upi or (same_amt and same_acc and same_time)`."""
        first = block(upi="111")
        assert len(extract(text(first, block(date="13 Sep, 2026", **second)))) == kept


class TestExtractLoops:
    def test_wbu_l01_outer_loop_zero_iterations(self):
        assert extract("") == []
        assert extract("   \n\n  ") == []

    def test_wbu_l02_lines_without_dates_are_skipped(self):
        """Outer `else: idx += 1` path for every non-date line."""
        assert extract("Statement\nAccount 1234\nPaid to Zomato\n$20") == []

    def test_wbu_l03_many_entries(self):
        entries = [block(date="%02d Sep, 2026" % d, detail="Paid to Shop%d" % d, upi=str(d)) for d in range(1, 6)]
        assert [t["account_name"] for t in extract(text(*entries))] == ["Shop%d" % d for d in range(1, 6)]

    @pytest.mark.parametrize("filler, found", [(6, True), (7, False)])
    def test_wbu_l04_lookahead_bound_of_eight_lines(self, filler, found):
        """Inner loop scans at most 8 lines after the date. The amount sits on the
        line right after `filler` noise lines plus the detail line:
        filler=6 -> amount is line 8 (inside the window), filler=7 -> line 9 (outside)."""
        lines = ["13 Sep, 2026", "Paid to Zomato"] + ["note"] * filler + ["$40"]
        assert (len(extract(text(lines))) == 1) is found

    def test_wbu_l05_lookahead_stops_at_next_date(self):
        """`if sub_idx > idx + 1 and date_regex.match(...)`: break -> T.
        The first entry has no amount, so the second entry's amount must NOT leak into it."""
        txs = extract(text(["13 Sep, 2026", "Paid to Zomato"], block(date="14 Sep, 2026", detail="Paid to Uber")))
        assert [t["account_name"] for t in txs] == ["Uber"]


# --------------------------------------------------------------------------
# parse_datetime_to_epoch(): one test per format in the loop + fallback
# --------------------------------------------------------------------------

@pytest.mark.parametrize("date_str, time_str, expected", [
    ("13 Sep 2026", "01:59 PM", datetime(2026, 9, 13, 13, 59)),
    ("13 September 2026", "01:59 PM", datetime(2026, 9, 13, 13, 59)),
    ("13 Sep 2026", "13:59", datetime(2026, 9, 13, 13, 59)),
    ("13/09/2026", "01:59 PM", datetime(2026, 9, 13, 13, 59)),
    ("2026-09-13", "13:59:00", datetime(2026, 9, 13, 13, 59)),
])
def test_wbu_d01_each_datetime_format(date_str, time_str, expected):
    """Loop over `formats`: the k-th format matches after k-1 ValueErrors."""
    assert parse_datetime_to_epoch(date_str, time_str) == int(expected.timestamp() * 1000)


def test_wbu_d02_no_format_matches_falls_back_to_now(monkeypatch):
    """All 5 iterations raise ValueError -> loop exits -> `return now`."""
    monkeypatch.setattr(pdf_parser.time, "time", lambda: 1_700_000_000.0)
    assert parse_datetime_to_epoch("someday", "noonish") == 1_700_000_000_000
