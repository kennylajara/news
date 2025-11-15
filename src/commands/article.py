"""
Article management commands.
"""

import click
from db import Database, Article, Tag
from get_news import get_domain, get_url_hash, download_html, clean_html, load_extractor


@click.group()
def article():
    """Manage news articles."""
    pass


@article.command()
@click.argument('url')
def fetch(url):
    """
    Fetch and extract article from URL.

    Example:
        news article fetch "https://example.com/article"
    """
    try:
        domain = get_domain(url)
        url_hash = get_url_hash(url)

        click.echo(f"URL: {url}")
        click.echo(f"Domain: {domain}")
        click.echo(f"Hash: {url_hash}")

        # Check if article already exists
        db = Database()
        session = db.get_session()
        try:
            if db.article_exists(session, url=url, hash=url_hash):
                click.echo(click.style("✓ Article already exists in database", fg="yellow"))
                return
        finally:
            session.close()

        # Download and clean HTML
        click.echo("Downloading HTML...")
        html_content = download_html(url)

        click.echo("Cleaning HTML...")
        cleaned_html = clean_html(html_content)

        # Load extractor
        click.echo(f"Looking for extractor for {domain}...")
        extractor = load_extractor(domain)

        if extractor is None:
            click.echo(click.style(f"✗ No extractor found for domain '{domain}'", fg="red"))
            click.echo(f"Create file: extractors/{domain.replace('.', '_')}.py")
            raise click.Abort()

        click.echo(click.style(f"✓ Extractor found: extractors/{domain.replace('.', '_')}.py", fg="green"))

        # Extract article data
        click.echo("Extracting article data...")
        article_data = extractor.extract(cleaned_html, url)

        # Add metadata
        article_data["_metadata"] = {
            "url": url,
            "domain": domain,
            "hash": url_hash
        }

        # Save to database
        click.echo("Saving to database...")
        db = Database()
        session = db.get_session()
        try:
            article_obj = db.save_article(session, article_data, domain)
            session.commit()
            click.echo(click.style(f"✓ Article saved to database (ID: {article_obj.id})", fg="green"))
        except Exception as db_error:
            session.rollback()
            click.echo(click.style(f"✗ Database error: {db_error}", fg="red"))
            raise
        finally:
            session.close()

        # Show extracted data
        click.echo("\nExtracted data:")
        click.echo(f"  Title: {article_data.get('title', 'N/A')[:80]}...")
        click.echo(f"  Author: {article_data.get('author', 'N/A')}")
        click.echo(f"  Date: {article_data.get('date', 'N/A')}")
        click.echo(f"  Location: {article_data.get('location', 'N/A')}")
        click.echo(f"  Tags: {len(article_data.get('tags', []))} tags")
        click.echo(f"  Content: {len(article_data.get('content', ''))} characters")

        click.echo(click.style("\n✓ Process completed successfully!", fg="green"))

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"))
        raise click.Abort()


@article.command()
@click.option('--limit', '-l', default=10, help='Number of articles to show')
@click.option('--source', '-s', help='Filter by source domain')
@click.option('--tag', '-t', help='Filter by tag')
def list(limit, source, tag):
    """
    List articles from database.

    Examples:
        news article list
        news article list --limit 20
        news article list --source diariolibre.com
        news article list --tag España
    """
    db = Database()
    session = db.get_session()

    try:
        if source:
            articles = db.get_articles_by_source(session, source, limit)
            click.echo(f"Articles from {source}:\n")
        elif tag:
            articles = db.get_articles_by_tag(session, tag, limit)
            click.echo(f"Articles tagged with '{tag}':\n")
        else:
            articles = db.get_recent_articles(session, limit)
            click.echo(f"Recent articles:\n")

        if not articles:
            click.echo(click.style("No articles found", fg="yellow"))
            return

        for art in articles:
            click.echo(f"[{art.id}] {art.title}")
            click.echo(f"    Source: {art.source.domain}")
            click.echo(f"    Date: {art.published_date}")
            click.echo(f"    Tags: {', '.join([t.name for t in art.tags[:3]])}{'...' if len(art.tags) > 3 else ''}")
            click.echo(f"    Hash: {art.hash[:16]}...")
            click.echo()

    finally:
        session.close()


@article.command()
@click.argument('article_id', type=int)
@click.option('--full', '-f', is_flag=True, help='Show full article content')
def show(article_id, full):
    """
    Show article details by ID.

    Examples:
        news article show 1
        news article show 1 --full
    """
    db = Database()
    session = db.get_session()

    try:
        art = session.query(Article).filter_by(id=article_id).first()

        if not art:
            click.echo(click.style(f"✗ Article {article_id} not found", fg="red"))
            return

        click.echo(click.style(f"\n=== Article #{art.id} ===\n", fg="cyan", bold=True))
        click.echo(f"Title: {art.title}")
        click.echo(f"Subtitle: {art.subtitle or 'N/A'}")
        click.echo(f"Author: {art.author or 'N/A'}")
        click.echo(f"Date: {art.published_date}")
        click.echo(f"Location: {art.location or 'N/A'}")
        click.echo(f"Source: {art.source.domain}")
        click.echo(f"Category: {art.category or 'N/A'}")
        click.echo(f"Tags: {', '.join([t.name for t in art.tags])}")
        click.echo(f"URL: {art.url}")
        click.echo(f"Hash: {art.hash}")
        click.echo(f"\nContent ({len(art.content)} chars):")
        click.echo("-" * 80)

        if full:
            click.echo(art.content)
        else:
            preview = art.content[:500] + "..." if len(art.content) > 500 else art.content
            click.echo(preview)
            if len(art.content) > 500:
                click.echo(click.style(f"\n[Use --full to see complete article]", fg="yellow"))

    finally:
        session.close()


@article.command()
@click.argument('article_id', type=int)
@click.confirmation_option(prompt='Are you sure you want to delete this article?')
def delete(article_id):
    """
    Delete article by ID.

    Example:
        news article delete 1
    """
    db = Database()
    session = db.get_session()

    try:
        art = session.query(Article).filter_by(id=article_id).first()

        if not art:
            click.echo(click.style(f"✗ Article {article_id} not found", fg="red"))
            return

        title = art.title
        session.delete(art)
        session.commit()

        click.echo(click.style(f"✓ Deleted article: {title}", fg="green"))

    except Exception as e:
        session.rollback()
        click.echo(click.style(f"✗ Error deleting article: {e}", fg="red"))
    finally:
        session.close()
