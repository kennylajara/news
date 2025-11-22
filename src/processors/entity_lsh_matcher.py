"""
LSH-based entity matching using MinHash for efficient candidate discovery.

Uses Locality Sensitive Hashing to find similar entities with O(n·k) complexity
instead of O(n²), making it scalable for large entity datasets.
"""

from typing import List, Set, Tuple
import re
from datasketch import MinHash, MinHashLSH
from sqlalchemy.orm import Session

from db.models import NamedEntity, EntityType


def normalize_text(text: str) -> str:
    """
    Normalize text for better comparison.

    Args:
        text: Input text to normalize

    Returns:
        Normalized lowercase text without accents or special characters
    """
    # Lowercase
    text = text.lower()

    # Remove accents (common Spanish characters)
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ñ': 'n',
        'ü': 'u', 'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u'
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)

    # Remove punctuation and special characters
    text = re.sub(r'[^\w\s]', '', text)

    # Collapse multiple spaces
    text = ' '.join(text.split())

    return text


def _is_spanish_plural_initials(text: str) -> bool:
    """Check if text is Spanish plural initials (e.g., EEUU, EE.UU., EE UU)."""
    clean = re.sub(r'[\s.]', '', text.upper())
    if len(clean) < 4 or len(clean) % 2 != 0:
        return False
    for i in range(0, len(clean), 2):
        if clean[i] != clean[i+1] or not clean[i].isalpha():
            return False
    return True


def _get_spanish_initials_variants(text: str) -> List[str]:
    """
    Get both collapsed and expanded variants of Spanish plural initials.

    "EE.UU." -> ["eeuu", "eu"]
    "EE. UU." -> ["ee uu", "eu"]
    """
    clean = re.sub(r'[\s.]', '', text.upper())
    # Collapsed: take first letter of each pair
    collapsed = ''.join(clean[i] for i in range(0, len(clean), 2)).lower()
    # Expanded: the full doubled form
    expanded = clean.lower()
    return [expanded, collapsed]


def text_to_shingles(text: str, char_ngram_size: int = 2, use_word_shingles: bool = False) -> Set[str]:
    """
    Convert text to shingles (character n-grams, optionally + word tokens).

    Args:
        text: Input text
        char_ngram_size: Size of character n-grams (default 2)
        use_word_shingles: If True, also include word tokens (default False)

    Returns:
        Set of shingle strings
    """
    shingles = set()

    # For Spanish plural initials, generate shingles for both variants
    if _is_spanish_plural_initials(text):
        variants = _get_spanish_initials_variants(text)
        for variant in variants:
            shingles.add(variant)
            # Add character n-grams for each variant
            for i in range(len(variant) - char_ngram_size + 1):
                ngram = variant[i:i + char_ngram_size]
                if ngram.strip():
                    shingles.add(ngram)
        return shingles

    text = normalize_text(text)

    # Word-level shingles (optional, disabled by default per benchmark)
    if use_word_shingles:
        words = text.split()
        for word in words:
            if word:  # Skip empty strings
                shingles.add(word)

    # Character-level n-grams (primary matching method)
    for i in range(len(text) - char_ngram_size + 1):
        ngram = text[i:i + char_ngram_size]
        if ngram.strip():  # Skip pure whitespace
            shingles.add(ngram)

    return shingles


def create_minhash(shingles: Set[str], num_perm: int = 50) -> MinHash:
    """
    Create MinHash signature from shingles.

    Args:
        shingles: Set of shingle strings
        num_perm: Number of permutations (default 50)

    Returns:
        MinHash object
    """
    minhash = MinHash(num_perm=num_perm)
    for shingle in shingles:
        minhash.update(shingle.encode('utf8'))
    return minhash


