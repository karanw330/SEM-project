"""
White-box technique 4: PATH COVERAGE

Goal: exercise complete independent paths through the control-flow graph of
the targeted features (see WHITE_BOX_TEST_PLAN.md for the CFGs and the
cyclomatic-complexity derivation of the basis paths).
"""

from datetime import datetime, timedelta

from conftest import days_ago_ms, now_ms
from pdf_factory import build_text_pdf, gpay_statement_lines


def test_wb_p01_history_grouping_today_yesterday_earlier(app, api):
    """
    renderHistory() grouping has 3 paths per transaction:
        P1 ts >= todayMs                        -> TODAY
        P2 todayMs > ts >= yesterdayMs          -> YESTERDAY
        P3 ts < yesterdayMs                     -> EARLIER
    """
    api.create_tx(10, "Today Shop", timestamp=now_ms())
    api.create_tx(20, "Yesterday Shop", timestamp=days_ago_ms(1))
    api.create_tx(30, "Old Shop", timestamp=days_ago_ms(10))
    app.open()
    app.switch_tab("history")

    groups = app.js("""
        return [...document.querySelectorAll('#history-list-container > div')].map(g => [
            g.querySelector('h3').textContent.trim(),
            [...g.querySelectorAll('h4')].map(h => h.textContent.trim())
        ]);
    """)
    assert groups == [
        ["TODAY", ["Today Shop"]],
        ["YESTERDAY", ["Yesterday Shop"]],
        ["EARLIER", ["Old Shop"]],
    ]


def test_wb_p02_pdf_import_new_then_duplicate_path(app, api, tmp_path):
    """
    Full GPay import path, then the duplicate path for the same statement:

      1st upload: handlePDFFile -> POST parse-pdf -> pdf_parser (Paid to / Received from
                  branches, UPI id) -> rule auto-match -> is_dup False -> preview (all checked)
                  -> confirm-import -> 2 rows inserted -> switchTab('history')
      2nd upload: same file -> `upi_match` True -> is_dup True -> preview (all unchecked)
                  -> confirm with nothing selected -> client-side error branch
                  -> "Toggle Select All" -> 2 selected
    """
    food = api.create_tag("Food", color_hex="#FF6600")
    api.create_rule("ZOMATO", tag_id=food["id"])
    pdf = tmp_path / "gpay_statement.pdf"
    pdf.write_bytes(build_text_pdf(gpay_statement_lines([
        {"date": "13 Sep, 2026", "time": "01:59 PM", "kind": "Paid to", "name": "ZomatoOnline",
         "amount": 250, "upi": "625679004115"},
        {"date": "14 Sep, 2026", "time": "09:46 AM", "kind": "Received from", "name": "Rahul",
         "amount": 1000, "upi": "521399859480"},
    ])))
    app.open()

    # ---- first import: everything is new ----
    app.click("#fab-add-tx")
    app.click("#btn-mode-pdf")
    app.upload("#pdf-file-input", str(pdf))
    app.wait_toast("Parsed 2 transaction(s)!")
    app.until(lambda: not app.has_class("#modal-pdf-preview", "hidden"))
    assert app.text("#pdf-stat-total") == "Total: 2"
    assert app.text("#pdf-stat-new") == "New: 2"
    assert app.text("#pdf-stat-dup") == "Duplicates: 0"
    assert app.text("#pdf-selected-count") == "2 transaction(s) selected"
    preview = app.text("#pdf-preview-list")
    assert "Zomato Online" in preview and "Food" in preview  # camel-case split + rule auto-tag

    app.click("#pdf-btn-confirm-import")
    app.wait_toast("Successfully imported 2 transaction(s).")
    app.until(lambda: app.state("activeTab") == "history")
    txs = {t["account_name"]: t for t in app.state("transactions")}
    assert txs["Zomato Online"]["type"] == "DEBIT"
    assert txs["Zomato Online"]["tag_id"] == food["id"]
    assert "UPI ID: 625679004115" in txs["Zomato Online"]["raw_message"]
    assert txs["Rahul"]["type"] == "CREDIT"

    # ---- second import of the same file: duplicate path ----
    app.click("#fab-add-tx")
    app.click("#btn-mode-pdf")
    app.js("document.getElementById('pdf-file-input').value = '';")
    app.upload("#pdf-file-input", str(pdf))
    app.until(lambda: app.text("#pdf-stat-dup") == "Duplicates: 2")
    assert app.text("#pdf-stat-new") == "New: 0"
    assert app.text("#pdf-selected-count") == "0 transaction(s) selected"

    app.click("#pdf-btn-confirm-import")
    text, is_error = app.wait_toast("Please select at least one transaction to import.")
    assert is_error

    app.click("#pdf-btn-toggle-all")
    assert app.text("#pdf-selected-count") == "2 transaction(s) selected"
    app.click("#pdf-btn-toggle-all")
    assert app.text("#pdf-selected-count") == "0 transaction(s) selected"


