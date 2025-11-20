"""
Automatic entity classification system.

This module implements the auto-classification algorithm that detects
aliases and ambiguous entities using heuristic pattern matching.
"""

from datetime import datetime
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from db.models import NamedEntity, EntityToken, EntityClassification, article_entities
from processors.tokenization import normalize_token
from typing import List, Optional, Tuple


def find_candidates_for_entity(
    entity: NamedEntity,
    session: Session,
    max_candidates: int = 100
) -> List[NamedEntity]:
    """
    Find candidate entities for matching against the given entity.

    Uses the reverse index (entity_tokens) to efficiently find entities that:
    1. Contain all non-stopword tokens from the evaluated entity, OR
    2. Are initials/acronyms that match the evaluated entity's initials

    The evaluated entity is always the shorter one.
    Candidates are always longer entities.

    Args:
        entity: The entity being evaluated (shorter)
        session: SQLAlchemy session
        max_candidates: Maximum number of candidates to return

    Returns:
        List of candidate NamedEntity objects (longer than evaluated entity)

    Example:
        >>> entity = session.query(NamedEntity).filter_by(name="JCE").first()
        >>> candidates = find_candidates_for_entity(entity, session)
        >>> # Returns: ["Junta Central Electoral", "Junta Católica Ecuménica", ...]
    """
    # Get tokens for the evaluated entity
    entity_tokens = session.query(EntityToken).filter_by(
        entity_id=entity.id
    ).all()

    # Separate stopwords from non-stopwords
    non_stopword_tokens = [
        t for t in entity_tokens if not t.is_stopword
    ]
    stopword_tokens = [
        t for t in entity_tokens if t.is_stopword
    ]

    is_single_token = len(non_stopword_tokens) == 1
    entity_seems_like_initials = (
        is_single_token and
        non_stopword_tokens[0].seems_like_initials == 1
    )

    candidates = set()

    # ========================================================================
    # CRITERION 1: All non-stopword tokens must be in candidate
    # ========================================================================
    if non_stopword_tokens:
        # Get normalized tokens
        normalized_tokens = [t.token_normalized for t in non_stopword_tokens]

        # Find entities that contain ALL these tokens
        # Using subquery to ensure all tokens are present
        from sqlalchemy import func

        # Get entity IDs that have all the required tokens
        for token_norm in normalized_tokens:
            # Find entities with this token
            entity_ids_subq = session.query(EntityToken.entity_id).filter(
                EntityToken.token_normalized == token_norm
            ).distinct().subquery()

            if not candidates:
                # First token: get all entities with this token
                result = session.query(NamedEntity.id).filter(
                    NamedEntity.id.in_(entity_ids_subq),
                    NamedEntity.id != entity.id,  # Exclude self
                    NamedEntity.name_length > entity.name_length  # Only longer
                ).all()
                candidates = set([r[0] for r in result])
            else:
                # Subsequent tokens: intersect with existing candidates
                result = session.query(NamedEntity.id).filter(
                    NamedEntity.id.in_(entity_ids_subq),
                    NamedEntity.id.in_(list(candidates))
                ).all()
                candidates = set([r[0] for r in result])

    # ========================================================================
    # CRITERION 2: Initials/acronyms matching
    # ========================================================================
    # Only applies if:
    # - Entity has more than one non-stopword token, OR
    # - Entity is not already marked as initials
    if len(non_stopword_tokens) > 1 or not entity_seems_like_initials:
        # Calculate initials from evaluated entity
        # Remove stopwords and take first character of each word
        initials = ''.join([
            t.token_normalized[0]
            for t in non_stopword_tokens
            if t.token_normalized
        ])

        if initials:
            # Find entities with seems_like_initials=1 matching these initials
            initial_result = session.query(NamedEntity.id).join(
                EntityToken,
                NamedEntity.id == EntityToken.entity_id
            ).filter(
                EntityToken.seems_like_initials == 1,
                EntityToken.token_normalized == initials,
                NamedEntity.id != entity.id,
                NamedEntity.name_length > entity.name_length
            ).distinct().all()

            # Add to candidates set (extract IDs from tuples)
            initial_ids = [r[0] for r in initial_result]
            if not candidates:
                candidates = set(initial_ids)
            else:
                candidates.update(initial_ids)

    # Convert to list of NamedEntity objects
    if candidates:
        result = session.query(NamedEntity).filter(
            NamedEntity.id.in_(list(candidates))
        ).order_by(NamedEntity.name_length.asc()).limit(max_candidates).all()
        return result

    return []


