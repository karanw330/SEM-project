import time
from sqlalchemy import Column, Integer, Float, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, index=True, nullable=False)
    color_hex = Column(String, nullable=False, default="#667EEA")
    emoji = Column(String, nullable=True, default="🏷️")
    created_at = Column(Integer, default=lambda: int(time.time() * 1000))

    transactions = relationship("Transaction", back_populates="tag", cascade="all, delete-orphan")
    auto_rules = relationship("AutoTagRule", back_populates="tag", cascade="all, delete-orphan")

class AutoTagRule(Base):
    __tablename__ = "auto_tag_rules"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    account_keyword = Column(String, unique=True, index=True, nullable=False)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=True)
    is_ignore_rule = Column(Boolean, default=False, nullable=False)

    tag = relationship("Tag", back_populates="auto_rules")

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False, default="DEBIT")  # "DEBIT" or "CREDIT"
    sender_address = Column(String, nullable=False, default="MANUAL")
    account_name = Column(String, nullable=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="SET NULL"), nullable=True)
    raw_message = Column(String, nullable=False, default="")
    timestamp = Column(Integer, nullable=False, default=lambda: int(time.time() * 1000))
    is_tagged = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    is_ignored = Column(Boolean, default=False)

    tag = relationship("Tag", back_populates="transactions")
