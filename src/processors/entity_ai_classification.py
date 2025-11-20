"""
AI-assisted entity classification using LLM for semantic understanding.

This module provides intelligent entity classification that complements the
heuristic auto_classify.py by using language models to understand context
and semantics.
"""

from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from db.models import (
    NamedEntity, EntityClassification, article_entities,
    EntityClassificationSuggestion
)
from processors.auto_classify import find_candidates_for_entity
from llm.openai_client import openai_structured_output


def extract_entity_context(
    entity: NamedEntity,
    candidates: List[NamedEntity],
    session: Session,
    max_sentences: int = 5
) -> Dict[str, Any]:
    """
    Extract contextual information for an entity to send to LLM.

    Args:
        entity: Entity to classify
        candidates: List of candidate canonical entities found via reverse index
        session: SQLAlchemy session
        max_sentences: Maximum number of context sentences to extract

    Returns:
        Dictionary with all context data for the LLM prompt
    """
    # Get article mentions for this entity
    from sqlalchemy import select

    article_entity_rows = session.execute(
        select(
            article_entities.c.article_id,
            article_entities.c.mentions,
            article_entities.c.context_sentences
        ).where(
            article_entities.c.entity_id == entity.id
        )
    ).fetchall()

    total_mentions = sum(row.mentions for row in article_entity_rows)
    article_count = len(article_entity_rows)

    # Extract context sentences (sample from context_sentences JSON)
    context_sentences = []
    for row in article_entity_rows[:3]:  # Sample from first 3 articles
        if row.context_sentences:
            # context_sentences is stored as JSON array
            sentences = row.context_sentences if isinstance(row.context_sentences, list) else []
            context_sentences.extend(sentences[:2])  # Take first 2 from each article

    # Limit to max_sentences
    context_sentences = context_sentences[:max_sentences]

    # Build candidate information
    candidate_data = []
    for candidate in candidates:
        # Count shared articles (articles where both entity and candidate appear)
        entity_article_ids = session.execute(
            select(article_entities.c.article_id).where(
                article_entities.c.entity_id == entity.id
            )
        ).scalars().all()

        if entity_article_ids:
            shared_articles_count = session.execute(
                select(func.count(article_entities.c.article_id.distinct())).where(
                    and_(
                        article_entities.c.article_id.in_(entity_article_ids),
                        article_entities.c.entity_id == candidate.id
                    )
                )
            ).scalar() or 0
        else:
            shared_articles_count = 0

        # Get sample sentences where both appear together
        sample_sentences = []
        if shared_articles_count > 0:
            # Find articles where both appear
            candidate_article_ids = session.execute(
                select(article_entities.c.article_id).where(
                    article_entities.c.entity_id == candidate.id
                )
            ).scalars().all()

            shared_article_ids = list(set(entity_article_ids) & set(candidate_article_ids))[:2]

            for article_id in shared_article_ids:
                # Get context from this article
                context_row = session.execute(
                    select(article_entities.c.context_sentences).where(
                        and_(
                            article_entities.c.article_id == article_id,
                            article_entities.c.entity_id == entity.id
                        )
                    )
                ).first()

                if context_row and context_row.context_sentences:
                    sentences = context_row.context_sentences if isinstance(context_row.context_sentences, list) else []
                    if sentences:
                        sample_sentences.append(sentences[0])

        # Extract common terms (simple keyword overlap)
        context_overlap = _extract_context_overlap(entity, candidate, session)

        candidate_data.append({
            'id': candidate.id,
            'name': candidate.name,
            'type': candidate.entity_type.value,
            'shared_articles': shared_articles_count,
            'context_overlap': context_overlap,
            'sample_sentences': sample_sentences[:2]
        })

    # Sort candidates by shared articles (most relevant first)
    candidate_data.sort(key=lambda x: x['shared_articles'], reverse=True)

    return {
        'entity_name': entity.name,
        'entity_type': entity.entity_type.value,
        'total_mentions': total_mentions,
        'article_count': article_count,
        'current_classification': entity.classified_as.value,
        'context_sentences': context_sentences,
        'candidates': candidate_data
    }


