"""
White-box technique 2: BRANCH (DECISION) COVERAGE

Goal: every decision in the targeted code evaluates to both TRUE and FALSE
at least once. Each test lists the decision(s) and which outcome each step
forces.
"""

import os

from conftest import now_ms
from pdf_factory import build_text_pdf


def test_wb_b01_untagged_banner_hidden_singular_plural(app, api):
    """
    Decision (app.js renderDashboard):
        if (stats.untagged_count > 0)            -> F, then T
        untagged_count > 1 ? 's' : ''            -> F (1 expense), then T (2 expenses)
    Backend: crud.get_dashboard_stats  `not t.tag_id or not t.is_tagged`
    """
    assert app.has_class("#untagged-banner", "hidden")

    api.create_tx(100, "Shop A")
    app.open()
    assert not app.has_class("#untagged-banner", "hidden")
    assert app.text("#untagged-banner-text") == "You have 1 expense without categories."

    api.create_tx(200, "Shop B")
    app.open()
    assert app.text("#untagged-banner-text") == "You have 2 expenses without categories."


def test_wb_b02_top_expense_with_and_without_debits(app, api):
    """
    Decisions
      crud.get_dashboard_stats: `max(debits) if debits else None`   -> F (credits only), then T
      app.js renderDashboard:   `if (stats.top_expenditure)`         -> F, then T
    Also checks credits are excluded from total_expenditure.
    """
    api.create_tx(5000, "Salary", tx_type="CREDIT")
    app.open()
    assert app.state("dashboardStats.top_expenditure") is None
    assert app.text("#dash-top-name") == "None"
    assert app.text("#dash-total-spent") == "₹0.00"
    assert app.state("dashboardStats.total_income") == 5000

    api.create_tx(300, "Book Store")
    api.create_tx(1200, "Electronics")
    app.open()
    assert app.text("#dash-top-name") == "Electronics"
    assert app.text("#dash-top-amount") == "₹1,200.00"
    assert app.text("#dash-total-spent") == "₹1,500.00"


def test_wb_b03_delete_transaction_confirm_cancel_and_accept(app, api):
    """
    Decision (app.js attachTransactionItemListeners): `if (id && confirm(...))`
        confirm -> false: nothing deleted
        confirm -> true : DELETE /api/transactions/{id}, crud.delete_transaction soft-deletes
    """
    api.create_tx(75, "Metro Card")
    app.open()
    app.switch_tab("history")

    app.click("#history-list-container .btn-delete-tx")
    app.answer_confirm(accept=False)
    assert app.state("transactions.length") == 1

    app.click("#history-list-container .btn-delete-tx")
    app.answer_confirm(accept=True)
    app.wait_toast("Transaction deleted")
    app.until(lambda: app.state("transactions.length") == 0)
    # Soft delete: hidden from the API listing as well
    assert api.transactions() == []


def test_wb_b04_tag_modal_create_vs_edit(app, api):
    """
    Decisions (app.js)
      openTagModal: `tagToEdit ? 'Edit Tag' : 'Add New Tag'`   -> T
      handleTagSubmit: `if (editId)`                            -> T (update path)
    Backend: crud.update_tag `if tag_update.name is not None` etc. -> T
    """
    tag = api.create_tag("Travl", color_hex="#123456")
    app.open()
    app.switch_tab("tags")
    app.click('#tags-grid-container .btn-edit-tag[data-id="%d"]' % tag["id"])
    app.until(lambda: not app.has_class("#modal-tag", "hidden"))

    assert app.text("#modal-tag-title") == "Edit Tag"
    assert app.el("#tag-edit-id").get_attribute("value") == str(tag["id"])
    assert app.el("#tag-name").get_attribute("value") == "Travl"

    app.type("#tag-name", "Travel")
    app.submit("form-tag")
    app.wait_toast("Tag updated!")
    app.until(lambda: app.state("tags[0].name") == "Travel")
    assert app.state("tags.length") == 1  # updated, not duplicated


def test_wb_b05_duplicate_tag_name_is_rejected_case_insensitively(app, api):
    """
    Decision (main.py create_tag): `if existing:` (ilike match)  -> T
    Frontend: handleTagSubmit catch-branch shows an error toast.
    """
    api.create_tag("Food")
    app.open()
    app.add_tag_ui("  fOOd  ")
    text, is_error = app.wait_toast("already exists")
    assert is_error
    assert "Tag with this name already exists" in text
    assert app.state("tags.length") == 1


