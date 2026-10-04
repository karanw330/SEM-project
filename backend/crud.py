import time
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_

import models
import schemas

# --- TAG CRUD ---

def get_tags(db: Session) -> List[models.Tag]:
    return db.query(models.Tag).order_by(models.Tag.name.asc()).all()

def get_tag_by_id(db: Session, tag_id: int) -> Optional[models.Tag]:
    return db.query(models.Tag).filter(models.Tag.id == tag_id).first()

def create_tag(db: Session, tag_data: schemas.TagCreate) -> models.Tag:
    db_tag = models.Tag(
        name=tag_data.name.strip(),
        color_hex=tag_data.color_hex,
        emoji=tag_data.emoji,
        created_at=int(time.time() * 1000)
    )
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag

def update_tag(db: Session, tag_id: int, tag_update: schemas.TagUpdate) -> Optional[models.Tag]:
    db_tag = get_tag_by_id(db, tag_id)
    if not db_tag:
        return None
    if tag_update.name is not None:
        db_tag.name = tag_update.name.strip()
    if tag_update.color_hex is not None:
        db_tag.color_hex = tag_update.color_hex
    if tag_update.emoji is not None:
        db_tag.emoji = tag_update.emoji
    db.commit()
    db.refresh(db_tag)
    return db_tag

def delete_tag(db: Session, tag_id: int) -> bool:
    db_tag = get_tag_by_id(db, tag_id)
    if not db_tag:
        return False
    # Set tag_id to null for transactions associated with this tag
    db.query(models.Transaction).filter(models.Transaction.tag_id == tag_id).update({"tag_id": None, "is_tagged": False})
    db.delete(db_tag)
    db.commit()
    return True


# --- AUTO-TAG RULE CRUD ---

def get_rules(db: Session) -> List[schemas.RuleResponse]:
    rules = db.query(models.AutoTagRule).all()
    res = []
    for r in rules:
        res.append(schemas.RuleResponse(
            id=r.id,
            account_keyword=r.account_keyword,
            tag_id=r.tag_id,
            is_ignore_rule=r.is_ignore_rule or False,
            tag_name=r.tag.name if r.tag else None,
            tag_color=r.tag.color_hex if r.tag else None,
            tag_emoji=r.tag.emoji if r.tag else None
        ))
    return res

