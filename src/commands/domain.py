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
@click.option('--no-pager', is_flag=True, help='Disable pagination')
def list(no_pager):
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

        # Build output
        output_lines = ["Registered news sources:\n"]
        for source in sources:
            article_count = len(source.articles)
            output_lines.append(f"[{source.id}] {source.domain}")
            output_lines.append(f"    Name: {source.name}")
            output_lines.append(f"    Articles: {article_count}")
            output_lines.append(f"    Created: {source.created_at}")
            output_lines.append("")

        output_text = "\n".join(output_lines)

        # Use pager if more than 20 results and not disabled
        if len(sources) > 20 and not no_pager:
            click.echo_via_pager(output_text)
        else:
            click.echo(output_text)

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
@click.option('--clusters', is_flag=True, help='Include cluster statistics')
def stats(clusters):
    """
    Show statistics about all sources.

    Examples:
        news domain stats
        news domain stats --clusters
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
        total_enriched = 0
        total_pending = 0

        for source in sorted(sources, key=lambda s: len(s.articles), reverse=True):
            count = len(source.articles)
            enriched = len([a for a in source.articles if a.enriched_at])
            pending = count - enriched

            total_articles += count
            total_enriched += enriched
            total_pending += pending

            click.echo(f"{source.domain:30} {count:5} articles ({click.style(str(enriched), fg='green')} enriched, {click.style(str(pending), fg='yellow')} pending)")

        click.echo(f"\n{'Total':30} {total_articles:5} articles")
        click.echo(f"{'Enriched':30} {click.style(str(total_enriched), fg='green'):5} articles")
        click.echo(f"{'Pending enrichment':30} {click.style(str(total_pending), fg='yellow'):5} articles")
        click.echo(f"{'Sources':30} {len(sources):5}")

        # Show cluster statistics if requested
        if clusters:
            from db import ArticleCluster, ClusterCategory

            click.echo(click.style("\n=== Cluster Statistics ===\n", fg="cyan", bold=True))

            # Count articles with clusters
            cluster_enriched_articles = session.query(Article).filter(
                Article.cluster_enriched_at.isnot(None)
            ).count()

            click.echo(f"{'Articles with clusters':30} {click.style(str(cluster_enriched_articles), fg='green'):5}")
            click.echo(f"{'Pending clustering':30} {click.style(str(total_articles - cluster_enriched_articles), fg='yellow'):5}")

            if cluster_enriched_articles > 0:
                # Total clusters
                total_clusters = session.query(ArticleCluster).count()

                # Clusters by category
                core_clusters = session.query(ArticleCluster).filter_by(
                    category=ClusterCategory.CORE
                ).count()
                secondary_clusters = session.query(ArticleCluster).filter_by(
                    category=ClusterCategory.SECONDARY
                ).count()
                filler_clusters = session.query(ArticleCluster).filter_by(
                    category=ClusterCategory.FILLER
                ).count()

                # Average clusters per article
                avg_clusters = total_clusters / cluster_enriched_articles

                click.echo(f"\n{'Total clusters':30} {total_clusters:5}")
                click.echo(f"{'Avg clusters/article':30} {avg_clusters:5.1f}")
                click.echo(f"{'Core clusters':30} {click.style(str(core_clusters), fg='green'):5} ({100*core_clusters/total_clusters if total_clusters > 0 else 0:.1f}%)")
                click.echo(f"{'Secondary clusters':30} {click.style(str(secondary_clusters), fg='yellow'):5} ({100*secondary_clusters/total_clusters if total_clusters > 0 else 0:.1f}%)")
                click.echo(f"{'Filler clusters':30} {click.style(str(filler_clusters), fg='white'):5} ({100*filler_clusters/total_clusters if total_clusters > 0 else 0:.1f}%)")

    finally:
        session.close()


@domain.group()
def process():
    """Manage article processing batches."""
    pass


@process.command()
@click.option('--domain', '-d', required=True, help='Domain to process')
@click.option('--type', '-t', 'process_type', type=click.Choice(['enrich_article']), required=True, help='Type of processing')
@click.option('--size', '-s', type=int, default=10, help='Batch size (default: 10)')
def start(domain, process_type, size):
    """
    Create and start a processing batch for articles from a domain.

    Example:
        news domain process start -d diariolibre.com -t enrich_article -s 10
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
        process_type_enum = ProcessType.ENRICH_ARTICLE

        # Get unenriched articles (enriched_at is NULL), ordered by most recent first
        unenriched = (
            session.query(Article)
            .filter(Article.source_id == source.id)
            .filter(Article.enriched_at.is_(None))
            .order_by(Article.created_at.desc())
            .limit(size)
            .all()
        )

        if not unenriched:
            click.echo(click.style(f"✗ No unenriched articles found for {domain}", fg="yellow"))
            return

        click.echo(f"Found {len(unenriched)} unenriched articles")
        click.echo(f"Creating batch for {domain}...")

        # Create batch and items atomically
        try:
            # Create batch
            batch = ProcessingBatch(
                source_id=source.id,
                process_type=process_type_enum,
                status='pending',
                total_items=len(unenriched),
                processed_items=0,
                successful_items=0,
                failed_items=0
            )
            session.add(batch)
            session.flush()

            # Create batch items
            for article in unenriched:
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

        click.echo(click.style(f"✓ Batch created (ID: {batch.id}) with {len(unenriched)} articles", fg="green"))
        click.echo(f"\nBatch details:")
        click.echo(f"  Source: {domain}")
        click.echo(f"  Type: {process_type}")
        click.echo(f"  Articles: {len(unenriched)}")
        click.echo(f"\nNow processing batch...")

        # Process the batch
        from processors.enrich import process_batch
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


