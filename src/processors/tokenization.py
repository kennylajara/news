"""
Tokenization utilities for entity auto-classification.

This module provides functions to tokenize entity names and populate the
entity_tokens reverse index table.
"""

import re
import unicodedata
from datetime import datetime
from sqlalchemy.orm import Session
from db.models import EntityToken


# TODO: Use Spacy
# Spanish stopwords (common words to mark but still index)
SPANISH_STOPWORDS = {
    'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
    'de', 'del', 'al', 'a', 'en', 'por', 'para', 'con', 'sin',
    'y', 'o', 'u', 'e', 'ni',
    'que', 'cual', 'cuales', 'quien', 'quienes',
    'este', 'esta', 'estos', 'estas',
    'ese', 'esa', 'esos', 'esas',
    'aquel', 'aquella', 'aquellos', 'aquellas',
}


def normalize_token(token: str) -> str:
    """
    Normalize a token for matching.

    - Convert to lowercase
    - Remove accents/diacritics
    - Remove periods

    Args:
        token: Original token

    Returns:
        Normalized token (lowercase, no accents, no periods)

    Examples:
        >>> normalize_token("José")
        'jose'
        >>> normalize_token("J.C.E.")
        'jce'
        >>> normalize_token("República")
        'republica'
    """
    # Convert to lowercase
    token = token.lower()

    # Remove accents/diacritics using NFD normalization
    # This decomposes characters like 'é' into 'e' + accent
    token = ''.join(
        c for c in unicodedata.normalize('NFD', token)
        if unicodedata.category(c) != 'Mn'  # Mn = Nonspacing Mark (accents)
    )

    # Remove periods
    token = token.replace('.', '')

    return token


def tokenize_entity_name(name: str) -> list[dict]:
    """
    Tokenize entity name into individual tokens with metadata.

    Tokenization rules:
    - Separator: any character that is not a letter or number
    - Special case for periods: NOT a separator if surrounded by letters/numbers
      Example: "J.C.E." → periods between letters are kept
    - If token contains internal periods, add final period
      Example: "J.C.E" → "J.C.E."

    Args:
        name: Entity name to tokenize (e.g., "Junta Central Electoral")

    Returns:
        List of token dictionaries with keys:
        - token: Original token with formatting
        - token_normalized: Normalized token (lowercase, no accents, no periods)
        - position: Position in entity name (0-indexed)
        - is_stopword: Whether token is a stopword (0 or 1)
        - seems_like_initials: Whether token appears to be initials (0 or 1)

    Examples:
        >>> tokenize_entity_name("Junta Central Electoral")
        [
            {'token': 'Junta', 'token_normalized': 'junta', 'position': 0, 'is_stopword': 0, 'seems_like_initials': 0},
            {'token': 'Central', 'token_normalized': 'central', 'position': 1, 'is_stopword': 0, 'seems_like_initials': 0},
            {'token': 'Electoral', 'token_normalized': 'electoral', 'position': 2, 'is_stopword': 0, 'seems_like_initials': 0}
        ]

        >>> tokenize_entity_name("J.C.E.")
        [{'token': 'J.C.E.', 'token_normalized': 'jce', 'position': 0, 'is_stopword': 0, 'seems_like_initials': 1}]

        >>> tokenize_entity_name("Banco Central de la República Dominicana")
        # Returns 6 tokens, with 'de' and 'la' marked as is_stopword=1
    """
    tokens = []
    position = 0

    # Split by any character that is not alphanumeric, but handle periods specially
    # Use regex to split but keep track of positions

    # First pass: identify token boundaries
    # A token is a sequence of alphanumeric characters, possibly with internal periods
    # that are surrounded by alphanumeric characters

    current_token = ""
    i = 0

    while i < len(name):
        char = name[i]

        if char.isalnum():
            # Alphanumeric character - add to current token
            current_token += char
            i += 1
        elif char == '.':
            # Period - check if surrounded by alphanumeric
            prev_is_alnum = (i > 0 and name[i-1].isalnum())
            next_is_alnum = (i < len(name) - 1 and name[i+1].isalnum())

            if prev_is_alnum and next_is_alnum:
                # Internal period - keep it
                current_token += char
                i += 1
            else:
                # Boundary period - finalize token and skip period
                if current_token:
                    # Check if token has internal periods
                    if '.' in current_token and not current_token.endswith('.'):
                        current_token += '.'
                    tokens.append(current_token)
                    current_token = ""
                i += 1
        else:
            # Other separator - finalize current token
            if current_token:
                # Check if token has internal periods
                if '.' in current_token and not current_token.endswith('.'):
                    current_token += '.'
                tokens.append(current_token)
                current_token = ""
            i += 1

    # Don't forget last token
    if current_token:
        # Check if token has internal periods
        if '.' in current_token and not current_token.endswith('.'):
            current_token += '.'
        tokens.append(current_token)

    # Second pass: create token metadata
    result = []
    non_stopword_count = 0

    for pos, token in enumerate(tokens):
        normalized = normalize_token(token)
        is_stopword = 1 if normalized in SPANISH_STOPWORDS else 0

        if not is_stopword:
            non_stopword_count += 1

        token_data = {
            'token': token,
            'token_normalized': normalized,
            'position': pos,
            'is_stopword': is_stopword,
            'seems_like_initials': 0  # Will be calculated after counting non-stopwords
        }

        result.append(token_data)

    # Third pass: determine seems_like_initials
    # Criteria for single token:
    # 1. Token is all uppercase
    # 2. Entity has exactly one non-stopword token
    # 3. Token (without periods) equals entity name (without periods)

    if non_stopword_count == 1:
        # Find the single non-stopword token
        for token_data in result:
            if not token_data['is_stopword']:
                token_no_periods = token_data['token'].replace('.', '')
                name_no_periods = name.replace('.', '')

                # Check if all uppercase and matches entity name
                if (token_no_periods.isupper() and
                    token_no_periods.lower() == name_no_periods.lower()):
                    token_data['seems_like_initials'] = 1
                break

    return result


