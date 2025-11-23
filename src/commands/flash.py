"""
Flash news management commands.
"""

import click
from datetime import datetime
from sqlalchemy import func, and_
from db import Database
from db.models import FlashNews, ArticleCluster, Article, Source
from domain.calculate_flash_news_relevance import (
    calculate_flash_news_relevance,
    select_flash_news_for_newsletter
)


@click.group()
def flash():
    """Manage flash news summaries."""
    pass


@flash.command()
@click.option('--article-id', type=int, help='Filter by article ID')
@click.option('--domain', help='Filter by source domain')
@click.option('--published', is_flag=True, help='Show only published flash news')
@click.option('--unpublished', is_flag=True, help='Show only unpublished flash news')
@click.option('--priority', type=click.Choice(['critical', 'high', 'medium', 'low']), help='Filter by priority')
@click.option('--limit', default=50, help='Maximum number of results (default: 50)')
@click.option('--no-pager', is_flag=True, help='Disable pagination')
def list(article_id, domain, published, unpublished, priority, limit, no_pager):
    """
    List flash news with optional filters.

    Example:
        news flash list
        news flash list --published
        news flash list --domain diariolibre.com
        news flash list --article-id 1
        news flash list --priority critical
    """
    db = Database()
    session = db.get_session()

    try:
        # Build query
        query = session.query(
            FlashNews,
            ArticleCluster,
            Article,
            Source
        ).join(
            ArticleCluster, FlashNews.cluster_id == ArticleCluster.id
        ).join(
            Article, ArticleCluster.article_id == Article.id
        ).join(
            Source, Article.source_id == Source.id
        )

        # Apply filters
        if article_id:
            query = query.filter(Article.id == article_id)

        if domain:
            query = query.filter(Source.domain == domain)

        if published and not unpublished:
            query = query.filter(FlashNews.published == 1)
        elif unpublished and not published:
            query = query.filter(FlashNews.published == 0)

        if priority:
            query = query.filter(FlashNews.priority == priority)

        # Order by relevance (if calculated), then creation date
        query = query.order_by(FlashNews.relevance_score.desc().nullslast(), FlashNews.created_at.desc())

        # Execute query with limit
        results = query.limit(limit).all()

        if not results:
            click.echo(click.style("No flash news found", fg="yellow"))
            return

        # Prepare output
        output_lines = []
        output_lines.append(click.style(f"\n=== Flash News ({len(results)} results) ===\n", bold=True))

        for flash, cluster, article, source in results:
            status_color = "green" if flash.published else "yellow"
            status_text = "PUBLISHED" if flash.published else "unpublished"

            # Priority color coding
            priority_colors = {
                'critical': 'red',
                'high': 'yellow',
                'medium': 'cyan',
                'low': 'white'
            }
            priority_text = flash.priority or 'N/A'
            priority_color = priority_colors.get(flash.priority, 'white')

            id_part = click.style(f"[{flash.id}] ", fg="cyan", bold=True)
            status_part = click.style(f"[{status_text}]", fg=status_color)
            priority_part = f" [{click.style(priority_text.upper(), fg=priority_color, bold=True)}]" if flash.priority else ""

            output_lines.append(id_part + status_part + priority_part)
            output_lines.append(f"  Article: [{article.id}] {article.title[:70]}...")
            output_lines.append(f"  Source: {source.domain}")
            output_lines.append(f"  Cluster: {cluster.cluster_label} ({cluster.category.value}, score={cluster.score:.2f})")

            # Show relevance if calculated
            if flash.relevance_score is not None:
                output_lines.append(f"  Relevance: {flash.relevance_score:.4f}")

            output_lines.append(f"  Summary: {flash.summary[:100]}...")
            output_lines.append(f"  Created: {flash.created_at}")
            output_lines.append("")

        output_text = "\n".join(output_lines)

        # Use pager if results are many and pager is not disabled
        if len(results) > 20 and not no_pager:
            click.echo_via_pager(output_text)
        else:
            click.echo(output_text)

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"))
        raise click.Abort()
    finally:
        session.close()


