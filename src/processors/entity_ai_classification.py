"""
AI-assisted entity classification using LLM with pairwise comparison.

This module uses LSH (Locality Sensitive Hashing) for efficient candidate
discovery and performs 1v1 entity comparisons where the LLM can recommend
actions for BOTH entities, eliminating order bias.
"""

from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_

from db.models import (
    NamedEntity, EntityClassification, article_entities,
    EntityClassificationSuggestion
)
from processors.entity_lsh_matcher import EntityLSHMatcher, build_lsh_index_for_type
from llm.openai_client import openai_structured_output


def extract_pairwise_context(
    entity_a: NamedEntity,
    entity_b: NamedEntity,
    session: Session,
    jaccard_similarity: float,
    max_sentences: int = 3
) -> Dict[str, Any]:
    """
    Extract contextual information for pairwise entity comparison.

    Args:
        entity_a: First entity (the one being evaluated)
        entity_b: Second entity (candidate for comparison)
        session: SQLAlchemy session
        jaccard_similarity: Jaccard similarity from LSH matching
        max_sentences: Maximum context sentences per entity

    Returns:
        Dictionary with context data for both entities
    """
    # Helper function to extract entity context
    def get_entity_data(entity):
        article_rows = session.execute(
            select(
                article_entities.c.article_id,
                article_entities.c.mentions,
                article_entities.c.context_sentences
            ).where(
                article_entities.c.entity_id == entity.id
            )
        ).fetchall()

        total_mentions = sum(row.mentions for row in article_rows)
        article_count = len(article_rows)

        # Extract context sentences
        context_sentences = []
        for row in article_rows[:3]:  # Sample from first 3 articles
            if row.context_sentences:
                sentences = row.context_sentences if isinstance(row.context_sentences, list) else []
                context_sentences.extend(sentences[:2])

        return {
            'mentions': total_mentions,
            'article_count': article_count,
            'context': context_sentences[:max_sentences]
        }

    # Get data for both entities
    data_a = get_entity_data(entity_a)
    data_b = get_entity_data(entity_b)

    # Calculate shared articles
    article_ids_a = session.execute(
        select(article_entities.c.article_id).where(
            article_entities.c.entity_id == entity_a.id
        )
    ).scalars().all()

    article_ids_b = session.execute(
        select(article_entities.c.article_id).where(
            article_entities.c.entity_id == entity_b.id
        )
    ).scalars().all()

    shared_articles = len(set(article_ids_a) & set(article_ids_b))

    # Get co-occurrence sentences (where both appear in same article)
    cooccurrence_sentences = []
    if shared_articles > 0:
        shared_article_ids = list(set(article_ids_a) & set(article_ids_b))[:2]

        for article_id in shared_article_ids:
            context_row = session.execute(
                select(article_entities.c.context_sentences).where(
                    and_(
                        article_entities.c.article_id == article_id,
                        article_entities.c.entity_id == entity_a.id
                    )
                )
            ).first()

            if context_row and context_row.context_sentences:
                sentences = context_row.context_sentences if isinstance(context_row.context_sentences, list) else []
                if sentences:
                    cooccurrence_sentences.append(sentences[0])

    return {
        # Entity A data
        'entity_a_name': entity_a.name,
        'entity_a_type': entity_a.entity_type.value,
        'entity_a_classification': entity_a.classified_as.value,
        'entity_a_mentions': data_a['mentions'],
        'entity_a_article_count': data_a['article_count'],
        'entity_a_context': data_a['context'],

        # Entity B data
        'entity_b_name': entity_b.name,
        'entity_b_type': entity_b.entity_type.value,
        'entity_b_classification': entity_b.classified_as.value,
        'entity_b_mentions': data_b['mentions'],
        'entity_b_article_count': data_b['article_count'],
        'entity_b_context': data_b['context'],

        # Comparison data
        'shared_articles': shared_articles,
        'jaccard_similarity': jaccard_similarity,
        'cooccurrence_sentences': cooccurrence_sentences[:3]
    }


