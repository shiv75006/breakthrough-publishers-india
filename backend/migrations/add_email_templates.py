"""
Migration script to add email_template table and update paper_correspondence table.
Run this script to create the necessary database tables.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import engine, SessionLocal
from sqlalchemy import text
import json

def run_migration():
    """Run the migration to add email templates table and update correspondence table."""
    db = SessionLocal()
    
    try:
        # Create email_template table
        print("Creating email_template table...")
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS email_template (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                slug VARCHAR(50) NOT NULL UNIQUE,
                subject VARCHAR(500) NOT NULL,
                body_template TEXT NOT NULL,
                placeholders TEXT,
                category VARCHAR(50) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_slug (slug),
                INDEX idx_category (category)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        print("✓ email_template table created")
        
        # Add new columns to paper_correspondence if they don't exist
        print("Updating paper_correspondence table...")
        
        # Check and add sender_id column
        try:
            db.execute(text("""
                ALTER TABLE paper_correspondence 
                ADD COLUMN sender_id INT NULL,
                ADD CONSTRAINT fk_correspondence_sender FOREIGN KEY (sender_id) REFERENCES user(id) ON DELETE SET NULL
            """))
            print("  ✓ Added sender_id column")
        except Exception as e:
            if "Duplicate column" in str(e):
                print("  - sender_id column already exists")
            else:
                print(f"  - sender_id: {e}")
        
        # Check and add sender_role column
        try:
            db.execute(text("""
                ALTER TABLE paper_correspondence 
                ADD COLUMN sender_role VARCHAR(50) NULL AFTER sender_id
            """))
            print("  ✓ Added sender_role column")
        except Exception as e:
            if "Duplicate column" in str(e):
                print("  - sender_role column already exists")
            else:
                print(f"  - sender_role: {e}")
        
        # Check and add template_id column
        try:
            db.execute(text("""
                ALTER TABLE paper_correspondence 
                ADD COLUMN template_id INT NULL,
                ADD CONSTRAINT fk_correspondence_template FOREIGN KEY (template_id) REFERENCES email_template(id) ON DELETE SET NULL
            """))
            print("  ✓ Added template_id column")
        except Exception as e:
            if "Duplicate column" in str(e):
                print("  - template_id column already exists")
            else:
                print(f"  - template_id: {e}")
        
        # Check and add is_read column
        try:
            db.execute(text("""
                ALTER TABLE paper_correspondence 
                ADD COLUMN is_read BOOLEAN DEFAULT FALSE NOT NULL
            """))
            print("  ✓ Added is_read column")
        except Exception as e:
            if "Duplicate column" in str(e):
                print("  - is_read column already exists")
            else:
                print(f"  - is_read: {e}")
        
        # Check and add read_at column
        try:
            db.execute(text("""
                ALTER TABLE paper_correspondence 
                ADD COLUMN read_at DATETIME NULL
            """))
            print("  ✓ Added read_at column")
        except Exception as e:
            if "Duplicate column" in str(e):
                print("  - read_at column already exists")
            else:
                print(f"  - read_at: {e}")
        
        db.commit()
        print("✓ paper_correspondence table updated")
        
        # Seed default email templates
        print("\nSeeding default email templates...")
        
        default_templates = [
            {
                "name": "Submission Received",
                "slug": "submission_received",
                "subject": "Paper Submission Received - {{paper_title}}",
                "body_template": """Dear {{author_name}},

Thank you for submitting your paper titled "{{paper_title}}" to {{journal_name}}.

Your submission has been received.

We will review your submission and notify you of our decision. Please allow 2-4 weeks for the initial review process.

If you have any questions, please contact our editorial office.

Best regards,
The Editorial Team
{{journal_name}}""",
                "placeholders": json.dumps(["author_name", "paper_title", "journal_name", "paper_id"]),
                "category": "submission"
            },
            {
                "name": "Under Review",
                "slug": "under_review",
                "subject": "Your Paper is Under Review - {{paper_title}}",
                "body_template": """Dear {{author_name}},

We are pleased to inform you that your paper titled "{{paper_title}}" has been sent for peer review.

The review process typically takes 4-8 weeks. We will notify you once we receive the reviewers' feedback.

Thank you for your patience.

Best regards,
The Editorial Team
{{journal_name}}""",
                "placeholders": json.dumps(["author_name", "paper_title", "journal_name", "paper_id"]),
                "category": "review"
            },
            {
                "name": "Revision Requested",
                "slug": "revision_requested",
                "subject": "Revision Requested for Your Paper - {{paper_title}}",
                "body_template": """Dear {{author_name}},

