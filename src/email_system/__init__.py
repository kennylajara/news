"""
Email module for sending emails with SMTP and Jinja2 templates.

This module provides:
- EmailClient: SMTP client for sending emails
- EmailRenderer: Jinja2 template rendering for TXT and HTML emails
- EmailService: High-level business logic for email operations
"""

# Note: Imports are not exposed at package level to avoid circular imports
# Import from submodules directly:
#   from email.client import EmailClient
#   from email.renderer import EmailRenderer
#   from email.service import EmailService

__all__ = ["client", "renderer", "service"]
