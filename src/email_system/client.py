"""
SMTP email client for sending emails.

This module provides the EmailClient class for sending emails via SMTP
with support for TLS/SSL, authentication, and comprehensive error handling.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import Optional, List
from datetime import datetime

from settings import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_PASSWORD,
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_USE_TLS,
    SMTP_USE_SSL,
    SMTP_TIMEOUT
)


class EmailClientError(Exception):
    """Base exception for email client errors."""
    pass


class EmailClient:
    """
    SMTP client for sending emails.

    Similar to the Database class pattern - provides high-level methods
    for email operations with proper error handling and logging.

    Example:
        >>> client = EmailClient()
        >>> client.send_email(
        ...     to="user@example.com",
        ...     subject="Test Email",
        ...     html_content="<h1>Hello</h1>",
        ...     text_content="Hello"
        ... )
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        use_tls: Optional[bool] = None,
        use_ssl: Optional[bool] = None,
        timeout: Optional[int] = None
    ):
        """
        Initialize email client with SMTP configuration.

        If parameters are not provided, uses values from settings.py.

        Args:
            host: SMTP server hostname
            port: SMTP server port
            username: SMTP authentication username
            password: SMTP authentication password
            from_email: Default sender email address
            from_name: Default sender name
            use_tls: Use TLS (STARTTLS)
            use_ssl: Use SSL
            timeout: Connection timeout in seconds
        """
        self.host = host or SMTP_HOST
        self.port = port or SMTP_PORT
        self.username = username or SMTP_USERNAME
        self.password = password or SMTP_PASSWORD
        self.from_email = from_email or SMTP_FROM_EMAIL
        self.from_name = from_name or SMTP_FROM_NAME
        self.use_tls = use_tls if use_tls is not None else SMTP_USE_TLS
        self.use_ssl = use_ssl if use_ssl is not None else SMTP_USE_SSL
        self.timeout = timeout or SMTP_TIMEOUT

        # Validate required settings
        if not self.host:
            raise EmailClientError("SMTP_HOST is required")
        if not self.from_email:
            raise EmailClientError("SMTP_FROM_EMAIL is required")

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
        bcc: Optional[str | List[str]] = None
    ) -> dict:
        """
        Send an email via SMTP.

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

        Returns:
            dict: Result with 'success', 'message_id', 'sent_at', 'error' keys

        Raises:
            EmailClientError: If email sending fails
        """
        # Validate content
        if not html_content and not text_content:
            raise EmailClientError("Either html_content or text_content is required")

        # Normalize recipients to lists
        to_list = [to] if isinstance(to, str) else to
        cc_list = [cc] if isinstance(cc, str) else (cc or [])
        bcc_list = [bcc] if isinstance(bcc, str) else (bcc or [])

        # Build email message
        msg = MIMEMultipart('alternative') if (html_content and text_content) else MIMEText('')

        # Set headers
        sender_email = from_email or self.from_email
        sender_name = from_name or self.from_name
        msg['From'] = formataddr((sender_name, sender_email))
        msg['To'] = ', '.join(to_list)
        msg['Subject'] = subject

        if cc_list:
            msg['Cc'] = ', '.join(cc_list)
        if reply_to:
            msg['Reply-To'] = reply_to

        # Attach content parts
        if html_content and text_content:
            # Both versions - attach text first, then HTML (preferred)
            part_text = MIMEText(text_content, 'plain', 'utf-8')
            part_html = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(part_text)
            msg.attach(part_html)
        elif html_content:
            msg = MIMEText(html_content, 'html', 'utf-8')
            msg['From'] = formataddr((sender_name, sender_email))
            msg['To'] = ', '.join(to_list)
            msg['Subject'] = subject
            if cc_list:
                msg['Cc'] = ', '.join(cc_list)
            if reply_to:
                msg['Reply-To'] = reply_to
        else:
            msg = MIMEText(text_content, 'plain', 'utf-8')
            msg['From'] = formataddr((sender_name, sender_email))
            msg['To'] = ', '.join(to_list)
            msg['Subject'] = subject
            if cc_list:
                msg['Cc'] = ', '.join(cc_list)
            if reply_to:
                msg['Reply-To'] = reply_to

        # All recipients (to + cc + bcc)
        all_recipients = to_list + cc_list + bcc_list

        # Send email
        try:
            # Choose SMTP class based on SSL setting
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)

            try:
                # Enable TLS if configured (and not using SSL)
                if self.use_tls and not self.use_ssl:
                    server.starttls()

                # Authenticate if credentials provided
                if self.username and self.password:
                    server.login(self.username, self.password)

                # Send email using sendmail() instead of send_message()
                # This allows the SMTP server to use the authenticated username
                # as the envelope sender, regardless of the From: header
                server.sendmail(sender_email, all_recipients, msg.as_string())

                return {
                    'success': True,
                    'message_id': msg.get('Message-ID'),
                    'sent_at': datetime.utcnow(),
                    'error': None
                }

            finally:
                server.quit()

        except smtplib.SMTPAuthenticationError as e:
            raise EmailClientError(f"SMTP authentication failed: {e}")
        except smtplib.SMTPException as e:
            raise EmailClientError(f"SMTP error: {e}")
        except Exception as e:
            raise EmailClientError(f"Failed to send email: {e}")

    def test_connection(self) -> bool:
        """
        Test SMTP connection and authentication.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)

            try:
                if self.use_tls and not self.use_ssl:
                    server.starttls()

                if self.username and self.password:
                    server.login(self.username, self.password)

                return True

            finally:
                server.quit()

        except Exception:
            return False
