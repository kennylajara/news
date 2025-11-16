"""
Domain/source management commands.
"""

import click
from datetime import datetime
from db import Database, Source, Article


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
