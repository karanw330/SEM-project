"""
White-box unit tests for backend/crud.py

Units: create_transaction(), reevaluate_all_transactions(),
       apply_single_rule_to_existing(), apply_all_rules(), tag/rule CRUD,
       get_transactions(), update_transaction(), _enrich_transaction(),
       get_dashboard_stats()
Techniques: basis-path coverage, branch coverage, condition coverage, loop testing.
"""

from datetime import datetime, timedelta

import pytest

import crud
import models
import schemas


# --------------------------------------------------------------------------
# create_transaction(): basis paths (V(G) = 6, see WHITE_BOX_UNIT_REPORT.md)
# --------------------------------------------------------------------------

class TestCreateTransactionPaths:
    def test_wbu_t01_p1_no_account_name_skips_rules(self, db, make_tag, make_rule):
        """P1: `if acc_name:` -> F. Unreachable from the UI (sender defaults to MANUAL),
        but reachable here by passing an empty sender."""
        tag = make_tag("Food")
        make_rule("ZOMATO", tag_id=tag.id)
        tx = crud.create_transaction(db, schemas.TransactionCreate(
            amount=10, account_name=None, sender_address="", raw_message="zomato order"))
        assert tx.tag_id is None and tx.is_tagged is False

    def test_wbu_t02_p2_no_rules_loop_zero(self, make_tx):
        """P2: rule loop runs 0 times."""
        tx = make_tx(10, "Zomato")
        assert (tx.tag_id, tx.tag_name, tx.is_ignored) == (None, "Untagged", False)

    def test_wbu_t03_p3_rules_without_match(self, make_tag, make_rule, make_tx):
        """P3: loop runs, match condition always F."""
        tag = make_tag("Food")
        make_rule("SWIGGY", tag_id=tag.id)
        make_rule("DOMINOS", tag_id=tag.id)
        assert make_tx(10, "Zomato").tag_id is None

    def test_wbu_t04_p4_ignore_rule(self, make_tag, make_rule, make_tx):
        """P4: match T, `if r.is_ignore_rule` T -> ignored, tag cleared even if given."""
        tag = make_tag("Food")
        make_rule("SELF", is_ignore_rule=True)
        tx = make_tx(10, "Self transfer", tag_id=tag.id)
        assert (tx.is_ignored, tx.tag_id, tx.is_tagged) == (True, None, False)

    def test_wbu_t05_p5_tag_rule_applies(self, make_tag, make_rule, make_tx):
        """P5: match T, ignore F, `if not is_tagged` T -> auto-tag."""
        tag = make_tag("Food")
        make_rule("ZOMATO", tag_id=tag.id)
        tx = make_tx(10, "Zomato Online")
        assert (tx.tag_id, tx.tag_name, tx.is_tagged) == (tag.id, "Food", True)

    def test_wbu_t06_p6_manual_tag_kept(self, make_tag, make_rule, make_tx):
        """P6: match T, ignore F, `if not is_tagged` F -> manual tag kept."""
        food, gifts = make_tag("Food"), make_tag("Gifts")
        make_rule("AMAZON", tag_id=gifts.id)
        assert make_tx(10, "Amazon", tag_id=food.id).tag_id == food.id


class TestCreateTransactionConditions:
    @pytest.mark.parametrize("account, message, matched", [
        ("Uber India", "", True),            # kw in acc_name T
        ("Card", "uber ride", True),         # kw in acc_name F, raw_message T
        ("Card", "", False),                 # raw_message falsy -> short-circuit F
        ("Card", "tea", False),              # both F
    ])
    def test_wbu_t07_match_condition(self, make_tag, make_rule, make_tx, account, message, matched):
        """`kw in acc_name or (raw_message and kw in raw_message)`"""
        tag = make_tag("Transport")
        make_rule("UBER", tag_id=tag.id)
        assert (make_tx(10, account, raw_message=message).tag_id == tag.id) is matched

    def test_wbu_t08_first_matching_rule_wins(self, make_tag, make_rule, make_tx):
        """`break` after the first match: insertion order beats specificity (defect D2)."""
        transport, food = make_tag("Transport"), make_tag("Food")
        make_rule("UBER", tag_id=transport.id)
        make_rule("UBER EATS", tag_id=food.id)
        assert make_tx(10, "Uber Eats Order").tag_id == transport.id

    def test_wbu_t09_defaults(self, db):
        """`timestamp or now`, `account_name or sender_address`, type upper-cased."""
        tx = crud.create_transaction(db, schemas.TransactionCreate(amount=5, type="credit", sender_address="VM-HDFC"))
        assert tx.account_name == "VM-HDFC"
        assert tx.type == "CREDIT"
        assert abs(tx.timestamp - datetime.now().timestamp() * 1000) < 60_000


