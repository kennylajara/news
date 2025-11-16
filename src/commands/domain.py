"""
Domain/source management commands.
"""

import click
from datetime import datetime
from db import Database, Source, Article, ProcessingBatch, BatchItem, ProcessType


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


@domain.command()
@click.option('--domain', '-d', required=True, help='Domain to process')
@click.option('--type', '-t', 'process_type', type=click.Choice(['pre_process_articles']), required=True, help='Type of processing')
@click.option('--size', '-s', type=int, default=10, help='Batch size (default: 10)')
def process(domain, process_type, size):
    """
    Create a processing batch for articles from a domain.

    Example:
        news domain process -d diariolibre.com -t pre_process_articles -s 10
    """
    db = Database()
    session = db.get_session()

    try:
        # Get source
        source = session.query(Source).filter_by(domain=domain).first()
        if not source:
            click.echo(click.style(f"✗ Domain '{domain}' not found", fg="red"))
            return

        # Map process type string to enum
        process_type_enum = ProcessType.PRE_PROCESS_ARTICLES

        # Get unprocessed articles (preprocessed_at is NULL), ordered by most recent first
        unprocessed = (
            session.query(Article)
            .filter(Article.source_id == source.id)
            .filter(Article.preprocessed_at.is_(None))
            .order_by(Article.created_at.desc())
            .limit(size)
            .all()
        )

        if not unprocessed:
            click.echo(click.style(f"✗ No unprocessed articles found for {domain}", fg="yellow"))
            return

        click.echo(f"Found {len(unprocessed)} unprocessed articles")
        click.echo(f"Creating batch for {domain}...")

        # Create batch and items atomically
        try:
            # Create batch
            batch = ProcessingBatch(
                source_id=source.id,
                process_type=process_type_enum,
                status='pending',
                total_items=len(unprocessed),
                processed_items=0,
                successful_items=0,
                failed_items=0
            )
            session.add(batch)
            session.flush()

            # Create batch items
            for article in unprocessed:
                item = BatchItem(
                    batch_id=batch.id,
                    article_id=article.id,
                    status='pending'
                )
                session.add(item)

            # Commit transaction atomically
            session.commit()
        except Exception as e:
            session.rollback()
            raise Exception(f"Failed to create batch atomically: {e}")

        click.echo(click.style(f"✓ Batch created (ID: {batch.id}) with {len(unprocessed)} articles", fg="green"))
        click.echo(f"\nBatch details:")
        click.echo(f"  Source: {domain}")
        click.echo(f"  Type: {process_type}")
        click.echo(f"  Articles: {len(unprocessed)}")
        click.echo(f"\nNow processing batch...")

        # Process the batch
        from processors.pre_process import process_batch
        success = process_batch(batch.id, session)

        if success:
            click.echo(click.style(f"\n✓ Batch processing completed successfully", fg="green"))
        else:
            click.echo(click.style(f"\n✗ Batch processing completed with errors", fg="yellow"))

    except Exception as e:
        session.rollback()
        click.echo(click.style(f"✗ Error creating batch: {e}", fg="red"))
        import traceback
        traceback.print_exc()
    finally:
        session.close()