def check_initials_match(
    evaluated: NamedEntity,
    candidate: NamedEntity,
    session: Session
) -> bool:
    """
    Check if evaluated entity is a valid match for candidate.

    This function checks TWO criteria:
    1. Token containment: All non-stopword tokens from evaluated are in candidate
    2. Initials match: Evaluated is acronym/initials of candidate

    Args:
        evaluated: Shorter entity (potential acronym or subset)
        candidate: Longer entity (potential full name)
        session: SQLAlchemy session

    Returns:
        True if either criterion matches, False otherwise

    Examples:
        Token containment:
        >>> check_initials_match("Luis Abinader", "Luis Abinader Corona", session)
        True

        Initials match:
        >>> check_initials_match("JCE", "Junta Central Electoral", session)
        True
        >>> check_initials_match("J.M. Fernández", "José Miguel Fernández", session)
        True
    """
    # Get non-stopword tokens for both entities
    eval_tokens = session.query(EntityToken).filter(
        EntityToken.entity_id == evaluated.id,
        EntityToken.is_stopword == 0
    ).order_by(EntityToken.position).all()

    cand_tokens = session.query(EntityToken).filter(
        EntityToken.entity_id == candidate.id,
        EntityToken.is_stopword == 0
    ).order_by(EntityToken.position).all()

    # ========================================================================
    # CRITERION 1: Token containment
    # All non-stopword tokens from evaluated must be present in candidate
    # ========================================================================
    eval_token_set = {t.token_normalized for t in eval_tokens}
    cand_token_set = {t.token_normalized for t in cand_tokens}

    if eval_token_set.issubset(cand_token_set):
        # All tokens from evaluated are in candidate
        return True

    # ========================================================================
    # CRITERION 2: Initials match
    # ========================================================================
    # Get initials
    eval_initials = ''.join([t.token_normalized[0] for t in eval_tokens if t.token_normalized])
    cand_initials = ''.join([t.token_normalized[0] for t in cand_tokens if t.token_normalized])

    # Basic check: initials match
    if eval_initials == cand_initials:
        return True

    # For PERSON entities: check if evaluated initials can be formed by
    # expanding middle names (e.g., "J.M. Fernández" matches "José Miguel Fernández")
    if evaluated.entity_type.value == 'person' and candidate.entity_type.value == 'person':
        # Try expanding each word in candidate to see if we can form evaluated
        eval_normalized = evaluated.name.replace('.', '').replace(' ', '').lower()

        for i, token in enumerate(cand_tokens):
            # Build candidate expansion: initial for this word, full names for others
            parts = []
            for j, t in enumerate(cand_tokens):
                if j == i:
                    # Use initial for this word
                    parts.append(t.token_normalized[0] if t.token_normalized else '')
                else:
                    # Use full word
                    parts.append(t.token_normalized)

            cand_expanded = ''.join(parts)

            if eval_normalized == cand_expanded:
                return True

    return False


def classify_entity(
    entity: NamedEntity,
    session: Session,
    dry_run: bool = True
) -> Tuple[str, Optional[NamedEntity], str]:
    """
    Classify a single entity using auto-classification algorithm.

    Implements the 9-case decision flow from the documentation.

    Args:
        entity: Entity to classify (must have last_review_type='none')
        session: SQLAlchemy session
        dry_run: If True, don't modify database (just return action)

    Returns:
        Tuple of (action, canonical_or_candidato, reason)
        - action: One of: 'no_match', 'alias', 'ambiguous', 'confirm', 'error'
        - canonical_or_candidato: The canonical entity or None
        - reason: Human-readable explanation

    Example:
        >>> entity = session.query(NamedEntity).filter_by(name="JCE").first()
        >>> action, canonical, reason = classify_entity(entity, session, dry_run=False)
        >>> print(f"{action}: {reason}")
        alias: Matched "Junta Central Electoral" (initials)
    """
    # Only process entities with last_review_type='none'
    if entity.last_review_type != 'none':
        return ('error', None, f'Entity already reviewed ({entity.last_review_type})')

    # Find candidates
    candidates = find_candidates_for_entity(entity, session)

    if not candidates:
        # No match found - mark as reviewed but don't change classification
        if not dry_run:
            entity.last_review_type = 'algorithmic'
            entity.last_review = datetime.utcnow()
            # is_approved NOT modified

        return ('no_match', None, 'No candidates found')

    # Check each candidate for a match
    matched_candidate = None
    for candidate in candidates:
        # Check if it's a valid match (initials or token containment)
        if check_initials_match(entity, candidate, session):
            matched_candidate = candidate
            break

    if not matched_candidate:
        # Candidates found but no match - mark as reviewed
        if not dry_run:
            entity.last_review_type = 'algorithmic'
            entity.last_review = datetime.utcnow()
            # is_approved NOT modified

        return ('no_match', None, f'Found {len(candidates)} candidates but no match')

    # We have a match! Now apply the decision flow
    # This will be implemented in the next function
    return apply_classification_rules(entity, matched_candidate, session, dry_run)


