"""
SQLAlchemy models for news portal.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Table, ForeignKey, Index, Enum, JSON, Float
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base()


class ProcessType(enum.Enum):
    """Types of domain processing."""
    ENRICH_ARTICLE = "enrich_article"


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
    Index('idx_article_entities_article', 'article_id'),
    Index('idx_article_entities_entity', 'entity_id'),
    Index('idx_article_entities_relevance', 'relevance')
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    # Relationships
    source = relationship('Source', back_populates='articles')
    tags = relationship('Tag', secondary=article_tags, back_populates='articles')
    entities = relationship('NamedEntity', secondary=article_entities, backref='articles')

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
    description = Column(Text, nullable=True)
    photo_url = Column(String(500), nullable=True)
    article_count = Column(Integer, nullable=False, default=0)  # Number of articles that mention this entity
    trend = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<NamedEntity(name='{self.name}', type={self.entity_type.value}, article_count={self.article_count})>"


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
