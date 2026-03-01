"""Editor API endpoints"""
import os
import json
from pathlib import Path
from fastapi import APIRouter, Depends, status, HTTPException, Query, Request, Body, BackgroundTasks, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_, exists, and_
from datetime import datetime, timedelta
import uuid
import secrets
from app.db.database import get_db
from app.db.models import User, Paper, OnlineReview, Editor, ReviewerInvitation, Journal, ReviewSubmission, PaperPublished, UserRole, PaperCoAuthor
from app.core.security import get_current_user, get_current_user_from_token_or_query
from app.core.rate_limit import limiter
from app.utils.auth_helpers import check_role, role_matches, get_editor_journal_ids, editor_has_journal_access
from app.utils.email_service import send_reviewer_invitation
from app.services.crossref_service import CrossrefService, generate_doi, DOIStatus
from app.services.correspondence_service import create_and_send_correspondence
from app.schemas.publish import (
    PublishPaperRequest, PublishPaperResponse, DOIResponse, 
    PublishedPaperResponse, AccessType
)

router = APIRouter(prefix="/api/v1/editor", tags=["Editor"])


# ============================================================================
# EDITOR JOURNAL ACCESS ENDPOINTS
# ============================================================================

@router.get("/my-journals")
@limiter.limit("100/minute")
async def get_my_journals(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get journals assigned to the current editor.
    
    Returns:
        List of journals the editor has access to manage
    """
    if not check_role(current_user.get("role"), "editor"):
        raise HTTPException(status_code=403, detail="Editor access required")
    
    from app.utils.auth_helpers import get_editor_journal_info
    journals = get_editor_journal_info(current_user.get("email"), db)
    
    if not journals:
        return {
            "message": "No journals assigned to this editor",
            "journals": []
        }
    
    # Add paper statistics for each journal
    for journal in journals:
        journal_id = journal["journal_id"]
        # Count papers in this journal (journal is now INT)
        total_papers = db.query(Paper).filter(Paper.journal == journal_id).count()
        pending_papers = db.query(Paper).filter(
            Paper.journal == journal_id,
            Paper.status == "submitted"
        ).count()
        under_review = db.query(Paper).filter(
            Paper.journal == journal_id,
            Paper.status == "under_review"
        ).count()
        
        journal["paper_stats"] = {
            "total": total_papers,
            "pending": pending_papers,
            "under_review": under_review
        }
    
    return {
        "total": len(journals),
        "journals": journals
    }


@router.put("/journals/{journal_id}")
@limiter.limit("50/minute")
async def update_editor_journal(
    request: Request,
    journal_id: int,
    description: str = Body(None),
    co_editor: str = Body(None),
    journal_logo: str = Body(None),
    guidelines: str = Body(None),
    # Chief editor only fields
    fld_journal_name: str = Body(None),
    freq: str = Body(None),
    issn_ol: str = Body(None),
    issn_prt: str = Body(None),
    cheif_editor: str = Body(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a journal that the editor is assigned to.
    
    Chief editors can update all fields.
    Section editors can only update: description, co_editor, journal_logo, guidelines.
    
    Args:
        journal_id: Journal ID to update
        description: Journal description
        co_editor: Co-editor name
        journal_logo: Journal logo path
        guidelines: Guidelines URL/path
        fld_journal_name: Journal name (chief editor only)
        freq: Publication frequency (chief editor only)
        issn_ol: ISSN Online (chief editor only)
        issn_prt: ISSN Print (chief editor only)
        cheif_editor: Chief editor name (chief editor only)
        
    Returns:
        Updated journal information
    """
    if not check_role(current_user.get("role"), "editor"):
        raise HTTPException(status_code=403, detail="Editor access required")
    
    # Verify editor has access to this journal
    if not editor_has_journal_access(current_user.get("email"), journal_id, db):
        raise HTTPException(
            status_code=403,
            detail="You don't have access to edit this journal"
        )
    
    # Get editor's type for this journal
    editor = db.query(Editor).filter(
        Editor.editor_email == current_user.get("email"),
        Editor.journal_id == journal_id  # journal_id is now INT
    ).first()
    
    is_chief_editor = editor and editor.editor_type == "chief_editor"
    
    # Get journal
    journal = db.query(Journal).filter(Journal.fld_id == journal_id).first()
    if not journal:
        raise HTTPException(status_code=404, detail="Journal not found")
    
    # Update fields based on editor type
    # Section editors can only update these fields
    if description is not None:
        journal.description = description
    if co_editor is not None:
        journal.co_editor = co_editor
    if journal_logo is not None:
        journal.journal_logo = journal_logo
    if guidelines is not None:
        journal.guidelines = guidelines
    
    # Chief editors can also update these fields
    if is_chief_editor:
        if fld_journal_name is not None:
            journal.fld_journal_name = fld_journal_name
        if freq is not None:
            journal.freq = freq
        if issn_ol is not None:
            journal.issn_ol = issn_ol
        if issn_prt is not None:
            journal.issn_prt = issn_prt
        if cheif_editor is not None:
            journal.cheif_editor = cheif_editor
    else:
        # Section editor tried to update restricted fields
        restricted_updated = any([
            fld_journal_name is not None,
            freq is not None,
            issn_ol is not None,
            issn_prt is not None,
            cheif_editor is not None
        ])
        if restricted_updated:
            raise HTTPException(
                status_code=403,
                detail="Section editors cannot update journal name, frequency, ISSN, or chief editor fields"
            )
    
    db.commit()
    db.refresh(journal)
    
    return {
        "id": journal.fld_id,
        "name": journal.fld_journal_name,
        "description": journal.description,
        "co_editor": journal.co_editor,
        "journal_logo": journal.journal_logo,
        "guidelines": journal.guidelines,
        "frequency": journal.freq,
        "issn_online": journal.issn_ol,
        "issn_print": journal.issn_prt,
        "chief_editor": journal.cheif_editor,
        "short_form": journal.short_form,
        "editor_type": editor.editor_type if editor else None,
        "message": "Journal updated successfully"
    }


# ============================================================================
# DASHBOARD ENDPOINTS  
# ============================================================================

@router.get("/dashboard/stats")
@limiter.limit("100/minute")
async def get_editor_stats(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get editor dashboard statistics.
    
    Returns:
        Dictionary with editor's paper management stats (filtered by assigned journals)
    """
    if not check_role(current_user.get("role"), "editor"):
        raise HTTPException(status_code=403, detail="Editor access required")
    
    # Get editor's assigned journals
    allowed_journals = get_editor_journal_ids(current_user.get("email"), db)
    
    # Build base query - filter by editor's journals (strict mode: no journals = no papers)
    base_query = db.query(Paper)
    if not allowed_journals:
        # Editor has no assigned journals - return zero counts
        return {
            "total_papers": 0,
            "pending_review": 0,
            "under_review": 0,
            "ready_publish": 0,
            "journals_access": []
        }
    base_query = base_query.filter(Paper.journal.in_(allowed_journals))
    
    total_papers = base_query.count()
    
    pending_review = base_query.filter(
        Paper.status == "submitted"
    ).count()
    
    under_review = base_query.filter(
        Paper.status == "under_review"
    ).count()
    
    ready_publish = base_query.filter(
        Paper.status == "accepted"
    ).count()
    
    return {
        "total_papers": total_papers,
        "pending_review": pending_review,
        "under_review": under_review,
        "ready_publish": ready_publish,
        "journals_access": allowed_journals
    }


@router.get("/paper-queue")
@limiter.limit("100/minute")
async def get_paper_queue(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: str = Query(None),
    journal_id: int = Query(None, description="Filter by specific journal"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get paper queue for editor to manage.
    Papers are filtered to only show those from journals the editor has access to.
    
    Args:
        skip: Number of records to skip
        limit: Number of records to return
        status_filter: Filter by paper status (pending, under_review, accepted, rejected)
        journal_id: Filter by specific journal
        
    Returns:
        List of papers for editorial management
    """
    if not check_role(current_user.get("role"), "editor"):
        raise HTTPException(status_code=403, detail="Editor access required")
    
    # Get editor's assigned journals
    allowed_journals = get_editor_journal_ids(current_user.get("email"), db)
    
    # If specific journal requested, verify editor has access
    if journal_id:
        if allowed_journals and journal_id not in allowed_journals:
            raise HTTPException(
                status_code=403, 
                detail=f"You don't have access to journal {journal_id}"
            )
    
    query = db.query(Paper)
    
    # Strict mode: no assigned journals = no papers
    if not allowed_journals:
        return {
            "total": 0,
            "skip": skip,
            "limit": limit,
            "papers": []
        }
    
    # Filter by editor's allowed journals
    if journal_id:
        query = query.filter(Paper.journal == journal_id)
    else:
        query = query.filter(Paper.journal.in_(allowed_journals))
    
    if status_filter:
        query = query.filter(Paper.status == status_filter)
    
    total = query.count()
    papers = query.order_by(desc(Paper.added_on)).offset(skip).limit(limit).all()
    
    papers_list = []
    for paper in papers:
        # Get journal name from journal table
        journal = None
        if paper.journal:
            journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
        
        # Get author info - added_by stores user ID
        author = None
        if paper.added_by and paper.added_by.isdigit():
            author = db.query(User).filter(User.id == int(paper.added_by)).first()
        
        # Get review status for the paper
        # Count total invitations sent (from ReviewerInvitation table)
        total_invitations = db.query(func.count(ReviewerInvitation.id)).filter(
            ReviewerInvitation.paper_id == paper.id
        ).scalar() or 0
        
        # Count accepted invitations
        accepted_invitations = db.query(func.count(ReviewerInvitation.id)).filter(
            ReviewerInvitation.paper_id == paper.id,
            ReviewerInvitation.status == "accepted"
        ).scalar() or 0
        
        # Also check OnlineReview for legacy assignments (before invitation system)
        legacy_assignments = db.query(func.count(OnlineReview.id)).filter(
            OnlineReview.paper_id == str(paper.id)
        ).scalar() or 0
        
        # Total assignments is invitations + any legacy assignments not linked to invitations
        total_assignments = max(total_invitations, legacy_assignments)
        
        completed_reviews = db.query(func.count(ReviewSubmission.id)).filter(
            ReviewSubmission.paper_id == paper.id,
            ReviewSubmission.status == "submitted"
        ).scalar() or 0
        
        # Determine review status based on invitations
        if total_invitations == 0 and legacy_assignments == 0:
            review_status = "not_assigned"
        elif accepted_invitations == 0 and legacy_assignments == 0:
            review_status = "invited"  # Invitations sent but none accepted yet
        elif completed_reviews == 0:
            review_status = "pending"  # Assigned but no reviews submitted
        elif completed_reviews < accepted_invitations or completed_reviews < legacy_assignments:
            review_status = "partial"  # Some reviews submitted
        else:
            review_status = "reviewed"  # All reviews complete
        
        # Get assigned reviewers from ReviewerInvitation table (primary)
        invitations = db.query(ReviewerInvitation).filter(
            ReviewerInvitation.paper_id == paper.id
        ).all()
        
        assigned_reviewers = []
        for invitation in invitations:
            reviewer = None
            if invitation.reviewer_id:
                reviewer = db.query(User).filter(User.id == invitation.reviewer_id).first()
            
            # Get review submission if exists
            review_submission = None
            if invitation.reviewer_id:
                review_submission = db.query(ReviewSubmission).filter(
                    ReviewSubmission.paper_id == paper.id,
                    ReviewSubmission.reviewer_id == str(invitation.reviewer_id)
                ).first()
            
            # Get OnlineReview assignment if exists
            online_review = None
            if invitation.reviewer_id:
                online_review = db.query(OnlineReview).filter(
                    OnlineReview.paper_id == str(paper.id),
                    OnlineReview.reviewer_id == str(invitation.reviewer_id)
                ).first()
            
            assigned_reviewers.append({
                "invitation_id": invitation.id,
                "assignment_id": online_review.id if online_review else None,
                "reviewer_id": invitation.reviewer_id,
                "reviewer_name": invitation.reviewer_name or (f"{reviewer.fname} {reviewer.lname or ''}".strip() if reviewer else "Unknown"),
                "reviewer_email": invitation.reviewer_email,
                "assigned_on": invitation.invited_on.isoformat() if invitation.invited_on else None,
                "due_date": invitation.token_expiry.isoformat() if invitation.token_expiry else None,
                "invitation_status": invitation.status,  # pending, accepted, declined, expired
                "review_status": online_review.review_status if online_review else ("invited" if invitation.status == "pending" else invitation.status),
                "has_submitted": review_submission.status == "submitted" if review_submission else False,
                "submitted_at": review_submission.submitted_at.isoformat() if review_submission and review_submission.submitted_at else None
            })
        
        # Also include legacy OnlineReview assignments not linked to invitations
        legacy_reviews = db.query(OnlineReview).filter(
            OnlineReview.paper_id == str(paper.id)
        ).all()
        
        # Add legacy assignments that don't have corresponding invitations
        existing_reviewer_ids = {inv.reviewer_id for inv in invitations if inv.reviewer_id}
        for assignment in legacy_reviews:
            if assignment.reviewer_id and int(assignment.reviewer_id) not in existing_reviewer_ids:
                reviewer = db.query(User).filter(User.id == int(assignment.reviewer_id)).first() if assignment.reviewer_id else None
                review_submission = db.query(ReviewSubmission).filter(
                    ReviewSubmission.assignment_id == assignment.id
                ).first()
                
                assigned_reviewers.append({
                    "invitation_id": None,
                    "assignment_id": assignment.id,
                    "reviewer_id": assignment.reviewer_id,
                    "reviewer_name": f"{reviewer.fname} {reviewer.lname or ''}".strip() if reviewer else "Unknown",
                    "reviewer_email": reviewer.email if reviewer else None,
                    "assigned_on": assignment.assigned_on.isoformat() if assignment.assigned_on else None,
                    "due_date": assignment.due_date.isoformat() if assignment.due_date else None,
                    "invitation_status": "accepted",  # Legacy assignments are considered accepted
                    "review_status": assignment.review_status,
                    "has_submitted": review_submission.status == "submitted" if review_submission else False,
                    "submitted_at": review_submission.submitted_at.isoformat() if review_submission and review_submission.submitted_at else None
                })
        
        papers_list.append({
            "id": paper.id,
            "paper_code": paper.paper_code,
            "title": paper.title,
            "abstract": paper.abstract,
            "keywords": paper.keyword,
            "author": f"{author.fname} {author.lname or ''}".strip() if author else (paper.author or "Unknown"),
            "author_email": author.email if author else None,
            "journal": journal.fld_journal_name if journal else "Unknown",
            "journal_id": paper.journal,
            "submitted_date": paper.added_on.isoformat() if paper.added_on else None,
            "status": paper.status,
            "file": paper.file,
            "review_status": review_status,
            "total_invitations": total_invitations,
            "accepted_invitations": accepted_invitations,
            "total_reviewers": len(assigned_reviewers),
            "completed_reviews": completed_reviews,
            "assigned_reviewers": assigned_reviewers,
            "version_number": paper.version_number,
            "revision_count": paper.revision_count,
            "research_area": paper.research_area
        })
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "papers": papers_list
    }


@router.get("/papers/{paper_id}")
@limiter.limit("100/minute")
async def get_paper_detail(
    request: Request,
    paper_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a single paper.
    
    Args:
        paper_id: Paper ID
        
    Returns:
        Complete paper details with reviews and assigned reviewers
    """
    if not check_role(current_user.get("role"), ["editor", "admin"]):
        raise HTTPException(status_code=403, detail="Editor or Admin access required")
    
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Check journal access for editors (admin has full access)
    if check_role(current_user.get("role"), "editor"):
        allowed_journals = get_editor_journal_ids(current_user.get("email"), db)
        # Strict mode: no journals = no access to any paper
        if not allowed_journals or paper.journal not in allowed_journals:
            raise HTTPException(
                status_code=403, 
                detail="You don't have access to papers from this journal"
            )
    
    # Get journal info
    journal = None
    if paper.journal:
        journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
    
    # Get author info
    author = None
    if paper.added_by and paper.added_by.isdigit():
        author = db.query(User).filter(User.id == int(paper.added_by)).first()
    
    # Get co-authors
    from app.db.models import PaperCoAuthor
    co_authors = db.query(PaperCoAuthor).filter(PaperCoAuthor.paper_id == paper_id).all()
    co_authors_list = []
    for ca in co_authors:
        co_authors_list.append({
            "id": ca.id,
            "salutation": ca.salutation,
            "first_name": ca.first_name,
            "middle_name": ca.middle_name,
            "last_name": ca.last_name,
            "email": ca.email
        })
    
    # Get review assignments
    assignments = db.query(OnlineReview).filter(
        OnlineReview.paper_id == str(paper.id)
    ).all()
    
    assigned_reviewers = []
    for assignment in assignments:
        reviewer = None
        if assignment.reviewer_id:
            reviewer = db.query(User).filter(User.id == assignment.reviewer_id).first()
        
        # Get review submission if exists
        review_submission = db.query(ReviewSubmission).filter(
            ReviewSubmission.assignment_id == assignment.id
        ).first()
        
        reviewer_info = {
            "assignment_id": assignment.id,
            "reviewer_id": assignment.reviewer_id,
            "reviewer_name": f"{reviewer.fname} {reviewer.lname or ''}".strip() if reviewer else "Unknown",
            "reviewer_email": reviewer.email if reviewer else None,
            "specialization": reviewer.specialization if reviewer else None,
            "affiliation": reviewer.affiliation if reviewer else None,
            "assigned_on": assignment.assigned_on.isoformat() if assignment.assigned_on else None,
            "due_date": assignment.due_date.isoformat() if assignment.due_date else None,
            "review_status": assignment.review_status,
            "has_submitted": False,
            "submitted_at": None,
            "review": None
        }
        
        if review_submission:
            reviewer_info["has_submitted"] = review_submission.status == "submitted"
            reviewer_info["submitted_at"] = review_submission.submitted_at.isoformat() if review_submission.submitted_at else None
            if review_submission.status == "submitted":
                reviewer_info["review"] = {
                    "id": review_submission.id,
                    "technical_quality": review_submission.technical_quality,
                    "clarity": review_submission.clarity,
                    "originality": review_submission.originality,
                    "significance": review_submission.significance,
                    "overall_rating": review_submission.overall_rating,
                    "author_comments": review_submission.author_comments,
                    "confidential_comments": review_submission.confidential_comments,
                    "recommendation": review_submission.recommendation,
                    "review_report_file": review_submission.review_report_file
                }
        
        assigned_reviewers.append(reviewer_info)
    
    # Calculate review stats
    total_assignments = len(assigned_reviewers)
    completed_reviews = sum(1 for r in assigned_reviewers if r["has_submitted"])
    
    # Determine review status
    if total_assignments == 0:
        review_status = "not_assigned"
    elif completed_reviews == 0:
        review_status = "pending"
    elif completed_reviews < total_assignments:
        review_status = "partial"
    else:
        review_status = "reviewed"
    
    return {
        "id": paper.id,
        "paper_code": paper.paper_code,
        "title": paper.title,
        "abstract": paper.abstract,
        "keywords": paper.keyword.split(",") if paper.keyword else [],
        "file": paper.file,
        "status": paper.status,
        "submitted_date": paper.added_on.isoformat() if paper.added_on else None,
        "author": {
            "id": author.id if author else None,
            "name": f"{author.fname} {author.lname or ''}".strip() if author else (paper.author or "Unknown"),
            "email": author.email if author else None,
            "affiliation": author.affiliation if author else None
        },
        "co_authors": co_authors_list,
        "journal": {
            "id": journal.fld_id if journal else None,
            "name": journal.fld_journal_name if journal else "Unknown"
        },
        "review_status": review_status,
        "total_reviewers": total_assignments,
        "completed_reviews": completed_reviews,
        "assigned_reviewers": assigned_reviewers,
        "version_number": paper.version_number,
        "revision_count": paper.revision_count,
        "revision_deadline": paper.revision_deadline.isoformat() if paper.revision_deadline else None,
        "revision_notes": paper.revision_notes,
        "revision_requested_date": paper.revision_requested_date.isoformat() if paper.revision_requested_date else None,
        "revision_type": paper.revision_type,
        "editor_comments": paper.editor_comments,
        "research_area": paper.research_area,
        "message_to_editor": paper.message_to_editor
    }


@router.post("/papers/{paper_id}/invite-reviewer")
@limiter.limit("100/minute")
async def invite_reviewer(
    request: Request,
    paper_id: int,
    reviewer_email: str = Query(..., description="Email of the reviewer to invite"),
    due_days: int = Query(14, ge=1, le=90, description="Days until review is due"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Invite a reviewer to review a paper by email.
    
    Args:
        paper_id: Paper ID
        reviewer_email: Email of reviewer to invite
        due_days: Number of days until review is due (1-90, default 14)
        
    Returns:
        Confirmation with invitation details
    """
    if not check_role(current_user.get("role"), ["editor", "admin"]):
        raise HTTPException(
            status_code=403, 
            detail="Editor or Admin access required. Only editors and admins can send reviewer invitations."
        )
    
    # Validate paper exists
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(
            status_code=404, 
            detail={
                "error": "Paper not found",
                "message": f"No paper found with ID {paper_id}",
                "paper_id": paper_id,
                "fix": "Verify the paper ID is correct and exists in the system"
            }
        )
    
    # Prevent editors from assigning reviewers to their own papers
    if paper.added_by == str(current_user.get("id")):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Conflict of interest",
                "message": "You cannot assign reviewers to papers you submitted",
                "paper_id": paper_id,
                "fix": "Ask another editor to handle reviewer assignments for this paper"
            }
        )
    
    # Check if reviewer exists in the system (for external reviewers, they may not exist yet)
    reviewer = db.query(User).filter(User.email == reviewer_email).first()
    is_external_reviewer = reviewer is None
    
    # For existing users, validate they have reviewer role
    if reviewer:
        has_reviewer_role = "reviewer" in (reviewer.role or "").lower()
        
        # Also check UserRole table for approved reviewer role
        if not has_reviewer_role:
            user_role_entry = db.query(UserRole).filter(
                UserRole.user_id == reviewer.id,
                UserRole.role == "reviewer",
                UserRole.status == "approved"
            ).first()
            has_reviewer_role = user_role_entry is not None
        
        if not has_reviewer_role:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid user role",
                    "message": f"User {reviewer_email} does not have an approved 'reviewer' role",
                    "reviewer_email": reviewer_email,
                    "reviewer_role": reviewer.role,
                    "fix": "Assign the 'reviewer' role to this user in the admin panel"
                }
            )
    
    # Check if already invited/assigned
    if reviewer:
        # For existing users, check OnlineReview table
        existing_review = db.query(OnlineReview).filter(
            OnlineReview.paper_id == str(paper_id),
            OnlineReview.reviewer_id == str(reviewer.id)
        ).first()
        
        if existing_review:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Already invited",
                    "message": f"Reviewer {reviewer_email} is already assigned to this paper",
                    "reviewer_email": reviewer_email,
                    "paper_id": paper_id,
                    "review_id": existing_review.id,
                    "fix": "Choose a different reviewer or remove the existing assignment"
                }
            )
    else:
        # For external reviewers, check ReviewerInvitation table by email
        existing_invitation = db.query(ReviewerInvitation).filter(
            ReviewerInvitation.paper_id == paper_id,
            ReviewerInvitation.reviewer_email == reviewer_email,
            ReviewerInvitation.status.in_(["pending", "accepted"])
        ).first()
        
        if existing_invitation:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Already invited",
                    "message": f"An invitation has already been sent to {reviewer_email} for this paper",
                    "reviewer_email": reviewer_email,
                    "paper_id": paper_id,
                    "invitation_id": existing_invitation.id,
                    "invitation_status": existing_invitation.status,
                    "fix": "Wait for the reviewer to respond or choose a different reviewer"
                }
            )
    
    # Prepare invitation data
    reviewer_name = f"{reviewer.fname} {reviewer.lname or ''}".strip() if reviewer else reviewer_email.split('@')[0].title()
    paper_title = paper.title or "Untitled Paper"
    paper_abstract = paper.abstract or "No abstract provided"
    
    # Get journal name from Journal table (paper.journal is an integer ID)
    journal_obj = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
    journal_name = journal_obj.fld_journal_name if journal_obj else "AACS Journals"
    
    # Calculate due date
    due_date = (datetime.utcnow() + timedelta(days=due_days)).strftime("%B %d, %Y")
    token_expiry = datetime.utcnow() + timedelta(days=due_days)
    
    # Generate unique invitation token
    invitation_token = secrets.token_urlsafe(32)
    
    # Create ReviewerInvitation record
    try:
        invitation = ReviewerInvitation(
            paper_id=paper_id,
            reviewer_id=reviewer.id if reviewer else None,  # None for external reviewers
            reviewer_email=reviewer_email,
            reviewer_name=reviewer_name,
            journal_id=paper.journal,
            invitation_token=invitation_token,
            token_expiry=token_expiry,
            status="pending",
            invited_on=datetime.utcnow(),
            invitation_message=f"You are invited to review the paper '{paper_title}' for {journal_name}",
            is_external=is_external_reviewer  # Track if external reviewer
        )
        db.add(invitation)
        db.commit()
        db.refresh(invitation)
        
        invitation_id = invitation.id
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create invitation: {str(e)}"
        )
    
    # Generate invitation link using configured frontend URL
    frontend_url = os.environ.get("FRONTEND_URL", "https://aacs-woad.vercel.app")
    invitation_link = f"{frontend_url}/invitations/{invitation_token}"
    
    # Send invitation email
    email_sent = send_reviewer_invitation(
        reviewer_email=reviewer_email,
        reviewer_name=reviewer_name,
        paper_title=paper_title,
        paper_abstract=paper_abstract,
        journal_name=journal_name,
        invitation_link=invitation_link,
        due_date=due_date
    )
    
    return {
        "message": "Reviewer invitation sent successfully" if email_sent else "Reviewer invitation prepared (email delivery pending)",
        "invitation_id": invitation_id,
        "paper_id": paper_id,
        "paper_title": paper_title,
        "reviewer_email": reviewer_email,
        "reviewer_name": reviewer_name,
        "due_days": due_days,
        "due_date": due_date,
        "status": "invitation_sent" if email_sent else "invitation_queued",
        "email_sent": email_sent,
        "is_external_reviewer": is_external_reviewer,
        "journal_name": journal_name
    }


