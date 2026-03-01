"""Reviewer API endpoints"""
from fastapi import APIRouter, Depends, status, HTTPException, Query, File, UploadFile, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime, date, timedelta
import os
from app.db.database import get_db
from app.db.models import Paper, Journal, OnlineReview, User, ReviewerInvitation, ReviewSubmission, Editor
from app.core.security import get_current_user, get_current_user_from_token_or_query
from app.utils.auth_helpers import check_role, role_matches
from app.services.correspondence_service import create_and_send_correspondence
router = APIRouter(prefix="/api/v1/reviewer", tags=["Reviewer"])


@router.get("/dashboard/stats")
async def get_reviewer_stats(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get reviewer dashboard statistics.
    
    Returns:
        Dictionary with reviewer's assignment and review stats
    """
    try:
        if not check_role(current_user.get("role"), "reviewer"):
            raise HTTPException(status_code=403, detail="Reviewer access required")
        
        reviewer_id = str(current_user.get("id"))
        
        # Count total assignments for this reviewer
        total_assignments = db.query(func.count(OnlineReview.id)).filter(
            OnlineReview.reviewer_id == reviewer_id
        ).scalar() or 0
        
        # Count pending reviews (using review_status field)
        pending_reviews = db.query(func.count(OnlineReview.id)).filter(
            OnlineReview.reviewer_id == reviewer_id,
            OnlineReview.review_status == "pending"
        ).scalar() or 0
        
        # Count completed reviews (using review_status field)
        completed_reviews = db.query(func.count(OnlineReview.id)).filter(
            OnlineReview.reviewer_id == reviewer_id,
            OnlineReview.review_status == "completed"
        ).scalar() or 0
        
        return {
            "total_assignments": total_assignments,
            "pending_reviews": pending_reviews,
            "completed_reviews": completed_reviews,
            "avg_review_time": "0 days"
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error fetching reviewer stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {str(e)}")


@router.get("/invitations")
async def get_pending_invitations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get pending reviewer invitations for the current user.
    
    Args:
        skip: Number of records to skip
        limit: Number of records to return
        
    Returns:
        List of pending invitations
    """
    try:
        if not check_role(current_user.get("role"), "reviewer"):
            raise HTTPException(status_code=403, detail="Reviewer access required")
        
        user_id = current_user.get("id")
        user_email = current_user.get("email")
        
        # Get invitations for this reviewer (by ID if accepted before, or by email if pending)
        query = db.query(ReviewerInvitation).filter(
            (ReviewerInvitation.reviewer_id == user_id) | (ReviewerInvitation.reviewer_email == user_email)
        ).filter(
            ReviewerInvitation.status == "pending"
        ).order_by(desc(ReviewerInvitation.invited_on))
        
        total = query.count()
        invitations = query.offset(skip).limit(limit).all()
        
        invitations_list = []
        for invitation in invitations:
            paper = db.query(Paper).filter(Paper.id == invitation.paper_id).first()
            # added_by stores user ID, not email
            author = db.query(User).filter(User.id == int(paper.added_by)).first() if paper and paper.added_by and paper.added_by.isdigit() else None
            
            # Get journal name from journal table
            journal = None
            if paper and paper.journal:
                journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
            
            invitations_list.append({
                "id": invitation.id,
                "invitation_token": invitation.invitation_token,
                "paper_id": invitation.paper_id,
                "paper_title": paper.title if paper else "Unknown",
                "author": f"{author.fname} {author.lname or ''}".strip() if author else "Unknown",
                "journal": journal.fld_journal_name if journal else "Unknown",
                "invited_on": invitation.invited_on.isoformat() if invitation.invited_on else None,
                "token_expiry": invitation.token_expiry.isoformat() if invitation.token_expiry else None,
                "invitation_message": invitation.invitation_message,
                "status": invitation.status
            })
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "invitations": invitations_list
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error fetching pending invitations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching invitations: {str(e)}")


@router.post("/invitations/{invitation_id}/accept")
async def accept_invitation(
    invitation_id: int,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Accept a reviewer invitation.
    
    Args:
        invitation_id: ID of the invitation to accept
        
    Returns:
        Updated invitation object and created assignment
    """
    try:
        if not check_role(current_user.get("role"), "reviewer"):
            raise HTTPException(status_code=403, detail="Reviewer access required")
        
        user_id = current_user.get("id")
        user_email = current_user.get("email")
        
        invitation = db.query(ReviewerInvitation).filter(
            ReviewerInvitation.id == invitation_id
        ).first()
        
        if not invitation:
            raise HTTPException(status_code=404, detail="Invitation not found")
        
        # Verify that the invitation is for this user
        if invitation.reviewer_email != user_email and invitation.reviewer_id != user_id:
            raise HTTPException(status_code=403, detail="This invitation is not for you")
        
        # Check if invitation is still pending
        if invitation.status != "pending":
            raise HTTPException(status_code=400, detail=f"Invitation has already been {invitation.status}")
        
        # Check if token hasn't expired
        if invitation.token_expiry < datetime.utcnow():
            invitation.status = "expired"
            db.commit()
            raise HTTPException(status_code=400, detail="Invitation token has expired")
        
        # Check if reviewer is already assigned to this paper
        existing_review = db.query(OnlineReview).filter(
            OnlineReview.paper_id == invitation.paper_id,
            OnlineReview.reviewer_id == str(user_id)
        ).first()
        
        if existing_review:
            raise HTTPException(
                status_code=409,
                detail=f"You are already assigned as a reviewer for this paper. Duplicate assignments are not allowed."
            )
        
        # Update invitation
        invitation.status = "accepted"
        invitation.accepted_on = datetime.utcnow()
        invitation.reviewer_id = user_id  # Store the reviewer ID
        
        # Create OnlineReview record so the assignment shows up in "My Assignments"
        online_review = None
        try:
            online_review = OnlineReview(
                paper_id=invitation.paper_id,
                reviewer_id=str(user_id),
                assigned_on=date.today()
            )
            db.add(online_review)
            db.flush()  # Flush to make sure it's added
        except Exception as e:
            import logging
            logging.error(f"Error creating OnlineReview: {str(e)}")
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error creating assignment: {str(e)}")
        
        # Commit all changes
        db.commit()
        db.refresh(invitation)
        if online_review:
            db.refresh(online_review)
        
        paper = db.query(Paper).filter(Paper.id == invitation.paper_id).first()
        
        # Notify editor that reviewer accepted
        if paper:
            # Find editor from journal's editor assignment
            editor = None
            if paper.journal:
                editor_record = db.query(Editor).filter(Editor.journal_id == paper.journal).first()
                if editor_record and editor_record.editor_email:
                    editor = db.query(User).filter(User.email == editor_record.editor_email).first()
            
            if editor and editor.email:
                journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
                reviewer_user = db.query(User).filter(User.id == user_id).first()
                reviewer_name = f"{reviewer_user.fname or ''} {reviewer_user.lname or ''}".strip() if reviewer_user else user_email
                
                # Calculate due date (typically 2-3 weeks from acceptance)
                due_date = (datetime.utcnow() + timedelta(days=21)).strftime('%B %d, %Y')
                
                async def send_accept_notification():
                    from app.db.database import SessionLocal
                    email_db = SessionLocal()
                    try:
                        await create_and_send_correspondence(
                            db=email_db,
                            paper_id=paper.id,
                            paper_code=paper.paper_code,
                            paper_title=paper.title,
                            journal_name=journal.fld_journal_name if journal else "Breakthrough Publishers India Journal",
                            author_email=editor.email,
                            author_name=f"{editor.fname or ''} {editor.lname or ''}".strip() or "Editor",
                            email_type="invitation_accepted_editor",
                            status_at_send=paper.status,
                            reviewer_name=reviewer_name,
                            due_date=due_date
                        )
                    finally:
                        email_db.close()
                
                background_tasks.add_task(send_accept_notification)
        
        return {
            "id": invitation.id,
            "paper_id": invitation.paper_id,
            "paper_title": paper.title if paper else "Unknown",
            "status": invitation.status,
            "accepted_on": invitation.accepted_on.isoformat() if invitation.accepted_on else None,
            "message": "Invitation accepted successfully! Assignment has been added to your assignments."
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import logging
        logging.error(f"Error accepting invitation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error accepting invitation: {str(e)}")


@router.post("/invitations/{invitation_id}/decline")
async def decline_invitation(
    invitation_id: int,
    reason: str = Query(None),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Decline a reviewer invitation.
    
    Args:
        invitation_id: ID of the invitation to decline
        reason: Optional reason for declining
        
    Returns:
        Updated invitation object
    """
    try:
        if not check_role(current_user.get("role"), "reviewer"):
            raise HTTPException(status_code=403, detail="Reviewer access required")
        
        user_id = current_user.get("id")
        user_email = current_user.get("email")
        
        invitation = db.query(ReviewerInvitation).filter(
            ReviewerInvitation.id == invitation_id
        ).first()
        
        if not invitation:
            raise HTTPException(status_code=404, detail="Invitation not found")
        
        # Verify that the invitation is for this user
        if invitation.reviewer_email != user_email and invitation.reviewer_id != user_id:
            raise HTTPException(status_code=403, detail="This invitation is not for you")
        
        # Check if invitation is still pending
        if invitation.status != "pending":
            raise HTTPException(status_code=400, detail=f"Invitation has already been {invitation.status}")
        
        # Update invitation
        invitation.status = "declined"
        invitation.declined_on = datetime.utcnow()
        invitation.decline_reason = reason or ""
        
        db.commit()
        db.refresh(invitation)
        
        paper = db.query(Paper).filter(Paper.id == invitation.paper_id).first()
        
        # Notify editor that reviewer declined
        if paper and background_tasks:
            editor = None
            # Find editor from paper's journal
            if paper.journal:
                editor_record = db.query(Editor).filter(Editor.journal_id == paper.journal).first()
                if editor_record and editor_record.editor_email:
                    editor = db.query(User).filter(User.email == editor_record.editor_email).first()
            
            if editor and editor.email:
                journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
                reviewer_user = db.query(User).filter(User.id == user_id).first()
                reviewer_name = f"{reviewer_user.fname or ''} {reviewer_user.lname or ''}".strip() if reviewer_user else user_email
                
                async def send_decline_notification():
                    from app.db.database import SessionLocal
                    email_db = SessionLocal()
                    try:
                        await create_and_send_correspondence(
                            db=email_db,
                            paper_id=paper.id,
                            paper_code=paper.paper_code,
                            paper_title=paper.title,
                            journal_name=journal.fld_journal_name if journal else "Breakthrough Publishers India Journal",
                            author_email=editor.email,
                            author_name=f"{editor.fname or ''} {editor.lname or ''}".strip() or "Editor",
                            email_type="invitation_declined_editor",
                            status_at_send=paper.status,
                            reviewer_name=reviewer_name,
                            decline_reason=reason or ""
                        )
                    finally:
                        email_db.close()
                
                background_tasks.add_task(send_decline_notification)
        
        return {
            "id": invitation.id,
            "paper_id": invitation.paper_id,
            "paper_title": paper.title if paper else "Unknown",
            "status": invitation.status,
            "declined_on": invitation.declined_on.isoformat() if invitation.declined_on else None,
            "decline_reason": invitation.decline_reason,
            "message": "Invitation declined successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error declining invitation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error declining invitation: {str(e)}")


@router.get("/assignments")
async def list_assignments(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: str = Query(None),
    sort_by: str = Query("due_soon"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List reviewer's paper assignments.
    
    Args:
        skip: Number of records to skip
        limit: Number of records to return
        status_filter: Filter by review status
        sort_by: Sort option (recent, assigned_date)
        
    Returns:
        List of paper assignments for review
    """
    try:
        if not check_role(current_user.get("role"), "reviewer"):
            raise HTTPException(status_code=403, detail="Reviewer access required")
        
        reviewer_id = str(current_user.get("id"))
        query = db.query(OnlineReview).filter(
            OnlineReview.reviewer_id == reviewer_id
        )
        
        # Sorting
        if sort_by == "recent":
            query = query.order_by(desc(OnlineReview.assigned_on))
        else:  # default to assigned_date
            query = query.order_by(OnlineReview.assigned_on)
        
        total = query.count()
        reviews = query.offset(skip).limit(limit).all()
        
        assignments_list = []
        for review in reviews:
            paper = db.query(Paper).filter(Paper.id == review.paper_id).first()
            
            # Get author info - added_by stores user ID, not email
            author = None
            if paper and paper.added_by and paper.added_by.isdigit():
                author = db.query(User).filter(User.id == int(paper.added_by)).first()
            
            # Get journal name from journal table
            journal = None
            if paper and paper.journal:
                journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
            
            # Calculate due date (14 days from assignment by default)
            due_date = None
            if review.assigned_on:
                due_date = (review.assigned_on + timedelta(days=14)).isoformat()
            
            # Check if this is a re-review (version > 1 and status is pending)
            is_resubmission = paper.version_number > 1 if paper else False
            
            assignments_list.append({
                "id": review.id,
                "paper_id": review.paper_id,
                "paper_title": paper.title if paper else "Unknown",
                "author": f"{author.fname} {author.lname or ''}".strip() if author else "Unknown",
                "journal": journal.fld_journal_name if journal else "Unknown",
                "assigned_date": review.assigned_on.isoformat() if review.assigned_on else None,
                "due_date": due_date,
                "status": review.review_status or "pending",
                "paper_version": paper.version_number if paper else 1,
                "is_resubmission": is_resubmission,
                "paper_status": paper.status if paper else "unknown",
                "paper_type": paper.paper_type if paper else "Full Length Article"
            })
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "assignments": assignments_list
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error fetching assignments: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching assignments: {str(e)}")


@router.get("/assignments/{review_id}")
async def get_assignment_detail(
    review_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a review assignment.
    
    Args:
        review_id: Review assignment ID
        
    Returns:
        Complete paper and review details
    """
    try:
        reviewer_id = str(current_user.get("id"))
        review = db.query(OnlineReview).filter(
            OnlineReview.id == review_id,
            OnlineReview.reviewer_id == reviewer_id
        ).first()
        
        if not review:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        paper = db.query(Paper).filter(Paper.id == review.paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        
        # added_by stores user ID, not email
        author = db.query(User).filter(User.id == int(paper.added_by)).first() if paper.added_by and paper.added_by.isdigit() else None
        
        # Get journal name from journal table
        journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first() if paper.journal else None
        
        return {
            "review_id": review.id,
            "paper": {
                "id": paper.id,
                "title": paper.title,
                "abstract": paper.abstract,
                "keywords": paper.keyword,
                "author": {
                    "name": f"{author.fname} {author.lname or ''}".strip() if author else "Unknown",
                    "email": author.email if author else None,
                    "affiliation": author.affiliation if author else None
                },
                "journal": journal.fld_journal_name if journal else "Unknown",
                "submitted_date": paper.added_on.isoformat() if paper.added_on else None,
                "file_url": f"/static/{paper.file}" if paper.file else None
            },
            "assignment": {
                "assigned_date": review.assigned_on.isoformat() if review.assigned_on else None,
                "status": review.review_status or "pending"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error fetching assignment detail: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching assignment: {str(e)}")


@router.get("/assignments/{review_id}/detail")
async def get_review_detail(
    review_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get paper and review submission details for the review form.
    
    Args:
        review_id: Review assignment ID
        
    Returns:
        Paper details, assignment info, and existing review submission if any
    """
    try:
        if not check_role(current_user.get("role"), "reviewer"):
            raise HTTPException(status_code=403, detail="Reviewer access required")
        
        reviewer_id = str(current_user.get("id"))
        
        # Get the assignment
        assignment = db.query(OnlineReview).filter(
            OnlineReview.id == review_id,
            OnlineReview.reviewer_id == reviewer_id
        ).first()
        
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        # Get the paper
        paper = db.query(Paper).filter(Paper.id == assignment.paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        
        current_version = paper.version_number or 1
        
        # Get author info - added_by stores user ID, not email
        author = db.query(User).filter(User.id == int(paper.added_by)).first() if paper.added_by and paper.added_by.isdigit() else None
        
        # Get journal name from journal table
        journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first() if paper.journal else None
        journal_name = journal.fld_journal_name if journal else "Unknown Journal"
        
        # Get existing review submission for current paper version if any
        review_submission = db.query(ReviewSubmission).filter(
            ReviewSubmission.assignment_id == review_id,
            ReviewSubmission.reviewer_id == reviewer_id,
            ReviewSubmission.paper_version == current_version
        ).order_by(desc(ReviewSubmission.updated_at)).first()
        
        # Check if this is a re-review (previous version was reviewed)
        previous_review = None
        if current_version > 1:
            previous_review = db.query(ReviewSubmission).filter(
                ReviewSubmission.assignment_id == review_id,
                ReviewSubmission.reviewer_id == reviewer_id,
                ReviewSubmission.paper_version == current_version - 1,
                ReviewSubmission.status == "submitted"
            ).first()
        
        return {
            "paper": {
                "id": paper.id,
                "title": paper.title,
                "abstract": paper.abstract,
                "keywords": paper.keyword,
                "author": {
                    "name": f"{author.fname} {author.lname or ''}".strip() if author else "Unknown",
                    "email": author.email if author else None,
                    "affiliation": author.affiliation if author else None
                },
                "journal": journal_name,
                "submitted_date": paper.added_on.isoformat() if paper.added_on else None,
                "file": paper.file,
                "version_number": current_version,
                "is_resubmission": current_version > 1,
                # Resubmission files (only populated for revised papers)
                "revised_track_changes": paper.revised_track_changes if current_version > 1 else None,
                "revised_clean": paper.revised_clean if current_version > 1 else None,
                "response_to_reviewer": paper.response_to_reviewer if current_version > 1 else None
            },
            "assignment": {
                "id": assignment.id,
                "due_date": (assignment.assigned_on + timedelta(days=14)).isoformat() if assignment.assigned_on else None,
                "status": assignment.review_status or "pending"
            },
            "review_submission": review_submission.to_dict() if review_submission else None,
            "previous_review": previous_review.to_dict() if previous_review else None
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error fetching review detail: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching review detail: {str(e)}")


@router.get("/assignments/{review_id}/view-paper")
async def view_paper_file(
    review_id: int,
    current_user: dict = Depends(get_current_user_from_token_or_query),
    db: Session = Depends(get_db)
):
    """
    View the paper file for a review assignment in browser.
    
    Args:
        review_id: Review assignment ID
        
    Returns:
        Paper file for inline viewing
    """
    from app.utils.file_handler import get_file_full_path
    
    if not check_role(current_user.get("role"), "reviewer"):
        raise HTTPException(status_code=403, detail="Reviewer access required")
    
    reviewer_id = str(current_user.get("id"))
    
    # Verify reviewer is assigned to this paper
    assignment = db.query(OnlineReview).filter(
        OnlineReview.id == review_id,
        OnlineReview.reviewer_id == reviewer_id
    ).first()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Get the paper
    paper = db.query(Paper).filter(Paper.id == assignment.paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Reviewers only see blinded manuscript (no author info) - fall back to file for older papers
    file_path = paper.blinded_manuscript or paper.file
    if not file_path:
        raise HTTPException(status_code=404, detail="Paper file not found")
    
    # Get full file path from relative path stored in DB
    filepath = get_file_full_path(file_path)
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Paper file not found on server")
    
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


@router.get("/assignments/{review_id}/view-track-changes")
async def view_track_changes_file(
    review_id: int,
    current_user: dict = Depends(get_current_user_from_token_or_query),
    db: Session = Depends(get_db)
):
    """
    View the track changes file for a resubmission.
    
    Args:
        review_id: Review assignment ID
        
    Returns:
        Track changes file for inline viewing
    """
    from app.utils.file_handler import get_file_full_path
    
    if not check_role(current_user.get("role"), "reviewer"):
        raise HTTPException(status_code=403, detail="Reviewer access required")
    
    reviewer_id = str(current_user.get("id"))
    
    assignment = db.query(OnlineReview).filter(
        OnlineReview.id == review_id,
        OnlineReview.reviewer_id == reviewer_id
    ).first()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    paper = db.query(Paper).filter(Paper.id == assignment.paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    if not paper.revised_track_changes:
        raise HTTPException(status_code=404, detail="Track changes file not found")
    
    filepath = get_file_full_path(paper.revised_track_changes)
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Track changes file not found on server")
    
    filename = filepath.name
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


@router.get("/assignments/{review_id}/view-clean-manuscript")
async def view_clean_manuscript_file(
    review_id: int,
    current_user: dict = Depends(get_current_user_from_token_or_query),
    db: Session = Depends(get_db)
):
    """
    View the clean revised manuscript for a resubmission.
    
    Args:
        review_id: Review assignment ID
        
    Returns:
        Clean revised manuscript for inline viewing
    """
    from app.utils.file_handler import get_file_full_path
    
    if not check_role(current_user.get("role"), "reviewer"):
        raise HTTPException(status_code=403, detail="Reviewer access required")
    
    reviewer_id = str(current_user.get("id"))
    
    assignment = db.query(OnlineReview).filter(
        OnlineReview.id == review_id,
        OnlineReview.reviewer_id == reviewer_id
    ).first()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    paper = db.query(Paper).filter(Paper.id == assignment.paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    if not paper.revised_clean:
        raise HTTPException(status_code=404, detail="Clean manuscript file not found")
    
    filepath = get_file_full_path(paper.revised_clean)
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Clean manuscript file not found on server")
    
    filename = filepath.name
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


@router.get("/assignments/{review_id}/view-response-to-reviewer")
async def view_response_to_reviewer_file(
    review_id: int,
    current_user: dict = Depends(get_current_user_from_token_or_query),
    db: Session = Depends(get_db)
):
    """
    View the author's response to reviewer comments for a resubmission.
    
    Args:
        review_id: Review assignment ID
        
    Returns:
        Response to reviewer file for inline viewing
    """
    from app.utils.file_handler import get_file_full_path
    
    if not check_role(current_user.get("role"), "reviewer"):
        raise HTTPException(status_code=403, detail="Reviewer access required")
    
    reviewer_id = str(current_user.get("id"))
    
    assignment = db.query(OnlineReview).filter(
        OnlineReview.id == review_id,
        OnlineReview.reviewer_id == reviewer_id
    ).first()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    paper = db.query(Paper).filter(Paper.id == assignment.paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    if not paper.response_to_reviewer:
        raise HTTPException(status_code=404, detail="Response to reviewer file not found")
    
    filepath = get_file_full_path(paper.response_to_reviewer)
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Response to reviewer file not found on server")
    
    filename = filepath.name
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


@router.post("/assignments/{review_id}/save-draft")
async def save_review_draft(
    review_id: int,
    draft_data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save a review as draft (auto-save). Updates status to in_progress on first save.
    
    Args:
        review_id: Review assignment ID
        draft_data: Draft data with ratings and comments
        
    Returns:
        Saved review submission
    """
    try:
        if not check_role(current_user.get("role"), "reviewer"):
            raise HTTPException(status_code=403, detail="Reviewer access required")
        
        reviewer_id = str(current_user.get("id"))
        
        # Get the assignment
        assignment = db.query(OnlineReview).filter(
            OnlineReview.id == review_id,
            OnlineReview.reviewer_id == reviewer_id
        ).first()
        
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        # Get paper to check version for version-aware review submissions
        paper = db.query(Paper).filter(Paper.id == assignment.paper_id).first()
        current_version = paper.version_number if paper else 1
        
        # Check if review submission exists for current paper version
        review_submission = db.query(ReviewSubmission).filter(
            ReviewSubmission.assignment_id == review_id,
            ReviewSubmission.reviewer_id == reviewer_id,
            ReviewSubmission.paper_version == current_version
        ).first()
        
        if not review_submission:
            # Create new review submission for this version
            review_submission = ReviewSubmission(
                paper_id=assignment.paper_id,
                reviewer_id=reviewer_id,
                assignment_id=review_id,
                paper_version=current_version,
                status="draft"
            )
        
        # Update fields from draft_data
        if 'technical_quality' in draft_data:
            review_submission.technical_quality = draft_data.get('technical_quality')
        if 'clarity' in draft_data:
            review_submission.clarity = draft_data.get('clarity')
        if 'originality' in draft_data:
            review_submission.originality = draft_data.get('originality')
        if 'significance' in draft_data:
            review_submission.significance = draft_data.get('significance')
        if 'overall_rating' in draft_data:
            review_submission.overall_rating = draft_data.get('overall_rating')
        if 'author_comments' in draft_data:
            review_submission.author_comments = draft_data.get('author_comments')
        if 'confidential_comments' in draft_data:
            review_submission.confidential_comments = draft_data.get('confidential_comments')
        if 'recommendation' in draft_data:
            review_submission.recommendation = draft_data.get('recommendation')
        
        # Auto-update assignment status to in_progress on first save
        if assignment.review_status != 'in_progress':
            assignment.review_status = 'in_progress'
        
        db.add(review_submission)
        db.add(assignment)
        db.commit()
        db.refresh(review_submission)
        db.refresh(assignment)
        
        return {
            "message": "Draft saved successfully",
            "review_submission": review_submission.to_dict(),
            "assignment_status": assignment.review_status
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import logging
        logging.error(f"Error saving draft: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving draft: {str(e)}")


@router.post("/assignments/{review_id}/submit")
async def submit_review_complete(
    review_id: int,
    review_data: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit a completed review with full validation.
    Sends notifications to editor and author.
    
    Args:
        review_id: Review assignment ID
        review_data: Complete review data
        
    Returns:
        Submitted review submission
    """
    try:
        if not check_role(current_user.get("role"), "reviewer"):
            raise HTTPException(status_code=403, detail="Reviewer access required")
        
        reviewer_id = str(current_user.get("id"))
        
        # Validate required fields
        required_fields = ['technical_quality', 'clarity', 'originality', 'significance', 'overall_rating', 'recommendation']
        for field in required_fields:
            if field not in review_data or review_data[field] is None:
                raise HTTPException(status_code=400, detail=f"{field} is required")
        
        # Validate ratings are 1-5
        for field in ['technical_quality', 'clarity', 'originality', 'significance', 'overall_rating']:
            value = review_data.get(field)
            if not isinstance(value, int) or value < 1 or value > 5:
                raise HTTPException(status_code=400, detail=f"{field} must be between 1 and 5")
        
        # Validate comments (at least 50 chars total)
        author_comments = review_data.get('author_comments', '')
        confidential_comments = review_data.get('confidential_comments', '')
        total_comments = author_comments + confidential_comments
        if len(total_comments.strip()) < 50:
            raise HTTPException(status_code=400, detail="Comments must be at least 50 characters total")
        
        # Get the assignment
        assignment = db.query(OnlineReview).filter(
            OnlineReview.id == review_id,
            OnlineReview.reviewer_id == reviewer_id
        ).first()
        
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        # Get paper to check version
        paper = db.query(Paper).filter(Paper.id == assignment.paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        
        current_version = paper.version_number or 1
        
        # Get or create review submission for the CURRENT paper version
        # This allows re-reviews for resubmitted papers
        review_submission = db.query(ReviewSubmission).filter(
            ReviewSubmission.assignment_id == review_id,
            ReviewSubmission.reviewer_id == reviewer_id,
            ReviewSubmission.paper_version == current_version
        ).first()
        
        if not review_submission:
            # Create new review submission for this version
            review_submission = ReviewSubmission(
                paper_id=assignment.paper_id,
                reviewer_id=reviewer_id,
                assignment_id=review_id,
                paper_version=current_version
            )
        
        # Update all fields
        review_submission.technical_quality = review_data.get('technical_quality')
        review_submission.clarity = review_data.get('clarity')
        review_submission.originality = review_data.get('originality')
        review_submission.significance = review_data.get('significance')
        review_submission.overall_rating = review_data.get('overall_rating')
        review_submission.author_comments = review_data.get('author_comments')
        review_submission.confidential_comments = review_data.get('confidential_comments')
        review_submission.recommendation = review_data.get('recommendation')
        review_submission.status = "submitted"
        review_submission.submitted_at = datetime.utcnow()
        
        # Update assignment status
        assignment.review_status = 'completed'
        assignment.date_submitted = datetime.utcnow()
        assignment.submitted_on = datetime.utcnow()
        
        db.add(review_submission)
        db.add(assignment)
        
        # Update paper status to 'reviewed' when a review is submitted (paper already fetched above)
        if paper.status in ['submitted', 'under_review']:
            paper.status = 'reviewed'
            db.add(paper)
        
        db.commit()
        db.refresh(review_submission)
        db.refresh(assignment)
        
        # Send notifications to editor and author
        journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
        reviewer_user = db.query(User).filter(User.id == int(reviewer_id)).first()
        reviewer_name = f"{reviewer_user.fname or ''} {reviewer_user.lname or ''}".strip() if reviewer_user else "Reviewer"
        recommendation = review_data.get('recommendation', 'N/A')
        overall_rating = review_data.get('overall_rating', 'N/A')
        
        # Notify editor
        editor = None
        if paper.journal:
            editor_record = db.query(Editor).filter(Editor.journal_id == paper.journal).first()
            if editor_record and editor_record.editor_email:
                editor = db.query(User).filter(User.email == editor_record.editor_email).first()
        
        if editor and editor.email:
            async def send_editor_notification():
                from app.db.database import SessionLocal
                email_db = SessionLocal()
                try:
                    await create_and_send_correspondence(
                        db=email_db,
                        paper_id=paper.id,
                        paper_code=paper.paper_code,
                        paper_title=paper.title,
                        journal_name=journal.fld_journal_name if journal else "Breakthrough Publishers India Journal",
                        author_email=editor.email,
                        author_name=f"{editor.fname or ''} {editor.lname or ''}".strip() or "Editor",
                        email_type="review_submitted_editor",
                        status_at_send=paper.status,
                        reviewer_name=reviewer_name,
                        recommendation=recommendation,
                        overall_rating=str(overall_rating)
                    )
                finally:
                    email_db.close()
            
            background_tasks.add_task(send_editor_notification)
        
        # Notify author that review is complete (without showing review details)
        author = None
        if paper.added_by and paper.added_by.isdigit():
            author = db.query(User).filter(User.id == int(paper.added_by)).first()
        
        if author and author.email:
            async def send_author_notification():
                from app.db.database import SessionLocal
                email_db = SessionLocal()
                try:
                    await create_and_send_correspondence(
                        db=email_db,
                        paper_id=paper.id,
                        paper_code=paper.paper_code,
                        paper_title=paper.title,
                        journal_name=journal.fld_journal_name if journal else "Breakthrough Publishers India Journal",
                        author_email=author.email,
                        author_name=f"{author.fname or ''} {author.lname or ''}".strip() or "Author",
                        email_type="review_completed_author",
                        status_at_send=paper.status
                    )
                finally:
                    email_db.close()
            
            background_tasks.add_task(send_author_notification)
        
        return {
            "message": "Review submitted successfully",
            "review_submission": review_submission.to_dict(),
            "assignment": {
                "id": assignment.id,
                "status": assignment.review_status,
                "submitted_on": assignment.date_submitted.isoformat() if assignment.date_submitted else None
            },
            "notifications_sent": True
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import logging
        logging.error(f"Error submitting review: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error submitting review: {str(e)}")


@router.post("/assignments/{review_id}/upload-report")
async def upload_review_report(
    review_id: int,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a review report file with version control.
    
    Args:
        review_id: Review assignment ID
        file: Report file to upload
        
    Returns:
        File upload info with path and version
    """
    try:
        if not check_role(current_user.get("role"), "reviewer"):
            raise HTTPException(status_code=403, detail="Reviewer access required")
        
        reviewer_id = str(current_user.get("id"))
        
        # Validate file type
        allowed_types = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Only PDF, DOC, and DOCX files are allowed")
        
        # Read file content to validate size (10MB max)
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size must be less than 10MB")
        
        # Get the assignment
        assignment = db.query(OnlineReview).filter(
            OnlineReview.id == review_id,
            OnlineReview.reviewer_id == reviewer_id
        ).first()
        
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        # Get or create review submission
        review_submission = db.query(ReviewSubmission).filter(
            ReviewSubmission.assignment_id == review_id,
            ReviewSubmission.reviewer_id == reviewer_id
        ).first()
        
        if not review_submission:
            review_submission = ReviewSubmission(
                paper_id=assignment.paper_id,
                reviewer_id=reviewer_id,
                assignment_id=review_id,
                status="draft"
            )
        
        # Increment version
        next_version = (review_submission.file_version or 0) + 1
        
        # Create upload directory using proper base path
        from app.utils.file_handler import UPLOAD_BASE_DIR
        # UPLOAD_BASE_DIR is backend/uploads/papers, we want backend/uploads/reviews
        upload_dir = UPLOAD_BASE_DIR.parent / "reviews" / f"reviewer_{reviewer_id}"
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generate filename with version
        filename = f"{review_id}_v{next_version}_{file.filename}"
        filepath = upload_dir / filename
        
        # Save file
        with open(filepath, 'wb') as f:
            f.write(content)
        
        # Store relative path in database (relative to backend/)
        relative_path = f"uploads/reviews/reviewer_{reviewer_id}/{filename}"
        
        # Update review submission
        review_submission.review_report_file = relative_path
        review_submission.file_version = next_version
        
        # Auto-update to in_progress if this is first interaction
        if assignment.review_status != 'in_progress':
            assignment.review_status = 'in_progress'
        
        db.add(review_submission)
        db.add(assignment)
        db.commit()
        db.refresh(review_submission)
        db.refresh(assignment)
        
        return {
            "message": "File uploaded successfully",
            "file_path": filepath,
            "file_version": next_version,
            "filename": filename,
            "assignment_status": assignment.review_status
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import logging
        logging.error(f"Error uploading report: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error uploading report: {str(e)}")


@router.get("/assignments/{review_id}/download-report")
async def download_review_report(
    review_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Download a review report file uploaded by the reviewer.
    
    Args:
        review_id: Review assignment ID
        
    Returns:
        File download
    """
    try:
        from pathlib import Path
        
        if not check_role(current_user.get("role"), "reviewer"):
            raise HTTPException(status_code=403, detail="Reviewer access required")
        
        reviewer_id = str(current_user.get("id"))
        
        # Get review submission
        review_submission = db.query(ReviewSubmission).filter(
            ReviewSubmission.assignment_id == review_id,
            ReviewSubmission.reviewer_id == reviewer_id
        ).first()
        
        if not review_submission:
            raise HTTPException(status_code=404, detail="Review submission not found")
        
        if not review_submission.review_report_file:
            raise HTTPException(status_code=404, detail="No report file uploaded")
        
        filepath = Path(review_submission.review_report_file)
        
        # If path is relative, make it absolute
        if not filepath.is_absolute():
            from app.utils.file_handler import UPLOAD_BASE_DIR
            # Path format: "uploads/reviews/reviewer_X/file.docx"
            # UPLOAD_BASE_DIR.parent.parent is backend/
            if review_submission.review_report_file.startswith("uploads/"):
                filepath = UPLOAD_BASE_DIR.parent.parent / review_submission.review_report_file
            else:
                filepath = UPLOAD_BASE_DIR.parent / review_submission.review_report_file
        
        # Check if file exists
        if not filepath.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        # Extract filename from path for download
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
            media_type=media_type
        )
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error downloading report: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error downloading report: {str(e)}")


@router.post("/assignments/{review_id}/submit-review")
async def submit_review(
    review_id: int,
    review_data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit a review for a paper.
    
    Args:
        review_id: Review assignment ID
        review_data: Review form data containing ratings and comments
        
    Returns:
        Updated review object
    """
    try:
        if not check_role(current_user.get("role"), "reviewer"):
            raise HTTPException(status_code=403, detail="Reviewer access required")
        
        reviewer_id = str(current_user.get("id"))
        review = db.query(OnlineReview).filter(
            OnlineReview.id == review_id,
            OnlineReview.reviewer_id == reviewer_id
        ).first()
        
        if not review:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        # Since OnlineReview model is simple, we can only store basic info
        # In a production system, you'd want to create a separate reviews table
        # For now, mark as reviewed and commit
        
        db.commit()
        db.refresh(review)
        
        return {
            "id": review.id,
            "paper_id": review.paper_id,
            "reviewer_id": review.reviewer_id,
            "assigned_on": review.assigned_on.isoformat() if review.assigned_on else None,
            "status": review.review_status or "pending"
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error submitting review: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error submitting review: {str(e)}")


@router.get("/history")
async def get_review_history(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get reviewer's review history.
    
    Returns:
        List of completed reviews with details
    """
    try:
        if not check_role(current_user.get("role"), "reviewer"):
            raise HTTPException(status_code=403, detail="Reviewer access required")
        
        reviewer_id = str(current_user.get("id"))
        all_reviews = db.query(OnlineReview).filter(
            OnlineReview.reviewer_id == reviewer_id
        ).order_by(desc(OnlineReview.assigned_on)).all()
        
        history_list = []
        for review in all_reviews:
            paper = db.query(Paper).filter(Paper.id == review.paper_id).first()
            
            # Get journal name from journal table
            journal = None
            if paper and paper.journal:
                journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
            
            # Get author info - added_by stores user ID
            author = None
            if paper and paper.added_by and paper.added_by.isdigit():
                author = db.query(User).filter(User.id == int(paper.added_by)).first()
            
            history_list.append({
                "review_id": review.id,
                "paper_id": review.paper_id,
                "paper_title": paper.title if paper else "Unknown",
                "author": f"{author.fname} {author.lname or ''}".strip() if author else "Unknown",
                "journal": journal.fld_journal_name if journal else "Unknown",
                "assigned_date": review.assigned_on.isoformat() if review.assigned_on else None,
                "status": review.review_status or "pending"
            })
        
        return {
            "total": len(history_list),
            "history": history_list
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error fetching review history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching history: {str(e)}")
    
    return history_list


@router.get("/profile")
async def get_reviewer_profile(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get reviewer's profile information.
    
    Returns:
        Reviewer profile with specialization and statistics
    """
    try:
        if not check_role(current_user.get("role"), "reviewer"):
            raise HTTPException(status_code=403, detail="Reviewer access required")
        
        user_id = current_user.get("id")
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Use reviewer_id instead of reviewer_email
        reviewer_id = str(user_id)
        total_reviews = db.query(func.count(OnlineReview.id)).filter(
            OnlineReview.reviewer_id == reviewer_id
        ).scalar() or 0
        
        return {
            "name": f"{user.fname} {user.lname or ''}",
            "email": user.email,
            "title": user.title,
            "affiliation": user.affiliation,
            "specialization": user.specialization,
            "contact": user.contact,
            "total_reviews": total_reviews
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error fetching reviewer profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching profile: {str(e)}")

@router.post("/notify-update")
async def notify_review_update(
    notification_data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send email notification to reviewer for updates (new assignment, submission confirmation, etc.).
    Can be called by reviewers for their own notifications or by editors/admins.
    
    Args:
        notification_data: Dictionary containing:
            - reviewer_email: Reviewer's email address
            - reviewer_name: Reviewer's name (optional, will fetch if not provided)
            - paper_title: Title of the paper
            - journal_name: Name of the journal
            - update_type: Type of update (new_assignment, submission_confirmed, admin_message)
            - message: Optional custom message (for admin_message type)
    
    Returns:
        Status of email delivery
    """
    from app.utils.reviewer_email_scheduler import ReviewerEmailScheduler
    
    # Only allow editors, admins, and the reviewer themselves
    user_role = current_user.get("role")
    user_email = current_user.get("email")
    target_reviewer_email = notification_data.get("reviewer_email")
    
    # Validate access - allow if user is admin/editor or if they're the target reviewer
    if not check_role(user_role, ["admin", "editor"]) and user_email != target_reviewer_email:
        raise HTTPException(status_code=403, detail="Not authorized to send this notification")
    
    try:
        reviewer_email = notification_data.get("reviewer_email")
        reviewer_name = notification_data.get("reviewer_name")
        paper_title = notification_data.get("paper_title")
        journal_name = notification_data.get("journal_name")
        update_type = notification_data.get("update_type", "admin_message")
        message = notification_data.get("message", "")
        
        # Validate required fields
        if not reviewer_email or not paper_title or not journal_name:
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: reviewer_email, paper_title, journal_name"
            )
        
        # Fetch reviewer name if not provided
        if not reviewer_name:
            reviewer = db.query(User).filter(User.email == reviewer_email).first()
            if reviewer:
                reviewer_name = reviewer.fname or "Reviewer"
            else:
                reviewer_name = "Reviewer"
        
        # Send notification
        success = ReviewerEmailScheduler.send_review_update_notification(
            reviewer_email=reviewer_email,
            reviewer_name=reviewer_name,
            paper_title=paper_title,
            journal_name=journal_name,
            update_type=update_type,
            message=message
        )
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to send email notification"
            )
        
        return {
            "status": "success",
            "message": f"Notification sent to {reviewer_email}",
            "update_type": update_type,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending review update notification: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error sending notification: {str(e)}"
        )


@router.post("/deadline-reminder")
async def send_deadline_reminder(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually trigger deadline reminder emails. 
    This endpoint should be called by a scheduler (e.g., APScheduler) at 9AM daily.
    Only accessible by admin or system scheduler.
    
    Returns:
        Summary of emails sent
    """
    from app.utils.reviewer_email_scheduler import ReviewerEmailScheduler
    
    # Only allow admin or internal calls
    user_role = current_user.get("role")
    if not check_role(user_role, "admin"):
        raise HTTPException(
            status_code=403,
            detail="Only administrators can trigger deadline reminders"
        )
    
    try:
        ReviewerEmailScheduler.send_deadline_reminder()
        
        return {
            "status": "success",
            "message": "Deadline reminder batch completed",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in deadline reminder endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error sending reminders: {str(e)}"
        )