def test_wb_b06_rule_type_tag_without_tag_vs_ignore_rule(app):
    """
    Decisions
      main.py create_rule: `if not rule_data.is_ignore_rule:` -> T, then `if not rule_data.tag_id` -> T (400)
      main.py create_rule: `if not rule_data.is_ignore_rule:` -> F (ignore rule path)
      app.js rule-type radio listener: `e.target.value === 'IGNORE'` -> T / F
      app.js handleRuleSubmit: `is_ignore_rule ? ... : ...` toast text
    With no tags created the tag <select> is empty, so tag_id is null.
    """
    app.add_rule_ui("NETFLIX")
    text, is_error = app.wait_toast("tag_id is required")
    assert is_error
    assert app.state("rules.length") == 0

    # Radio toggles the tag picker visibility (both outcomes)
    app.click("#rule-type-ignore")
    assert app.has_class("#rule-tag-container", "hidden")
    app.click("#rule-type-tag")
    assert not app.has_class("#rule-tag-container", "hidden")

    app.click("#rule-type-ignore")
    app.submit("form-rule")
    app.wait_toast("Vendor ignore rule created & applied!")
    app.until(lambda: app.state("rules.length") == 1)
    rule = app.state("rules[0]")
    assert rule["is_ignore_rule"] is True
    assert rule["tag_id"] is None
    assert "IGNORE TRANSACTIONS" in app.text("#rules-list-container")


def test_wb_b07_duplicate_rule_keyword_after_normalisation(app, api):
    """
    Decision (main.py create_rule): `if existing:` after `.strip().upper()` -> T
    """
    tag = api.create_tag("Food")
    api.create_rule("SWIGGY", tag_id=tag["id"])
    app.open()
    app.add_rule_ui("  swiggy ", tag_id=tag["id"])
    text, is_error = app.wait_toast("already exists")
    assert is_error
    assert "Rule for keyword 'SWIGGY' already exists" in text


def test_wb_b08_not_found_branches_of_every_endpoint(api):
    """
    Decisions that the UI cannot reach (ids always come from the server),
    so they are driven directly through the REST layer:
      main.py update_transaction / update_transaction_tag / delete_transaction: `if not updated/success` -> T
      main.py update_tag / delete_tag / delete_rule:                             `if not ...`            -> T
      main.py create_rule: `if not tag:` (tag id does not exist)                                         -> T
    """
    missing = 999999
    assert api.request("PUT", "/api/transactions/%d" % missing, {"amount": 1})[0] == 404
    assert api.request("PUT", "/api/transactions/%d/tag" % missing, {"tag_id": None})[0] == 404
    assert api.request("DELETE", "/api/transactions/%d" % missing)[0] == 404
    assert api.request("PUT", "/api/tags/%d" % missing, {"name": "x"})[0] == 404
    assert api.request("DELETE", "/api/tags/%d" % missing)[0] == 404
    assert api.request("DELETE", "/api/rules/%d" % missing)[0] == 404
    status, body = api.create_rule("AMAZON", tag_id=missing)
    assert status == 404 and body["detail"] == "Tag not found"


def test_wb_b09_theme_toggle_both_branches_and_persistence(app):
    """
    Decisions (app.js)
      initTheme:   `if (state.isDarkMode)`             -> F on first load, T after toggle + reload
      toggleTheme: `state.isDarkMode ? 'dark' : 'light'` -> both
    """
    html_classes = lambda: app.js("return document.documentElement.className;").split()
    assert "dark" not in html_classes()
    assert app.text("#theme-icon") == "dark_mode"

    app.click("#btn-theme-toggle")
    assert "dark" in html_classes()
    assert app.text("#theme-icon") == "light_mode"
    assert app.js("return localStorage.getItem('fc_theme');") == "dark"

    app.open()  # reload: state.isDarkMode is read back from localStorage
    assert app.state("isDarkMode") is True
    assert "dark" in html_classes()

    app.click("#btn-theme-toggle")
    assert "dark" not in html_classes()
    assert app.js("return localStorage.getItem('fc_theme');") == "light"


def test_wb_b10_transaction_modal_mode_switch(app):
    """
    Decision (app.js switchTxModalMode): `if (mode === 'pdf')` -> T, then F
    """
    app.click("#fab-add-tx")
    app.until(lambda: not app.has_class("#modal-transaction", "hidden"))
    assert app.text("#modal-tx-title") == "Add New Transaction"
    assert app.has_class("#tx-panel-pdf", "hidden")

    app.click("#btn-mode-pdf")
    assert app.has_class("#tx-panel-manual", "hidden")
    assert not app.has_class("#tx-panel-pdf", "hidden")

    app.click("#btn-mode-manual")
    assert not app.has_class("#tx-panel-manual", "hidden")
    assert app.has_class("#tx-panel-pdf", "hidden")


