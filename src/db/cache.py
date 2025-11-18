"""
Cache database for storing downloaded HTML content.

This module provides a separate SQLite database for caching URL content,
allowing development iterations without re-downloading content.
"""

import hashlib
from datetime import datetime
from typing import Optional, Dict, List
from urllib.parse import urlparse

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Index
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from settings import get_setting


Base = declarative_base()


class URLCache(Base):
    """Cache entry for a downloaded URL."""

    __tablename__ = 'url_cache'

    id = Column(Integer, primary_key=True, autoincrement=True)
    url_hash = Column(String(64), unique=True, nullable=False, index=True)
    url = Column(Text, nullable=False)
    domain = Column(String(255), nullable=False, index=True)
    content = Column(Text, nullable=False)  # For redirects (30x), stores final URL; otherwise HTML
    status_code = Column(Integer, nullable=False)
    content_length = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    accessed_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Composite indexes for common queries
    __table_args__ = (
        Index('idx_cache_domain_created', 'domain', 'created_at'),
        Index('idx_cache_domain_accessed', 'domain', 'accessed_at'),
    )


class CacheDatabase:
    """Database interface for URL cache operations."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize cache database.

        Args:
            db_path: Path to SQLite database file. If None, uses default from settings.
        """
        if db_path is None:
            db_path = get_setting('CACHE_DB_PATH', 'data/cache.db')

        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def _get_session(self) -> Session:
        """Create a new database session."""
        return self.SessionLocal()

    @staticmethod
    def compute_url_hash(url: str) -> str:
        """Compute SHA-256 hash of URL."""
        return hashlib.sha256(url.encode('utf-8')).hexdigest()

    @staticmethod
    def extract_domain(url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc

    def get_cached_content(self, url: str) -> Optional[Dict]:
        """
        Retrieve cached content for a URL.

        Automatically follows redirects stored in cache (30x status codes).

        Args:
            url: The URL to look up

        Returns:
            Dictionary with cache data if found, None otherwise.
            Keys: url, url_hash, domain, content, status_code, created_at, accessed_at
        """
        session = self._get_session()
        try:
            url_hash = self.compute_url_hash(url)
            entry = session.query(URLCache).filter_by(url_hash=url_hash).first()

            if not entry:
                return None

            # Update accessed_at timestamp
            entry.accessed_at = datetime.utcnow()
            session.commit()

            # If this is a redirect (30x), follow it to get the actual content
            if 300 <= entry.status_code < 400:
                # Content field contains the final URL for redirects
                final_url = entry.content
                final_url_hash = self.compute_url_hash(final_url)
                final_entry = session.query(URLCache).filter_by(url_hash=final_url_hash).first()

                if final_entry:
                    # Update accessed_at for final entry too
                    final_entry.accessed_at = datetime.utcnow()
                    session.commit()

                    # Return the final content
                    return {
                        'url': final_entry.url,
                        'url_hash': final_entry.url_hash,
                        'domain': final_entry.domain,
                        'content': final_entry.content,
                        'status_code': final_entry.status_code,
                        'content_length': final_entry.content_length,
                        'created_at': final_entry.created_at,
                        'accessed_at': final_entry.accessed_at,
                        'was_redirected': True,
                        'original_url': url
                    }
                else:
                    # Redirect exists but final URL not cached - return redirect info
                    return {
                        'url': entry.url,
                        'url_hash': entry.url_hash,
                        'domain': entry.domain,
                        'content': entry.content,  # This is the redirect target URL
                        'status_code': entry.status_code,
                        'content_length': entry.content_length,
                        'created_at': entry.created_at,
                        'accessed_at': entry.accessed_at
                    }

            # Not a redirect, return normally
            return {
                'url': entry.url,
                'url_hash': entry.url_hash,
                'domain': entry.domain,
                'content': entry.content,
                'status_code': entry.status_code,
                'content_length': entry.content_length,
                'created_at': entry.created_at,
                'accessed_at': entry.accessed_at
            }
        finally:
            session.close()

    def save_to_cache(self, url: str, content: str, status_code: int = 200) -> bool:
        """
        Save content to cache.

        Args:
            url: The URL being cached
            content: HTML content to cache
            status_code: HTTP status code (default 200)

        Returns:
            True if saved successfully, False otherwise
        """
        session = self._get_session()
        try:
            url_hash = self.compute_url_hash(url)
            domain = self.extract_domain(url)
            content_length = len(content)

            # Check if already exists
            existing = session.query(URLCache).filter_by(url_hash=url_hash).first()

            if existing:
                # Update existing entry
                existing.content = content
                existing.status_code = status_code
                existing.content_length = content_length
                existing.accessed_at = datetime.utcnow()
            else:
                # Create new entry
                new_entry = URLCache(
                    url_hash=url_hash,
                    url=url,
                    domain=domain,
                    content=content,
                    status_code=status_code,
                    content_length=content_length
                )
                session.add(new_entry)

            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()

    def get_stats(self, domain: Optional[str] = None) -> Dict:
        """
        Get cache statistics.

        Args:
            domain: Optional domain to filter by

        Returns:
            Dictionary with stats: total_entries, total_size_bytes, domains,
            oldest_entry, newest_entry
        """
        session = self._get_session()
        try:
            query = session.query(URLCache)

            if domain:
                query = query.filter_by(domain=domain)

            entries = query.all()

            if not entries:
                return {
                    'total_entries': 0,
                    'total_size_bytes': 0,
                    'domains': [],
                    'oldest_entry': None,
                    'newest_entry': None
                }

            total_size = sum(e.content_length for e in entries)
            domains = list(set(e.domain for e in entries))
            oldest = min(entries, key=lambda e: e.created_at)
            newest = max(entries, key=lambda e: e.created_at)

            return {
                'total_entries': len(entries),
                'total_size_bytes': total_size,
                'domains': sorted(domains),
                'oldest_entry': oldest.created_at,
                'newest_entry': newest.created_at
            }
        finally:
            session.close()

    def list_entries(self, domain: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """
        List cached URLs.

        Args:
            domain: Optional domain to filter by
            limit: Maximum number of entries to return

        Returns:
            List of dictionaries with URL metadata
        """
        session = self._get_session()
        try:
            query = session.query(URLCache)

            if domain:
                query = query.filter_by(domain=domain)

            # Order by created_at descending (most recent first)
            query = query.order_by(URLCache.created_at.desc())

            if limit:
                query = query.limit(limit)

            entries = query.all()

            return [
                {
                    'url': e.url,
                    'url_hash': e.url_hash,
                    'domain': e.domain,
                    'content_length': e.content_length,
                    'status_code': e.status_code,
                    'created_at': e.created_at,
                    'accessed_at': e.accessed_at
                }
                for e in entries
            ]
        finally:
            session.close()

    def get_by_hash(self, url_hash: str) -> Optional[Dict]:
        """
        Retrieve cached content by URL hash (full or partial).

        Args:
            url_hash: The URL hash to look up (can be partial, minimum 8 chars)

        Returns:
            Dictionary with cache data if found, None otherwise
        """
        session = self._get_session()
        try:
            # Try exact match first
            entry = session.query(URLCache).filter_by(url_hash=url_hash).first()

            # If not found and hash is partial, try prefix match
            if not entry and len(url_hash) >= 8:
                entry = session.query(URLCache).filter(
                    URLCache.url_hash.like(f'{url_hash}%')
                ).first()

            if entry:
                # Update accessed_at timestamp
                entry.accessed_at = datetime.utcnow()
                session.commit()

                return {
                    'url': entry.url,
                    'url_hash': entry.url_hash,
                    'domain': entry.domain,
                    'content': entry.content,
                    'status_code': entry.status_code,
                    'content_length': entry.content_length,
                    'created_at': entry.created_at,
                    'accessed_at': entry.accessed_at
                }
            return None
        finally:
            session.close()

    def clear_cache(self, domain: Optional[str] = None) -> int:
        """
        Clear cache entries.

        Args:
            domain: If provided, only clear entries for this domain.
                   If None, clear all cache.

        Returns:
            Number of entries deleted
        """
        session = self._get_session()
        try:
            query = session.query(URLCache)

            if domain:
                query = query.filter_by(domain=domain)

            count = query.count()
            query.delete()
            session.commit()

            return count
        except Exception:
            session.rollback()
            return 0
        finally:
            session.close()

    def get_domains(self) -> List[Dict]:
        """
        Get list of cached domains with stats.

        Returns:
            List of dictionaries with domain stats: domain, count, total_size
        """
        session = self._get_session()
        try:
            from sqlalchemy import func

            results = session.query(
                URLCache.domain,
                func.count(URLCache.id).label('count'),
                func.sum(URLCache.content_length).label('total_size')
            ).group_by(URLCache.domain).all()

            return [
                {
                    'domain': r.domain,
                    'count': r.count,
                    'total_size': r.total_size or 0
                }
                for r in results
            ]
        finally:
            session.close()