class EntityLSHMatcher:
    """
    LSH-based entity matcher for efficient candidate discovery.

    Builds an LSH index over entities and allows querying for similar candidates
    with sublinear time complexity.
    """

    def __init__(
        self,
        threshold: float = 0.3,
        num_perm: int = 50,
        char_ngram_size: int = 2,
        use_word_shingles: bool = False
    ):
        """
        Initialize LSH matcher.

        Args:
            threshold: Minimum Jaccard similarity to consider (default 0.3)
            num_perm: Number of MinHash permutations (default 50)
            char_ngram_size: Size of character n-grams (default 2)
            use_word_shingles: Include word tokens in shingles (default False)
        """
        self.threshold = threshold
        self.num_perm = num_perm
        self.char_ngram_size = char_ngram_size
        self.use_word_shingles = use_word_shingles

        # Use 25 bands for 50 permutations (optimal for threshold 0.3)
        bands = 25 if num_perm == 50 else None

        if bands:
            self.lsh = MinHashLSH(threshold=threshold, num_perm=num_perm, params=(bands, num_perm // bands))
        else:
            self.lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)

        self.minhashes = {}  # entity_id -> MinHash
        self.entities = {}   # entity_id -> NamedEntity

    def index_entity(self, entity: NamedEntity):
        """
        Add an entity to the LSH index.

        Args:
            entity: NamedEntity to index
        """
        shingles = text_to_shingles(entity.name, self.char_ngram_size, self.use_word_shingles)
        minhash = create_minhash(shingles, self.num_perm)

        # Store
        entity_key = str(entity.id)
        self.minhashes[entity_key] = minhash
        self.entities[entity_key] = entity

        # Insert into LSH
        self.lsh.insert(entity_key, minhash)

    def index_entities(self, entities: List[NamedEntity]):
        """
        Bulk index multiple entities.

        Args:
            entities: List of NamedEntity objects to index
        """
        for entity in entities:
            self.index_entity(entity)

    def find_candidates(
        self,
        entity: NamedEntity,
        max_candidates: int = 10,
        exclude_self: bool = True
    ) -> List[Tuple[NamedEntity, float]]:
        """
        Find candidate entities similar to the given entity.

        Args:
            entity: Entity to find candidates for
            max_candidates: Maximum number of candidates to return
            exclude_self: Whether to exclude the entity itself from results

        Returns:
            List of (candidate_entity, jaccard_similarity) tuples,
            sorted by similarity (highest first)
        """
        # Create MinHash for query entity
        shingles = text_to_shingles(entity.name, self.char_ngram_size, self.use_word_shingles)
        query_minhash = create_minhash(shingles, self.num_perm)

        # Query LSH for candidates
        candidate_keys = self.lsh.query(query_minhash)

        # Calculate actual Jaccard similarities
        results = []
        for key in candidate_keys:
            # Skip self if requested
            if exclude_self and key == str(entity.id):
                continue

            candidate = self.entities.get(key)
            if candidate is None:
                continue

            # Calculate exact Jaccard similarity
            candidate_minhash = self.minhashes[key]
            similarity = query_minhash.jaccard(candidate_minhash)

            results.append((candidate, similarity))

        # Sort by similarity (highest first) and limit
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:max_candidates]


def build_lsh_index_for_type(
    session: Session,
    entity_type: str,
    threshold: float = 0.3,
    only_canonical: bool = True,
    **lsh_kwargs
) -> EntityLSHMatcher:
    """
    Build LSH index for entities of a specific type.

    Args:
        session: SQLAlchemy session
        entity_type: Entity type to index ('person', 'org', 'gpe', etc.)
        threshold: Minimum Jaccard similarity threshold (default 0.3)
        only_canonical: Whether to only index CANONICAL entities
        **lsh_kwargs: Additional arguments for EntityLSHMatcher (num_perm, char_ngram_size, etc.)

    Returns:
        EntityLSHMatcher with indexed entities
    """
    from db.models import EntityClassification

    # Query entities - convert string to enum if needed
    type_enum = EntityType[entity_type.upper()] if isinstance(entity_type, str) else entity_type
    query = session.query(NamedEntity).filter(
        NamedEntity.entity_type == type_enum
    )

    if only_canonical:
        query = query.filter(
            NamedEntity.classified_as == EntityClassification.CANONICAL
        )

    entities = query.all()

    # Build index with optimized parameters
    matcher = EntityLSHMatcher(threshold=threshold, **lsh_kwargs)
    matcher.index_entities(entities)

    return matcher