@flash.command()
@click.argument('flash_id', type=int)
def show(flash_id):
    """
    Show detailed information about a specific flash news.

    Example:
        news flash show 1
    """
    db = Database()
    session = db.get_session()

    try:
        # Query flash news with related data
        result = session.query(
            FlashNews,
            ArticleCluster,
            Article,
            Source
        ).join(
            ArticleCluster, FlashNews.cluster_id == ArticleCluster.id
        ).join(
            Article, ArticleCluster.article_id == Article.id
        ).join(
            Source, Article.source_id == Source.id
        ).filter(
            FlashNews.id == flash_id
        ).first()

        if not result:
            click.echo(click.style(f"✗ Flash news #{flash_id} not found", fg="red"))
            raise click.Abort()

        flash, cluster, article, source = result

        # Display information
        click.echo(click.style(f"\n=== Flash News #{flash.id} ===\n", bold=True))

        status_color = "green" if flash.published else "yellow"
        status_text = "PUBLISHED" if flash.published else "UNPUBLISHED"
        click.echo(f"Status: {click.style(status_text, fg=status_color, bold=True)}")
        click.echo(f"Created: {flash.created_at}")
        click.echo(f"Updated: {flash.updated_at}")

        click.echo(click.style("\nSummary:", bold=True))
        click.echo(flash.summary)

        click.echo(click.style("\nSource Article:", bold=True))
        click.echo(f"  ID: {article.id}")
        click.echo(f"  Title: {article.title}")
        click.echo(f"  URL: {article.url}")
        click.echo(f"  Source: {source.domain}")
        click.echo(f"  Published: {article.published_date or 'N/A'}")

        click.echo(click.style("\nCluster Information:", bold=True))
        click.echo(f"  ID: {cluster.id}")
        click.echo(f"  Label: {cluster.cluster_label}")
        click.echo(f"  Category: {cluster.category.value}")
        click.echo(f"  Score: {cluster.score:.4f}")
        click.echo(f"  Size: {cluster.size} sentences")

        # Show relevance information if calculated
        if flash.relevance_score is not None:
            click.echo(click.style("\nRelevance Information:", bold=True))
            click.echo(f"  Score: {click.style(f'{flash.relevance_score:.4f}', fg='cyan', bold=True)}")
            if flash.priority:
                priority_colors = {'critical': 'red', 'high': 'yellow', 'medium': 'cyan', 'low': 'white'}
                priority_color = priority_colors.get(flash.priority, 'white')
                click.echo(f"  Priority: {click.style(flash.priority.upper(), fg=priority_color, bold=True)}")
            if flash.relevance_calculated_at:
                click.echo(f"  Calculated: {flash.relevance_calculated_at}")

            # Show component breakdown if available
            if flash.relevance_components:
                click.echo(click.style("\n  Component Breakdown:", bold=True))
                for component, value in flash.relevance_components.items():
                    click.echo(f"    {component}: {value:.4f}")

        # Get sentences in cluster
        if cluster.sentence_indices:
            from db.models import ArticleSentence
            sentences = session.query(ArticleSentence).filter(
                ArticleSentence.cluster_id == cluster.id
            ).order_by(ArticleSentence.sentence_index).all()

            if sentences:
                click.echo(click.style("\nCluster Sentences:", bold=True))
                for sent in sentences:
                    click.echo(f"  [{sent.sentence_index}] {sent.sentence_text}")

        click.echo()

    except Exception as e:
        if "not found" not in str(e):
            click.echo(click.style(f"✗ Error: {e}", fg="red"))
        raise click.Abort()
    finally:
        session.close()