def populate_entity_tokens(entity_id: int, entity_name: str, session: Session) -> int:
    """
    Populate entity_tokens table for a given entity.

    This should be called when:
    - A new entity is created
    - An entity's name is updated

    Args:
        entity_id: ID of the entity
        entity_name: Name of the entity
        session: SQLAlchemy session

    Returns:
        Number of tokens created

    Example:
        >>> session = get_session()
        >>> entity = NamedEntity(name="Junta Central Electoral", ...)
        >>> session.add(entity)
        >>> session.flush()
        >>> count = populate_entity_tokens(entity.id, entity.name, session)
        >>> print(f"Created {count} tokens")
        Created 3 tokens
    """
    # First, delete any existing tokens for this entity
    session.query(EntityToken).filter_by(entity_id=entity_id).delete()

    # Tokenize the entity name
    tokens = tokenize_entity_name(entity_name)

    # Create EntityToken records
    for token_data in tokens:
        entity_token = EntityToken(
            entity_id=entity_id,
            token=token_data['token'],
            token_normalized=token_data['token_normalized'],
            position=token_data['position'],
            is_stopword=token_data['is_stopword'],
            seems_like_initials=token_data['seems_like_initials'],
            created_at=datetime.utcnow()
        )
        session.add(entity_token)

    return len(tokens)


def update_entity_tokens(entity_id: int, new_name: str, session: Session) -> int:
    """
    Update entity_tokens when an entity's name changes.

    This deletes old tokens and creates new ones.

    Args:
        entity_id: ID of the entity
        new_name: New name of the entity
        session: SQLAlchemy session

    Returns:
        Number of tokens created
    """
    return populate_entity_tokens(entity_id, new_name, session)
