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
    ANALYZE_ARTICLE = "analyze_article"


class EntityType(enum.Enum):
    """Types of named entities for recommendation systems."""
    PERSON = "PERSON"       # Specific individuals users follow (Nicolás Maduro, Donald Trump)
    ORG = "ORG"             # Organizations, companies, institutions (PSUV, Apple, Gobierno de Venezuela)
    GPE = "GPE"             # Geographic locations for filtering (Venezuela, Caracas, Estados Unidos)
    EVENT = "EVENT"         # Named events for grouping coverage (Elecciones 2024, Copa Mundial)
    PRODUCT = "PRODUCT"     # Specific products/services (iPhone 16, ChatGPT, Tesla Model 3)
    NORP = "NORP"           # Political/religious/ethnic groups (chavistas, republicanos, evangélicos)
    FAC = "FAC"             # Buildings, airports, highways, bridges (Aeropuerto Las Américas, Autopista Duarte)
    LOC = "LOC"             # Non-GPE locations, mountain ranges, bodies of water (Cordillera Central, Mar Caribe)


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
    AI_ANALYSIS = "ai_analysis"    # Extracted by OpenAI during article analysis
    CLASSIFICATION = "classification"  # Added by entity classification (ALIAS/AMBIGUOUS)


class ReviewType(enum.Enum):
    """Type of review performed on entity."""
    NONE = "none"                  # No review performed
    AI_ASSISTED = "ai_assisted"    # AI-assisted classification
    MANUAL = "manual"              # Manual human review

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
    Column('origin', Enum(EntityOrigin), nullable=False, default=EntityOrigin.AI_ANALYSIS), # Origin: AI_ANALYSIS (extracted) or CLASSIFICATION (added)
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
    authority_score = Column(Float, nullable=True, default=0.5)  # 0.0-1.0, default neutral (optional for flash news relevance)
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

    clusterized_at = Column(DateTime, nullable=True, index=True)
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
    name = Column(String(255), nullable=False, index=True)
    name_length = Column(Integer, nullable=False, index=True)  # len(name) - for ordering by length
    entity_type = Column(Enum(EntityType), nullable=False, index=True)
    detected_types = Column(JSON, nullable=True)  # List of EntityType values detected for this entity

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

    # Review and approval fields
    last_review_type = Column(Enum(ReviewType), nullable=False, default=ReviewType.NONE, index=True)
    is_approved = Column(Integer, nullable=False, default=0, index=True)  # 0=no, 1=yes
    last_review = Column(DateTime, nullable=True, index=True)  # Last time entity was reviewed

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

    # Table constraints
    __table_args__ = (
        # Unique constraint on (name, entity_type) to allow same name with different types
        Index('idx_entity_name_type_unique', 'name', 'entity_type', unique=True),
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

    def _update_dependents_on_canonical_to_alias(self, new_canonical_entity, session):
        """
        Update dependent entities when a CANONICAL entity becomes an ALIAS.

        This is called BEFORE changing self from CANONICAL to ALIAS.

        Rules:
        - Dependent ALIAS entities: redirect to new_canonical_entity
        - Dependent AMBIGUOUS entities: replace self with new_canonical_entity in their list

        Args:
            new_canonical_entity: The new canonical this entity will point to
            session: SQLAlchemy session
        """
        if self.classified_as != EntityClassification.CANONICAL:
            # This method should only be called on CANONICAL entities
            return

        # Find all ALIAS entities pointing to self
        dependent_aliases = session.query(NamedEntity).join(
            entity_canonical_refs,
            NamedEntity.id == entity_canonical_refs.c.entity_id
        ).filter(
            entity_canonical_refs.c.canonical_id == self.id,
            NamedEntity.classified_as == EntityClassification.ALIAS
        ).all()

        # Find all AMBIGUOUS entities that have self in their canonical_refs
        dependent_ambiguous = session.query(NamedEntity).join(
            entity_canonical_refs,
            NamedEntity.id == entity_canonical_refs.c.entity_id
        ).filter(
            entity_canonical_refs.c.canonical_id == self.id,
            NamedEntity.classified_as == EntityClassification.AMBIGUOUS
        ).all()

        # Update ALIAS dependents: redirect to new canonical
        for alias_entity in dependent_aliases:
            alias_entity.canonical_refs = [new_canonical_entity]

        # Update AMBIGUOUS dependents: replace self with new_canonical in list
        for ambiguous_entity in dependent_ambiguous:
            # Remove self from list and add new_canonical_entity
            current_canonicals = [e for e in ambiguous_entity.canonical_refs if e.id != self.id]

            # Add new canonical if not already in list
            if new_canonical_entity.id not in {e.id for e in current_canonicals}:
                current_canonicals.append(new_canonical_entity)

            # Ensure we still have at least 2 canonicals
            if len(current_canonicals) >= 2:
                ambiguous_entity.canonical_refs = current_canonicals
            else:
                # If only 1 canonical left, convert to ALIAS
                ambiguous_entity.classified_as = EntityClassification.ALIAS
                ambiguous_entity.canonical_refs = current_canonicals

    def _update_dependents_on_canonical_to_ambiguous(self, new_canonical_entities, session):
        """
        Update dependent entities when a CANONICAL entity becomes AMBIGUOUS.

        This is called BEFORE changing self from CANONICAL to AMBIGUOUS.

        Rules:
        - Dependent ALIAS entities: convert to AMBIGUOUS with same canonicals
        - Dependent AMBIGUOUS entities: replace self with new_canonical_entities (expand list)

        Args:
            new_canonical_entities: List of new canonicals this entity will point to
            session: SQLAlchemy session
        """
        if self.classified_as != EntityClassification.CANONICAL:
            # This method should only be called on CANONICAL entities
            return

        # Find all ALIAS entities pointing to self
        dependent_aliases = session.query(NamedEntity).join(
            entity_canonical_refs,
            NamedEntity.id == entity_canonical_refs.c.entity_id
        ).filter(
            entity_canonical_refs.c.canonical_id == self.id,
            NamedEntity.classified_as == EntityClassification.ALIAS
        ).all()

        # Find all AMBIGUOUS entities that have self in their canonical_refs
        dependent_ambiguous = session.query(NamedEntity).join(
            entity_canonical_refs,
            NamedEntity.id == entity_canonical_refs.c.entity_id
        ).filter(
            entity_canonical_refs.c.canonical_id == self.id,
            NamedEntity.classified_as == EntityClassification.AMBIGUOUS
        ).all()

        # Update ALIAS dependents: convert to AMBIGUOUS with same canonicals
        for alias_entity in dependent_aliases:
            alias_entity.classified_as = EntityClassification.AMBIGUOUS
            alias_entity.canonical_refs = new_canonical_entities

        # Update AMBIGUOUS dependents: replace self with new_canonical_entities (expand list)
        for ambiguous_entity in dependent_ambiguous:
            # Remove self from list
            current_canonicals = [e for e in ambiguous_entity.canonical_refs if e.id != self.id]

            # Add all new canonicals if not already in list
            current_ids = {e.id for e in current_canonicals}
            for new_canonical in new_canonical_entities:
                if new_canonical.id not in current_ids:
                    current_canonicals.append(new_canonical)
                    current_ids.add(new_canonical.id)

            # Update the list
            ambiguous_entity.canonical_refs = current_canonicals

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

        # CASCADE: Update dependents if this is currently CANONICAL
        if self.classified_as == EntityClassification.CANONICAL:
            self._update_dependents_on_canonical_to_alias(canonical_entity, session)

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

        # CASCADE: Update dependents if this is currently CANONICAL
        if self.classified_as == EntityClassification.CANONICAL:
            self._update_dependents_on_canonical_to_ambiguous(canonical_entities, session)

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


class EntityToken(Base):
    """Reverse index for entity tokens to enable efficient matching."""
    __tablename__ = 'entity_tokens'

    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey('named_entities.id', ondelete='CASCADE'), nullable=False)
    token = Column(String(100), nullable=False)  # Original token with formatting (e.g., "J.C.E.", "Junta")
    token_normalized = Column(String(100), nullable=False, index=True)  # Normalized: lowercase, no accents, no periods
    position = Column(Integer, nullable=False)  # Position in entity name (0-indexed)
    is_stopword = Column(Integer, nullable=False, default=0)  # 0=no, 1=yes
    seems_like_initials = Column(Integer, nullable=False, default=0, index=True)  # 0=no, 1=yes (all caps, single token)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Indexes for efficient searches
    __table_args__ = (
        Index('idx_entity_tokens_entity', 'entity_id'),
        Index('idx_entity_tokens_composite', 'token_normalized', 'entity_id'),
    )

    def __repr__(self):
        return f"<EntityToken(entity_id={self.entity_id}, token='{self.token}', normalized='{self.token_normalized}', position={self.position})>"


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

    # Relevance scoring fields
    relevance_score = Column(Float, nullable=True, default=0.0, index=True)  # Composite relevance score (0.0-1.0)
    relevance_components = Column(JSON, nullable=True)  # Breakdown of score components for debugging
    relevance_calculated_at = Column(DateTime, nullable=True, index=True)  # When score was last calculated
    priority = Column(String(20), nullable=True, index=True)  # 'critical', 'high', 'medium', 'low'

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    # Relationships
    cluster = relationship('ArticleCluster', backref='flash_news')

    # Indexes
    __table_args__ = (
        Index('idx_flash_news_cluster', 'cluster_id'),
        Index('idx_flash_news_published', 'published'),
        Index('idx_flash_news_created', 'created_at'),
        Index('idx_flash_news_relevance', 'relevance_score'),
        Index('idx_flash_news_priority', 'priority'),
    )

    def __repr__(self):
        return f"<FlashNews(id={self.id}, cluster_id={self.cluster_id}, published={bool(self.published)}, summary='{self.summary[:50]}...')>"


