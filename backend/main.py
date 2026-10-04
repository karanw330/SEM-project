import os
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import engine, get_db, Base
import models
import schemas
import crud
import seed_data
import pdf_parser

# Re-create database tables automatically if schema changes
try:
    Base.metadata.create_all(bind=engine)
except Exception:
    pass

# Ensure schema is up to date by checking column presence or recreating if needed
with Session(engine) as db_session:
    try:
        db_session.query(models.AutoTagRule).first()
    except Exception:
        db_session.rollback()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

# Clear any existing seed/demo data completely
with Session(engine) as db_session:
    seed_data.clear_all_data(db_session)

app = FastAPI(
    title="Financial Clarity Web API",
    description="Backend API for Financial Clarity Expense & Tag Manager",
    version="1.0.0"
)

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DASHBOARD ENDPOINTS ---

@app.get("/api/dashboard/stats", response_model=schemas.DashboardStatsResponse)
def get_dashboard_stats(
    start_ts: Optional[int] = Query(None),
    end_ts: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    return crud.get_dashboard_stats(db, start_ts=start_ts, end_ts=end_ts)


# --- TRANSACTION ENDPOINTS ---

@app.get("/api/transactions", response_model=List[schemas.TransactionResponse])
def list_transactions(
    start_ts: Optional[int] = Query(None),
    end_ts: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    tx_type: Optional[str] = Query(None),
    tag_id: Optional[int] = Query(None),
    untagged_only: bool = Query(False),
    db: Session = Depends(get_db)
):
    return crud.get_transactions(
        db,
        start_ts=start_ts,
        end_ts=end_ts,
        search=search,
        tx_type=tx_type,
        tag_id=tag_id,
        untagged_only=untagged_only
    )

@app.post("/api/transactions", response_model=schemas.TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    tx_data: schemas.TransactionCreate,
    db: Session = Depends(get_db)
):
    return crud.create_transaction(db, tx_data)

@app.put("/api/transactions/{tx_id}", response_model=schemas.TransactionResponse)
def update_transaction(
    tx_id: int,
    tx_update: schemas.TransactionUpdate,
    db: Session = Depends(get_db)
):
    updated = crud.update_transaction(db, tx_id, tx_update)
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return updated

@app.put("/api/transactions/{tx_id}/tag", response_model=schemas.TransactionResponse)
def update_transaction_tag(
    tx_id: int,
    tag_data: schemas.TransactionTagUpdate,
    db: Session = Depends(get_db)
):
    updated = crud.update_transaction_tag(db, tx_id, tag_data.tag_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return updated

@app.delete("/api/transactions/{tx_id}")
def delete_transaction(
    tx_id: int,
    db: Session = Depends(get_db)
):
    success = crud.delete_transaction(db, tx_id)
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"message": "Transaction deleted successfully"}


# --- PDF STATEMENT IMPORT ENDPOINTS ---

@app.post("/api/transactions/parse-pdf", response_model=schemas.PDFParseResultResponse)
async def parse_gpay_pdf_endpoint(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF document.")

    content = await file.read()
    try:
        parsed_res = pdf_parser.parse_gpay_pdf(content, password=password)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    extracted_txs = parsed_res.get("transactions", [])
    if not extracted_txs:
        raise HTTPException(
            status_code=400,
            detail="No transaction records could be extracted from this PDF. Ensure it is a valid GPay statement."
        )

    # Fetch active auto-tag rules and tags for auto-matching
    rules = crud.get_rules(db)
    tags = crud.get_tags(db)
    tag_dict = {t.id: t for t in tags}

    # Fetch existing database transactions for deduplication
    existing_db_txs = db.query(models.Transaction).filter(models.Transaction.is_deleted == False).all()

    result_items = []
    duplicate_count = 0

    for item in extracted_txs:
        account_name = item.get("account_name", "")
        amount = item.get("amount", 0.0)
        timestamp = item.get("timestamp", 0)
        tx_type = item.get("type", "DEBIT")
        raw_msg = item.get("raw_message", "")
        upi_id = item.get("upi_id", "")

        # Auto-match rules
        assigned_tag_id = None
        for r in rules:
            if r.account_keyword and r.account_keyword.lower() in account_name.lower():
                assigned_tag_id = r.tag_id
                break

        tag_obj = tag_dict.get(assigned_tag_id) if assigned_tag_id else None

        # Deduplication check: same amount, type, account name, AND timestamp within 5 minutes OR matching UPI ID
        is_dup = False
        for ex in existing_db_txs:
            same_amt = abs(ex.amount - amount) < 0.01
            same_type = ex.type == tx_type
            same_account = (ex.account_name or "").lower().strip() == account_name.lower().strip()
            same_time = abs(ex.timestamp - timestamp) < (300 * 1000)  # within 5 minutes

            upi_match = bool(upi_id and upi_id in (ex.raw_message or ""))

            if upi_match or (same_amt and same_type and same_account and same_time):
                is_dup = True
                break

        if is_dup:
            duplicate_count += 1

        result_items.append(schemas.PDFParsedTransaction(
            amount=amount,
            type=tx_type,
            account_name=account_name,
            raw_message=raw_msg,
            timestamp=timestamp,
            tag_id=assigned_tag_id,
            tag_name=tag_obj.name if tag_obj else None,
            tag_color=tag_obj.color_hex if tag_obj else None,
            tag_emoji=tag_obj.emoji if tag_obj else None,
            is_duplicate=is_dup
        ))

    return schemas.PDFParseResultResponse(
        total_found=len(result_items),
        new_count=len(result_items) - duplicate_count,
        duplicate_count=duplicate_count,
        transactions=result_items
    )

@app.post("/api/transactions/confirm-import")
def confirm_import_transactions(
    req: schemas.PDFConfirmImportRequest,
    db: Session = Depends(get_db)
):
    created_count = 0
    existing_db_txs = db.query(models.Transaction).filter(models.Transaction.is_deleted == False).all()

    for tx_data in req.transactions:
        # Prevent inserting duplicates if confirm-import is clicked again
        is_already_in_db = False
        for ex in existing_db_txs:
            same_amt = abs(ex.amount - tx_data.amount) < 0.01
            same_type = ex.type == tx_data.type
            same_account = (ex.account_name or "").lower().strip() == (tx_data.account_name or "").lower().strip()
            same_time = abs(ex.timestamp - (tx_data.timestamp or 0)) < (300 * 1000)

            if same_amt and same_type and same_account and same_time:
                is_already_in_db = True
                break

        if not is_already_in_db:
            crud.create_transaction(db, tx_data)
            created_count += 1

    return {"message": f"Successfully imported {created_count} transaction(s)."}


# --- TAG ENDPOINTS ---


@app.get("/api/tags", response_model=List[schemas.TagResponse])
def get_tags(db: Session = Depends(get_db)):
    return crud.get_tags(db)

@app.post("/api/tags", response_model=schemas.TagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(tag_data: schemas.TagCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Tag).filter(models.Tag.name.ilike(tag_data.name.strip())).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tag with this name already exists")
    return crud.create_tag(db, tag_data)

@app.put("/api/tags/{tag_id}", response_model=schemas.TagResponse)
def update_tag(tag_id: int, tag_update: schemas.TagUpdate, db: Session = Depends(get_db)):
    updated = crud.update_tag(db, tag_id, tag_update)
    if not updated:
        raise HTTPException(status_code=404, detail="Tag not found")
    return updated

@app.delete("/api/tags/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    success = crud.delete_tag(db, tag_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"message": "Tag deleted successfully"}


# --- AUTO-TAG RULE ENDPOINTS ---

@app.get("/api/rules", response_model=List[schemas.RuleResponse])
def get_rules(db: Session = Depends(get_db)):
    return crud.get_rules(db)

@app.post("/api/rules", response_model=schemas.RuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(rule_data: schemas.RuleCreate, db: Session = Depends(get_db)):
    tag = None
    if not rule_data.is_ignore_rule:
        if not rule_data.tag_id:
            raise HTTPException(status_code=400, detail="tag_id is required for tag rules")
        tag = crud.get_tag_by_id(db, rule_data.tag_id)
        if not tag:
            raise HTTPException(status_code=404, detail="Tag not found")
    
    kw = rule_data.account_keyword.strip().upper()
    existing = db.query(models.AutoTagRule).filter(models.AutoTagRule.account_keyword == kw).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Rule for keyword '{kw}' already exists")
    
    rule = crud.create_rule(db, rule_data)
    return schemas.RuleResponse(
        id=rule.id,
        account_keyword=rule.account_keyword,
        tag_id=rule.tag_id,
        is_ignore_rule=rule.is_ignore_rule or False,
        tag_name=tag.name if tag else "IGNORED",
        tag_color=tag.color_hex if tag else "#E53E3E",
        tag_emoji=tag.emoji if tag else "🚫"
    )

@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    success = crud.delete_rule(db, rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Rule deleted successfully"}

@app.post("/api/rules/apply-all")
def apply_all_rules(db: Session = Depends(get_db)):
    count = crud.apply_all_rules(db)
    return {"message": f"Applied rules to {count} transactions"}

@app.post("/api/seed")
def seed_demo(db: Session = Depends(get_db)):
    seed_data.clear_all_data(db)
    return {"message": "All data cleared successfully"}


# --- STATIC FILES FRONTEND SERVING ---

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

if os.path.exists(FRONTEND_DIR):
    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        fav_path = os.path.join(FRONTEND_DIR, "favicon.ico")
        if os.path.exists(fav_path):
            return FileResponse(fav_path)
        raise HTTPException(status_code=204)

    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