def _extract_context_overlap(
    entity: NamedEntity,
    candidate: NamedEntity,
    session: Session
) -> str:
    """
    Extract common terms that appear near both entity and candidate.

    Simple implementation: just lists candidate name as the overlap.
    Could be enhanced to extract actual nearby terms from articles.
    """
    # For now, return a simple description
    # TODO: Enhance to extract actual nearby terms from article content
    return f"{candidate.name}"


def classify_entity_with_ai(
    entity: NamedEntity,
    session: Session,
    min_confidence: float = 0.70,
    dry_run: bool = False
) -> Tuple[str, Optional[Dict], Optional[str]]:
    """
    Classify an entity using AI/LLM based on semantic context.

    Args:
        entity: Entity to classify
        session: SQLAlchemy session
        min_confidence: Minimum confidence to apply classification (0.0-1.0)
        dry_run: If True, don't modify database

    Returns:
        Tuple of (status, suggestion_dict, error_message)
        - status: 'success', 'skipped_low_confidence', 'skipped_no_candidates', 'error'
        - suggestion_dict: Classification suggestion data (or None)
        - error_message: Error description (or None)
    """
    try:
        # Step 1: Find candidates using reverse index (reuse from auto_classify)
        candidates = find_candidates_for_entity(entity, session, max_candidates=10)

        if not candidates:
            # No candidates found - could be canonical or need manual review
            # Don't send to LLM to save costs
            if not dry_run:
                # Mark as reviewed by AI (even though LLM wasn't called)
                entity.last_review_type = 'ai-assisted'
                entity.last_review = datetime.utcnow()

                # If already CANONICAL, approve it (likely correct)
                # Otherwise, needs manual review (could be error or ambiguous)
                if entity.classified_as == EntityClassification.CANONICAL:
                    entity.is_approved = 1
                else:
                    entity.is_approved = 0

                session.commit()

            return ('skipped_no_candidates', None, 'No candidates found via reverse index')

        # Convert candidate IDs to entities
        candidate_entities = session.query(NamedEntity).filter(
            NamedEntity.id.in_([c.id for c in candidates])
        ).all()

        # Step 2: Extract context for LLM
        context = extract_entity_context(entity, candidate_entities, session)

        # Step 3: Call LLM
        result = openai_structured_output('entity_classification', context)

        # Step 4: Validate result
        confidence = result.confidence

        if confidence < min_confidence:
            # Save as suggestion but don't apply
            if not dry_run:
                # Mark as reviewed by AI (even if not applied)
                entity.last_review_type = 'ai-assisted'
                entity.last_review = datetime.utcnow()
                # Don't approve - needs manual review
                entity.is_approved = 0

                suggestion = EntityClassificationSuggestion(
                    entity_id=entity.id,
                    suggested_classification=result.classification,
                    suggested_canonical_ids=result.canonical_ids,
                    confidence=confidence,
                    reasoning=result.reasoning,
                    alternative_classification=result.alternative_classification,
                    alternative_confidence=result.alternative_confidence,
                    applied=0
                )
                session.add(suggestion)
                session.commit()

            return ('skipped_low_confidence', {
                'classification': result.classification,
                'canonical_ids': result.canonical_ids,
                'confidence': confidence,
                'reasoning': result.reasoning
            }, f'Confidence {confidence:.2f} < threshold {min_confidence:.2f}')

        # Step 5: Apply classification
        applied = False
        if not dry_run:
            applied = _apply_classification(entity, result, session)

        # Step 6: Save suggestion (whether applied or not)
        if not dry_run:
            suggestion = EntityClassificationSuggestion(
                entity_id=entity.id,
                suggested_classification=result.classification,
                suggested_canonical_ids=result.canonical_ids,
                confidence=confidence,
                reasoning=result.reasoning,
                alternative_classification=result.alternative_classification,
                alternative_confidence=result.alternative_confidence,
                applied=1 if applied else 0
            )
            session.add(suggestion)
            session.commit()

        return ('success', {
            'classification': result.classification,
            'canonical_ids': result.canonical_ids,
            'confidence': confidence,
            'reasoning': result.reasoning,
            'applied': applied
        }, None)

    except Exception as e:
        return ('error', None, str(e))


