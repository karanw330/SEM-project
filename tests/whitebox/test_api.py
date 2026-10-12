"""
White-box tests for backend/main.py through FastAPI's in-process TestClient.

Units: every route handler, especially the PDF import pipeline
(parse_gpay_pdf_endpoint) and confirm_import_transactions().
Techniques: basis-path coverage (create_rule, V(G)=5), branch coverage of
all 400/404 exits, condition coverage of both duplicate-detection rules.
"""

from datetime import datetime

import pytest

from pdf_factory import build_text_pdf, gpay_statement_lines

STATEMENT = [
    {"date": "13 Sep, 2026", "time": "01:59 PM", "kind": "Paid to", "name": "ZomatoOnline", "amount": 250, "upi": "111"},
    {"date": "14 Sep, 2026", "time": "09:46 AM", "kind": "Received from", "name": "Rahul", "amount": 1000, "upi": "222"},
]


def upload(client, content, filename="statement.pdf", password=None):
    data = {"password": password} if password else {}
    return client.post("/api/transactions/parse-pdf", files={"file": (filename, content, "application/pdf")}, data=data)


def ms(s):
    return int(datetime.strptime(s, "%d %b %Y %I:%M %p").timestamp() * 1000)


# --------------------------------------------------------------------------
# create_rule(): all 5 basis paths
# --------------------------------------------------------------------------

class TestCreateRulePaths:
    def test_wbu_a01_p1_tag_rule_without_tag_id(self, client):
        r = client.post("/api/rules", json={"account_keyword": "X"})
        assert (r.status_code, r.json()["detail"]) == (400, "tag_id is required for tag rules")

    def test_wbu_a02_p2_tag_not_found(self, client):
        r = client.post("/api/rules", json={"account_keyword": "X", "tag_id": 999})
        assert (r.status_code, r.json()["detail"]) == (404, "Tag not found")

    def test_wbu_a03_p3_duplicate_keyword(self, client, make_tag):
        tag = make_tag("Food")
        client.post("/api/rules", json={"account_keyword": "ZOMATO", "tag_id": tag.id})
        r = client.post("/api/rules", json={"account_keyword": " zomato ", "tag_id": tag.id})
        assert (r.status_code, r.json()["detail"]) == (400, "Rule for keyword 'ZOMATO' already exists")

    def test_wbu_a04_p4_tag_rule_created(self, client, make_tag):
        tag = make_tag("Food", color_hex="#FF6600", emoji="🍔")
        r = client.post("/api/rules", json={"account_keyword": "zomato", "tag_id": tag.id})
        assert r.status_code == 201
        assert r.json() | {"id": 0} == {"id": 0, "account_keyword": "ZOMATO", "tag_id": tag.id, "is_ignore_rule": False,
                                         "tag_name": "Food", "tag_color": "#FF6600", "tag_emoji": "🍔"}

    def test_wbu_a05_p5_ignore_rule_created(self, client):
        r = client.post("/api/rules", json={"account_keyword": "self", "is_ignore_rule": True, "tag_id": 5})
        body = r.json()
        assert r.status_code == 201
        assert (body["tag_id"], body["tag_name"], body["tag_color"], body["tag_emoji"]) == (None, "IGNORED", "#E53E3E", "🚫")


# --------------------------------------------------------------------------
# Error branches of every other route
# --------------------------------------------------------------------------

@pytest.mark.parametrize("method, url, body", [
    ("put", "/api/transactions/999", {"amount": 1}),
    ("put", "/api/transactions/999/tag", {"tag_id": None}),
    ("delete", "/api/transactions/999", None),
    ("put", "/api/tags/999", {"name": "x"}),
    ("delete", "/api/tags/999", None),
    ("delete", "/api/rules/999", None),
])
def test_wbu_a06_not_found_branches(client, method, url, body):
    kwargs = {"json": body} if body is not None else {}
    assert getattr(client, method)(url, **kwargs).status_code == 404


def test_wbu_a07_success_branches_of_simple_routes(client, make_tag):
    tx = client.post("/api/transactions", json={"amount": 10, "account_name": "Shop"}).json()
    tag = make_tag("Food")
    assert [t["name"] for t in client.get("/api/tags").json()] == ["Food"]
    assert client.put("/api/transactions/%d" % tx["id"], json={"amount": 15}).json()["amount"] == 15
    assert client.put("/api/transactions/%d/tag" % tx["id"], json={"tag_id": tag.id}).json()["tag_name"] == "Food"
    assert client.get("/api/transactions", params={"tag_id": tag.id}).json()[0]["id"] == tx["id"]
    assert client.get("/api/dashboard/stats").json()["total_expenditure"] == 15
    assert client.put("/api/tags/%d" % tag.id, json={"name": "Meals"}).json()["name"] == "Meals"
    assert client.post("/api/rules/apply-all").json() == {"message": "Applied rules to 1 transactions"}
    assert client.delete("/api/transactions/%d" % tx["id"]).status_code == 200
    assert client.delete("/api/tags/%d" % tag.id).status_code == 200
    rule = client.post("/api/rules", json={"account_keyword": "x", "is_ignore_rule": True}).json()
    assert client.get("/api/rules").json()[0]["id"] == rule["id"]
    assert client.delete("/api/rules/%d" % rule["id"]).status_code == 200
    assert client.post("/api/seed").json() == {"message": "All data cleared successfully"}
    import seed_data
    assert seed_data.seed_default_data(None) is None   # documented no-op


