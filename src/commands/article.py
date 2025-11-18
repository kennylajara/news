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
@click.option('--cache-no-read', is_flag=True, default=False, help='Skip reading from cache, always download')
@click.option('--cache-no-save', is_flag=True, default=False, help='Skip saving to cache after download')
def fetch(url, cache_no_read, cache_no_save):
    """
    Fetch and extract article from URL.

    By default, uses cache for both reading and writing.
    Use --cache-no-read to force fresh download.
    Use --cache-no-save to prevent caching the download.

    Example:
        news article fetch "https://example.com/article"
        news article fetch "https://example.com/article" --cache-no-read
        news article fetch "https://example.com/article" --cache-no-read --cache-no-save
    """
    try:
        domain = get_domain(url)
        url_hash = get_url_hash(url)

        click.echo(f"URL: {url}")
        click.echo(f"Domain: {domain}")
        click.echo(f"Hash: {url_hash}")

        # Check cache for potential redirect BEFORE checking if article exists
        # This ensures we check the final URL, not the redirect URL
        from db.cache import CacheDatabase
        cache_db = CacheDatabase()
        cached = cache_db.get_cached_content(url)

        # If cached and was redirected, use the final URL for existence check
        final_url = url
        final_hash = url_hash
        if cached and cached.get('was_redirected'):
            final_url = cached['url']
            final_hash = get_url_hash(final_url)
            click.echo(f"Redirect detected: {url} → {final_url}")

        # Check if article already exists (using final URL if redirected)
        db = Database()
        session = db.get_session()
        try:
            if db.article_exists(session, url=final_url, hash=final_hash):
                click.echo(click.style("✓ Article already exists in database", fg="yellow"))
                return
        finally:
            session.close()

        # Download HTML (with cache support)
        click.echo("Downloading HTML..." if cache_no_read else "Checking cache...")
        download_result = download_html(
            url,
            use_cache_read=not cache_no_read,
            use_cache_save=not cache_no_save,
            verbose=True
        )
        html_content = download_result['content']
        final_url = download_result['final_url']

        # If URL was redirected, update our variables to use the final URL
        if final_url != url:
            click.echo(f"Following redirect: {url} → {final_url}")
            url = final_url
            domain = get_domain(final_url)
            url_hash = get_url_hash(final_url)

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

        # Add metadata (using final URL after redirects)
        article_data["_metadata"] = {
            "url": url,  # This is now the final URL
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
@click.option('--enriched', is_flag=True, help='Show only enriched articles')
@click.option('--pending-enrich', is_flag=True, help='Show only articles pending enrichment')
@click.option('--no-pager', is_flag=True, help='Disable pagination')
def list(limit, source, tag, enriched, pending_enrich, no_pager):
    """
    List articles from database.

    Examples:
        news article list
        news article list --limit 20
        news article list --source diariolibre.com
        news article list --tag España
        news article list --enriched
        news article list --pending-enrich
    """
    db = Database()
    session = db.get_session()

    try:
        # Build query
        query = session.query(Article)

        # Apply filters
        if source:
            from db import Source
            query = query.join(Source).filter(Source.domain == source)

        if tag:
            query = query.join(Article.tags).filter(Tag.name == tag)

        if enriched:
            query = query.filter(Article.enriched_at.isnot(None))
        elif pending_enrich:
            query = query.filter(Article.enriched_at.is_(None))

        # Order and limit
        articles = query.order_by(Article.created_at.desc()).limit(limit).all()

        # Build header
        header_parts = []
        if enriched:
            header_parts.append("Enriched")
        elif pending_enrich:
            header_parts.append("Pending enrichment")
        if source:
            header_parts.append(f"from {source}")
        if tag:
            header_parts.append(f"tagged with '{tag}'")

        if header_parts:
            header = f"{' '.join(header_parts)} articles:\n"
        else:
            header = f"Recent articles:\n"

        if not articles:
            click.echo(header)
            click.echo(click.style("No articles found", fg="yellow"))
            return

        # Build output
        output_lines = [header]
        for art in articles:
            enrich_status = click.style("✓", fg="green") if art.enriched_at else click.style("○", fg="yellow")
            output_lines.append(f"{enrich_status} [{art.id}] {art.title}")
            output_lines.append(f"    Source: {art.source.domain}")
            output_lines.append(f"    Date: {art.published_date}")
            output_lines.append(f"    Tags: {', '.join([t.name for t in art.tags[:3]])}{'...' if len(art.tags) > 3 else ''}")
            if art.enriched_at:
                output_lines.append(f"    Enriched: {art.enriched_at}")
            output_lines.append("")

        output_text = "\n".join(output_lines)

        # Use pager if more than 20 results and not disabled
        if len(articles) > 20 and not no_pager:
            click.echo_via_pager(output_text)
        else:
            click.echo(output_text)

    finally:
        session.close()


@article.command()
@click.argument('article_id', type=int)
@click.option('--full', '-f', is_flag=True, help='Show full article content')
@click.option('--entities', '-e', is_flag=True, help='Show extracted entities (NER)')
@click.option('--clusters', '-c', is_flag=True, help='Show sentence clusters')
def show(article_id, full, entities, clusters):
    """
    Show article details by ID.

    Examples:
        news article show 1
        news article show 1 --full
        news article show 1 --entities
        news article show 1 --clusters
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
        click.echo(f"Enriched: {click.style('Yes', fg='green') if art.enriched_at else click.style('No', fg='yellow')} {f'({art.enriched_at})' if art.enriched_at else ''}")
        click.echo(f"URL: {art.url}")
        click.echo(f"Hash: {art.hash}")

        # Show entities if requested
        if entities:
            from db.models import article_entities
            from db import NamedEntity
            from sqlalchemy import select

            click.echo(f"\n{click.style('Entities:', bold=True)}")

            if not art.enriched_at:
                click.echo(click.style("  Article has not been enriched yet", fg="yellow"))
            else:
                # Query article_entities association table
                stmt = select(
                    NamedEntity.name,
                    NamedEntity.entity_type,
                    article_entities.c.mentions,
                    article_entities.c.relevance
                ).join(
                    NamedEntity, article_entities.c.entity_id == NamedEntity.id
                ).where(
                    article_entities.c.article_id == article_id
                ).order_by(
                    article_entities.c.mentions.desc()
                )

                results = session.execute(stmt).fetchall()

                if not results:
                    click.echo(click.style("  No entities found", fg="yellow"))
                else:
                    click.echo(f"  Total entities: {len(results)}\n")
                    for name, entity_type, mentions, relevance in results:
                        click.echo(f"  • {name}")
                        click.echo(f"    Type: {entity_type.value}")
                        click.echo(f"    Mentions: {mentions}")
                        click.echo(f"    Relevance: {relevance:.2f}")

        # Show clusters if requested
        if clusters:
            from db import ArticleCluster, ArticleSentence

            click.echo(f"\n{click.style('Clusters:', bold=True)}")

            if not art.cluster_enriched_at:
                click.echo(click.style("  Article has not been cluster-enriched yet", fg="yellow"))
            else:
                # Query clusters for this article
                article_clusters = session.query(ArticleCluster).filter_by(
                    article_id=article_id
                ).order_by(ArticleCluster.score.desc()).all()

                if not article_clusters:
                    click.echo(click.style("  No clusters found", fg="yellow"))
                else:
                    click.echo(f"  Total clusters: {len(article_clusters)}\n")

                    for cluster in article_clusters:
                        # Color code by category
                        category_colors = {
                            'core': 'green',
                            'secondary': 'yellow',
                            'filler': 'white'
                        }
                        color = category_colors.get(cluster.category.value, 'white')

                        click.echo(click.style(f"  Cluster {cluster.cluster_label}: {cluster.category.value.upper()}",
                                             fg=color, bold=True))
                        click.echo(f"    Score: {cluster.score:.3f}")
                        click.echo(f"    Size: {cluster.size} sentences")
                        click.echo(f"    Sentence indices: {cluster.sentence_indices}")

                        # Show first 2 sentences as examples
                        cluster_sentences = session.query(ArticleSentence).filter_by(
                            cluster_id=cluster.id
                        ).order_by(ArticleSentence.sentence_index).limit(2).all()

                        if cluster_sentences:
                            click.echo(f"    Sample sentences:")
                            for sent in cluster_sentences:
                                preview = sent.sentence_text[:80] + "..." if len(sent.sentence_text) > 80 else sent.sentence_text
                                click.echo(f"      [{sent.sentence_index}] {preview}")
                        click.echo()

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