class ArticleAnalysis(Base):
    """Deep analysis of article for recommendation system matching."""
    __tablename__ = 'article_analyses'

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('articles.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)

    # Semantic analysis (stored as JSON)
    key_concepts = Column(JSON, nullable=False)  # List of strings
    semantic_relations = Column(JSON, nullable=False)  # List of {subject, predicate, object}

    # Narrative and tone
    narrative_frames = Column(JSON, nullable=False)  # List of frame enums
    editorial_tone = Column(String(50), nullable=False)
    style_descriptors = Column(JSON, nullable=False)  # List of strings

    # Controversy and bias
    controversy_score = Column(Integer, nullable=False)  # 0-100
    political_bias = Column(Integer, nullable=False)  # -100 to 100

    # Quality indicators
    has_named_sources = Column(Integer, nullable=False, default=0)  # 0=no, 1=yes
    has_data_or_statistics = Column(Integer, nullable=False, default=0)
    has_multiple_perspectives = Column(Integer, nullable=False, default=0)
    quality_score = Column(Integer, nullable=False)  # 0-100

    # Content format and temporal relevance
    content_format = Column(String(50), nullable=False)  # news, feature, opinion, analysis, interview, listicle
    temporal_relevance = Column(String(50), nullable=False)  # breaking, timely, evergreen

    # Audience targeting
    audience_education = Column(String(50), nullable=False)
    target_age_range = Column(String(50), nullable=False)
    target_professions = Column(JSON, nullable=False)  # List of strings
    required_interests = Column(JSON, nullable=False)  # List of strings

    # Industry/sector
    relevant_industries = Column(JSON, nullable=False)  # List of strings

    # Geographic/cultural context
    geographic_scope = Column(String(50), nullable=False)
    cultural_context = Column(String(100), nullable=False)

    # Source diversity
    voices_represented = Column(JSON, nullable=False)  # List of {type, stance}
    source_diversity_score = Column(Integer, nullable=False)  # 0-100

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)

    # Relationships
    article = relationship('Article', backref='analysis')

    # Indexes for common queries
    __table_args__ = (
        Index('idx_article_analysis_controversy', 'controversy_score'),
        Index('idx_article_analysis_quality', 'quality_score'),
        Index('idx_article_analysis_bias', 'political_bias'),
        Index('idx_article_analysis_content_format', 'content_format'),
        Index('idx_article_analysis_temporal', 'temporal_relevance'),
        Index('idx_article_analysis_education', 'audience_education'),
    )

    def __repr__(self):
        return f"<ArticleAnalysis(article_id={self.article_id}, quality={self.quality_score}, controversy={self.controversy_score})>"


