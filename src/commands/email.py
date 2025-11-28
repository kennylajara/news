"""
Email management commands.
"""

import click
from datetime import datetime
from db import Database
from db.models import EmailTemplate, EmailLog, EmailStatus, EmailTemplateType
from email_system.service import EmailService, EmailServiceError
from email_system.renderer import EmailRenderer


@click.group()
def email():
    """Manage email templates and sending."""
    pass


@email.command()
@click.option('--recipient', '-r', required=True, help='Recipient email address')
@click.option('--subject', '-s', required=True, help='Email subject')
@click.option('--message', '-m', required=True, help='Email message')
@click.option('--html', is_flag=True, help='Message is HTML (default: plain text)')
def send(recipient, subject, message, html):
    """
    Send a simple email.

    Example:
        uv run news email send -r user@example.com -s "Test" -m "Hello World"
        uv run news email send -r user@example.com -s "Test" -m "<h1>Hello</h1>" --html
    """
    service = EmailService()

    try:
        click.echo(f"Sending email to {recipient}...")

        if html:
            result = service.send_email(
                to=recipient,
                subject=subject,
                html_content=message
            )
        else:
            result = service.send_email(
                to=recipient,
                subject=subject,
                text_content=message
            )

        if result['success']:
            click.echo(click.style(f"✓ Email sent successfully (Log ID: {result['log_id']})", fg="green"))
        else:
            click.echo(click.style(f"✗ Email failed: {result['error']}", fg="red"))

    except EmailServiceError as e:
        click.echo(click.style(f"Error: {e}", fg="red"))


@email.command()
@click.option('--template', '-t', required=True, help='Template name (without .jinja extension)')
@click.option('--recipient', '-r', required=True, help='Recipient email address')
@click.option('--subject', '-s', required=True, help='Email subject')
@click.option('--var', '-v', multiple=True, help='Template variables (key=value)')
def send_template(template, recipient, subject, var):
    """
    Send email using file-based template.

    Example:
        uv run news email send-template -t test -r user@example.com -s "Test Email" \\
            -v title="Welcome" -v message="Hello World" -v name="John"

        uv run news email send-template -t newsletter -r user@example.com -s "Newsletter" \\
            -v subscriber_name="John"
    """
    service = EmailService()

    # Parse template variables
    context = {}
    for item in var:
        if '=' not in item:
            click.echo(click.style(f"Invalid variable format: {item} (use key=value)", fg="red"))
            return

        key, value = item.split('=', 1)
        context[key] = value

    # Add defaults
    context.setdefault('current_year', str(datetime.now().year))

    try:
        click.echo(f"Rendering template '{template}' and sending to {recipient}...")

        result = service.send_with_file_template(
            template_name=template,
            recipient=recipient,
            context=context,
            subject=subject
        )

        if result['success']:
            click.echo(click.style(f"✓ Email sent successfully (Log ID: {result['log_id']})", fg="green"))
        else:
            click.echo(click.style(f"✗ Email failed: {result['error']}", fg="red"))

    except EmailServiceError as e:
        click.echo(click.style(f"Error: {e}", fg="red"))


@email.command()
@click.option('--name', '-n', required=True, help='Template name')
@click.option('--subject', '-s', required=True, help='Email subject')
@click.option('--type', '-t', type=click.Choice(['txt', 'html']), required=True, help='Template type')
@click.option('--file', '-f', type=click.Path(exists=True), help='Template file to import')
@click.option('--content', '-c', help='Template content (if not using --file)')
@click.option('--description', '-d', help='Template description')
def create_template(name, subject, type, file, content, description):
    """
    Create email template in database.

    Example:
        uv run news email create-template -n test_html -s "Test" -t html \\
            -f src/email/templates/test.html.jinja -d "Test HTML template"

        uv run news email create-template -n test_txt -s "Test" -t txt \\
            -c "Hello {{ name }}" -d "Test text template"
    """
    if not file and not content:
        click.echo(click.style("Error: Either --file or --content is required", fg="red"))
        return

    # Read content from file or use provided content
    if file:
        with open(file, 'r') as f:
            template_content = f.read()
    else:
        template_content = content

    db = Database()
    session = db.get_session()

    try:
        # Check if template exists
        existing = session.query(EmailTemplate).filter(
            EmailTemplate.name == name
        ).first()

        if existing:
            click.echo(click.style(f"Error: Template '{name}' already exists", fg="red"))
            return

        # Create template
        template = EmailTemplate(
            name=name,
            subject=subject,
            template_type=EmailTemplateType.HTML if type == 'html' else EmailTemplateType.TXT,
            content=template_content,
            description=description
        )

        session.add(template)
        session.commit()

        click.echo(click.style(f"✓ Template '{name}' created (ID: {template.id})", fg="green"))

    except Exception as e:
        session.rollback()
        click.echo(click.style(f"Error: {e}", fg="red"))
    finally:
        session.close()


