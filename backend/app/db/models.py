"""SQLAlchemy ORM Models mapped to MySQL database"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, func, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, date
from app.db.database import Base


class User(Base):
    """User model mapping to existing MySQL user table"""
    __tablename__ = "user"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=True, default="User")
    fname = Column(String(100), nullable=True)
    lname = Column(String(100), nullable=True)
    mname = Column(String(100), nullable=True)
    title = Column(String(100), nullable=True)
    affiliation = Column(String(255), nullable=True)
    specialization = Column(Text, nullable=True)
    contact = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)
    added_on = Column(DateTime, default=datetime.utcnow, nullable=True)
    # New author profile fields
    salutation = Column(String(20), nullable=True)  # Prof. Dr., Prof., Dr., Mr., Ms.
    designation = Column(String(100), nullable=True)  # Designation/Occupation
    department = Column(String(200), nullable=True)
    organisation = Column(String(255), nullable=True)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "fname": self.fname,
            "lname": self.lname,
            "mname": self.mname,
            "title": self.title,
            "affiliation": self.affiliation,
            "specialization": self.specialization,
            "contact": self.contact,
            "address": self.address,
            "added_on": self.added_on.isoformat() if self.added_on else None,
            "salutation": self.salutation,
            "designation": self.designation,
            "department": self.department,
            "organisation": self.organisation
        }

# Research categories for journal classification
RESEARCH_CATEGORIES = [
    "Arts & Humanities",
    "Social Sciences",
    "Business & Economics",
    "Law",
    "Education",
    "Computer Science",
    "Engineering",
    "Physical Sciences",
    "Life Sciences",
    "Medicine & Health"
]


class Journal(Base):
    """Journal model mapping to existing MySQL journal table"""
    __tablename__ = "journal"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    fld_id = Column(Integer, primary_key=True, index=True)
    fld_journal_name = Column(String(200), nullable=True)
    fld_primary_category = Column(String(100), nullable=True)  # Research category for recommendations
    freq = Column(String(250), nullable=True)  # Frequency
    issn_ol = Column(String(250), nullable=True)  # ISSN Online
    issn_prt = Column(String(250), nullable=True)  # ISSN Print
    cheif_editor = Column(String(250), nullable=True)
    co_editor = Column(String(250), nullable=True)
    password = Column(String(100), nullable=False)
    abs_ind = Column(String(300), nullable=True)  # Abstract Indexing
    short_form = Column(String(255), nullable=False)
    journal_image = Column(String(255), nullable=False)
    journal_logo = Column(String(200), nullable=False)
    guidelines = Column(String(200), nullable=False)
    copyright = Column(String(200), nullable=False)
    membership = Column(String(200), nullable=False)
    subscription = Column(String(200), nullable=False)
    publication = Column(String(200), nullable=False)
    advertisement = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    added_on = Column(Date, nullable=False)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.fld_id,
            "name": self.fld_journal_name,
            "primary_category": self.fld_primary_category,
            "frequency": self.freq,
            "issn_online": self.issn_ol,
            "issn_print": self.issn_prt,
            "chief_editor": self.cheif_editor,
            "co_editor": self.co_editor,
            "abstract_indexing": self.abs_ind,
            "short_form": self.short_form,
            "journal_image": self.journal_image,
            "journal_logo": self.journal_logo,
            "guidelines": self.guidelines,
            "copyright": self.copyright,
            "membership": self.membership,
            "subscription": self.subscription,
            "publication": self.publication,
            "advertisement": self.advertisement,
            "description": self.description,
            "added_on": self.added_on.isoformat() if self.added_on else None
        }


class JournalDetails(Base):
    """Journal Details model mapping to existing MySQL journal_details table"""
    __tablename__ = "journal_details"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    journal_id = Column(String(50), nullable=False)
    about_journal = Column(Text, nullable=True)
    cheif_say = Column(Text, nullable=True)  # Chief's say
    aim_objective = Column(Text, nullable=True)
    criteria = Column(Text, nullable=True)
    scope = Column(Text, nullable=True)
    guidelines = Column(Text, nullable=True)
    readings = Column(Text, nullable=True)
    added_on = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "journal_id": self.journal_id,
            "about_journal": self.about_journal,
            "chief_say": self.cheif_say,
            "aim_objective": self.aim_objective,
            "criteria": self.criteria,
            "scope": self.scope,
            "guidelines": self.guidelines,
            "readings": self.readings,
            "added_on": self.added_on.isoformat() if self.added_on else None
        }


class Paper(Base):
    """Paper/Submission model mapping to existing MySQL paper table"""
    __tablename__ = "paper"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    paper_code = Column(String(200), nullable=False, default="")
    journal = Column(Integer, nullable=True)  # Journal ID as INT
    title = Column(String(500), nullable=False, default="")
    abstract = Column(String(2500), nullable=False, default="")
    keyword = Column(String(1000), nullable=False, default="")
    file = Column(String(200), nullable=False, default="")  # Legacy field - kept for backwards compatibility
    title_page = Column(String(200), nullable=True, default="")  # Title page with author info
    blinded_manuscript = Column(String(200), nullable=True, default="")  # Blinded manuscript for review
    # Revision files (populated during resubmission)
    revised_track_changes = Column(String(200), nullable=True, default="")  # Manuscript with track changes
    revised_clean = Column(String(200), nullable=True, default="")  # Clean revised manuscript
    response_to_reviewer = Column(String(200), nullable=True, default="")  # Response letter to reviewer
    added_on = Column(DateTime, nullable=False, default=datetime.utcnow)
    added_by = Column(String(100), nullable=False, default="")
    status = Column(String(50), nullable=False, default="submitted")
    mailstatus = Column(String(10), nullable=False, default="0")
    volume = Column(String(100), nullable=False, default="")
    issue = Column(String(100), nullable=False, default="")
    author = Column(String(100), nullable=False, default="")
    coauth = Column(String(200), nullable=False, default="")
    rev = Column(String(200), nullable=False, default="")
    # Version tracking fields
    version_number = Column(Integer, nullable=False, default=1)
    revision_count = Column(Integer, nullable=False, default=0)
    revision_deadline = Column(DateTime, nullable=True)
    revision_notes = Column(Text, nullable=True)
    revision_requested_date = Column(DateTime, nullable=True)
    revision_type = Column(String(20), nullable=True)  # 'minor' or 'major'
    editor_comments = Column(Text, nullable=True)  # Editor's decision comments
    # New paper metadata fields
    research_area = Column(String(200), nullable=True)
    message_to_editor = Column(Text, nullable=True)
    terms_accepted = Column(Boolean, nullable=False, default=False)
    paper_type = Column(String(50), nullable=True, default="Full Length Article")  # Full Length Article, Review Paper, Short Communication, Case Study, Technical Note
    # Decision tracking
    accepted_on = Column(DateTime, nullable=True)  # When paper was accepted
    
    # Relationship to co-authors
    co_authors = relationship("PaperCoAuthor", back_populates="paper", cascade="all, delete-orphan")
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "paper_code": self.paper_code,
            "journal": self.journal,
            "title": self.title,
            "abstract": self.abstract,
            "keywords": self.keyword,
            "file": self.file,
            "title_page": self.title_page,
            "blinded_manuscript": self.blinded_manuscript,
            "revised_track_changes": self.revised_track_changes,
            "revised_clean": self.revised_clean,
            "response_to_reviewer": self.response_to_reviewer,
            "added_on": self.added_on.isoformat() if self.added_on else None,
            "added_by": self.added_by,
            "status": self.status,
            "author": self.author,
            "coauth": self.coauth,
            "research_area": self.research_area,
            "message_to_editor": self.message_to_editor,
            "terms_accepted": self.terms_accepted,
            "paper_type": self.paper_type,
            "accepted_on": self.accepted_on.isoformat() if self.accepted_on else None
        }


class PaperPublished(Base):
    """Published papers model"""
    __tablename__ = "paper_published"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(250), nullable=False)
    abstract = Column(String(2000), nullable=False, default="")
    p_reference = Column(Text, nullable=True)  # References/citations
    author = Column(String(1000), nullable=False, default="")
    journal = Column(String(250), nullable=False, default="")
    journal_id = Column(Integer, nullable=False)
    volume = Column(String(250), nullable=False, default="")
    issue = Column(String(250), nullable=False, default="")
    date = Column(DateTime, nullable=False)
    pages = Column(String(250), nullable=False, default="")
    keyword = Column(String(300), nullable=False, default="")
    language = Column(String(20), nullable=False, default="en")
    paper = Column(String(200), nullable=True)  # File path
    # Access control - subscription by default, admin can change to open
    access_type = Column(String(20), nullable=False, default="subscription")  # subscription, open
    email = Column(String(100), nullable=True)  # Author email
    affiliation = Column(String(500), nullable=True)  # Author affiliation (increased size)
    # Structured author information as JSON
    co_authors_json = Column(Text, nullable=True)  # JSON array of {name, affiliation, is_corresponding, is_primary}
    # DOI fields
    doi = Column(String(100), nullable=True)  # DOI identifier (e.g., 10.58517/IJICM.2024.1101)
    doi_status = Column(String(50), nullable=False, default="pending")  # pending, registered, failed
    doi_registered_at = Column(DateTime, nullable=True)  # When DOI was registered with Crossref
    crossref_batch_id = Column(String(100), nullable=True)  # Crossref deposit batch ID
    # Link to original submission
    paper_submission_id = Column(Integer, nullable=True)  # Reference to original paper.id
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "title": self.title,
            "abstract": self.abstract,
            "p_reference": self.p_reference,
            "author": self.author,
            "journal": self.journal,
            "journal_id": self.journal_id,
            "volume": self.volume,
            "issue": self.issue,
            "date": self.date.isoformat() if self.date else None,
            "pages": self.pages,
            "keyword": self.keyword,
            "language": self.language,
            "paper": self.paper,
            "access_type": self.access_type,
            "email": self.email,
            "affiliation": self.affiliation,
            "co_authors_json": self.co_authors_json,
            "doi": self.doi,
            "doi_status": self.doi_status,
            "doi_registered_at": self.doi_registered_at.isoformat() if self.doi_registered_at else None,
            "crossref_batch_id": self.crossref_batch_id,
            "paper_submission_id": self.paper_submission_id
        }


class PaperVersion(Base):
    """Paper version history model for tracking all submissions and revisions"""
    __tablename__ = "paper_version"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    file = Column(String(200), nullable=False)
    file_size = Column(Integer, nullable=True)
    uploaded_on = Column(DateTime, nullable=False, default=datetime.utcnow)
    revision_reason = Column(Text, nullable=True)
    change_summary = Column(Text, nullable=True)
    uploaded_by = Column(String(100), nullable=False)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "version_number": self.version_number,
            "file": self.file,
            "file_size": self.file_size,
            "uploaded_on": self.uploaded_on.isoformat() if self.uploaded_on else None,
            "revision_reason": self.revision_reason,
            "change_summary": self.change_summary,
            "uploaded_by": self.uploaded_by
        }


class PaperComment(Base):
    """Paper comments/feedback model"""
    __tablename__ = "paper_comment"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, nullable=True)
    comment_by = Column(String(255), nullable=True)
    comment_text = Column(Text, nullable=True)
    added_on = Column(DateTime, nullable=True, default=datetime.utcnow)


class OnlineReview(Base):
    """Online review model"""
    __tablename__ = "online_review"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, nullable=True)
    reviewer_id = Column(String(100), nullable=True)
    assigned_on = Column(Date, nullable=True)
    submitted_on = Column(DateTime, nullable=True)
    date_submitted = Column(DateTime, nullable=True)
    review_status = Column(String(50), default="pending", nullable=False)  # pending, in_progress, submitted, completed
    review_submission_id = Column(Integer, nullable=True)
    invitation_id = Column(Integer, nullable=True)
    due_date = Column(DateTime, nullable=True)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "reviewer_id": self.reviewer_id,
            "assigned_on": self.assigned_on.isoformat() if self.assigned_on else None,
            "submitted_on": self.submitted_on.isoformat() if self.submitted_on else None,
            "review_status": self.review_status
        }


class Editor(Base):
    """Editor model"""
    __tablename__ = "editor"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    editor_name = Column(String(100), nullable=True)
    editor_email = Column(String(100), nullable=True)
    editor_address = Column(String(200), nullable=True)
    editor_contact = Column(String(100), nullable=True)
    editor_affiliation = Column(String(200), nullable=True)
    editor_department = Column(String(200), nullable=True)
    editor_college = Column(String(200), nullable=True)
    password = Column(String(200), nullable=True)
    journal_id = Column(Integer, nullable=True)  # Journal this editor is assigned to (INT)
    role = Column(String(50), nullable=True)  # Editor, Admin
    editor_type = Column(String(50), nullable=True, default="section_editor")  # chief_editor, section_editor
    added_on = Column(DateTime, default=datetime.utcnow, nullable=True)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "editor_name": self.editor_name,
            "editor_email": self.editor_email,
            "journal_id": self.journal_id,
            "role": self.role,
            "editor_type": self.editor_type,
            "editor_affiliation": self.editor_affiliation,
            "editor_department": self.editor_department,
            "editor_college": self.editor_college,
            "editor_contact": self.editor_contact,
            "added_on": self.added_on.isoformat() if self.added_on else None
        }


class Volume(Base):
    """Volume model for journal volumes"""
    __tablename__ = "volume"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    journal = Column(String(250), nullable=False)  # Journal ID as string
    volume_no = Column(Integer, nullable=False)
    year = Column(String(200), nullable=True)
    added_on = Column(Date, nullable=True)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "journal_id": self.journal,
            "volume_no": self.volume_no,
            "year": self.year,
            "added_on": self.added_on.isoformat() if self.added_on else None
        }


class Issue(Base):
    """Issue model for journal issues within volumes"""
    __tablename__ = "issue"
    __table_args__ = {"mysql_engine": "MyISAM"}
    
    id = Column(Integer, primary_key=True, index=True)
    pages = Column(String(7), nullable=True)  # Page range e.g., "1-212"
    month = Column(String(16), nullable=True)  # Publication period e.g., "July-December"
    volume = Column(Integer, nullable=True)  # Volume ID reference
    journal = Column(Integer, nullable=True)  # Journal ID reference
    add_on = Column(String(10), nullable=True)
    issue_no = Column(Integer, nullable=True)  # Issue number within volume (1, 2, 3, 4)
    complete_issue = Column(String(10), nullable=True)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "pages": self.pages,
            "month": self.month,
            "volume_id": self.volume,
            "journal_id": self.journal,
            "issue_no": self.issue_no,
            "complete_issue": self.complete_issue
        }


class ReviewerInvitation(Base):
    """Reviewer invitation model for tracking reviewer assignments and acceptances"""
    __tablename__ = "reviewer_invitation"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, nullable=False, index=True)
    reviewer_id = Column(Integer, nullable=True)  # Reviewer user ID (if known)
    reviewer_email = Column(String(255), nullable=False)
    reviewer_name = Column(String(255), nullable=True)
    journal_id = Column(String(100), nullable=True)
    
    # Invitation token for magic link
    invitation_token = Column(String(255), nullable=False, unique=True, index=True)
    token_expiry = Column(DateTime, nullable=False)
    
    # Status tracking
    status = Column(String(50), default="pending")  # pending, accepted, declined, expired
    
    # Timestamps
    invited_on = Column(DateTime, default=datetime.utcnow)
    accepted_on = Column(DateTime, nullable=True)
    declined_on = Column(DateTime, nullable=True)
    
    # Additional info
    invitation_message = Column(Text, nullable=True)
    decline_reason = Column(Text, nullable=True)
    is_external = Column(Boolean, default=False)  # True if reviewer is not in the system
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "reviewer_id": self.reviewer_id,
            "reviewer_email": self.reviewer_email,
            "reviewer_name": self.reviewer_name,
            "journal_id": self.journal_id,
            "status": self.status,
            "invited_on": self.invited_on.isoformat() if self.invited_on else None,
            "accepted_on": self.accepted_on.isoformat() if self.accepted_on else None,
            "declined_on": self.declined_on.isoformat() if self.declined_on else None,
            "token_expiry": self.token_expiry.isoformat() if self.token_expiry else None,
            "is_external": self.is_external,
        }


class ReviewSubmission(Base):
    """Review submission model for storing reviewer feedback with version control"""
    __tablename__ = "review_submission"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Link to paper and reviewer
    paper_id = Column(Integer, nullable=False, index=True)
    reviewer_id = Column(String(100), nullable=False, index=True)
    
    # Link to online_review assignment
    assignment_id = Column(Integer, nullable=True, index=True)
    
    # Paper version being reviewed (for resubmissions)
    paper_version = Column(Integer, nullable=False, default=1)
    
    # Review ratings (1-5 scale)
    technical_quality = Column(Integer, nullable=True)  # 1-5
    clarity = Column(Integer, nullable=True)  # 1-5
    originality = Column(Integer, nullable=True)  # 1-5
    significance = Column(Integer, nullable=True)  # 1-5
    overall_rating = Column(Integer, nullable=True)  # 1-5
    
    # Review comments
    author_comments = Column(Text, nullable=True)  # Public comments for authors
    confidential_comments = Column(Text, nullable=True)  # Private comments for editors
    
    # Recommendation
    recommendation = Column(String(50), nullable=True)  # accept, minor_revisions, major_revisions, reject
    
    # File upload tracking for review reports (multiple versions)
    review_report_file = Column(String(500), nullable=True)  # Path to uploaded review report
    file_version = Column(Integer, default=1)  # Version number for multiple uploads
    
    # Status and timestamps
    status = Column(String(50), default="draft")  # draft, submitted
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    submitted_at = Column(DateTime, nullable=True)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "reviewer_id": self.reviewer_id,
            "assignment_id": self.assignment_id,
            "paper_version": self.paper_version,
            "technical_quality": self.technical_quality,
            "clarity": self.clarity,
            "originality": self.originality,
            "significance": self.significance,
            "overall_rating": self.overall_rating,
            "author_comments": self.author_comments,
            "confidential_comments": self.confidential_comments,
            "recommendation": self.recommendation,
            "review_report_file": self.review_report_file,
            "file_version": self.file_version,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
        }


class PaperCoAuthor(Base):
    """Paper co-author model for storing structured co-author information"""
    __tablename__ = "paper_co_author"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("paper.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Author details
    salutation = Column(String(20), nullable=True)  # Prof. Dr., Prof., Dr., Mr., Ms.
    first_name = Column(String(100), nullable=False)
    middle_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=True)
    designation = Column(String(100), nullable=True)  # Designation/Occupation
    department = Column(String(200), nullable=True)
    organisation = Column(String(255), nullable=True)
    
    # Order and flags
    author_order = Column(Integer, nullable=False, default=1)
    is_corresponding = Column(Boolean, nullable=False, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship back to paper
    paper = relationship("Paper", back_populates="co_authors")
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "salutation": self.salutation,
            "first_name": self.first_name,
            "middle_name": self.middle_name,
            "last_name": self.last_name,
            "email": self.email,
            "designation": self.designation,
            "department": self.department,
            "organisation": self.organisation,
            "author_order": self.author_order,
            "is_corresponding": self.is_corresponding,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================================
# MULTI-ROLE SYSTEM MODELS
# ============================================================================

class UserRole(Base):
    """
    Junction table for user-role assignments.
    Allows users to have multiple roles (author, reviewer, editor, admin).
    """
    __tablename__ = "user_role"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # author, reviewer, editor, admin
    status = Column(String(20), nullable=False, default="approved")  # pending, approved, rejected
    
    # Approval tracking
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    approved_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejected_reason = Column(Text, nullable=True)
    
    # For editor role - journal assignment and type
    journal_id = Column(Integer, nullable=True)  # Links to journal.fld_id
    editor_type = Column(String(50), nullable=True)  # chief_editor, section_editor (for editor role)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="user_roles")
    approver = relationship("User", foreign_keys=[approved_by])
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "role": self.role,
            "status": self.status,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejected_reason": self.rejected_reason,
            "journal_id": self.journal_id,
            "editor_type": self.editor_type,
        }


class RoleRequest(Base):
    """
    Tracks role access requests from users.
    Users can request access to additional roles through their dashboard.
    """
    __tablename__ = "role_request"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_role = Column(String(50), nullable=False)  # author, reviewer, editor
    status = Column(String(20), nullable=False, default="pending")  # pending, approved, rejected
    
    # Request details
    reason = Column(Text, nullable=True)  # Why the user wants this role
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Processing details
    processed_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    processed_at = Column(DateTime, nullable=True)
    admin_notes = Column(Text, nullable=True)  # Notes from admin during approval/rejection
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="role_requests")
    processor = relationship("User", foreign_keys=[processed_by])
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "requested_role": self.requested_role,
            "status": self.status,
            "reason": self.reason,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "processed_by": self.processed_by,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "admin_notes": self.admin_notes,
        }


# ============================================================================
# PAPER CORRESPONDENCE MODEL
# ============================================================================

class EmailTemplate(Base):
    """
    Model for email templates used in correspondence.
    Templates can use placeholders like {{author_name}}, {{paper_title}}, etc.
    """
    __tablename__ = "email_template"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # Display name
    slug = Column(String(50), unique=True, nullable=False, index=True)  # Unique identifier
    subject = Column(String(500), nullable=False)  # Email subject template
    body_template = Column(Text, nullable=False)  # Email body template with placeholders
    placeholders = Column(Text, nullable=True)  # JSON list of available placeholders
    category = Column(String(50), nullable=False)  # submission, review, decision, general
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    
    def to_dict(self):
        """Convert model to dictionary"""
        import json
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "subject": self.subject,
            "body_template": self.body_template,
            "placeholders": json.loads(self.placeholders) if self.placeholders else [],
            "category": self.category,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PaperCorrespondence(Base):
    """
    Model for tracking all email correspondence related to paper lifecycle.
    Stores email history with delivery status for author visibility.
    """
    __tablename__ = "paper_correspondence"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("paper.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Sender info (admin/editor who sent the email)
    sender_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    sender_role = Column(String(50), nullable=True)  # admin, editor
    
    # Recipient info (author only)
    recipient_email = Column(String(255), nullable=False)
    recipient_name = Column(String(255), nullable=True)
    
    # Email content
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    
    # Template reference
    template_id = Column(Integer, ForeignKey("email_template.id", ondelete="SET NULL"), nullable=True)
    
    # Email metadata
    email_type = Column(String(50), nullable=False)  # submission_confirmed, under_review, revision_requested, accepted, rejected, published, resubmitted, general_inquiry
    status_at_send = Column(String(50), nullable=True)  # Paper status when email was sent
    
    # Read tracking for author
    is_read = Column(Boolean, default=False, nullable=False)
    read_at = Column(DateTime, nullable=True)
    
    # Delivery tracking
    delivery_status = Column(String(50), nullable=False, default="pending")  # pending, sent, delivered, failed, bounced
    webhook_id = Column(String(100), nullable=True, unique=True, index=True)  # For delivery webhook tracking
    webhook_received_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    
    # Relationships
    paper = relationship("Paper", backref="correspondence")
    sender = relationship("User", foreign_keys=[sender_id])
    template = relationship("EmailTemplate")
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "sender_id": self.sender_id,
            "sender_role": self.sender_role,
            "sender_name": f"{self.sender.fname} {self.sender.lname}" if self.sender else "System",
            "recipient_email": self.recipient_email,
            "recipient_name": self.recipient_name,
            "subject": self.subject,
            "body": self.body,
            "template_id": self.template_id,
            "email_type": self.email_type,
            "status_at_send": self.status_at_send,
            "is_read": self.is_read,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "delivery_status": self.delivery_status,
            "webhook_id": self.webhook_id,
            "webhook_received_at": self.webhook_received_at.isoformat() if self.webhook_received_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
        }


# ============================================================================
# NEWS / ANNOUNCEMENTS MODEL
# ============================================================================

class News(Base):
    """
    Model for news and announcements displayed on the website.
    Can be journal-specific or general announcements.
    """
    __tablename__ = "news"
    __table_args__ = {"extend_existing": True, "mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    added_on = Column(Date, default=datetime.utcnow, nullable=True)
    journal_id = Column(Integer, ForeignKey("journal.fld_id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Relationship to journal
    journal = relationship("Journal", backref="news_items")
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "added_on": self.added_on.isoformat() if self.added_on else None,
            "journal_id": self.journal_id,
            "journal_name": self.journal.fld_journal_name if self.journal else None,
        }


# ============================================================================
# COPYRIGHT TRANSFER FORM MODEL
# ============================================================================

class CopyrightForm(Base):
    """
    Model for copyright transfer forms required after paper acceptance.
    Authors must complete this form within 48 hours of acceptance.
    """
    __tablename__ = "copyright_form"
    __table_args__ = {"mysql_engine": "InnoDB"}
    
    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("paper.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Status tracking
    status = Column(String(20), nullable=False, default="pending")  # pending, completed, expired
    
    # Deadline and reminders
    deadline = Column(DateTime, nullable=False)  # 48 hours from acceptance
    reminder_count = Column(Integer, nullable=False, default=0)  # 0, 1, 2
    last_reminder_at = Column(DateTime, nullable=True)
    
    # Form data (stored as JSON)
    author_name = Column(String(255), nullable=True)
    author_affiliation = Column(String(500), nullable=True)
    co_authors_consent = Column(Boolean, nullable=True, default=False)  # Confirms co-authors agreed
    copyright_agreed = Column(Boolean, nullable=True, default=False)  # Agrees to transfer
    signature = Column(String(255), nullable=True)  # Digital signature (typed name)
    signed_date = Column(DateTime, nullable=True)
    
    # Additional declarations
    original_work = Column(Boolean, nullable=True, default=False)  # Work is original
    no_conflict = Column(Boolean, nullable=True, default=False)  # No conflict of interest
    rights_transfer = Column(Boolean, nullable=True, default=False)  # Agrees to rights transfer
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    paper = relationship("Paper", backref="copyright_form")
    author = relationship("User", backref="copyright_forms")
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "author_id": self.author_id,
            "status": self.status,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "reminder_count": self.reminder_count,
            "last_reminder_at": self.last_reminder_at.isoformat() if self.last_reminder_at else None,
            "author_name": self.author_name,
            "author_affiliation": self.author_affiliation,
            "co_authors_consent": self.co_authors_consent,
            "copyright_agreed": self.copyright_agreed,
            "signature": self.signature,
            "signed_date": self.signed_date.isoformat() if self.signed_date else None,
            "original_work": self.original_work,
            "no_conflict": self.no_conflict,
            "rights_transfer": self.rights_transfer,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }