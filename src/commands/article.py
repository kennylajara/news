"""
Article management commands.
"""

import hashlib
import click
from db import Database, Article, Tag
from get_news import get_domain, get_url_hash, download_html, clean_html, load_extractor


def _process_article_from_html(url, html_content, verbose=True, force_reprocess=False):
    """
    Process article from HTML content.

    This is a helper function shared by fetch and fetch-cached commands.

    Args:
        url: Article URL (should be final URL after redirects)
        html_content: Raw HTML content
        verbose: Whether to print progress messages
        force_reprocess: If True, always reset enrichment status even if content hasn't changed

    Returns:
        Dictionary with:
            - 'success': bool
            - 'article': Article object if success, None otherwise
            - 'error': str if not success, None otherwise
            - 'article_data': dict with extracted data if success
    """
    try:
        domain = get_domain(url)
        url_hash = get_url_hash(url)

        # Clean HTML
        if verbose:
            click.echo("Cleaning HTML...")
        cleaned_html = clean_html(html_content)

        # Calculate SHA-256 hash of cleaned HTML for change detection
        cleaned_html_hash = hashlib.sha256(cleaned_html.encode('utf-8')).hexdigest()

        # Load extractor
        if verbose:
            click.echo(f"Looking for extractor for {domain}...")
        extractor = load_extractor(domain)

        if extractor is None:
            error_msg = f"No extractor found for domain '{domain}'"
            if verbose:
                click.echo(click.style(f"✗ {error_msg}", fg="red"))
                click.echo(f"Create file: extractors/{domain.replace('.', '_')}.py")
            return {
                'success': False,
                'article': None,
                'error': error_msg,
                'article_data': None
            }

        if verbose:
            click.echo(click.style(f"✓ Extractor found: extractors/{domain.replace('.', '_')}.py", fg="green"))

        # Extract article data
        if verbose:
            click.echo("Extracting article data...")
        article_data = extractor.extract(cleaned_html, url)

        # Add metadata
        article_data["_metadata"] = {
            "url": url,
            "domain": domain,
            "hash": url_hash,
            "cleaned_html_hash": cleaned_html_hash
        }

        # Save to database (or update if exists)
        if verbose:
            click.echo("Saving to database...")
        db = Database()
        session = db.get_session()
        try:
            article_obj, was_updated = db.save_or_update_article(session, article_data, domain, force_reprocess=force_reprocess)
            session.commit()

            # Extract ID before closing session
            article_id = article_obj.id

            if verbose:
                if was_updated:
                    click.echo(click.style(f"✓ Article updated in database (ID: {article_id})", fg="green"))
                else:
                    click.echo(click.style(f"✓ Article saved to database (ID: {article_id})", fg="green"))

            return {
                'success': True,
                'article_id': article_id,
                'was_updated': was_updated,
                'error': None,
                'article_data': article_data
            }
        except Exception as db_error:
            session.rollback()
            error_msg = f"Database error: {db_error}"
            if verbose:
                click.echo(click.style(f"✗ {error_msg}", fg="red"))
            return {
                'success': False,
                'article_id': None,
                'was_updated': False,
                'error': error_msg,
                'article_data': None
            }
        finally:
            session.close()

    except Exception as e:
        error_msg = str(e)
        if verbose:
            click.echo(click.style(f"✗ Error: {error_msg}", fg="red"))
        return {
            'success': False,
            'article': None,
            'error': error_msg,
            'article_data': None
        }


@click.group()
def article():
    """Manage news articles."""
    pass