@email.command()
def list_templates():
    """
    List all email templates.

    Example:
        uv run news email list-templates
    """
    db = Database()
    session = db.get_session()

    try:
        # Get database templates
        db_templates = session.query(EmailTemplate).order_by(EmailTemplate.name).all()

        # Get file templates
        renderer = EmailRenderer()
        file_templates = renderer.list_file_templates()

        # Display results
        click.echo(click.style("\n=== Database Templates ===\n", bold=True))

        if db_templates:
            for template in db_templates:
                click.echo(f"  {click.style(template.name, fg='cyan')} ({template.template_type.value})")
                click.echo(f"    Subject: {template.subject}")
                if template.description:
                    click.echo(f"    Description: {template.description}")
                click.echo(f"    Created: {template.created_at.strftime('%Y-%m-%d %H:%M')}")
                click.echo()
        else:
            click.echo(click.style("  No database templates found", fg="yellow"))

        click.echo(click.style("\n=== File Templates ===\n", bold=True))

        if file_templates:
            for template in file_templates:
                click.echo(f"  {click.style(template, fg='cyan')}")
        else:
            click.echo(click.style("  No file templates found", fg="yellow"))

        click.echo()

    finally:
        session.close()


@email.command()
@click.option('--status', type=click.Choice(['pending', 'sent', 'failed']), help='Filter by status')
@click.option('--recipient', help='Filter by recipient email')
@click.option('--limit', default=50, help='Maximum number of results (default: 50)')
@click.option('--no-pager', is_flag=True, help='Disable pagination')
def logs(status, recipient, limit, no_pager):
    """
    Show email sending logs.

    Example:
        uv run news email logs
        uv run news email logs --status failed
        uv run news email logs --recipient user@example.com
    """
    service = EmailService()

    # Convert status string to enum
    status_enum = None
    if status:
        status_enum = EmailStatus[status.upper()]

    # Get logs
    email_logs = service.get_email_logs(
        recipient=recipient,
        status=status_enum,
        limit=limit
    )

    if not email_logs:
        click.echo(click.style("No email logs found", fg="yellow"))
        return

    # Prepare output
    output_lines = []
    output_lines.append(click.style(f"\n=== Email Logs ({len(email_logs)} results) ===\n", bold=True))

    for log in email_logs:
        # Status color
        status_colors = {
            EmailStatus.SENT: 'green',
            EmailStatus.PENDING: 'yellow',
            EmailStatus.FAILED: 'red'
        }
        status_color = status_colors.get(log['status'], 'white')

        output_lines.append(f"ID: {click.style(str(log['id']), fg='cyan')}")
        output_lines.append(f"  Status: {click.style(log['status'].value.upper(), fg=status_color)}")
        output_lines.append(f"  Recipient: {log['recipient']}")
        output_lines.append(f"  Subject: {log['subject']}")

        if log['template_id']:
            output_lines.append(f"  Template ID: {log['template_id']}")

        output_lines.append(f"  Created: {log['created_at'].strftime('%Y-%m-%d %H:%M:%S')}")

        if log['sent_at']:
            output_lines.append(f"  Sent: {log['sent_at'].strftime('%Y-%m-%d %H:%M:%S')}")

        if log['error_message']:
            output_lines.append(f"  Error: {click.style(log['error_message'], fg='red')}")

        output_lines.append("")

    # Output with or without pager
    output_text = '\n'.join(output_lines)

    if no_pager or len(email_logs) <= 20:
        click.echo(output_text)
    else:
        click.echo_via_pager(output_text)


@email.command()
def test():
    """
    Test SMTP connection and configuration.

    Example:
        uv run news email test
    """
    service = EmailService()

    click.echo("Testing SMTP connection...")

    try:
        if service.test_smtp_connection():
            click.echo(click.style("✓ SMTP connection successful", fg="green"))
        else:
            click.echo(click.style("✗ SMTP connection failed", fg="red"))
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"))