@flash.command(name='publish-id')
@click.argument('flash_ids', nargs=-1, type=int, required=True)
def publish_id(flash_ids):
    """
    Mark one or more flash news as published by ID.

    Example:
        news flash publish-id 1
        news flash publish-id 1 2 3
        news flash publish-id 14 15 16
    """
    db = Database()
    session = db.get_session()

    try:
        published_count = 0
        already_published_count = 0
        not_found = []

        for flash_id in flash_ids:
            flash = session.query(FlashNews).filter(FlashNews.id == flash_id).first()

            if not flash:
                not_found.append(flash_id)
                continue

            if flash.published:
                already_published_count += 1
                continue

            flash.published = 1
            flash.updated_at = datetime.utcnow()
            published_count += 1

        session.commit()

        # Display results
        if published_count > 0:
            click.echo(click.style(f"✓ Published {published_count} flash news", fg="green"))

        if already_published_count > 0:
            click.echo(click.style(f"⚠ {already_published_count} already published", fg="yellow"))

        if not_found:
            ids_str = ', '.join(map(str, not_found))
            click.echo(click.style(f"✗ Not found: {ids_str}", fg="red"))

        if not published_count and not already_published_count and not_found:
            raise click.Abort()

    except Exception as e:
        session.rollback()
        if "Not found" not in str(e):
            click.echo(click.style(f"✗ Error: {e}", fg="red"))
        raise click.Abort()
    finally:
        session.close()


@flash.command(name='unpublish-id')
@click.argument('flash_ids', nargs=-1, type=int, required=True)
def unpublish_id(flash_ids):
    """
    Mark one or more flash news as unpublished by ID.

    Example:
        news flash unpublish-id 1
        news flash unpublish-id 1 2 3
        news flash unpublish-id 14 15 16
    """
    db = Database()
    session = db.get_session()

    try:
        unpublished_count = 0
        already_unpublished_count = 0
        not_found = []

        for flash_id in flash_ids:
            flash = session.query(FlashNews).filter(FlashNews.id == flash_id).first()

            if not flash:
                not_found.append(flash_id)
                continue

            if not flash.published:
                already_unpublished_count += 1
                continue

            flash.published = 0
            flash.updated_at = datetime.utcnow()
            unpublished_count += 1

        session.commit()

        # Display results
        if unpublished_count > 0:
            click.echo(click.style(f"✓ Unpublished {unpublished_count} flash news", fg="green"))

        if already_unpublished_count > 0:
            click.echo(click.style(f"⚠ {already_unpublished_count} already unpublished", fg="yellow"))

        if not_found:
            ids_str = ', '.join(map(str, not_found))
            click.echo(click.style(f"✗ Not found: {ids_str}", fg="red"))

        if not unpublished_count and not already_unpublished_count and not_found:
            raise click.Abort()

    except Exception as e:
        session.rollback()
        if "Not found" not in str(e):
            click.echo(click.style(f"✗ Error: {e}", fg="red"))
        raise click.Abort()
    finally:
        session.close()


@flash.command()
@click.option('--domain', help='Filter by source domain')
def stats(domain):
    """
    Show flash news statistics.

    Example:
        news flash stats
        news flash stats --domain diariolibre.com
    """
    db = Database()
    session = db.get_session()

    try:
        # Base query
        query = session.query(FlashNews).join(
            ArticleCluster, FlashNews.cluster_id == ArticleCluster.id
        ).join(
            Article, ArticleCluster.article_id == Article.id
        ).join(
            Source, Article.source_id == Source.id
        )

        # Apply domain filter if specified
        if domain:
            query = query.filter(Source.domain == domain)
            domain_filter_text = f" for {domain}"
        else:
            domain_filter_text = ""

        # Get counts
        total = query.count()
        published = query.filter(FlashNews.published == 1).count()
        unpublished = query.filter(FlashNews.published == 0).count()

        # Get flash news per domain
        domain_stats = session.query(
            Source.domain,
            func.count(FlashNews.id).label('count'),
            func.sum(FlashNews.published).label('published_count')
        ).select_from(FlashNews).join(
            ArticleCluster, FlashNews.cluster_id == ArticleCluster.id
        ).join(
            Article, ArticleCluster.article_id == Article.id
        ).join(
            Source, Article.source_id == Source.id
        )

        if domain:
            domain_stats = domain_stats.filter(Source.domain == domain)

        domain_stats = domain_stats.group_by(Source.domain).all()

        # Display statistics
        click.echo(click.style(f"\n=== Flash News Statistics{domain_filter_text} ===\n", bold=True))

        click.echo(f"Total flash news: {click.style(str(total), fg='cyan', bold=True)}")
        click.echo(f"  Published: {click.style(str(published), fg='green')} ({published/total*100 if total > 0 else 0:.1f}%)")
        click.echo(f"  Unpublished: {click.style(str(unpublished), fg='yellow')} ({unpublished/total*100 if total > 0 else 0:.1f}%)")

        if domain_stats:
            click.echo(click.style("\nBy Domain:", bold=True))
            for dom, count, pub_count in domain_stats:
                pub_count = pub_count or 0
                unpub_count = count - pub_count
                click.echo(f"  {dom}:")
                click.echo(f"    Total: {count}")
                click.echo(f"    Published: {click.style(str(pub_count), fg='green')} | Unpublished: {click.style(str(unpub_count), fg='yellow')}")

        click.echo()

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"))
        raise click.Abort()
    finally:
        session.close()


