"""Async email service for paper correspondence with delivery tracking"""
import aiosmtplib
import logging
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# SMTP Configuration (same as existing service)
SMTP_SERVER = "mail.aacsjournals.com"
SMTP_PORT = 587
SMTP_USERNAME = "info@aacsjournals.com"
SMTP_PASSWORD = "Aacs@2020"
EMAIL_FROM = "info@aacsjournals.com"
EMAIL_FROM_NAME = "Breakthrough Publishers India Journal Management System"

# Base URL for webhooks (configure based on environment)
WEBHOOK_BASE_URL = "https://api.breakthroughpublishers.com/api/v1/webhooks"


# Email templates for each status type
EMAIL_TEMPLATES: Dict[str, Dict[str, str]] = {
    "submission_confirmed": {
        "subject": "Paper Submission Confirmation - {paper_title}",
        "color": "#769FCD",
        "heading": "Submission Received",
        "message": """
            <p>Thank you for submitting your paper to <strong>{journal_name}</strong>. 
            We have successfully received your submission.</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #769FCD; margin: 20px 0;">
                <p><strong>Submission Details:</strong></p>
                <p><strong>Paper Title:</strong> {paper_title}</p>
                <p><strong>Paper ID:</strong> {paper_code}</p>
                <p><strong>Journal:</strong> {journal_name}</p>
                <p><strong>Submission Date:</strong> {date}</p>
            </div>
            
            <p>Our editorial team will review your paper and you will receive updates on its status. 
            The typical review timeline is 4-8 weeks.</p>
            
            <p>You can track your submission status by logging into your author portal.</p>
        """
    },
    "under_review": {
        "subject": "Your Paper is Under Review - {paper_title}",
        "color": "#3498db",
        "heading": "Paper Under Review",
        "message": """
            <p>Your paper submitted to <strong>{journal_name}</strong> has been assigned to reviewers 
            and is now under peer review.</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #3498db; margin: 20px 0;">
                <p><strong>Paper Details:</strong></p>
                <p><strong>Paper Title:</strong> {paper_title}</p>
                <p><strong>Paper ID:</strong> {paper_code}</p>
                <p><strong>Status:</strong> <span style="color: #3498db; font-weight: bold;">Under Review</span></p>
            </div>
            
            <p>We will notify you once the review process is complete. This typically takes 4-6 weeks.</p>
            
            <p>Thank you for your patience.</p>
        """
    },
    "revision_requested": {
        "subject": "Revision Requested - {paper_title}",
        "color": "#f39c12",
        "heading": "Revision Requested",
        "message": """
            <p>Based on the peer review feedback, your paper requires revisions before it can be 
            accepted for publication in <strong>{journal_name}</strong>.</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #f39c12; margin: 20px 0;">
                <p><strong>Paper Details:</strong></p>
                <p><strong>Paper Title:</strong> {paper_title}</p>
                <p><strong>Paper ID:</strong> {paper_code}</p>
                <p><strong>Status:</strong> <span style="color: #f39c12; font-weight: bold;">Revision Requested</span></p>
                {deadline_info}
            </div>
            
            {comments_section}
            
            <p>Please address the reviewer comments and submit your revised manuscript through the author portal.</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{portal_url}" 
                   style="background-color: #f39c12; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                    Submit Revision
                </a>
            </div>
        """
    },
    "accepted": {
        "subject": "Congratulations! Your Paper Has Been Accepted - {paper_title}",
        "color": "#27ae60",
        "heading": "Paper Accepted",
        "message": """
            <p>We are pleased to inform you that your paper has been <strong>ACCEPTED</strong> for 
            publication in <strong>{journal_name}</strong>.</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #27ae60; margin: 20px 0;">
                <p><strong>Paper Details:</strong></p>
                <p><strong>Paper Title:</strong> {paper_title}</p>
                <p><strong>Paper ID:</strong> {paper_code}</p>
                <p><strong>Status:</strong> <span style="color: #27ae60; font-weight: bold;">ACCEPTED</span></p>
            </div>
            
            {comments_section}
            
            <p>The editorial team will now prepare your paper for publication. You will receive 
            further communication regarding:</p>
            <ul>
                <li>Proofing and final corrections</li>
                <li>Publication schedule</li>
                <li>DOI assignment</li>
            </ul>
            
            <p>Congratulations on this achievement!</p>
        """
    },
    "rejected": {
        "subject": "Editorial Decision - {paper_title}",
        "color": "#e74c3c",
        "heading": "Paper Not Accepted",
        "message": """
            <p>We regret to inform you that after careful consideration, your paper could not be 
            accepted for publication in <strong>{journal_name}</strong>.</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #e74c3c; margin: 20px 0;">
                <p><strong>Paper Details:</strong></p>
                <p><strong>Paper Title:</strong> {paper_title}</p>
                <p><strong>Paper ID:</strong> {paper_code}</p>
                <p><strong>Status:</strong> <span style="color: #e74c3c; font-weight: bold;">Not Accepted</span></p>
            </div>
            
            {comments_section}
            
            <p>We appreciate your interest in {journal_name} and encourage you to consider submitting 
            other work in the future.</p>
            
            <p>Thank you for considering our journal for publication.</p>
        """
    },
    "published": {
        "subject": "Your Paper Has Been Published - {paper_title}",
        "color": "#9b59b6",
        "heading": "Paper Published",
        "message": """
            <p>We are delighted to inform you that your paper has been <strong>PUBLISHED</strong> in 
            <strong>{journal_name}</strong>.</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #9b59b6; margin: 20px 0;">
                <p><strong>Publication Details:</strong></p>
                <p><strong>Paper Title:</strong> {paper_title}</p>
                <p><strong>Journal:</strong> {journal_name}</p>
                <p><strong>Volume/Issue:</strong> {volume_issue}</p>
                {doi_info}
            </div>
            
            <p>Your paper is now available online for readers worldwide.</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{paper_url}" 
                   style="background-color: #9b59b6; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                    View Published Paper
                </a>
            </div>
            
            <p>Congratulations on this accomplishment!</p>
        """
    },
    "resubmitted": {
        "subject": "Revised Paper Received - {paper_title}",
        "color": "#1abc9c",
        "heading": "Revision Received",
        "message": """
            <p>Thank you for submitting your revised manuscript to <strong>{journal_name}</strong>. 
            We have received your revision successfully.</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #1abc9c; margin: 20px 0;">
                <p><strong>Revision Details:</strong></p>
                <p><strong>Paper Title:</strong> {paper_title}</p>
                <p><strong>Paper ID:</strong> {paper_code}</p>
                <p><strong>Version:</strong> {version_number}</p>
                <p><strong>Submission Date:</strong> {date}</p>
            </div>
            
            <p>Your revised manuscript will now undergo further review. We will notify you of the 
            editorial decision as soon as possible.</p>
            
            <p>Thank you for your prompt response to the revision request.</p>
        """
    },
    # Editor notification templates
    "review_submitted_editor": {
        "subject": "Review Submitted for Paper - {paper_title}",
        "color": "#2ecc71",
        "heading": "Review Submitted",
        "message": """
            <p>A reviewer has submitted their review for a paper under your editorial management.</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #2ecc71; margin: 20px 0;">
                <p><strong>Review Details:</strong></p>
                <p><strong>Paper Title:</strong> {paper_title}</p>
                <p><strong>Paper ID:</strong> {paper_code}</p>
                <p><strong>Reviewer:</strong> {reviewer_name}</p>
                <p><strong>Recommendation:</strong> <span style="font-weight: bold;">{recommendation}</span></p>
                <p><strong>Overall Rating:</strong> {overall_rating}/5</p>
            </div>
            
            <p>Please log in to the editor dashboard to view the full review and make an editorial decision.</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{portal_url}" 
                   style="background-color: #2ecc71; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                    View Review
                </a>
            </div>
        """
    },
    "revision_received_editor": {
        "subject": "Revised Paper Received - {paper_title}",
        "color": "#3498db",
        "heading": "Revision Received",
        "message": """
            <p>An author has submitted a revised version of their paper.</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #3498db; margin: 20px 0;">
                <p><strong>Revision Details:</strong></p>
                <p><strong>Paper Title:</strong> {paper_title}</p>
                <p><strong>Paper ID:</strong> {paper_code}</p>
                <p><strong>Author:</strong> {author_name}</p>
                <p><strong>Version:</strong> {version_number}</p>
                <p><strong>Submitted:</strong> {date}</p>
            </div>
            
            <p>Please log in to the editor dashboard to review the revised manuscript and make a decision.</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{portal_url}" 
                   style="background-color: #3498db; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                    Review Revision
                </a>
            </div>
        """
    },
    "invitation_accepted_editor": {
        "subject": "Reviewer Accepted Invitation - {paper_title}",
        "color": "#27ae60",
        "heading": "Invitation Accepted",
        "message": """
            <p>A reviewer has accepted your invitation to review a paper.</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #27ae60; margin: 20px 0;">
                <p><strong>Details:</strong></p>
                <p><strong>Paper Title:</strong> {paper_title}</p>
                <p><strong>Paper ID:</strong> {paper_code}</p>
                <p><strong>Reviewer:</strong> {reviewer_name}</p>
                <p><strong>Review Due Date:</strong> {due_date}</p>
            </div>
            
            <p>The reviewer has been assigned and will submit their review by the due date.</p>
        """
    },
    "invitation_declined_editor": {
        "subject": "Reviewer Declined Invitation - {paper_title}",
        "color": "#e67e22",
        "heading": "Invitation Declined",
        "message": """
            <p>A reviewer has declined your invitation to review a paper.</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #e67e22; margin: 20px 0;">
                <p><strong>Details:</strong></p>
                <p><strong>Paper Title:</strong> {paper_title}</p>
                <p><strong>Paper ID:</strong> {paper_code}</p>
                <p><strong>Reviewer:</strong> {reviewer_name}</p>
                {decline_reason_section}
            </div>
            
            <p>You may need to invite another reviewer for this paper.</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{portal_url}" 
                   style="background-color: #e67e22; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                    Invite Another Reviewer
                </a>
            </div>
        """
    },
    # Author notification when review is complete
    "review_completed_author": {
        "subject": "Review Completed for Your Paper - {paper_title}",
        "color": "#9b59b6",
        "heading": "Review Completed",
        "message": """
            <p>A reviewer has completed their review of your paper submitted to <strong>{journal_name}</strong>.</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #9b59b6; margin: 20px 0;">
                <p><strong>Paper Details:</strong></p>
                <p><strong>Paper Title:</strong> {paper_title}</p>
                <p><strong>Paper ID:</strong> {paper_code}</p>
            </div>
            
            <p>The editorial team will review the feedback and communicate their decision shortly.</p>
            
            <p>You can track your paper status by logging into your author portal.</p>
        """
    }
}


