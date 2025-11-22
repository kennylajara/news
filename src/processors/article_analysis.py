"""
Deep article analysis module.
Generates multi-dimensional analysis of articles for recommendation system matching.
"""

from datetime import datetime
from db import ProcessingBatch, BatchItem, Article, ArticleAnalysis


def process_article_analysis(article, batch_item, session):
    """
    Generate deep analysis for an article.

    Args:
        article: Article object (must have enriched_at set for entity context)
        batch_item: BatchItem object for tracking
        session: Database session

    Returns:
        dict: Statistics about processing
    """
    logs = []
    stats = {
        'analysis_generated': 0,
        'analysis_skipped': 0,
        'entities_extracted': 0,
        'processing_time': 0
    }

    start_time = datetime.utcnow()
    batch_item.status = 'processing'
    batch_item.started_at = start_time
    session.flush()

    try:
        logs.append(f"Processing analysis for article {article.id}: {article.title[:50]}...")

        # Check if analysis already exists
        existing_analysis = session.query(ArticleAnalysis).filter_by(article_id=article.id).first()
        if existing_analysis:
            logs.append(f"Analysis already exists (ID: {existing_analysis.id}), skipping")
            stats['analysis_skipped'] = 1
            batch_item.status = 'completed'
            batch_item.completed_at = datetime.utcnow()
            batch_item.logs = "\\n".join(logs)
            batch_item.stats = stats
            session.flush()
            return stats

        # Import LLM client
        try:
            from llm.openai_client import openai_structured_output
        except ImportError as e:
            raise ImportError(f"Could not import OpenAI client: {e}")

        # Prepare data for LLM (excluding source/author to avoid bias)
        llm_data = {
            'title': article.title,
            'subtitle': article.subtitle or '',
            'published_date': article.published_date.strftime('%Y-%m-%d') if article.published_date else '',
            'category': article.category or '',
            'content': article.content
        }

        logs.append(f"Calling LLM for analysis...")

        # Call OpenAI for structured analysis
        result = openai_structured_output('article_analysis', llm_data)

        # Process extracted entities
        from db import NamedEntity, EntityType, EntityOrigin
        from sqlalchemy.dialects.sqlite import insert
        from db.models import article_entities

        entity_counts = {}
        for ent in result.entities:
            entity_counts[ent.text] = entity_counts.get(ent.text, 0) + 1

        # Save entities to database
        for ent in result.entities:
            # Get or create entity
            entity = session.query(NamedEntity).filter_by(
                name=ent.text,
                entity_type=EntityType[ent.type.value]
            ).first()

            if not entity:
                entity = NamedEntity(
                    name=ent.text,
                    name_length=len(ent.text),
                    entity_type=EntityType[ent.type.value],
                    is_approved=1,
                    last_review_type='ai-assisted'
                )
                session.add(entity)
                session.flush()

            # Insert into article_entities with relevance based on mention count
            mentions = entity_counts[ent.text]
            relevance = min(mentions / 10.0, 1.0)  # Simple relevance: mentions / 10, capped at 1.0

            stmt = insert(article_entities).values(
                article_id=article.id,
                entity_id=entity.id,
                mentions=mentions,
                relevance=relevance,
                origin=EntityOrigin.AI_ANALYSIS,
                context_sentences=[]  # Could be populated if needed
            ).on_conflict_do_nothing()  # Skip if already exists
            session.execute(stmt)

        stats['entities_extracted'] = len(set(ent.text for ent in result.entities))
        logs.append(f"Extracted {stats['entities_extracted']} unique entities")

        # Create ArticleAnalysis record
        analysis = ArticleAnalysis(
            article_id=article.id,
            # Semantic
            key_concepts=result.key_concepts,
            semantic_relations=[],  # Commented out in schema
            # Narrative
            narrative_frames=[f.value for f in result.narrative_frames],
            editorial_tone=result.editorial_tone.value,
            style_descriptors=[],  # Commented out in schema
            # Controversy/bias
            controversy_score=result.controversy_score,
            political_bias=result.political_bias,
            # Quality
            has_named_sources=0,  # Commented out in schema
            has_data_or_statistics=0,  # Commented out in schema
            has_multiple_perspectives=0,  # Commented out in schema
            quality_score=0,  # Commented out in schema
            # Content format and temporal relevance
            content_format=result.content_format.value,
            temporal_relevance=result.temporal_relevance.value,
            # Audience
            audience_education=result.audience_education.value,
            target_age_range=result.target_age_range.value,
            target_professions=[],  # Commented out in schema
            required_interests=[],  # Commented out in schema
            # Industry
            relevant_industries=[i.value for i in result.relevant_industries],
            # Geographic
            geographic_scope=result.geographic_scope.value,
            cultural_context="",  # Commented out in schema
            # Source diversity
            voices_represented=[],  # Commented out in schema
            source_diversity_score=0  # Commented out in schema
        )
        session.add(analysis)
        session.flush()

        stats['analysis_generated'] = 1
        logs.append(f"✓ Generated analysis (ID: {analysis.id})")
        logs.append(f"  Controversy: {result.controversy_score}, Bias: {result.political_bias}")
        logs.append(f"  Frames: {', '.join(f.value for f in result.narrative_frames)}")
        logs.append(f"  Tone: {result.editorial_tone.value}, Format: {result.content_format.value}, Temporal: {result.temporal_relevance.value}")

        # Update batch item
        batch_item.status = 'completed'
        batch_item.completed_at = datetime.utcnow()
        batch_item.logs = "\\n".join(logs)
        stats['processing_time'] = (datetime.utcnow() - start_time).total_seconds()
        batch_item.stats = stats
        session.flush()

        return stats

    except Exception as e:
        # Mark as failed
        batch_item.status = 'failed'
        batch_item.error_message = str(e)
        batch_item.completed_at = datetime.utcnow()
        batch_item.logs = "\\n".join(logs + [f"ERROR: {str(e)}"])
        session.flush()
        raise


