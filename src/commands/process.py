"""
Article processing batch commands.
"""

import click
from db import Database, Source, Article, ProcessingBatch, BatchItem, ProcessType


@click.group()
def process():
    """Manage article processing batches."""
    pass


@process.command()
@click.option('--domain', '-d', required=True, help='Domain to process')
@click.option('--type', '-t', 'process_type', type=click.Choice(['enrich_article', 'generate_flash_news']), required=True, help='Type of processing')
@click.option('--size', '-s', type=int, default=10, help='Batch size (default: 10)')
def start(domain, process_type, size):
    """
    Create and start a processing batch for articles from a domain.

    Examples:
        news process start -d diariolibre.com -t enrich_article -s 10
        news process start -d diariolibre.com -t generate_flash_news -s 10
    """
    db = Database()
    session = db.get_session()

    try:
        # Get source
        source = session.query(Source).filter_by(domain=domain).first()
        if not source:
            click.echo(click.style(f"✗ Domain '{domain}' not found", fg="red"))
            return

        # Map process type string to enum and select appropriate articles
        if process_type == 'enrich_article':
            process_type_enum = ProcessType.ENRICH_ARTICLE

            # Get unenriched articles (enriched_at is NULL)
            articles_to_process = (
                session.query(Article)
                .filter(Article.source_id == source.id)
                .filter(Article.enriched_at.is_(None))
                .order_by(Article.created_at.desc())
                .limit(size)
                .all()
            )
            articles_label = "unenriched articles"

        elif process_type == 'generate_flash_news':
            process_type_enum = ProcessType.GENERATE_FLASH_NEWS

            # Get articles with clusters (cluster_enriched_at is NOT NULL)
            articles_to_process = (
                session.query(Article)
                .filter(Article.source_id == source.id)
                .filter(Article.cluster_enriched_at.isnot(None))
                .order_by(Article.created_at.desc())
                .limit(size)
                .all()
            )
            articles_label = "articles with clusters"

        else:
            click.echo(click.style(f"✗ Unknown process type: {process_type}", fg="red"))
            return

        if not articles_to_process:
            click.echo(click.style(f"✗ No {articles_label} found for {domain}", fg="yellow"))
            return

        click.echo(f"Found {len(articles_to_process)} {articles_label}")
        click.echo(f"Creating batch for {domain}...")

        # Create batch and items atomically
        try:
            # Create batch
            batch = ProcessingBatch(
                source_id=source.id,
                process_type=process_type_enum,
                status='pending',
                total_items=len(articles_to_process),
                processed_items=0,
                successful_items=0,
                failed_items=0
            )
            session.add(batch)
            session.flush()

            # Create batch items
            for article in articles_to_process:
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

        click.echo(click.style(f"✓ Batch created (ID: {batch.id}) with {len(articles_to_process)} articles", fg="green"))
        click.echo(f"\nBatch details:")
        click.echo(f"  Source: {domain}")
        click.echo(f"  Type: {process_type}")
        click.echo(f"  Articles: {len(articles_to_process)}")
        click.echo(f"\nNow processing batch...")

        # Process the batch with appropriate processor
        if process_type_enum == ProcessType.ENRICH_ARTICLE:
            from processors.enrich import process_batch
            success = process_batch(batch.id, session)
        elif process_type_enum == ProcessType.GENERATE_FLASH_NEWS:
            from processors.flash_news import process_flash_news_batch
            success = process_flash_news_batch(batch.id, session)
        else:
            click.echo(click.style(f"✗ No processor found for type: {process_type}", fg="red"))
            return

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
        news process list
        news process list --status completed
        news process list --domain diariolibre.com
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
        news process show 1
        news process show 1 --item 5
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