def generate_email_html(
    template_type: str,
    author_name: str,
    **kwargs
) -> str:
    """
    Generate HTML email content from template.
    
    Args:
        template_type: Type of email (submission_confirmed, under_review, etc.)
        author_name: Recipient's name
        **kwargs: Additional template variables
        
    Returns:
        HTML email content
    """
    template = EMAIL_TEMPLATES.get(template_type)
    if not template:
        raise ValueError(f"Unknown email template type: {template_type}")
    
    # Set default values for optional fields
    kwargs.setdefault("date", datetime.utcnow().strftime('%B %d, %Y'))
    kwargs.setdefault("portal_url", "https://aacsjournals.com/author/dashboard")
    kwargs.setdefault("paper_url", "#")
    kwargs.setdefault("comments_section", "")
    kwargs.setdefault("deadline_info", "")
    kwargs.setdefault("volume_issue", "")
    kwargs.setdefault("doi_info", "")
    kwargs.setdefault("version_number", "1")
    kwargs.setdefault("reviewer_name", "Anonymous Reviewer")
    kwargs.setdefault("recommendation", "N/A")
    kwargs.setdefault("overall_rating", "N/A")
    kwargs.setdefault("due_date", "N/A")
    kwargs.setdefault("decline_reason_section", "")
    
    # Build comments section if comments provided
    if kwargs.get("comments"):
        kwargs["comments_section"] = f"""
        <div style="background-color: #f9f9f9; padding: 15px; border-left: 4px solid {template['color']}; margin: 20px 0;">
            <p><strong>Editor/Reviewer Comments:</strong></p>
            <p>{kwargs['comments']}</p>
        </div>
        """
    
    # Build deadline info if deadline provided
    if kwargs.get("deadline"):
        kwargs["deadline_info"] = f"<p><strong>Revision Deadline:</strong> {kwargs['deadline']}</p>"
    
    # Build DOI info if DOI provided
    if kwargs.get("doi"):
        kwargs["doi_info"] = f"<p><strong>DOI:</strong> {kwargs['doi']}</p>"
    
    # Build decline reason section if provided
    if kwargs.get("decline_reason"):
        kwargs["decline_reason_section"] = f"<p><strong>Reason:</strong> {kwargs['decline_reason']}</p>"
    
    # Format the message with provided variables
    try:
        message_content = template["message"].format(**kwargs)
    except KeyError as e:
        logger.error(f"Missing template variable: {e}")
        message_content = template["message"]
    
    # Build full HTML email
    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                <h2 style="color: {template['color']};">{template['heading']}</h2>
                
                <p>Dear {author_name},</p>
                
                {message_content}
                
                <p>If you have any questions, please don't hesitate to contact us at info@breakthroughpublishers.com.</p>
                
                <p>Best regards,<br/>
                The Breakthrough Publishers India Editorial Team</p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="font-size: 12px; color: #999; text-align: center;">
                    This is an automated message from the Breakthrough Publishers India Journal Management System.<br/>
                    Please do not reply directly to this email.
                </p>
            </div>
        </body>
    </html>
    """
    
    return html_content


def generate_subject(template_type: str, **kwargs) -> str:
    """Generate email subject from template"""
    template = EMAIL_TEMPLATES.get(template_type)
    if not template:
        return f"Breakthrough Publishers India Journal Notification - {kwargs.get('paper_title', 'Your Paper')}"
    
    try:
        return template["subject"].format(**kwargs)
    except KeyError:
        return template["subject"].replace("{paper_title}", kwargs.get("paper_title", "Your Paper"))


async def send_correspondence_email_async(
    recipient_email: str,
    recipient_name: str,
    subject: str,
    html_content: str,
    webhook_id: str
) -> tuple[bool, Optional[str]]:
    """
    Send email asynchronously using aiosmtplib.
    
    Args:
        recipient_email: Recipient email address
        recipient_name: Recipient name
        subject: Email subject
        html_content: HTML email content
        webhook_id: Unique ID for webhook tracking
        
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
        msg['To'] = recipient_email
        # Add custom header for webhook tracking
        msg['X-Webhook-ID'] = webhook_id
        
        # Attach HTML content
        msg.attach(MIMEText(html_content, 'html'))
        
        logger.debug(f"Attempting async email to {recipient_email} via {SMTP_SERVER}:{SMTP_PORT}")
        
        # Send email asynchronously
        await aiosmtplib.send(
            msg,
            hostname=SMTP_SERVER,
            port=SMTP_PORT,
            username=SMTP_USERNAME,
            password=SMTP_PASSWORD,
            start_tls=True,
            timeout=30
        )
        
        logger.info(f"Email sent successfully to {recipient_email}, webhook_id: {webhook_id}")
        return True, None
        
    except aiosmtplib.SMTPAuthenticationError as auth_err:
        error_msg = f"SMTP Authentication failed: {str(auth_err)}"
        logger.error(error_msg)
        return False, error_msg
        
    except aiosmtplib.SMTPException as smtp_err:
        error_msg = f"SMTP error: {str(smtp_err)}"
        logger.error(error_msg)
        return False, error_msg
        
    except Exception as e:
        error_msg = f"Failed to send email: {str(e)}"
        logger.error(error_msg)
        return False, error_msg


