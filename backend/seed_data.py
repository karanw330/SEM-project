from sqlalchemy.orm import Session
import models

def seed_default_data(db: Session):
    """No-op: Demo seeding has been disabled."""
    pass

def clear_all_data(db: Session):
    """Completely clear all transactions, auto-tag rules, and tags from the database."""
    db.query(models.Transaction).delete()
    db.query(models.AutoTagRule).delete()
    db.query(models.Tag).delete()
    db.commit()
    print("Database cleared successfully!")