class EntityClassificationSuggestion(Base):
    """AI-assisted entity classification suggestions for audit and review."""
    __tablename__ = 'entity_classification_suggestions'

    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey('named_entities.id', ondelete='CASCADE'), nullable=False)

    # Suggestion details
    suggested_classification = Column(String(20), nullable=False)  # canonical, alias, ambiguous, not_an_entity
    suggested_canonical_ids = Column(JSON, nullable=True)  # Array of IDs for alias/ambiguous
    confidence = Column(Float, nullable=False)  # 0.0 to 1.0
    reasoning = Column(Text, nullable=False)  # LLM explanation

    # Alternative suggestion (if LLM was uncertain)
    alternative_classification = Column(String(20), nullable=True)
    alternative_confidence = Column(Float, nullable=True)

    # Application status
    applied = Column(Integer, nullable=False, default=0)  # 0=suggestion only, 1=applied to entity
    approved_by_user = Column(Integer, nullable=True)  # NULL=pending, 0=rejected, 1=approved

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    entity = relationship('NamedEntity', backref='classification_suggestions')

    __table_args__ = (
        Index('idx_entity_classification_entity', 'entity_id'),
        Index('idx_entity_classification_applied', 'applied'),
        Index('idx_entity_classification_confidence', 'confidence'),
        Index('idx_entity_classification_approved', 'approved_by_user'),
    )

    def __repr__(self):
        return f"<EntityClassificationSuggestion(id={self.id}, entity_id={self.entity_id}, classification={self.suggested_classification}, confidence={self.confidence:.2f}, applied={bool(self.applied)})>"