Thank you for submitting your paper titled "{{paper_title}}" to {{journal_name}}.

After careful review, the reviewers have requested revisions to your manuscript. Please find the reviewer comments below:

{{reviewer_comments}}

Please submit your revised manuscript within 30 days. When resubmitting, please include a detailed response to each reviewer comment.

If you have any questions, please don't hesitate to contact us.

Best regards,
The Editorial Team
{{journal_name}}""",
                "placeholders": json.dumps(["author_name", "paper_title", "journal_name", "paper_id", "reviewer_comments"]),
                "category": "decision"
            },
            {
                "name": "Paper Accepted",
                "slug": "paper_accepted",
                "subject": "Congratulations! Your Paper Has Been Accepted - {{paper_title}}",
                "body_template": """Dear {{author_name}},

We are pleased to inform you that your paper titled "{{paper_title}}" has been accepted for publication in {{journal_name}}.

Congratulations on this achievement!

Our production team will contact you shortly with information about the publication process, including proofreading and formatting requirements.

Thank you for choosing {{journal_name}} for your research.

Best regards,
The Editorial Team
{{journal_name}}""",
                "placeholders": json.dumps(["author_name", "paper_title", "journal_name", "paper_id"]),
                "category": "decision"
            },
            {
                "name": "Paper Rejected",
                "slug": "paper_rejected",
                "subject": "Decision on Your Paper Submission - {{paper_title}}",
                "body_template": """Dear {{author_name}},

Thank you for submitting your paper titled "{{paper_title}}" to {{journal_name}}.

After careful consideration by our reviewers and editorial board, we regret to inform you that your paper has not been accepted for publication.

{{rejection_reason}}

We encourage you to consider the feedback provided and submit future research to our journal.

Thank you for your interest in {{journal_name}}.

Best regards,
The Editorial Team
{{journal_name}}""",
                "placeholders": json.dumps(["author_name", "paper_title", "journal_name", "paper_id", "rejection_reason"]),
                "category": "decision"
            },
            {
                "name": "General Inquiry",
                "slug": "general_inquiry",
                "subject": "RE: {{paper_title}}",
                "body_template": """Dear {{author_name}},

Thank you for your inquiry regarding your paper titled "{{paper_title}}".

{{custom_message}}

If you have any further questions, please don't hesitate to contact us.

Best regards,
{{sender_name}}
{{journal_name}}""",
                "placeholders": json.dumps(["author_name", "paper_title", "journal_name", "paper_id", "custom_message", "sender_name"]),
                "category": "general"
            },
            {
                "name": "Reviewer Invitation",
                "slug": "reviewer_invitation",
                "subject": "Invitation to Review - {{paper_title}}",
                "body_template": """Dear {{reviewer_name}},

We would like to invite you to review a paper titled "{{paper_title}}" for {{journal_name}}.

Abstract:
{{paper_abstract}}

If you are able to review this paper, please respond within 7 days. The review deadline would be {{review_deadline}}.

To accept or decline this invitation, please click the link below:
{{invitation_link}}

Thank you for your valuable contribution to the peer review process.

Best regards,
The Editorial Team
{{journal_name}}""",
                "placeholders": json.dumps(["reviewer_name", "paper_title", "journal_name", "paper_abstract", "review_deadline", "invitation_link"]),
                "category": "review"
            },
            {
                "name": "Status Update",
                "slug": "status_update",
                "subject": "Status Update - {{paper_title}}",
                "body_template": """Dear {{author_name}},

This is an update regarding your paper titled "{{paper_title}}".

{{status_message}}

Current Status: {{current_status}}

If you have any questions, please contact our editorial office.

Best regards,
The Editorial Team
{{journal_name}}""",
                "placeholders": json.dumps(["author_name", "paper_title", "journal_name", "paper_id", "status_message", "current_status"]),
                "category": "general"
            }
        ]
        
        for template in default_templates:
            try:
                # Check if template already exists
                result = db.execute(text("SELECT id FROM email_template WHERE slug = :slug"), {"slug": template["slug"]})
                if result.fetchone():
                    print(f"  - Template '{template['name']}' already exists")
                    continue
                
                db.execute(text("""
                    INSERT INTO email_template (name, slug, subject, body_template, placeholders, category, is_active)
                    VALUES (:name, :slug, :subject, :body_template, :placeholders, :category, TRUE)
                """), template)
                print(f"  ✓ Added template: {template['name']}")
            except Exception as e:
                print(f"  - Error adding template '{template['name']}': {e}")
        
        db.commit()
        print("\n✓ Migration completed successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"\n✗ Migration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_migration()
