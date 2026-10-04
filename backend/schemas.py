from pydantic import BaseModel, Field
from typing import Optional, List

# Tag Schemas
class TagBase(BaseModel):
    name: str
    color_hex: str = "#667EEA"
    emoji: Optional[str] = "🏷️"

class TagCreate(TagBase):
    pass

class TagUpdate(BaseModel):
    name: Optional[str] = None
    color_hex: Optional[str] = None
    emoji: Optional[str] = None

class TagResponse(TagBase):
    id: int
    created_at: int

    class Config:
        from_attributes = True

# Rule Schemas
class RuleCreate(BaseModel):
    account_keyword: str
    tag_id: Optional[int] = None
    is_ignore_rule: bool = False

class RuleResponse(BaseModel):
    id: int
    account_keyword: str
    tag_id: Optional[int] = None
    is_ignore_rule: bool = False
    tag_name: Optional[str] = None
    tag_color: Optional[str] = None
    tag_emoji: Optional[str] = None

    class Config:
        from_attributes = True

# Transaction Schemas
class TransactionBase(BaseModel):
    amount: float
    type: str = "DEBIT"  # "DEBIT" or "CREDIT"
    sender_address: str = "MANUAL"
    account_name: Optional[str] = None
    tag_id: Optional[int] = None
    raw_message: Optional[str] = ""
    timestamp: Optional[int] = None

class TransactionCreate(TransactionBase):
    pass

class TransactionUpdate(BaseModel):
    amount: Optional[float] = None
    type: Optional[str] = None
    sender_address: Optional[str] = None
    account_name: Optional[str] = None
    tag_id: Optional[int] = None
    raw_message: Optional[str] = None
    is_tagged: Optional[bool] = None
    is_ignored: Optional[bool] = None

class TransactionTagUpdate(BaseModel):
    tag_id: Optional[int] = None

class TransactionResponse(BaseModel):
    id: int
    amount: float
    type: str
    sender_address: str
    account_name: Optional[str] = None
    tag_id: Optional[int] = None
    tag_name: Optional[str] = None
    tag_color: Optional[str] = None
    tag_emoji: Optional[str] = None
    raw_message: str
    timestamp: int
    is_tagged: bool
    is_deleted: bool
    is_ignored: bool

    class Config:
        from_attributes = True

# Dashboard Stats Schemas
class TagTotal(BaseModel):
    tag_id: Optional[int] = None
    tag_name: str
    tag_color: str
    tag_emoji: str
    total_amount: float
    percentage: float = 0.0

class DailySpend(BaseModel):
    day_label: str
    date_str: str
    total_amount: float
    percentage: float = 0.0

class DashboardStatsResponse(BaseModel):
    total_expenditure: float
    total_income: float
    top_expenditure: Optional[TransactionResponse] = None
    untagged_count: int
    tag_totals: List[TagTotal]
    daily_trend: List[DailySpend]

# PDF Upload & Parsing Schemas
class PDFParsedTransaction(BaseModel):
    amount: float
    type: str
    account_name: str
    raw_message: str
    timestamp: int
    tag_id: Optional[int] = None
    tag_name: Optional[str] = None
    tag_color: Optional[str] = None
    tag_emoji: Optional[str] = None
    is_duplicate: bool = False

class PDFParseResultResponse(BaseModel):
    total_found: int
    new_count: int
    duplicate_count: int
    transactions: List[PDFParsedTransaction]

class PDFConfirmImportRequest(BaseModel):
    transactions: List[TransactionCreate]