class EntityPairComparison(Base):
    """Track entity pairs that have been compared by AI to avoid retesting."""
    __tablename__ = 'entity_pair_comparisons'

    id = Column(Integer, primary_key=True)
    entity_a_id = Column(Integer, ForeignKey('named_entities.id', ondelete='CASCADE'), nullable=False)
    entity_b_id = Column(Integer, ForeignKey('named_entities.id', ondelete='CASCADE'), nullable=False)

    # Comparison results
    relationship = Column(String(20), nullable=False)  # SAME, DIFFERENT, AMBIGUOUS
    confidence = Column(Float, nullable=False)  # 0.0 to 1.0
    reasoning = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        # Ensure we don't compare the same pair twice (order-independent)
        Index('idx_entity_pair_unique', 'entity_a_id', 'entity_b_id', unique=True),
        Index('idx_entity_pair_relationship', 'relationship'),
    )

    def __repr__(self):
        return f"<EntityPairComparison(id={self.id}, entities=[{self.entity_a_id}, {self.entity_b_id}], relationship={self.relationship}, confidence={self.confidence:.2f})>"


class LLMApiCall(Base):
    """Log of LLM API calls for monitoring, debugging, and cost tracking."""
    __tablename__ = 'llm_api_calls'

    id = Column(Integer, primary_key=True)

    # Metadata of the call
    call_type = Column(String(50), nullable=False, index=True)  # 'structured_output', 'chat_completion', 'embedding', etc.
    task_name = Column(String(100), nullable=True, index=True)  # 'article_analysis', 'entity_pairwise_classification', etc.
    model = Column(String(50), nullable=False, index=True)  # 'gpt-5-nano', 'gpt-4o', etc.

    # Timing
    started_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)  # Calculated: completed_at - started_at in seconds

    # Tokens
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)

    # Prompts and response
    system_prompt = Column(Text, nullable=True)
    user_prompt = Column(Text, nullable=True)
    messages = Column(JSON, nullable=True)  # For chat completions (non-structured)
    response_raw = Column(JSON, nullable=False)  # Full OpenAI response object
    parsed_output = Column(JSON, nullable=True)  # For structured outputs (Pydantic model dump)

    # Status and errors
    success = Column(Integer, nullable=False, default=1, index=True)  # 1=success, 0=error
    error_message = Column(Text, nullable=True)

    # Context metadata (for filtering and analysis)
    context_data = Column(JSON, nullable=True)  # Additional metadata (article_id, entity_id, etc.)

    # Indexes for common queries
    __table_args__ = (
        Index('idx_llm_api_calls_started_at', 'started_at'),
        Index('idx_llm_api_calls_task_model', 'task_name', 'model'),
        Index('idx_llm_api_calls_success', 'success'),
    )

    def __repr__(self):
        status = 'success' if self.success else 'error'
        duration = f"{self.duration_seconds:.2f}s" if self.duration_seconds else 'N/A'
        return f"<LLMApiCall(id={self.id}, type={self.call_type}, task={self.task_name}, model={self.model}, status={status}, duration={duration})>"


