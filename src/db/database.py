"""
Database connection and operations.
"""

from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base, Source, Article, Tag, DomainProcess, ProcessType


class Database:
    """Database manager for news portal."""

    def __init__(self, db_path: str = "data/news.db"):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        # Ensure data directory exists
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        # Create engine and session
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def get_or_create_source(self, session: Session, domain: str, name: str = None) -> Source:
        """
        Get existing source or create new one.
        Automatically initializes domain_processes with epoch date (1970-01-01).

        Args:
            session: Database session
            domain: Source domain (e.g., 'diariolibre.com')
            name: Source display name (optional, defaults to domain)

        Returns:
            Source object
        """
        source = session.query(Source).filter_by(domain=domain).first()
        if not source:
            source = Source(domain=domain, name=name or domain)
            session.add(source)
            session.flush()  # Get the ID without committing

            # Initialize process tracking with epoch date (equivalent to "never processed")
            for process_type in ProcessType:
                process = DomainProcess(
                    source_id=source.id,
                    process_type=process_type,
                    last_processed_at=datetime(1970, 1, 1)  # Unix epoch
                )
                session.add(process)
            session.flush()
        return source

    def get_or_create_tag(self, session: Session, tag_name: str) -> Tag:
        """
        Get existing tag or create new one.

        Args:
            session: Database session
            tag_name: Tag name

        Returns:
            Tag object
        """
        tag = session.query(Tag).filter_by(name=tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            session.add(tag)
            session.flush()
        return tag

    def article_exists(self, session: Session, url: str = None, hash: str = None) -> bool:
        """
        Check if article already exists.

        Args:
            session: Database session
            url: Article URL
            hash: Article hash

        Returns:
            True if article exists, False otherwise
        """
        query = session.query(Article)
        if url:
            if query.filter_by(url=url).first():
                return True
        if hash:
            if query.filter_by(hash=hash).first():
                return True
        return False

    def save_article(self, session: Session, article_data: dict, source_domain: str) -> Article:
        """
        Save article to database.

        Args:
            session: Database session
            article_data: Dictionary with article data
            source_domain: Domain of the source

        Returns:
            Article object
        """
        # Get or create source
        source = self.get_or_create_source(session, source_domain)

        # Parse published date if present
        published_date = None
        if article_data.get('date'):
            try:
                # RFC 3339 format: "2025-11-15T00:01:00-04:00"
                date_str = article_data['date']
                # Remove timezone suffix for datetime parsing
                if '+' in date_str or date_str.count('-') > 2:
                    date_str = date_str[:19]  # Keep only YYYY-MM-DDTHH:MM:SS
                published_date = datetime.fromisoformat(date_str)
            except (ValueError, TypeError):
                pass

        # Create article
        article = Article(
            hash=article_data['_metadata']['hash'],
            url=article_data['_metadata']['url'],
            source_id=source.id,
            title=article_data.get('title', ''),
            subtitle=article_data.get('subtitle'),
            author=article_data.get('author'),
            published_date=published_date,
            location=article_data.get('location'),
            content=article_data.get('content', ''),
            category=article_data.get('category'),
            html_path=None,  # Will be set by caller if needed
            cleaned_html_hash=article_data['_metadata'].get('cleaned_html_hash')
        )

        session.add(article)

        # Add tags with autoflush disabled to ensure atomic transaction
        # This prevents SQLAlchemy from flushing the article before all tags are added
        # If any tag operation fails, the entire transaction (article + tags) will rollback
        with session.no_autoflush:
            for tag_name in article_data.get('tags', []):
                if tag_name:  # Skip empty tags
                    tag = self.get_or_create_tag(session, tag_name)
                    article.tags.append(tag)

        return article

    def save_or_update_article(self, session: Session, article_data: dict, source_domain: str, force_reprocess: bool = False) -> tuple[Article, bool]:
        """
        Save article to database or update if it already exists.

        Args:
            session: Database session
            article_data: Dictionary with article data
            source_domain: Domain of the source
            force_reprocess: If True, always reset enrichment status even if content hasn't changed

        Returns:
            Tuple of (Article object, was_updated: bool)
            was_updated is True if article was updated, False if it was created
        """
        article_hash = article_data['_metadata']['hash']
        article_url = article_data['_metadata']['url']
        new_cleaned_html_hash = article_data['_metadata'].get('cleaned_html_hash')

        # Check if article exists by hash or URL
        existing = session.query(Article).filter(
            (Article.hash == article_hash) | (Article.url == article_url)
        ).first()

        if existing:
            # Update existing article
            source = self.get_or_create_source(session, source_domain)

            # Parse published date if present
            published_date = None
            if article_data.get('date'):
                try:
                    date_str = article_data['date']
                    if '+' in date_str or date_str.count('-') > 2:
                        date_str = date_str[:19]
                    published_date = datetime.fromisoformat(date_str)
                except (ValueError, TypeError):
                    pass

            # Check if content actually changed by comparing cleaned HTML hashes
            content_changed = (
                force_reprocess or
                new_cleaned_html_hash is None or
                existing.cleaned_html_hash is None or
                new_cleaned_html_hash != existing.cleaned_html_hash
            )

            # Update fields
            existing.hash = article_hash
            existing.url = article_url
            existing.source_id = source.id
            existing.title = article_data.get('title', '')
            existing.subtitle = article_data.get('subtitle')
            existing.author = article_data.get('author')
            existing.published_date = published_date
            existing.location = article_data.get('location')
            existing.content = article_data.get('content', '')
            existing.category = article_data.get('category')
            existing.cleaned_html_hash = new_cleaned_html_hash
            existing.updated_at = datetime.utcnow()

            # Only reset enrichment status if content actually changed
            if content_changed:
                existing.enriched_at = None
                existing.cluster_enriched_at = None

            # Update tags: clear existing and add new ones
            existing.tags.clear()
            with session.no_autoflush:
                for tag_name in article_data.get('tags', []):
                    if tag_name:
                        tag = self.get_or_create_tag(session, tag_name)
                        existing.tags.append(tag)

            return existing, True
        else:
            # Create new article using existing save_article method
            article = self.save_article(session, article_data, source_domain)
            return article, False

    def get_article_by_hash(self, session: Session, hash: str) -> Article:
        """Get article by hash."""
        return session.query(Article).filter_by(hash=hash).first()

    def get_article_by_url(self, session: Session, url: str) -> Article:
        """Get article by URL."""
        return session.query(Article).filter_by(url=url).first()

    def get_articles_by_source(self, session: Session, domain: str, limit: int = 100) -> list:
        """Get articles from a specific source."""
        source = session.query(Source).filter_by(domain=domain).first()
        if not source:
            return []
        return (session.query(Article)
                .filter_by(source_id=source.id)
                .order_by(Article.published_date.desc())
                .limit(limit)
                .all())

    def get_articles_by_tag(self, session: Session, tag_name: str, limit: int = 100) -> list:
        """Get articles with a specific tag."""
        tag = session.query(Tag).filter_by(name=tag_name).first()
        if not tag:
            return []
        return (session.query(Article)
                .join(Article.tags)
                .filter(Tag.id == tag.id)
                .order_by(Article.published_date.desc())
                .limit(limit)
                .all())

    def get_recent_articles(self, session: Session, limit: int = 100) -> list:
        """Get most recent articles."""
        return (session.query(Article)
                .order_by(Article.published_date.desc())
                .limit(limit)
                .all())
