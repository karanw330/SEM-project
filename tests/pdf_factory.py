"""
Builds tiny, valid single-page PDFs in memory so the GPay import path
(pdf_parser.parse_gpay_pdf -> /api/transactions/parse-pdf -> preview modal
-> confirm-import) can be exercised end-to-end without real bank statements.
"""


def _escape(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_text_pdf(lines):
    """Return PDF bytes with each string in `lines` drawn on its own line."""
    stream_ops = ["BT", "/F1 11 Tf", "14 TL", "50 800 Td"]
    for line in lines:
        stream_ops.append("(%s) Tj T*" % _escape(line))
    stream_ops.append("ET")
    stream = "\n".join(stream_ops).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_pos)
    return bytes(out)


def gpay_statement_lines(entries):
    """entries: list of dicts with date, time, kind ('Paid to'/'Received from'), name, amount, upi."""
    lines = ["Transaction statement"]
    for e in entries:
        lines += [
            e["date"],
            e["time"],
            "%s %s" % (e["kind"], e["name"]),
            "UPI Transaction ID: %s" % e["upi"],
            "$%.2f" % e["amount"],
        ]
    return lines
