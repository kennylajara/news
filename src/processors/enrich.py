"""
Article enrichment module.
Includes Named Entity Recognition (NER) using spaCy and semantic sentence clustering.
"""

import spacy
from datetime import datetime
from sqlalchemy import insert, update, delete
from db import ProcessingBatch, BatchItem, Article, NamedEntity, EntityType, ArticleCluster, ArticleSentence, ClusterCategory, FlashNews, EntityClassification, EntityOrigin
from db.models import article_entities
from processors.clustering import extract_sentences, make_embeddings, cluster_article
from processors.tokenization import populate_entity_tokens
from collections import defaultdict


# Configuration constants for ambiguous entity resolution
MAX_AMBIGUITY_THRESHOLD = 10  # Entities with more than this many canonical refs are ignored if they couldn't be disambiguated
MAX_CONTEXTUAL_RESOLUTION_REFS = 10  # Maximum canonical refs to attempt contextual resolution (should be <= MAX_AMBIGUITY_THRESHOLD)


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


def resolve_ambiguous_entity_contextually(canonical_entities, article_content, detected_entities_names, session, max_ambiguity=MAX_CONTEXTUAL_RESOLUTION_REFS):
    """
    Resolve AMBIGUOUS entity by finding contextual clues in the article.

    Args:
        canonical_entities: List of NamedEntity objects this ambiguous entity points to
        article_content: Article text content for substring search
        detected_entities_names: Set of entity names detected by NER (for fast lookup)
        session: SQLAlchemy session
        max_ambiguity: Don't resolve if entity has more than this many canonical refs

    Returns:
        List of NamedEntity objects that are contextually relevant (subset of canonical_entities)
        or None if no resolution was possible
    """
    # Don't resolve if too ambiguous (performance optimization)
    if len(canonical_entities) > max_ambiguity:
        return None

    contextually_relevant = []
    article_lower = article_content.lower()

    for canonical_entity in canonical_entities:
        # Case (a): Check if canonical entity name is mentioned directly in article
        if canonical_entity.name.lower() in article_lower:
            contextually_relevant.append(canonical_entity)
            continue

        # Case (b): Check if canonical entity is referenced by other entities in the article
        # Find entities that point to this canonical (ALIAS or AMBIGUOUS)
        referencing_entities = session.query(NamedEntity).join(
            entity_canonical_refs,
            NamedEntity.id == entity_canonical_refs.c.entity_id
        ).filter(
            entity_canonical_refs.c.canonical_id == canonical_entity.id
        ).all()

        for ref_entity in referencing_entities:
            # First check detected entities (fast)
            if ref_entity.name in detected_entities_names:
                contextually_relevant.append(canonical_entity)
                break

            # Then check substring in article (slower)
            if ref_entity.name.lower() in article_lower:
                contextually_relevant.append(canonical_entity)
                break

    # Only return if we found at least one contextual match
    # Otherwise return None to indicate "no resolution found, use default behavior"
    return contextually_relevant if contextually_relevant else None


