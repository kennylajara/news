"""
Entity management commands.
"""

import click
from datetime import datetime
from db import Database, NamedEntity, Article, EntityType, EntityClassification
from db.models import article_entities, entity_same_as
from sqlalchemy import select, func
from domain.calculate_global_relevance import calculate_global_relevance


@click.group()
def entity():
    """Manage named entities."""
    pass


@entity.command()
@click.option('--limit', '-l', type=int, default=20, help='Number of entities to show (default: 20)')
@click.option('--type', '-t', 'entity_type', help='Filter by entity type')
@click.option('--min-articles', '-a', type=int, help='Minimum number of articles')
@click.option('--order-by', '-o', type=click.Choice(['articles', 'global_rank'], case_sensitive=False), default='articles', help='Order by articles or global_rank')
@click.option('--no-pager', is_flag=True, help='Disable pagination')
def list(limit, entity_type, min_articles, order_by, no_pager):
    """
    List named entities with filters.

    Examples:
        news entity list
        news entity list --limit 50
        news entity list --type person
        news entity list --min-articles 5
        news entity list --order-by global_rank
        news entity list --type org --min-articles 10 --order-by global_rank
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

        if min_articles:
            query = query.filter(NamedEntity.article_count >= min_articles)

        # Order by specified field
        if order_by == 'global_rank':
            query = query.order_by(NamedEntity.global_relevance.desc().nullslast())
        else:
            query = query.order_by(NamedEntity.article_count.desc())

        entities = query.limit(limit).all()

        # Build header
        header_parts = []
        if entity_type:
            header_parts.append(f"Type: {entity_type}")
        if min_articles:
            header_parts.append(f"Min articles: {min_articles}")
        header_parts.append(f"Order: {order_by}")

        if len(header_parts) > 1:
            header = f"Entities ({', '.join(header_parts)}):\n"
        else:
            header = f"Top entities by {order_by}:\n"

        if not entities:
            click.echo(header)
            click.echo(click.style("No entities found", fg="yellow"))
            return

        # Build output
        output_lines = [header]

        # Build entity list
        for ent in entities:
            output_lines.append(f"[{ent.id}] {ent.name}")
            output_lines.append(f"    Type: {ent.entity_type.value}")
            output_lines.append(f"    Articles: {click.style(str(ent.article_count), fg='green')}")
            if ent.global_relevance is not None and ent.global_relevance > 0:
                output_lines.append(f"    Global Rank: {click.style(f'{ent.global_relevance:.6f}', fg='cyan')}")
            if ent.avg_local_relevance is not None and ent.avg_local_relevance > 0:
                output_lines.append(f"    Avg Local Relevance: {ent.avg_local_relevance:.3f}")
            if ent.diversity > 0:
                output_lines.append(f"    Diversity: {ent.diversity} entities")
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

        # Calculate ranking position if global_relevance exists
        rank_position = None
        total_ranked = None
        if ent.global_relevance is not None and ent.global_relevance > 0:
            # Count entities with higher or equal global_relevance
            total_ranked = session.query(NamedEntity).filter(
                NamedEntity.global_relevance.isnot(None),
                NamedEntity.global_relevance > 0
            ).count()

            rank_position = session.query(NamedEntity).filter(
                NamedEntity.global_relevance > ent.global_relevance
            ).count() + 1

        # Build output
        output_lines = []
        output_lines.append(click.style(f"\n=== {ent.name} ===\n", fg="cyan", bold=True))
        output_lines.append(f"ID: {ent.id}")
        output_lines.append(f"Type: {ent.entity_type.value}")
        output_lines.append(f"Articles: {click.style(str(ent.article_count), fg='green')}")

        if ent.global_relevance is not None and ent.global_relevance > 0:
            output_lines.append(f"Global Rank: {click.style(f'{ent.global_relevance:.6f}', fg='cyan')} (#{rank_position} of {total_ranked})")

        if ent.avg_local_relevance is not None and ent.avg_local_relevance > 0:
            output_lines.append(f"Avg Local Relevance: {ent.avg_local_relevance:.3f}")

        if ent.diversity > 0:
            output_lines.append(f"Diversity: {ent.diversity} co-occurring entities")

        if ent.last_rank_calculated_at:
            output_lines.append(f"Last Ranked: {ent.last_rank_calculated_at}")

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
        ).order_by(NamedEntity.article_count.desc()).limit(limit).all()

        if not entities:
            click.echo(click.style(f"✗ No entities found matching '{query}'", fg="yellow"))
            return

        # Build output
        output_lines = [f"Entities matching '{query}':\n"]

        for ent in entities:
            output_lines.append(f"[{ent.id}] {ent.name}")
            output_lines.append(f"    Type: {ent.entity_type.value}")
            output_lines.append(f"    Articles: {click.style(str(ent.article_count), fg='green')}")
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
@click.option('--domain', '-d', help='Filter articles by domain (for testing)')
@click.option('--damping', type=float, default=0.85, help='PageRank damping factor (default: 0.85)')
@click.option('--threshold', '-t', type=float, default=0.3, help='Min relevance threshold (default: 0.3)')
@click.option('--time-decay', type=int, help='Time decay in days (optional)')
@click.option('--show-stats', is_flag=True, help='Show detailed statistics')
def rerank(domain, damping, threshold, time_decay, show_stats):
    """
    Calculate global relevance for all entities using PageRank.

    This command analyzes co-occurrences of entities across articles
    and calculates a global importance score based on the network
    of relationships between entities.

    Examples:
        news entity rerank
        news entity rerank --domain diariolibre.com
        news entity rerank --damping 0.9 --threshold 0.4
        news entity rerank --time-decay 30 --show-stats
    """
    db = Database()
    session = db.get_session()

    try:
        click.echo(click.style("🔄 Calculating global entity relevance...\n", fg="cyan", bold=True))

        # Step 1: Count total articles and entities
        total_articles_query = session.query(Article).filter(Article.enriched_at.isnot(None))
        if domain:
            from db.models import Source
            total_articles_query = total_articles_query.join(Article.source).filter(Source.domain == domain)

        total_articles_count = total_articles_query.count()

        if total_articles_count == 0:
            click.echo(click.style("✗ No enriched articles found", fg="red"))
            if domain:
                click.echo(f"  (filtered by domain: {domain})")
            return

        # Count entities that will be ranked
        from domain.entity_rank import EntityRankCalculator
        ranked_types = EntityRankCalculator.RANKED_TYPES
        total_entities = session.query(NamedEntity).filter(
            NamedEntity.entity_type.in_(ranked_types)
        ).count()

        click.echo(f"📊 {click.style('Loading data:', bold=True)}")
        click.echo(f"   • {click.style(str(total_articles_count), fg='green')} enriched articles")
        click.echo(f"   • {click.style(str(total_entities), fg='green')} entities to rank")

        if domain:
            click.echo(f"   • Filtered by domain: {click.style(domain, fg='yellow')}")

        click.echo()

        # Step 2: Calculate global relevance
        click.echo(f"⚙️  {click.style('Executing PageRank...', bold=True)}")
        click.echo(f"   • Damping: {damping}")
        click.echo(f"   • Threshold: {threshold}")
        if time_decay:
            click.echo(f"   • Time decay: {time_decay} days")

        click.echo()

        stats = calculate_global_relevance(
            db=db,
            session=session,
            source_domain=domain,
            damping=damping,
            min_relevance_threshold=threshold,
            time_decay_days=time_decay
        )

        # Step 3: Display results
        click.echo(click.style("✅ Global relevance calculated successfully!\n", fg="green", bold=True))

        iterations_str = click.style(str(stats['iterations']), fg='cyan')
        time_str = click.style(f"{stats['convergence_time']:.2f}s", fg='cyan')
        entities_str = click.style(str(stats['total_entities']), fg='green')

        click.echo(f"   • Converged in {iterations_str} iterations")
        click.echo(f"   • Processing time: {time_str}")
        click.echo(f"   • Entities ranked: {entities_str}")
        click.echo()

        # Show top 10 entities
        click.echo(click.style("🏆 Top 10 entities by global relevance:\n", bold=True))

        for i, entity_data in enumerate(stats['top_entities'], 1):
            name = entity_data['name']
            score = entity_data['score']
            name_styled = click.style(name, fg='cyan')
            score_styled = click.style(f'{score:.6f}', fg='green')
            click.echo(f"   {i:2d}. {name_styled} - {score_styled}")

        click.echo()

        # Show detailed stats if requested
        if show_stats:
            click.echo(click.style("📈 Detailed Statistics:\n", bold=True))

            # Get distribution stats
            all_entities = session.query(NamedEntity).filter(
                NamedEntity.global_relevance.isnot(None),
                NamedEntity.global_relevance > 0
            ).all()

            if all_entities:
                scores = [e.global_relevance for e in all_entities]
                import numpy as np

                click.echo(f"   • Mean: {np.mean(scores):.6f}")
                click.echo(f"   • Median: {np.median(scores):.6f}")
                click.echo(f"   • Std Dev: {np.std(scores):.6f}")
                click.echo(f"   • Min: {np.min(scores):.6f}")
                click.echo(f"   • Max: {np.max(scores):.6f}")
                click.echo()

                # Distribution by entity type
                click.echo("   Distribution by type:")
                type_counts = {}
                for e in all_entities:
                    type_name = e.entity_type.value
                    if type_name not in type_counts:
                        type_counts[type_name] = 0
                    type_counts[type_name] += 1

                for etype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
                    click.echo(f"     - {etype}: {count}")
                click.echo()

        click.echo(click.style("💾 Updated database", fg="green"))
        click.echo()
        click.echo("💡 View ranked entities with:")
        click.echo("   news entity list --order-by global_rank")

    except Exception as e:
        click.echo(click.style(f"✗ Error calculating global relevance: {str(e)}", fg="red"))
        import traceback
        traceback.print_exc()

    finally:
        session.close()


@entity.command()
@click.argument('name')
@click.option('--type', '-t', 'entity_type', required=True, help='Entity type (person, org, gpe, etc.)')
@click.option('--description', '-d', help='Entity description')
@click.option('--photo-url', '-p', help='Photo URL')
@click.option('--canonical/--no-canonical', default=True, help='Create as CANONICAL entity (default: True)')
def create(name, entity_type, description, photo_url, canonical):
    """
    Create a new entity manually (useful for canonical entities).

    Examples:
        news entity create "Banco Central República Dominicana" --type org
        news entity create "BCRD" --type org --description "Banco Central RD"
        news entity create "Luis Abinader Corona" --type person --canonical
    """
    db = Database()
    session = db.get_session()

    try:
        # Check if entity already exists
        existing = session.query(NamedEntity).filter(
            func.lower(NamedEntity.name) == func.lower(name)
        ).first()

        if existing:
            click.echo(click.style(f"✗ Entity '{name}' already exists (ID: {existing.id})", fg="red"))
            return

        # Validate entity type
        try:
            type_enum = EntityType[entity_type.upper()]
        except KeyError:
            valid_types = ', '.join([t.name.lower() for t in EntityType])
            click.echo(click.style(f"✗ Invalid entity type. Valid types: {valid_types}", fg="red"))
            return

        # Create entity
        entity = NamedEntity(
            name=name,
            entity_type=type_enum,
            detected_types=[type_enum.value],
            description=description,
            photo_url=photo_url,
            classified_as=EntityClassification.CANONICAL if canonical else EntityClassification.CANONICAL,
            needs_review=0,  # Manually created entities don't need review
            article_count=0
        )

        session.add(entity)
        session.commit()

        click.echo(click.style(f"✓ Created entity '{name}' (ID: {entity.id})", fg="green"))
        click.echo(f"  Type: {entity.entity_type.value}")
        click.echo(f"  Classification: {entity.classified_as.value}")
        if description:
            click.echo(f"  Description: {description}")

    except Exception as e:
        session.rollback()
        click.echo(click.style(f"✗ Error creating entity: {str(e)}", fg="red"))

    finally:
        session.close()


@entity.command()
@click.option('--limit', '-l', type=int, default=20, help='Number of entities to show (default: 20)')
@click.option('--type', '-t', 'entity_type', help='Filter by entity type')
@click.option('--multiple-types', is_flag=True, help='Show only entities with multiple detected types')
@click.option('--no-pager', is_flag=True, help='Disable pagination')
def review_list(limit, entity_type, multiple_types, no_pager):
    """
    List entities that need manual review.

    Examples:
        news entity review-list
        news entity review-list --limit 50
        news entity review-list --type person
        news entity review-list --multiple-types
    """
    db = Database()
    session = db.get_session()

    try:
        # Build query for entities needing review
        query = session.query(NamedEntity).filter(NamedEntity.needs_review == 1)

        # Apply filters
        if entity_type:
            try:
                type_enum = EntityType[entity_type.upper()]
                query = query.filter(NamedEntity.entity_type == type_enum)
            except KeyError:
                valid_types = ', '.join([t.name.lower() for t in EntityType])
                click.echo(click.style(f"✗ Invalid entity type. Valid types: {valid_types}", fg="red"))
                return

        # Order by article count (review most mentioned first)
        query = query.order_by(NamedEntity.article_count.desc())

        entities = query.limit(limit).all()

        if not entities:
            click.echo(click.style("✓ No entities need review!", fg="green"))
            return

        # Build output
        output_lines = [click.style(f"Entities needing review ({len(entities)}):\n", bold=True)]

        for ent in entities:
            # Check if has multiple detected types
            has_multiple = ent.detected_types and len(ent.detected_types) > 1

            if multiple_types and not has_multiple:
                continue

            output_lines.append(f"[{ent.id}] {click.style(ent.name, fg='yellow')}")
            output_lines.append(f"    Type: {ent.entity_type.value}")

            if has_multiple:
                types_str = ', '.join(ent.detected_types)
                output_lines.append(f"    {click.style('Detected types:', fg='red')} {types_str}")

            output_lines.append(f"    Classification: {ent.classified_as.value}")
            output_lines.append(f"    Articles: {ent.article_count}")

            if ent.last_review:
                output_lines.append(f"    Last review: {ent.last_review}")

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
@click.argument('entity_id', type=int)
@click.option('--no-pager', is_flag=True, help='Disable pagination')
def review_start(entity_id, no_pager):
    """
    Start reviewing an entity (show details and context).

    Examples:
        news entity review-start 123
    """
    db = Database()
    session = db.get_session()

    try:
        entity = session.query(NamedEntity).filter_by(id=entity_id).first()

        if not entity:
            click.echo(click.style(f"✗ Entity ID {entity_id} not found", fg="red"))
            return

        # Build output
        output_lines = []
        output_lines.append(click.style(f"\n=== Reviewing: {entity.name} ===\n", fg="cyan", bold=True))
        output_lines.append(f"ID: {entity.id}")
        output_lines.append(f"Current Type: {click.style(entity.entity_type.value, fg='yellow')}")

        if entity.detected_types:
            types_str = ', '.join(entity.detected_types)
            if len(entity.detected_types) > 1:
                output_lines.append(f"Detected Types: {click.style(types_str, fg='red')} ⚠️  INCONSISTENT")
            else:
                output_lines.append(f"Detected Types: {types_str}")

        output_lines.append(f"Classification: {entity.classified_as.value}")
        output_lines.append(f"Articles: {entity.article_count}")

        if entity.alias_for_id:
            alias_for = session.query(NamedEntity).filter_by(id=entity.alias_for_id).first()
            if alias_for:
                output_lines.append(f"Alias for: {alias_for.name} (ID: {alias_for.id})")

        if entity.description:
            output_lines.append(f"Description: {entity.description}")

        output_lines.append("")

        # Get context sentences from articles
        stmt = select(
            Article.id,
            Article.title,
            article_entities.c.context_sentences,
            article_entities.c.mentions
        ).join(
            article_entities, Article.id == article_entities.c.article_id
        ).where(
            article_entities.c.entity_id == entity.id
        ).order_by(
            article_entities.c.relevance.desc()
        ).limit(10)

        results = session.execute(stmt).fetchall()

        if results:
            output_lines.append(click.style("Context from articles:\n", bold=True))

            for article_id, title, context_sentences, mentions in results:
                output_lines.append(f"[{article_id}] {title[:60]}...")
                output_lines.append(f"    Mentions: {mentions}")

                if context_sentences:
                    output_lines.append("    Contexts:")
                    for ctx in context_sentences[:3]:  # Show first 3 contexts
                        output_lines.append(f"      • {ctx[:100]}...")

                output_lines.append("")

        output_lines.append(click.style("\nNext steps:", bold=True))
        output_lines.append(f"  • Approve: news entity review-approve {entity_id}")
        output_lines.append(f"  • Change type: news entity review-classify {entity_id} --type <new_type>")
        output_lines.append(f"  • Mark as alias: news entity classify-alias {entity_id} <canonical_id>")
        output_lines.append(f"  • Mark as ambiguous: news entity classify-ambiguous {entity_id} <id1> <id2> ...")

        output_text = "\n".join(output_lines)

        # Use pager if long output and not disabled
        if len(output_lines) > 30 and not no_pager:
            click.echo_via_pager(output_text)
        else:
            click.echo(output_text)

    finally:
        session.close()


@entity.command()
@click.argument('entity_id', type=int)
def review_approve(entity_id):
    """
    Approve entity as correct (mark as reviewed).

    Examples:
        news entity review-approve 123
    """
    db = Database()
    session = db.get_session()

    try:
        entity = session.query(NamedEntity).filter_by(id=entity_id).first()

        if not entity:
            click.echo(click.style(f"✗ Entity ID {entity_id} not found", fg="red"))
            return

        entity.needs_review = 0
        entity.last_review = datetime.utcnow()

        session.commit()

        click.echo(click.style(f"✓ Approved entity '{entity.name}' (ID: {entity_id})", fg="green"))
        click.echo(f"  Marked as reviewed at: {entity.last_review}")

    except Exception as e:
        session.rollback()
        click.echo(click.style(f"✗ Error approving entity: {str(e)}", fg="red"))

    finally:
        session.close()


@entity.command()
@click.argument('entity_id', type=int)
@click.option('--type', '-t', 'new_type', required=True, help='New entity type')
def review_classify(entity_id, new_type):
    """
    Change entity type and mark as reviewed.

    Examples:
        news entity review-classify 123 --type org
        news entity review-classify 456 --type person
    """
    db = Database()
    session = db.get_session()

    try:
        entity = session.query(NamedEntity).filter_by(id=entity_id).first()

        if not entity:
            click.echo(click.style(f"✗ Entity ID {entity_id} not found", fg="red"))
            return

        # Validate new entity type
        try:
            type_enum = EntityType[new_type.upper()]
        except KeyError:
            valid_types = ', '.join([t.name.lower() for t in EntityType])
            click.echo(click.style(f"✗ Invalid entity type. Valid types: {valid_types}", fg="red"))
            return

        old_type = entity.entity_type.value
        entity.entity_type = type_enum
        entity.needs_review = 0
        entity.last_review = datetime.utcnow()

        session.commit()

        click.echo(click.style(f"✓ Updated entity '{entity.name}' (ID: {entity_id})", fg="green"))
        click.echo(f"  Type: {old_type} → {type_enum.value}")
        click.echo(f"  Marked as reviewed at: {entity.last_review}")

    except Exception as e:
        session.rollback()
        click.echo(click.style(f"✗ Error updating entity: {str(e)}", fg="red"))

    finally:
        session.close()


@entity.command()
@click.argument('alias_id', type=int)
@click.argument('canonical_id', type=int)
def classify_alias(alias_id, canonical_id):
    """
    Mark entity as ALIAS of another canonical entity.

    Examples:
        news entity classify-alias 456 123
        # Makes entity 456 an alias of entity 123
    """
    db = Database()
    session = db.get_session()

    try:
        alias_entity = session.query(NamedEntity).filter_by(id=alias_id).first()
        canonical_entity = session.query(NamedEntity).filter_by(id=canonical_id).first()

        if not alias_entity:
            click.echo(click.style(f"✗ Alias entity ID {alias_id} not found", fg="red"))
            return

        if not canonical_entity:
            click.echo(click.style(f"✗ Canonical entity ID {canonical_id} not found", fg="red"))
            return

        # Use helper method for safe classification
        alias_entity.set_as_alias(canonical_entity, session)
        alias_entity.needs_review = 0
        alias_entity.last_review = datetime.utcnow()

        session.commit()

        click.echo(click.style(f"✓ Marked '{alias_entity.name}' as ALIAS of '{canonical_entity.name}'", fg="green"))
        click.echo(f"  Alias ID: {alias_id}")
        click.echo(f"  Canonical ID: {canonical_id}")

    except ValueError as e:
        session.rollback()
        click.echo(click.style(f"✗ Validation error: {str(e)}", fg="red"))
    except Exception as e:
        session.rollback()
        click.echo(click.style(f"✗ Error setting alias: {str(e)}", fg="red"))

    finally:
        session.close()


@entity.command()
@click.argument('ambiguous_id', type=int)
@click.argument('canonical_ids', nargs=-1, type=int, required=True)
def classify_ambiguous(ambiguous_id, canonical_ids):
    """
    Mark entity as AMBIGUOUS pointing to multiple canonical entities.

    Examples:
        news entity classify-ambiguous 789 123 456
        # Makes entity 789 ambiguous, pointing to entities 123 and 456
    """
    db = Database()
    session = db.get_session()

    try:
        if len(canonical_ids) < 2:
            click.echo(click.style("✗ AMBIGUOUS entity must point to at least 2 canonical entities", fg="red"))
            return

        ambiguous_entity = session.query(NamedEntity).filter_by(id=ambiguous_id).first()

        if not ambiguous_entity:
            click.echo(click.style(f"✗ Ambiguous entity ID {ambiguous_id} not found", fg="red"))
            return

        # Fetch all canonical entities
        canonical_entities = []
        for can_id in canonical_ids:
            entity = session.query(NamedEntity).filter_by(id=can_id).first()
            if not entity:
                click.echo(click.style(f"✗ Canonical entity ID {can_id} not found", fg="red"))
                return
            canonical_entities.append(entity)

        # Use helper method for safe classification
        ambiguous_entity.set_as_ambiguous(canonical_entities, session)
        ambiguous_entity.needs_review = 0
        ambiguous_entity.last_review = datetime.utcnow()

        session.commit()

        canonical_names = ', '.join([e.name for e in canonical_entities])
        click.echo(click.style(f"✓ Marked '{ambiguous_entity.name}' as AMBIGUOUS", fg="green"))
        click.echo(f"  Points to: {canonical_names}")
        click.echo(f"  IDs: {', '.join(map(str, canonical_ids))}")

    except ValueError as e:
        session.rollback()
        click.echo(click.style(f"✗ Validation error: {str(e)}", fg="red"))
    except Exception as e:
        session.rollback()
        click.echo(click.style(f"✗ Error setting ambiguous: {str(e)}", fg="red"))

    finally:
        session.close()


@entity.command()
@click.argument('entity_id', type=int)
def classify_canonical(entity_id):
    """
    Mark entity as CANONICAL (primary entity).

    Examples:
        news entity classify-canonical 123
    """
    db = Database()
    session = db.get_session()

    try:
        entity = session.query(NamedEntity).filter_by(id=entity_id).first()

        if not entity:
            click.echo(click.style(f"✗ Entity ID {entity_id} not found", fg="red"))
            return

        # Use helper method for safe classification
        entity.set_as_canonical(session)
        entity.needs_review = 0
        entity.last_review = datetime.utcnow()

        session.commit()

        click.echo(click.style(f"✓ Marked '{entity.name}' as CANONICAL", fg="green"))

    except ValueError as e:
        session.rollback()
        click.echo(click.style(f"✗ Validation error: {str(e)}", fg="red"))
    except Exception as e:
        session.rollback()
        click.echo(click.style(f"✗ Error setting canonical: {str(e)}", fg="red"))

    finally:
        session.close()
