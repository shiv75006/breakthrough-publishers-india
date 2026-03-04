"""Pydantic schemas for journal-related requests and responses"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import date, datetime


class JournalDetailRequest(BaseModel):
    """Journal details request schema"""
    about_journal: Optional[str] = Field(None, description="About the journal")
    chief_say: Optional[str] = Field(None, description="Chief editor's statement")
    aim_objective: Optional[str] = Field(None, description="Aims and objectives")
    criteria: Optional[str] = Field(None, description="Publication criteria")
    scope: Optional[str] = Field(None, description="Journal scope")
    guidelines: Optional[str] = Field(None, description="Submission guidelines")
    readings: Optional[str] = Field(None, description="Recommended readings")


class JournalDetailResponse(BaseModel):
    """Journal details response schema"""
    id: int = Field(..., description="Detail ID")
    journal_id: str = Field(..., description="Journal ID")
    about_journal: Optional[str] = Field(None, description="About the journal")
    chief_say: Optional[str] = Field(None, description="Chief editor's statement")
    aim_objective: Optional[str] = Field(None, description="Aims and objectives")
    criteria: Optional[str] = Field(None, description="Publication criteria")
    scope: Optional[str] = Field(None, description="Journal scope")
    guidelines: Optional[str] = Field(None, description="Submission guidelines")
    readings: Optional[str] = Field(None, description="Recommended readings")
    added_on: Optional[str] = Field(None, description="Added date")
    
    class Config:
        from_attributes = True


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


class JournalRequest(BaseModel):
    """Journal request schema for create/update"""
    fld_journal_name: str = Field(..., min_length=1, max_length=200, description="Journal name")
    primary_category: Optional[str] = Field(None, max_length=100, description="Primary research category")
    freq: Optional[str] = Field(None, max_length=250, description="Publication frequency")
    issn_ol: Optional[str] = Field(None, max_length=250, description="ISSN Online")
    issn_prt: Optional[str] = Field(None, max_length=250, description="ISSN Print")
    cheif_editor: Optional[str] = Field(None, max_length=250, description="Chief editor name")
    co_editor: Optional[str] = Field(None, max_length=250, description="Co-editor name")
    password: str = Field(..., min_length=1, max_length=100, description="Journal password")
    abs_ind: Optional[str] = Field(None, max_length=300, description="Abstract indexing services")
    short_form: str = Field(..., min_length=1, max_length=255, description="Journal short form/abbreviation")
    journal_image: Optional[str] = Field(None, max_length=255, description="Journal image path")
    journal_logo: Optional[str] = Field(None, max_length=200, description="Journal logo path")
    guidelines: Optional[str] = Field(None, max_length=500, description="Guidelines URL/path")
    copyright: Optional[str] = Field(None, max_length=200, description="Copyright info URL/path")
    membership: Optional[str] = Field(None, max_length=200, description="Membership URL/path")
    subscription: Optional[str] = Field(None, max_length=200, description="Subscription URL/path")
    publication: Optional[str] = Field(None, max_length=200, description="Publication policy URL/path")
    advertisement: Optional[str] = Field(None, max_length=200, description="Advertisement URL/path")
    description: Optional[str] = Field(None, description="Journal description")
    chief_editor_id: Optional[int] = Field(None, description="ID of the chief editor to assign")
    co_editor_id: Optional[int] = Field(None, description="ID of the co-editor to assign")
    section_editor_ids: Optional[List[int]] = Field(None, description="List of section editor IDs to assign")
    # Journal details fields
    about_journal: Optional[str] = Field(None, description="About the journal (HTML content)")
    chief_say: Optional[str] = Field(None, description="Chief editor's statement (HTML content)")
    aim_objective: Optional[str] = Field(None, description="Aims and objectives (HTML content)")
    criteria: Optional[str] = Field(None, description="Publication criteria (HTML content)")
    scope: Optional[str] = Field(None, description="Journal scope (HTML content)")
    detailed_guidelines: Optional[str] = Field(None, description="Detailed submission guidelines (HTML content)")
    readings: Optional[str] = Field(None, description="Recommended readings (HTML content)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "fld_journal_name": "International Journal of Computer Science",
                "freq": "Quarterly",
                "issn_ol": "2395-0056",
                "issn_prt": "2395-0064",
                "cheif_editor": "Dr. John Smith",
                "co_editor": "Dr. Jane Doe",
                "password": "secure_journal_password",
                "abs_ind": "Indexed in Scopus, Web of Science",
                "short_form": "IJCS",
                "journal_image": "/images/journal.jpg",
                "journal_logo": "/images/logo.png",
                "guidelines": "/guidelines.pdf",
                "copyright": "/copyright.pdf",
                "membership": "/membership.pdf",
                "subscription": "/subscription.pdf",
                "publication": "/publication-policy.pdf",
                "advertisement": "/advertisement.pdf",
                "description": "A leading journal in computer science research"
            }
        }


class JournalResponse(BaseModel):
    """Journal response schema"""
    id: int = Field(..., description="Journal ID")
    name: str = Field(..., description="Journal name")
    primary_category: Optional[str] = Field(None, description="Primary research category")
    frequency: Optional[str] = Field(None, description="Publication frequency")
    issn_online: Optional[str] = Field(None, description="ISSN Online")
    issn_print: Optional[str] = Field(None, description="ISSN Print")
    chief_editor: Optional[str] = Field(None, description="Chief editor name")
    co_editor: Optional[str] = Field(None, description="Co-editor name")
    abstract_indexing: Optional[str] = Field(None, description="Abstract indexing services")
    short_form: str = Field(..., description="Journal short form/abbreviation")
    journal_image: str = Field(..., description="Journal image path")
    journal_logo: str = Field(..., description="Journal logo path")
    guidelines: str = Field(..., description="Guidelines URL/path")
    copyright: str = Field(..., description="Copyright info URL/path")
    membership: str = Field(..., description="Membership URL/path")
    subscription: str = Field(..., description="Subscription URL/path")
    publication: str = Field(..., description="Publication policy URL/path")
    advertisement: str = Field(..., description="Advertisement URL/path")
    description: str = Field(..., description="Journal description")
    added_on: Optional[str] = Field(None, description="Added date")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "name": "International Journal of Computer Science",
                "frequency": "Quarterly",
                "issn_online": "2395-0056",
                "issn_print": "2395-0064",
                "chief_editor": "Dr. John Smith",
                "co_editor": "Dr. Jane Doe",
                "short_form": "IJCS",
                "journal_image": "/images/journal.jpg",
                "journal_logo": "/images/logo.png",
                "description": "A leading journal in computer science research",
                "added_on": "2026-02-15"
            }
        }


class JournalListResponse(BaseModel):
    """Journal list response schema (simplified)"""
    id: int = Field(..., description="Journal ID")
    name: str = Field(..., description="Journal name")
    short_form: str = Field(..., description="Journal short form")
    issn_online: Optional[str] = Field(None, description="ISSN Online")
    issn_print: Optional[str] = Field(None, description="ISSN Print")
    chief_editor: Optional[str] = Field(None, description="Chief editor")
    co_editor: Optional[str] = Field(None, description="Co-editor")
    journal_logo: str = Field(..., description="Journal logo path")
    description: str = Field(..., description="Journal description")
    
    class Config:
        from_attributes = True


# ============================================
# Co-Author Schemas
# ============================================

class CoAuthorCreate(BaseModel):
    """Schema for creating a co-author entry"""
    salutation: Optional[str] = Field(None, max_length=20, description="Salutation (Prof. Dr., Prof., Dr., Mr., Ms.)")
    first_name: str = Field(..., min_length=1, max_length=100, description="First name")
    middle_name: Optional[str] = Field(None, max_length=100, description="Middle name (optional)")
    last_name: str = Field(..., min_length=1, max_length=100, description="Last name")
    email: Optional[EmailStr] = Field(None, description="Email address (optional)")
    designation: Optional[str] = Field(None, max_length=100, description="Designation/Occupation")
    department: Optional[str] = Field(None, max_length=200, description="Department")
    organisation: Optional[str] = Field(None, max_length=255, description="Organisation/Institution")
    author_order: int = Field(default=1, ge=1, description="Order of authorship")
    is_corresponding: bool = Field(default=False, description="Is corresponding author")
    
    class Config:
        json_schema_extra = {
            "example": {
                "salutation": "Dr.",
                "first_name": "John",
                "middle_name": "William",
                "last_name": "Smith",
                "email": "john.smith@university.edu",
                "designation": "Associate Professor",
                "department": "Computer Science",
                "organisation": "University of Technology",
                "author_order": 2,
                "is_corresponding": False
            }
        }


class CoAuthorResponse(BaseModel):
    """Schema for co-author response"""
    id: int = Field(..., description="Co-author ID")
    paper_id: int = Field(..., description="Paper ID")
    salutation: Optional[str] = Field(None, description="Salutation")
    first_name: str = Field(..., description="First name")
    middle_name: Optional[str] = Field(None, description="Middle name")
    last_name: str = Field(..., description="Last name")
    email: Optional[str] = Field(None, description="Email address")
    designation: Optional[str] = Field(None, description="Designation/Occupation")
    department: Optional[str] = Field(None, description="Department")
    organisation: Optional[str] = Field(None, description="Organisation/Institution")
    author_order: int = Field(..., description="Order of authorship")
    is_corresponding: bool = Field(..., description="Is corresponding author")
    
    class Config:
        from_attributes = True


class AuthorProfileCreate(BaseModel):
    """Schema for creating/updating author profile (primary author details)"""
    salutation: Optional[str] = Field(None, max_length=20, description="Salutation (Prof. Dr., Prof., Dr., Mr., Ms.)")
    first_name: str = Field(..., min_length=1, max_length=100, description="First name")
    middle_name: Optional[str] = Field(None, max_length=100, description="Middle name (optional)")
    last_name: str = Field(..., min_length=1, max_length=100, description="Last name")
    designation: Optional[str] = Field(None, max_length=100, description="Designation/Occupation")
    department: Optional[str] = Field(None, max_length=200, description="Department")
    organisation: Optional[str] = Field(None, max_length=255, description="Organisation/Institution")
    
    class Config:
        json_schema_extra = {
            "example": {
                "salutation": "Prof. Dr.",
                "first_name": "Jane",
                "middle_name": None,
                "last_name": "Doe",
                "designation": "Professor",
                "department": "Physics",
                "organisation": "MIT"
            }
        }


class PaperSubmitExtended(BaseModel):
    """Extended paper submission schema with metadata and co-authors"""
    title: str = Field(..., min_length=10, max_length=500, description="Paper title")
    abstract: str = Field(..., min_length=100, max_length=2000, description="Paper abstract")
    keywords: str = Field(..., min_length=1, max_length=1000, description="Keywords (comma-separated)")
    journal_id: int = Field(..., description="Target journal ID")
    research_area: Optional[str] = Field(None, max_length=200, description="Research area/field")
    message_to_editor: Optional[str] = Field(None, description="Message to the editor (optional)")
    # Primary author details
    author_details: AuthorProfileCreate = Field(..., description="Primary author details")
    # Co-authors list
    co_authors: List[CoAuthorCreate] = Field(default=[], description="List of co-authors")
    # Terms and conditions
    terms_accepted: bool = Field(..., description="Terms and conditions accepted")
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "A Novel Approach to Machine Learning",
                "abstract": "This paper presents a novel approach...",
                "keywords": "machine learning, deep learning, neural networks",
                "journal_id": 1,
                "research_area": "Artificial Intelligence",
                "message_to_editor": "Please consider this for the special issue.",
                "author_details": {
                    "salutation": "Dr.",
                    "first_name": "Alice",
                    "last_name": "Johnson",
                    "designation": "Research Scientist",
                    "department": "AI Research",
                    "organisation": "Tech Corp"
                },
                "co_authors": [],
                "terms_accepted": True
            }
        }


# Journal Recommendation Schemas
class JournalRecommendationRequest(BaseModel):
    """Request schema for journal recommendations"""
    research_area: str = Field(..., description="Research area/category (required for accurate recommendations)")
    keywords: List[str] = Field(..., min_items=5, description="List of keywords (minimum 5)")
    abstract: Optional[str] = Field(None, description="Paper abstract (optional but improves accuracy)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "research_area": "Computer Science",
                "keywords": ["machine learning", "deep learning", "neural networks", "artificial intelligence", "data science"],
                "abstract": "This paper presents a novel approach to machine learning..."
            }
        }


class JournalRecommendationItem(BaseModel):
    """Single journal recommendation"""
    journal_id: int = Field(..., description="Journal ID")
    journal_name: str = Field(..., description="Journal name")
    score: float = Field(..., description="Recommendation score (0-1)")
    is_recommended: bool = Field(..., description="Whether this journal is recommended")
    match_reason: str = Field(..., description="Reason for recommendation")


class JournalRecommendationResponse(BaseModel):
    """Response schema for journal recommendations"""
    recommendations: List[JournalRecommendationItem] = Field(..., description="List of recommended journals")
    total: int = Field(..., description="Total number of recommendations")