def calculate_local_relevance_with_classification(
    article,
    entity_counts,
    entity_contexts,
    entities_original,
    clusters_info,
    sentences,
    session
):
    """
    Calculate local relevance considering entity classifications.

    Handles CANONICAL, ALIAS, AMBIGUOUS, and NOT_AN_ENTITY classifications.

    Args:
        article: Article object
        entity_counts: Dict mapping entity_text -> mention_count
        entity_contexts: Dict mapping entity_text -> [sentences]
        entities_original: List of (entity_text, entity_type) tuples from NER
        clusters_info: Cluster data for boost calculation
        sentences: List of sentence strings
        session: SQLAlchemy session

    Returns:
        List of dicts with keys: entity_id, entity_name, mentions, relevance, origin, is_new, context_sentences
    """
    # Total mentions for normalization
    total_mentions = sum(entity_counts.values())

    # Structure to hold entity data: entity_text -> {entity_obj, mention_count, raw_relevance, cluster_boost, should_ignore, origin, is_new}
    entity_data = {}

    # Additional entities to add (from classifications)
    additional_entities = []  # List of (canonical_entity_obj, mention_count, raw_relevance, cluster_boost, origin)

    # ========== STEP 1: Process original entities from NER ==========
    for entity_text, mention_count in entity_counts.items():
        # Find entity type from original NER extraction
        entity_type = next((et for et, _ in [(e[1], e[0]) for e in entities_original if e[0] == entity_text]), None)
        if not entity_type:
            continue

        # Get or create entity
        entity = session.query(NamedEntity).filter_by(name=entity_text).first()
        is_new = False  # Track if this is a new entity

        if not entity:
            # Create new entity
            entity = NamedEntity(
                name=entity_text,
                name_length=len(entity_text),
                entity_type=entity_type,
                detected_types=[entity_type.value],
                article_count=1,
                trend=0
            )
            session.add(entity)
            session.flush()

            # Populate entity_tokens reverse index
            populate_entity_tokens(entity.id, entity.name, session)

            is_new = True  # Mark as new
        else:
            # Update existing entity
            entity.article_count += 1

            # Update detected_types if needed
            if entity.detected_types is None:
                entity.detected_types = [entity_type.value]
                entity.needs_review = 1
            elif entity_type.value not in entity.detected_types:
                entity.detected_types = entity.detected_types + [entity_type.value]
                entity.needs_review = 1

        # Calculate raw relevance
        raw_relevance = calculate_entity_relevance(article, entity_text, mention_count, total_mentions)

        # Calculate cluster boost
        cluster_boost = 1.0
        if clusters_info:
            cluster_boost = calculate_cluster_boost(entity_text, clusters_info, sentences)

        # Determine how to handle based on classification
        should_ignore = False
        origin = EntityOrigin.NER

        if entity.classified_as == EntityClassification.CANONICAL:
            # Normal entity, include in calculation
            pass

        elif entity.classified_as == EntityClassification.ALIAS:
            # Mark for ignore, add canonical instead
            should_ignore = True
            canonical_entities = entity.canonical_refs if entity.canonical_refs else []

            if len(canonical_entities) == 1:
                canonical_entity = canonical_entities[0]
                # Only add canonical if not already detected by NER in this article
                if canonical_entity.name not in entity_data:
                    additional_entities.append((
                        canonical_entity,
                        mention_count,
                        raw_relevance,
                        cluster_boost,
                        EntityOrigin.CLASSIFICATION
                    ))
                # If canonical already exists, the alias relevance will transfer to it automatically
            else:
                # WARNING: Inconsistent DB state - ALIAS must have exactly 1 canonical
                print(f"⚠️  WARNING: ALIAS entity '{entity.name}' (ID: {entity.id}) has {len(canonical_entities)} canonical_refs (expected 1). Entity will be ignored.")
                # Entity remains as should_ignore=True, relevance=0

        elif entity.classified_as == EntityClassification.AMBIGUOUS:
            # Mark for ignore
            should_ignore = True

            # Get canonical entities this ambiguous entity points to
            canonical_entities = entity.canonical_refs if entity.canonical_refs else []

            if len(canonical_entities) < 2:
                # WARNING: Inconsistent DB state - AMBIGUOUS requires minimum 2 canonical entities
                print(f"⚠️  WARNING: AMBIGUOUS entity '{entity.name}' (ID: {entity.id}) has {len(canonical_entities)} canonical_refs (minimum 2 required). Entity will be ignored.")
                # Entity remains as should_ignore=True, relevance=0
            else:
                # Check if any canonical was already detected by NER in this article
                detected_canonicals = [ce for ce in canonical_entities if ce.name in entity_data]

                if detected_canonicals:
                    # At least one canonical was detected by NER - only use those
                    # This prevents diluting relevance among unmentioned entities
                    # The ambiguous entity's relevance will be divided only among detected canonicals
                    pass  # detected_canonicals will be used in STEP 6 for division
                else:
                    # No canonical was detected by NER - try contextual resolution
                    detected_entities_names = set(entity_data.keys())
                    contextually_resolved = resolve_ambiguous_entity_contextually(
                        canonical_entities=canonical_entities,
                        article_content=article.content,
                        detected_entities_names=detected_entities_names,
                        session=session,
                        max_ambiguity=MAX_CONTEXTUAL_RESOLUTION_REFS
                    )

                    if contextually_resolved:
                        # Contextual resolution found specific canonicals - use only those
                        for canonical_entity in contextually_resolved:
                            if canonical_entity.name not in entity_data:
                                additional_entities.append((
                                    canonical_entity,
                                    mention_count,
                                    raw_relevance,
                                    cluster_boost,
                                    EntityOrigin.CLASSIFICATION
                                ))
                    else:
                        # No contextual resolution possible - check if too ambiguous
                        if len(canonical_entities) > MAX_AMBIGUITY_THRESHOLD:
                            # Too ambiguous and couldn't resolve - ignore to avoid diluting relevance
                            print(f"⚠️  WARNING: AMBIGUOUS entity '{entity.name}' (ID: {entity.id}) has {len(canonical_entities)} canonical_refs (threshold: {MAX_AMBIGUITY_THRESHOLD}) and couldn't be contextually resolved. Entity will be ignored.")
                            # Entity remains as should_ignore=True, relevance=0
                        else:
                            # Manageable ambiguity - add all canonicals as candidates
                            for canonical_entity in canonical_entities:
                                if canonical_entity.name not in entity_data:
                                    additional_entities.append((
                                        canonical_entity,
                                        mention_count,
                                        raw_relevance,
                                        cluster_boost,
                                        EntityOrigin.CLASSIFICATION
                                    ))

        elif entity.classified_as == EntityClassification.NOT_AN_ENTITY:
            # False positive, ignore completely
            should_ignore = True

        # Store entity data
        entity_data[entity_text] = {
            'entity': entity,
            'mention_count': mention_count,
            'raw_relevance': raw_relevance,
            'cluster_boost': cluster_boost,
            'should_ignore': should_ignore,
            'origin': origin,
            'is_new': is_new
        }

    # ========== STEP 2: Add additional canonical entities ==========
    for canonical_entity, mention_count, raw_relevance, cluster_boost, origin in additional_entities:
        if canonical_entity.name not in entity_data:
            # For AMBIGUOUS->canonical: mark as should_ignore since relevance will be divided later
            should_ignore_canonical = (origin == EntityOrigin.CLASSIFICATION)  # Classification canonicals are marked to ignore

            entity_data[canonical_entity.name] = {
                'entity': canonical_entity,
                'mention_count': mention_count,
                'raw_relevance': raw_relevance,
                'cluster_boost': cluster_boost,
                'should_ignore': should_ignore_canonical,
                'origin': origin,
                'is_new': False  # Classification entities are never "new" from NER perspective
            }

    # ========== STEP 3: Calculate boosted relevances (only for non-ignored) ==========
    entities_for_normalization = []

    for entity_text, data in entity_data.items():
        if not data['should_ignore']:
            boosted_relevance = data['raw_relevance'] * data['cluster_boost']
            entities_for_normalization.append((entity_text, boosted_relevance))

    # ========== STEP 4: Normalization ==========
    normalization_factor = 1.0
    if entities_for_normalization:
        max_relevance = max(rel for _, rel in entities_for_normalization)
        if max_relevance > 0:
            normalization_factor = 1.0 / max_relevance

    # ========== STEP 5: Apply normalization and handle AMBIGUOUS divisions ==========
    final_relevances = []  # List of dicts ready for insertion

    for entity_text, data in entity_data.items():
        entity = data['entity']
        boosted_relevance = data['raw_relevance'] * data['cluster_boost']

        # If ignored, set relevance to 0
        if data['should_ignore']:
            final_relevance = 0.0
        else:
            final_relevance = boosted_relevance * normalization_factor

        # Get context sentences
        contexts = entity_contexts.get(entity_text, [])

        final_relevances.append({
            'entity_id': entity.id,
            'entity_name': entity.name,
            'mentions': data['mention_count'],
            'relevance': final_relevance,
            'origin': data['origin'],
            'is_new': data['is_new'],
            'context_sentences': contexts
        })

    # ========== STEP 6: Transfer ALIAS/AMBIGUOUS relevance to canonicals ==========
    for entity_text, data in entity_data.items():
        entity = data['entity']

        if entity.classified_as == EntityClassification.ALIAS:
            # Transfer alias relevance to its canonical entity
            alias_relevance = data['raw_relevance'] * data['cluster_boost'] * normalization_factor
            canonical_entities = entity.canonical_refs if entity.canonical_refs else []

            if len(canonical_entities) == 1:
                canonical_entity = canonical_entities[0]
                # Find canonical in final_relevances and add alias relevance
                for item in final_relevances:
                    if item['entity_id'] == canonical_entity.id:
                        item['relevance'] += alias_relevance
                        break

        elif entity.classified_as == EntityClassification.AMBIGUOUS:
            # Get the ambiguous entity's boosted relevance
            ambiguous_relevance = data['raw_relevance'] * data['cluster_boost'] * normalization_factor

            # Get all canonical refs
            all_canonical_entities = entity.canonical_refs if entity.canonical_refs else []

            # Find which canonicals are actually present in this article (detected by NER or added)
            present_canonicals = []
            for canonical_entity in all_canonical_entities:
                for item in final_relevances:
                    if item['entity_id'] == canonical_entity.id:
                        present_canonicals.append(canonical_entity)
                        break

            # Divide ambiguous relevance only among present canonicals
            if present_canonicals:
                divided_relevance = ambiguous_relevance / len(present_canonicals)

                # Add divided relevance to each present canonical entity
                for canonical_entity in present_canonicals:
                    for item in final_relevances:
                        if item['entity_id'] == canonical_entity.id:
                            item['relevance'] += divided_relevance
                            break

    return final_relevances