def create_rule(db: Session, rule_data: schemas.RuleCreate) -> models.AutoTagRule:
    keyword = rule_data.account_keyword.strip().upper()
    db_rule = models.AutoTagRule(
        account_keyword=keyword,
        tag_id=rule_data.tag_id if not rule_data.is_ignore_rule else None,
        is_ignore_rule=rule_data.is_ignore_rule
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    
    # Auto-apply this new rule to existing transactions matching the keyword
    apply_single_rule_to_existing(db, keyword, rule_data.tag_id, is_ignore=rule_data.is_ignore_rule)
    
    return db_rule

def delete_rule(db: Session, rule_id: int) -> bool:
    db_rule = db.query(models.AutoTagRule).filter(models.AutoTagRule.id == rule_id).first()
    if not db_rule:
        return False
    db.delete(db_rule)
    db.commit()
    
    # Re-evaluate all transactions against remaining rules
    reevaluate_all_transactions(db)
    return True

def reevaluate_all_transactions(db: Session):
    """Reset rule-derived fields on non-deleted transactions and re-apply all active rules."""
    rules = db.query(models.AutoTagRule).all()
    txs = db.query(models.Transaction).filter(models.Transaction.is_deleted == False).all()
    
    for tx in txs:
        # Reset ignore status
        tx.is_ignored = False
        
        # Check matching rule
        acc_name = tx.account_name or tx.sender_address or ""
        raw_msg = tx.raw_message or ""
        
        matched = False
        for r in rules:
            if r.account_keyword and (
                r.account_keyword.lower() in acc_name.lower() or 
                r.account_keyword.lower() in raw_msg.lower()
            ):
                matched = True
                if r.is_ignore_rule:
                    tx.is_ignored = True
                    tx.tag_id = None
                    tx.is_tagged = False
                else:
                    tx.tag_id = r.tag_id
                    tx.is_tagged = True
                break
        
        # If no rule matched and it was previously tagged by a deleted rule or untagged, leave tag_id if set manually

    db.commit()

def apply_single_rule_to_existing(db: Session, keyword: str, tag_id: Optional[int], is_ignore: bool = False) -> int:
    kw_pattern = f"%{keyword}%"
    matching = db.query(models.Transaction).filter(
        models.Transaction.is_deleted == False,
        or_(
            func.upper(models.Transaction.account_name).like(kw_pattern),
            func.upper(models.Transaction.raw_message).like(kw_pattern)
        )
    ).all()
    
    count = 0
    for tx in matching:
        if is_ignore:
            tx.is_ignored = True
            tx.tag_id = None
            tx.is_tagged = False
        else:
            tx.tag_id = tag_id
            tx.is_tagged = True
        count += 1
    
    if count > 0:
        db.commit()
    return count

def apply_all_rules(db: Session) -> int:
    reevaluate_all_transactions(db)
    return db.query(models.Transaction).filter(models.Transaction.is_deleted == False).count()


# --- TRANSACTION CRUD ---

def _enrich_transaction(tx: models.Transaction) -> schemas.TransactionResponse:
    return schemas.TransactionResponse(
        id=tx.id,
        amount=tx.amount,
        type=tx.type,
        sender_address=tx.sender_address,
        account_name=tx.account_name,
        tag_id=tx.tag_id,
        tag_name=tx.tag.name if tx.tag else ("Untagged" if not tx.tag_id else None),
        tag_color=tx.tag.color_hex if tx.tag else "#95A5A6",
        tag_emoji=tx.tag.emoji if tx.tag else "📦",
        raw_message=tx.raw_message,
        timestamp=tx.timestamp,
        is_tagged=tx.is_tagged or (tx.tag_id is not None),
        is_deleted=tx.is_deleted,
        is_ignored=tx.is_ignored
    )

def create_transaction(db: Session, tx_data: schemas.TransactionCreate) -> schemas.TransactionResponse:
    ts = tx_data.timestamp or int(time.time() * 1000)
    acc_name = tx_data.account_name or tx_data.sender_address
    
    tag_id = tx_data.tag_id
    is_tagged = tag_id is not None
    is_ignored = False

    # Check auto-tag/ignore rules if not tagged
    if acc_name:
        rules = db.query(models.AutoTagRule).all()
        for r in rules:
            if r.account_keyword and (
                r.account_keyword.lower() in acc_name.lower() or 
                (tx_data.raw_message and r.account_keyword.lower() in tx_data.raw_message.lower())
            ):
                if r.is_ignore_rule:
                    is_ignored = True
                    tag_id = None
                    is_tagged = False
                else:
                    if not is_tagged:
                        tag_id = r.tag_id
                        is_tagged = True
                break

    db_tx = models.Transaction(
        amount=tx_data.amount,
        type=tx_data.type.upper(),
        sender_address=tx_data.sender_address,
        account_name=acc_name,
        tag_id=tag_id,
        raw_message=tx_data.raw_message or "",
        timestamp=ts,
        is_tagged=is_tagged,
        is_deleted=False,
        is_ignored=is_ignored
    )
    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)
    return _enrich_transaction(db_tx)

def get_transactions(
    db: Session,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
    search: Optional[str] = None,
    tx_type: Optional[str] = None,
    tag_id: Optional[int] = None,
    untagged_only: bool = False
) -> List[schemas.TransactionResponse]:
    query = db.query(models.Transaction).filter(
        models.Transaction.is_deleted == False,
        models.Transaction.is_ignored == False
    )

    if start_ts is not None:
        query = query.filter(models.Transaction.timestamp >= start_ts)
    if end_ts is not None:
        query = query.filter(models.Transaction.timestamp <= end_ts)
    if tx_type:
        query = query.filter(models.Transaction.type == tx_type.upper())
    if untagged_only:
        query = query.filter(or_(models.Transaction.tag_id == None, models.Transaction.is_tagged == False))
    elif tag_id is not None:
        query = query.filter(models.Transaction.tag_id == tag_id)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                models.Transaction.account_name.like(pattern),
                models.Transaction.raw_message.like(pattern),
                models.Transaction.sender_address.like(pattern)
            )
        )

    txs = query.order_by(models.Transaction.timestamp.desc()).all()
    return [_enrich_transaction(t) for t in txs]

def update_transaction_tag(db: Session, transaction_id: int, tag_id: Optional[int]) -> Optional[schemas.TransactionResponse]:
    tx = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not tx:
        return None
    tx.tag_id = tag_id
    tx.is_tagged = tag_id is not None
    db.commit()
    db.refresh(tx)
    return _enrich_transaction(tx)