class PageRankExecution(Base):
    """Log of PageRank algorithm executions for performance monitoring."""
    __tablename__ = 'pagerank_executions'

    id = Column(Integer, primary_key=True)

    # Execution metadata
    started_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Input parameters
    damping = Column(Float, nullable=False, default=0.85)
    max_iter = Column(Integer, nullable=False, default=1000)
    tolerance = Column(Float, nullable=False, default=1e-6)
    min_relevance_threshold = Column(Float, nullable=False, default=0.3)
    time_decay_days = Column(Integer, nullable=True)
    timeout_seconds = Column(Float, nullable=False, default=30.0)
    source_domain = Column(String(255), nullable=True, index=True)  # Optional domain filter

    # Graph statistics
    total_articles = Column(Integer, nullable=False)
    total_entities = Column(Integer, nullable=False)
    graph_edges = Column(Integer, nullable=True)  # Number of non-zero edges in graph
    graph_density = Column(Float, nullable=True)  # Percentage of possible edges that exist

    # Memory statistics
    matrix_memory_mb = Column(Float, nullable=True)  # Memory used by sparse matrix
    matrix_nnz = Column(Integer, nullable=True)  # Number of non-zero elements (nnz = non-zero)
    matrix_sparsity = Column(Float, nullable=True)  # Percentage of zeros in matrix

    # Convergence statistics
    iterations = Column(Integer, nullable=False)
    converged = Column(Integer, nullable=False, default=1)  # 1=converged, 0=timeout
    convergence_delta = Column(Float, nullable=True)  # Final delta before stopping

    # Results statistics
    entities_ranked = Column(Integer, nullable=False)
    min_score = Column(Float, nullable=True)
    max_score = Column(Float, nullable=True)
    mean_score = Column(Float, nullable=True)
    median_score = Column(Float, nullable=True)
    std_dev_score = Column(Float, nullable=True)

    # Top entities (for quick reference)
    top_entities = Column(JSON, nullable=True)  # List of top 10: [{"name": "...", "score": 0.95}, ...]

    # Success/error tracking
    success = Column(Integer, nullable=False, default=1, index=True)  # 1=success, 0=error
    error_message = Column(Text, nullable=True)

    # Indexes for common queries
    __table_args__ = (
        Index('idx_pagerank_executions_started_at', 'started_at'),
        Index('idx_pagerank_executions_domain', 'source_domain'),
        Index('idx_pagerank_executions_success', 'success'),
    )

    def __repr__(self):
        status = 'success' if self.success else 'error'
        duration = f"{self.duration_seconds:.2f}s" if self.duration_seconds else 'N/A'
        return f"<PageRankExecution(id={self.id}, entities={self.entities_ranked}, iterations={self.iterations}, duration={duration}, status={status})>"
