"""
Jinja2 template renderer for emails.

This module provides the EmailRenderer class for rendering email templates
from both filesystem (Jinja files) and database (EmailTemplate records).
"""

from pathlib import Path
from typing import Any, Dict, Optional
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, Template

from settings import EMAIL_TEMPLATES_DIR
from db.models import EmailTemplate, EmailTemplateType
from db.database import Database


class RendererError(Exception):
    """Base exception for renderer errors."""
    pass


class EmailRenderer:
    """
    Email template renderer using Jinja2.

    Supports loading templates from:
    1. Filesystem: .jinja files in EMAIL_TEMPLATES_DIR
    2. Database: EmailTemplate records

    Similar to llm/openai_client.py pattern - uses Jinja2 with FileSystemLoader
    and provides methods for rendering both TXT and HTML templates.

    Example:
        >>> renderer = EmailRenderer()
        >>> html = renderer.render_file('newsletter.html.jinja', {'articles': articles})
        >>> text = renderer.render_file('newsletter.txt.jinja', {'articles': articles})
    """

    def __init__(self, templates_dir: Optional[str] = None):
        """
        Initialize email renderer.

        Args:
            templates_dir: Path to templates directory (defaults to EMAIL_TEMPLATES_DIR from settings)
        """
        self.templates_dir = Path(templates_dir or EMAIL_TEMPLATES_DIR)

        # Ensure templates directory exists
        if not self.templates_dir.exists():
            self.templates_dir.mkdir(parents=True, exist_ok=True)

        # Setup Jinja2 environment (same config as llm/openai_client.py)
        self.jinja_env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=True,  # Enable autoescape for HTML safety
            trim_blocks=True,
            lstrip_blocks=True
        )

        # Add custom filters if needed
        self._setup_filters()

    def _setup_filters(self):
        """Setup custom Jinja2 filters for email templates."""
        # Example: date formatting filter
        def datetimeformat(value, format='%Y-%m-%d %H:%M'):
            """Format datetime object."""
            if value is None:
                return ''
            return value.strftime(format)

        self.jinja_env.filters['datetimeformat'] = datetimeformat

    def render_file(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render a template file from the filesystem.

        Args:
            template_name: Template filename (e.g., 'newsletter.html.jinja')
            context: Dictionary with variables to render in template

        Returns:
            str: Rendered template content

        Raises:
            RendererError: If template not found or rendering fails

        Example:
            >>> renderer.render_file('digest.html.jinja', {'articles': articles})
        """
        try:
            template = self.jinja_env.get_template(template_name)
            return template.render(**context)
        except TemplateNotFound:
            raise RendererError(f"Template not found: {template_name}")
        except Exception as e:
            raise RendererError(f"Failed to render template '{template_name}': {e}")

    def render_string(self, template_string: str, context: Dict[str, Any]) -> str:
        """
        Render a template from a string.

        Useful for rendering templates from database (EmailTemplate.content).

        Args:
            template_string: Template content as string
            context: Dictionary with variables to render in template

        Returns:
            str: Rendered template content

        Raises:
            RendererError: If rendering fails

        Example:
            >>> template_str = "Hello {{ name }}!"
            >>> renderer.render_string(template_str, {'name': 'World'})
            'Hello World!'
        """
        try:
            template = Template(template_string, autoescape=True)
            return template.render(**context)
        except Exception as e:
            raise RendererError(f"Failed to render template string: {e}")

    def render_from_db(
        self,
        template_name: str,
        context: Dict[str, Any],
        session=None
    ) -> Dict[str, str]:
        """
        Render email templates from database.

        Fetches EmailTemplate record(s) by name and renders both TXT and HTML versions
        if available.

        Args:
            template_name: Template name in database (e.g., 'newsletter_digest')
            context: Dictionary with variables to render in template
            session: SQLAlchemy session (optional, creates new if not provided)

        Returns:
            dict: {'subject': str, 'html': Optional[str], 'text': Optional[str]}

        Raises:
            RendererError: If template not found or rendering fails

        Example:
            >>> result = renderer.render_from_db('flash_news_alert', {'news': flash_news})
            >>> result['subject']  # "Flash News Alert"
            >>> result['html']     # "<h1>Flash News</h1>..."
            >>> result['text']     # "Flash News\\n\\n..."
        """
        # Create session if not provided
        should_close = False
        if session is None:
            db = Database()
            session = db.get_session()
            should_close = True

        try:
            # Fetch all templates with this name (TXT and HTML versions)
            templates = session.query(EmailTemplate).filter(
                EmailTemplate.name == template_name
            ).all()

            if not templates:
                raise RendererError(f"Template not found in database: {template_name}")

            # Render each template type
            result = {
                'subject': templates[0].subject,  # Subject is same for all versions
                'html': None,
                'text': None
            }

            for template in templates:
                rendered = self.render_string(template.content, context)

                if template.template_type == EmailTemplateType.HTML:
                    result['html'] = rendered
                elif template.template_type == EmailTemplateType.TXT:
                    result['text'] = rendered

            return result

        finally:
            if should_close:
                session.close()

    def list_file_templates(self) -> list[str]:
        """
        List all available template files in the templates directory.

        Returns:
            list[str]: List of template filenames

        Example:
            >>> renderer.list_file_templates()
            ['newsletter.html.jinja', 'newsletter.txt.jinja', ...]
        """
        if not self.templates_dir.exists():
            return []

        return [
            f.name
            for f in self.templates_dir.iterdir()
            if f.is_file() and f.suffix == '.jinja'
        ]