@article.command()
@click.argument('url')
@click.option('--reindex', is_flag=True, default=False, help='Fetch fresh content and update if article exists')
@click.option('--dont-cache', is_flag=True, default=False, help='Don\'t save downloaded content to cache')
@click.option('--force-enrichment', is_flag=True, default=False, help='Force re-enrichment even if content hasn\'t changed')
def fetch(url, reindex, dont_cache, force_enrichment):
    """
    Fetch and extract article from URL.

    By default, uses cache for reading and writing, and skips articles
    that already exist in the database.

    --reindex: Fetch fresh content (bypass cache) and update if article exists.
    --dont-cache: Don't save downloaded content to cache (useful for temporary URLs).

    Examples:
        news article fetch "https://example.com/article"
        news article fetch "https://example.com/article" --reindex
        news article fetch "https://example.com/article" --dont-cache
        news article fetch "https://example.com/article" --reindex --dont-cache
    """
    try:
        domain = get_domain(url)
        url_hash = get_url_hash(url)

        click.echo(f"URL: {url}")
        click.echo(f"Domain: {domain}")
        click.echo(f"Hash: {url_hash}")

        # Check cache for potential redirect BEFORE checking if article exists
        # This ensures we check the final URL, not the redirect URL
        # Skip cache check if --reindex (we'll download fresh anyway)
        from db.cache import CacheDatabase
        cache_db = CacheDatabase()
        cached = None
        if not reindex:
            cached = cache_db.get_cached_content(url)

        # If cached and was redirected, use the final URL for existence check
        final_url = url
        final_hash = url_hash
        if cached and cached.get('was_redirected'):
            final_url = cached['url']
            final_hash = get_url_hash(final_url)
            click.echo(f"Redirect detected: {url} → {final_url}")

        # Check if article already exists (using final URL if redirected)
        # Skip this check if --reindex is enabled
        if not reindex:
            db = Database()
            session = db.get_session()
            try:
                if db.article_exists(session, url=final_url, hash=final_hash):
                    click.echo(click.style("✓ Article already exists in database", fg="yellow"))
                    click.echo("  Use --reindex to fetch fresh content and update it")
                    return
            finally:
                session.close()

        # Download HTML (with cache support)
        # If --reindex: force fresh download (don't read cache)
        # If --dont-cache: don't save to cache
        use_cache_read = not reindex
        use_cache_save = not dont_cache

        click.echo("Downloading fresh content..." if reindex else "Checking cache...")
        download_result = download_html(
            url,
            use_cache_read=use_cache_read,
            use_cache_save=use_cache_save,
            verbose=True
        )
        html_content = download_result['content']
        final_url = download_result['final_url']

        # If URL was redirected, update our variables to use the final URL
        if final_url != url:
            click.echo(f"Following redirect: {url} → {final_url}")
            url = final_url

        # Process article using shared helper
        result = _process_article_from_html(url, html_content, verbose=True, force_reprocess=force_enrichment)

        if not result['success']:
            raise click.Abort()

        # Show extracted data
        article_data = result['article_data']
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
@click.option('--analysis', '-a', is_flag=True, help='Show deep analysis for recommendations')
@click.option('--flash', is_flag=True, help='Show flash news summaries')
def show(article_id, full, entities, clusters, analysis, flash):
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

        # Show analysis if requested
        if analysis:
            from db import ArticleAnalysis

            click.echo(f"\n{click.style('Deep Analysis:', bold=True)}")

            art_analysis = session.query(ArticleAnalysis).filter_by(article_id=article_id).first()

            if not art_analysis:
                click.echo(click.style("  Article has not been analyzed yet", fg="yellow"))
                click.echo(click.style("  Run: news process start -d <domain> -t analyze_article", fg="yellow"))
            else:
                # Semantic
                click.echo(f"\n  {click.style('Semantic:', fg='cyan')}")
                click.echo(f"    Key concepts: {', '.join(art_analysis.key_concepts)}")

                # Narrative
                click.echo(f"\n  {click.style('Narrative:', fg='cyan')}")
                click.echo(f"    Frames: {', '.join(art_analysis.narrative_frames)}")
                click.echo(f"    Tone: {art_analysis.editorial_tone}")
                click.echo(f"    Format: {art_analysis.content_format}")
                click.echo(f"    Temporal relevance: {art_analysis.temporal_relevance}")

                # Scores
                click.echo(f"\n  {click.style('Scores:', fg='cyan')}")

                # Controversy with color coding
                controversy_color = 'green' if art_analysis.controversy_score < 40 else ('yellow' if art_analysis.controversy_score < 70 else 'red')
                click.echo(f"    Controversy: {click.style(str(art_analysis.controversy_score), fg=controversy_color)}/100")

                # Political bias with color coding
                bias = art_analysis.political_bias
                bias_label = "neutral" if -20 <= bias <= 20 else ("left" if bias < -20 else "right")
                bias_color = 'white' if -20 <= bias <= 20 else ('blue' if bias < -20 else 'red')
                click.echo(f"    Political bias: {click.style(f'{bias} ({bias_label})', fg=bias_color)}")

                # Audience
                click.echo(f"\n  {click.style('Target audience:', fg='cyan')}")
                click.echo(f"    Education level: {art_analysis.audience_education}")
                click.echo(f"    Age range: {art_analysis.target_age_range}")

                # Context
                click.echo(f"\n  {click.style('Context:', fg='cyan')}")
                click.echo(f"    Geographic scope: {art_analysis.geographic_scope}")
                if art_analysis.relevant_industries:
                    click.echo(f"    Industries: {', '.join(art_analysis.relevant_industries)}")

        # Show flash news if requested
        if flash:
            from db import FlashNews, ArticleCluster

            click.echo(f"\n{click.style('Flash News:', bold=True)}")

            # Get flash news through clusters
            flash_items = (
                session.query(FlashNews)
                .join(ArticleCluster)
                .filter(ArticleCluster.article_id == article_id)
                .all()
            )

            if not flash_items:
                click.echo(click.style("  No flash news generated yet", fg="yellow"))
                click.echo(click.style("  Run: news process start -a <id> -t generate_flash_news", fg="yellow"))
            else:
                for fn in flash_items:
                    click.echo(f"\n  {click.style(fn.summary, fg='green')}")

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
@click.option('--domain', '-d', help='Filter by domain')
@click.option('--limit', '-l', type=int, help='Maximum number of articles to fetch')
@click.option('--reindex', is_flag=True, help='Re-process and update articles that already exist')
@click.option('--force-enrichment', is_flag=True, default=False, help='Force re-enrichment even if content hasn\'t changed')
def fetch_cached(domain, limit, reindex, force_enrichment):
    """
    Fetch and process articles from cache.

    Reads cached URLs and processes them into the main database.
    By default, skips articles that already exist in the database.

    --domain: Filter by specific domain.
    --limit: Maximum number of articles to process.
    --reindex: Re-process and update articles that already exist.

    Examples:
        news article fetch-cached
        news article fetch-cached --domain diariolibre.com
        news article fetch-cached --limit 50
        news article fetch-cached --reindex
    """
    from db.cache import CacheDatabase

    cache_db = CacheDatabase()

    # Get cached URLs
    click.echo("Loading cached URLs...")
    cached_entries = cache_db.list_entries(domain=domain, limit=limit if limit else None)

    if not cached_entries:
        if domain:
            click.echo(click.style(f"✗ No cached URLs found for domain '{domain}'", fg="yellow"))
        else:
            click.echo(click.style("✗ No cached URLs found", fg="yellow"))
        return

    total = len(cached_entries)
    click.echo(f"Found {total} cached URL(s)")

    # Filter out redirects (30x status codes) since they don't contain article content
    article_entries = [e for e in cached_entries if not (300 <= e['status_code'] < 400)]
    redirect_count = total - len(article_entries)

    if redirect_count > 0:
        click.echo(f"Skipping {redirect_count} redirect(s)")

    if not article_entries:
        click.echo(click.style("✗ No article URLs to process (all are redirects)", fg="yellow"))
        return

    click.echo(f"\nProcessing {len(article_entries)} article(s)...\n")

    # Statistics
    created = 0
    updated = 0
    skipped = 0
    errors = 0

    db = Database()

    for i, entry in enumerate(article_entries, 1):
        url = entry['url']

        click.echo(f"[{i}/{len(article_entries)}] {url}")

        try:
            # Check if already exists (skip unless --reindex is set)
            if not reindex:
                session = db.get_session()
                try:
                    url_hash = get_url_hash(url)
                    if db.article_exists(session, url=url, hash=url_hash):
                        click.echo(click.style("  ⊘ Already exists, skipping", fg="yellow"))
                        skipped += 1
                        continue
                finally:
                    session.close()

            # Get cached content
            cached = cache_db.get_cached_content(url)
            if not cached:
                click.echo(click.style("  ✗ Cache entry disappeared", fg="red"))
                errors += 1
                continue

            html_content = cached['content']

            # Process article using shared helper (verbose=False for cleaner output)
            result = _process_article_from_html(url, html_content, verbose=False, force_reprocess=force_enrichment)

            if result['success']:
                if result['was_updated']:
                    click.echo(click.style(f"  ↻ Updated (ID: {result['article_id']})", fg="cyan"))
                    updated += 1
                else:
                    click.echo(click.style(f"  ✓ Created (ID: {result['article_id']})", fg="green"))
                    created += 1
            else:
                click.echo(click.style(f"  ✗ {result['error']}", fg="red"))
                errors += 1

        except Exception as e:
            click.echo(click.style(f"  ✗ Error: {e}", fg="red"))
            errors += 1

    # Summary
    total_processed = created + updated
    click.echo(f"\n{click.style('Summary:', bold=True)}")
    if created > 0:
        click.echo(f"  Created: {click.style(str(created), fg='green')}")
    if updated > 0:
        click.echo(f"  Updated: {click.style(str(updated), fg='cyan')}")
    if skipped > 0:
        click.echo(f"  Skipped: {click.style(str(skipped), fg='yellow')}")
    if errors > 0:
        click.echo(f"  Errors: {click.style(str(errors), fg='red')}")

    if total_processed > 0:
        click.echo(click.style(f"\n✓ Successfully processed {total_processed} article(s)!", fg="green"))


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
