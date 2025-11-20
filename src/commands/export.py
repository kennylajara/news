"""
Export commands for corpus database.
"""

import os
import click
from pathlib import Path

from db.database import Database
from db.export import export_articles_to_corpus


@click.group()
def export():
    """Export articles to corpus database."""
    pass


@export.command()
@click.option('--domain', '-d', default=None, help='Filter by source domain (e.g., diariolibre.com)')
@click.option('--limit', '-l', type=int, default=None, help='Limit number of articles to export')
@click.option('--skip-enriched', is_flag=True, help='Only export articles without enrichment')
@click.option('--output', '-o', default='ai/corpus/raw_news.db', help='Output database path')
def corpus(domain, limit, skip_enriched, output):
    """
    Export articles to corpus database with plain text content.

    The corpus database contains articles in plain text format (no markdown),
    with separated category and subcategory fields. Perfect for ML/NLP tasks.

    Examples:
        news export corpus
        news export corpus --domain diariolibre.com
        news export corpus --domain diariolibre.com --limit 100
        news export corpus --skip-enriched --limit 50
    """
    db = Database()

    # Resolve output path
    output_path = os.path.abspath(output)

    # Show confirmation
    click.echo(f"Exporting articles to: {click.style(output_path, fg='cyan', bold=True)}\n")

    if domain:
        click.echo(f"  Domain filter: {click.style(domain, fg='yellow')}")
    else:
        click.echo(f"  Domain filter: {click.style('ALL', fg='yellow')}")

    if limit:
        click.echo(f"  Limit: {click.style(str(limit), fg='yellow')}")
    else:
        click.echo(f"  Limit: {click.style('NONE', fg='yellow')}")

    if skip_enriched:
        click.echo(f"  Skip enriched: {click.style('YES', fg='yellow')}")
    else:
        click.echo(f"  Skip enriched: {click.style('NO', fg='yellow')}")

    click.echo()

    # Confirm if file already exists
    if os.path.exists(output_path):
        if not click.confirm(f"Database already exists at {output_path}. Continue (will update existing records)?"):
            click.echo(click.style("Export cancelled", fg="yellow"))
            return

    click.echo("Starting export...")

    # Export articles
    session = db.get_session()
    try:
        stats = export_articles_to_corpus(
            session=session,
            corpus_db_path=output_path,
            source_domain=domain,
            limit=limit,
            skip_enriched=skip_enriched
        )

        # Show results
        click.echo()
        click.echo(click.style("Export completed!", fg="green", bold=True))
        click.echo()
        click.echo(f"  Total articles processed: {click.style(str(stats['total']), fg='cyan')}")
        click.echo(f"  Inserted: {click.style(str(stats['inserted']), fg='green')}")
        click.echo(f"  Updated: {click.style(str(stats['updated']), fg='yellow')}")
        click.echo(f"  Skipped: {click.style(str(stats['skipped']), fg='blue')}")

        if stats['errors'] > 0:
            click.echo(f"  Errors: {click.style(str(stats['errors']), fg='red')}")

        click.echo()
        click.echo(f"Database saved to: {click.style(output_path, fg='cyan')}")

    except Exception as e:
        click.echo(click.style(f"Error during export: {str(e)}", fg="red"))
        raise
    finally:
        session.close()


@export.command()
@click.option('--db-path', '-p', default='ai/corpus/raw_news.db', help='Path to corpus database')
def stats(db_path):
    """
    Show statistics for corpus database.

    Example:
        news export stats
        news export stats --db-path ai/corpus/my_corpus.db
    """
    import sqlite3
    from datetime import datetime

    db_path = os.path.abspath(db_path)

    if not os.path.exists(db_path):
        click.echo(click.style(f"Database not found: {db_path}", fg="red"))
        click.echo(click.style("Run 'news export corpus' first to create the database", fg="yellow"))
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Total articles
    cursor.execute("SELECT COUNT(*) FROM articles")
    total = cursor.fetchone()[0]

    if total == 0:
        click.echo(click.style("No articles in corpus database", fg="yellow"))
        conn.close()
        return

    # Articles by source
    cursor.execute("""
        SELECT source_domain, COUNT(*) as count
        FROM articles
        GROUP BY source_domain
        ORDER BY count DESC
    """)
    sources = cursor.fetchall()

    # Articles by category
    cursor.execute("""
        SELECT category, COUNT(*) as count
        FROM articles
        WHERE category IS NOT NULL
        GROUP BY category
        ORDER BY count DESC
        LIMIT 10
    """)
    categories = cursor.fetchall()

    # Date range
    cursor.execute("SELECT MIN(published_date), MAX(published_date) FROM articles WHERE published_date IS NOT NULL")
    date_range = cursor.fetchone()

    # Database size
    db_size = os.path.getsize(db_path)
    if db_size < 1024:
        size_str = f"{db_size} B"
    elif db_size < 1024 * 1024:
        size_str = f"{db_size / 1024:.2f} KB"
    else:
        size_str = f"{db_size / (1024 * 1024):.2f} MB"

    # Display stats
    click.echo(f"Corpus database: {click.style(db_path, fg='cyan', bold=True)}\n")
    click.echo(f"Total articles: {click.style(str(total), fg='green', bold=True)}")
    click.echo(f"Database size: {click.style(size_str, fg='green')}")

    if date_range[0] and date_range[1]:
        click.echo(f"Date range: {date_range[0][:10]} to {date_range[1][:10]}")

    click.echo(f"\nSources ({len(sources)} total):")
    for source, count in sources:
        click.echo(f"  {click.style(source, fg='cyan')}: {count} articles")

    if categories:
        click.echo(f"\nTop categories:")
        for category, count in categories:
            click.echo(f"  {click.style(category, fg='yellow')}: {count} articles")

    conn.close()