def apply_classification_rules(
    evaluated: NamedEntity,
    candidato: NamedEntity,
    session: Session,
    dry_run: bool = True
) -> Tuple[str, Optional[NamedEntity], str]:
    """
    Apply the 9-case decision flow based on evaluated and candidato classifications.

    Cases:
    - A1, A2, A3: Candidato is CANONICAL
    - B1, B2.1, B2.2, B3: Candidato is ALIAS
    - C1, C2, C3: Candidato is AMBIGUOUS

    Args:
        evaluated: The entity being evaluated (shorter)
        candidato: The matched candidate (longer)
        session: SQLAlchemy session
        dry_run: If True, don't modify database

    Returns:
        Tuple of (action, canonical, reason)
    """
    eval_class = evaluated.classified_as
    cand_class = candidato.classified_as

    # ========================================================================
    # CASO A: CANDIDATO es CANONICAL
    # ========================================================================
    if cand_class == EntityClassification.CANONICAL:
        # A1: Evaluada es CANONICAL
        if eval_class == EntityClassification.CANONICAL:
            if not dry_run:
                evaluated.set_as_alias(candidato, session)
                evaluated.last_review_type = 'algorithmic'
                evaluated.is_approved = 1  # ✅ APROBADO
                evaluated.last_review = datetime.utcnow()

            return ('alias', candidato, f'A1: CANONICAL → ALIAS of "{candidato.name}"')

        # A2: Evaluada es ALIAS
        elif eval_class == EntityClassification.ALIAS:
            canonical_vieja = evaluated.canonical_refs[0] if evaluated.canonical_refs else None

            if not dry_run:
                evaluated.set_as_ambiguous([canonical_vieja, candidato], session)
                evaluated.last_review_type = 'algorithmic'
                # is_approved NO se modifica
                evaluated.last_review = datetime.utcnow()

            return ('ambiguous', candidato, f'A2: ALIAS → AMBIGUOUS (conflict with "{canonical_vieja.name if canonical_vieja else "unknown"}")')

        # A3: Evaluada es AMBIGUOUS
        elif eval_class == EntityClassification.AMBIGUOUS:
            if not dry_run:
                evaluated.set_as_ambiguous(list(evaluated.canonical_refs) + [candidato], session)
                evaluated.last_review_type = 'algorithmic'
                # is_approved NO se modifica
                evaluated.last_review = datetime.utcnow()

            return ('ambiguous', candidato, f'A3: AMBIGUOUS + CANONICAL "{candidato.name}"')

    # ========================================================================
    # CASO B: CANDIDATO es ALIAS
    # ========================================================================
    elif cand_class == EntityClassification.ALIAS:
        cand_canonical = candidato.canonical_refs[0] if candidato.canonical_refs else None

        if not cand_canonical:
            return ('error', None, f'Candidato "{candidato.name}" is ALIAS but has no canonical_ref')

        # B1: Evaluada es CANONICAL
        if eval_class == EntityClassification.CANONICAL:
            if not dry_run:
                evaluated.set_as_alias(cand_canonical, session)
                evaluated.last_review_type = 'algorithmic'
                evaluated.is_approved = 1  # ✅ APROBADO
                evaluated.last_review = datetime.utcnow()

            return ('alias', cand_canonical, f'B1: CANONICAL → ALIAS of "{cand_canonical.name}" (via "{candidato.name}")')

        # B2: Evaluada es ALIAS
        elif eval_class == EntityClassification.ALIAS:
            eval_canonical = evaluated.canonical_refs[0] if evaluated.canonical_refs else None

            if not eval_canonical:
                return ('error', None, f'Evaluated "{evaluated.name}" is ALIAS but has no canonical_ref')

            # B2.1: Mismo canonical
            if eval_canonical.id == cand_canonical.id:
                if not dry_run:
                    # No change classification
                    evaluated.last_review_type = 'algorithmic'
                    evaluated.is_approved = 1  # ✅ APROBADO (confirma)
                    evaluated.last_review = datetime.utcnow()

                return ('confirm', cand_canonical, f'B2.1: Both ALIAS of "{cand_canonical.name}" (confirmed)')

            # B2.2: Distinto canonical
            else:
                if not dry_run:
                    evaluated.set_as_ambiguous([eval_canonical, cand_canonical], session)
                    evaluated.last_review_type = 'algorithmic'
                    # is_approved NO se modifica
                    evaluated.last_review = datetime.utcnow()

                return ('ambiguous', None, f'B2.2: ALIAS → AMBIGUOUS (conflict: "{eval_canonical.name}" vs "{cand_canonical.name}")')

        # B3: Evaluada es AMBIGUOUS
        elif eval_class == EntityClassification.AMBIGUOUS:
            # Check if cand_canonical already in evaluada.canonicals
            existing_canonical_ids = {c.id for c in evaluated.canonical_refs}

            if cand_canonical.id in existing_canonical_ids:
                # B3.1: Ya está incluido
                if not dry_run:
                    # No change canonicals
                    evaluated.last_review_type = 'algorithmic'
                    # is_approved NO se modifica
                    evaluated.last_review = datetime.utcnow()

                return ('confirm', cand_canonical, f'B3.1: Canonical "{cand_canonical.name}" already in AMBIGUOUS list')

            else:
                # B3.2: No está incluido
                if not dry_run:
                    evaluated.set_as_ambiguous(list(evaluated.canonical_refs) + [cand_canonical], session)
                    evaluated.last_review_type = 'algorithmic'
                    # is_approved NO se modifica
                    evaluated.last_review = datetime.utcnow()

                return ('ambiguous', cand_canonical, f'B3.2: AMBIGUOUS + canonical "{cand_canonical.name}"')

    # ========================================================================
    # CASO C: CANDIDATO es AMBIGUOUS
    # ========================================================================
    elif cand_class == EntityClassification.AMBIGUOUS:
        cand_canonicals = list(candidato.canonical_refs)

        if not cand_canonicals:
            return ('error', None, f'Candidato "{candidato.name}" is AMBIGUOUS but has no canonical_refs')

        # C1: Evaluada es CANONICAL
        if eval_class == EntityClassification.CANONICAL:
            # Check if evaluada already in candidato.canonicals
            if evaluated.id in {c.id for c in cand_canonicals}:
                # C1.1: Ya está incluida
                if not dry_run:
                    # No change canonicals
                    evaluated.last_review_type = 'algorithmic'
                    # is_approved NO se modifica
                    evaluated.last_review = datetime.utcnow()

                return ('confirm', None, f'C1.1: CANONICAL already in candidato\'s AMBIGUOUS list')

            else:
                # C1.2: No está incluida
                if not dry_run:
                    evaluated.set_as_ambiguous(cand_canonicals + [evaluated], session)
                    evaluated.last_review_type = 'algorithmic'
                    # is_approved NO se modifica
                    evaluated.last_review = datetime.utcnow()

                canon_names = ', '.join([c.name for c in cand_canonicals])
                return ('ambiguous', None, f'C1.2: CANONICAL → AMBIGUOUS ({canon_names})')

        # C2: Evaluada es ALIAS
        elif eval_class == EntityClassification.ALIAS:
            canonical_vieja = evaluated.canonical_refs[0] if evaluated.canonical_refs else None

            if not canonical_vieja:
                return ('error', None, f'Evaluated "{evaluated.name}" is ALIAS but has no canonical_ref')

            # Check if canonical_vieja already in candidato.canonicals
            if canonical_vieja.id in {c.id for c in cand_canonicals}:
                # C2.1: Ya está incluida
                if not dry_run:
                    evaluated.set_as_ambiguous(cand_canonicals, session)
                    evaluated.last_review_type = 'algorithmic'
                    # is_approved NO se modifica
                    evaluated.last_review = datetime.utcnow()

                return ('ambiguous', None, f'C2.1: ALIAS → AMBIGUOUS (canonical already in candidato list)')

            else:
                # C2.2: No está incluida
                if not dry_run:
                    evaluated.set_as_ambiguous([canonical_vieja] + cand_canonicals, session)
                    evaluated.last_review_type = 'algorithmic'
                    # is_approved NO se modifica
                    evaluated.last_review = datetime.utcnow()

                return ('ambiguous', None, f'C2.2: ALIAS → AMBIGUOUS (+ {len(cand_canonicals)} from candidato)')

        # C3: Evaluada es AMBIGUOUS
        elif eval_class == EntityClassification.AMBIGUOUS:
            eval_canonical_ids = {c.id for c in evaluated.canonical_refs}
            nuevas_canonicals = [c for c in cand_canonicals if c.id not in eval_canonical_ids]

            if not nuevas_canonicals:
                # C3.1: Sin nuevas
                if not dry_run:
                    # No change canonicals
                    evaluated.last_review_type = 'algorithmic'
                    # is_approved NO se modifica
                    evaluated.last_review = datetime.utcnow()

                return ('confirm', None, f'C3.1: All canonicals from candidato already in evaluated')

            else:
                # C3.2: Hay nuevas
                if not dry_run:
                    evaluated.set_as_ambiguous(list(evaluated.canonical_refs) + nuevas_canonicals, session)
                    evaluated.last_review_type = 'algorithmic'
                    # is_approved NO se modifica
                    evaluated.last_review = datetime.utcnow()

                return ('ambiguous', None, f'C3.2: AMBIGUOUS + {len(nuevas_canonicals)} new canonicals from candidato')

    return ('error', None, f'Unknown classification combination: {eval_class.value} vs {cand_class.value}')