def test_wbu_a08_create_tag_duplicate_branch(client):
    assert client.post("/api/tags", json={"name": "Food"}).status_code == 201
    r = client.post("/api/tags", json={"name": "  FOOD "})
    assert (r.status_code, r.json()["detail"]) == (400, "Tag with this name already exists")


def test_wbu_a09_frontend_and_favicon(client):
    """Static frontend mount, and favicon route `if os.path.exists(fav_path)` -> F (204)."""
    assert client.get("/").status_code == 200
    assert "<html" in client.get("/").text.lower()
    assert client.get("/favicon.ico").status_code == 204


# --------------------------------------------------------------------------
# parse-pdf endpoint: branches and the per-row loop
# --------------------------------------------------------------------------

class TestParsePdfEndpoint:
    def test_wbu_a10_not_a_pdf_filename(self, client):
        r = upload(client, b"hello", filename="notes.txt")
        assert (r.status_code, r.json()["detail"]) == (400, "File must be a PDF document.")

    def test_wbu_a11_parser_exception(self, client):
        r = upload(client, b"garbage")
        assert r.status_code == 400 and "Invalid PDF file" in r.json()["detail"]

    def test_wbu_a12_no_rows_extracted(self, client):
        r = upload(client, build_text_pdf(["Nothing here"]))
        assert r.status_code == 400 and "No transaction records" in r.json()["detail"]

    def test_wbu_a13_new_rows_with_rule_auto_match(self, client, make_tag, make_rule):
        """Rule loop: `if r.account_keyword and kw in account_name` T for row 1, F for row 2;
        dedup loop over an empty table (0 iterations)."""
        tag = make_tag("Food", color_hex="#FF6600", emoji="🍔")
        make_rule("ZOMATO", tag_id=tag.id)
        body = upload(client, build_text_pdf(gpay_statement_lines(STATEMENT))).json()
        assert (body["total_found"], body["new_count"], body["duplicate_count"]) == (2, 2, 0)
        zomato, rahul = body["transactions"]
        assert (zomato["tag_name"], zomato["tag_emoji"], zomato["is_duplicate"]) == ("Food", "🍔", False)
        assert (rahul["tag_id"], rahul["type"]) == (None, "CREDIT")

    @pytest.mark.parametrize("existing, is_dup", [
        (dict(amount=1, type="CREDIT", account_name="Other", raw_message="UPI ID: 111", ts=0), True),     # upi_match T
        (dict(amount=250, type="DEBIT", account_name=" zomato online ", raw_message="", ts=0), True),    # all 4 field conditions T
        (dict(amount=251, type="DEBIT", account_name="Zomato Online", raw_message="", ts=0), False),     # same_amt F
        (dict(amount=250, type="CREDIT", account_name="Zomato Online", raw_message="", ts=0), False),    # same_type F
        (dict(amount=250, type="DEBIT", account_name="Swiggy", raw_message="", ts=0), False),            # same_account F
        (dict(amount=250, type="DEBIT", account_name="Zomato Online", raw_message="", ts=6 * 60_000), False),  # same_time F
    ])
    def test_wbu_a14_duplicate_detection_against_db(self, client, make_tx, existing, is_dup):
        """Decision `upi_match or (same_amt and same_type and same_account and same_time)`."""
        make_tx(existing["amount"], existing["account_name"], type=existing["type"],
                raw_message=existing["raw_message"], timestamp=ms("13 Sep 2026 01:59 PM") + existing["ts"])
        body = upload(client, build_text_pdf(gpay_statement_lines(STATEMENT[:1]))).json()
        assert body["transactions"][0]["is_duplicate"] is is_dup
        assert body["duplicate_count"] == int(is_dup)


# --------------------------------------------------------------------------
# confirm-import endpoint
# --------------------------------------------------------------------------

def test_wbu_a15_confirm_import_loop_and_dedup(client):
    """Outer loop over requested rows, inner loop over existing rows; second call
    with the same rows takes the `is_already_in_db` T branch for every row;
    rows with timestamp/account None exercise the `or` defaults."""
    rows = [
        {"amount": 250, "type": "DEBIT", "account_name": "Zomato", "timestamp": ms("13 Sep 2026 01:59 PM")},
        {"amount": 99, "type": "DEBIT", "account_name": None, "sender_address": "SMS", "timestamp": None},
    ]
    assert client.post("/api/transactions/confirm-import", json={"transactions": rows}).json() == \
        {"message": "Successfully imported 2 transaction(s)."}
    assert client.post("/api/transactions/confirm-import", json={"transactions": rows[:1]}).json() == \
        {"message": "Successfully imported 0 transaction(s)."}
    # new row: inner loop compares against both existing rows, condition F each time (no break)
    fresh = {"amount": 5, "type": "DEBIT", "account_name": "Kirana", "timestamp": ms("14 Sep 2026 10:00 AM")}
    assert client.post("/api/transactions/confirm-import", json={"transactions": [fresh]}).json() == \
        {"message": "Successfully imported 1 transaction(s)."}
    assert client.post("/api/transactions/confirm-import", json={"transactions": []}).json() == \
        {"message": "Successfully imported 0 transaction(s)."}
    assert len(client.get("/api/transactions").json()) == 3
