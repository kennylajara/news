"""
Article enrichment module.
Includes Named Entity Recognition (NER) using spaCy and semantic sentence clustering.
"""

import spacy
from datetime import datetime
from sqlalchemy import insert, update
from db import ProcessingBatch, BatchItem, Article, NamedEntity, EntityType, ArticleCluster, ArticleSentence, ClusterCategory, FlashNews
from db.models import article_entities
from processors.clustering import extract_sentences, make_embeddings, cluster_article


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


def calculate_entity_relevance(article, entity_text, mentions, total_mentions):
    """
    Calculate relevance score for an entity within a specific article.

    Base score is the proportion of this entity's mentions relative to all entity mentions.
    Bonuses are applied as percentages of the base score.
    Final score is in base 1.

    Args:
        article: Article object
        entity_text: The text of the entity
        mentions: Number of times this entity appears in the article
        total_mentions: Total mentions of all entities in the article

    Returns:
        float: Calculated relevance score (0.0 to ~2.0+ depending on bonuses)
    """
    if total_mentions == 0:
        return 0.0

    # Base score: proportion of this entity's mentions vs all entity mentions
    base_score = mentions / total_mentions

    # Start with base score
    score = base_score

    # Apply bonuses as percentages of base score
    # Remove multiple spaces and line breaks for cleaner matching
    content_lower = " ".join(article.content.split()).lower()
    entity_lower = entity_text.lower()

    # Bonus: +50% if entity appears in title
    if article.title and entity_lower in article.title.lower():
        score += base_score * 0.5

    # Bonus: +25% if entity appears in subtitle
    if article.subtitle and entity_lower in article.subtitle.lower():
        score += base_score * 0.25

    # Bonus based on position of first occurrence
    if content_lower:
        first_occurrence = content_lower.find(entity_lower)
        if first_occurrence != -1:
            relative_position = first_occurrence / len(content_lower)
            if relative_position < 0.2:  # First 20%
                score += base_score * 0.3  # +30%
            elif relative_position < 0.4:  # First 40%
                score += base_score * 0.15  # +15%

    # Bonus: +10% per mention beyond 3 (cap at +50%)
    if mentions > 3:
        bonus_mentions = min(mentions - 3, 5)  # Cap at 5 extra mentions
        score += base_score * (bonus_mentions * 0.1)

    return round(score, 6)  # Keep precision for very small values