@flash.command(name='calculate-relevance')
@click.option('--flash-id', type=int, help='Calculate for specific flash news only')
@click.option('--recalculate-all', is_flag=True, help='Recalculate all flash news (even if already calculated)')
@click.option('--time-window', type=int, default=24, help='Time window in hours for topic diversity (default: 24)')
@click.option('--show-stats', is_flag=True, help='Show detailed statistics')
def calculate_relevance(flash_id, recalculate_all, time_window, show_stats):
    """
    Calculate relevance scores for flash news.

    Example:
        news flash calculate-relevance
        news flash calculate-relevance --recalculate-all
        news flash calculate-relevance --flash-id 1
        news flash calculate-relevance --time-window 48 --show-stats
    """
    db = Database()
    session = db.get_session()

    try:
        click.echo(click.style("\n🔄 Calculating flash news relevance...\n", bold=True))

        # Calculate relevance
        result = calculate_flash_news_relevance(
            db=db,
            session=session,
            flash_news_id=flash_id,
            recalculate_all=recalculate_all,
            time_window_hours=time_window
        )

        # Display results
        click.echo(click.style("✅ Relevance calculation complete!\n", fg="green", bold=True))
        updated_text = click.style(str(result['updated']), fg='cyan', bold=True)
        click.echo(f"  Flash news processed: {updated_text}")
        click.echo(f"  Processing time: {result['processing_time']:.2f}s")

        # Show priority breakdown
        if result['by_priority']:
            click.echo(click.style("\n📊 By Priority:", bold=True))
            priority_colors = {'critical': 'red', 'high': 'yellow', 'medium': 'cyan', 'low': 'white'}
            for priority, count in sorted(result['by_priority'].items(), key=lambda x: ['critical', 'high', 'medium', 'low'].index(x[0])):
                color = priority_colors.get(priority, 'white')
                click.echo(f"  {click.style(priority.upper(), fg=color, bold=True)}: {count}")

        # Show detailed stats if requested
        if show_stats and result['updated'] > 0:
            click.echo(click.style("\n💡 View results with:", bold=True))
            click.echo("  news flash list --priority critical")
            click.echo("  news flash list --priority high")
            click.echo("  news flash show <id>")

        click.echo()

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"))
        raise click.Abort()
    finally:
        session.close()


