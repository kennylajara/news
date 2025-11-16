"""
Entity management commands.
"""

import click
from db import Database, NamedEntity, Article, EntityType
from db.models import article_entities
from sqlalchemy import select, func


@click.group()
def entity():
    """Manage named entities."""
    pass


@entity.command()
@click.option('--limit', '-l', type=int, default=20, help='Number of entities to show (default: 20)')
@click.option('--type', '-t', 'entity_type', help='Filter by entity type')
@click.option('--min-relevance', '-r', type=int, help='Minimum global relevance score')
@click.option('--no-pager', is_flag=True, help='Disable pagination')
def list(limit, entity_type, min_relevance, no_pager):
    """
    List named entities with filters.

    Examples:
        news entity list
        news entity list --limit 50
        news entity list --type person
        news entity list --min-relevance 5
        news entity list --type org --min-relevance 10
    """
    db = Database()
    session = db.get_session()

    try:
        # Build query
        query = session.query(NamedEntity)

        # Apply filters
        if entity_type:
            # Validate entity type
            try:
                type_enum = EntityType[entity_type.upper()]
                query = query.filter(NamedEntity.entity_type == type_enum)
            except KeyError:
                valid_types = ', '.join([t.name.lower() for t in EntityType])
                click.echo(click.style(f"✗ Invalid entity type. Valid types: {valid_types}", fg="red"))
                return

        if min_relevance:
            query = query.filter(NamedEntity.relevance >= min_relevance)

        # Order by relevance and limit
        entities = query.order_by(NamedEntity.relevance.desc()).limit(limit).all()

        # Build header
        header_parts = []
        if entity_type:
            header_parts.append(f"Type: {entity_type}")
        if min_relevance:
            header_parts.append(f"Min relevance: {min_relevance}")

        if header_parts:
            header = f"Entities ({', '.join(header_parts)}):\n"
        else:
            header = f"Top entities by relevance:\n"

        if not entities:
            click.echo(header)
            click.echo(click.style("No entities found", fg="yellow"))
            return

        # Build output
        output_lines = [header]

        # Count articles per entity
        for ent in entities:
            # Count articles that mention this entity
            article_count = session.query(func.count(article_entities.c.article_id)).filter(
                article_entities.c.entity_id == ent.id
            ).scalar()

            output_lines.append(f"[{ent.id}] {ent.name}")
            output_lines.append(f"    Type: {ent.entity_type.value}")
            output_lines.append(f"    Global relevance: {click.style(str(ent.relevance), fg='green')}")
            output_lines.append(f"    Mentioned in: {article_count} articles")
            if ent.description:
                output_lines.append(f"    Description: {ent.description[:80]}...")
            output_lines.append("")

        output_text = "\n".join(output_lines)

        # Use pager if more than 20 results and not disabled
        if len(entities) > 20 and not no_pager:
            click.echo_via_pager(output_text)
        else:
            click.echo(output_text)

    finally:
        session.close()


@entity.command()
@click.argument('name')
@click.option('--limit', '-l', type=int, default=10, help='Number of articles to show (default: 10)')
@click.option('--no-pager', is_flag=True, help='Disable pagination')
def show(name, limit, no_pager):
    """
    Show details of a named entity and articles that mention it.

    Examples:
        news entity show "Policía"
        news entity show "Luis Abinader" --limit 20
    """
    db = Database()
    session = db.get_session()

    try:
        # Find entity by name (case-insensitive)
        ent = session.query(NamedEntity).filter(
            func.lower(NamedEntity.name) == func.lower(name)
        ).first()

        if not ent:
            click.echo(click.style(f"✗ Entity '{name}' not found", fg="red"))
            return

        # Build output
        output_lines = []
        output_lines.append(click.style(f"\n=== {ent.name} ===\n", fg="cyan", bold=True))
        output_lines.append(f"ID: {ent.id}")
        output_lines.append(f"Type: {ent.entity_type.value}")
        output_lines.append(f"Global relevance: {click.style(str(ent.relevance), fg='green')}")
        output_lines.append(f"Trend: {ent.trend}")
        if ent.description:
            output_lines.append(f"Description: {ent.description}")
        if ent.photo_url:
            output_lines.append(f"Photo: {ent.photo_url}")
        output_lines.append(f"Created: {ent.created_at}")
        output_lines.append(f"Updated: {ent.updated_at}")

        # Get articles that mention this entity
        stmt = select(
            Article.id,
            Article.title,
            Article.published_date,
            article_entities.c.mentions,
            article_entities.c.relevance
        ).join(
            article_entities, Article.id == article_entities.c.article_id
        ).where(
            article_entities.c.entity_id == ent.id
        ).order_by(
            article_entities.c.relevance.desc()
        ).limit(limit)

        results = session.execute(stmt).fetchall()

        if not results:
            output_lines.append(click.style(f"\n✗ No articles found mentioning '{ent.name}'", fg="yellow"))
        else:
            output_lines.append(f"\n{click.style('Articles mentioning this entity:', bold=True)} (showing top {min(limit, len(results))} by relevance)\n")
            for article_id, title, published_date, mentions, relevance in results:
                output_lines.append(f"[{article_id}] {title[:70]}...")
                output_lines.append(f"    Published: {published_date}")
                output_lines.append(f"    Mentions: {mentions}")
                output_lines.append(f"    Relevance: {relevance:.2f}")
                output_lines.append("")

        output_text = "\n".join(output_lines)

        # Use pager if more than 20 articles and not disabled
        if len(results) > 20 and not no_pager:
            click.echo_via_pager(output_text)
        else:
            click.echo(output_text)

    finally:
        session.close()


@entity.command()
@click.argument('query')
@click.option('--limit', '-l', type=int, default=10, help='Number of results to show (default: 10)')
@click.option('--no-pager', is_flag=True, help='Disable pagination')
def search(query, limit, no_pager):
    """
    Search for entities by name (partial match).

    Examples:
        news entity search "Luis"
        news entity search "Policía" --limit 5
    """
    db = Database()
    session = db.get_session()

    try:
        # Search entities by partial name match (case-insensitive)
        entities = session.query(NamedEntity).filter(
            func.lower(NamedEntity.name).like(f"%{query.lower()}%")
        ).order_by(NamedEntity.relevance.desc()).limit(limit).all()

        if not entities:
            click.echo(click.style(f"✗ No entities found matching '{query}'", fg="yellow"))
            return

        # Build output
        output_lines = [f"Entities matching '{query}':\n"]

        for ent in entities:
            # Count articles that mention this entity
            article_count = session.query(func.count(article_entities.c.article_id)).filter(
                article_entities.c.entity_id == ent.id
            ).scalar()

            output_lines.append(f"[{ent.id}] {ent.name}")
            output_lines.append(f"    Type: {ent.entity_type.value}")
            output_lines.append(f"    Global relevance: {click.style(str(ent.relevance), fg='green')}")
            output_lines.append(f"    Mentioned in: {article_count} articles")
            output_lines.append("")

        output_text = "\n".join(output_lines)

        # Use pager if more than 20 results and not disabled
        if len(entities) > 20 and not no_pager:
            click.echo_via_pager(output_text)
        else:
            click.echo(output_text)

    finally:
        session.close()
