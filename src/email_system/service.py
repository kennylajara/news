"""
High-level email service for business logic.

This module provides the EmailService class that integrates EmailClient
and EmailRenderer with database logging for comprehensive email operations.
"""

from typing import Any, Dict, Optional, List
from datetime import datetime

from email_system.client import EmailClient, EmailClientError
from email_system.renderer import EmailRenderer, RendererError
from email_system.logging import EmailLogger
from db.database import Database
from db.models import EmailLog, EmailStatus, EmailTemplate


class EmailServiceError(Exception):
    """Base exception for email service errors."""
    pass


class EmailService:
    """
    High-level email service for sending emails with templates and logging.

    Integrates:
    - EmailClient: SMTP sending
    - EmailRenderer: Template rendering
    - Database: Email logging (EmailLog table)

    Similar to processors pattern - handles business logic and database operations.

    Example:
        >>> service = EmailService()
        >>> service.send_with_template(
        ...     template_name='newsletter_digest',
        ...     recipient='user@example.com',
        ...     context={'articles': articles}
        ... )
    """

    def __init__(self):
        """Initialize email service with client, renderer, and database."""
        self.client = EmailClient()
        self.renderer = EmailRenderer()
        self.db = Database()

    def send_email(
        self,
        to: str | List[str],
        subject: str,
        html_content: Optional[str] = None,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[str | List[str]] = None,
        bcc: Optional[str | List[str]] = None,
        template_id: Optional[int] = None,
        context_data: Optional[Dict[str, Any]] = None,
        log_to_db: bool = True
    ) -> dict:
        """
        Send an email and optionally log to database.

        Args:
            to: Recipient email address(es)
            subject: Email subject
            html_content: HTML version of email body
            text_content: Plain text version of email body
            from_email: Sender email (overrides default)
            from_name: Sender name (overrides default)
            reply_to: Reply-To email address
            cc: CC recipient(s)
            bcc: BCC recipient(s)
            template_id: Optional EmailTemplate ID for logging
            context_data: Template context data for logging
            log_to_db: Whether to log to database (default: True)

        Returns:
            dict: Result with 'success', 'log_id', 'error' keys

        Raises:
            EmailServiceError: If sending fails
        """
        # Normalize recipient to string for logging
        recipient = to if isinstance(to, str) else ', '.join(to)

        # Create logger
        logger = None
        if log_to_db:
            logger = EmailLogger(
                recipient=recipient,
                subject=subject,
                template_id=template_id,
                context_data=context_data
            )

        try:
            # Send email
            result = self.client.send_email(
                to=to,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                from_email=from_email,
                from_name=from_name,
                reply_to=reply_to,
                cc=cc,
                bcc=bcc
            )

            # Mark as sent and save log
            if logger:
                logger.mark_sent()
                logger.save()

            return {
                'success': True,
                'log_id': logger.log_id if logger else None,
                'error': None
            }

        except EmailClientError as e:
            # Mark as failed and save log
            if logger:
                logger.mark_failed(str(e))
                logger.save()

            raise EmailServiceError(f"Failed to send email: {e}")

    def send_with_file_template(
        self,
        template_name: str,
        recipient: str | List[str],
        context: Dict[str, Any],
        subject: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[str | List[str]] = None,
        bcc: Optional[str | List[str]] = None
    ) -> dict:
        """
        Send email using file-based templates.

        Renders both .html.jinja and .txt.jinja if available.

        Args:
            template_name: Base template name (without .html.jinja/.txt.jinja extension)
            recipient: Recipient email address(es)
            context: Template rendering context
            subject: Email subject (required if not in template)
            from_email: Sender email
            from_name: Sender name
            reply_to: Reply-To email
            cc: CC recipient(s)
            bcc: BCC recipient(s)

        Returns:
            dict: Result with 'success', 'log_id', 'error' keys

        Raises:
            EmailServiceError: If rendering or sending fails

        Example:
            >>> # Uses newsletter.html.jinja and newsletter.txt.jinja
            >>> service.send_with_file_template(
            ...     template_name='newsletter',
            ...     recipient='user@example.com',
            ...     context={'articles': articles},
            ...     subject='Weekly Newsletter'
            ... )
        """
        if not subject:
            raise EmailServiceError("Subject is required for file-based templates")

        try:
            # Render HTML template if exists
            html_content = None
            try:
                html_content = self.renderer.render_file(
                    f"{template_name}.html.jinja",
                    context
                )
            except RendererError:
                pass  # HTML template optional

            # Render TXT template if exists
            text_content = None
            try:
                text_content = self.renderer.render_file(
                    f"{template_name}.txt.jinja",
                    context
                )
            except RendererError:
                pass  # TXT template optional

            # At least one template must exist
            if not html_content and not text_content:
                raise EmailServiceError(
                    f"No templates found for: {template_name}.html.jinja or {template_name}.txt.jinja"
                )

            # Send email
            return self.send_email(
                to=recipient,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                from_email=from_email,
                from_name=from_name,
                reply_to=reply_to,
                cc=cc,
                bcc=bcc,
                context_data=context
            )

        except RendererError as e:
            raise EmailServiceError(f"Template rendering failed: {e}")

    def send_with_db_template(
        self,
        template_name: str,
        recipient: str | List[str],
        context: Dict[str, Any],
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[str | List[str]] = None,
        bcc: Optional[str | List[str]] = None
    ) -> dict:
        """
        Send email using database-stored templates.

        Renders EmailTemplate records (both TXT and HTML versions if available).

        Args:
            template_name: Template name in database
            recipient: Recipient email address(es)
            context: Template rendering context
            from_email: Sender email
            from_name: Sender name
            reply_to: Reply-To email
            cc: CC recipient(s)
            bcc: BCC recipient(s)

        Returns:
            dict: Result with 'success', 'log_id', 'error' keys

        Raises:
            EmailServiceError: If rendering or sending fails

        Example:
            >>> service.send_with_db_template(
            ...     template_name='flash_news_alert',
            ...     recipient='user@example.com',
            ...     context={'news': flash_news}
            ... )
        """
        session = self.db.get_session()

        try:
            # Render template from database
            rendered = self.renderer.render_from_db(
                template_name=template_name,
                context=context,
                session=session
            )

            # Get template ID for logging
            template = session.query(EmailTemplate).filter(
                EmailTemplate.name == template_name
            ).first()

            # Send email
            return self.send_email(
                to=recipient,
                subject=rendered['subject'],
                html_content=rendered['html'],
                text_content=rendered['text'],
                from_email=from_email,
                from_name=from_name,
                reply_to=reply_to,
                cc=cc,
                bcc=bcc,
                template_id=template.id if template else None,
                context_data=context
            )

        except RendererError as e:
            raise EmailServiceError(f"Template rendering failed: {e}")
        finally:
            session.close()

    def get_email_logs(
        self,
        recipient: Optional[str] = None,
        status: Optional[EmailStatus] = None,
        limit: int = 50
    ) -> List[dict]:
        """
        Get email logs with optional filtering.

        Args:
            recipient: Filter by recipient email
            status: Filter by status
            limit: Maximum number of logs to return

        Returns:
            List[dict]: List of email log records as dictionaries
        """
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from pathlib import Path

        # Ensure data directory exists
        Path("data").mkdir(parents=True, exist_ok=True)

        # Use same database as LLM logs
        engine = create_engine('sqlite:///data/llm_logs.db', echo=False)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        try:
            query = session.query(EmailLog).order_by(EmailLog.created_at.desc())

            if recipient:
                query = query.filter(EmailLog.recipient == recipient)

            if status:
                query = query.filter(EmailLog.status == status)

            logs = query.limit(limit).all()

            # Convert to dictionaries to avoid detached instance errors
            results = []
            for log in logs:
                results.append({
                    'id': log.id,
                    'recipient': log.recipient,
                    'subject': log.subject,
                    'status': log.status,
                    'template_id': log.template_id,
                    'error_message': log.error_message,
                    'sent_at': log.sent_at,
                    'created_at': log.created_at
                })

            return results

        finally:
            session.close()
            engine.dispose()

    def test_smtp_connection(self) -> bool:
        """
        Test SMTP connection and authentication.

        Returns:
            bool: True if connection successful, False otherwise
        """
        return self.client.test_connection()
