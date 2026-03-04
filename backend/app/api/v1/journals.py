"""Journal API endpoints"""
from fastapi import APIRouter, Depends, status, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
import re
from app.db.database import get_db
from app.db.models import Journal, JournalDetails, Volume, Issue, PaperPublished, Editor, User, UserRole
from app.core.security import get_current_user
from app.utils.auth_helpers import check_role
from app.schemas.journal import (
    JournalRequest, JournalResponse, JournalListResponse,
    JournalDetailRequest, JournalDetailResponse,
    JournalRecommendationRequest, JournalRecommendationResponse, JournalRecommendationItem
)
from app.services.journal_recommendation_service import JournalRecommendationService
from typing import List, Optional
from datetime import date

router = APIRouter(prefix="/api/v1/journals", tags=["Journals"])


def strip_html_tags(text: str) -> str:
    """Remove HTML tags from text and clean up whitespace"""
    if not text:
        return text
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', text)
    # Replace multiple whitespace/newlines with single space
    clean = re.sub(r'\s+', ' ', clean)
    # Strip leading/trailing whitespace
    return clean.strip()


@router.get(
    "/",
    response_model=List[JournalListResponse],
    status_code=status.HTTP_200_OK,
    summary="List all journals",
    description="Retrieve a list of all available journals with basic information"
)
async def list_journals(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of journals to skip"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of journals to return")
):
    """
    Get all journals with pagination support.
    
    - **skip**: Number of journals to skip (default: 0)
    - **limit**: Maximum number of journals to return (default: 10, max: 100)
    """
    journals = db.query(Journal).offset(skip).limit(limit).all()
    return [
        JournalListResponse(
            id=j.fld_id,
            name=j.fld_journal_name,
            short_form=j.short_form,
            issn_online=j.issn_ol,
            issn_print=j.issn_prt,
            chief_editor=j.cheif_editor,
            co_editor=j.co_editor,
            journal_logo=j.journal_logo,
            description=j.description
        )
        for j in journals
    ]


@router.get(
    "/by-subdomain/{short_form}",
    response_model=JournalResponse,
    status_code=status.HTTP_200_OK,
    summary="Get journal by short form",
    description="Retrieve journal information using its short_form identifier"
)
async def get_journal_by_short_form(short_form: str, db: Session = Depends(get_db)):
    """
    Get a journal by its short_form.
    
    - **short_form**: The journal's short_form (e.g., 'ijest', 'ijrm')
    
    This endpoint is used when accessing journal pages via routing
    (e.g., /j/ijest) to identify which journal to display.
    """
    journal = db.query(Journal).filter(
        Journal.short_form.ilike(short_form)
    ).first()
    
    if not journal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal with short_form '{short_form}' not found"
        )
    
    return JournalResponse(
        id=journal.fld_id,
        name=journal.fld_journal_name,
        primary_category=journal.fld_primary_category,
        frequency=journal.freq,
        issn_online=journal.issn_ol,
        issn_print=journal.issn_prt,
        chief_editor=journal.cheif_editor,
        co_editor=journal.co_editor,
        abstract_indexing=journal.abs_ind,
        short_form=journal.short_form,
        journal_image=journal.journal_image,
        journal_logo=journal.journal_logo,
        guidelines=journal.guidelines,
        copyright=journal.copyright,
        membership=journal.membership,
        subscription=journal.subscription,
        publication=journal.publication,
        advertisement=journal.advertisement,
        description=journal.description,
        added_on=journal.added_on.isoformat() if journal.added_on else None
    )


