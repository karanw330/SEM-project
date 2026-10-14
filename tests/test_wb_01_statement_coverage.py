"""
White-box technique 1: STATEMENT COVERAGE

Goal: every executable statement of the targeted functions runs at least
once. Each test names the functions (and the source lines) it is designed
to execute; the coverage report printed at the end of the run confirms it.
"""


def test_wb_s01_empty_dashboard_executes_all_empty_state_statements(app):
    """
    Targets
      backend/crud.py  get_dashboard_stats(): `top_tx = ... if debits else None`,
                       `anchor_dt = ... else datetime.now()`, `if max_day == 0: max_day = 1.0`
      frontend app.js  renderDashboard() else-branch for top expense,
                       renderCategoryGrid() / renderRecentOperations() empty-state statements,
                       renderDonutChart() early return
    """
    stats = app.state("dashboardStats")
    assert stats["total_expenditure"] == 0
    assert stats["top_expenditure"] is None
    assert len(stats["daily_trend"]) == 7
    # max_day was forced to 1.0, so every bar percentage is 0 (no ZeroDivisionError)
    assert all(day["percentage"] == 0 for day in stats["daily_trend"])

    assert app.text("#dash-total-spent") == "₹0.00"
    assert app.text("#dash-top-name") == "None"
    assert app.text("#dash-top-amount") == "₹0.00"
    assert app.has_class("#untagged-banner", "hidden")
    assert "No category data yet." in app.text("#dash-category-grid")
    assert "No recent transactions." in app.text("#dash-recent-list")
    # Only the background ring is drawn, no segments
    assert len(app.els("#donut-svg .donut-segment")) == 0


def test_wb_s02_empty_lists_on_every_tab(app):
    """
    Targets app.js renderHistory(), renderTags(), renderRules() empty-state statements.
    """
    app.switch_tab("history")
    assert "No transactions match your filter." in app.text("#history-list-container")
    app.switch_tab("tags")
    assert "No tags created yet." in app.text("#tags-grid-container")
    app.switch_tab("rules")
    assert "No auto-tag rules configured yet." in app.text("#rules-list-container")


def test_wb_s03_create_transaction_through_modal(app):
    """
    Targets
      app.js   openTransactionModal(), handleTransactionSubmit() (create path), showToast()
      main.py  create_transaction()
      crud.py  create_transaction() and _enrich_transaction()
    """
    app.add_transaction_ui(499.5, "Cafe Coffee Day", notes="Cold coffee")
    text, is_error = app.wait_toast("Transaction created!")
    assert not is_error

    tx = app.state("transactions[0]")
    assert tx["account_name"] == "Cafe Coffee Day"
    assert tx["type"] == "DEBIT"
    assert tx["raw_message"] == "Cold coffee"
    # _enrich_transaction(): untagged rows get the placeholder name/colour/emoji
    assert tx["tag_name"] == "Untagged"
    assert tx["tag_color"] == "#95A5A6"

    app.until(lambda: app.text("#dash-total-spent") == "₹499.50")
    assert "Cafe Coffee Day" in app.text("#dash-recent-list")
    assert app.text("#dash-top-name") == "Cafe Coffee Day"


def test_wb_s04_create_tag_through_modal(app):
    """
    Targets
      app.js   openTagModal(), handleTagSubmit() (create path), renderTags(),
               renderHistoryFilterPills(), populateTagSelectDropdowns()
      main.py  create_tag(); crud.py create_tag()
    """
    app.add_tag_ui("Groceries", color="#22AA55")
    app.wait_toast("Tag created!")
    app.until(lambda: app.state("tags.length") == 1)

    tag = app.state("tags[0]")
    assert tag["name"] == "Groceries"
    assert tag["color_hex"] == "#22AA55"
    assert "Groceries" in app.text("#tags-grid-container")
    assert "0 transactions" in app.text("#tags-grid-container")
    # The new tag is offered everywhere tags can be chosen
    assert app.els('#tx-tag option[value="%d"]' % tag["id"])
    assert app.els('#rule-tag option[value="%d"]' % tag["id"])
    assert app.els('#history-filter-pills [data-filter="%d"]' % tag["id"])


def test_wb_s05_create_tag_rule_through_modal(app, api):
    """
    Targets
      app.js   openRuleModal(), handleRuleSubmit() (TAG path), renderRules()
      main.py  create_rule() happy path; crud.py create_rule(), apply_single_rule_to_existing()
    """
    tag = api.create_tag("Food", emoji="🍔", color_hex="#FF6600")
    app.open()
    app.add_rule_ui("  zomato ", tag_id=tag["id"])
    app.wait_toast("Auto-tag rule created & applied!")
    app.until(lambda: app.state("rules.length") == 1)

    rule = app.state("rules[0]")
    # crud.create_rule(): keyword is stripped and upper-cased before storage
    assert rule["account_keyword"] == "ZOMATO"
    assert rule["tag_id"] == tag["id"]
    assert '"ZOMATO"' in app.text("#rules-list-container")
    assert "Food" in app.text("#rules-list-container")
