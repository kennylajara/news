"""
Pre-processing module for articles.
Includes Named Entity Recognition (NER) using spaCy.
"""

import spacy
from datetime import datetime
from sqlalchemy import insert
from db import ProcessingBatch, BatchItem, Article, NamedEntity, EntityType
from db.models import article_entities


# Load spaCy model (Spanish)
try:
    nlp = spacy.load("es_core_news_sm")
except OSError:
    print("spaCy Spanish model not found. Install with: python -m spacy download es_core_news_sm")
    nlp = None


# Map spaCy entity labels to our EntityType enum
SPACY_TO_ENTITY_TYPE = {
    'PER': EntityType.PERSON,
    'PERSON': EntityType.PERSON,
    'NORP': EntityType.NORP,
    'FAC': EntityType.FAC,
    'ORG': EntityType.ORG,
    'GPE': EntityType.GPE,
    'LOC': EntityType.LOC,
    'PRODUCT': EntityType.PRODUCT,
    'EVENT': EntityType.EVENT,
    'WORK_OF_ART': EntityType.WORK_OF_ART,
    'LAW': EntityType.LAW,
    'LANGUAGE': EntityType.LANGUAGE,
    'DATE': EntityType.DATE,
    'TIME': EntityType.TIME,
    'PERCENT': EntityType.PERCENT,
    'MONEY': EntityType.MONEY,
    'QUANTITY': EntityType.QUANTITY,
    'ORDINAL': EntityType.ORDINAL,
    'CARDINAL': EntityType.CARDINAL,
}


def extract_entities(text):
    """
    Extract named entities from text using spaCy.

    Args:
        text: Text to process

    Returns:
        List of tuples: [(entity_text, entity_type), ...]
    """
    if not nlp:
        return []

    doc = nlp(text)
    entities = []

    for ent in doc.ents:
        # Map spaCy label to our EntityType
        entity_type = SPACY_TO_ENTITY_TYPE.get(ent.label_, None)
        if entity_type:
            entities.append((ent.text, entity_type))

    return entities


def process_article(article, batch_item, session):
    """
    Process a single article: extract entities and associate them.

    Args:
        article: Article object
        batch_item: BatchItem object
        session: Database session

    Returns:
        dict: Statistics about processing
    """
    logs = []
    stats = {
        'entities_found': 0,
        'entities_new': 0,
        'entities_existing': 0,
        'processing_time': 0
    }

    start_time = datetime.utcnow()
    batch_item.status = 'processing'
    batch_item.started_at = start_time
    session.flush()

    try:
        logs.append(f"Processing article {article.id}: {article.title[:50]}...")

        # Extract entities from title and content
        text = f"{article.title} {article.content}"
        entities = extract_entities(text)

        stats['entities_found'] = len(entities)
        logs.append(f"Found {len(entities)} entities")

        # Get or create entities and associate with article
        entity_counts = {}
        for entity_text, entity_type in entities:
            # Skip if entity text is too short or just numbers
            if len(entity_text) < 2 or entity_text.isdigit():
                continue

            # Count entity mentions for this article
            entity_counts[entity_text] = entity_counts.get(entity_text, 0) + 1

        # Process unique entities
        for entity_text, mention_count in entity_counts.items():
            # Find entity type from original entities list
            entity_type = next((et for et, _ in [(e[1], e[0]) for e in entities if e[0] == entity_text]), None)
            if not entity_type:
                continue

            # Get or create entity
            entity = session.query(NamedEntity).filter_by(name=entity_text).first()
            if not entity:
                entity = NamedEntity(
                    name=entity_text,
                    entity_type=entity_type,
                    relevance=1,  # Initial global relevance
                    trend=0
                )
                session.add(entity)
                session.flush()
                stats['entities_new'] += 1
                logs.append(f"Created new entity: {entity_text} ({entity_type.value})")
            else:
                # Update global relevance (increment for each article that mentions it)
                entity.relevance += 1
                stats['entities_existing'] += 1

            # Calculate relevance score for this specific article-entity pair
            # Simple formula: base on number of mentions
            # TODO: Enhance with position in text, presence in title, etc.
            article_entity_relevance = float(mention_count)

            # Insert into article_entities association table
            stmt = insert(article_entities).values(
                article_id=article.id,
                entity_id=entity.id,
                mentions=mention_count,
                relevance=article_entity_relevance
            )
            session.execute(stmt)

        # Mark article as preprocessed
        article.preprocessed_at = datetime.utcnow()

        # Update batch item
        batch_item.status = 'completed'
        batch_item.completed_at = datetime.utcnow()
        batch_item.logs = "\\n".join(logs)

        # Calculate processing time
        stats['processing_time'] = (datetime.utcnow() - start_time).total_seconds()
        batch_item.stats = stats

        session.flush()
        logs.append(f"Successfully processed article {article.id}")

        return stats

    except Exception as e:
        # Mark as failed
        batch_item.status = 'failed'
        batch_item.error_message = str(e)
        batch_item.completed_at = datetime.utcnow()
        batch_item.logs = "\\n".join(logs + [f"ERROR: {str(e)}"])
        session.flush()

        raise


def process_batch(batch_id, session):
    """
    Process all items in a batch.

    Args:
        batch_id: ID of the batch to process
        session: Database session

    Returns:
        bool: True if all items processed successfully, False otherwise
    """
    batch = session.query(ProcessingBatch).filter_by(id=batch_id).first()
    if not batch:
        print(f"Batch {batch_id} not found")
        return False

    # Update batch status
    batch.status = 'processing'
    batch.started_at = datetime.utcnow()
    session.commit()

    # Get all pending items
    items = session.query(BatchItem).filter_by(batch_id=batch_id, status='pending').all()

    total_stats = {
        'entities_found': 0,
        'entities_new': 0,
        'entities_existing': 0,
        'total_processing_time': 0
    }

    for item in items:
        try:
            article = session.query(Article).filter_by(id=item.article_id).first()
            if not article:
                item.status = 'failed'
                item.error_message = f"Article {item.article_id} not found"
                batch.failed_items += 1
                continue

            # Process the article
            stats = process_article(article, item, session)

            # Aggregate stats
            for key in total_stats:
                if key in stats:
                    total_stats[key] += stats[key]

            batch.successful_items += 1
            batch.processed_items += 1

            print(f"  ✓ Processed article {article.id}: {stats['entities_found']} entities found")

        except Exception as e:
            batch.failed_items += 1
            batch.processed_items += 1
            print(f"  ✗ Failed to process article {item.article_id}: {e}")

        session.commit()

    # Update batch
    batch.status = 'completed' if batch.failed_items == 0 else 'failed'
    batch.completed_at = datetime.utcnow()
    batch.stats = total_stats
    session.commit()

    print(f"\nBatch {batch_id} completed:")
    print(f"  Total items: {batch.total_items}")
    print(f"  Successful: {batch.successful_items}")
    print(f"  Failed: {batch.failed_items}")
    print(f"  Total entities found: {total_stats['entities_found']}")
    print(f"  New entities: {total_stats['entities_new']}")
    print(f"  Existing entities: {total_stats['entities_existing']}")

    return batch.failed_items == 0
