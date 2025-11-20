"""
Export module for raw_news corpus database.

Creates a separate SQLite database in ai/corpus/raw_news.db with plain text articles
for machine learning and NLP applications.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from db.models import Article, Source
from extractors.markdown_to_txt import markdown_to_plain_text


def split_category(category_str: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Split category string into category and subcategory.

    Expects format: "Category > Subcategory" or "Category"

    Args:
        category_str: Category string from article (can be None)

    Returns:
        Tuple of (category, subcategory) - both can be None
    """
    if not category_str:
        return (None, None)

    # Split by " > " or " - " or " / "
    separators = [' > ', ' - ', ' / ', '>', '-', '/']

    for sep in separators:
        if sep in category_str:
            parts = category_str.split(sep, 1)
            category = parts[0].strip()
            subcategory = parts[1].strip() if len(parts) > 1 else None
            return (category, subcategory)

    # No separator found - it's just a category
    return (category_str.strip(), None)


def create_export_schema(db_path: str):
    """
    Create the raw_news.db schema.

    Args:
        db_path: Path to the SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create articles table with plain text content
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY,
            hash TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            source_domain TEXT NOT NULL,
            source_name TEXT NOT NULL,

            title TEXT NOT NULL,
            subtitle TEXT,
            author TEXT,
            published_date TEXT,
            location TEXT,
            content TEXT NOT NULL,
            category TEXT,
            subcategory TEXT,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            exported_at TEXT NOT NULL
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_hash ON articles(hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_domain)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_exported ON articles(exported_at)")

    conn.commit()
    conn.close()


def export_articles_to_corpus(
    session: Session,
    corpus_db_path: str,
    source_domain: Optional[str] = None,
    limit: Optional[int] = None,
    skip_enriched: bool = False
) -> dict:
    """
    Export articles from main database to corpus database.

    Args:
        session: SQLAlchemy session to main database
        corpus_db_path: Path to corpus database file
        source_domain: Optional domain filter (e.g., 'diariolibre.com')
        limit: Optional limit on number of articles to export
        skip_enriched: If True, only export articles without enrichment

    Returns:
        Dictionary with export statistics
    """
    # Create corpus database if it doesn't exist
    os.makedirs(os.path.dirname(corpus_db_path), exist_ok=True)
    create_export_schema(corpus_db_path)

    # Build query
    query = session.query(Article).join(Source)

    if source_domain:
        query = query.filter(Source.domain == source_domain)

    if skip_enriched:
        query = query.filter(Article.enriched_at.is_(None))

    # Order by published_date descending (most recent first)
    query = query.order_by(Article.published_date.desc())

    if limit:
        query = query.limit(limit)

    articles = query.all()

    # Connect to corpus database
    conn = sqlite3.connect(corpus_db_path)
    cursor = conn.cursor()

    stats = {
        'total': len(articles),
        'inserted': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0
    }

    for article in articles:
        try:
            # Convert markdown content to plain text
            plain_text_content = markdown_to_plain_text(article.content)

            # Split category into category and subcategory
            category, subcategory = split_category(article.category)

            # Convert datetime to ISO format strings
            published_date_str = article.published_date.isoformat() if article.published_date else None
            created_at_str = article.created_at.isoformat()
            updated_at_str = article.updated_at.isoformat()
            exported_at_str = datetime.utcnow().isoformat()

            # Check if article already exists
            cursor.execute("SELECT id FROM articles WHERE hash = ?", (article.hash,))
            existing = cursor.fetchone()

            if existing:
                # Update existing article
                cursor.execute("""
                    UPDATE articles SET
                        url = ?,
                        source_domain = ?,
                        source_name = ?,
                        title = ?,
                        subtitle = ?,
                        author = ?,
                        published_date = ?,
                        location = ?,
                        content = ?,
                        category = ?,
                        subcategory = ?,
                        updated_at = ?,
                        exported_at = ?
                    WHERE hash = ?
                """, (
                    article.url,
                    article.source.domain,
                    article.source.name,
                    article.title,
                    article.subtitle,
                    article.author,
                    published_date_str,
                    article.location,
                    plain_text_content,
                    category,
                    subcategory,
                    updated_at_str,
                    exported_at_str,
                    article.hash
                ))
                stats['updated'] += 1
            else:
                # Insert new article
                cursor.execute("""
                    INSERT INTO articles (
                        hash, url, source_domain, source_name,
                        title, subtitle, author, published_date, location,
                        content, category, subcategory,
                        created_at, updated_at, exported_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    article.hash,
                    article.url,
                    article.source.domain,
                    article.source.name,
                    article.title,
                    article.subtitle,
                    article.author,
                    published_date_str,
                    article.location,
                    plain_text_content,
                    category,
                    subcategory,
                    created_at_str,
                    updated_at_str,
                    exported_at_str
                ))
                stats['inserted'] += 1

        except Exception as e:
            stats['errors'] += 1
            print(f"Error exporting article {article.hash}: {str(e)}")
            continue

    conn.commit()
    conn.close()

    return stats
