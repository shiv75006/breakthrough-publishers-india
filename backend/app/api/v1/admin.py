"""Admin API endpoints"""
from fastapi import APIRouter, Depends, status, HTTPException, Query, Body, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from datetime import datetime
from app.db.database import get_db
from app.db.models import User, Journal, Paper, PaperPublished, OnlineReview, ReviewSubmission, UserRole, News, EmailTemplate, PaperCorrespondence
from app.core.security import get_current_user
from app.core.rate_limit import limiter
from app.utils.auth_helpers import check_role
from app.schemas.publish import (
    AccessTypeUpdate, AccessType, BulkAccessUpdateRequest, 
    BulkAccessUpdateResponse, PublishedPaperResponse
)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


@router.get("/dashboard/stats")
@limiter.limit("200/minute")
async def get_dashboard_stats(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get admin dashboard statistics.
    
    Returns:
        Dictionary with dashboard stats (total users, journals, papers, published)
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_journals = db.query(func.count(Journal.fld_id)).scalar() or 0
    total_submissions = db.query(func.count(Paper.id)).scalar() or 0
    pending_papers = db.query(func.count(Paper.id)).filter(
        Paper.status.in_(["submitted", "under_review"])
    ).scalar() or 0
    published_papers = db.query(func.count(PaperPublished.id)).scalar() or 0
    
    return {
        "total_users": total_users,
        "total_journals": total_journals,
        "total_submissions": total_submissions,
        "pending_papers": pending_papers,
        "published_papers": published_papers
    }


@router.get("/users")
@limiter.limit("200/minute")
async def list_users(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=2000),
    search: str = Query(None),
    role: str = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all users with optional filtering and pagination.
    
    Args:
        skip: Number of records to skip
        limit: Number of records to return
        search: Search by email or name
        role: Filter by user role
        
    Returns:
        List of users with pagination info including all assigned roles
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    query = db.query(User)
    
    if search:
        query = query.filter(
            (User.email.ilike(f"%{search}%")) |
            (User.fname.ilike(f"%{search}%")) |
            (User.lname.ilike(f"%{search}%"))
        )
    
    if role:
        query = query.filter(User.role == role)
    
    total = query.count()
    users = query.offset(skip).limit(limit).all()
    
    # Get all user IDs to fetch their roles in one query
    user_ids = [user.id for user in users]
    
    # Fetch all roles for these users
    user_roles = db.query(UserRole).filter(
        UserRole.user_id.in_(user_ids),
        UserRole.status == "approved"
    ).all()
    
    # Create a mapping of user_id to list of roles
    roles_map = {}
    for ur in user_roles:
        if ur.user_id not in roles_map:
            roles_map[ur.user_id] = []
        roles_map[ur.user_id].append(ur.role)
    
    # Build user data with all roles
    users_data = []
    for user in users:
        user_data = user.to_dict()
        # Get all roles from user_role table, or fall back to primary role
        all_roles = roles_map.get(user.id, [])
        if not all_roles and user.role:
            all_roles = [user.role]
        user_data["all_roles"] = all_roles
        users_data.append(user_data)
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "users": users_data
    }


