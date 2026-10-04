import re
import io
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    import pypdf
except ImportError:
    pypdf = None

def parse_gpay_pdf(file_bytes: bytes, password: Optional[str] = None) -> Dict[str, Any]:
    """
    Parses Google Pay (GPay) transaction statement PDFs.
    Handles encrypted PDFs, extracts transactions, and formats records for database ingestion.
    """
    if pypdf is None:
        raise RuntimeError("pypdf is not installed. Please run: pip install pypdf")

    stream = io.BytesIO(file_bytes)
    try:
        reader = pypdf.PdfReader(stream)
    except Exception as e:
        raise ValueError(f"Invalid PDF file or corrupted data: {str(e)}")

    if reader.is_encrypted:
        if not password:
            raise ValueError("PDF is password protected. Please enter password.")
        decrypted = False
        try:
            decrypted = reader.decrypt(password)
        except Exception:
            decrypted = False
        if not decrypted:
            raise ValueError("Incorrect PDF password.")

    full_text = ""
    for page in reader.pages:
        txt = page.extract_text() or ""
        full_text += txt + "\n"

    parsed_transactions = extract_transactions_from_text(full_text)
    return {
        "total_extracted": len(parsed_transactions),
        "transactions": parsed_transactions,
        "raw_text_snippet": full_text[:1000]
    }

def extract_transactions_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Regex & heuristic parser matching GPay PDF statement layouts.
    Handles un-spaced/merged PDF lines (e.g., '13Sep,2026', '01:59PM', 'PaidtoGooglePlayrechargecode')
    and spaced lines.
    """
    transactions = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Match Date: "13Sep,2026", "13 Sep, 2026", "01 Aug, 2025", "1 Aug 2025"
    date_regex = re.compile(r"^(\d{1,2})\s*([A-Za-z]{3})\s*,?\s*(\d{4})", re.IGNORECASE)
    # Match Time: "01:59PM", "09:46 PM", "8:44 AM"
    time_regex = re.compile(r"^(\d{1,2}:\d{2})\s*(AM|PM)$", re.IGNORECASE)
    # Match Amount: "₹89", "₹327.56", "₹2,000", "$50.00"
    amount_regex = re.compile(r"[₹Rs\.\$]\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
    # Match UPI ID: "UPITransactionID:625679004115", "UPI Transaction ID: 521399859480"
    upi_regex = re.compile(r"UPI\s*(?:Transaction\s*)?ID\s*:\s*(\d+)", re.IGNORECASE)

    # Match Detail: "Paidto...", "Paid to...", "Receivedfrom...", "Received from...", "Self transfer to..."
    paid_to_regex = re.compile(r"^(?:Paid\s*to|Payment\s*to)\s*(.+)$", re.IGNORECASE)
    rec_from_regex = re.compile(r"^(?:Received\s*from|Cashback\s*from|Refund\s*from)\s*(.+)$", re.IGNORECASE)
    self_tx_regex = re.compile(r"^(?:Self\s*transfer\s*to)\s*(.+)$", re.IGNORECASE)

    idx = 0
    num_lines = len(lines)

    def format_merchant_name(raw_name: str) -> str:
        # Separate concatenated camelCase or joined words (e.g. ZomatoOnlineOrder -> Zomato Online Order)
        clean = re.sub(r'([a-z])([A-Z])', r'\1 \2', raw_name)
        return clean.strip()

    while idx < num_lines:
        line = lines[idx]
        date_match = date_regex.match(line)

        if date_match:
            day, month_str, year = date_match.groups()
            date_str = f"{day} {month_str} {year}"

            time_str = "12:00 PM"
            amount_val = 0.0
            upi_id = ""
            tx_type = "DEBIT"
            merchant_name = ""
            details_line = ""

            sub_idx = idx + 1
            max_lookahead = min(sub_idx + 8, num_lines)

            while sub_idx < max_lookahead:
                sub_line = lines[sub_idx]

                # Stop if next transaction date begins
                if sub_idx > idx + 1 and date_regex.match(sub_line):
                    break

                # Time
                t_match = time_regex.match(sub_line)
                if t_match:
                    time_str = f"{t_match.group(1)} {t_match.group(2).upper()}"

                # Amount
                amt_match = amount_regex.search(sub_line)
                if amt_match and amount_val == 0.0:
                    try:
                        clean_amt = amt_match.group(1).replace(",", "")
                        amount_val = float(clean_amt)
                    except ValueError:
                        pass

                # UPI ID
                upi_m = upi_regex.search(sub_line)
                if upi_m:
                    upi_id = upi_m.group(1)

                # Paid to
                paid_m = paid_to_regex.match(sub_line)
                if paid_m and not merchant_name:
                    tx_type = "DEBIT"
                    merchant_name = format_merchant_name(paid_m.group(1))
                    details_line = sub_line

                # Received from
                rec_m = rec_from_regex.match(sub_line)
                if rec_m and not merchant_name:
                    tx_type = "CREDIT"
                    merchant_name = format_merchant_name(rec_m.group(1))
                    details_line = sub_line

                # Self transfer
                self_m = self_tx_regex.match(sub_line)
                if self_m and not merchant_name:
                    tx_type = "DEBIT"
                    merchant_name = format_merchant_name(f"Self Transfer: {self_m.group(1)}")
                    details_line = sub_line

                sub_idx += 1

            if amount_val > 0 and merchant_name:
                timestamp_ms = parse_datetime_to_epoch(date_str, time_str)
                raw_msg = f"{details_line or merchant_name}"
                if upi_id:
                    raw_msg += f" | UPI ID: {upi_id}"

                tx_obj = {
                    "date_str": date_str,
                    "time_str": time_str,
                    "account_name": merchant_name,
                    "amount": amount_val,
                    "type": tx_type,
                    "raw_message": raw_msg,
                    "upi_id": upi_id,
                    "timestamp": timestamp_ms
                }

                # Deduplicate identical items extracted within the same PDF stream
                is_batch_dup = False
                for prev in transactions:
                    same_amt = abs(prev["amount"] - amount_val) < 0.01
                    same_acc = prev["account_name"].lower().strip() == merchant_name.lower().strip()
                    same_time = abs(prev["timestamp"] - timestamp_ms) < (300 * 1000)
                    same_upi = bool(upi_id and prev["upi_id"] and prev["upi_id"] == upi_id)

                    if same_upi or (same_amt and same_acc and same_time):
                        is_batch_dup = True
                        break

                if not is_batch_dup:
                    transactions.append(tx_obj)

            idx = sub_idx
        else:
            idx += 1

    return transactions

def parse_datetime_to_epoch(date_str: str, time_str: str) -> int:
    """Helper to convert date ('01 Aug 2025') & time ('09:46 PM') into epoch milliseconds."""
    full_str = f"{date_str.strip()} {time_str.strip()}"
    formats = [
        "%d %b %Y %I:%M %p",
        "%d %B %Y %I:%M %p",
        "%d %b %Y %H:%M",
        "%d/%m/%Y %I:%M %p",
        "%Y-%m-%d %H:%M:%S"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(full_str, fmt)
            return int(dt.timestamp() * 1000)
        except ValueError:
            pass
    return int(time.time() * 1000)