# --------------------------------------------------------------------------
# Rule application and re-evaluation
# --------------------------------------------------------------------------

class TestRules:
    def test_wbu_r01_create_rule_normalises_and_applies(self, db, make_tag, make_rule, make_tx):
        """create_rule(): keyword stripped + upper-cased, then applied to existing rows."""
        tag = make_tag("Food")
        make_tx(10, "zomato")
        rule = make_rule("  zomato ", tag_id=tag.id)
        assert rule.account_keyword == "ZOMATO"
        assert crud.get_transactions(db)[0].tag_id == tag.id

    def test_wbu_r02_apply_single_rule_count_zero_and_paths(self, db, make_tag, make_tx):
        """`if count > 0` F (no matches); then tag path and ignore path."""
        tag = make_tag("Food")
        assert crud.apply_single_rule_to_existing(db, "NOTHING", tag.id) == 0
        make_tx(10, "Zomato")
        make_tx(20, "Card", raw_message="ZOMATO via card")
        assert crud.apply_single_rule_to_existing(db, "ZOMATO", tag.id) == 2
        assert crud.apply_single_rule_to_existing(db, "ZOMATO", None, is_ignore=True) == 2
        rows = db.query(models.Transaction).all()
        assert all(r.is_ignored and r.tag_id is None for r in rows)

    def test_wbu_r03_reevaluate_paths(self, db, make_tag, make_rule, make_tx):
        """Per-transaction paths: no match / tag rule / ignore rule,
        plus `account_name or sender_address` fallback and raw_message match."""
        tag = make_tag("Bills")
        no_match = make_tx(1, "Tea Stall")
        by_sender = models.Transaction(amount=2, type="DEBIT", account_name=None, sender_address="AIRTEL-SMS",
                                       raw_message="", timestamp=1)
        db.add(by_sender)
        by_message = make_tx(3, "Card", raw_message="netflix monthly")
        db.add(models.AutoTagRule(account_keyword="AIRTEL", tag_id=tag.id, is_ignore_rule=False))
        db.add(models.AutoTagRule(account_keyword="NETFLIX", tag_id=None, is_ignore_rule=True))
        db.commit()

        crud.reevaluate_all_transactions(db)
        get = lambda t: db.get(models.Transaction, t.id)
        assert (get(no_match).tag_id, get(no_match).is_ignored) == (None, False)
        assert (get(by_sender).tag_id, get(by_sender).is_tagged) == (tag.id, True)
        assert (get(by_message).is_ignored, get(by_message).tag_id) == (True, None)

    def test_wbu_r04_delete_rule_branches(self, db, make_rule):
        """`if not db_rule` T (missing) and F (deleted + reevaluate)."""
        assert crud.delete_rule(db, 999) is False
        rule = make_rule("X", is_ignore_rule=True)
        assert crud.delete_rule(db, rule.id) is True
        assert crud.get_rules(db) == []

    def test_wbu_r05_get_rules_with_and_without_tag(self, make_tag, make_rule, db):
        """`r.tag.name if r.tag else None` -> both outcomes."""
        tag = make_tag("Food", emoji="🍔")
        make_rule("ZOMATO", tag_id=tag.id)
        make_rule("SELF", is_ignore_rule=True)
        by_kw = {r.account_keyword: r for r in crud.get_rules(db)}
        assert (by_kw["ZOMATO"].tag_name, by_kw["ZOMATO"].tag_emoji) == ("Food", "🍔")
        assert (by_kw["SELF"].tag_name, by_kw["SELF"].is_ignore_rule) == (None, True)

    def test_wbu_r06_apply_all_rules_returns_active_count(self, db, make_tx):
        make_tx(1, "A")
        make_tx(2, "B")
        deleted = make_tx(3, "C")
        crud.delete_transaction(db, deleted.id)
        assert crud.apply_all_rules(db) == 2


# --------------------------------------------------------------------------
# Tag CRUD and transaction updates
# --------------------------------------------------------------------------