def test_wb_p03_rule_lifecycle_reevaluation_paths(app, api):
    """
    crud.reevaluate_all_transactions() per-transaction paths:
        P1 no rule matches                 -> is_ignored reset to False, tag left as is
        P2 tag rule matches                -> tag_id = rule.tag_id
        P3 ignore rule matches             -> is_ignored True, tag cleared
    Driven by: create rule (apply_single_rule_to_existing), delete rule, "Apply Rules".
    """
    subs = api.create_tag("Subscriptions")
    api.create_tx(649, "Netflix")
    app.open()

    # P2 via create rule in the UI (apply_single_rule_to_existing on existing rows)
    app.add_rule_ui("netflix", tag_id=subs["id"])
    app.wait_toast("Auto-tag rule created & applied!")
    app.until(lambda: app.state("transactions[0].tag_id") == subs["id"])

    # Delete the tag rule -> reevaluate: P1 (tag kept, documented behaviour)
    rule_id = app.state("rules[0].id")
    app.click('.btn-delete-rule[data-id="%d"]' % rule_id)
    app.answer_confirm(True)
    app.wait_toast("Rule deleted")
    app.until(lambda: app.state("rules.length") == 0)
    assert app.state("transactions[0].tag_id") == subs["id"]

    # P3: ignore rule hides the transaction
    app.add_rule_ui("NETFLIX", ignore=True)
    app.wait_toast("Vendor ignore rule created & applied!")
    app.until(lambda: app.state("transactions.length") == 0)
    assert app.text("#dash-total-spent") == "₹0.00"

    # Deleting the ignore rule -> reevaluate resets is_ignored -> row comes back (P1)
    rule_id = app.state("rules[0].id")
    app.click('.btn-delete-rule[data-id="%d"]' % rule_id)
    app.answer_confirm(True)
    app.until(lambda: app.state("transactions.length") == 1)
    assert app.state("transactions[0].tag_id") is None  # ignore rule cleared the tag

    # "Apply Rules" button with a new tag rule created via API -> P2 for all rows
    api.create_rule("NETFLIX", tag_id=subs["id"])
    api.request("PUT", "/api/transactions/%d/tag" % app.state("transactions[0].id"), {"tag_id": None})
    app.reload_data()
    app.switch_tab("rules")
    app.click("#btn-apply-all-rules")
    app.wait_toast("Applied rules to 1 transactions")
    app.until(lambda: app.state("transactions[0].tag_id") == subs["id"])