def update_transaction(db: Session, transaction_id: int, update_data: schemas.TransactionUpdate) -> Optional[schemas.TransactionResponse]:
    tx = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not tx:
        return None
    
    if update_data.amount is not None:
        tx.amount = update_data.amount
    if update_data.type is not None:
        tx.type = update_data.type.upper()
    if update_data.sender_address is not None:
        tx.sender_address = update_data.sender_address
    if update_data.account_name is not None:
        tx.account_name = update_data.account_name
    if update_data.tag_id is not None:
        tx.tag_id = update_data.tag_id
        tx.is_tagged = True
    if update_data.raw_message is not None:
        tx.raw_message = update_data.raw_message
    if update_data.is_ignored is not None:
        tx.is_ignored = update_data.is_ignored

    db.commit()
    db.refresh(tx)
    return _enrich_transaction(tx)

def delete_transaction(db: Session, transaction_id: int) -> bool:
    tx = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not tx:
        return False
    tx.is_deleted = True
    db.commit()
    return True


# --- DASHBOARD STATS ---

def get_dashboard_stats(db: Session, start_ts: Optional[int] = None, end_ts: Optional[int] = None) -> schemas.DashboardStatsResponse:
    query = db.query(models.Transaction).filter(
        models.Transaction.is_deleted == False,
        models.Transaction.is_ignored == False
    )

    if start_ts is not None:
        query = query.filter(models.Transaction.timestamp >= start_ts)
    if end_ts is not None:
        query = query.filter(models.Transaction.timestamp <= end_ts)

    txs = query.all()

    total_expenditure = sum(t.amount for t in txs if t.type == "DEBIT")
    total_income = sum(t.amount for t in txs if t.type == "CREDIT")

    # Top expenditure
    debits = [t for t in txs if t.type == "DEBIT"]
    top_tx = max(debits, key=lambda t: t.amount) if debits else None
    top_expenditure_res = _enrich_transaction(top_tx) if top_tx else None

    # Untagged count
    untagged_count = sum(1 for t in debits if not t.tag_id or not t.is_tagged)

    # Category totals breakdown
    tag_sums = {}
    for t in debits:
        key = t.tag_id if t.tag_id else -1
        tag_sums[key] = tag_sums.get(key, 0.0) + t.amount

    all_tags = {tag.id: tag for tag in db.query(models.Tag).all()}
    
    tag_totals: List[schemas.TagTotal] = []
    for tid, amt in tag_sums.items():
        if tid != -1 and tid in all_tags:
            tag_obj = all_tags[tid]
            t_name, t_color, t_emoji = tag_obj.name, tag_obj.color_hex, tag_obj.emoji or "📦"
        else:
            t_name, t_color, t_emoji = "Other / Untagged", "#95A5A6", "📦"

        pct = round((amt / total_expenditure * 100), 1) if total_expenditure > 0 else 0.0
        tag_totals.append(schemas.TagTotal(
            tag_id=tid if tid != -1 else None,
            tag_name=t_name,
            tag_color=t_color,
            tag_emoji=t_emoji,
            total_amount=round(amt, 2),
            percentage=pct
        ))

    tag_totals.sort(key=lambda x: x.total_amount, reverse=True)

    # Daily Trend Chart for 7 days ending at latest transaction or today
    latest_tx = max(debits, key=lambda t: t.timestamp) if debits else None
    anchor_dt = datetime.fromtimestamp(latest_tx.timestamp / 1000) if latest_tx else datetime.now()

    daily_trend: List[schemas.DailySpend] = []
    day_amounts = []
    
    for i in range(6, -1, -1):
        day_date = anchor_dt - timedelta(days=i)
        day_start = datetime(day_date.year, day_date.month, day_date.day, 0, 0, 0)
        day_end = datetime(day_date.year, day_date.month, day_date.day, 23, 59, 59)

        start_milli = int(day_start.timestamp() * 1000)
        end_milli = int(day_end.timestamp() * 1000)

        day_total = sum(t.amount for t in debits if start_milli <= t.timestamp <= end_milli)
        day_amounts.append((day_date.strftime("%a").upper(), day_date.strftime("%Y-%m-%d"), round(day_total, 2)))

    max_day = max((amt for _, _, amt in day_amounts), default=1.0)
    if max_day == 0:
        max_day = 1.0

    for label, d_str, amt in day_amounts:
        pct = round((amt / max_day * 100), 1)
        daily_trend.append(schemas.DailySpend(
            day_label=label,
            date_str=d_str,
            total_amount=amt,
            percentage=pct
        ))

    return schemas.DashboardStatsResponse(
        total_expenditure=round(total_expenditure, 2),
        total_income=round(total_income, 2),
        top_expenditure=top_expenditure_res,
        untagged_count=untagged_count,
        tag_totals=tag_totals,
        daily_trend=daily_trend
    )