class TestTagsAndUpdates:
    def test_wbu_u01_update_tag_each_field(self, db, make_tag):
        """Every `if tag_update.X is not None` -> T once and F once; missing id -> None."""
        tag = make_tag("Travl", color_hex="#111111", emoji="✈️")
        assert crud.update_tag(db, 999, schemas.TagUpdate(name="x")) is None
        crud.update_tag(db, tag.id, schemas.TagUpdate())                     # all F
        assert (tag.name, tag.color_hex, tag.emoji) == ("Travl", "#111111", "✈️")
        crud.update_tag(db, tag.id, schemas.TagUpdate(name=" Travel ", color_hex="#222222", emoji="🚆"))
        assert (tag.name, tag.color_hex, tag.emoji) == ("Travel", "#222222", "🚆")

    def test_wbu_u02_delete_tag_untags_transactions(self, db, make_tag, make_tx):
        tag = make_tag("Bills")
        tx = make_tx(10, "Airtel", tag_id=tag.id)
        assert crud.delete_tag(db, 999) is False
        assert crud.delete_tag(db, tag.id) is True
        row = db.get(models.Transaction, tx.id)
        assert (row.tag_id, row.is_tagged) == (None, False)

    def test_wbu_u03_update_transaction_each_field(self, db, make_tag, make_tx):
        tag = make_tag("Food")
        tx = make_tx(10, "Dominos")
        assert crud.update_transaction(db, 999, schemas.TransactionUpdate()) is None
        same = crud.update_transaction(db, tx.id, schemas.TransactionUpdate())   # all F
        assert (same.amount, same.type) == (10, "DEBIT")
        upd = crud.update_transaction(db, tx.id, schemas.TransactionUpdate(
            amount=20, type="credit", sender_address="BANK", account_name="Dominos Refund",
            tag_id=tag.id, raw_message="refund", is_ignored=True))
        assert (upd.amount, upd.type, upd.sender_address, upd.account_name) == (20, "CREDIT", "BANK", "Dominos Refund")
        assert (upd.tag_id, upd.is_tagged, upd.raw_message, upd.is_ignored) == (tag.id, True, "refund", True)

    def test_wbu_u04_update_tag_on_transaction_and_delete(self, db, make_tag, make_tx):
        tag = make_tag("Food")
        tx = make_tx(10, "Swiggy")
        assert crud.update_transaction_tag(db, 999, tag.id) is None
        assert crud.update_transaction_tag(db, tx.id, tag.id).is_tagged is True
        assert crud.update_transaction_tag(db, tx.id, None).is_tagged is False
        assert crud.delete_transaction(db, 999) is False
        assert crud.delete_transaction(db, tx.id) is True
        assert crud.get_transactions(db) == []

    def test_wbu_u05_enrich_with_dangling_tag_id(self, db):
        """_enrich_transaction: `tx.tag` None but tag_id set -> tag_name None (not 'Untagged')."""
        row = models.Transaction(amount=1, type="DEBIT", account_name="X", tag_id=424242,
                                 raw_message="", timestamp=1, is_tagged=True)
        db.add(row)
        db.commit()
        tx = crud._enrich_transaction(row)
        assert (tx.tag_name, tx.tag_color, tx.tag_emoji) == (None, "#95A5A6", "📦")


# --------------------------------------------------------------------------
# get_transactions(): each filter branch
# --------------------------------------------------------------------------

def test_wbu_f01_transaction_filters(db, make_tag, make_tx):
    food = make_tag("Food")
    make_tx(10, "Old", timestamp=1_000)
    make_tx(20, "Pizza Place", tag_id=food.id, timestamp=2_000)
    make_tx(30, "Employer", type="CREDIT", timestamp=3_000, raw_message="salary")
    names = lambda **f: sorted(t.account_name for t in crud.get_transactions(db, **f))
    assert names() == ["Employer", "Old", "Pizza Place"]
    assert names(start_ts=1_500) == ["Employer", "Pizza Place"]
    assert names(end_ts=1_500) == ["Old"]
    assert names(tx_type="credit") == ["Employer"]
    assert names(untagged_only=True) == ["Employer", "Old"]
    assert names(untagged_only=True, tag_id=food.id) == ["Employer", "Old"]   # `if` wins over `elif`
    assert names(tag_id=food.id) == ["Pizza Place"]
    assert names(search="salary") == ["Employer"]


# --------------------------------------------------------------------------
# get_dashboard_stats(): branches, boundaries and the 7-day loop
# --------------------------------------------------------------------------

def _ms(dt):
    return int(dt.timestamp() * 1000)


