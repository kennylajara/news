"""
SQLAlchemy models for news portal.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Table, ForeignKey, Index, Enum, JSON, Float, event, update
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

# Table for group memberships with temporal tracking
entity_group_members = Table(
    'entity_group_members',
    Base.metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('group_id', Integer, ForeignKey('named_entities.id', ondelete='CASCADE'), nullable=False),
    Column('member_id', Integer, ForeignKey('named_entities.id', ondelete='CASCADE'), nullable=False),
    Column('role', String(100), nullable=True),  # Role within the group (e.g., "vocalist", "CEO", "minister")
    Column('since', DateTime, nullable=True, index=True),  # Start date (NULL = unknown/always)
    Column('until', DateTime, nullable=True, index=True),  # End date (NULL = present/ongoing)
    Column('created_at', DateTime, default=datetime.utcnow, nullable=False),
    Column('updated_at', DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False),
    Index('idx_entity_group_members_group', 'group_id'),
    Index('idx_entity_group_members_member', 'member_id'),
    Index('idx_entity_group_members_dates', 'group_id', 'member_id', 'since', 'until'),  # For temporal queries
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
    cleaned_html_hash = Column(String(64), nullable=True)  # SHA-256 hash of cleaned HTML (for change detection)

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

    # Group flag (only meaningful for CANONICAL entities)
    is_group = Column(Integer, nullable=False, default=0, index=True)  # 0=no, 1=yes (SQLite doesn't have native boolean)

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

    # Group relationships (only meaningful when is_group=1)
    members = relationship(
        'NamedEntity',
        secondary=entity_group_members,
        primaryjoin=id == entity_group_members.c.group_id,
        secondaryjoin=id == entity_group_members.c.member_id,
        backref='member_of_groups',  # Inverse: groups this entity is a member of
        viewonly=True  # Prevent automatic sync (we manage manually for temporal control)
    )

    def __repr__(self):
        return f"<NamedEntity(name='{self.name}', type={self.entity_type.value}, classified_as={self.classified_as.value}, is_group={self.is_group})>"

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

        This method SUMS the provided canonical entities with any existing ones,
        ensuring no duplicates.

        Args:
            canonical_entities: List of NamedEntity instances (all must be CANONICAL)
            session: SQLAlchemy session

        Raises:
            ValueError: If entity is not persisted, canonical entities are invalid,
                       or final count would be less than 2
        """
        if self.id is None:
            raise ValueError(
                f"Entity '{self.name}' must be persisted (committed/flushed) before changing classification"
            )

        if len(canonical_entities) < 1:
            raise ValueError(
                f"Must provide at least 1 canonical entity (got {len(canonical_entities)})"
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

        # Sum new canonical_entities with existing ones (avoiding duplicates)
        existing_canonical_ids = {e.id for e in self.canonical_refs}
        new_canonicals = [e for e in canonical_entities if e.id not in existing_canonical_ids]

        # Combine existing + new (unique by ID)
        combined_canonicals = list(self.canonical_refs) + new_canonicals

        # Validate final count is at least 2
        if len(combined_canonicals) < 2:
            raise ValueError(
                f"AMBIGUOUS entity must point to at least 2 canonical entities "
                f"(would have {len(combined_canonicals)} after merge)"
            )

        self.classified_as = EntityClassification.AMBIGUOUS
        self.canonical_refs = combined_canonicals

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

    # ====================
    # Group Management Methods
    # ====================

    def set_as_group(self, session):
        """
        Mark this entity as a group.

        Only CANONICAL entities can be marked as groups.

        Raises:
            ValueError: If entity is not CANONICAL
        """
        if self.classified_as != EntityClassification.CANONICAL:
            raise ValueError(
                f"Only CANONICAL entities can be groups. "
                f"Entity '{self.name}' is {self.classified_as.value}"
            )

        self.is_group = 1

    def unset_as_group(self, session):
        """
        Unmark this entity as a group.

        Raises:
            ValueError: If entity still has members
        """
        if self.id is not None:
            # Check if entity has members
            member_count = session.query(entity_group_members).filter(
                entity_group_members.c.group_id == self.id
            ).count()

            if member_count > 0:
                raise ValueError(
                    f"Cannot unset group: entity '{self.name}' still has {member_count} member(s). "
                    f"Remove all members first."
                )

        self.is_group = 0

    def _check_membership_overlap(self, member_id, since, until, session, exclude_membership_id=None):
        """
        Check if a membership period overlaps with existing memberships.

        Args:
            member_id: ID of the member to check
            since: Start date of new membership (can be None)
            until: End date of new membership (can be None)
            session: SQLAlchemy session
            exclude_membership_id: Membership ID to exclude from check (for updates)

        Returns:
            bool: True if there's an overlap, False otherwise
        """
        if self.id is None:
            return False  # Entity not persisted yet, no existing memberships

        # Query existing memberships for this (group_id, member_id) pair
        query = session.query(entity_group_members).filter(
            entity_group_members.c.group_id == self.id,
            entity_group_members.c.member_id == member_id
        )

        if exclude_membership_id:
            query = query.filter(entity_group_members.c.id != exclude_membership_id)

        existing_memberships = query.all()

        # Check for overlaps
        for membership in existing_memberships:
            existing_since = membership.since
            existing_until = membership.until

            # Two periods overlap if:
            # - new_since < existing_until (or existing_until is NULL)
            # AND
            # - new_until > existing_since (or new_until is NULL)

            # Handle NULL dates (NULL means open-ended)
            new_since = since if since else datetime.min
            new_until = until if until else datetime.max
            existing_since_cmp = existing_since if existing_since else datetime.min
            existing_until_cmp = existing_until if existing_until else datetime.max

            if new_since < existing_until_cmp and new_until > existing_since_cmp:
                return True  # Overlap detected

        return False

    def add_member(self, member, role=None, since=None, until=None, session=None):
        """
        Add a member to this group.

        Args:
            member: NamedEntity instance to add as member
            role: Optional role within the group
            since: Start date (None = unknown/always)
            until: End date (None = present/ongoing)
            session: SQLAlchemy session (required for overlap check)

        Raises:
            ValueError: If entity is not a group, member is not persisted, or period overlaps
        """
        if not self.is_group:
            raise ValueError(
                f"Entity '{self.name}' is not a group. Use set_as_group() first."
            )

        if self.id is None:
            raise ValueError(
                f"Group '{self.name}' must be persisted before adding members"
            )

        if member.id is None:
            raise ValueError(
                f"Member '{member.name}' must be persisted before being added to group"
            )

        if session is None:
            raise ValueError("session parameter is required for overlap validation")

        # Prevent self-membership
        if self.id == member.id:
            raise ValueError(
                f"Entity cannot be a member of itself: '{self.name}'"
            )

        # Validate date range
        if since and until and since > until:
            raise ValueError(
                f"Invalid date range: since ({since.strftime('%Y-%m-%d')}) must be before until ({until.strftime('%Y-%m-%d')})"
            )

        # Prevent future dates
        now = datetime.utcnow()
        if since and since > now:
            raise ValueError(
                f"Start date cannot be in the future: {since.strftime('%Y-%m-%d')}"
            )
        if until and until > now:
            raise ValueError(
                f"End date cannot be in the future: {until.strftime('%Y-%m-%d')}"
            )

        # Check for overlapping periods
        if self._check_membership_overlap(member.id, since, until, session):
            raise ValueError(
                f"Membership period overlaps with existing membership for '{member.name}' in group '{self.name}'"
            )

        # Insert membership
        session.execute(
            entity_group_members.insert().values(
                group_id=self.id,
                member_id=member.id,
                role=role,
                since=since,
                until=until,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
        )

    def remove_member(self, member, until_date=None, session=None):
        """
        Mark a member as having left the group by setting the 'until' date.

        Finds the active membership (until=NULL) and sets its until date.

        Args:
            member: NamedEntity instance to remove
            until_date: Date when member left (default: now)
            session: SQLAlchemy session

        Raises:
            ValueError: If no active membership found
        """
        if not self.is_group:
            raise ValueError(
                f"Entity '{self.name}' is not a group"
            )

        if self.id is None or member.id is None:
            raise ValueError("Both group and member must be persisted")

        if session is None:
            raise ValueError("session parameter is required")

        if until_date is None:
            until_date = datetime.utcnow()

        # Find active membership (until=NULL)
        result = session.execute(
            update(entity_group_members).where(
                (entity_group_members.c.group_id == self.id) &
                (entity_group_members.c.member_id == member.id) &
                (entity_group_members.c.until.is_(None))
            ).values(
                until=until_date,
                updated_at=datetime.utcnow()
            )
        )

        if result.rowcount == 0:
            raise ValueError(
                f"No active membership found for '{member.name}' in group '{self.name}'"
            )

    def get_active_members_at(self, date, session):
        """
        Get members that were active in the group at a specific date.

        Args:
            date: datetime object (usually article.published_date)
            session: SQLAlchemy session

        Returns:
            List of NamedEntity members active at that date
        """
        if not self.is_group:
            return []

        if self.id is None:
            return []

        # Query members where:
        # - since <= date (or since IS NULL)
        # - until >= date (or until IS NULL)
        from sqlalchemy import and_, or_

        members = session.query(NamedEntity).join(
            entity_group_members,
            NamedEntity.id == entity_group_members.c.member_id
        ).filter(
            entity_group_members.c.group_id == self.id,
            # since condition: NULL or since <= date
            or_(
                entity_group_members.c.since.is_(None),
                entity_group_members.c.since <= date
            ),
            # until condition: NULL or until >= date
            or_(
                entity_group_members.c.until.is_(None),
                entity_group_members.c.until >= date
            )
        ).all()

        return members

    def get_active_groups_at(self, date, session):
        """
        Get groups this entity was a member of at a specific date.

        Args:
            date: datetime object
            session: SQLAlchemy session

        Returns:
            List of NamedEntity groups this entity belonged to at that date
        """
        if self.id is None:
            return []

        from sqlalchemy import and_, or_

        groups = session.query(NamedEntity).join(
            entity_group_members,
            NamedEntity.id == entity_group_members.c.group_id
        ).filter(
            entity_group_members.c.member_id == self.id,
            NamedEntity.is_group == 1,
            # since condition
            or_(
                entity_group_members.c.since.is_(None),
                entity_group_members.c.since <= date
            ),
            # until condition
            or_(
                entity_group_members.c.until.is_(None),
                entity_group_members.c.until >= date
            )
        ).all()

        return groups


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
