"""
Domain/source management commands.
"""

import click
from db import Database, Source


@click.group()
def domain():
    """Manage news sources/domains."""
    pass


@domain.command()
def list():
    """
    List all registered news sources.

    Example:
        news domain list
    """
    db = Database()
    session = db.get_session()

    try:
        sources = session.query(Source).order_by(Source.domain).all()

        if not sources:
            click.echo(click.style("No sources found", fg="yellow"))
            return

        click.echo("Registered news sources:\n")
        for source in sources:
            article_count = len(source.articles)
            click.echo(f"[{source.id}] {source.domain}")
            click.echo(f"    Name: {source.name}")
            click.echo(f"    Articles: {article_count}")
            click.echo(f"    Created: {source.created_at}")
            click.echo()

    finally:
        session.close()


@domain.command()
@click.argument('domain_name')
def show(domain_name):
    """
    Show details for a specific domain.

    Example:
        news domain show diariolibre.com
    """
    db = Database()
    session = db.get_session()

    try:
        source = session.query(Source).filter_by(domain=domain_name).first()

        if not source:
            click.echo(click.style(f"✗ Domain '{domain_name}' not found", fg="red"))
            return

        click.echo(click.style(f"\n=== {source.domain} ===\n", fg="cyan", bold=True))
        click.echo(f"ID: {source.id}")
        click.echo(f"Name: {source.name}")
        click.echo(f"Total articles: {len(source.articles)}")
        click.echo(f"Created: {source.created_at}")

        if source.articles:
            click.echo(f"\nRecent articles:")
            for art in sorted(source.articles, key=lambda a: a.published_date or a.created_at, reverse=True)[:5]:
                click.echo(f"  - [{art.id}] {art.title[:60]}...")
                click.echo(f"    Date: {art.published_date}")

    finally:
        session.close()


@domain.command()
@click.argument('domain_name')
@click.option('--name', '-n', help='Display name for the source')
def add(domain_name, name):
    """
    Manually add a news source.

    Example:
        news domain add example.com --name "Example News"
    """
    db = Database()
    session = db.get_session()

    try:
        # Check if already exists
        existing = session.query(Source).filter_by(domain=domain_name).first()
        if existing:
            click.echo(click.style(f"✗ Domain '{domain_name}' already exists (ID: {existing.id})", fg="yellow"))
            return

        # Create new source
        source = Source(
            domain=domain_name,
            name=name or domain_name
        )
        session.add(source)
        session.commit()

        click.echo(click.style(f"✓ Added source: {domain_name} (ID: {source.id})", fg="green"))

    except Exception as e:
        session.rollback()
        click.echo(click.style(f"✗ Error adding source: {e}", fg="red"))
    finally:
        session.close()


@domain.command()
@click.argument('domain_name')
@click.confirmation_option(prompt='Are you sure? This will delete all articles from this source.')
def delete(domain_name):
    """
    Delete a news source and all its articles.

    Example:
        news domain delete example.com
    """
    db = Database()
    session = db.get_session()

    try:
        source = session.query(Source).filter_by(domain=domain_name).first()

        if not source:
            click.echo(click.style(f"✗ Domain '{domain_name}' not found", fg="red"))
            return

        article_count = len(source.articles)
        session.delete(source)
        session.commit()

        click.echo(click.style(f"✓ Deleted source '{domain_name}' and {article_count} articles", fg="green"))

    except Exception as e:
        session.rollback()
        click.echo(click.style(f"✗ Error deleting source: {e}", fg="red"))
    finally:
        session.close()


@domain.command()
def stats():
    """
    Show statistics about all sources.

    Example:
        news domain stats
    """
    db = Database()
    session = db.get_session()

    try:
        sources = session.query(Source).all()

        if not sources:
            click.echo(click.style("No sources found", fg="yellow"))
            return

        click.echo(click.style("\n=== Source Statistics ===\n", fg="cyan", bold=True))

        total_articles = 0
        for source in sorted(sources, key=lambda s: len(s.articles), reverse=True):
            count = len(source.articles)
            total_articles += count
            click.echo(f"{source.domain:30} {count:5} articles")

        click.echo(f"\n{'Total':30} {total_articles:5} articles")
        click.echo(f"{'Sources':30} {len(sources):5}")

    finally:
        session.close()