@flash.command(name='publish')
@click.option('--min', 'min_count', type=int, default=1, help='Minimum number of flash news to publish (default: 1)')
@click.option('--max', 'max_count', type=int, default=5, help='Maximum number of flash news, unless all exceed high-score (default: 5)')
@click.option('--low-score', type=float, default=0.55, help='Minimum score for normal publication (default: 0.55)')
@click.option('--high-score', type=float, default=0.75, help='Score to bypass max limit (default: 0.75)')
@click.option('--max-per-source', type=int, default=1, help='Maximum flash news per source (default: 1)')
@click.option('--calculate', is_flag=True, help='Calculate relevance before selecting (auto-calculates missing scores)')
@click.option('--dry-run', is_flag=True, help='Preview selection without publishing')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed scoring breakdown for each flash news')
def publish(min_count, max_count, low_score, high_score, max_per_source, calculate, dry_run, verbose):
    """
    Select and publish multiple flash news for newsletter with flexible criteria.

    Publishes by default unless --dry-run is used.

    Selection rules:
    - CRITICAL (>= high-score): Always publish, even if exceeds --max
    - NORMAL (low-score to high-score): Publish if space available
    - FILLER (< low-score): Only publish to reach --min
    - Diversify: no more than max-per-source per source

    Requires relevance scores to be calculated first. Use --calculate to auto-calculate
    missing scores, or run 'news flash calculate-relevance' separately.

    Example:
        news flash publish --calculate              # Auto-calculate & publish
        news flash publish --dry-run                # Preview (requires scores)
        news flash publish --min 2 --max 10         # Adjust quantity
        news flash publish --low-score 0.6 --high-score 0.8  # Adjust thresholds
        news flash publish --calculate --dry-run -v # Full workflow preview
    """
    db = Database()
    session = db.get_session()

    try:
        click.echo(click.style("\n📬 Selecting flash news for newsletter...\n", bold=True))

        # Calculate relevance if requested
        if calculate:
            # Step 1: Calculate PageRank for entities
            click.echo(click.style("🔄 Calculating entity PageRank...\n", bold=True))

            from domain.calculate_global_relevance import calculate_global_relevance

            pagerank_result = calculate_global_relevance(db=db, session=session)
            entities_updated = pagerank_result.get('entities_updated', 0)

            if entities_updated > 0:
                click.echo(click.style(f"✅ Updated PageRank for {entities_updated} entities\n", fg="green"))
            else:
                click.echo(click.style("✅ Entity PageRank already up to date\n", fg="green"))

            # Step 2: Calculate flash news relevance
            click.echo(click.style("🔄 Calculating flash news relevance scores...\n", bold=True))

            result = calculate_flash_news_relevance(
                db=db,
                session=session,
                recalculate_all=False
            )

            if result['updated'] > 0:
                click.echo(click.style(f"✅ Calculated relevance for {result['updated']} flash news\n", fg="green"))
            else:
                click.echo(click.style("✅ All flash news already have relevance scores\n", fg="green"))

        # Check for flash news without relevance
        uncalculated = session.query(FlashNews).filter(
            FlashNews.published == 0,
            FlashNews.relevance_calculated_at.is_(None)
        ).count()

        if uncalculated > 0:
            error_msg = f"⚠️  {uncalculated} flash news without relevance scores.\n\n"
            error_msg += "Options:\n"
            error_msg += "  1. Run with --calculate flag:\n"
            error_msg += f"     news flash publish --calculate\n\n"
            error_msg += "  2. Calculate separately first:\n"
            error_msg += f"     news flash calculate-relevance"
            click.echo(click.style(error_msg, fg="yellow"))
            raise click.Abort()

        # Show selection criteria
        click.echo(click.style("Selection criteria:", bold=True))
        click.echo(f"  Min count: {click.style(str(min_count), fg='cyan')}")
        click.echo(f"  Max count: {click.style(str(max_count), fg='cyan')} (bypassed by CRITICAL >= {high_score})")
        click.echo(f"  Low score: {click.style(f'{low_score:.2f}', fg='yellow')} (normal publication threshold)")
        click.echo(f"  High score: {click.style(f'{high_score:.2f}', fg='red')} (CRITICAL, bypasses max)")
        click.echo(f"  Max per source: {max_per_source}\n")

        # Determine if we should publish (default True, False if dry_run)
        mark_published = not dry_run

        if dry_run:
            click.echo(click.style("🔍 DRY RUN MODE - No changes will be made\n", fg="yellow"))

        # Select flash news
        selected = select_flash_news_for_newsletter(
            session=session,
            min_count=min_count,
            max_count=max_count,
            low_score=low_score,
            high_score=high_score,
            max_per_source=max_per_source,
            mark_as_published=mark_published
        )

        if not selected:
            click.echo(click.style("⚠️  No flash news found", fg="yellow"))
            click.echo(f"\n  Try calculating relevance first:")
            click.echo(f"    news flash calculate-relevance")
            click.echo()
            return

        # Categorize selected for display
        critical_selected = [fn for fn in selected if fn.relevance_score >= high_score]
        normal_selected = [fn for fn in selected if low_score <= fn.relevance_score < high_score]
        filler_selected = [fn for fn in selected if fn.relevance_score < low_score]

        # Display selected flash news with category info
        result_msg = f"✅ Selected {len(selected)} flash news for newsletter"
        if critical_selected:
            result_msg += f" ({len(critical_selected)} CRITICAL"
            if len(critical_selected) > max_count:
                result_msg += f", exceeded max by {len(critical_selected) - max_count}"
            result_msg += ")"
        click.echo(click.style(f"{result_msg}:\n", fg="green", bold=True))

        # Group by source for display
        by_source = {}
        for fn in selected:
            source_domain = fn.cluster.article.source.domain
            if source_domain not in by_source:
                by_source[source_domain] = []
            by_source[source_domain].append(fn)

        # Display grouped by selection category
        categories = [
            ('CRITICAL', critical_selected, 'red'),
            ('NORMAL', normal_selected, 'yellow'),
            ('FILLER', filler_selected, 'white')
        ]

        for category_name, category_items, color in categories:
            if not category_items:
                continue

            click.echo(click.style(f"[{category_name}]", fg=color, bold=True))

            for fn in category_items:
                article = fn.cluster.article
                source = article.source
                score_text = click.style(f'{fn.relevance_score:.4f}', fg='cyan')
                click.echo(f"  [{fn.id}] {score_text} | {source.domain}")

                if verbose:
                    # Show detailed component breakdown
                    if fn.relevance_components:
                        click.echo("      Components:")
                        for comp_name, comp_value in fn.relevance_components.items():
                            # Format component name for display
                            display_name = comp_name.replace('_', ' ').title()
                            value_text = click.style(f'{comp_value:.4f}', fg='white')
                            click.echo(f"        • {display_name}: {value_text}")

                    # Show article info
                    click.echo(f"      Article: [{article.id}] {article.title[:60]}...")
                    if article.published_date:
                        hours_old = (datetime.utcnow() - article.published_date).total_seconds() / 3600
                        click.echo(f"      Age: {hours_old:.1f} hours old")

                click.echo(f"      {fn.summary[:80]}...")

                if verbose:
                    click.echo()  # Extra spacing in verbose mode

            click.echo()

        # Show source distribution
        click.echo(click.style("📊 Distribution by source:", bold=True))
        for source, items in sorted(by_source.items()):
            click.echo(f"  {source}: {len(items)} flash news")

        # Show category summary
        click.echo(click.style("\n📈 Selection summary:", bold=True))
        if critical_selected:
            click.echo(f"  {click.style('CRITICAL', fg='red', bold=True)}: {len(critical_selected)} (score >= {high_score})")
        if normal_selected:
            click.echo(f"  {click.style('NORMAL', fg='yellow', bold=True)}: {len(normal_selected)} ({low_score} <= score < {high_score})")
        if filler_selected:
            click.echo(f"  {click.style('FILLER', fg='white', bold=True)}: {len(filler_selected)} (score < {low_score}, used to reach min)")

        # Show action taken
        if mark_published:
            click.echo(click.style(f"\n✅ Published {len(selected)} flash news", fg="green", bold=True))
        else:
            click.echo(click.style("\n💡 To publish for real, run without --dry-run:", bold=True))
            click.echo("  news flash publish")

        click.echo()

    except Exception as e:
        session.rollback()
        click.echo(click.style(f"✗ Error: {e}", fg="red"))
        raise click.Abort()
    finally:
        session.close()
