"""
Migration: Add primary_category column to journal table
This migration adds the fld_primary_category column and populates it for existing journals.
"""
import os
import sys

# Add app to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import text
from app.db.database import engine, SessionLocal

# Category mappings for existing journals (case-insensitive matching)
JOURNAL_CATEGORY_MAP = {
    "art and commerce": "Arts & Humanities",
    "humanities and social sciences": "Social Sciences",
    "operations research": "Engineering",
    "inventory control": "Business & Economics",
    "science and engineering": "Physical Sciences",
    "biomedical and life sciences": "Life Sciences",
    "education and information": "Education",
    "stability and fluid mechanics": "Engineering",
    "test journal": "Physical Sciences",
}


def run_migration():
    """Add primary_category column and populate for existing journals."""
    db = SessionLocal()
    
    try:
        # Step 1: Check if column exists
        print("Checking if fld_primary_category column exists...")
        result = db.execute(text("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'journal' 
            AND COLUMN_NAME = 'fld_primary_category'
        """))
        column_exists = result.fetchone() is not None
        
        if not column_exists:
            # Step 2: Add the column
            print("Adding fld_primary_category column...")
            db.execute(text("""
                ALTER TABLE journal 
                ADD COLUMN fld_primary_category VARCHAR(100) NULL 
                AFTER fld_journal_name
            """))
            db.commit()
            print("✓ Column added successfully")
        else:
            print("✓ Column already exists")
        
        # Step 3: Populate categories for existing journals
        print("\nPopulating categories for existing journals...")
        
        # Get all journals
        result = db.execute(text("SELECT fld_id, fld_journal_name FROM journal"))
        journals = result.fetchall()
        
        updated_count = 0
        for journal_id, journal_name in journals:
            if not journal_name:
                continue
                
            # Find matching category
            journal_name_lower = journal_name.lower()
            matched_category = None
            
            for pattern, category in JOURNAL_CATEGORY_MAP.items():
                if pattern in journal_name_lower:
                    matched_category = category
                    break
            
            if matched_category:
                db.execute(text("""
                    UPDATE journal 
                    SET fld_primary_category = :category 
                    WHERE fld_id = :id AND (fld_primary_category IS NULL OR fld_primary_category = '')
                """), {"category": matched_category, "id": journal_id})
                print(f"  {journal_name} → {matched_category}")
                updated_count += 1
            else:
                print(f"  {journal_name} → (no match, manual assignment needed)")
        
        db.commit()
        print(f"\n✓ Updated {updated_count} journals with categories")
        
        # Step 4: Show summary
        print("\n=== Summary ===")
        result = db.execute(text("""
            SELECT fld_primary_category, COUNT(*) as count 
            FROM journal 
            GROUP BY fld_primary_category
        """))
        for category, count in result.fetchall():
            print(f"  {category or '(uncategorized)'}: {count} journals")
        
        print("\n✓ Migration completed successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"\n✗ Migration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_migration()
