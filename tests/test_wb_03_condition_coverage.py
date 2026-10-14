"""
White-box technique 3: CONDITION COVERAGE (incl. MC/DC-style cases)

Goal: every atomic condition inside a compound decision takes both TRUE and
FALSE, and (for the import de-duplication rule) each condition is shown to
independently change the decision's outcome.
"""

import pytest

from conftest import now_ms


def _history_names(app):
    return [h.get_attribute("textContent").strip()
            for h in app.els("#history-list-container h4")]


def test_wb_c01_history_search_or_conditions(app, api):
    """
    Decision (app.js renderHistory search filter):
        A: account_name includes q   ||   B: raw_message includes q   ||   C: tag_name includes q
    Inputs chosen so that each operand is the ONLY true one, then all false.
    """
    food = api.create_tag("Food")
    api.create_tx(250, "Zomato", raw_message="dinner")
    api.create_tx(120, "Amazon", raw_message="birthday gift")
    api.create_tx(90, "Corner Bakery", tag_id=food["id"])
    app.open()
    app.switch_tab("history")

    cases = [
        ("zomato", ["Zomato"]),            # A true, B false, C false
        ("birthday", ["Amazon"]),          # A false, B true,  C false
        ("food", ["Corner Bakery"]),       # A false, B false, C true
    ]
    for query, expected in cases:
        app.type("#input-search-tx", query)
        app.until(lambda: _history_names(app) == expected, "search %r" % query)
        assert app.state("searchQuery") == query

    app.type("#input-search-tx", "xyz-no-match")  # A, B, C all false
    app.until(lambda: "No transactions match your filter." in app.text("#history-list-container"))


def test_wb_c02_auto_tag_rule_match_conditions(app, api):
    """
    Decision (crud.create_transaction):
        r.account_keyword and ( kw in acc_name  or  kw in raw_message )
    Case 1: keyword in account name            -> tagged
    Case 2: keyword only in notes/raw_message  -> tagged
    Case 3: keyword in neither                 -> untagged
    Transactions are created through the UI modal (handleTransactionSubmit).
    """
    transport = api.create_tag("Transport")
    api.create_rule("UBER", tag_id=transport["id"])
    app.open()

    app.add_transaction_ui(180, "Uber India")
    app.add_transaction_ui(60, "Card Payment", notes="uber trip to office")
    app.add_transaction_ui(40, "Tea Stall", notes="chai")

    by_name = {t["account_name"]: t for t in app.state("transactions")}
    assert by_name["Uber India"]["tag_id"] == transport["id"]
    assert by_name["Card Payment"]["tag_id"] == transport["id"]
    assert by_name["Tea Stall"]["tag_id"] is None


def test_wb_c03_manual_tag_wins_over_rule(app, api):
    """
    Decision (crud.create_transaction): `if not is_tagged:` -> F
    The user picked a tag in the modal, so a matching tag rule must NOT override it.
    """
    food = api.create_tag("Food")
    gifts = api.create_tag("Gifts")
    api.create_rule("AMAZON", tag_id=gifts["id"])
    app.open()

    app.add_transaction_ui(350, "Amazon Fresh", tag_id=food["id"])
    tx = app.state("transactions[0]")
    assert tx["tag_id"] == food["id"]
    assert tx["tag_name"] == "Food"


def test_wb_c04_ignore_rule_condition_hides_transaction(app, api):
    """
    Decision (crud.create_transaction): `if r.is_ignore_rule:` -> T
    is_ignored=True rows are filtered by get_transactions / get_dashboard_stats
    (`is_ignored == False`), so the UI never shows them.
    """
    api.create_rule("SELF TRANSFER", is_ignore_rule=True)
    app.open()
    app.add_transaction_ui(100, "Kirana Store")          # creates a visible row
    app.click("#fab-add-tx")
    app.type("#tx-amount", "5000")
    app.type("#tx-account", "Self Transfer HDFC")
    app.submit("form-transaction")
    app.wait_toast("Transaction created!")
    app.reload_data()

    names = [t["account_name"] for t in app.state("transactions")]
    assert names == ["Kirana Store"]
    assert app.state("dashboardStats.total_expenditure") == 100


def test_wb_c05_untagged_filter_and_type_filter(app, api):
    """
    Decisions (app.js renderHistory)
      `state.activeTypeFilter !== 'ALL'`               -> F (All), T (Debits / Credits)
      `state.activeFilter === 'untagged'`              -> T
      `else if (state.activeFilter !== 'all')`         -> T (specific tag pill)
      untagged predicate `!t.tag_id || !t.is_tagged`   -> T for untagged row, F for tagged row
    """
    food = api.create_tag("Food")
    api.create_tx(500, "Swiggy", tag_id=food["id"])
    api.create_tx(80, "Parking")
    api.create_tx(20000, "Salary", tx_type="CREDIT")
    app.open()
    app.switch_tab("history")
    assert sorted(_history_names(app)) == ["Parking", "Salary", "Swiggy"]

    app.click('.tx-type-filter-btn[data-type="DEBIT"]')
    app.until(lambda: sorted(_history_names(app)) == ["Parking", "Swiggy"])
    app.click('.tx-type-filter-btn[data-type="CREDIT"]')
    app.until(lambda: _history_names(app) == ["Salary"])
    app.click('.tx-type-filter-btn[data-type="ALL"]')

    app.click('#history-filter-pills [data-filter="untagged"]')
    app.until(lambda: sorted(_history_names(app)) == ["Parking", "Salary"])
    assert app.state("activeFilter") == "untagged"

    app.click('#history-filter-pills [data-filter="%d"]' % food["id"])
    app.until(lambda: _history_names(app) == ["Swiggy"])

    app.click('#history-filter-pills [data-filter="all"]')
    app.until(lambda: len(_history_names(app)) == 3)


BASE = {"amount": 450.0, "type": "DEBIT", "account_name": "Dominos", "raw_message": "pizza"}


@pytest.mark.parametrize("label, change, expect_created", [
    ("identical row               -> all 4 conditions T -> duplicate", {}, 0),
    ("amount differs              -> same_amt F", {"amount": 451.0}, 1),
    ("type differs                -> same_type F", {"type": "CREDIT"}, 1),
    ("account differs             -> same_account F", {"account_name": "Pizza Hut"}, 1),
    ("account differs only by case/space -> same_account T", {"account_name": "  DOMINOS "}, 0),
    ("time 10 min later           -> same_time F", {"timestamp_offset": 10 * 60 * 1000}, 1),
    ("time 4 min later (boundary) -> same_time T", {"timestamp_offset": 4 * 60 * 1000}, 0),
])
def test_wb_c06_confirm_import_dedup_mcdc(app, api, label, change, expect_created):
    """
    Decision (main.py confirm_import_transactions):
        same_amt and same_type and same_account and same_time  -> skip insert
    MC/DC: starting from an all-TRUE duplicate, flip exactly one condition per
    case and show the outcome changes. Driven through the REST layer, result
    verified in the browser.
    """
    ts = now_ms()
    api.create_tx(timestamp=ts, tx_type=BASE["type"], amount=BASE["amount"],
                  account_name=BASE["account_name"], raw_message=BASE["raw_message"])

    row = dict(BASE, timestamp=ts + change.pop("timestamp_offset", 0))
    row.update(change)
    status, body = api.request("POST", "/api/transactions/confirm-import", {"transactions": [row]})
    assert status == 200
    assert body["message"] == "Successfully imported %d transaction(s)." % expect_created

    app.open()
    assert app.state("transactions.length") == 1 + expect_created, label