@process.command()
@click.option('--limit', '-l', type=int, default=20, help='Number of batches to show (default: 20)')
@click.option('--status', '-s', type=click.Choice(['pending', 'processing', 'completed', 'failed']), help='Filter by status')
@click.option('--domain', '-d', help='Filter by domain')
@click.option('--no-pager', is_flag=True, help='Disable pagination')
def list(limit, status, domain, no_pager):
    """
    List processing batches.

    Example:
        news domain process list
        news domain process list --status completed
        news domain process list --domain diariolibre.com
    """
    db = Database()
    session = db.get_session()

    try:
        query = session.query(ProcessingBatch).join(Source)

        # Apply filters
        if status:
            query = query.filter(ProcessingBatch.status == status)
        if domain:
            query = query.filter(Source.domain == domain)

        # Order by most recent first
        batches = query.order_by(ProcessingBatch.created_at.desc()).limit(limit).all()

        if not batches:
            click.echo(click.style("No batches found", fg="yellow"))
            return

        # Build output
        output_lines = [click.style("\n=== Processing Batches ===\n", fg="cyan", bold=True)]

        for batch in batches:
            # Status color
            status_color = {
                'pending': 'yellow',
                'processing': 'blue',
                'completed': 'green',
                'failed': 'red'
            }.get(batch.status, 'white')

            output_lines.append(f"[{batch.id}] {batch.source.domain} - {batch.process_type.value}")
            output_lines.append(f"    Status: {click.style(batch.status, fg=status_color)}")
            output_lines.append(f"    Items: {batch.successful_items}/{batch.total_items} successful, {batch.failed_items} failed")
            output_lines.append(f"    Created: {batch.created_at}")
            if batch.started_at:
                output_lines.append(f"    Started: {batch.started_at}")
            if batch.completed_at:
                output_lines.append(f"    Completed: {batch.completed_at}")
            output_lines.append("")

        output_text = "\n".join(output_lines)

        # Use pager if more than 20 results and not disabled
        if len(batches) > 20 and not no_pager:
            click.echo_via_pager(output_text)
        else:
            click.echo(output_text)

    finally:
        session.close()