def compare_entities_with_ai(
    entity_a: NamedEntity,
    entity_b: NamedEntity,
    session: Session,
    jaccard_similarity: float,
    min_confidence: float = 0.70,
    dry_run: bool = False
) -> Tuple[str, Optional[Dict], Optional[str]]:
    """
    Compare two entities using AI/LLM with pairwise analysis.

    Args:
        entity_a: First entity to compare
        entity_b: Second entity to compare
        session: SQLAlchemy session
        jaccard_similarity: Jaccard similarity score from LSH
        min_confidence: Minimum confidence to apply actions (0.0-1.0)
        dry_run: If True, don't modify database

    Returns:
        Tuple of (status, result_dict, error_message)
    """
    try:
        # Step 1: Extract context for both entities
        context = extract_pairwise_context(
            entity_a, entity_b, session, jaccard_similarity
        )

        # Step 2: Call LLM for pairwise comparison
        result = openai_structured_output('entity_pairwise_classification', context)

        # Step 3: Validate confidence
        confidence = result.confidence

        if confidence < min_confidence:
            # Save as suggestion but don't apply
            if not dry_run:
                suggestion = EntityClassificationSuggestion(
                    entity_id=entity_a.id,
                    suggested_classification=f"pairwise:{result.relationship}",
                    suggested_canonical_ids=[entity_b.id],
                    confidence=confidence,
                    reasoning=f"vs {entity_b.name}: {result.reasoning}",
                    alternative_classification=result.alternative_relationship,
                    alternative_confidence=result.alternative_confidence,
                    applied=0
                )
                session.add(suggestion)
                session.commit()

            return ('skipped_low_confidence', {
                'relationship': result.relationship,
                'entity_a_action': result.entity_a_action,
                'entity_b_action': result.entity_b_action,
                'confidence': confidence,
                'reasoning': result.reasoning
            }, f'Confidence {confidence:.2f} < threshold {min_confidence:.2f}')

        # Step 4: Apply actions for both entities
        applied = False
        if not dry_run:
            applied = _apply_pairwise_actions(
                entity_a, entity_b, result, session
            )

        # Step 5: Save suggestion
        if not dry_run:
            suggestion = EntityClassificationSuggestion(
                entity_id=entity_a.id,
                suggested_classification=f"pairwise:{result.relationship}",
                suggested_canonical_ids=[entity_b.id],
                confidence=confidence,
                reasoning=f"vs {entity_b.name}: {result.reasoning}",
                alternative_classification=result.alternative_relationship,
                alternative_confidence=result.alternative_confidence,
                applied=1 if applied else 0
            )
            session.add(suggestion)
            session.commit()

        return ('success', {
            'relationship': result.relationship,
            'entity_a_action': result.entity_a_action,
            'entity_b_action': result.entity_b_action,
            'confidence': confidence,
            'reasoning': result.reasoning,
            'applied': applied
        }, None)

    except Exception as e:
        return ('error', None, str(e))


def _apply_pairwise_actions(
    entity_a: NamedEntity,
    entity_b: NamedEntity,
    result,  # StructuredOutput from LLM
    session: Session
) -> bool:
    """
    Apply LLM's recommended actions for both entities.

    Args:
        entity_a: First entity
        entity_b: Second entity
        result: Pairwise classification result from LLM
        session: SQLAlchemy session

    Returns:
        True if actions were applied, False otherwise
    """
    confidence = result.confidence
    relationship = result.relationship
    action_a = result.entity_a_action
    action_b = result.entity_b_action

    # Determine auto-approval thresholds based on relationship
    should_approve_a = False
    should_approve_b = False

    if relationship == 'same_entity':
        # High confidence for same entity relationships
        if confidence >= 0.90:
            should_approve_a = True
            should_approve_b = True
    elif relationship == 'different_entities':
        # Medium confidence needed for different entities
        if confidence >= 0.80:
            should_approve_a = True
            should_approve_b = True
    elif relationship == 'ambiguous_usage':
        # Lower threshold for ambiguous (more conservative)
        if confidence >= 0.85:
            should_approve_a = True
            should_approve_b = True

    # Apply action for entity_a
    if action_a == 'make_alias':
        # Make entity_a an alias of entity_b
        if entity_b.classified_as == EntityClassification.CANONICAL:
            entity_a.set_as_alias(entity_b, session)
        else:
            return False  # Can't make alias of non-canonical

    elif action_a == 'make_canonical':
        entity_a.classified_as = EntityClassification.CANONICAL
        entity_a.canonical_refs = []

    elif action_a == 'make_not_an_entity':
        entity_a.classified_as = EntityClassification.NOT_AN_ENTITY
        entity_a.canonical_refs = []

    # Apply action for entity_b
    if action_b == 'make_alias':
        # Make entity_b an alias of entity_a
        if entity_a.classified_as == EntityClassification.CANONICAL:
            entity_b.set_as_alias(entity_a, session)
        else:
            return False  # Can't make alias of non-canonical

    elif action_b == 'make_canonical':
        entity_b.classified_as = EntityClassification.CANONICAL
        entity_b.canonical_refs = []

    elif action_b == 'make_not_an_entity':
        entity_b.classified_as = EntityClassification.NOT_AN_ENTITY
        entity_b.canonical_refs = []

    # Mark both as reviewed by AI
    entity_a.last_review_type = 'ai-assisted'
    entity_a.last_review = datetime.utcnow()
    entity_a.is_approved = 1 if should_approve_a else 0

    entity_b.last_review_type = 'ai-assisted'
    entity_b.last_review = datetime.utcnow()
    entity_b.is_approved = 1 if should_approve_b else 0

    return True