@router.get(
    "/{journal_id}",
    response_model=JournalResponse,
    status_code=status.HTTP_200_OK,
    summary="Get journal details",
    description="Retrieve detailed information about a specific journal"
)
async def get_journal(journal_id: int, db: Session = Depends(get_db)):
    """
    Get a specific journal by ID with all details.
    
    - **journal_id**: The journal ID
    """
    journal = db.query(Journal).filter(Journal.fld_id == journal_id).first()
    if not journal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal with ID {journal_id} not found"
        )
    return JournalResponse(
        id=journal.fld_id,
        name=journal.fld_journal_name,
        primary_category=journal.fld_primary_category,
        frequency=journal.freq,
        issn_online=journal.issn_ol,
        issn_print=journal.issn_prt,
        chief_editor=journal.cheif_editor,
        co_editor=journal.co_editor,
        abstract_indexing=journal.abs_ind,
        short_form=journal.short_form,
        journal_image=journal.journal_image,
        journal_logo=journal.journal_logo,
        guidelines=journal.guidelines,
        copyright=journal.copyright,
        membership=journal.membership,
        subscription=journal.subscription,
        publication=journal.publication,
        advertisement=journal.advertisement,
        description=journal.description,
        added_on=journal.added_on.isoformat() if journal.added_on else None
    )


@router.get(
    "/{journal_id}/details",
    response_model=JournalDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get journal extended details",
    description="Retrieve extended details (about, guidelines, scope, etc.) for a journal"
)
async def get_journal_details(journal_id: int, db: Session = Depends(get_db)):
    """
    Get extended details for a specific journal.
    
    - **journal_id**: The journal ID
    """
    # First check if journal exists
    journal = db.query(Journal).filter(Journal.fld_id == journal_id).first()
    if not journal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal with ID {journal_id} not found"
        )
    
    # Get journal details
    journal_detail = db.query(JournalDetails).filter(
        JournalDetails.journal_id == str(journal_id)
    ).first()
    
    if not journal_detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Details for journal {journal_id} not found"
        )
    
    return JournalDetailResponse(
        id=journal_detail.id,
        journal_id=journal_detail.journal_id,
        about_journal=journal_detail.about_journal,
        chief_say=journal_detail.cheif_say,
        aim_objective=journal_detail.aim_objective,
        criteria=journal_detail.criteria,
        scope=journal_detail.scope,
        guidelines=journal_detail.guidelines,
        readings=journal_detail.readings,
        added_on=journal_detail.added_on.isoformat() if journal_detail.added_on else None
    )


@router.post(
    "/recommend",
    response_model=JournalRecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get journal recommendations",
    description="Get journal recommendations based on paper keywords and abstract"
)
async def get_journal_recommendations(
    data: JournalRecommendationRequest,
    db: Session = Depends(get_db)
):
    """
    Get journal recommendations for authors based on their paper's keywords and abstract.
    
    - **research_area**: Research area/category (required for filtering)
    - **keywords**: List of keywords (minimum 5 required)
    - **abstract**: Paper abstract (optional but improves accuracy)
    
    Returns up to 3 highly relevant journal recommendations with match reasons.
    """
    if len(data.keywords) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 5 keywords are required for accurate recommendations"
        )
    
    # Initialize recommendation service
    recommendation_service = JournalRecommendationService(db)
    
    # Get recommendations
    recommendations = recommendation_service.get_recommendations(
        research_area=data.research_area,
        keywords=data.keywords,
        abstract=data.abstract or ""
    )
    
    # Convert to response format
    recommendation_items = [
        JournalRecommendationItem(
            journal_id=rec["journal_id"],
            journal_name=rec["journal_name"],
            score=rec["score"],
            is_recommended=rec["is_recommended"],
            match_reason=rec["match_reason"]
        )
        for rec in recommendations
    ]
    
    return JournalRecommendationResponse(
        recommendations=recommendation_items,
        total=len(recommendation_items)
    )