def _apply_classification(
    entity: NamedEntity,
    result,  # StructuredOutput from LLM
    session: Session
) -> bool:
    """
    Apply the LLM's classification suggestion to the entity.

    Returns:
        True if classification was applied, False otherwise
    """
    classification = result.classification
    canonical_ids = result.canonical_ids or []
    confidence = result.confidence

    # Determine if we should auto-approve
    should_approve = False

    if classification == 'alias':
        if confidence >= 0.90:
            should_approve = True
        if len(canonical_ids) != 1:
            # Invalid: ALIAS must have exactly 1 canonical
            return False

        # Get canonical entity
        canonical = session.query(NamedEntity).filter_by(id=canonical_ids[0]).first()
        if not canonical or canonical.classified_as != EntityClassification.CANONICAL:
            # Candidate is not CANONICAL, can't create alias
            return False

        # Apply
        entity.set_as_alias(canonical, session)

    elif classification == 'ambiguous':
        if confidence >= 0.80:
            should_approve = True
        if len(canonical_ids) < 2:
            # Invalid: AMBIGUOUS must have 2+ canonicals
            return False

        # Get canonical entities
        canonicals = session.query(NamedEntity).filter(
            NamedEntity.id.in_(canonical_ids),
            NamedEntity.classified_as == EntityClassification.CANONICAL
        ).all()

        if len(canonicals) < 2:
            # Not enough valid canonicals
            return False

        # Apply
        entity.set_as_ambiguous(canonicals, session)

    elif classification == 'not_an_entity':
        if confidence >= 0.85:
            should_approve = True

        # Mark as NOT_AN_ENTITY
        entity.classified_as = EntityClassification.NOT_AN_ENTITY
        entity.canonical_refs = []

    elif classification == 'canonical':
        # Keep as CANONICAL (no action needed)
        # Don't auto-approve unless confidence is very high
        if confidence >= 0.95:
            should_approve = True

    # Mark as reviewed by AI
    entity.last_review_type = 'ai-assisted'
    entity.last_review = datetime.utcnow()
    entity.is_approved = 1 if should_approve else 0

    return True


def batch_classify_entities(
    session: Session,
    entity_type: Optional[str] = None,
    limit: Optional[int] = None,
    min_confidence: float = 0.70,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    Classify multiple entities in batch using AI.

    Processes entities that were already reviewed algorithmically but not approved,
    to add precision to the heuristic classifications.

    Args:
        session: SQLAlchemy session
        entity_type: Filter by entity type (person, org, etc.) or None for all
        limit: Maximum number of entities to process
        min_confidence: Minimum confidence to apply classification
        dry_run: If True, don't modify database

    Returns:
        Statistics dictionary with counts
    """
    # Query entities that need AI classification:
    # - Processed by algorithmic classifier (last_review_type='algorithmic')
    # - But not approved (is_approved=0) - need AI precision
    query = session.query(NamedEntity).filter(
        NamedEntity.last_review_type == 'algorithmic',
        NamedEntity.is_approved == 0
    ).order_by(
        NamedEntity.article_count.desc(),  # More mentions first (more context)
        NamedEntity.name_length.asc()      # Shorter names first (more likely to be aliases)
    )

    if entity_type:
        query = query.filter(NamedEntity.entity_type == entity_type)

    if limit:
        query = query.limit(limit)

    entities = query.all()

    # Statistics
    stats = {
        'processed': 0,
        'success': 0,
        'skipped_low_confidence': 0,
        'skipped_no_candidates': 0,
        'errors': 0,
        'applied': 0,
        'auto_approved': 0
    }

    for entity in entities:
        status, suggestion, error = classify_entity_with_ai(
            entity, session, min_confidence, dry_run
        )

        stats['processed'] += 1

        if status == 'success':
            stats['success'] += 1
            if suggestion and suggestion.get('applied'):
                stats['applied'] += 1
            # Check if it was auto-approved
            if not dry_run:
                session.refresh(entity)
                if entity.is_approved == 1:
                    stats['auto_approved'] += 1

        elif status == 'skipped_low_confidence':
            stats['skipped_low_confidence'] += 1
        elif status == 'skipped_no_candidates':
            stats['skipped_no_candidates'] += 1
        elif status == 'error':
            stats['errors'] += 1

    return stats