class TestDashboardStats:
    def test_wbu_s01_empty(self, db):
        """debits empty -> top None, anchor = now, max_day 0 -> 1.0 (no division by zero)."""
        s = crud.get_dashboard_stats(db)
        assert (s.total_expenditure, s.top_expenditure, s.untagged_count, s.tag_totals) == (0, None, 0, [])
        assert len(s.daily_trend) == 7 and all(d.percentage == 0 for d in s.daily_trend)
        assert s.daily_trend[-1].date_str == datetime.now().strftime("%Y-%m-%d")

    def test_wbu_s02_zero_amount_debit(self, make_tx, db):
        """`pct = ... if total_expenditure > 0 else 0.0` -> F branch (only reachable with a ₹0 debit)."""
        make_tx(0, "Free sample")
        s = crud.get_dashboard_stats(db)
        assert s.tag_totals[0].percentage == 0.0
        assert s.top_expenditure.account_name == "Free sample"

    def test_wbu_s03_category_totals(self, db, make_tag, make_tx):
        """tag_totals branches: real tag, untagged (-1), tag with emoji None,
        tag id that no longer exists; sorted by amount; percentages."""
        food = make_tag("Food")
        food.emoji = None          # TagCreate(emoji=None) gets the column default, so set NULL directly
        db.commit()
        make_tx(300, "Swiggy", tag_id=food.id)
        make_tx(100, "Unknown")
        db.add(models.Transaction(amount=600, type="DEBIT", account_name="Ghost", tag_id=777,
                                  raw_message="", timestamp=_ms(datetime.now()), is_tagged=True))
        db.add(models.Transaction(amount=5000, type="CREDIT", account_name="Salary",
                                  raw_message="", timestamp=_ms(datetime.now())))
        db.commit()

        s = crud.get_dashboard_stats(db)
        assert (s.total_expenditure, s.total_income) == (1000, 5000)
        rows = [(t.tag_id, t.tag_name, t.tag_emoji, t.total_amount, t.percentage) for t in s.tag_totals]
        assert rows == [
            (777, "Other / Untagged", "📦", 600, 60.0),
            (food.id, "Food", "📦", 300, 30.0),
            (None, "Other / Untagged", "📦", 100, 10.0),
        ]
        assert s.untagged_count == 1
        assert s.top_expenditure.account_name == "Ghost"

    def test_wbu_s04_seven_day_loop_and_window(self, db, make_tx):
        """`for i in range(6, -1, -1)`: 7 iterations ending on the latest debit's day;
        day-window boundaries 00:00:00 and 23:59:59 are inclusive; 7 days back is excluded."""
        anchor = datetime(2026, 6, 20, 15, 0)
        make_tx(100, "Anchor", timestamp=_ms(anchor))
        make_tx(50, "Midnight", timestamp=_ms(datetime(2026, 6, 20, 0, 0, 0)))
        make_tx(25, "Day start -6", timestamp=_ms(datetime(2026, 6, 14, 0, 0, 0)))
        make_tx(10, "Day end -6", timestamp=_ms(datetime(2026, 6, 14, 23, 59, 59)))
        make_tx(999, "Too old", timestamp=_ms(datetime(2026, 6, 13, 23, 59, 59)))

        trend = crud.get_dashboard_stats(db).daily_trend
        assert [d.date_str for d in trend] == ["2026-06-%02d" % d for d in range(14, 21)]
        assert trend[0].day_label == "SUN" and trend[-1].day_label == "SAT"
        assert trend[0].total_amount == 35 and trend[-1].total_amount == 150
        assert trend[-1].percentage == 100.0 and trend[0].percentage == round(35 / 150 * 100, 1)
        assert sum(d.total_amount for d in trend[1:-1]) == 0

    def test_wbu_s05_time_range_filters(self, db, make_tx):
        """`if start_ts is not None` / `if end_ts is not None` -> T."""
        make_tx(10, "A", timestamp=1_000)
        make_tx(20, "B", timestamp=2_000)
        make_tx(40, "C", timestamp=3_000)
        assert crud.get_dashboard_stats(db, start_ts=1_500).total_expenditure == 60
        assert crud.get_dashboard_stats(db, end_ts=2_500).total_expenditure == 30
        assert crud.get_dashboard_stats(db, start_ts=1_500, end_ts=2_500).total_expenditure == 20

    def test_wbu_s06_deleted_and_ignored_excluded(self, db, make_tx, make_rule):
        keep = make_tx(10, "Keep")
        gone = make_tx(20, "Gone")
        crud.delete_transaction(db, gone.id)
        make_rule("HIDE", is_ignore_rule=True)
        make_tx(40, "Hide me")
        s = crud.get_dashboard_stats(db)
        assert s.total_expenditure == 10 and s.top_expenditure.id == keep.id