@router.post("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    role: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update user role (single role - legacy endpoint).
    
    Args:
        user_id: User ID to update
        role: New role (admin, author, editor, reviewer)
        
    Returns:
        Updated user object
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    allowed_roles = ["admin", "author", "editor", "reviewer"]
    if role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Allowed: {allowed_roles}")
    
    user.role = role
    db.commit()
    db.refresh(user)
    
    return user.to_dict()


@router.get("/users/{user_id}/roles")
async def get_user_roles(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all roles assigned to a user.
    
    Args:
        user_id: User ID
        
    Returns:
        List of user roles with details
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get roles from UserRole table
    user_roles = db.query(UserRole).filter(
        UserRole.user_id == user_id,
        UserRole.status == "approved"
    ).all()
    
    return {
        "user_id": user_id,
        "primary_role": user.role,
        "roles": [ur.to_dict() for ur in user_roles]
    }


@router.put("/users/{user_id}/roles")
async def update_user_roles(
    user_id: int,
    roles: list = Body(..., embed=True),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update user roles - allows assigning multiple roles.
    
    Args:
        user_id: User ID to update
        roles: List of role strings (admin, author, editor, reviewer)
        
    Returns:
        Updated user with all roles
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    allowed_roles = ["admin", "author", "editor", "reviewer"]
    invalid_roles = [r for r in roles if r not in allowed_roles]
    if invalid_roles:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid roles: {invalid_roles}. Allowed: {allowed_roles}"
        )
    
    if not roles:
        raise HTTPException(status_code=400, detail="At least one role is required")
    
    admin_id = current_user.get("id")
    
    # Get existing approved roles for this user
    existing_roles = db.query(UserRole).filter(
        UserRole.user_id == user_id,
        UserRole.status == "approved"
    ).all()
    existing_role_names = {ur.role for ur in existing_roles}
    
    # Determine roles to add and remove
    new_roles = set(roles)
    roles_to_add = new_roles - existing_role_names
    roles_to_remove = existing_role_names - new_roles
    
    # Remove roles that are no longer assigned
    if roles_to_remove:
        db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.role.in_(roles_to_remove)
        ).delete(synchronize_session=False)
    
    # Add new roles
    for role in roles_to_add:
        new_user_role = UserRole(
            user_id=user_id,
            role=role,
            status="approved",
            requested_at=datetime.utcnow(),
            approved_by=admin_id,
            approved_at=datetime.utcnow()
        )
        db.add(new_user_role)
    
    # Update primary role (first role in the list, prefer admin > editor > reviewer > author)
    role_priority = {"admin": 4, "editor": 3, "reviewer": 2, "author": 1}
    primary_role = max(roles, key=lambda r: role_priority.get(r, 0))
    user.role = primary_role
    
    db.commit()
    
    # Fetch updated roles
    updated_roles = db.query(UserRole).filter(
        UserRole.user_id == user_id,
        UserRole.status == "approved"
    ).all()
    
    return {
        "success": True,
        "message": f"User roles updated successfully",
        "user": user.to_dict(),
        "roles": [ur.to_dict() for ur in updated_roles]
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a user.
    
    Args:
        user_id: User ID to delete
        
    Returns:
        Confirmation message
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user)
    db.commit()
    
    return {"message": f"User {user_id} deleted successfully"}


@router.get("/papers")
@limiter.limit("200/minute")
async def list_all_papers(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: str = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all papers with optional status filter.
    
    Args:
        skip: Number of records to skip
        limit: Number of records to return
        status: Filter by paper status
        
    Returns:
        List of papers with pagination info
    """
    if not check_role(current_user.get("role"), ["admin", "editor"]):
        raise HTTPException(status_code=403, detail="Admin or Editor access required")
    
    query = db.query(Paper)
    
    if status:
        query = query.filter(Paper.status == status)
    
    total = query.count()
    papers = query.order_by(desc(Paper.added_on)).offset(skip).limit(limit).all()
    
    # Get journal names and review status for papers
    paper_list = []
    for paper in papers:
        paper_dict = paper.to_dict()
        if paper.journal:
            # paper.journal is now INT
            journal = db.query(Journal).filter(Journal.fld_id == paper.journal).first()
            if journal:
                paper_dict['journal_name'] = journal.fld_journal_name
        
        # Get author info - added_by stores user ID
        if paper.added_by and paper.added_by.isdigit():
            author = db.query(User).filter(User.id == int(paper.added_by)).first()
            if author:
                paper_dict['author_name'] = f"{author.fname} {author.lname or ''}".strip()
        
        # Get review status for the paper
        # Note: OnlineReview.paper_id is stored as VARCHAR in the database
        total_assignments = db.query(func.count(OnlineReview.id)).filter(
            OnlineReview.paper_id == str(paper.id)
        ).scalar() or 0
        
        completed_reviews = db.query(func.count(ReviewSubmission.id)).filter(
            ReviewSubmission.paper_id == paper.id,
            ReviewSubmission.status == "submitted"
        ).scalar() or 0
        
        # Determine review status
        if total_assignments == 0:
            review_status = "not_assigned"
        elif completed_reviews == 0:
            review_status = "pending"
        elif completed_reviews < total_assignments:
            review_status = "partial"
        else:
            review_status = "reviewed"
        
        paper_dict['review_status'] = review_status
        paper_dict['total_reviewers'] = total_assignments
        paper_dict['completed_reviews'] = completed_reviews
        
        paper_list.append(paper_dict)
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "papers": paper_list
    }


@router.get("/papers/{paper_id}")
@limiter.limit("200/minute")
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
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
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
        "research_area": paper.research_area,
        "message_to_editor": paper.message_to_editor
    }


@router.get("/journals")
@limiter.limit("200/minute")
async def list_all_journals(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all journals with optional search.
    
    Args:
        skip: Number of records to skip
        limit: Number of records to return
        search: Search by journal name or short form
        
    Returns:
        List of journals with pagination info
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    query = db.query(Journal)
    
    if search:
        query = query.filter(
            (Journal.fld_journal_name.ilike(f"%{search}%")) |
            (Journal.short_form.ilike(f"%{search}%"))
        )
    
    total = query.count()
    journals = query.offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "journals": [journal.to_dict() for journal in journals]
    }


@router.get("/activity")
@limiter.limit("200/minute")
async def get_recent_activity(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get recent system activity (new users, papers, etc).
    
    Args:
        limit: Number of activities to return
        
    Returns:
        List of recent activities
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    activities = []
    
    # Get recent users
    recent_users = db.query(User).order_by(desc(User.added_on)).limit(limit // 2).all()
    for user in recent_users:
        if user.added_on:
            activities.append({
                "type": "user_registration",
                "description": f"New user registered: {user.email}",
                "timestamp": user.added_on.isoformat() if user.added_on else None
            })
    
    # Get recent papers
    recent_papers = db.query(Paper).order_by(desc(Paper.added_on)).limit(limit // 2).all()
    for paper in recent_papers:
        if paper.added_on:
            activities.append({
                "type": "paper_submission",
                "description": f"New paper submitted: {paper.title or 'Untitled'}",
                "timestamp": paper.added_on.isoformat() if paper.added_on else None
            })
    
    # Sort by timestamp (handle None) and return
    activities.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return activities[:limit]


@router.get("/stats/papers-by-status")
@limiter.limit("200/minute")
async def get_papers_by_status(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get breakdown of papers by status.
    
    Returns:
        Dictionary with paper counts by status
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Include all paper statuses including "reviewed"
    statuses = ["submitted", "under_review", "reviewed", "accepted", "rejected", "correction", "under_publication", "published", "resubmitted"]
    stats = {}
    
    for status in statuses:
        count = db.query(func.count(Paper.id)).filter(
            Paper.status == status
        ).scalar() or 0
        # Only include statuses that have at least one paper
        if count > 0:
            stats[status] = count
    
    return stats


@router.get("/papers/{paper_id}/view")
@limiter.limit("200/minute")
async def admin_view_paper_file(
    request: Request,
    paper_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    View any paper file (admin only).
    
    Args:
        paper_id: Paper ID
        
    Returns:
        Paper file for inline viewing
    """
    from fastapi.responses import FileResponse
    from app.utils.file_handler import get_file_full_path
    
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    if not paper.file:
        raise HTTPException(status_code=404, detail="Paper file not found")
    
    # Get full file path from relative path stored in DB
    filepath = get_file_full_path(paper.file)
    
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


# ============================================================================
# PAPER ACCESS CONTROL ENDPOINTS
# ============================================================================

@router.patch("/published-papers/{paper_id}/access")
@limiter.limit("100/minute")
async def update_paper_access_type(
    request: Request,
    paper_id: int,
    access_update: AccessTypeUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update access type for a published paper (Admin only).
    
    Allows admin to change a paper from 'subscription' to 'open' access or vice versa.
    By default, all papers are published with 'subscription' access.
    
    Args:
        paper_id: ID of the published paper
        access_update: New access type (subscription or open)
    
    Returns:
        Updated published paper details
    
    Raises:
        403: Admin access required
        404: Published paper not found
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    published_paper = db.query(PaperPublished).filter(PaperPublished.id == paper_id).first()
    
    if not published_paper:
        raise HTTPException(status_code=404, detail="Published paper not found")
    
    old_access = published_paper.access_type
    published_paper.access_type = access_update.access_type.value
    
    db.commit()
    db.refresh(published_paper)
    
    return {
        "success": True,
        "message": f"Access type updated from '{old_access}' to '{access_update.access_type.value}'",
        "paper": published_paper.to_dict()
    }


@router.patch("/published-papers/bulk-access")
@limiter.limit("20/minute")
async def bulk_update_access_type(
    request: Request,
    bulk_update: BulkAccessUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Bulk update access type for multiple published papers (Admin only).
    
    Args:
        bulk_update: List of paper IDs and new access type
    
    Returns:
        Summary of updated papers
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    updated_count = 0
    failed_ids = []
    
    for paper_id in bulk_update.paper_ids:
        published_paper = db.query(PaperPublished).filter(PaperPublished.id == paper_id).first()
        
        if published_paper:
            published_paper.access_type = bulk_update.access_type.value
            updated_count += 1
        else:
            failed_ids.append(paper_id)
    
    db.commit()
    
    return BulkAccessUpdateResponse(
        success=len(failed_ids) == 0,
        updated_count=updated_count,
        failed_ids=failed_ids,
        message=f"Updated {updated_count} papers to '{bulk_update.access_type.value}' access"
    )


@router.get("/published-papers")
@limiter.limit("200/minute")
async def list_published_papers(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    access_type: str = Query(None, description="Filter by access type (subscription, open)"),
    doi_status: str = Query(None, description="Filter by DOI status (pending, registered, failed)"),
    journal_id: int = Query(None, description="Filter by journal ID"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all published papers with filtering options (Admin only).
    
    Args:
        skip: Pagination offset
        limit: Number of records to return
        access_type: Filter by access type
        doi_status: Filter by DOI registration status
        journal_id: Filter by journal
    
    Returns:
        List of published papers with pagination info
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    query = db.query(PaperPublished)
    
    if access_type:
        query = query.filter(PaperPublished.access_type == access_type)
    
    if doi_status:
        query = query.filter(PaperPublished.doi_status == doi_status)
    
    if journal_id:
        query = query.filter(PaperPublished.journal_id == journal_id)
    
    total = query.count()
    papers = query.order_by(desc(PaperPublished.date)).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "papers": [paper.to_dict() for paper in papers]
    }


@router.get("/published-papers/{paper_id}")
@limiter.limit("200/minute")
async def get_published_paper_detail(
    request: Request,
    paper_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a published paper (Admin only).
    
    Args:
        paper_id: Published paper ID
    
    Returns:
        Complete published paper details including DOI info
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    published_paper = db.query(PaperPublished).filter(PaperPublished.id == paper_id).first()
    
    if not published_paper:
        raise HTTPException(status_code=404, detail="Published paper not found")
    
    # Get original submission if linked
    original_submission = None
    if published_paper.paper_submission_id:
        original = db.query(Paper).filter(Paper.id == published_paper.paper_submission_id).first()
        if original:
            original_submission = {
                "id": original.id,
                "paper_code": original.paper_code,
                "submitted_date": original.added_on.isoformat() if original.added_on else None,
                "status": original.status
            }
    
    paper_dict = published_paper.to_dict()
    paper_dict["doi_url"] = f"https://doi.org/{published_paper.doi}" if published_paper.doi else None
    paper_dict["original_submission"] = original_submission
    
    return paper_dict


@router.get("/doi-statistics")
@limiter.limit("100/minute")
async def get_doi_statistics(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get DOI registration statistics (Admin only).
    
    Returns:
        Summary of DOI registration statuses and access types
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # DOI status counts
    total_published = db.query(func.count(PaperPublished.id)).scalar() or 0
    doi_registered = db.query(func.count(PaperPublished.id)).filter(
        PaperPublished.doi_status == "registered"
    ).scalar() or 0
    doi_pending = db.query(func.count(PaperPublished.id)).filter(
        PaperPublished.doi_status == "pending"
    ).scalar() or 0
    doi_failed = db.query(func.count(PaperPublished.id)).filter(
        PaperPublished.doi_status == "failed"
    ).scalar() or 0
    no_doi = db.query(func.count(PaperPublished.id)).filter(
        PaperPublished.doi == None
    ).scalar() or 0
    
    # Access type counts
    subscription_access = db.query(func.count(PaperPublished.id)).filter(
        PaperPublished.access_type == "subscription"
    ).scalar() or 0
    open_access = db.query(func.count(PaperPublished.id)).filter(
        PaperPublished.access_type == "open"
    ).scalar() or 0
    
    return {
        "total_published": total_published,
        "doi_statistics": {
            "registered": doi_registered,
            "pending": doi_pending,
            "failed": doi_failed,
            "no_doi": no_doi
        },
        "access_statistics": {
            "subscription": subscription_access,
            "open": open_access
        }
    }


# ============================================================================
# EDITOR MANAGEMENT ENDPOINTS
# ============================================================================

from app.db.models import Editor

@router.get("/editors")
@limiter.limit("200/minute")
async def list_editors(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    journal_id: int = Query(None, description="Filter by journal ID"),
    editor_type: str = Query(None, description="Filter by editor type (chief_editor/section_editor)"),
    search: str = Query(None, description="Search by name or email"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all editor assignments with optional filtering.
    Uses user_role + user tables for the new multi-role system.
    
    Args:
        skip: Number of records to skip
        limit: Number of records to return
        journal_id: Filter by specific journal
        editor_type: Filter by editor type (chief_editor/section_editor)
        search: Search by editor name or email
        
    Returns:
        List of editor assignments with journal information
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Query user_role joined with user for editor roles
    query = db.query(UserRole, User).join(
        User, UserRole.user_id == User.id
    ).filter(
        UserRole.role == "editor",
        UserRole.status == "approved"
    )
    
    if journal_id:
        query = query.filter(UserRole.journal_id == journal_id)
    
    if editor_type:
        query = query.filter(UserRole.editor_type == editor_type)
    
    if search:
        query = query.filter(
            or_(
                func.concat(User.fname, ' ', User.lname).ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )
    
    total = query.count()
    results = query.order_by(desc(UserRole.requested_at)).offset(skip).limit(limit).all()
    
    # Transform to legacy format for backward compatibility
    editor_list = []
    for user_role, user in results:
        # Build editor dict in the format frontend expects
        editor_dict = {
            "id": user_role.id,  # Use user_role.id as the editor ID
            "user_id": user.id,
            "editor_name": f"{user.fname or ''} {user.lname or ''}".strip() or user.email,
            "editor_email": user.email,
            "journal_id": user_role.journal_id,
            "role": "Editor",
            "editor_type": user_role.editor_type or "section_editor",
            "editor_affiliation": user.affiliation,
            "editor_department": user.department,
            "editor_college": user.organisation,
            "editor_contact": user.contact,
            "added_on": user_role.requested_at.isoformat() if user_role.requested_at else None
        }
        
        # Enrich with journal information
        if user_role.journal_id:
            journal = db.query(Journal).filter(Journal.fld_id == user_role.journal_id).first()
            if journal:
                editor_dict["journal_name"] = journal.fld_journal_name
                editor_dict["journal_short_form"] = journal.short_form
        
        editor_list.append(editor_dict)
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "editors": editor_list
    }


@router.post("/editors")
@limiter.limit("100/minute")
async def create_editor(
    request: Request,
    editor_name: str = Body(..., embed=False),
    editor_email: str = Body(..., embed=False),
    journal_id: int = Body(..., embed=False),
    editor_type: str = Body("section_editor", embed=False),
    editor_affiliation: str = Body(None, embed=False),
    editor_department: str = Body(None, embed=False),
    editor_college: str = Body(None, embed=False),
    editor_contact: str = Body(None, embed=False),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new editor assignment for a journal.
    Uses user + user_role tables for the new multi-role system.
    
    Args:
        editor_name: Name of the editor
        editor_email: Email of the editor
        journal_id: Journal ID to assign
        editor_type: Type of editor (chief_editor/section_editor)
        editor_affiliation: Editor's affiliation (optional)
        editor_department: Editor's department (optional)
        editor_college: Editor's college (optional)
        editor_contact: Editor's contact (optional)
        
    Returns:
        Created editor assignment
    """
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Validate editor_type
    if editor_type not in ["chief_editor", "section_editor"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid editor_type. Must be 'chief_editor' or 'section_editor'"
        )
    
    # Verify journal exists
    journal = db.query(Journal).filter(Journal.fld_id == journal_id).first()
    if not journal:
        raise HTTPException(status_code=404, detail=f"Journal with ID {journal_id} not found")
    
    # Find or create user account
    user = db.query(User).filter(User.email == editor_email).first()
    
    if not user:
        # Create new user account
        name_parts = editor_name.split(' ', 1) if editor_name else ['', '']
        user = User(
            email=editor_email,
            password=pwd_context.hash("TempPassword123!"),
            role="Editor",
            fname=name_parts[0] if name_parts else None,
            lname=name_parts[1] if len(name_parts) > 1 else None,
            affiliation=editor_affiliation,
            department=editor_department,
            organisation=editor_college,
            contact=editor_contact,
            added_on=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    # Check if this user is already an editor for this journal
    existing_role = db.query(UserRole).filter(
        UserRole.user_id == user.id,
        UserRole.role == "editor",
        UserRole.journal_id == journal_id
    ).first()
    
    if existing_role:
        raise HTTPException(
            status_code=400,
            detail=f"Editor {editor_email} is already assigned to this journal"
        )
    
    # If assigning as chief_editor, check if journal already has one
    if editor_type == "chief_editor":
        existing_chief = db.query(UserRole, User).join(
            User, UserRole.user_id == User.id
        ).filter(
            UserRole.journal_id == journal_id,
            UserRole.role == "editor",
            UserRole.editor_type == "chief_editor",
            UserRole.status == "approved"
        ).first()
        
        if existing_chief:
            chief_user = existing_chief[1]
            chief_name = f"{chief_user.fname or ''} {chief_user.lname or ''}".strip() or chief_user.email
            raise HTTPException(
                status_code=400,
                detail=f"Journal already has a chief editor ({chief_name}). Remove them first or assign as section_editor."
            )
    
    # Create user_role entry for editor
    new_role = UserRole(
        user_id=user.id,
        role="editor",
        status="approved",
        requested_at=datetime.utcnow(),
        approved_at=datetime.utcnow(),
        approved_by=current_user.get("user_id"),
        journal_id=journal_id,
        editor_type=editor_type
    )
    
    db.add(new_role)
    db.commit()
    db.refresh(new_role)
    
    # Return result in legacy format for backward compatibility
    result = {
        "id": new_role.id,
        "user_id": user.id,
        "editor_name": f"{user.fname or ''} {user.lname or ''}".strip() or user.email,
        "editor_email": user.email,
        "journal_id": journal_id,
        "role": "Editor",
        "editor_type": editor_type,
        "editor_affiliation": user.affiliation,
        "editor_department": user.department,
        "editor_college": user.organisation,
        "editor_contact": user.contact,
        "added_on": new_role.requested_at.isoformat() if new_role.requested_at else None,
        "journal_name": journal.fld_journal_name,
        "journal_short_form": journal.short_form
    }
    
    return result


@router.get("/journals/{journal_id}/editors")
@limiter.limit("200/minute")
async def get_journal_editors(
    request: Request,
    journal_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all editors assigned to a specific journal.
    Uses user_role + user tables.
    
    Args:
        journal_id: Journal ID
        
    Returns:
        List of editors for the journal with their types
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Verify journal exists
    journal = db.query(Journal).filter(Journal.fld_id == journal_id).first()
    if not journal:
        raise HTTPException(status_code=404, detail=f"Journal with ID {journal_id} not found")
    
    # Query user_role joined with user for this journal's editors
    results = db.query(UserRole, User).join(
        User, UserRole.user_id == User.id
    ).filter(
        UserRole.journal_id == journal_id,
        UserRole.role == "editor",
        UserRole.status == "approved"
    ).order_by(
        # Chief editor first, then by name
        UserRole.editor_type.desc(),
        User.fname
    ).all()
    
    chief_editor = None
    co_editor = None
    section_editors = []
    
    for user_role, user in results:
        editor_dict = {
            "id": user_role.id,
            "user_id": user.id,
            "editor_name": f"{user.fname or ''} {user.lname or ''}".strip() or user.email,
            "editor_email": user.email,
            "journal_id": user_role.journal_id,
            "role": "Editor",
            "editor_type": user_role.editor_type or "section_editor",
            "editor_affiliation": user.affiliation,
            "editor_department": user.department,
            "editor_college": user.organisation,
            "editor_contact": user.contact,
            "added_on": user_role.requested_at.isoformat() if user_role.requested_at else None
        }
        
        if user_role.editor_type == "chief_editor":
            chief_editor = editor_dict
        elif user_role.editor_type == "co_editor":
            co_editor = editor_dict
        else:
            section_editors.append(editor_dict)
    
    return {
        "journal_id": journal_id,
        "journal_name": journal.fld_journal_name,
        "chief_editor": chief_editor,
        "co_editor": co_editor,
        "section_editors": section_editors,
        "total_editors": len(results)
    }


@router.put("/editors/{editor_id}")
@limiter.limit("100/minute")
async def update_editor(
    request: Request,
    editor_id: int,
    editor_name: str = Body(None),
    editor_type: str = Body(None),
    editor_affiliation: str = Body(None),
    editor_department: str = Body(None),
    editor_college: str = Body(None),
    editor_contact: str = Body(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an editor assignment.
    Uses user_role + user tables.
    
    Args:
        editor_id: UserRole ID (editor assignment)
        editor_name: Updated name (optional)
        editor_type: Updated type (optional)
        editor_affiliation: Updated affiliation (optional)
        editor_department: Updated department (optional)
        editor_college: Updated college (optional)
        editor_contact: Updated contact (optional)
        
    Returns:
        Updated editor assignment
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Find user_role entry
    user_role = db.query(UserRole).filter(
        UserRole.id == editor_id,
        UserRole.role == "editor"
    ).first()
    
    if not user_role:
        raise HTTPException(status_code=404, detail="Editor assignment not found")
    
    # Get associated user
    user = db.query(User).filter(User.id == user_role.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Associated user not found")
    
    # Validate editor_type if provided
    if editor_type and editor_type not in ["chief_editor", "section_editor"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid editor_type. Must be 'chief_editor' or 'section_editor'"
        )
    
    # If changing to chief_editor, check if journal already has one
    if editor_type == "chief_editor" and user_role.editor_type != "chief_editor":
        existing_chief = db.query(UserRole).filter(
            UserRole.journal_id == user_role.journal_id,
            UserRole.role == "editor",
            UserRole.editor_type == "chief_editor",
            UserRole.id != editor_id,
            UserRole.status == "approved"
        ).first()
        
        if existing_chief:
            chief_user = db.query(User).filter(User.id == existing_chief.user_id).first()
            chief_name = f"{chief_user.fname or ''} {chief_user.lname or ''}".strip() if chief_user else "Unknown"
            raise HTTPException(
                status_code=400,
                detail=f"Journal already has a chief editor ({chief_name})"
            )
    
    # Update user_role fields
    if editor_type is not None:
        user_role.editor_type = editor_type
    
    # Update user profile fields
    if editor_name is not None:
        name_parts = editor_name.split(' ', 1)
        user.fname = name_parts[0]
        user.lname = name_parts[1] if len(name_parts) > 1 else None
    if editor_affiliation is not None:
        user.affiliation = editor_affiliation
    if editor_department is not None:
        user.department = editor_department
    if editor_college is not None:
        user.organisation = editor_college
    if editor_contact is not None:
        user.contact = editor_contact
    
    db.commit()
    db.refresh(user_role)
    db.refresh(user)
    
    # Build result in legacy format
    result = {
        "id": user_role.id,
        "user_id": user.id,
        "editor_name": f"{user.fname or ''} {user.lname or ''}".strip() or user.email,
        "editor_email": user.email,
        "journal_id": user_role.journal_id,
        "role": "Editor",
        "editor_type": user_role.editor_type or "section_editor",
        "editor_affiliation": user.affiliation,
        "editor_department": user.department,
        "editor_college": user.organisation,
        "editor_contact": user.contact,
        "added_on": user_role.requested_at.isoformat() if user_role.requested_at else None
    }
    
    # Add journal info
    if user_role.journal_id:
        journal = db.query(Journal).filter(Journal.fld_id == user_role.journal_id).first()
        if journal:
            result["journal_name"] = journal.fld_journal_name
            result["journal_short_form"] = journal.short_form
    
    return result


@router.delete("/editors/{editor_id}")
@limiter.limit("100/minute")
async def delete_editor(
    request: Request,
    editor_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Remove an editor assignment.
    Uses user_role table.
    
    Args:
        editor_id: UserRole ID (editor assignment) to delete
        
    Returns:
        Confirmation message
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Find user_role entry
    user_role = db.query(UserRole).filter(
        UserRole.id == editor_id,
        UserRole.role == "editor"
    ).first()
    
    if not user_role:
        raise HTTPException(status_code=404, detail="Editor assignment not found")
    
    # Get user for display name
    user = db.query(User).filter(User.id == user_role.user_id).first()
    editor_name = f"{user.fname or ''} {user.lname or ''}".strip() if user else "Unknown"
    
    # Check if this is the last chief editor for the journal
    if user_role.editor_type == "chief_editor":
        # Count other editors for this journal
        other_editors = db.query(UserRole).filter(
            UserRole.journal_id == user_role.journal_id,
            UserRole.role == "editor",
            UserRole.status == "approved",
            UserRole.id != editor_id
        ).count()
        
        if other_editors == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot remove the only editor from a journal. Assign another editor first."
            )
    
    db.delete(user_role)
    db.commit()
    
    return {"message": f"Editor '{editor_name}' removed successfully"}


@router.post("/users/create")
@limiter.limit("50/minute")
async def create_admin_user(
    request: Request,
    email: str = Body(...),
    password: str = Body(...),
    fname: str = Body(...),
    lname: str = Body(None),
    role: str = Body("admin"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new user with specified role (Admin only).
    Useful for creating admin accounts directly.
    
    Args:
        email: User email
        password: User password
        fname: First name
        lname: Last name (optional)
        role: User role (admin, editor, author, reviewer)
        
    Returns:
        Created user information
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Validate role
    allowed_roles = ["admin", "editor", "author", "reviewer"]
    if role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Allowed: {allowed_roles}"
        )
    
    # Check if email already exists
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"User with email {email} already exists"
        )
    
    # Hash password
    from app.core.security import get_password_hash
    hashed_password = get_password_hash(password)
    
    # Create user
    new_user = User(
        email=email,
        password=hashed_password,
        fname=fname,
        lname=lname,
        role=role
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {
        "id": new_user.id,
        "email": new_user.email,
        "fname": new_user.fname,
        "lname": new_user.lname,
        "role": new_user.role,
        "message": f"User created successfully with role '{role}'"
    }


# ============================================================================
# NEWS / ANNOUNCEMENTS MANAGEMENT
# ============================================================================

@router.get("/news")
@limiter.limit("200/minute")
async def list_news(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    journal_id: int = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all news/announcements with optional filtering.
    
    Args:
        skip: Number of records to skip
        limit: Number of records to return
        journal_id: Filter by journal (optional)
        
    Returns:
        List of news items with pagination info
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    query = db.query(News)
    
    if journal_id:
        query = query.filter(News.journal_id == journal_id)
    
    total = query.count()
    news_items = query.order_by(News.added_on.desc()).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "news": [item.to_dict() for item in news_items]
    }


@router.post("/news")
@limiter.limit("50/minute")
async def create_news(
    request: Request,
    title: str = Body(..., min_length=1, max_length=300),
    description: str = Body(None),
    journal_id: int = Body(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new news/announcement item.
    
    Args:
        title: News title (required)
        description: News description/content
        journal_id: Associated journal ID (optional, for journal-specific news)
        
    Returns:
        Created news item
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Validate journal_id if provided
    if journal_id:
        journal = db.query(Journal).filter(Journal.fld_id == journal_id).first()
        if not journal:
            raise HTTPException(status_code=404, detail=f"Journal with ID {journal_id} not found")
    
    new_news = News(
        title=title,
        description=description,
        journal_id=journal_id,
        added_on=datetime.utcnow().date()
    )
    
    db.add(new_news)
    db.commit()
    db.refresh(new_news)
    
    return {
        "message": "News created successfully",
        "news": new_news.to_dict()
    }


@router.put("/news/{news_id}")
@limiter.limit("50/minute")
async def update_news(
    request: Request,
    news_id: int,
    title: str = Body(None, min_length=1, max_length=300),
    description: str = Body(None),
    journal_id: int = Body(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an existing news/announcement item.
    
    Args:
        news_id: ID of the news item to update
        title: New title (optional)
        description: New description (optional)
        journal_id: New journal ID (optional, use -1 to remove journal association)
        
    Returns:
        Updated news item
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    news_item = db.query(News).filter(News.id == news_id).first()
    if not news_item:
        raise HTTPException(status_code=404, detail=f"News item with ID {news_id} not found")
    
    if title is not None:
        news_item.title = title
    if description is not None:
        news_item.description = description
    if journal_id is not None:
        if journal_id == -1:
            news_item.journal_id = None
        else:
            journal = db.query(Journal).filter(Journal.fld_id == journal_id).first()
            if not journal:
                raise HTTPException(status_code=404, detail=f"Journal with ID {journal_id} not found")
            news_item.journal_id = journal_id
    
    db.commit()
    db.refresh(news_item)
    
    return {
        "message": "News updated successfully",
        "news": news_item.to_dict()
    }


@router.delete("/news/{news_id}")
@limiter.limit("50/minute")
async def delete_news(
    request: Request,
    news_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a news/announcement item.
    
    Args:
        news_id: ID of the news item to delete
        
    Returns:
        Success message
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    news_item = db.query(News).filter(News.id == news_id).first()
    if not news_item:
        raise HTTPException(status_code=404, detail=f"News item with ID {news_id} not found")
    
    db.delete(news_item)
    db.commit()
    
    return {"message": f"News item '{news_item.title}' deleted successfully"}


# ============================================================================
# EMAIL TEMPLATE ENDPOINTS
# ============================================================================

@router.get("/email-templates")
@limiter.limit("100/minute")
async def list_email_templates(
    request: Request,
    category: str = Query(None, description="Filter by category (submission, review, decision, general)"),
    is_active: bool = Query(None, description="Filter by active status"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all email templates for admin use.
    
    Args:
        category: Optional category filter
        is_active: Optional active status filter
        
    Returns:
        List of email templates
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    query = db.query(EmailTemplate)
    
    if category:
        query = query.filter(EmailTemplate.category == category)
    if is_active is not None:
        query = query.filter(EmailTemplate.is_active == is_active)
    
    templates = query.order_by(EmailTemplate.category, EmailTemplate.name).all()
    
    return {
        "templates": [t.to_dict() for t in templates],
        "total": len(templates)
    }


@router.get("/email-templates/{template_id}")
@limiter.limit("100/minute")
async def get_email_template(
    request: Request,
    template_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific email template by ID.
    
    Args:
        template_id: ID of the template
        
    Returns:
        Email template details
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    template = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Email template not found")
    
    return {"template": template.to_dict()}


@router.post("/email-templates")
@limiter.limit("50/minute")
async def create_email_template(
    request: Request,
    name: str = Body(...),
    slug: str = Body(...),
    subject: str = Body(...),
    body_template: str = Body(...),
    category: str = Body(...),
    placeholders: list = Body(default=[]),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new email template.
    
    Args:
        name: Template display name
        slug: Unique identifier slug
        subject: Email subject line (supports {{placeholders}})
        body_template: Email body (supports {{placeholders}})
        category: Template category (submission, review, decision, general)
        placeholders: List of placeholder names used in template
        
    Returns:
        Created email template
    """
    import json
    
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Check if slug already exists
    existing = db.query(EmailTemplate).filter(EmailTemplate.slug == slug).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Template with slug '{slug}' already exists")
    
    template = EmailTemplate(
        name=name,
        slug=slug,
        subject=subject,
        body_template=body_template,
        category=category,
        placeholders=json.dumps(placeholders) if placeholders else None,
        is_active=True
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    
    return {
        "message": "Email template created successfully",
        "template": template.to_dict()
    }


@router.put("/email-templates/{template_id}")
@limiter.limit("50/minute")
async def update_email_template(
    request: Request,
    template_id: int,
    name: str = Body(None),
    subject: str = Body(None),
    body_template: str = Body(None),
    category: str = Body(None),
    placeholders: list = Body(None),
    is_active: bool = Body(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an existing email template.
    
    Args:
        template_id: ID of the template to update
        name, subject, body_template, category, placeholders, is_active: Fields to update
        
    Returns:
        Updated email template
    """
    import json
    
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    template = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Email template not found")
    
    if name is not None:
        template.name = name
    if subject is not None:
        template.subject = subject
    if body_template is not None:
        template.body_template = body_template
    if category is not None:
        template.category = category
    if placeholders is not None:
        template.placeholders = json.dumps(placeholders)
    if is_active is not None:
        template.is_active = is_active
    
    db.commit()
    db.refresh(template)
    
    return {
        "message": "Email template updated successfully",
        "template": template.to_dict()
    }


# ============================================================================
# PAPER CORRESPONDENCE ENDPOINTS
# ============================================================================

@router.get("/papers/{paper_id}/correspondence")
@limiter.limit("100/minute")
async def get_paper_correspondence(
    request: Request,
    paper_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all correspondence for a paper (admin view).
    
    Args:
        paper_id: ID of the paper
        
    Returns:
        List of correspondence items with sender details
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Verify paper exists
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    correspondence = db.query(PaperCorrespondence).filter(
        PaperCorrespondence.paper_id == paper_id
    ).order_by(desc(PaperCorrespondence.sent_at)).all()
    
    result = []
    for corr in correspondence:
        corr_dict = corr.to_dict()
        # Add sender info
        if corr.sender_id:
            sender = db.query(User).filter(User.id == corr.sender_id).first()
            if sender:
                corr_dict["sender_name"] = sender.name
                corr_dict["sender_email"] = sender.email
        result.append(corr_dict)
    
    return {
        "correspondence": result,
        "total": len(result),
        "paper_id": paper_id,
        "paper_title": paper.title
    }


@router.post("/papers/{paper_id}/correspondence")
@limiter.limit("30/minute")
async def send_paper_correspondence(
    request: Request,
    paper_id: int,
    template_id: int = Body(None, description="Email template ID to use"),
    subject: str = Body(None, description="Custom subject (overrides template)"),
    message: str = Body(None, description="Custom message (overrides template)"),
    placeholders: dict = Body(default={}, description="Placeholder values for template"),
    send_email: bool = Body(default=True, description="Whether to send actual email"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send correspondence to a paper's author(s).
    
    Can use an email template or custom subject/message.
    Supports placeholder substitution in templates.
    
    Args:
        paper_id: ID of the paper
        template_id: Optional email template ID
        subject: Custom subject (required if no template)
        message: Custom message (required if no template)
        placeholders: Dict of placeholder values for template substitution
        send_email: Whether to actually send the email (default True)
        
    Returns:
        Created correspondence record
    """
    import re
    
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Verify paper exists and get author info
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    author = db.query(User).filter(User.id == paper.author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Paper author not found")
    
    # Get journal info
    journal = db.query(Journal).filter(Journal.fld_id == paper.journal_id).first()
    journal_name = journal.fld_name if journal else "Breakthrough Publishers India Journal"
    
    # Prepare subject and message
    final_subject = subject
    final_message = message
    template = None
    
    if template_id:
        template = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Email template not found")
        
        final_subject = template.subject
        final_message = template.body_template
    
    if not final_subject or not final_message:
        raise HTTPException(
            status_code=400, 
            detail="Either template_id or both subject and message are required"
        )
    
    # Default placeholders
    default_placeholders = {
        "author_name": author.name,
        "paper_title": paper.title,
        "paper_id": str(paper.id),
        "journal_name": journal_name,
        "sender_name": current_user.get("name", "Admin"),
        "current_status": paper.status
    }
    
    # Merge with provided placeholders (provided values take precedence)
    all_placeholders = {**default_placeholders, **placeholders}
    
    # Substitute placeholders in subject and message
    def substitute_placeholders(text, values):
        for key, value in values.items():
            text = re.sub(r'\{\{' + key + r'\}\}', str(value or ''), text, flags=re.IGNORECASE)
        return text
    
    final_subject = substitute_placeholders(final_subject, all_placeholders)
    final_message = substitute_placeholders(final_message, all_placeholders)
    
    # Create correspondence record
    correspondence = PaperCorrespondence(
        paper_id=paper_id,
        sender_id=current_user.get("id"),
        sender_role="admin",
        template_id=template_id,
        subject=final_subject,
        message=final_message,
        sent_at=datetime.utcnow(),
        is_read=False
    )
    
    db.add(correspondence)
    db.commit()
    db.refresh(correspondence)
    
    # Send actual email if requested
    email_sent = False
    if send_email:
        try:
            from app.services.correspondence_service import send_simple_email
            email_sent = send_simple_email(
                recipient_email=author.email,
                recipient_name=author.name,
                subject=final_subject,
                message=final_message,
                paper_title=paper.title,
                paper_id=paper.id
            )
        except Exception as e:
            # Log error but don't fail - correspondence is still recorded
            print(f"Email sending failed: {e}")
    
    return {
        "message": "Correspondence sent successfully",
        "correspondence": correspondence.to_dict(),
        "email_sent": email_sent,
        "recipient": {
            "name": author.name,
            "email": author.email
        }
    }