"""
AI-assisted entity classification using LLM with pairwise comparison.

This module uses LSH (Locality Sensitive Hashing) for efficient candidate
discovery and performs 1v1 entity comparisons where the LLM can recommend
classification changes and reference modifications for BOTH entities.
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


def _get_canonical_refs_info(entity: NamedEntity, session: Session) -> List[Dict[str, Any]]:
    """
    Get information about canonical references for an entity.

    Args:
        entity: Entity to get references for
        session: SQLAlchemy session

    Returns:
        List of dicts with {id, name, type} for each canonical reference
    """
    if not entity.canonical_refs:
        return []

    canonical_entities = session.query(NamedEntity).filter(
        NamedEntity.id.in_(entity.canonical_refs)
    ).all()

    return [
        {
            'id': ce.id,
            'name': ce.name,
            'type': ce.entity_type.value
        }
        for ce in canonical_entities
    ]


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
        Dictionary with context data for both entities including IDs and canonical_refs
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

    # Get canonical references info
    refs_a = _get_canonical_refs_info(entity_a, session)
    refs_b = _get_canonical_refs_info(entity_b, session)

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
        'entity_a_id': entity_a.id,
        'entity_a_name': entity_a.name,
        'entity_a_type': entity_a.entity_type.value,
        'entity_a_classification': entity_a.classified_as.value,
        'entity_a_mentions': data_a['mentions'],
        'entity_a_article_count': data_a['article_count'],
        'entity_a_context': data_a['context'],
        'entity_a_canonical_refs': refs_a,

        # Entity B data
        'entity_b_id': entity_b.id,
        'entity_b_name': entity_b.name,
        'entity_b_type': entity_b.entity_type.value,
        'entity_b_classification': entity_b.classified_as.value,
        'entity_b_mentions': data_b['mentions'],
        'entity_b_article_count': data_b['article_count'],
        'entity_b_context': data_b['context'],
        'entity_b_canonical_refs': refs_b,

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

        # Step 2: Call LLM for pairwise comparison with validation context
        result = openai_structured_output(
            'entity_pairwise_classification',
            context,
            validation_context={'valid_entity_ids': [entity_a.id, entity_b.id]}
        )

        # Step 3: Validate confidence
        confidence = result.confidence

        if confidence < min_confidence:
            # Save as suggestion but don't apply
            if not dry_run:
                # Create summary of changes for suggestion
                changes_summary = {
                    'classification_changes': [
                        {'entity_id': c.entity_id, 'classification': c.classification}
                        for c in result.classification_changes
                    ],
                    'reference_changes': [
                        {
                            'entity_id': r.entity_id,
                            'add_refs': r.add_refs,
                            'remove_refs': r.remove_refs
                        }
                        for r in (result.reference_changes or [])
                    ] if result.reference_changes else None
                }

                suggestion = EntityClassificationSuggestion(
                    entity_id=entity_a.id,
                    suggested_classification=f"pairwise:{changes_summary}",
                    suggested_canonical_ids=[entity_b.id],
                    confidence=confidence,
                    reasoning=f"vs {entity_b.name}: {result.reasoning}",
                    alternative_classification=None,
                    alternative_confidence=None,
                    applied=0
                )
                session.add(suggestion)
                session.commit()

            return ('skipped_low_confidence', {
                'classification_changes': [
                    {'entity_id': c.entity_id, 'classification': c.classification}
                    for c in result.classification_changes
                ],
                'reference_changes': result.reference_changes,
                'confidence': confidence,
                'reasoning': result.reasoning
            }, f'Confidence {confidence:.2f} < threshold {min_confidence:.2f}')

        # Step 4: Apply classification and reference changes
        applied = False
        if not dry_run:
            applied = _apply_pairwise_changes(
                entity_a, entity_b, result, session
            )

        # Step 5: Save suggestion
        if not dry_run:
            changes_summary = {
                'classification_changes': [
                    {'entity_id': c.entity_id, 'classification': c.classification}
                    for c in result.classification_changes
                ],
                'reference_changes': [
                    {
                        'entity_id': r.entity_id,
                        'add_refs': r.add_refs,
                        'remove_refs': r.remove_refs
                    }
                    for r in (result.reference_changes or [])
                ] if result.reference_changes else None
            }

            suggestion = EntityClassificationSuggestion(
                entity_id=entity_a.id,
                suggested_classification=f"pairwise:{changes_summary}",
                suggested_canonical_ids=[entity_b.id],
                confidence=confidence,
                reasoning=f"vs {entity_b.name}: {result.reasoning}",
                alternative_classification=None,
                alternative_confidence=None,
                applied=1 if applied else 0
            )
            session.add(suggestion)
            session.commit()

        return ('success', {
            'classification_changes': [
                {'entity_id': c.entity_id, 'classification': c.classification}
                for c in result.classification_changes
            ],
            'reference_changes': result.reference_changes,
            'confidence': confidence,
            'reasoning': result.reasoning,
            'applied': applied
        }, None)

    except Exception as e:
        return ('error', None, str(e))


def _apply_pairwise_changes(
    entity_a: NamedEntity,
    entity_b: NamedEntity,
    result,  # StructuredOutput from LLM
    session: Session
) -> bool:
    """
    Apply LLM's recommended classification and reference changes for both entities.

    Args:
        entity_a: First entity
        entity_b: Second entity
        result: Pairwise classification result from LLM
        session: SQLAlchemy session

    Returns:
        True if changes were applied, False otherwise
    """
    confidence = result.confidence

    # Build entity lookup
    entities_by_id = {
        entity_a.id: entity_a,
        entity_b.id: entity_b
    }

    # Apply classification changes
    for change in result.classification_changes:
        entity = entities_by_id.get(change.entity_id)
        if not entity:
            return False

        new_classification = change.classification

        # Update classification
        if new_classification == 'canonical':
            entity.classified_as = EntityClassification.CANONICAL
        elif new_classification == 'alias':
            entity.classified_as = EntityClassification.ALIAS
        elif new_classification == 'ambiguous':
            entity.classified_as = EntityClassification.AMBIGUOUS
        elif new_classification == 'not_an_entity':
            entity.classified_as = EntityClassification.NOT_AN_ENTITY
            entity.canonical_refs = []  # Clear references for NOT_AN_ENTITY

    # Apply reference changes
    if result.reference_changes:
        for ref_change in result.reference_changes:
            entity = entities_by_id.get(ref_change.entity_id)
            if not entity:
                continue

            # Get current refs
            current_refs = set(entity.canonical_refs or [])

            # Add new refs
            if ref_change.add_refs:
                current_refs.update(ref_change.add_refs)

            # Remove refs
            if ref_change.remove_refs:
                current_refs -= set(ref_change.remove_refs)

            # Update entity
            entity.canonical_refs = list(current_refs)

    # Determine auto-approval based on confidence
    should_approve_a = False
    should_approve_b = False

    if confidence >= 0.90:
        should_approve_a = True
        should_approve_b = True
    elif confidence >= 0.80:
        # Medium confidence: approve if classifications didn't change significantly
        # (e.g., CANONICAL → CANONICAL, or simple ALIAS assignments)
        should_approve_a = True
        should_approve_b = True

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