def classify_entity_with_ai(
    entity: NamedEntity,
    session: Session,
    lsh_matcher: Optional[EntityLSHMatcher] = None,
    min_confidence: float = 0.70,
    max_candidates: int = 10,
    dry_run: bool = False
) -> Tuple[str, Optional[Dict], Optional[str]]:
    """
    Classify an entity using LSH + pairwise AI comparison.

    Args:
        entity: Entity to classify
        session: SQLAlchemy session
        lsh_matcher: Pre-built LSH matcher (or None to build on demand)
        min_confidence: Minimum confidence to apply classification
        max_candidates: Maximum number of candidates to compare
        dry_run: If True, don't modify database

    Returns:
        Tuple of (status, result_dict, error_message)
    """
    try:
        # Build LSH index if not provided
        if lsh_matcher is None:
            lsh_matcher = build_lsh_index_for_type(
                session,
                entity.entity_type.value,
                threshold=0.4,
                only_canonical=True
            )

        # Find candidates using LSH
        candidates = lsh_matcher.find_candidates(
            entity,
            max_candidates=max_candidates,
            exclude_self=True
        )

        if not candidates:
            # No candidates found
            if not dry_run:
                entity.last_review_type = 'ai-assisted'
                entity.last_review = datetime.utcnow()

                # If already CANONICAL, approve it
                if entity.classified_as == EntityClassification.CANONICAL:
                    entity.is_approved = 1
                else:
                    entity.is_approved = 0

                session.commit()

            return ('skipped_no_candidates', None, 'No candidates found via LSH')

        # Compare with each candidate (1v1)
        best_result = None
        best_confidence = 0.0
        best_candidate = None

        for candidate, similarity in candidates:
            status, result, error = compare_entities_with_ai(
                entity, candidate, session, similarity,
                min_confidence, dry_run
            )

            # Track best result
            if result and result.get('confidence', 0.0) > best_confidence:
                best_confidence = result['confidence']
                best_result = result
                best_candidate = candidate

        # Return best result
        if best_result:
            return ('success', best_result, None)
        else:
            # All comparisons had low confidence
            if not dry_run:
                entity.last_review_type = 'ai-assisted'
                entity.last_review = datetime.utcnow()
                entity.is_approved = 0
                session.commit()

            return ('skipped_low_confidence', None, 'All comparisons below threshold')

    except Exception as e:
        return ('error', None, str(e))


def batch_classify_entities(
    session: Session,
    entity_type: Optional[str] = None,
    limit: Optional[int] = None,
    min_confidence: float = 0.70,
    max_candidates: int = 10,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    Classify multiple entities in batch using LSH + pairwise AI.

    Args:
        session: SQLAlchemy session
        entity_type: Filter by entity type or None for all
        limit: Maximum number of entities to process
        min_confidence: Minimum confidence to apply classification
        max_candidates: Maximum candidates per entity
        dry_run: If True, don't modify database

    Returns:
        Statistics dictionary with counts
    """
    # Query entities needing AI classification
    query = session.query(NamedEntity).filter(
        NamedEntity.last_review_type == 'algorithmic',
        NamedEntity.is_approved == 0
    ).order_by(
        NamedEntity.article_count.desc(),
        NamedEntity.name_length.asc()
    )

    if entity_type:
        query = query.filter(NamedEntity.entity_type == entity_type)

    if limit:
        query = query.limit(limit)

    entities = query.all()

    # Build LSH index once for efficiency
    # Group entities by type
    entities_by_type = {}
    for entity in entities:
        type_val = entity.entity_type.value
        if type_val not in entities_by_type:
            entities_by_type[type_val] = []
        entities_by_type[type_val].append(entity)

    # Process each type with its own LSH index
    stats = {
        'processed': 0,
        'success': 0,
        'skipped_low_confidence': 0,
        'skipped_no_candidates': 0,
        'errors': 0,
        'comparisons': 0,
        'applied': 0,
        'auto_approved': 0
    }

    for type_val, type_entities in entities_by_type.items():
        # Build LSH index for this type
        lsh_matcher = build_lsh_index_for_type(
            session, type_val, threshold=0.4, only_canonical=True
        )

        for entity in type_entities:
            status, result, error = classify_entity_with_ai(
                entity, session, lsh_matcher, min_confidence,
                max_candidates, dry_run
            )

            stats['processed'] += 1

            if status == 'success':
                stats['success'] += 1
                if result and result.get('applied'):
                    stats['applied'] += 1

                # Check if auto-approved
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
