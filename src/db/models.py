"""
SQLAlchemy models for news portal.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Table, ForeignKey, Index, Enum, JSON, Float, event
from sqlalchemy.orm import relationship, declarative_base, Session
from sqlalchemy.exc import IntegrityError
import enum

Base = declarative_base()


class ProcessType(enum.Enum):
    """Types of domain processing."""
    ENRICH_ARTICLE = "enrich_article"
    GENERATE_FLASH_NEWS = "generate_flash_news"


class EntityType(enum.Enum):
    """Types of named entities (based on spaCy NER labels)."""
    PERSON = "person"              # People, including fictional
    NORP = "norp"                  # Nationalities or religious or political groups
    FAC = "fac"                    # Buildings, airports, highways, bridges, etc.
    ORG = "org"                    # Companies, agencies, institutions, etc.
    GPE = "gpe"                    # Countries, cities, states
    LOC = "loc"                    # Non-GPE locations, mountain ranges, bodies of water
    PRODUCT = "product"            # Objects, vehicles, foods, etc. (Not services)
    EVENT = "event"                # Named hurricanes, battles, wars, sports events, etc.
    WORK_OF_ART = "work_of_art"    # Titles of books, songs, etc.
    LAW = "law"                    # Named documents made into laws
    LANGUAGE = "language"          # Any named language
    DATE = "date"                  # Absolute or relative dates or periods
    TIME = "time"                  # Times smaller than a day
    PERCENT = "percent"            # Percentage, including "%"
    MONEY = "money"                # Monetary values, including unit
    QUANTITY = "quantity"          # Measurements, as of weight or distance
    ORDINAL = "ordinal"            # "first", "second", etc.
    CARDINAL = "cardinal"          # Numerals that do not fall under another type


class ClusterCategory(enum.Enum):
    """Categories for sentence clusters based on importance."""
    CORE = "core"                  # Main topic of the article
    SECONDARY = "secondary"        # Important related topics
    FILLER = "filler"              # Filler or contextual information


class EntityClassification(enum.Enum):
    """Classification of named entities for disambiguation."""
    CANONICAL = "canonical"        # Primary entity (the "real" one)
    ALIAS = "alias"                # Alias/variant of another entity
    AMBIGUOUS = "ambiguous"        # Ambiguous entity that could refer to multiple canonical entities
    NOT_AN_ENTITY = "not_an_entity"  # False positive (not actually an entity)


class EntityOrigin(enum.Enum):
    """Origin of entity in article-entity relationship."""
    NER = "ner"                    # Detected by Named Entity Recognition
    CLASSIFICATION = "classification"  # Added by entity classification (ALIAS/AMBIGUOUS)

# Association table for many-to-many relationship between articles and tags
article_tags = Table(
    'article_tags',
    Base.metadata,
    Column('article_id', Integer, ForeignKey('articles.id', ondelete='CASCADE'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    Index('idx_article_tags_article', 'article_id'),
    Index('idx_article_tags_tag', 'tag_id')
)

# Association table for many-to-many relationship between articles and entities
article_entities = Table(
    'article_entities',
    Base.metadata,
    Column('article_id', Integer, ForeignKey('articles.id', ondelete='CASCADE'), primary_key=True),
    Column('entity_id', Integer, ForeignKey('named_entities.id', ondelete='CASCADE'), primary_key=True),
    Column('mentions', Integer, nullable=False, default=1),      # Number of mentions in this article
    Column('relevance', Float, nullable=False, default=0.0),     # Calculated relevance score for this article-entity pair
    Column('origin', Enum(EntityOrigin), nullable=False, default=EntityOrigin.NER), # Origin: NER (detected) or CLASSIFICATION (added)
    Column('context_sentences', JSON, nullable=True),            # List of sentences where entity was found (for manual review)
    Index('idx_article_entities_article_origin', 'article_id', 'origin'),  # Composite index for recalculation queries
    Index('idx_article_entities_entity', 'entity_id'),
    Index('idx_article_entities_relevance', 'relevance')
)

# Association table for entity canonical references
entity_canonical_refs = Table(
    'entity_canonical_refs',
    Base.metadata,
    Column('entity_id', Integer, ForeignKey('named_entities.id', ondelete='CASCADE'), primary_key=True),
    Column('canonical_id', Integer, ForeignKey('named_entities.id', ondelete='RESTRICT'), primary_key=True),
    Index('idx_entity_canonical_refs_entity', 'entity_id'),
    Index('idx_entity_canonical_refs_canonical', 'canonical_id')
)

# Table to track articles that need local relevance recalculation
articles_needs_rerank = Table(
    'articles_needs_rerank',
    Base.metadata,
    Column('article_id', Integer, ForeignKey('articles.id', ondelete='CASCADE'), primary_key=True),
    Column('created_at', DateTime, default=datetime.utcnow, nullable=False, index=True)
)


class Source(Base):
    """News source/domain."""
    __tablename__ = 'sources'

    id = Column(Integer, primary_key=True)
    domain = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    # Relationships
    articles = relationship('Article', back_populates='source', cascade='all, delete-orphan')
    processes = relationship('DomainProcess', back_populates='source', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Source(domain='{self.domain}', name='{self.name}')>"


class DomainProcess(Base):
    """Track last processing time for different process types per domain."""
    __tablename__ = 'domain_processes'

    source_id = Column(Integer, ForeignKey('sources.id', ondelete='CASCADE'), primary_key=True)
    process_type = Column(Enum(ProcessType), primary_key=True)
    last_processed_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    # Relationships
    source = relationship('Source', back_populates='processes')

    def __repr__(self):
        return f"<DomainProcess(source_id={self.source_id}, type={self.process_type.value}, last_processed_at={self.last_processed_at})>"


class Article(Base):
    """News article."""
    __tablename__ = 'articles'

    id = Column(Integer, primary_key=True)
    hash = Column(String(64), nullable=False, unique=True, index=True)
    url = Column(String(2048), nullable=False)  # No unique, no index - uniqueness guaranteed by hash
    source_id = Column(Integer, ForeignKey('sources.id'), nullable=False)

    title = Column(String(500), nullable=False)
    subtitle = Column(String(1000))
    author = Column(String(255))
    published_date = Column(DateTime, index=True)
    location = Column(String(255))
    content = Column(Text, nullable=False)
    category = Column(String(255))
    html_path = Column(String(500))

    enriched_at = Column(DateTime, nullable=True, index=True)
    cluster_enriched_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    # Relationships
    source = relationship('Source', back_populates='articles')
    tags = relationship('Tag', secondary=article_tags, back_populates='articles')
    entities = relationship('NamedEntity', secondary=article_entities, backref='articles')
    clusters = relationship('ArticleCluster', back_populates='article', cascade='all, delete-orphan')
    sentences = relationship('ArticleSentence', back_populates='article', cascade='all, delete-orphan')

    # Indexes
    __table_args__ = (
        Index('idx_article_source_hash', 'source_id', 'hash'),
    )

    def __repr__(self):
        return f"<Article(hash='{self.hash}', title='{self.title[:50]}...')>"


class Tag(Base):
    """Article tag/label."""
    __tablename__ = 'tags'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    # Relationships
    articles = relationship('Article', secondary=article_tags, back_populates='tags')

    def __repr__(self):
        return f"<Tag(name='{self.name}')>"


class NamedEntity(Base):
    """Named entity extracted from articles using NER."""
    __tablename__ = 'named_entities'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    entity_type = Column(Enum(EntityType), nullable=False)
    detected_types = Column(JSON, nullable=True)  # List of EntityType values spaCy has detected for this entity

    # Entity classification for disambiguation
    classified_as = Column(Enum(EntityClassification), nullable=False, default=EntityClassification.CANONICAL, index=True)

    description = Column(Text, nullable=True)
    photo_url = Column(String(500), nullable=True)
    article_count = Column(Integer, nullable=False, default=0)  # Number of articles that mention this entity
    avg_local_relevance = Column(Float, nullable=True, default=0.0)  # Average local relevance across articles
    diversity = Column(Integer, nullable=False, default=0)  # Number of unique entities co-occurring with
    pagerank = Column(Float, nullable=True, default=0.0)  # Raw PageRank score (unnormalized)
    global_relevance = Column(Float, nullable=True, default=0.0, index=True)  # Normalized PageRank (0.0-1.0, min-max scaled)
    last_rank_calculated_at = Column(DateTime, nullable=True, index=True)  # Last time global rank was calculated
    needs_review = Column(Integer, nullable=False, default=1, index=True)  # 1=needs review, 0=reviewed and correct
    last_review = Column(DateTime, nullable=True, index=True)  # Last time entity was manually reviewed
    trend = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    # Relationships
    canonical_refs = relationship(
        'NamedEntity',
        secondary=entity_canonical_refs,
        primaryjoin=id == entity_canonical_refs.c.entity_id,
        secondaryjoin=id == entity_canonical_refs.c.canonical_id,
        backref='referenced_by'  # Canonical entities can see who references them
    )

    def __repr__(self):
        return f"<NamedEntity(name='{self.name}', type={self.entity_type.value}, classified_as={self.classified_as.value})>"

    def _mark_articles_for_rerank(self, session):
        """
        Mark all articles containing this entity for local relevance recalculation.
        Internal helper called by classification change methods.
        """
        # Get all articles where this entity appears
        article_ids = session.query(article_entities.c.article_id).filter(
            article_entities.c.entity_id == self.id
        ).distinct().all()

        # Insert into articles_needs_rerank (ignore duplicates with INSERT IGNORE equivalent)
        for (article_id,) in article_ids:
            # Use INSERT OR IGNORE pattern (SQLite compatible)
            try:
                session.execute(
                    articles_needs_rerank.insert().values(
                        article_id=article_id,
                        created_at=datetime.utcnow()
                    )
                )
            except:
                # Duplicate, ignore
                pass

    # Helper methods for safe classification changes
    def set_as_not_entity(self, session):
        """
        Set entity as NOT_AN_ENTITY (false positive).

        Raises:
            ValueError: If entity is not persisted
        """
        if self.id is None:
            raise ValueError(
                f"Entity '{self.name}' must be persisted (committed/flushed) before changing classification"
            )

        # Mark articles for recalculation
        self._mark_articles_for_rerank(session)

        # Clear any existing canonical_refs relationships
        session.execute(
            entity_canonical_refs.delete().where(
                (entity_canonical_refs.c.entity_id == self.id) |
                (entity_canonical_refs.c.canonical_id == self.id)
            )
        )

        self.classified_as = EntityClassification.NOT_AN_ENTITY
        self.canonical_refs = []

    def set_as_canonical(self, session):
        """
        Set entity as CANONICAL.
        Validates: No outgoing canonical_refs relationships.

        Raises:
            ValueError: If entity is not persisted or has invalid relationships
        """
        if self.id is None:
            raise ValueError(
                f"Entity '{self.name}' must be persisted (committed/flushed) before changing classification"
            )

        # Mark articles for recalculation
        self._mark_articles_for_rerank(session)

        # Check no outgoing canonical_refs relationships
        outgoing_count = session.query(entity_canonical_refs).filter(
            entity_canonical_refs.c.entity_id == self.id
        ).count()

        if outgoing_count > 0:
            raise ValueError(
                f"Cannot set '{self.name}' as CANONICAL: has {outgoing_count} canonical_refs relationships. "
                f"Remove them first."
            )

        self.classified_as = EntityClassification.CANONICAL
        self.canonical_refs = []

    def set_as_alias(self, canonical_entity, session):
        """
        Set entity as ALIAS of another canonical entity.

        Args:
            canonical_entity: NamedEntity instance that this entity is an alias of
            session: SQLAlchemy session

        Raises:
            ValueError: If entity is not persisted or canonical_entity is invalid
        """
        if self.id is None:
            raise ValueError(
                f"Entity '{self.name}' must be persisted (committed/flushed) before changing classification"
            )

        if canonical_entity.id is None:
            raise ValueError(
                f"Canonical entity '{canonical_entity.name}' must be persisted before being referenced"
            )

        if canonical_entity.classified_as != EntityClassification.CANONICAL:
            raise ValueError(
                f"Cannot set alias: '{canonical_entity.name}' is not CANONICAL "
                f"(is {canonical_entity.classified_as.value})"
            )

        # Mark articles for recalculation
        self._mark_articles_for_rerank(session)

        # Clear any existing canonical_refs relationships
        session.execute(
            entity_canonical_refs.delete().where(
                (entity_canonical_refs.c.entity_id == self.id) |
                (entity_canonical_refs.c.canonical_id == self.id)
            )
        )

        self.classified_as = EntityClassification.ALIAS
        self.canonical_refs = [canonical_entity]

    def set_as_ambiguous(self, canonical_entities, session):
        """
        Set entity as AMBIGUOUS pointing to multiple canonical entities.

        Args:
            canonical_entities: List of NamedEntity instances (minimum 2, all must be CANONICAL)
            session: SQLAlchemy session

        Raises:
            ValueError: If entity is not persisted or canonical entities are invalid
        """
        if self.id is None:
            raise ValueError(
                f"Entity '{self.name}' must be persisted (committed/flushed) before changing classification"
            )

        if len(canonical_entities) < 2:
            raise ValueError(
                f"AMBIGUOUS entity must point to at least 2 canonical entities "
                f"(got {len(canonical_entities)})"
            )

        # Validate all are CANONICAL and persisted
        for entity in canonical_entities:
            if entity.id is None:
                raise ValueError(
                    f"Canonical entity '{entity.name}' must be persisted before being referenced"
                )
            if entity.classified_as != EntityClassification.CANONICAL:
                raise ValueError(
                    f"Cannot link to '{entity.name}': not CANONICAL "
                    f"(is {entity.classified_as.value})"
                )

        # Mark articles for recalculation
        self._mark_articles_for_rerank(session)

        self.classified_as = EntityClassification.AMBIGUOUS
        self.canonical_refs = canonical_entities

    def validate_classification(self, session):
        """
        Validate entity classification constraints.
        Returns tuple: (is_valid: bool, errors: List[str])

        Note: This method can be called even if entity is not yet persisted.
        """
        errors = []

        # If not persisted, can only validate basic field constraints
        if self.id is None:
            if self.classified_as == EntityClassification.CANONICAL:
                pass  # No canonical_refs expected
            elif self.classified_as == EntityClassification.ALIAS:
                # Can't validate canonical_refs before persistence
                errors.append("ALIAS entity not yet persisted - cannot validate canonical_refs")
            elif self.classified_as == EntityClassification.AMBIGUOUS:
                # Can't validate canonical_refs before persistence
                errors.append("AMBIGUOUS entity not yet persisted - cannot validate canonical_refs")
            elif self.classified_as == EntityClassification.NOT_AN_ENTITY:
                pass  # No canonical_refs expected

            return (len(errors) == 0, errors)

        # Full validation for persisted entities
        outgoing_count = session.query(entity_canonical_refs).filter(
            entity_canonical_refs.c.entity_id == self.id
        ).count()
        incoming_count = session.query(entity_canonical_refs).filter(
            entity_canonical_refs.c.canonical_id == self.id
        ).count()

        if self.classified_as == EntityClassification.CANONICAL:
            if outgoing_count > 0:
                errors.append(f"CANONICAL entity has {outgoing_count} outgoing canonical_refs")

        elif self.classified_as == EntityClassification.ALIAS:
            if outgoing_count != 1:
                errors.append(f"ALIAS entity must have exactly 1 canonical_ref (has {outgoing_count})")
            if incoming_count > 0:
                errors.append(f"ALIAS entity has {incoming_count} incoming canonical_refs")

        elif self.classified_as == EntityClassification.AMBIGUOUS:
            if outgoing_count < 2:
                errors.append(f"AMBIGUOUS entity must have 2+ canonical_refs (has {outgoing_count})")
            if incoming_count > 0:
                errors.append(f"AMBIGUOUS entity has {incoming_count} incoming canonical_refs")

        elif self.classified_as == EntityClassification.NOT_AN_ENTITY:
            if outgoing_count > 0 or incoming_count > 0:
                errors.append("NOT_AN_ENTITY cannot have canonical_refs relationships")

        return (len(errors) == 0, errors)


# Note: No automatic constraint validation for canonical_refs since it's a many-to-many relationship
# Use the set_as_* helper methods for safe classification changes, which handle all validation


class ProcessingBatch(Base):
    """Batch processing job for articles."""
    __tablename__ = 'processing_batches'

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey('sources.id', ondelete='CASCADE'), nullable=False, index=True)
    process_type = Column(Enum(ProcessType), nullable=False, index=True)
    status = Column(String(20), nullable=False, default='pending', index=True)  # pending, processing, completed, failed
    total_items = Column(Integer, nullable=False, default=0)
    processed_items = Column(Integer, nullable=False, default=0)
    successful_items = Column(Integer, nullable=False, default=0)
    failed_items = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    stats = Column(JSON, nullable=True)  # JSON field for additional statistics
    started_at = Column(DateTime, nullable=True, index=True)
    completed_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    # Relationships
    source = relationship('Source', backref='processing_batches')
    items = relationship('BatchItem', back_populates='batch', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<ProcessingBatch(id={self.id}, type={self.process_type.value}, status={self.status}, {self.processed_items}/{self.total_items})>"


class BatchItem(Base):
    """Individual item in a processing batch."""
    __tablename__ = 'batch_items'

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey('processing_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    article_id = Column(Integer, ForeignKey('articles.id', ondelete='CASCADE'), nullable=False, index=True)
    status = Column(String(20), nullable=False, default='pending', index=True)  # pending, processing, completed, failed, skipped
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)  # Processing logs for this item
    stats = Column(JSON, nullable=True)  # JSON field for item-specific statistics
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    # Relationships
    batch = relationship('ProcessingBatch', back_populates='items')
    article = relationship('Article', backref='batch_items')

    # Indexes
    __table_args__ = (
        Index('idx_batch_item_batch_status', 'batch_id', 'status'),
        Index('idx_batch_item_article', 'article_id'),
    )

    def __repr__(self):
        return f"<BatchItem(id={self.id}, batch_id={self.batch_id}, article_id={self.article_id}, status={self.status})>"


class ArticleCluster(Base):
    """Semantic cluster of sentences within an article."""
    __tablename__ = 'article_clusters'

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('articles.id', ondelete='CASCADE'), nullable=False, index=True)
    cluster_label = Column(Integer, nullable=False)  # 0, 1, 2... or -1 for noise
    category = Column(Enum(ClusterCategory), nullable=False)  # core, secondary, filler
    score = Column(Float, nullable=False, default=0.0)  # Importance score 0.0-1.0
    size = Column(Integer, nullable=False, default=0)  # Number of sentences in cluster
    centroid_embedding = Column(JSON, nullable=True)  # List of floats representing centroid
    sentence_indices = Column(JSON, nullable=False)  # List of sentence indices [0, 3, 5...]
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    # Relationships
    article = relationship('Article', back_populates='clusters')

    # Indexes
    __table_args__ = (
        Index('idx_article_cluster_article', 'article_id'),
        Index('idx_article_cluster_category', 'category'),
        Index('idx_article_cluster_score', 'score'),
    )

    def __repr__(self):
        return f"<ArticleCluster(id={self.id}, article_id={self.article_id}, label={self.cluster_label}, category={self.category.value}, score={self.score:.2f})>"


class ArticleSentence(Base):
    """Individual sentence in an article with its cluster assignment."""
    __tablename__ = 'article_sentences'

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('articles.id', ondelete='CASCADE'), nullable=False, index=True)
    sentence_index = Column(Integer, nullable=False)  # Position in article (0-based)
    sentence_text = Column(Text, nullable=False)
    cluster_id = Column(Integer, ForeignKey('article_clusters.id', ondelete='SET NULL'), nullable=True, index=True)
    embedding = Column(JSON, nullable=True)  # List of floats, optional
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    article = relationship('Article', back_populates='sentences')
    cluster = relationship('ArticleCluster', backref='sentences')

    # Indexes
    __table_args__ = (
        Index('idx_article_sentence_article', 'article_id'),
        Index('idx_article_sentence_index', 'article_id', 'sentence_index'),
        Index('idx_article_sentence_cluster', 'cluster_id'),
    )

    def __repr__(self):
        return f"<ArticleSentence(id={self.id}, article_id={self.article_id}, index={self.sentence_index}, cluster_id={self.cluster_id})>"


class FlashNews(Base):
    """Flash news generated from core article clusters."""
    __tablename__ = 'flash_news'

    id = Column(Integer, primary_key=True)
    cluster_id = Column(Integer, ForeignKey('article_clusters.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    summary = Column(Text, nullable=False)  # LLM-generated summary
    embedding = Column(JSON, nullable=True)  # Vector embedding of summary (list of floats)
    published = Column(Integer, nullable=False, default=0)  # 0=unpublished, 1=published (SQLite doesn't have native boolean)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    # Relationships
    cluster = relationship('ArticleCluster', backref='flash_news')

    # Indexes
    __table_args__ = (
        Index('idx_flash_news_cluster', 'cluster_id'),
        Index('idx_flash_news_published', 'published'),
        Index('idx_flash_news_created', 'created_at'),
    )

    def __repr__(self):
        return f"<FlashNews(id={self.id}, cluster_id={self.cluster_id}, published={bool(self.published)}, summary='{self.summary[:50]}...')>"