def recalculate_article_relevance(article_id, session):
    """
    Recalculate local relevance for a single article based on current entity classifications.

    This function:
    1. Loads existing entities for the article (from original NER)
    2. Deletes all article_entities entries for this article
    3. Recalculates relevance using current classifications
    4. Saves new relevances with origin flags

    Args:
        article_id: Article ID to recalculate
        session: SQLAlchemy session

    Returns:
        Dict with statistics: entities_processed, entities_ignored, entities_classification
    """
    # Load article
    article = session.query(Article).filter_by(id=article_id).first()
    if not article:
        raise ValueError(f"Article {article_id} not found")

    # Get existing entities for this article (before deletion)
    existing_entities = session.query(
        article_entities.c.entity_id,
        article_entities.c.mentions,
        article_entities.c.context_sentences
    ).filter(
        article_entities.c.article_id == article_id,
        article_entities.c.origin == EntityOrigin.NER  # Only original NER entities
    ).all()

    # Build entity_counts and entity_contexts from existing data
    entity_counts = {}
    entity_contexts = {}
    entities_original = []

    for entity_id, mentions, contexts in existing_entities:
        entity = session.query(NamedEntity).filter_by(id=entity_id).first()
        if entity:
            entity_counts[entity.name] = mentions
            entity_contexts[entity.name] = contexts or []
            entities_original.append((entity.name, entity.entity_type))

    if not entity_counts:
        # No entities to recalculate
        return {
            'entities_processed': 0,
            'entities_ignored': 0,
            'entities_classification': 0
        }

    # Load cluster info if available
    clusters_info = []
    sentences = []

    if article.cluster_enriched_at:
        # Load clusters and sentences
        clusters = session.query(ArticleCluster).filter_by(article_id=article_id).all()

        for cluster in clusters:
            clusters_info.append({
                'label': cluster.cluster_label,
                'category': cluster.category.value,
                'score': cluster.score,
                'size': cluster.size,
                'indices': cluster.sentence_indices or []
            })

        # Load sentences
        article_sentences = session.query(ArticleSentence).filter_by(article_id=article_id)\
            .order_by(ArticleSentence.sentence_index).all()
        sentences = [s.sentence_text for s in article_sentences]

    # CRITICAL: Decrement article_count for NER entities before deletion
    # This prevents article_count inflation on recalculation
    for entity_id, mentions, contexts in existing_entities:
        entity = session.query(NamedEntity).filter_by(id=entity_id).first()
        if entity and entity.article_count > 0:
            entity.article_count -= 1

    # Delete all existing article_entities for this article
    session.execute(
        delete(article_entities).where(article_entities.c.article_id == article_id)
    )

    # Recalculate relevances with classifications
    final_relevances = calculate_local_relevance_with_classification(
        article=article,
        entity_counts=entity_counts,
        entity_contexts=entity_contexts,
        entities_original=entities_original,
        clusters_info=clusters_info,
        sentences=sentences,
        session=session
    )

    # Insert new relevances
    stats = {
        'entities_processed': len(final_relevances),
        'entities_ignored': 0,
        'entities_classification': 0
    }

    for data in final_relevances:
        session.execute(
            insert(article_entities).values(
                article_id=article_id,
                entity_id=data['entity_id'],
                mentions=data['mentions'],
                relevance=data['relevance'],
                origin=data['origin'],
                context_sentences=data['context_sentences']
            )
        )

        if data['relevance'] == 0.0:
            stats['entities_ignored'] += 1
        if data['origin'] == EntityOrigin.CLASSIFICATION:
            stats['entities_classification'] += 1

    return stats