def test_wb_b11_pdf_upload_error_branches(app, tmp_path):
    """
    Decisions
      app.js handlePDFFile: `!file.name.toLowerCase().endsWith('.pdf')`         -> T (client-side reject)
      pdf_parser.parse_gpay_pdf: PdfReader raises -> ValueError                -> main.py except-branch (400)
      main.py parse_gpay_pdf_endpoint: `if not extracted_txs:`                 -> T (valid PDF, no rows)
    """
    not_pdf = tmp_path / "statement.txt"
    not_pdf.write_text("hello")
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"this is not really a pdf")
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(build_text_pdf(["Google Pay statement", "No activity this month"]))

    app.click("#fab-add-tx")
    app.click("#btn-mode-pdf")

    app.upload("#pdf-file-input", str(not_pdf))
    text, is_error = app.wait_toast("Please select a valid PDF document.")
    assert is_error

    app.js("document.getElementById('pdf-file-input').value = '';")
    app.upload("#pdf-file-input", str(corrupt))
    text, is_error = app.wait_toast("Invalid PDF file")
    assert is_error

    app.js("document.getElementById('pdf-file-input').value = '';")
    app.upload("#pdf-file-input", str(empty))
    text, is_error = app.wait_toast("No transaction records could be extracted")
    assert is_error
    assert app.has_class("#modal-pdf-preview", "hidden")


def test_wb_b12_clear_all_data_confirm_cancel_and_accept(app, api):
    """
    Decision (app.js #btn-seed handler): `if (confirm(...))` -> F, then T
    Backend: main.seed_demo -> seed_data.clear_all_data()
    """
    api.create_tag("Bills")
    api.create_tx(999, "Electricity Board", timestamp=now_ms())
    app.open()

    app.click("#btn-seed")
    app.answer_confirm(accept=False)
    assert app.state("transactions.length") == 1

    app.click("#btn-seed")
    app.answer_confirm(accept=True)
    app.wait_toast("All data cleared successfully!")
    app.until(lambda: app.state("transactions.length") == 0 and app.state("tags.length") == 0)


def test_wb_b13_edit_transaction_branch_via_internal_call(app, api):
    """
    Decisions (app.js)
      openTransactionModal: `txToEdit ? 'Edit Transaction' : ...`   -> T
      handleTransactionSubmit: `if (editId)`                        -> T (update path)
    Backend: crud.update_transaction, every `if update_data.X is not None` -> T

    Finding: no UI control ever calls openTransactionModal(tx), so the edit path is
    unreachable for users. White-box knowledge lets us call it directly to test it.
    """
    food = api.create_tag("Food")
    api.create_tx(100, "Dominos", raw_message="pizza")
    app.open()

    app.js("openTransactionModal(state.transactions[0]);")
    app.until(lambda: not app.has_class("#modal-transaction", "hidden"))
    assert app.text("#modal-tx-title") == "Edit Transaction"
    assert app.el("#tx-account").get_attribute("value") == "Dominos"

    app.type("#tx-amount", "180")
    app.select("#tx-type", "CREDIT")
    app.type("#tx-account", "Dominos Refund")
    app.type("#tx-notes", "refund")
    app.select("#tx-tag", food["id"])
    app.submit("form-transaction")
    app.wait_toast("Transaction updated!")
    app.until(lambda: app.state("transactions[0].amount") == 180)

    tx = app.state("transactions[0]")
    assert app.state("transactions.length") == 1
    assert (tx["type"], tx["account_name"], tx["raw_message"], tx["tag_id"], tx["is_tagged"]) == \
        ("CREDIT", "Dominos Refund", "refund", food["id"], True)


def test_wb_b14_server_side_transaction_filters(api):
    """
    Decisions (crud.get_transactions): `if start_ts`, `if end_ts`, `if tx_type`,
    `if untagged_only` / `elif tag_id`, `if search`  -> each T at least once.

    Finding: the SPA filters in the browser and never sends these query params,
    so these branches are only reachable through the REST layer.
    """
    food = api.create_tag("Food")
    api.create_tx(10, "Old", timestamp=1_000_000)
    api.create_tx(20, "Pizza Place", tag_id=food["id"], timestamp=2_000_000)
    api.create_tx(30, "Employer", tx_type="CREDIT", timestamp=3_000_000)

    names = lambda **q: sorted(t["account_name"] for t in api.transactions(**q))
    assert names(start_ts=1_500_000) == ["Employer", "Pizza Place"]
    assert names(end_ts=1_500_000) == ["Old"]
    assert names(tx_type="credit") == ["Employer"]
    assert names(untagged_only="true") == ["Employer", "Old"]
    assert names(tag_id=food["id"]) == ["Pizza Place"]
    assert names(search="Pizza") == ["Pizza Place"]