@router.post(
    "/",
    response_model=JournalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new journal",
    description="Create a new journal (admin only)"
)
async def create_journal(
    data: JournalRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new journal.
    
    Requires all mandatory fields. This is an admin-only operation.
    """
    # Verify admin access
    if not check_role(current_user.get("role"), "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    # Check if journal with same name already exists
    existing = db.query(Journal).filter(
        Journal.fld_journal_name == data.fld_journal_name
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Journal '{data.fld_journal_name}' already exists"
        )
    
    # Create new journal
    new_journal = Journal(
        fld_journal_name=data.fld_journal_name,
        fld_primary_category=data.primary_category,
        freq=data.freq,
        issn_ol=data.issn_ol,
        issn_prt=data.issn_prt,
        cheif_editor=data.cheif_editor,
        co_editor=data.co_editor,
        password=data.password,
        abs_ind=data.abs_ind,
        short_form=data.short_form,
        journal_image=data.journal_image,
        journal_logo=data.journal_logo,
        guidelines=data.guidelines,
        copyright=data.copyright,
        membership=data.membership,
        subscription=data.subscription,
        publication=data.publication,
        advertisement=data.advertisement,
        description=data.description,
        added_on=date.today()
    )
    
    db.add(new_journal)
    db.commit()
    db.refresh(new_journal)
    
    # Assign chief editor if provided (using user_role table)
    if data.chief_editor_id:
        # chief_editor_id is now a user_role ID
        chief_role = db.query(UserRole).filter(
            UserRole.id == data.chief_editor_id,
            UserRole.role == "editor"
        ).first()
        if chief_role:
            chief_role.journal_id = new_journal.fld_id
            chief_role.editor_type = 'chief_editor'
            db.commit()
    
    # Assign co-editor if provided (using user_role table)
    if data.co_editor_id:
        co_role = db.query(UserRole).filter(
            UserRole.id == data.co_editor_id,
            UserRole.role == "editor"
        ).first()
        if co_role:
            co_role.journal_id = new_journal.fld_id
            co_role.editor_type = 'co_editor'
            db.commit()
    
    # Assign section editors if provided (using user_role table)
    if data.section_editor_ids:
        for role_id in data.section_editor_ids:
            # section_editor_ids are now user_role IDs
            section_role = db.query(UserRole).filter(
                UserRole.id == role_id,
                UserRole.role == "editor"
            ).first()
            if section_role:
                section_role.journal_id = new_journal.fld_id
                section_role.editor_type = 'section_editor'
        db.commit()
    
    # Create JournalDetails if any detail fields are provided
    if any([data.about_journal, data.chief_say, data.aim_objective, 
            data.criteria, data.scope, data.detailed_guidelines, data.readings]):
        journal_details = JournalDetails(
            journal_id=str(new_journal.fld_id),
            about_journal=data.about_journal,
            cheif_say=data.chief_say,
            aim_objective=data.aim_objective,
            criteria=data.criteria,
            scope=data.scope,
            guidelines=data.detailed_guidelines,
            readings=data.readings,
            added_on=datetime.utcnow()
        )
        db.add(journal_details)
        db.commit()
    
    return JournalResponse(
        id=new_journal.fld_id,
        name=new_journal.fld_journal_name,
        primary_category=new_journal.fld_primary_category,
        frequency=new_journal.freq,
        issn_online=new_journal.issn_ol,
        issn_print=new_journal.issn_prt,
        chief_editor=new_journal.cheif_editor,
        co_editor=new_journal.co_editor,
        abstract_indexing=new_journal.abs_ind,
        short_form=new_journal.short_form,
        journal_image=new_journal.journal_image,
        journal_logo=new_journal.journal_logo,
        guidelines=new_journal.guidelines,
        copyright=new_journal.copyright,
        membership=new_journal.membership,
        subscription=new_journal.subscription,
        publication=new_journal.publication,
        advertisement=new_journal.advertisement,
        description=new_journal.description,
        added_on=new_journal.added_on.isoformat() if new_journal.added_on else None
    )


@router.put(
    "/{journal_id}",
    response_model=JournalResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a journal",
    description="Update journal information (admin only)"
)
async def update_journal(
    journal_id: int,
    data: JournalRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing journal.
    
    - **journal_id**: The journal ID to update
    
    Admin-only operation.
    """
    # Verify admin access
    if not check_role(current_user.get("role"), "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    journal = db.query(Journal).filter(Journal.fld_id == journal_id).first()
    if not journal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal with ID {journal_id} not found"
        )
    
    # Update fields - only update if provided, otherwise keep existing values
    journal.fld_journal_name = data.fld_journal_name
    journal.fld_primary_category = data.primary_category if data.primary_category is not None else journal.fld_primary_category
    journal.freq = data.freq if data.freq is not None else journal.freq
    journal.issn_ol = data.issn_ol if data.issn_ol is not None else journal.issn_ol
    journal.issn_prt = data.issn_prt if data.issn_prt is not None else journal.issn_prt
    journal.cheif_editor = data.cheif_editor if data.cheif_editor is not None else journal.cheif_editor
    journal.co_editor = data.co_editor if data.co_editor is not None else journal.co_editor
    journal.password = data.password
    journal.abs_ind = data.abs_ind if data.abs_ind is not None else journal.abs_ind
    journal.short_form = data.short_form
    journal.journal_image = data.journal_image if data.journal_image is not None else journal.journal_image
    journal.journal_logo = data.journal_logo if data.journal_logo is not None else journal.journal_logo
    journal.guidelines = data.guidelines if data.guidelines is not None else journal.guidelines
    journal.copyright = data.copyright if data.copyright is not None else journal.copyright
    journal.membership = data.membership if data.membership is not None else journal.membership
    journal.subscription = data.subscription if data.subscription is not None else journal.subscription
    journal.publication = data.publication if data.publication is not None else journal.publication
    journal.advertisement = data.advertisement if data.advertisement is not None else journal.advertisement
    journal.description = data.description if data.description is not None else journal.description
    
    db.commit()
    db.refresh(journal)
    
    # Update or create JournalDetails if any detail fields are provided
    if any([data.about_journal, data.chief_say, data.aim_objective, 
            data.criteria, data.scope, data.detailed_guidelines, data.readings]):
        journal_details = db.query(JournalDetails).filter(
            JournalDetails.journal_id == str(journal_id)
        ).first()
        
        if journal_details:
            # Update existing details
            if data.about_journal is not None:
                journal_details.about_journal = data.about_journal
            if data.chief_say is not None:
                journal_details.cheif_say = data.chief_say
            if data.aim_objective is not None:
                journal_details.aim_objective = data.aim_objective
            if data.criteria is not None:
                journal_details.criteria = data.criteria
            if data.scope is not None:
                journal_details.scope = data.scope
            if data.detailed_guidelines is not None:
                journal_details.guidelines = data.detailed_guidelines
            if data.readings is not None:
                journal_details.readings = data.readings
        else:
            # Create new details
            journal_details = JournalDetails(
                journal_id=str(journal_id),
                about_journal=data.about_journal,
                cheif_say=data.chief_say,
                aim_objective=data.aim_objective,
                criteria=data.criteria,
                scope=data.scope,
                guidelines=data.detailed_guidelines,
                readings=data.readings,
                added_on=datetime.utcnow()
            )
            db.add(journal_details)
        
        db.commit()
    
    return JournalResponse(
        id=journal.fld_id,
        name=journal.fld_journal_name,
        primary_category=journal.fld_primary_category,
        frequency=journal.freq,
        issn_online=journal.issn_ol,
        issn_print=journal.issn_prt,
        chief_editor=journal.cheif_editor,
        co_editor=journal.co_editor,
        abstract_indexing=journal.abs_ind,
        short_form=journal.short_form,
        journal_image=journal.journal_image,
        journal_logo=journal.journal_logo,
        guidelines=journal.guidelines,
        copyright=journal.copyright,
        membership=journal.membership,
        subscription=journal.subscription,
        publication=journal.publication,
        advertisement=journal.advertisement,
        description=journal.description,
        added_on=journal.added_on.isoformat() if journal.added_on else None
    )


@router.delete(
    "/{journal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a journal",
    description="Delete a journal (admin only)"
)
async def delete_journal(
    journal_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a specific journal.
    
    - **journal_id**: The journal ID to delete
    
    Admin-only operation.
    """
    # Verify admin access
    if not check_role(current_user.get("role"), "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    journal = db.query(Journal).filter(Journal.fld_id == journal_id).first()
    if not journal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal with ID {journal_id} not found"
        )
    
    # Also delete associated journal details
    db.query(JournalDetails).filter(JournalDetails.journal_id == str(journal_id)).delete()
    
    db.delete(journal)
    db.commit()
    
    return None


# ============================================================================
# VOLUME AND ISSUE ENDPOINTS
# ============================================================================

@router.get(
    "/{journal_id}/volumes",
    status_code=status.HTTP_200_OK,
    summary="Get journal volumes",
    description="Retrieve all volumes for a specific journal"
)
async def get_journal_volumes(
    journal_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all volumes for a specific journal, ordered by volume number descending.
    
    - **journal_id**: The journal ID
    
    Returns list of volumes with their issues count.
    """
    # Verify journal exists
    journal = db.query(Journal).filter(Journal.fld_id == journal_id).first()
    if not journal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal with ID {journal_id} not found"
        )
    
    # Get volumes for this journal (journal field stores journal_id as string)
    volumes = db.query(Volume).filter(
        Volume.journal == str(journal_id)
    ).order_by(desc(Volume.volume_no)).all()
    
    volumes_list = []
    for vol in volumes:
        # Count issues in this volume
        issue_count = db.query(Issue).filter(
            Issue.volume == vol.id
        ).count()
        
        volumes_list.append({
            "id": vol.id,
            "volume_no": vol.volume_no,
            "year": vol.year,
            "issue_count": issue_count,
            "added_on": vol.added_on.isoformat() if vol.added_on else None
        })
    
    return {
        "journal_id": journal_id,
        "journal_name": journal.fld_journal_name,
        "total_volumes": len(volumes_list),
        "volumes": volumes_list
    }


@router.get(
    "/{journal_id}/volumes/{volume_no}/issues",
    status_code=status.HTTP_200_OK,
    summary="Get volume issues",
    description="Retrieve all issues for a specific volume"
)
async def get_volume_issues(
    journal_id: int,
    volume_no: int,
    db: Session = Depends(get_db)
):
    """
    Get all issues for a specific volume.
    
    - **journal_id**: The journal ID
    - **volume_no**: The volume number
    
    Returns list of issues with article counts.
    """
    # Verify journal exists
    journal = db.query(Journal).filter(Journal.fld_id == journal_id).first()
    if not journal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal with ID {journal_id} not found"
        )
    
    # Verify volume exists and belongs to this journal (using volume_no, not id)
    volume = db.query(Volume).filter(
        Volume.volume_no == volume_no,
        Volume.journal == str(journal_id)
    ).first()
    if not volume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Volume {volume_no} not found for this journal"
        )
    
    # Get issues for this volume (using volume.id as foreign key reference)
    issues = db.query(Issue).filter(
        Issue.volume == volume.id
    ).order_by(Issue.issue_no).all()
    
    issues_list = []
    for issue in issues:
        # Count published papers in this issue
        paper_count = db.query(PaperPublished).filter(
            PaperPublished.journal_id == journal_id,
            PaperPublished.volume == str(volume.volume_no),
            PaperPublished.issue == str(issue.issue_no)
        ).count()
        
        issues_list.append({
            "id": issue.id,
            "issue_no": issue.issue_no,
            "month": issue.month,
            "pages": issue.pages,
            "paper_count": paper_count,
            "complete_issue": issue.complete_issue
        })
    
    return {
        "journal_id": journal_id,
        "journal_name": journal.fld_journal_name,
        "volume_id": volume.id,
        "volume_no": volume.volume_no,
        "year": volume.year,
        "total_issues": len(issues_list),
        "issues": issues_list
    }


