"""
White-box technique 5: LOOP TESTING

Simple-loop strategy: run each loop 0 times, once, a typical number of times,
and at / just past its bound (n-1, n, n+1).
"""

import pytest

from conftest import days_ago_ms, now_ms


@pytest.mark.parametrize("n_tx, expected_rows", [(0, 0), (1, 1), (4, 4), (5, 5), (6, 5)])
def test_wb_l01_recent_operations_slice_bound(app, api, n_tx, expected_rows):
    """
    Loop: renderRecentOperations() renders `state.transactions.slice(0, 5)`.
    Bound n = 5 -> test 0, 1, n-1, n, n+1 iterations.
    """
    for i in range(n_tx):
        api.create_tx(10 * (i + 1), "Vendor %d" % i, timestamp=now_ms() - i * 1000)
    app.open()

    rows = app.els("#dash-recent-list .btn-delete-tx")
    assert len(rows) == expected_rows
    if n_tx == 0:
        assert "No recent transactions." in app.text("#dash-recent-list")
    else:
        # newest first (ORDER BY timestamp DESC)
        assert app.els("#dash-recent-list h4")[0].get_attribute("textContent").strip() == "Vendor 0"


def test_wb_l02_daily_trend_fixed_seven_iterations(app, api):
    """
    Loop: crud.get_dashboard_stats  `for i in range(6, -1, -1)`  (always 7 iterations),
    plus the inner generator summing debits per day. Front-end renderDailyTrend() maps
    the same 7 items to bars (min height 10%).
    """
    api.create_tx(100, "Day -2", timestamp=days_ago_ms(2))
    api.create_tx(400, "Today A", timestamp=now_ms())
    api.create_tx(100, "Today B", timestamp=now_ms() - 1000)
    api.create_tx(9999, "Credit ignored", tx_type="CREDIT", timestamp=now_ms())
    app.open()
    app.select("#select-month", "all")
    app.until(lambda: app.state("selectedMonth") == "all")

    trend = app.state("dashboardStats.daily_trend")
    assert len(trend) == 7
    assert len(app.els("#trend-bars-container > div")) == 7
    assert len(app.els("#trend-labels-container span")) == 7

    # last iteration (i = 0) is the anchor day = day of the latest debit
    assert trend[-1]["total_amount"] == 500     # 400 + 100, credit excluded
    assert trend[-1]["percentage"] == 100
    assert trend[-3]["total_amount"] == 100
    assert trend[-3]["percentage"] == 20
    assert [d["day_label"] for d in trend] == [s.get_attribute("textContent").strip()
                                               for s in app.els("#trend-labels-container span")]


@pytest.mark.parametrize("rules, expected_tag", [
    ([], None),                                          # loop body runs 0 times
    ([("UBER", "Transport")], "Transport"),              # 1 iteration, match
    ([("OLA", "Transport"), ("SWIGGY", "Food")], None),  # many iterations, no match
    ([("UBER", "Transport"), ("UBER EATS", "Food")], "Transport"),  # early `break` on first match
])
def test_wb_l03_create_transaction_rule_loop(app, api, rules, expected_tag):
    """
    Loop: crud.create_transaction  `for r in rules: ... break`
    The last case documents that the loop stops at the FIRST matching rule (by id),
    so a broader keyword created earlier beats a more specific one.
    """
    tags = {}
    for kw, tag_name in rules:
        if tag_name not in tags:
            tags[tag_name] = api.create_tag(tag_name)
        status, _ = api.create_rule(kw, tag_id=tags[tag_name]["id"])
        assert status == 201
    app.open()

    app.add_transaction_ui(320, "Uber Eats Order")
    assert app.state("transactions[0].tag_name") == (expected_tag or "Untagged")


@pytest.mark.parametrize("n_categories", [1, 3])
def test_wb_l04_donut_segments_one_per_category(app, api, n_categories):
    """
    Loop: renderDonutChart() `tagTotals.forEach` -> one <circle.donut-segment> per category,
    each with mouseenter/mouseleave handlers that swap the centre label.
    """
    for i in range(n_categories):
        tag = api.create_tag("Cat%d" % i, color_hex="#%06X" % (0x111111 * (i + 1)))
        api.create_tx(100 * (i + 1), "Shop %d" % i, tag_id=tag["id"])
    app.open()

    segments = app.els("#donut-svg .donut-segment")
    assert len(segments) == n_categories
    assert len(app.state("dashboardStats.tag_totals")) == n_categories
    # tag_totals sorted DESC by amount -> first segment is the largest category
    assert segments[0].get_attribute("data-category").endswith("Cat%d" % (n_categories - 1))

    app.js("arguments[0].dispatchEvent(new Event('mouseenter'));", segments[0])
    assert app.text("#center-label").endswith("Cat%d" % (n_categories - 1))
    app.js("arguments[0].dispatchEvent(new Event('mouseleave'));", segments[0])
    assert app.text("#center-label") == "Total Expenditure"


def test_wb_l05_tag_card_counts_and_pluralisation(app, api):
    """
    Loop: renderTags() `state.tags.map(...)` with an inner filter loop counting transactions;
    ternary `txCount !== 1 ? 's' : ''` -> 0, 1 and many.
    """
    a = api.create_tag("A-Zero")
    b = api.create_tag("B-One")
    c = api.create_tag("C-Three")
    api.create_tx(1, "x1", tag_id=b["id"])
    for i in range(3):
        api.create_tx(1, "y%d" % i, tag_id=c["id"])
    app.open()
    app.switch_tab("tags")

    cards = app.js("""
        return [...document.querySelectorAll('#tags-grid-container h3')].map(h =>
            [h.textContent.trim(), h.nextElementSibling.textContent.trim()]);
    """)
    assert cards == [
        ["A-Zero", "0 transactions"],
        ["B-One", "1 transaction"],
        ["C-Three", "3 transactions"],
    ]