@router.post("/papers/{paper_id}/assign-reviewer")
async def assign_reviewer(
    paper_id: int,
    reviewer_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Assign a reviewer to a paper.
    
    Args:
        paper_id: Paper ID
        reviewer_id: Reviewer user ID
        
    Returns:
        Confirmation with assignment details
    """
    if not check_role(current_user.get("role"), "editor"):
        raise HTTPException(status_code=403, detail="Editor access required")
    
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(
            status_code=404, 
            detail={
                "error": "Paper not found",
                "message": f"No paper found with ID {paper_id}",
                "paper_id": paper_id,
                "fix": "Verify the paper ID is correct"
            }
        )
    
    # Prevent editors from assigning reviewers to their own papers
    if paper.added_by == str(current_user.get("id")):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Conflict of interest",
                "message": "You cannot assign reviewers to papers you submitted",
                "paper_id": paper_id,
                "fix": "Ask another editor to handle reviewer assignments for this paper"
            }
        )
    
    reviewer = db.query(User).filter(User.id == reviewer_id).first()
    if not reviewer or "reviewer" not in (reviewer.role or "").lower():
        raise HTTPException(
            status_code=404, 
            detail={
                "error": "Reviewer not found",
                "message": f"No reviewer found with ID {reviewer_id}",
                "reviewer_id": reviewer_id,
                "fix": "Verify the reviewer ID exists and user has reviewer role"
            }
        )
    
    # Create review assignment
    new_review = OnlineReview(
        paper_id=paper_id,
        reviewer_id=str(reviewer_id)
    )
    
    db.add(new_review)
    paper.status = "under_review"
    db.commit()
    db.refresh(new_review)
    
    return {
        "message": "Reviewer assigned successfully",
        "review_id": new_review.id,
        "paper_id": paper_id,
        "reviewer_id": reviewer_id,
        "assigned_date": datetime.utcnow().isoformat()
    }


# Status to email type mapping
STATUS_EMAIL_TYPE_MAP = {
    "under_review": "under_review",
    "accepted": "accepted",
    "rejected": "rejected",
    "correction": "revision_requested",
    "published": "published"
}


async def send_status_email_background(
    db_session_factory,
    paper_id: int,
    paper_code: str,
    paper_title: str,
    journal_name: str,
    author_email: str,
    author_name: str,
    email_type: str,
    status_at_send: str,
    comments: str = None,
    deadline: str = None
):
    """Background task to send status update email"""
    from app.db.database import SessionLocal
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        db = SessionLocal()
        result = await create_and_send_correspondence(
            db=db,
            paper_id=paper_id,
            paper_code=paper_code,
            paper_title=paper_title,
            journal_name=journal_name,
            author_email=author_email,
            author_name=author_name,
            email_type=email_type,
            status_at_send=status_at_send,
            comments=comments,
            deadline=deadline
        )
        
        if result["success"]:
            logger.info(f"Status email sent for paper {paper_id}, type: {email_type}")
        else:
            logger.error(f"Failed to send status email for paper {paper_id}: {result['error_message']}")
    except Exception as e:
        logger.error(f"Error sending status email: {str(e)}")
    finally:
        db.close()


@router.post("/papers/{paper_id}/status")
async def update_paper_status(
    paper_id: int,
    status: str,
    comments: str = None,
    revision_deadline: str = None,
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update paper status (accept, reject, request revisions).
    Sends notification email to author asynchronously.
    
    Args:
        paper_id: Paper ID
        status: New status (accepted, rejected, under_review, pending, correction)
        comments: Optional editorial comments
        revision_deadline: Optional deadline for revisions (ISO format date)
        
    Returns:
        Updated paper object with email notification status
    """
    if not check_role(current_user.get("role"), "editor"):
        raise HTTPException(status_code=403, detail="Editor access required")
    
    allowed_statuses = ["accepted", "rejected", "under_review", "pending", "correction", "published"]
    if status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {allowed_statuses}")
    
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    old_status = paper.status
    paper.status = status
    
    # Set revision deadline if provided
    if revision_deadline and status == "correction":
        try:
            paper.revision_deadline = datetime.fromisoformat(revision_deadline)
            paper.revision_requested_date = datetime.utcnow()
            paper.revision_notes = comments
        except ValueError:
            pass  # Ignore invalid date format
    
    db.commit()
    db.refresh(paper)
    
    # Prepare email notification
    email_sent = False
    email_type = STATUS_EMAIL_TYPE_MAP.get(status)
    
    if email_type and background_tasks:
        # Get author info
        author = None
        if paper.added_by and paper.added_by.isdigit():
            author = db.query(User).filter(User.id == int(paper.added_by)).first()
        
        # Get journal info
        journal = None
        if paper.journal:
            journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
        
        if author and author.email:
            author_name = f"{author.fname or ''} {author.lname or ''}".strip() or "Author"
            journal_name = journal.fld_journal_name if journal else "Breakthrough Publishers India Journal"
            
            # Schedule background email task
            background_tasks.add_task(
                send_status_email_background,
                None,  # db_session_factory not used
                paper.id,
                paper.paper_code,
                paper.title,
                journal_name,
                author.email,
                author_name,
                email_type,
                status,
                comments,
                paper.revision_deadline.strftime('%B %d, %Y') if paper.revision_deadline else None
            )
            email_sent = True
    
    return {
        "id": paper.id,
        "title": paper.title,
        "status": paper.status,
        "previous_status": old_status,
        "updated_date": datetime.utcnow().isoformat(),
        "email_notification_queued": email_sent
    }


# ============================================================================
# EDITOR DECISION ENDPOINTS
# ============================================================================

@router.post("/papers/{paper_id}/decision")
@limiter.limit("50/minute")
async def make_paper_decision(
    request: Request,
    paper_id: int,
    decision: str = Body(..., embed=False),
    editor_comments: str = Body(..., embed=False),
    revision_type: str = Body(None, embed=False),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Make a decision on a paper (accept, request revisions, or reject).
    Sends notification email to author asynchronously.
    
    Args:
        paper_id: Paper ID
        decision: Decision type (accepted, correction, rejected)
        editor_comments: Editor's comments to author (required, 50-2000 chars)
        revision_type: For corrections - 'minor' or 'major' (optional)
        
    Returns:
        Decision result with paper details
    """
    if not check_role(current_user.get("role"), "editor"):
        raise HTTPException(status_code=403, detail="Editor access required")
    
    # Validate decision
    allowed_decisions = ["accepted", "correction", "rejected"]
    if decision not in allowed_decisions:
        raise HTTPException(status_code=400, detail=f"Invalid decision. Allowed: {allowed_decisions}")
    
    # Validate editor comments
    if not editor_comments or len(editor_comments.strip()) < 50:
        raise HTTPException(status_code=400, detail="Editor comments must be at least 50 characters")
    
    # Validate revision type for corrections
    if decision == "correction":
        if revision_type and revision_type not in ["minor", "major"]:
            raise HTTPException(status_code=400, detail="Invalid revision type. Allowed: minor, major")
    
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    old_status = paper.status
    paper.status = decision
    paper.editor_comments = editor_comments.strip()
    
    # Set revision fields if requesting corrections
    if decision == "correction":
        paper.revision_requested_date = datetime.utcnow()
        # Set default revision deadline (14 days for minor, 30 days for major)
        if revision_type == "major":
            paper.revision_deadline = datetime.utcnow() + timedelta(days=30)
        else:
            paper.revision_deadline = datetime.utcnow() + timedelta(days=14)
        paper.revision_notes = editor_comments.strip()
        paper.revision_type = revision_type or "minor"
    
    db.commit()
    db.refresh(paper)
    
    # Prepare email notification
    email_sent = False
    email_type = STATUS_EMAIL_TYPE_MAP.get(decision)
    
    if email_type and background_tasks:
        # Get author info
        author = None
        if paper.added_by and paper.added_by.isdigit():
            author = db.query(User).filter(User.id == int(paper.added_by)).first()
        
        # Get journal info
        journal = None
        if paper.journal:
            journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
        
        if author and author.email:
            author_name = f"{author.fname or ''} {author.lname or ''}".strip() or "Author"
            journal_name = journal.fld_journal_name if journal else "Breakthrough Publishers India Journal"
            
            # Schedule background email task
            background_tasks.add_task(
                send_status_email_background,
                None,
                paper.id,
                paper.paper_code,
                paper.title,
                journal_name,
                author.email,
                author_name,
                email_type,
                decision,
                editor_comments.strip(),
                paper.revision_deadline.strftime('%B %d, %Y') if paper.revision_deadline else None
            )
            email_sent = True
    
    return {
        "success": True,
        "paper_id": paper.id,
        "title": paper.title,
        "decision": decision,
        "previous_status": old_status,
        "editor_comments": paper.editor_comments,
        "revision_type": revision_type if decision == "correction" else None,
        "revision_deadline": paper.revision_deadline.isoformat() if paper.revision_deadline else None,
        "updated_at": datetime.utcnow().isoformat(),
        "email_notification_queued": email_sent
    }


@router.get("/papers/{paper_id}/decision")
@limiter.limit("100/minute")
async def get_paper_decision(
    request: Request,
    paper_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the current decision/status details for a paper.
    
    Returns:
        Paper status, revision details, and editor comments
    """
    if not check_role(current_user.get("role"), "editor"):
        raise HTTPException(status_code=403, detail="Editor access required")
    
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Get author info
    author = None
    if paper.added_by and paper.added_by.isdigit():
        author = db.query(User).filter(User.id == int(paper.added_by)).first()
    
    return {
        "paper_id": paper.id,
        "title": paper.title,
        "status": paper.status,
        "editor_comments": getattr(paper, 'editor_comments', None),
        "revision_type": getattr(paper, 'revision_type', None),
        "revision_notes": paper.revision_notes if hasattr(paper, 'revision_notes') else None,
        "revision_deadline": paper.revision_deadline.isoformat() if paper.revision_deadline else None,
        "revision_requested_date": paper.revision_requested_date.isoformat() if paper.revision_requested_date else None,
        "author": {
            "id": author.id if author else None,
            "name": f"{author.fname or ''} {author.lname or ''}".strip() if author else None,
            "email": author.email if author else None
        } if author else None
    }


@router.get("/papers/{paper_id}/reviews")
@limiter.limit("100/minute")
async def get_paper_reviews(
    request: Request,
    paper_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get paper details with all reviews for editor decision panel.
    
    Args:
        paper_id: Paper ID
        
    Returns:
        Paper details, reviews with reviewer info, and statistics
    """
    if not check_role(current_user.get("role"), "editor"):
        raise HTTPException(status_code=403, detail="Editor access required")
    
    # Get paper details
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Get author info
    author_name = paper.author or "Unknown"
    if paper.added_by and paper.added_by.isdigit():
        author_user = db.query(User).filter(User.id == int(paper.added_by)).first()
        if author_user:
            author_name = f"{author_user.fname or ''} {author_user.lname or ''}".strip() or author_user.email
    
    # Get review submissions with detailed information
    review_submissions = db.query(ReviewSubmission).filter(
        ReviewSubmission.paper_id == paper_id
    ).all()
    
    reviews_list = []
    total_rating = 0
    rating_count = 0
    accept_count = 0
    minor_count = 0
    major_count = 0
    reject_count = 0
    
    for review in review_submissions:
        # Get reviewer info
        reviewer = db.query(User).filter(User.id == review.reviewer_id).first()
        reviewer_name = "Anonymous Reviewer"
        reviewer_email = None
        if reviewer:
            reviewer_name = f"{reviewer.fname or ''} {reviewer.lname or ''}".strip() or reviewer.email
            reviewer_email = reviewer.email
        
        # Parse rating (use overall_rating field)
        rating = review.overall_rating if review.overall_rating else 0
        if rating:
            total_rating += rating
            rating_count += 1
        
        # Count recommendations
        recommendation = review.recommendation or ""
        if recommendation == "accept":
            accept_count += 1
        elif recommendation == "minor_revision":
            minor_count += 1
        elif recommendation == "major_revision":
            major_count += 1
        elif recommendation == "reject":
            reject_count += 1
        
        reviews_list.append({
            "review_id": review.id,
            "reviewer_id": review.reviewer_id,
            "reviewer_name": reviewer_name,
            "reviewer_email": reviewer_email,
            "rating": rating,
            "recommendation": recommendation,
            "author_comments": review.author_comments,
            "editor_comments": review.confidential_comments,
            "submitted_date": review.submitted_at.isoformat() if review.submitted_at else None
        })
    
    # Calculate statistics
    statistics = {
        "total_reviews": len(reviews_list),
        "average_rating": total_rating / rating_count if rating_count > 0 else 0,
        "accept_count": accept_count,
        "minor_revisions_count": minor_count,
        "major_revisions_count": major_count,
        "reject_count": reject_count
    }
    
    return {
        "paper_id": paper.id,
        "paper_name": paper.title,
        "paper_code": paper.paper_code,
        "author": author_name,
        "abstract": paper.abstract,
        "keywords": paper.keyword,
        "status": paper.status,
        "submitted_date": paper.added_on.isoformat() if paper.added_on else None,
        "reviews": reviews_list,
        "statistics": statistics
    }


@router.get("/reviewers")
@limiter.limit("100/minute")
async def list_available_reviewers(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List available reviewers for assignment.
    
    Args:
        skip: Number of records to skip
        limit: Number of records to return
        search: Search by name or email
        
    Returns:
        List of available reviewers
    """
    if not check_role(current_user.get("role"), ["editor", "admin"]):
        raise HTTPException(status_code=403, detail="Editor or Admin access required")
    
    # Check for users who have reviewer role either in:
    # 1. User.role column (legacy - contains "reviewer" anywhere in the string)
    # 2. UserRole table (new multi-role system with status="approved")
    has_reviewer_in_user_role = exists().where(
        and_(
            UserRole.user_id == User.id,
            UserRole.role == "reviewer",
            UserRole.status == "approved"
        )
    )
    
    query = db.query(User).filter(
        or_(
            User.role.ilike("%reviewer%"),
            has_reviewer_in_user_role
        )
    ).distinct()
    
    if search:
        query = query.filter(
            (User.email.ilike(f"%{search}%")) |
            (User.fname.ilike(f"%{search}%")) |
            (User.lname.ilike(f"%{search}%"))
        )
    
    total = query.count()
    reviewers = query.offset(skip).limit(limit).all()
    
    reviewers_list = []
    for reviewer in reviewers:
        reviewers_list.append({
            "id": reviewer.id,
            "name": f"{reviewer.fname} {reviewer.lname or ''}".strip(),
            "email": reviewer.email,
            "specialization": reviewer.specialization,
            "affiliation": reviewer.affiliation
        })
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "reviewers": reviewers_list
    }


@router.get("/pending-actions")
@limiter.limit("100/minute")
async def get_pending_actions(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get pending actions for editor dashboard.
    
    Returns:
        Summary of pending actions
    """
    if not check_role(current_user.get("role"), "editor"):
        raise HTTPException(status_code=403, detail="Editor access required")
    
    pending_assignments = db.query(func.count(Paper.id)).filter(
        Paper.status == "pending"
    ).scalar() or 0
    
    # Count assigned reviews (papers under review)
    overdue_reviews = db.query(func.count(OnlineReview.id)).scalar() or 0
    
    ready_for_publication = db.query(func.count(Paper.id)).filter(
        Paper.status == "accepted"
    ).scalar() or 0
    
    return {
        "pending_assignments": pending_assignments,
        "assigned_reviews": overdue_reviews,
        "ready_for_publication": ready_for_publication
    }


@router.get("/papers-pending-decision")
@limiter.limit("100/minute")
async def get_papers_pending_decision(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get papers that have completed reviews and are pending editor decision.
    
    Returns:
        List of papers with review status and summary statistics
    """
    if not check_role(current_user.get("role"), "editor"):
        raise HTTPException(status_code=403, detail="Editor access required")
    
    # Get editor's assigned journals (strict mode)
    allowed_journals = get_editor_journal_ids(current_user.get("email"), db)
    if not allowed_journals:
        return {
            "papers": [],
            "total": 0,
            "skip": skip,
            "limit": limit
        }
    
    # Get papers that are under review or awaiting decision (filtered by editor's journals)
    query = db.query(Paper).filter(
        Paper.status.in_(["under_review", "correction", "resubmitted"]),
        Paper.journal.in_(allowed_journals)
    )
    
    total = query.count()
    papers = query.offset(skip).limit(limit).all()
    
    papers_with_reviews = []
    for paper in papers:
        # Get author info - added_by stores user ID
        author = None
        if paper.added_by and paper.added_by.isdigit():
            author = db.query(User).filter(User.id == int(paper.added_by)).first()
        
        # Get journal name from journal table
        journal = None
        if paper.journal:
            journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
        
        papers_with_reviews.append({
            "id": paper.id,
            "title": paper.title,
            "author": f"{author.fname} {author.lname or ''}".strip() if author else (paper.author or "Unknown"),
            "journal": journal.fld_journal_name if journal else "Unknown",
            "status": paper.status,
            "submitted_date": paper.added_on.isoformat() if paper.added_on else None,
            "added_by": paper.added_by
        })
    
    return {
        "papers": papers_with_reviews,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.post("/papers/{paper_id}/publish", response_model=PublishPaperResponse)
@limiter.limit("20/minute")
async def publish_paper_with_doi(
    request: Request,
    paper_id: int,
    publish_data: PublishPaperRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Publish an accepted paper and register DOI with Crossref.
    
    This endpoint:
    1. Validates paper status is 'accepted'
    2. Generates a unique DOI following pattern: 10.58517/{JOURNAL}.{YEAR}.{VOL}{ISSUE}{NUM}
    3. Builds Crossref deposit XML
    4. Submits DOI registration to Crossref API
    5. Creates PaperPublished record with access_type='subscription'
    6. Updates Paper status to 'published'
    
    Args:
        paper_id: ID of the accepted paper to publish
        publish_data: Publishing metadata (volume, issue, pages, etc.)
    
    Returns:
        PublishPaperResponse with published paper and DOI details
    
    Raises:
        404: Paper not found
        400: Paper not in 'accepted' status
        403: Editor access required
    """
    if not check_role(current_user.get("role"), ["editor", "admin"]):
        raise HTTPException(status_code=403, detail="Editor or Admin access required")
    
    # Get the paper
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Check journal access for editors (admin has full access)
    if check_role(current_user.get("role"), "editor"):
        allowed_journals = get_editor_journal_ids(current_user.get("email"), db)
        if allowed_journals and paper.journal and int(paper.journal) not in allowed_journals:
            raise HTTPException(
                status_code=403, 
                detail="You don't have access to publish papers from this journal"
            )
    
    # Validate paper status
    if paper.status != "accepted":
        raise HTTPException(
            status_code=400, 
            detail=f"Only accepted papers can be published. Current status: {paper.status}"
        )
    
    # Check if paper is already published
    existing_published = db.query(PaperPublished).filter(
        PaperPublished.paper_submission_id == paper_id
    ).first()
    if existing_published:
        raise HTTPException(
            status_code=400,
            detail=f"Paper already published with ID {existing_published.id}"
        )
    
    # Get journal info (paper.journal is INT)
    journal = None
    if paper.journal:
        journal = db.query(Journal).filter(
            Journal.fld_id == paper.journal
        ).first()
    
    if not journal:
        raise HTTPException(status_code=400, detail="Journal not found for this paper")
    
    # Get author info
    author_user = None
    if paper.added_by and paper.added_by.isdigit():
        author_user = db.query(User).filter(User.id == int(paper.added_by)).first()
    
    # Determine publication date
    pub_date = publish_data.publication_date or datetime.utcnow().date()
    pub_datetime = datetime.combine(pub_date, datetime.min.time())
    
    # Count existing papers in this volume/issue for paper numbering
    existing_count = db.query(func.count(PaperPublished.id)).filter(
        PaperPublished.journal_id == journal.fld_id,
        PaperPublished.volume == publish_data.volume,
        PaperPublished.issue == publish_data.issue
    ).scalar() or 0
    paper_num = existing_count + 1
    
    # Generate DOI
    doi = generate_doi(
        journal_short=journal.short_form,
        year=pub_date.year,
        volume=publish_data.volume,
        issue=publish_data.issue,
        paper_num=paper_num
    )
    
    # Prepare author list for Crossref
    authors_list = []
    if publish_data.authors:
        authors_list = [
            {
                "name": a.name,
                "email": a.email,
                "affiliation": a.affiliation
            } for a in publish_data.authors
        ]
    else:
        # Use paper author info
        author_name = paper.author or (f"{author_user.fname} {author_user.lname or ''}".strip() if author_user else "Unknown")
        authors_list = [{
            "name": author_name,
            "email": author_user.email if author_user else None,
            "affiliation": author_user.affiliation if author_user else None
        }]
    
    # Author string for display
    author_string = ", ".join([a["name"] for a in authors_list])
    
    # Primary author email and affiliation
    primary_email = authors_list[0].get("email") if authors_list else (author_user.email if author_user else None)
    primary_affiliation = authors_list[0].get("affiliation") if authors_list else (author_user.affiliation if author_user else None)
    
    # Prepare paper URL
    paper_url = publish_data.paper_url or f"https://aacsjournals.com/article/{doi}"
    
    # Register DOI with Crossref
    crossref_service = CrossrefService()
    
    paper_data = {
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": authors_list,
        "publication_date": pub_datetime,
        "pages": publish_data.pages,
        "url": paper_url,
        "paper_num": paper_num
    }
    
    journal_data = {
        "name": journal.fld_journal_name,
        "short_form": journal.short_form,
        "issn_online": journal.issn_ol,
        "issn_print": journal.issn_prt,
        "volume": publish_data.volume,
        "issue": publish_data.issue
    }
    
    doi_result = await crossref_service.register_doi(paper_data, journal_data, doi)
    
    # Determine DOI status
    doi_status = "registered" if doi_result.success else "failed"
    if doi_result.status == DOIStatus.PENDING:
        doi_status = "pending"
    
    # Create PaperPublished record
    published_paper = PaperPublished(
        title=paper.title,
        abstract=paper.abstract,
        p_reference=publish_data.references or "",  # Default to empty string if None
        author=author_string,
        journal=journal.fld_journal_name,
        journal_id=journal.fld_id,
        volume=publish_data.volume,
        issue=publish_data.issue,
        date=pub_datetime,
        pages=publish_data.pages,
        keyword=paper.keyword,
        language=publish_data.language,
        paper=paper.file,
        access_type="subscription",  # Default to subscription
        email=primary_email,
        affiliation=primary_affiliation,
        doi=doi,
        doi_status=doi_status,
        doi_registered_at=datetime.utcnow() if doi_result.success else None,
        crossref_batch_id=doi_result.batch_id,
        paper_submission_id=paper.id
    )
    
    db.add(published_paper)
    
    # Update paper status
    paper.status = "published"
    
    db.commit()
    db.refresh(published_paper)
    
    # Build response
    doi_response = DOIResponse(
        doi=doi,
        doi_url=f"https://doi.org/{doi}",
        status=doi_status,
        batch_id=doi_result.batch_id,
        registered_at=datetime.utcnow() if doi_result.success else None,
        message=doi_result.message
    )
    
    published_response = PublishedPaperResponse(
        id=published_paper.id,
        title=published_paper.title,
        abstract=published_paper.abstract,
        author=published_paper.author,
        journal=published_paper.journal,
        journal_id=published_paper.journal_id,
        volume=published_paper.volume,
        issue=published_paper.issue,
        pages=published_paper.pages,
        date=published_paper.date,
        keyword=published_paper.keyword,
        language=published_paper.language,
        paper=published_paper.paper,
        access_type=published_paper.access_type,
        doi=published_paper.doi,
        doi_status=published_paper.doi_status,
        doi_registered_at=published_paper.doi_registered_at,
        email=published_paper.email,
        affiliation=published_paper.affiliation
    )
    
    return PublishPaperResponse(
        success=True,
        message=f"Paper published successfully. DOI: {doi}. Crossref status: {doi_result.message}",
        published_paper=published_response,
        doi_result=doi_response
    )


# Published papers directory
PUBLISHED_PAPERS_DIR = Path(__file__).parent.parent.parent.parent / "uploads" / "published"


async def save_published_paper_file(file: UploadFile, paper_id: int, journal_id: int) -> str:
    """Save the final published paper file"""
    # Ensure directory exists
    PUBLISHED_PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create journal-specific subdirectory
    journal_dir = PUBLISHED_PAPERS_DIR / str(journal_id)
    journal_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    file_ext = Path(file.filename).suffix.lower()
    filename = f"paper_{paper_id}_{timestamp}{file_ext}"
    
    # Save file
    file_path = journal_dir / filename
    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)
    
    # Return relative path for database
    return f"published/{journal_id}/{filename}"


@router.post("/papers/{paper_id}/publish-with-file")
@limiter.limit("20/minute")
async def publish_paper_with_file(
    request: Request,
    paper_id: int,
    final_paper: UploadFile = File(..., description="Final paper PDF for publishing"),
    volume: int = Form(...),
    issue: int = Form(...),
    page_start: int = Form(None),
    page_end: int = Form(None),
    doi_suffix: str = Form(None),
    publication_date: str = Form(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Publish an accepted paper with editor-uploaded final paper file.
    
    This endpoint:
    1. Validates paper status is 'accepted'
    2. Saves the editor-uploaded final paper file
    3. Extracts co-author information from original submission
    4. Generates and registers DOI with Crossref
    5. Creates PaperPublished record
    6. Updates Paper status to 'published'
    """
    if not check_role(current_user.get("role"), ["editor", "admin"]):
        raise HTTPException(status_code=403, detail="Editor or Admin access required")
    
    # Validate file type
    if final_paper.content_type not in ["application/pdf"]:
        raise HTTPException(status_code=400, detail="Only PDF files are allowed for publishing")
    
    # Get the paper
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Check journal access for editors
    if check_role(current_user.get("role"), "editor"):
        allowed_journals = get_editor_journal_ids(current_user.get("email"), db)
        if allowed_journals and paper.journal and int(paper.journal) not in allowed_journals:
            raise HTTPException(
                status_code=403, 
                detail="You don't have access to publish papers from this journal"
            )
    
    # Validate paper status
    if paper.status != "accepted":
        raise HTTPException(
            status_code=400, 
            detail=f"Only accepted papers can be published. Current status: {paper.status}"
        )
    
    # Check if paper is already published
    existing_published = db.query(PaperPublished).filter(
        PaperPublished.paper_submission_id == paper_id
    ).first()
    if existing_published:
        raise HTTPException(
            status_code=400,
            detail=f"Paper already published with ID {existing_published.id}"
        )
    
    # Get journal info
    journal = None
    if paper.journal:
        journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
    if not journal:
        raise HTTPException(status_code=400, detail="Journal not found for this paper")
    
    # Get author info
    author_user = None
    if paper.added_by and paper.added_by.isdigit():
        author_user = db.query(User).filter(User.id == int(paper.added_by)).first()
    
    # Get co-authors from original paper
    co_authors = db.query(PaperCoAuthor).filter(
        PaperCoAuthor.paper_id == paper_id
    ).order_by(PaperCoAuthor.author_order).all()
    
    # Build structured author info with affiliations
    authors_info = []
    
    # Primary author first
    primary_name = paper.author or (f"{author_user.fname} {author_user.lname or ''}".strip() if author_user else "Unknown")
    primary_affiliation = author_user.affiliation if author_user else None
    authors_info.append({
        "name": primary_name,
        "affiliation": primary_affiliation,
        "email": author_user.email if author_user else None,
        "is_primary": True,
        "is_corresponding": True
    })
    
    # Add co-authors
    for ca in co_authors:
        full_name = f"{ca.salutation or ''} {ca.first_name} {ca.middle_name or ''} {ca.last_name}".strip()
        full_name = " ".join(full_name.split())  # Normalize whitespace
        authors_info.append({
            "name": full_name,
            "affiliation": ca.organisation,
            "email": ca.email,
            "is_primary": False,
            "is_corresponding": ca.is_corresponding
        })
    
    # Author string for display (all authors comma-separated)
    author_string = ", ".join([a["name"] for a in authors_info])
    
    # Primary author info
    primary_email = authors_info[0].get("email") if authors_info else None
    primary_affiliation = authors_info[0].get("affiliation") if authors_info else None
    
    # Store co-authors JSON
    co_authors_json_str = json.dumps(authors_info)
    
    # Determine publication date
    pub_date = None
    if publication_date:
        try:
            pub_date = datetime.strptime(publication_date, "%Y-%m-%d").date()
        except:
            pub_date = datetime.utcnow().date()
    else:
        pub_date = datetime.utcnow().date()
    pub_datetime = datetime.combine(pub_date, datetime.min.time())
    
    # Calculate pages string
    pages = None
    if page_start and page_end:
        pages = f"{page_start}-{page_end}"
    elif page_start:
        pages = str(page_start)
    else:
        pages = "1"
    
    # Save the uploaded file
    try:
        file_path = await save_published_paper_file(final_paper, paper_id, journal.fld_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Count existing papers in this volume/issue for paper numbering
    existing_count = db.query(func.count(PaperPublished.id)).filter(
        PaperPublished.journal_id == journal.fld_id,
        PaperPublished.volume == str(volume),
        PaperPublished.issue == str(issue)
    ).scalar() or 0
    paper_num = existing_count + 1
    
    # Generate DOI
    doi = generate_doi(
        journal_short=journal.short_form,
        year=pub_date.year,
        volume=str(volume),
        issue=str(issue),
        paper_num=paper_num
    )
    
    # Prepare data for Crossref
    authors_list = [{"name": a["name"], "email": a.get("email"), "affiliation": a.get("affiliation")} for a in authors_info]
    paper_url = f"https://aacsjournals.com/article/{doi}"
    
    paper_data = {
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": authors_list,
        "publication_date": pub_datetime,
        "pages": pages,
        "url": paper_url,
        "paper_num": paper_num
    }
    
    journal_data = {
        "name": journal.fld_journal_name,
        "short_form": journal.short_form,
        "issn_online": journal.issn_ol,
        "issn_print": journal.issn_prt,
        "volume": str(volume),
        "issue": str(issue)
    }
    
    # Register DOI with Crossref
    crossref_service = CrossrefService()
    doi_result = await crossref_service.register_doi(paper_data, journal_data, doi)
    
    # Determine DOI status
    doi_status = "registered" if doi_result.success else "failed"
    if doi_result.status == DOIStatus.PENDING:
        doi_status = "pending"
    
    # Create PaperPublished record
    published_paper = PaperPublished(
        title=paper.title,
        abstract=paper.abstract,
        p_reference=paper.keyword,  # Using references from original paper if needed
        author=author_string,
        journal=journal.fld_journal_name,
        journal_id=journal.fld_id,
        volume=str(volume),
        issue=str(issue),
        date=pub_datetime,
        pages=pages,
        keyword=paper.keyword,
        language="en",
        paper=file_path,  # Use the uploaded file path
        access_type="subscription",
        email=primary_email,
        affiliation=primary_affiliation,
        co_authors_json=co_authors_json_str,
        doi=doi,
        doi_status=doi_status,
        doi_registered_at=datetime.utcnow() if doi_result.success else None,
        crossref_batch_id=doi_result.batch_id,
        paper_submission_id=paper.id
    )
    
    db.add(published_paper)
    
    # Update paper status
    paper.status = "published"
    
    db.commit()
    db.refresh(published_paper)
    
    return {
        "success": True,
        "message": f"Paper published successfully with DOI: {doi}",
        "published_paper": {
            "id": published_paper.id,
            "title": published_paper.title,
            "author": published_paper.author,
            "journal": published_paper.journal,
            "volume": published_paper.volume,
            "issue": published_paper.issue,
            "doi": published_paper.doi,
            "doi_status": published_paper.doi_status,
            "paper_file": published_paper.paper,
            "co_authors": authors_info
        }
    }


@router.get("/papers/{paper_id}/doi-status")
@limiter.limit("60/minute")
async def check_doi_status(
    request: Request,
    paper_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check the DOI registration status for a published paper.
    
    Args:
        paper_id: ID of the paper submission
    
    Returns:
        DOI status information from Crossref
    """
    if not check_role(current_user.get("role"), ["editor", "admin"]):
        raise HTTPException(status_code=403, detail="Editor or Admin access required")
    
    # Find published paper
    published = db.query(PaperPublished).filter(
        PaperPublished.paper_submission_id == paper_id
    ).first()
    
    if not published:
        raise HTTPException(status_code=404, detail="Published paper not found")
    
    if not published.crossref_batch_id:
        return {
            "paper_id": paper_id,
            "published_id": published.id,
            "doi": published.doi,
            "doi_status": published.doi_status,
            "message": "No Crossref batch ID found - DOI may not have been submitted"
        }
    
    # Check status with Crossref
    crossref_service = CrossrefService()
    status_result = await crossref_service.check_deposit_status(published.crossref_batch_id)
    
    return {
        "paper_id": paper_id,
        "published_id": published.id,
        "doi": published.doi,
        "doi_url": f"https://doi.org/{published.doi}" if published.doi else None,
        "doi_status": published.doi_status,
        "batch_id": published.crossref_batch_id,
        "registered_at": published.doi_registered_at.isoformat() if published.doi_registered_at else None,
        "crossref_check": status_result
    }


@router.get("/accepted-papers")
@limiter.limit("100/minute")
async def get_accepted_papers(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    journal_id: int = Query(None, description="Filter by specific journal"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all accepted papers ready for publishing.
    Papers are filtered to only show those from journals the editor has access to.
    
    Returns papers with status='accepted' that haven't been published yet.
    """
    if not check_role(current_user.get("role"), ["editor", "admin"]):
        raise HTTPException(status_code=403, detail="Editor or Admin access required")
    
    # Get editor's assigned journals (admin has full access)
    allowed_journals = []
    if check_role(current_user.get("role"), "editor"):
        allowed_journals = get_editor_journal_ids(current_user.get("email"), db)
        
        # If specific journal requested, verify editor has access
        if journal_id and allowed_journals and journal_id not in allowed_journals:
            raise HTTPException(
                status_code=403, 
                detail=f"You don't have access to journal {journal_id}"
            )
    
    # Get accepted papers
    query = db.query(Paper).filter(Paper.status == "accepted")
    
    # Filter by editor's allowed journals (journal is now INT)
    if allowed_journals:
        if journal_id:
            query = query.filter(Paper.journal == journal_id)
        else:
            query = query.filter(Paper.journal.in_(allowed_journals))
    elif journal_id:
        # Admin or no restrictions - filter by requested journal
        query = query.filter(Paper.journal == journal_id)
    
    total = query.count()
    papers = query.order_by(desc(Paper.added_on)).offset(skip).limit(limit).all()
    
    papers_list = []
    for paper in papers:
        # Check if already published
        existing_published = db.query(PaperPublished).filter(
            PaperPublished.paper_submission_id == paper.id
        ).first()
        
        # Get journal info (paper.journal is INT)
        journal = None
        if paper.journal:
            journal = db.query(Journal).filter(
                Journal.fld_id == paper.journal
            ).first()
        
        # Get author info
        author = None
        if paper.added_by and paper.added_by.isdigit():
            author = db.query(User).filter(User.id == int(paper.added_by)).first()
        
        papers_list.append({
            "id": paper.id,
            "paper_code": paper.paper_code,
            "title": paper.title,
            "abstract": paper.abstract[:300] + "..." if len(paper.abstract) > 300 else paper.abstract,
            "keywords": paper.keyword,
            "author": f"{author.fname} {author.lname or ''}".strip() if author else (paper.author or "Unknown"),
            "author_email": author.email if author else None,
            "journal": journal.fld_journal_name if journal else "Unknown",
            "journal_id": paper.journal,
            "journal_short": journal.short_form if journal else None,
            "submitted_date": paper.added_on.isoformat() if paper.added_on else None,
            "status": paper.status,
            "file": paper.file,
            "already_published": existing_published is not None,
            "published_id": existing_published.id if existing_published else None,
            "published_doi": existing_published.doi if existing_published else None
        })
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "papers": papers_list
    }


@router.get("/ready-to-publish")
@limiter.limit("100/minute")
async def get_ready_to_publish(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    journal_id: int = Query(None, description="Filter by specific journal"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Alias for get_accepted_papers - returns papers ready for publishing.
    """
    return await get_accepted_papers(
        request=request,
        skip=skip,
        limit=limit,
        journal_id=journal_id,
        current_user=current_user,
        db=db
    )


# ============================================================================
# EDITOR FILE VIEW ENDPOINTS
# ============================================================================

@router.get("/papers/{paper_id}/view-title-page")
async def view_paper_title_page(
    paper_id: int,
    current_user: dict = Depends(get_current_user_from_token_or_query),
    db: Session = Depends(get_db)
):
    """
    View the title page file in browser.
    
    Args:
        paper_id: Paper ID
        
    Returns:
        Title page file for inline viewing
    """
    from fastapi.responses import FileResponse
    from app.utils.file_handler import get_file_full_path
    
    user_role = current_user.get("role", "").lower()
    if not check_role(user_role, ["editor", "admin"]):
        raise HTTPException(status_code=403, detail="Editor or Admin access required")
    
    # Verify editor has access to this paper's journal (admins have full access)
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Admins can access all papers, editors need journal access
    if user_role != "admin":
        editor_journal_ids = get_editor_journal_ids(current_user.get("email"), db)
        if paper.journal not in editor_journal_ids:
            raise HTTPException(status_code=403, detail="You don't have access to this paper's journal")
    
    # Use title_page if available, fall back to file
    file_path = paper.title_page or paper.file
    
    if not file_path:
        raise HTTPException(status_code=404, detail="Title page file not found")
    
    # Get full file path from relative path stored in DB
    filepath = get_file_full_path(file_path)
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Title page file not found on server")
    
    filename = filepath.name
    
    # Determine correct media type based on file extension
    ext = filepath.suffix.lower()
    media_types = {
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    }
    media_type = media_types.get(ext, 'application/octet-stream')
    
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type=media_type,
        headers={"Content-Disposition": f"inline; filename=\"{filename}\""}
    )


@router.get("/papers/{paper_id}/view-blinded-manuscript")
async def view_paper_blinded_manuscript(
    paper_id: int,
    current_user: dict = Depends(get_current_user_from_token_or_query),
    db: Session = Depends(get_db)
):
    """
    View the blinded manuscript file in browser.
    
    Args:
        paper_id: Paper ID
        
    Returns:
        Blinded manuscript file for inline viewing
    """
    from fastapi.responses import FileResponse
    from app.utils.file_handler import get_file_full_path
    
    user_role = current_user.get("role", "").lower()
    if not check_role(user_role, ["editor", "admin"]):
        raise HTTPException(status_code=403, detail="Editor or Admin access required")
    
    # Verify editor has access to this paper's journal (admins have full access)
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Admins can access all papers, editors need journal access
    if user_role != "admin":
        editor_journal_ids = get_editor_journal_ids(current_user.get("email"), db)
        if paper.journal not in editor_journal_ids:
            raise HTTPException(status_code=403, detail="You don't have access to this paper's journal")
    
    # Use blinded_manuscript if available, fall back to file
    file_path = paper.blinded_manuscript or paper.file
    
    if not file_path:
        raise HTTPException(status_code=404, detail="Blinded manuscript file not found")
    
    # Get full file path from relative path stored in DB
    filepath = get_file_full_path(file_path)
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Blinded manuscript file not found on server")
    
    filename = filepath.name
    
    # Determine correct media type based on file extension
    ext = filepath.suffix.lower()
    media_types = {
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    }
    media_type = media_types.get(ext, 'application/octet-stream')
    
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type=media_type,
        headers={"Content-Disposition": f"inline; filename=\"{filename}\""}
    )


@router.get("/papers/{paper_id}/view-track-changes")
async def view_paper_track_changes(
    paper_id: int,
    current_user: dict = Depends(get_current_user_from_token_or_query),
    db: Session = Depends(get_db)
):
    """
    View the revised manuscript with track changes in browser.
    """
    from fastapi.responses import FileResponse
    from app.utils.file_handler import get_file_full_path
    
    user_role = current_user.get("role", "").lower()
    if not check_role(user_role, ["editor", "admin"]):
        raise HTTPException(status_code=403, detail="Editor or Admin access required")
    
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Admins can access all papers, editors need journal access
    if user_role != "admin":
        editor_journal_ids = get_editor_journal_ids(current_user.get("email"), db)
        if paper.journal not in editor_journal_ids:
            raise HTTPException(status_code=403, detail="You don't have access to this paper's journal")
    
    file_path = paper.revised_track_changes
    if not file_path:
        raise HTTPException(status_code=404, detail="Track changes file not found - paper may not have been revised yet")
    
    filepath = get_file_full_path(file_path)
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Track changes file not found on server")
    
    filename = filepath.name
    ext = filepath.suffix.lower()
    media_types = {'.pdf': 'application/pdf', '.doc': 'application/msword', '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
    media_type = media_types.get(ext, 'application/octet-stream')
    
    return FileResponse(path=str(filepath), filename=filename, media_type=media_type, headers={"Content-Disposition": f"inline; filename=\"{filename}\""})


@router.get("/papers/{paper_id}/view-clean-revision")
async def view_paper_clean_revision(
    paper_id: int,
    current_user: dict = Depends(get_current_user_from_token_or_query),
    db: Session = Depends(get_db)
):
    """
    View the clean revised manuscript in browser.
    """
    from fastapi.responses import FileResponse
    from app.utils.file_handler import get_file_full_path
    
    user_role = current_user.get("role", "").lower()
    if not check_role(user_role, ["editor", "admin"]):
        raise HTTPException(status_code=403, detail="Editor or Admin access required")
    
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Admins can access all papers, editors need journal access
    if user_role != "admin":
        editor_journal_ids = get_editor_journal_ids(current_user.get("email"), db)
        if paper.journal not in editor_journal_ids:
            raise HTTPException(status_code=403, detail="You don't have access to this paper's journal")
    
    file_path = paper.revised_clean
    if not file_path:
        raise HTTPException(status_code=404, detail="Clean revision file not found - paper may not have been revised yet")
    
    filepath = get_file_full_path(file_path)
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Clean revision file not found on server")
    
    filename = filepath.name
    ext = filepath.suffix.lower()
    media_types = {'.pdf': 'application/pdf', '.doc': 'application/msword', '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
    media_type = media_types.get(ext, 'application/octet-stream')
    
    return FileResponse(path=str(filepath), filename=filename, media_type=media_type, headers={"Content-Disposition": f"inline; filename=\"{filename}\""})


@router.get("/papers/{paper_id}/view-response-to-reviewer")
async def view_paper_response_to_reviewer(
    paper_id: int,
    current_user: dict = Depends(get_current_user_from_token_or_query),
    db: Session = Depends(get_db)
):
    """
    View the response to reviewer comments file in browser.
    """
    from fastapi.responses import FileResponse
    from app.utils.file_handler import get_file_full_path
    
    user_role = current_user.get("role", "").lower()
    if not check_role(user_role, ["editor", "admin"]):
        raise HTTPException(status_code=403, detail="Editor or Admin access required")
    
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Admins can access all papers, editors need journal access
    if user_role != "admin":
        editor_journal_ids = get_editor_journal_ids(current_user.get("email"), db)
        if paper.journal not in editor_journal_ids:
            raise HTTPException(status_code=403, detail="You don't have access to this paper's journal")
    
    file_path = paper.response_to_reviewer
    if not file_path:
        raise HTTPException(status_code=404, detail="Response to reviewer file not found - paper may not have been revised yet")
    
    filepath = get_file_full_path(file_path)
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Response to reviewer file not found on server")
    
    filename = filepath.name
    ext = filepath.suffix.lower()
    media_types = {'.pdf': 'application/pdf', '.doc': 'application/msword', '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
    media_type = media_types.get(ext, 'application/octet-stream')
    
    return FileResponse(path=str(filepath), filename=filename, media_type=media_type, headers={"Content-Disposition": f"inline; filename=\"{filename}\""})


# ============================================================================
# PUBLIC INVITATION ENDPOINTS (No Authentication Required)
# ============================================================================

@router.get("/invitations/status/{token}")
async def get_invitation_status(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Get invitation status by token (public endpoint, no auth required).
    Used by external reviewers to view invitation details before accepting.
    
    Args:
        token: Invitation token from email link
        
    Returns:
        Invitation details including paper title, journal, due date
    """
    invitation = db.query(ReviewerInvitation).filter(
        ReviewerInvitation.invitation_token == token
    ).first()
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found. The token may be invalid.")
    
    # Check if expired
    is_expired = invitation.token_expiry < datetime.utcnow() if invitation.token_expiry else False
    
    # Get paper details
    paper = db.query(Paper).filter(Paper.id == invitation.paper_id).first()
    paper_title = paper.title if paper else "Unknown Paper"
    paper_abstract = paper.abstract[:500] + "..." if paper and paper.abstract and len(paper.abstract) > 500 else (paper.abstract if paper else "")
    
    # Get journal name
    journal = db.query(Journal).filter(Journal.fld_id == invitation.journal_id).first() if invitation.journal_id else None
    journal_name = journal.fld_journal_name if journal else "AACS Journals"
    
    return {
        "id": invitation.id,
        "paper_id": invitation.paper_id,
        "paper_title": paper_title,
        "paper_abstract": paper_abstract,
        "journal_name": journal_name,
        "reviewer_email": invitation.reviewer_email,
        "reviewer_name": invitation.reviewer_name,
        "status": invitation.status,
        "invited_on": invitation.invited_on.isoformat() if invitation.invited_on else None,
        "token_expiry": invitation.token_expiry.isoformat() if invitation.token_expiry else None,
        "is_expired": is_expired,
        "is_external": invitation.is_external if hasattr(invitation, 'is_external') else False,
        "invitation_message": invitation.invitation_message
    }


@router.post("/invitations/{token}/accept")
async def accept_invitation_by_token(
    token: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Accept an invitation by token (public endpoint).
    For existing users: Creates the review assignment.
    For external reviewers: Requires them to register first.
    
    Args:
        token: Invitation token from email link
        
    Returns:
        Acceptance confirmation with next steps
    """
    invitation = db.query(ReviewerInvitation).filter(
        ReviewerInvitation.invitation_token == token
    ).first()
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found. The token may be invalid.")
    
    # Check if already processed
    if invitation.status != "pending":
        raise HTTPException(status_code=400, detail=f"Invitation has already been {invitation.status}")
    
    # Check if expired
    if invitation.token_expiry and invitation.token_expiry < datetime.utcnow():
        invitation.status = "expired"
        db.commit()
        raise HTTPException(status_code=410, detail="Invitation has expired. Please contact the editor for a new invitation.")
    
    # Check if reviewer exists in the system
    reviewer = db.query(User).filter(User.email == invitation.reviewer_email).first()
    
    if not reviewer:
        # External reviewer - they need to register first
        return {
            "status": "registration_required",
            "message": "Please create an account to accept this invitation",
            "invitation_id": invitation.id,
            "reviewer_email": invitation.reviewer_email,
            "requires_registration": True
        }
    
    # Check if already assigned
    existing_review = db.query(OnlineReview).filter(
        OnlineReview.paper_id == invitation.paper_id,
        OnlineReview.reviewer_id == str(reviewer.id)
    ).first()
    
    if existing_review:
        raise HTTPException(status_code=409, detail="You are already assigned as a reviewer for this paper.")
    
    # Accept the invitation
    invitation.status = "accepted"
    invitation.accepted_on = datetime.utcnow()
    invitation.reviewer_id = reviewer.id
    
    # Create the review assignment
    from datetime import date
    online_review = OnlineReview(
        paper_id=invitation.paper_id,
        reviewer_id=str(reviewer.id),
        assigned_on=date.today()
    )
    db.add(online_review)
    db.commit()
    db.refresh(online_review)
    
    return {
        "status": "accepted",
        "message": "You have been assigned as a reviewer for this paper",
        "invitation_id": invitation.id,
        "paper_id": invitation.paper_id,
        "review_id": online_review.id,
        "accepted_on": invitation.accepted_on.isoformat() if invitation.accepted_on else None,
        "requires_registration": False
    }


@router.post("/invitations/{token}/decline")
async def decline_invitation_by_token(
    token: str,
    reason: str = Query("", description="Optional reason for declining"),
    db: Session = Depends(get_db)
):
    """
    Decline an invitation by token (public endpoint).
    
    Args:
        token: Invitation token from email link
        reason: Optional reason for declining
        
    Returns:
        Confirmation of decline
    """
    invitation = db.query(ReviewerInvitation).filter(
        ReviewerInvitation.invitation_token == token
    ).first()
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found. The token may be invalid.")
    
    # Check if already processed
    if invitation.status != "pending":
        raise HTTPException(status_code=400, detail=f"Invitation has already been {invitation.status}")
    
    # Decline the invitation
    invitation.status = "declined"
    invitation.declined_on = datetime.utcnow()
    invitation.decline_reason = reason if reason else None
    
    db.commit()
    
    return {
        "status": "declined",
        "message": "You have declined this review invitation",
        "invitation_id": invitation.id,
        "declined_on": invitation.declined_on.isoformat() if invitation.declined_on else None
    }


@router.post("/invitations/{token}/register-accept")
async def register_and_accept_invitation(
    token: str,
    fname: str = Query(..., description="First name"),
    lname: str = Query("", description="Last name"),
    password: str = Query(..., min_length=6, description="Password"),
    organization: str = Query("", description="Organization/Institution"),
    db: Session = Depends(get_db)
):
    """
    Register a new user and accept the invitation in one step (for external reviewers).
    
    Args:
        token: Invitation token
        fname: First name
        lname: Last name (optional)
        password: Password (min 6 chars)
        organization: Organization/Institution (optional)
        
    Returns:
        Registration confirmation and review assignment details
    """
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    invitation = db.query(ReviewerInvitation).filter(
        ReviewerInvitation.invitation_token == token
    ).first()
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found. The token may be invalid.")
    
    if invitation.status != "pending":
        raise HTTPException(status_code=400, detail=f"Invitation has already been {invitation.status}")
    
    if invitation.token_expiry and invitation.token_expiry < datetime.utcnow():
        invitation.status = "expired"
        db.commit()
        raise HTTPException(status_code=410, detail="Invitation has expired.")
    
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == invitation.reviewer_email).first()
    if existing_user:
        raise HTTPException(
            status_code=400, 
            detail="An account with this email already exists. Please log in and accept the invitation from your dashboard."
        )
    
    # Create new user with reviewer role
    hashed_password = pwd_context.hash(password)
    new_user = User(
        fname=fname,
        lname=lname,
        email=invitation.reviewer_email,
        password=hashed_password,
        role="reviewer",
        organization=organization,
        status="active"
    )
    db.add(new_user)
    db.flush()  # Get the user ID
    
    # Also add to UserRole table
    user_role = UserRole(
        user_id=new_user.id,
        role="reviewer",
        status="approved"
    )
    db.add(user_role)
    
    # Accept the invitation
    invitation.status = "accepted"
    invitation.accepted_on = datetime.utcnow()
    invitation.reviewer_id = new_user.id
    invitation.is_external = False  # Now they're an internal user
    
    # Create the review assignment
    from datetime import date
    online_review = OnlineReview(
        paper_id=invitation.paper_id,
        reviewer_id=str(new_user.id),
        assigned_on=date.today()
    )
    db.add(online_review)
    
    db.commit()
    db.refresh(new_user)
    db.refresh(online_review)
    
    return {
        "status": "registered_and_accepted",
        "message": "Account created and review assignment confirmed",
        "user_id": new_user.id,
        "user_email": new_user.email,
        "invitation_id": invitation.id,
        "paper_id": invitation.paper_id,
        "review_id": online_review.id,
        "accepted_on": invitation.accepted_on.isoformat() if invitation.accepted_on else None
    }