def process_article_analysis_batch(batch_id, session):
    """
    Process all items in an article analysis batch.

    Args:
        batch_id: ID of the batch to process
        session: Database session

    Returns:
        bool: True if all items processed successfully, False otherwise
    """
    batch = session.query(ProcessingBatch).filter_by(id=batch_id).first()
    if not batch:
        print(f"Batch {batch_id} not found")
        return False

    # Update batch status
    batch.status = 'processing'
    batch.started_at = datetime.utcnow()
    session.commit()

    # Get all pending items
    items = session.query(BatchItem).filter_by(batch_id=batch_id, status='pending').all()

    total_stats = {
        'analysis_generated': 0,
        'analysis_skipped': 0,
        'entities_extracted': 0,
        'total_processing_time': 0
    }

    for item in items:
        try:
            article = session.query(Article).filter_by(id=item.article_id).first()
            if not article:
                item.status = 'failed'
                item.error_message = f"Article {item.article_id} not found"
                batch.failed_items += 1
                continue

            # Process the article
            stats = process_article_analysis(article, item, session)

            # Aggregate stats
            for key in total_stats:
                if key in stats:
                    total_stats[key] += stats[key]

            batch.successful_items += 1
            batch.processed_items += 1

            if stats['analysis_generated']:
                print(f"  ✓ Analyzed article {article.id}: {article.title[:50]}...")
            else:
                print(f"  - Skipped article {article.id} (already analyzed)")

        except Exception as e:
            batch.failed_items += 1
            batch.processed_items += 1
            print(f"  ✗ Failed to analyze article {item.article_id}: {e}")

        session.commit()

    # Update batch
    batch.status = 'completed' if batch.failed_items == 0 else 'failed'
    batch.completed_at = datetime.utcnow()
    batch.stats = total_stats
    session.commit()

    print(f"\nBatch {batch_id} completed:")
    print(f"  Total items: {batch.total_items}")
    print(f"  Successful: {batch.successful_items}")
    print(f"  Failed: {batch.failed_items}")
    print(f"  Analyses generated: {total_stats['analysis_generated']}")
    print(f"  Analyses skipped: {total_stats['analysis_skipped']}")
    print(f"  Entities extracted: {total_stats['entities_extracted']}")

    return batch.failed_items == 0