def calculate_cluster_boost(entity_text, clusters_info, sentences):
    """
    Calculate relevance boost based on entity presence in semantic clusters.

    Args:
        entity_text: The entity text to search for
        clusters_info: List of cluster dicts from clustering
        sentences: List of sentence strings

    Returns:
        float: Boost multiplier (1.3 for core, 1.0 for secondary, 0.7 otherwise)
    """
    entity_lower = entity_text.lower()

    # Check each cluster category
    in_core = False
    in_secondary = False

    for cluster in clusters_info:
        category = cluster.get('category', 'filler')
        indices = cluster.get('indices', [])

        # Check if entity appears in any sentence of this cluster
        for idx in indices:
            if idx < len(sentences):
                sentence_lower = sentences[idx].lower()
                if entity_lower in sentence_lower:
                    if category == 'core':
                        in_core = True
                        break  # Core takes precedence
                    elif category == 'secondary':
                        in_secondary = True

        if in_core:
            break  # No need to check further

    # Apply boost
    if in_core:
        return 1.3
    elif in_secondary:
        return 1.0
    else:
        return 0.7


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
    Process a single article: clustering → NER with cluster-based relevance boost.

    Args:
        article: Article object
        batch_item: BatchItem object
        session: Database session

    Returns:
        dict: Statistics about processing
    """
    logs = []
    stats = {
        'sentences_extracted': 0,
        'clusters_found': 0,
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

        # ========== PHASE 1: SEMANTIC CLUSTERING ==========
        logs.append("Phase 1: Extracting and clustering sentences...")

        # Extract sentences from content (title separate)
        sentences = extract_sentences(article.content)
        stats['sentences_extracted'] = len(sentences)
        logs.append(f"Extracted {len(sentences)} sentences")

        clusters_info = []
        labels = []

        if len(sentences) > 0:
            # Generate title embedding separately
            title_embedding = make_embeddings([article.title])

            # Cluster sentences
            clusters_info, labels, probs = cluster_article(sentences, title_embedding)
            stats['clusters_found'] = len(clusters_info)
            logs.append(f"Found {len(clusters_info)} clusters")

            # Save clusters to database
            for cluster_data in clusters_info:
                cluster = ArticleCluster(
                    article_id=article.id,
                    cluster_label=int(cluster_data['label']),  # Convert numpy int to Python int
                    category=ClusterCategory[cluster_data['category'].upper()],
                    score=float(cluster_data['score']),  # Ensure float type
                    size=int(cluster_data['size']),  # Ensure int type
                    centroid_embedding=cluster_data['centroid'],
                    sentence_indices=cluster_data['indices']
                )
                session.add(cluster)
                session.flush()

                logs.append(f"  Cluster {cluster_data['label']}: {cluster_data['category']} "
                           f"(score={cluster_data['score']:.2f}, size={cluster_data['size']})")

                # Save sentences with cluster assignment
                for idx in cluster_data['indices']:
                    if idx < len(sentences):
                        sentence = ArticleSentence(
                            article_id=article.id,
                            sentence_index=idx,
                            sentence_text=sentences[idx],
                            cluster_id=cluster.id
                        )
                        session.add(sentence)

            # Mark as cluster-enriched
            article.cluster_enriched_at = datetime.utcnow()
            logs.append("Clustering complete")

            # ========== PHASE 1.1: CLUSTER SUMMARIZATION ==========
            logs.append("Phase 1.1: Generating flash news from core clusters...")

            core_clusters = [c for c in clusters_info if c['category'] == 'core']
            stats['flash_news_generated'] = 0

            if core_clusters:
                logs.append(f"Found {len(core_clusters)} core clusters to summarize")

                try:
                    from llm.openai_client import openai_structured_output

                    for cluster_data in core_clusters:
                        try:
                            # Find the cluster object we just created
                            cluster = session.query(ArticleCluster).filter_by(
                                article_id=article.id,
                                cluster_label=int(cluster_data['label'])
                            ).first()

                            if not cluster:
                                logs.append(f"  Warning: Could not find cluster {cluster_data['label']} in DB")
                                continue

                            # Check if flash news already exists for this cluster
                            existing_flash = session.query(FlashNews).filter_by(cluster_id=cluster.id).first()
                            if existing_flash:
                                logs.append(f"  Skipping cluster {cluster_data['label']}: flash news already exists")
                                continue

                            # Get sentences for this cluster
                            cluster_sentences = [sentences[idx] for idx in cluster_data['indices'] if idx < len(sentences)]

                            # Prepare data for LLM
                            llm_data = {
                                'title': article.title,
                                'cluster_sentences': cluster_sentences,
                                'cluster_score': cluster_data['score']
                            }

                            # Call OpenAI for structured summarization
                            result = openai_structured_output('core_cluster_summarization', llm_data)
                            summary_text = result.summary

                            # Generate embedding for the summary
                            summary_embedding = make_embeddings([summary_text])
                            summary_embedding_list = summary_embedding[0].tolist()

                            # Create FlashNews record
                            flash_news = FlashNews(
                                cluster_id=cluster.id,
                                summary=summary_text,
                                embedding=summary_embedding_list,
                                published=0
                            )
                            session.add(flash_news)
                            session.flush()

                            stats['flash_news_generated'] += 1
                            logs.append(f"  ✓ Cluster {cluster_data['label']}: Generated flash news (ID: {flash_news.id})")
                            logs.append(f"    Summary: {summary_text[:100]}...")

                        except Exception as cluster_error:
                            # Log error but continue processing other clusters
                            logs.append(f"  ✗ Failed to generate flash news for cluster {cluster_data['label']}: {str(cluster_error)}")
                            continue

                    logs.append(f"Generated {stats['flash_news_generated']} flash news from {len(core_clusters)} core clusters")

                except ImportError as e:
                    logs.append(f"Warning: Could not import OpenAI client, skipping summarization: {e}")
                except Exception as e:
                    logs.append(f"Warning: Error during cluster summarization: {e}")

            else:
                logs.append("No core clusters found, skipping flash news generation")

        else:
            logs.append("No sentences found, skipping clustering")

        # ========== PHASE 2: NER ==========
        logs.append("Phase 2: Extracting named entities...")

        # Extract entities from title, subtitle, and content
        # Note: subtitle is included for NER but NOT for clustering
        text_parts = [article.title]
        if article.subtitle:
            text_parts.append(article.subtitle)
        text_parts.append(article.content)
        text = " ".join(text_parts)
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

        # Calculate total mentions for relevance calculation
        total_mentions = sum(entity_counts.values())

        # First pass: Calculate raw relevances and create/update entities
        entity_relevances = []  # List of (entity_text, entity_id, mention_count, raw_relevance, cluster_boost)

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
                    article_count=1,  # First article mentioning this entity
                    trend=0
                )
                session.add(entity)
                session.flush()
                stats['entities_new'] += 1
                logs.append(f"Created new entity: {entity_text} ({entity_type.value})")
            else:
                # Update article count (increment for each article that mentions it)
                entity.article_count += 1
                stats['entities_existing'] += 1

            # Calculate raw relevance for this entity in this article
            raw_relevance = calculate_entity_relevance(article, entity_text, mention_count, total_mentions)

            # ========== PHASE 2.1: APPLY CLUSTER BOOST ==========
            cluster_boost = 1.0
            if clusters_info:
                cluster_boost = calculate_cluster_boost(entity_text, clusters_info, sentences)

            entity_relevances.append((entity_text, entity.id, mention_count, raw_relevance, cluster_boost))

        # ========== PHASE 3: NORMALIZATION ==========
        # Normalize relevances so the most relevant entity has a score of 1.0
        # (after applying cluster boost)
        if entity_relevances:
            # Apply cluster boost before normalization
            boosted_relevances = [(et, eid, mc, rv * cb, cb) for et, eid, mc, rv, cb in entity_relevances]
            max_relevance = max(rv for _, _, _, rv, _ in boosted_relevances)

            if max_relevance > 0:
                normalization_factor = 1.0 / max_relevance
            else:
                normalization_factor = 1.0  # All relevances are 0, no normalization needed

            # Second pass: Insert with normalized relevances
            for entity_text, entity_id, mention_count, boosted_relevance, cluster_boost in boosted_relevances:
                normalized_relevance = boosted_relevance * normalization_factor

                # Insert into article_entities association table
                stmt = insert(article_entities).values(
                    article_id=article.id,
                    entity_id=entity_id,
                    mentions=mention_count,
                    relevance=normalized_relevance
                )
                session.execute(stmt)

                logs.append(f"  {entity_text}: {mention_count} mentions, "
                           f"boost={cluster_boost:.1f}x, relevance={normalized_relevance:.4f}")

        # ========== PHASE 4: UPDATE DB RECORDS ==========
        # Mark article as enriched
        article.enriched_at = datetime.utcnow()

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