def extract_entities(text):
    """
    Extract named entities from text using spaCy with their sentence contexts.

    Args:
        text: Text to process

    Returns:
        Tuple of:
            - entities: List of tuples: [(entity_text, entity_type), ...]
            - entity_contexts: Dict mapping entity_text -> list of sentences containing it
    """
    if not nlp:
        return [], {}

    doc = nlp(text)
    entities = []
    entity_contexts = {}  # entity_text -> [sentence1, sentence2, ...]

    for ent in doc.ents:
        # Map spaCy label to our EntityType
        entity_type = SPACY_TO_ENTITY_TYPE.get(ent.label_, None)
        if entity_type:
            entities.append((ent.text, entity_type))

            # Get the sentence containing this entity
            sentence_text = ent.sent.text.strip()

            # Add to context list for this entity
            if ent.text not in entity_contexts:
                entity_contexts[ent.text] = []

            # Only add if not already present (avoid duplicates)
            if sentence_text not in entity_contexts[ent.text]:
                entity_contexts[ent.text].append(sentence_text)

    return entities, entity_contexts


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

            # ========== PHASE 1.1: CLUSTER SUMMARIZATION (MOVED TO flash_news.py) ==========
            # NOTE: Flash news generation has been moved to a separate process: generate_flash_news
            # Run: news process start -d <domain> -t generate_flash_news
            # This code is kept commented as reference
            #
            # logs.append("Phase 1.1: Generating flash news from core clusters...")
            #
            # core_clusters = [c for c in clusters_info if c['category'] == 'core']
            # stats['flash_news_generated'] = 0
            #
            # if core_clusters:
            #     logs.append(f"Found {len(core_clusters)} core clusters to summarize")
            #
            #     try:
            #         from llm.openai_client import openai_structured_output
            #
            #         for cluster_data in core_clusters:
            #             try:
            #                 # Find the cluster object we just created
            #                 cluster = session.query(ArticleCluster).filter_by(
            #                     article_id=article.id,
            #                     cluster_label=int(cluster_data['label'])
            #                 ).first()
            #
            #                 if not cluster:
            #                     logs.append(f"  Warning: Could not find cluster {cluster_data['label']} in DB")
            #                     continue
            #
            #                 # Check if flash news already exists for this cluster
            #                 existing_flash = session.query(FlashNews).filter_by(cluster_id=cluster.id).first()
            #                 if existing_flash:
            #                     logs.append(f"  Skipping cluster {cluster_data['label']}: flash news already exists")
            #                     continue
            #
            #                 # Get sentences for this cluster
            #                 cluster_sentences = [sentences[idx] for idx in cluster_data['indices'] if idx < len(sentences)]
            #
            #                 # Prepare data for LLM
            #                 llm_data = {
            #                     'title': article.title,
            #                     'cluster_sentences': cluster_sentences,
            #                     'cluster_score': cluster_data['score']
            #                 }
            #
            #                 # Call OpenAI for structured summarization
            #                 result = openai_structured_output('core_cluster_summarization', llm_data)
            #                 summary_text = result.summary
            #
            #                 # Generate embedding for the summary
            #                 summary_embedding = make_embeddings([summary_text])
            #                 summary_embedding_list = summary_embedding[0].tolist()
            #
            #                 # Create FlashNews record
            #                 flash_news = FlashNews(
            #                     cluster_id=cluster.id,
            #                     summary=summary_text,
            #                     embedding=summary_embedding_list,
            #                     published=0
            #                 )
            #                 session.add(flash_news)
            #                 session.flush()
            #
            #                 stats['flash_news_generated'] += 1
            #                 logs.append(f"  ✓ Cluster {cluster_data['label']}: Generated flash news (ID: {flash_news.id})")
            #                 logs.append(f"    Summary: {summary_text[:100]}...")
            #
            #             except Exception as cluster_error:
            #                 # Log error but continue processing other clusters
            #                 logs.append(f"  ✗ Failed to generate flash news for cluster {cluster_data['label']}: {str(cluster_error)}")
            #                 continue
            #
            #         logs.append(f"Generated {stats['flash_news_generated']} flash news from {len(core_clusters)} core clusters")
            #
            #     except ImportError as e:
            #         logs.append(f"Warning: Could not import OpenAI client, skipping summarization: {e}")
            #     except Exception as e:
            #         logs.append(f"Warning: Error during cluster summarization: {e}")
            #
            # else:
            #     logs.append("No core clusters found, skipping flash news generation")

        else:
            logs.append("No sentences found, skipping clustering")

        # ========== PHASE 2: NER ==========
        logs.append("Phase 2: Extracting named entities...")

        # Extract entities from title, subtitle, and content
        # Note: subtitle is included for NER but NOT for clustering
        # Use period+space separator to prevent NER from merging entities across parts
        # (e.g., "...con Epstein" + "Summers dijo..." would merge into "Epstein Summers")
        text_parts = [article.title]
        if article.subtitle:
            text_parts.append(article.subtitle)
        text_parts.append(article.content)
        text = " ".join([f"{part}." if not part.endswith('.') else part for part in text_parts ])
        entities, entity_contexts = extract_entities(text)

        stats['entities_found'] = len(entities)
        logs.append(f"Found {len(entities)} entities")

        # Count entity mentions
        entity_counts = {}
        for entity_text, entity_type in entities:
            # Skip if entity text is too short or just numbers
            if len(entity_text) < 2 or entity_text.isdigit():
                continue

            # Count entity mentions for this article
            entity_counts[entity_text] = entity_counts.get(entity_text, 0) + 1

        # ========== PHASE 3: CALCULATE RELEVANCES WITH CLASSIFICATIONS ==========
        logs.append("Phase 3: Calculating relevances with entity classifications...")

        # Use new unified relevance calculation function
        final_relevances = calculate_local_relevance_with_classification(
            article=article,
            entity_counts=entity_counts,
            entity_contexts=entity_contexts,
            entities_original=entities,
            clusters_info=clusters_info,
            sentences=sentences,
            session=session
        )

        # Track statistics
        stats['entities_new'] = 0
        stats['entities_existing'] = 0
        stats['entities_classification'] = 0

        # Insert relevances into article_entities
        for data in final_relevances:
            # Count new vs existing entities (only NER ones)
            if data['origin'] == EntityOrigin.NER:  # Only count entities detected by NER
                if data['is_new']:
                    stats['entities_new'] += 1
                else:
                    stats['entities_existing'] += 1

            # Track classification entities separately
            if data['origin'] == EntityOrigin.CLASSIFICATION:
                stats['entities_classification'] += 1

            # Insert into article_entities association table
            stmt = insert(article_entities).values(
                article_id=article.id,
                entity_id=data['entity_id'],
                mentions=data['mentions'],
                relevance=data['relevance'],
                origin=data['origin'],
                context_sentences=data['context_sentences']
            )
            session.execute(stmt)

            # Log entity processing
            origin_flag = " [classification]" if data['origin'] == EntityOrigin.CLASSIFICATION else ""
            ignored_flag = " [IGNORED]" if data['relevance'] == 0.0 else ""
            logs.append(f"  {data['entity_name']}: {data['mentions']} mentions, "
                       f"relevance={data['relevance']:.4f}{origin_flag}{ignored_flag}")

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
