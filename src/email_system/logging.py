"""
Email sending logging system.

Provides logger class for tracking all email sending operations,
including recipients, subjects, templates, status, and errors.

Uses the same logs database as LLM logs (data/llm_logs.db).
"""

from datetime import datetime
from typing import Any, Dict, Optional


class EmailLogger:
    """
    Logger for email sending operations.

    Tracks all relevant information about an email including recipient,
    subject, template, status, and errors.
    """

    def __init__(
        self,
        recipient: str,
        subject: str,
        template_id: Optional[int] = None,
        context_data: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize logger.

        Args:
            recipient: Email recipient address
            subject: Email subject
            template_id: Optional template ID from EmailTemplate table
            context_data: Optional template variables used for rendering
        """
        self.recipient = recipient
        self.subject = subject
        self.template_id = template_id
        self.context_data = context_data or {}

        # Timing
        self.created_at = datetime.utcnow()
        self.sent_at: Optional[datetime] = None

        # Status
        self.status = 'pending'  # pending, sent, failed
        self.error_message: Optional[str] = None
        self.log_id: Optional[int] = None

    def mark_sent(self):
        """Mark email as successfully sent."""
        self.sent_at = datetime.utcnow()
        self.status = 'sent'

    def mark_failed(self, error_message: str):
        """Mark email as failed with error message."""
        self.status = 'failed'
        self.error_message = error_message

    def save(self):
        """
        Save log entry to logs database.

        Uses the same database as LLM logs (data/llm_logs.db) to keep
        all system logs in one place.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from db.models import Base, EmailLog, EmailStatus
        from pathlib import Path

        # Ensure data directory exists
        Path("data").mkdir(parents=True, exist_ok=True)

        # Use same database as LLM logs
        engine = create_engine('sqlite:///data/llm_logs.db', echo=False)

        # Create tables if they don't exist
        Base.metadata.create_all(engine)

        # Create session
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        try:
            # Map string status to enum
            status_map = {
                'pending': EmailStatus.PENDING,
                'sent': EmailStatus.SENT,
                'failed': EmailStatus.FAILED
            }

            # Create log entry
            log_entry = EmailLog(
                template_id=self.template_id,
                recipient=self.recipient,
                subject=self.subject,
                status=status_map[self.status],
                error_message=self.error_message,
                context_data=self.context_data if self.context_data else None,
                sent_at=self.sent_at,
                created_at=self.created_at,
                updated_at=datetime.utcnow()
            )

            session.add(log_entry)
            session.commit()

            # Store the ID for reference
            self.log_id = log_entry.id

        except Exception as e:
            # Silently fail - logging shouldn't crash the main application
            session.rollback()
            import sys
            print(f"Warning: Failed to save email log: {e}", file=sys.stderr)

        finally:
            session.close()
            engine.dispose()