def test_wb_p04_delete_tag_untags_its_transactions(app, api):
    """
    crud.delete_tag(): `UPDATE transactions SET tag_id=NULL, is_tagged=False WHERE tag_id=?`
    then delete. Path continues into renderDashboard banner branch (untagged_count 0 -> 1).
    """
    bills = api.create_tag("Bills")
    api.create_tx(1500, "Airtel", tag_id=bills["id"])
    app.open()
    assert app.has_class("#untagged-banner", "hidden")

    app.switch_tab("tags")
    assert "1 transaction" in app.text("#tags-grid-container")
    app.click('.btn-delete-tag[data-id="%d"]' % bills["id"])
    app.answer_confirm(True)
    app.wait_toast("Tag deleted")
    app.until(lambda: app.state("tags.length") == 0)

    tx = app.state("transactions[0]")
    assert tx["tag_id"] is None and tx["is_tagged"] is False
    assert not app.has_class("#untagged-banner", "hidden")


def test_wb_p05_inline_tag_selector_set_and_clear(app, api):
    """
    attachTransactionItemListeners .btn-tag-selector change handler:
        `select.value ? parseInt(...) : null`  -> tag id path, then null path
    crud.update_transaction_tag: is_tagged = tag_id is not None  -> T, then F
    """
    travel = api.create_tag("Travel")
    tx = api.create_tx(2200, "IRCTC")
    app.open()
    app.switch_tab("history")

    sel = '#history-list-container .btn-tag-selector[data-id="%d"]' % tx["id"]
    app.select(sel, travel["id"])
    app.wait_toast("Transaction tag updated")
    app.until(lambda: app.state("transactions[0].tag_id") == travel["id"])
    assert app.state("transactions[0].is_tagged") is True

    app.select(sel, "")
    app.until(lambda: app.state("transactions[0].tag_id") is None)
    assert app.state("transactions[0].is_tagged") is False


def test_wb_p06_dashboard_range_paths(app, api):
    """
    getRangeTimestamps() paths (anchored at the latest transaction):
        selectedMonth === 'all'  -> no bounds
        range 'week'             -> anchor - 6 days
        range 'month'            -> 1st of anchor month
        range 'year'             -> 1st Jan of anchor year
    crud.get_dashboard_stats: `if start_ts is not None` -> T (week/month/year), F (all)
    """
    anchor = datetime(2026, 6, 20, 12, 0, 0)
    ms = lambda d: int(d.timestamp() * 1000)
    api.create_tx(100, "In week", timestamp=ms(anchor))
    api.create_tx(200, "In month", timestamp=ms(anchor - timedelta(days=12)))   # Jun 8
    api.create_tx(400, "In year", timestamp=ms(datetime(2026, 2, 1, 12)))
    api.create_tx(800, "Last year", timestamp=ms(datetime(2025, 12, 31, 12)))
    app.open()

    def spent():
        return app.state("dashboardStats.total_expenditure")

    assert spent() == 300                        # default: month
    app.click('.range-btn[data-range="week"]')
    app.until(lambda: spent() == 100)
    app.click('.range-btn[data-range="year"]')
    app.until(lambda: spent() == 700)
    app.click('.range-btn[data-range="month"]')
    app.until(lambda: spent() == 300)
    app.select("#select-month", "all")
    app.until(lambda: spent() == 1500)
    assert app.text("#dash-total-spent") == "₹1,500.00"


def test_wb_p07_review_untagged_banner_navigates_with_filter(app, api):
    """
    #btn-review-untagged handler path: switchTab('history') -> setHistoryFilter('untagged')
    -> renderHistory untagged branch.
    """
    tag = api.create_tag("Health")
    api.create_tx(300, "Apollo Pharmacy", tag_id=tag["id"])
    api.create_tx(120, "Unknown UPI")
    app.open()

    app.click("#btn-review-untagged")
    app.until(lambda: app.state("activeTab") == "history")
    assert app.state("activeFilter") == "untagged"
    assert not app.has_class("#view-history", "hidden")
    assert app.has_class("#view-dashboard", "hidden")
    names = [h.get_attribute("textContent").strip() for h in app.els("#history-list-container h4")]
    assert names == ["Unknown UPI"]