@process.command()
@click.argument('batch_id', type=int)
@click.option('--item', '-i', type=int, help='Show detailed logs for a specific item')
def show(batch_id, item):
    """
    Show detailed information about a processing batch.

    Examples:
        news domain process show 1
        news domain process show 1 --item 5
    """
    db = Database()
    session = db.get_session()

    try:
        batch = session.query(ProcessingBatch).filter_by(id=batch_id).first()

        if not batch:
            click.echo(click.style(f"✗ Batch {batch_id} not found", fg="red"))
            return

        # If --item is specified, show item details
        if item:
            batch_item = session.query(BatchItem).filter_by(id=item, batch_id=batch_id).first()

            if not batch_item:
                click.echo(click.style(f"✗ Item {item} not found in batch {batch_id}", fg="red"))
                return

            # Status color
            status_color = {
                'pending': 'yellow',
                'processing': 'blue',
                'completed': 'green',
                'failed': 'red',
                'skipped': 'cyan'
            }.get(batch_item.status, 'white')

            click.echo(click.style(f"\n=== Batch Item #{batch_item.id} ===\n", fg="cyan", bold=True))
            click.echo(f"Batch: {batch_id}")
            click.echo(f"Article: {batch_item.article_id}")
            click.echo(f"Status: {click.style(batch_item.status, fg=status_color)}")

            if batch_item.started_at:
                click.echo(f"\nStarted: {batch_item.started_at}")
            if batch_item.completed_at:
                click.echo(f"Completed: {batch_item.completed_at}")
                if batch_item.started_at:
                    duration = (batch_item.completed_at - batch_item.started_at).total_seconds()
                    click.echo(f"Duration: {duration:.2f} seconds")

            click.echo(f"\nCreated: {batch_item.created_at}")
            click.echo(f"Updated: {batch_item.updated_at}")

            # Show statistics if available
            if batch_item.stats:
                click.echo(f"\n{click.style('Statistics:', bold=True)}")
                for key, value in batch_item.stats.items():
                    click.echo(f"  {key}: {value}")

            # Show error message if failed
            if batch_item.error_message:
                click.echo(f"\n{click.style('Error:', fg='red', bold=True)}")
                click.echo(f"  {batch_item.error_message}")

            # Show logs
            if batch_item.logs:
                click.echo(f"\n{click.style('Processing Logs:', bold=True)}")
                click.echo("-" * 80)
                # Logs are stored with \\n, need to replace with actual newlines
                logs_formatted = batch_item.logs.replace('\\n', '\n')
                click.echo(logs_formatted)
                click.echo("-" * 80)

            return

        # Show batch summary (original behavior)
        # Status color
        status_color = {
            'pending': 'yellow',
            'processing': 'blue',
            'completed': 'green',
            'failed': 'red'
        }.get(batch.status, 'white')

        click.echo(click.style(f"\n=== Batch #{batch.id} ===\n", fg="cyan", bold=True))
        click.echo(f"Source: {batch.source.domain}")
        click.echo(f"Type: {batch.process_type.value}")
        click.echo(f"Status: {click.style(batch.status, fg=status_color)}")
        click.echo(f"\nProgress:")
        click.echo(f"  Total items: {batch.total_items}")
        click.echo(f"  Processed: {batch.processed_items}")
        click.echo(f"  Successful: {click.style(str(batch.successful_items), fg='green')}")
        click.echo(f"  Failed: {click.style(str(batch.failed_items), fg='red')}")

        if batch.started_at:
            click.echo(f"\nStarted: {batch.started_at}")
        if batch.completed_at:
            click.echo(f"Completed: {batch.completed_at}")
            duration = (batch.completed_at - batch.started_at).total_seconds()
            click.echo(f"Duration: {duration:.2f} seconds")

        click.echo(f"\nCreated: {batch.created_at}")
        click.echo(f"Updated: {batch.updated_at}")

        # Show statistics if available
        if batch.stats:
            click.echo(f"\n{click.style('Statistics:', bold=True)}")
            for key, value in batch.stats.items():
                click.echo(f"  {key}: {value}")

        # Show error message if failed
        if batch.error_message:
            click.echo(f"\n{click.style('Error:', fg='red', bold=True)}")
            click.echo(f"  {batch.error_message}")

        # Show items summary
        click.echo(f"\n{click.style('Items:', bold=True)}")
        items = session.query(BatchItem).filter_by(batch_id=batch_id).all()

        status_counts = {}
        for item in items:
            status_counts[item.status] = status_counts.get(item.status, 0) + 1

        for status, count in status_counts.items():
            click.echo(f"  {status}: {count}")

        # Show failed items if any
        failed_items = [item for item in items if item.status == 'failed']
        if failed_items:
            click.echo(f"\n{click.style('Failed Items:', fg='red', bold=True)}")
            for item in failed_items[:5]:  # Show first 5
                click.echo(f"  Item #{item.id} - Article {item.article_id}: {item.error_message}")
            if len(failed_items) > 5:
                click.echo(f"  ... and {len(failed_items) - 5} more")
            click.echo(f"\nUse --item <id> to see detailed logs for a specific item")

    finally:
        session.close()