@router.get(
    "/{journal_id}/issues",
    status_code=status.HTTP_200_OK,
    summary="Get all journal issues",
    description="Retrieve all issues for a journal with volume information"
)
async def get_all_journal_issues(
    journal_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all issues for a journal, grouped by volume.
    
    - **journal_id**: The journal ID
    
    Returns hierarchical structure of volumes and their issues.
    """
    # Verify journal exists
    journal = db.query(Journal).filter(Journal.fld_id == journal_id).first()
    if not journal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal with ID {journal_id} not found"
        )
    
    # Get all volumes for this journal
    volumes = db.query(Volume).filter(
        Volume.journal == str(journal_id)
    ).order_by(desc(Volume.volume_no)).all()
    
    result = []
    for vol in volumes:
        # Get issues for this volume
        issues = db.query(Issue).filter(
            Issue.volume == vol.id
        ).order_by(Issue.issue_no).all()
        
        issues_list = []
        for issue in issues:
            # Count published papers in this issue
            paper_count = db.query(PaperPublished).filter(
                PaperPublished.journal_id == journal_id,
                PaperPublished.volume == str(vol.volume_no),
                PaperPublished.issue == str(issue.issue_no)
            ).count()
            
            issues_list.append({
                "id": issue.id,
                "issue_no": issue.issue_no,
                "month": issue.month,
                "pages": issue.pages,
                "paper_count": paper_count,
                "complete_issue": issue.complete_issue
            })
        
        result.append({
            "volume_id": vol.id,
            "volume_no": vol.volume_no,
            "year": vol.year,
            "issues": issues_list
        })
    
    return {
        "journal_id": journal_id,
        "journal_name": journal.fld_journal_name,
        "journal_short": journal.short_form,
        "volumes": result
    }


@router.get(
    "/{journal_id}/issues/{volume_no}/{issue_no}/papers",
    status_code=status.HTTP_200_OK,
    summary="Get papers in an issue",
    description="Retrieve all published papers in a specific issue"
)
async def get_issue_papers(
    journal_id: int,
    volume_no: int,
    issue_no: int,
    db: Session = Depends(get_db)
):
    """
    Get all published papers in a specific issue.
    
    - **journal_id**: The journal ID
    - **volume_no**: The volume number
    - **issue_no**: The issue number
    
    Returns list of published papers with metadata.
    """
    # Verify journal exists
    journal = db.query(Journal).filter(Journal.fld_id == journal_id).first()
    if not journal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal with ID {journal_id} not found"
        )
    
    # Get volume info for the year
    volume = db.query(Volume).filter(
        Volume.journal == str(journal_id),
        Volume.volume_no == volume_no
    ).first()
    
    if not volume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Volume {volume_no} not found for journal {journal_id}"
        )
    
    # Get issue info
    issue = db.query(Issue).filter(
        Issue.volume == volume.id,
        Issue.issue_no == issue_no
    ).first()
    
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Issue {issue_no} not found in volume {volume_no}"
        )
    
    # Get published papers - note: paper_published stores volume.id and issue.id as strings
    papers = db.query(PaperPublished).filter(
        PaperPublished.journal_id == journal_id,
        PaperPublished.volume == str(volume.id),
        PaperPublished.issue == str(issue.id)
    ).order_by(PaperPublished.pages).all()
    
    papers_list = []
    for paper in papers:
        # Strip HTML tags and clean up text
        clean_title = strip_html_tags(paper.title)
        clean_abstract = strip_html_tags(paper.abstract)
        clean_author = strip_html_tags(paper.author)
        clean_keyword = strip_html_tags(paper.keyword)
        clean_pages = strip_html_tags(paper.pages) if paper.pages else None
        clean_doi = strip_html_tags(paper.doi) if paper.doi else None
        
        # Truncate abstract if needed
        if clean_abstract and len(clean_abstract) > 300:
            clean_abstract = clean_abstract[:300] + "..."
        
        papers_list.append({
            "id": paper.id,
            "title": clean_title,
            "author": clean_author,
            "abstract": clean_abstract,
            "pages": clean_pages,
            "doi": clean_doi,
            "doi_url": f"https://doi.org/{clean_doi}" if clean_doi else None,
            "access_type": paper.access_type,
            "keyword": clean_keyword,
            "date": paper.date.isoformat() if paper.date else None
        })
    
    return {
        "journal_id": journal_id,
        "journal_name": journal.fld_journal_name,
        "volume_no": volume_no,
        "year": volume.year if volume else None,
        "issue_no": issue_no,
        "month": issue.month if issue else None,
        "total_papers": len(papers_list),
        "papers": papers_list
    }
