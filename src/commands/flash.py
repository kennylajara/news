"""
Flash news management commands.
"""

import click
from datetime import datetime
from sqlalchemy import func, and_
from db import Database
from db.models import FlashNews, ArticleCluster, Article, Source


@click.group()
def flash():
    """Manage flash news summaries."""
    pass


@flash.command()
@click.option('--article-id', type=int, help='Filter by article ID')
@click.option('--domain', help='Filter by source domain')
@click.option('--published', is_flag=True, help='Show only published flash news')
@click.option('--unpublished', is_flag=True, help='Show only unpublished flash news')
@click.option('--limit', default=50, help='Maximum number of results (default: 50)')
@click.option('--no-pager', is_flag=True, help='Disable pagination')
def list(article_id, domain, published, unpublished, limit, no_pager):
    """
    List flash news with optional filters.

    Example:
        news flash list
        news flash list --published
        news flash list --domain diariolibre.com
        news flash list --article-id 1
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

        # Order by creation date (newest first)
        query = query.order_by(FlashNews.created_at.desc())

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

            output_lines.append(click.style(f"[{flash.id}] ", fg="cyan", bold=True) +
                              click.style(f"[{status_text}]", fg=status_color))
            output_lines.append(f"  Article: [{article.id}] {article.title[:70]}...")
            output_lines.append(f"  Source: {source.domain}")
            output_lines.append(f"  Cluster: {cluster.cluster_label} ({cluster.category}, score={cluster.score:.2f})")
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
        click.echo(f"  Category: {cluster.category}")
        click.echo(f"  Score: {cluster.score:.4f}")
        click.echo(f"  Size: {cluster.size} sentences")

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


@flash.command()
@click.argument('flash_id', type=int)
def publish(flash_id):
    """
    Mark a flash news as published.

    Example:
        news flash publish 1
    """
    db = Database()
    session = db.get_session()

    try:
        flash = session.query(FlashNews).filter(FlashNews.id == flash_id).first()

        if not flash:
            click.echo(click.style(f"✗ Flash news #{flash_id} not found", fg="red"))
            raise click.Abort()

        if flash.published:
            click.echo(click.style(f"Flash news #{flash_id} is already published", fg="yellow"))
            return

        flash.published = 1
        flash.updated_at = datetime.utcnow()
        session.commit()

        click.echo(click.style(f"✓ Flash news #{flash_id} marked as published", fg="green"))

    except Exception as e:
        session.rollback()
        if "not found" not in str(e):
            click.echo(click.style(f"✗ Error: {e}", fg="red"))
        raise click.Abort()
    finally:
        session.close()


@flash.command()
@click.argument('flash_id', type=int)
def unpublish(flash_id):
    """
    Mark a flash news as unpublished.

    Example:
        news flash unpublish 1
    """
    db = Database()
    session = db.get_session()

    try:
        flash = session.query(FlashNews).filter(FlashNews.id == flash_id).first()

        if not flash:
            click.echo(click.style(f"✗ Flash news #{flash_id} not found", fg="red"))
            raise click.Abort()

        if not flash.published:
            click.echo(click.style(f"Flash news #{flash_id} is already unpublished", fg="yellow"))
            return

        flash.published = 0
        flash.updated_at = datetime.utcnow()
        session.commit()

        click.echo(click.style(f"✓ Flash news #{flash_id} marked as unpublished", fg="green"))

    except Exception as e:
        session.rollback()
        if "not found" not in str(e):
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