async def create_and_send_correspondence(
    db: Session,
    paper_id: int,
    paper_code: str,
    paper_title: str,
    journal_name: str,
    author_email: str,
    author_name: str,
    email_type: str,
    status_at_send: str,
    comments: Optional[str] = None,
    deadline: Optional[str] = None,
    volume_issue: Optional[str] = None,
    doi: Optional[str] = None,
    version_number: int = 1,
    reviewer_name: Optional[str] = None,
    recommendation: Optional[str] = None,
    overall_rating: Optional[str] = None,
    due_date: Optional[str] = None,
    decline_reason: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create correspondence record and send email asynchronously.
    
    This is the main function to be called when sending paper lifecycle emails.
    
    Args:
        db: Database session
        paper_id: Paper ID
        paper_code: Paper code
        paper_title: Paper title
        journal_name: Journal name
        author_email: Author/recipient email
        author_name: Author/recipient name
        email_type: Type of email to send
        status_at_send: Paper status when email is sent
        comments: Optional editor/reviewer comments
        deadline: Optional revision deadline
        volume_issue: Optional volume/issue for published papers
        doi: Optional DOI for published papers
        version_number: Paper version number
        reviewer_name: Reviewer name (for editor notifications)
        recommendation: Review recommendation (for editor notifications)
        overall_rating: Overall rating (for editor notifications)
        due_date: Review due date (for editor notifications)
        decline_reason: Reason for declining (for editor notifications)
        
    Returns:
        Dictionary with correspondence_id, success status, and any error message
    """
    from app.db.models import PaperCorrespondence
    
    # Generate unique webhook ID
    webhook_id = str(uuid.uuid4())
    
    # Generate email content
    subject = generate_subject(
        email_type,
        paper_title=paper_title
    )
    
    html_content = generate_email_html(
        email_type,
        author_name=author_name,
        paper_title=paper_title,
        paper_code=paper_code,
        journal_name=journal_name,
        comments=comments,
        deadline=deadline,
        volume_issue=volume_issue,
        doi=doi,
        version_number=str(version_number),
        reviewer_name=reviewer_name,
        recommendation=recommendation,
        overall_rating=overall_rating,
        due_date=due_date,
        decline_reason=decline_reason
    )
    
    # Create correspondence record with pending status
    correspondence = PaperCorrespondence(
        paper_id=paper_id,
        recipient_email=author_email,
        recipient_name=author_name,
        subject=subject,
        body=html_content,
        email_type=email_type,
        status_at_send=status_at_send,
        delivery_status="pending",
        webhook_id=webhook_id,
        created_at=datetime.utcnow()
    )
    
    db.add(correspondence)
    db.commit()
    db.refresh(correspondence)
    
    correspondence_id = correspondence.id
    
    # Send email asynchronously
    success, error_message = await send_correspondence_email_async(
        recipient_email=author_email,
        recipient_name=author_name,
        subject=subject,
        html_content=html_content,
        webhook_id=webhook_id
    )
    
    # Update correspondence record with send result
    if success:
        correspondence.delivery_status = "sent"
        correspondence.sent_at = datetime.utcnow()
    else:
        correspondence.delivery_status = "failed"
        correspondence.error_message = error_message
        correspondence.retry_count = 1
    
    db.commit()
    
    return {
        "correspondence_id": correspondence_id,
        "success": success,
        "error_message": error_message,
        "webhook_id": webhook_id
    }


def create_correspondence_sync(
    db: Session,
    paper_id: int,
    paper_code: str,
    paper_title: str,
    journal_name: str,
    author_email: str,
    author_name: str,
    email_type: str,
    status_at_send: str,
    comments: Optional[str] = None,
    deadline: Optional[str] = None,
    volume_issue: Optional[str] = None,
    doi: Optional[str] = None,
    version_number: int = 1
) -> int:
    """
    Create correspondence record (sync version for background tasks).
    Returns correspondence ID for later async sending.
    """
    from app.db.models import PaperCorrespondence
    
    webhook_id = str(uuid.uuid4())
    
    subject = generate_subject(email_type, paper_title=paper_title)
    
    html_content = generate_email_html(
        email_type,
        author_name=author_name,
        paper_title=paper_title,
        paper_code=paper_code,
        journal_name=journal_name,
        comments=comments,
        deadline=deadline,
        volume_issue=volume_issue,
        doi=doi,
        version_number=str(version_number)
    )
    
    correspondence = PaperCorrespondence(
        paper_id=paper_id,
        recipient_email=author_email,
        recipient_name=author_name,
        subject=subject,
        body=html_content,
        email_type=email_type,
        status_at_send=status_at_send,
        delivery_status="pending",
        webhook_id=webhook_id,
        created_at=datetime.utcnow()
    )
    
    db.add(correspondence)
    db.commit()
    db.refresh(correspondence)
    
    return correspondence.id


async def send_pending_correspondence(db: Session, correspondence_id: int) -> bool:
    """
    Send a pending correspondence entry.
    Used by background tasks and retry jobs.
    """
    from app.db.models import PaperCorrespondence
    
    correspondence = db.query(PaperCorrespondence).filter(
        PaperCorrespondence.id == correspondence_id
    ).first()
    
    if not correspondence:
        logger.error(f"Correspondence {correspondence_id} not found")
        return False
    
    if correspondence.delivery_status not in ["pending", "failed"]:
        logger.info(f"Correspondence {correspondence_id} already processed")
        return True
    
    success, error_message = await send_correspondence_email_async(
        recipient_email=correspondence.recipient_email,
        recipient_name=correspondence.recipient_name or "Author",
        subject=correspondence.subject,
        html_content=correspondence.body,
        webhook_id=correspondence.webhook_id
    )
    
    if success:
        correspondence.delivery_status = "sent"
        correspondence.sent_at = datetime.utcnow()
        correspondence.error_message = None
    else:
        correspondence.delivery_status = "failed"
        correspondence.error_message = error_message
        correspondence.retry_count += 1
    
    db.commit()
    
    return success


def send_simple_email(
    recipient_email: str,
    recipient_name: str,
    subject: str,
    message: str,
    paper_title: str = None,
    paper_id: int = None
) -> bool:
    """
    Send a simple email synchronously.
    
    This is a straightforward email send function for use with custom correspondence.
    
    Args:
        recipient_email: Recipient email address
        recipient_name: Recipient name
        subject: Email subject
        message: Email body (plain text, will be wrapped in HTML template)
        paper_title: Optional paper title for context
        paper_id: Optional paper ID for context
        
    Returns:
        bool: True if sent successfully, False otherwise
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    try:
        # Create HTML email with basic styling
        # Note: Don't add "Dear recipient" here since the message body may already contain a greeting
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f9fafb; }}
                .footer {{ padding: 15px; text-align: center; font-size: 12px; color: #6b7280; border-top: 1px solid #e5e7eb; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 style="margin: 0;">Breakthrough Publishers India Journal Management System</h2>
                </div>
                <div class="content">
                    {message.replace(chr(10), '<br>')}
                </div>
                <div class="footer">
                    <p>This is an automated message from Breakthrough Publishers India Journal Management System.</p>
                    <p>© {datetime.utcnow().year} Breakthrough Publishers India. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
        msg['To'] = recipient_email
        
        # Attach both plain text and HTML versions
        msg.attach(MIMEText(message, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))
        
        logger.debug(f"Sending simple email to {recipient_email}")
        
        # Send email using standard smtplib (synchronous)
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, recipient_email, msg.as_string())
        
        logger.info(f"Simple email sent successfully to {recipient_email}")
        return True
        
    except smtplib.SMTPAuthenticationError as auth_err:
        logger.error(f"SMTP Authentication failed: {str(auth_err)}")
        return False
        
    except smtplib.SMTPException as smtp_err:
        logger.error(f"SMTP error: {str(smtp_err)}")
        return False
        
    except Exception as e:
        logger.error(f"Failed to send simple email: {str(e)}")
        return False


def send_simple_email(
    recipient_email: str,
    recipient_name: str,
    subject: str,
    message: str,
    paper_title: Optional[str] = None,
    paper_id: Optional[int] = None
) -> bool:
    """
    Synchronous email sending for correspondence.
    Uses standard smtplib for sync sending.
    
    Args:
        recipient_email: Email address to send to
        recipient_name: Recipient's name
        subject: Email subject
        message: Email body (can be plain text or HTML)
        paper_title: Optional paper title for reference
        paper_id: Optional paper ID for reference
        
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    import smtplib
    
    try:
        # Create HTML email with simple styling
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #769FCD; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #fff; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Breakthrough Publishers India Journal Management System</h2>
                </div>
                <div class="content">
                    <p>Dear {recipient_name},</p>
                    {message.replace(chr(10), '<br>')}
                </div>
                <div class="footer">
                    <p>© Breakthrough Publishers India | <a href="https://breakthroughpublishers.com">breakthroughpublishers.com</a></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
        msg['To'] = recipient_email
        
        # Attach plain text and HTML versions
        msg.attach(MIMEText(message, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))
        
        logger.debug(f"Attempting sync email to {recipient_email}")
        
        # Connect and send
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Email sent successfully to {recipient_email}")
        return True
        
    except smtplib.SMTPAuthenticationError as auth_err:
        logger.error(f"SMTP Authentication failed: {str(auth_err)}")
        return False
        
    except smtplib.SMTPException as smtp_err:
        logger.error(f"SMTP error: {str(smtp_err)}")
        return False
        
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return False
