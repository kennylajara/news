"""
Deep article analysis module.
Generates multi-dimensional analysis of articles for recommendation system matching.
"""

from datetime import datetime
from db import ProcessingBatch, BatchItem, Article, ArticleAnalysis


def categorize_sentences_by_cluster(clusters_info, sentences, original_content):
    """
    Categorize sentences by cluster importance and prepare annotated content.
    Preserves original Markdown formatting (paragraphs, headings, etc).

    Args:
        clusters_info: List of cluster dicts with 'category' and 'indices'
        sentences: List of sentence strings
        original_content: Original article content with Markdown formatting

    Returns:
        dict: Categorized content with formatting preserved
            {
                'annotated_content': str,  # Content with <strong> tags and [^N] refs
                'footnotes': [(ref_num, sentence), ...],  # FILLER sentences as footnotes
                'stats': {'core': count, 'secondary': count, 'filler': count, ...}
            }
    """
    if not clusters_info or not sentences or not original_content:
        return None

    # Map sentence indices to categories
    sentence_categories = {}
    for cluster in clusters_info:
        category = cluster['category']
        for idx in cluster['indices']:
            sentence_categories[idx] = category

    # Build replacement mapping and footnotes
    footnotes = []
    stats = {'core': 0, 'secondary': 0, 'filler': 0, 'total': len(sentences)}
    footnote_counter = 1

    # Start with original content
    annotated_content = original_content

    # Process sentences in reverse order to avoid offset issues
    for idx in range(len(sentences) - 1, -1, -1):
        sentence = sentences[idx]
        category = sentence_categories.get(idx, 'filler')

        # Find sentence in content (escape special regex chars)
        import re
        escaped_sentence = re.escape(sentence)

        if category == 'core':
            # Wrap in <strong> tags
            replacement = f"<strong>{sentence}</strong>"
            annotated_content = re.sub(escaped_sentence, replacement, annotated_content, count=1)
            stats['core'] += 1
        elif category == 'secondary':
            # Keep as-is
            stats['secondary'] += 1
        else:  # filler - replace with footnote reference
            replacement = f"[^{footnote_counter}]"
            annotated_content = re.sub(escaped_sentence, replacement, annotated_content, count=1)
            footnotes.insert(0, (footnote_counter, sentence))  # Insert at beginning to maintain order
            footnote_counter += 1
            stats['filler'] += 1

    stats['main_content'] = stats['core'] + stats['secondary']

    return {
        'annotated_content': annotated_content,
        'footnotes': footnotes,
        'stats': stats
    }


def process_article_analysis(article, batch_item, session):
    """
    Generate deep analysis for an article.

    Args:
        article: Article object
        batch_item: BatchItem object for tracking
        session: Database session

    Returns:
        dict: Statistics about processing
    """
    logs = []
    stats = {
        'analysis_generated': 0,
        'analysis_skipped': 0,
        'entities_extracted': 0,
        'processing_time': 0
    }

    start_time = datetime.utcnow()
    batch_item.status = 'processing'
    batch_item.started_at = start_time
    session.flush()

    try:
        logs.append(f"Processing analysis for article {article.id}: {article.title[:50]}...")

        # Check if analysis already exists
        existing_analysis = session.query(ArticleAnalysis).filter_by(article_id=article.id).first()
        if existing_analysis:
            logs.append(f"Analysis already exists (ID: {existing_analysis.id}), skipping")
            stats['analysis_skipped'] = 1
            batch_item.status = 'completed'
            batch_item.completed_at = datetime.utcnow()
            batch_item.logs = "\\n".join(logs)
            batch_item.stats = stats
            session.flush()
            return stats

        # AUTO-CLUSTERING: Execute clustering if not done yet
        if not article.clusterized_at:
            logs.append("No clusters found, running clustering first...")
            try:
                from processors.enrich import process_article as enrich_process_article
                from db import BatchItem as TempBatchItem

                # Create temporary batch item for clustering
                temp_batch_item = TempBatchItem(
                    batch_id=batch_item.batch_id,
                    article_id=article.id,
                    status='pending'
                )
                session.add(temp_batch_item)
                session.flush()

                # Run clustering
                enrich_process_article(article, temp_batch_item, session)
                logs.append("✓ Clustering completed successfully")
                stats['auto_clustered'] = 1

            except Exception as e:
                logs.append(f"⚠ Clustering failed: {e}")
                logs.append("Continuing analysis without clusters...")
                stats['auto_clustered'] = 0

        # Import LLM client
        try:
            from llm.openai_client import openai_structured_output
        except ImportError as e:
            raise ImportError(f"Could not import OpenAI client: {e}")

        # CONTENT CATEGORIZATION: Load clusters and categorize sentences
        from db import ArticleCluster, ArticleSentence

        categorized_content = None

        if article.clusterized_at:
            # Load clusters
            clusters = session.query(ArticleCluster).filter_by(article_id=article.id).all()
            clusters_info = []
            for cluster in clusters:
                clusters_info.append({
                    'label': cluster.cluster_label,
                    'category': cluster.category.value,
                    'score': cluster.score,
                    'size': cluster.size,
                    'indices': cluster.sentence_indices or []
                })

            # Load sentences
            article_sentences = session.query(ArticleSentence).filter_by(article_id=article.id)\
                .order_by(ArticleSentence.sentence_index).all()
            sentences = [s.sentence_text for s in article_sentences]

            # Categorize sentences for template
            categorized_content = categorize_sentences_by_cluster(clusters_info, sentences, article.content)

            if categorized_content:
                stats_data = categorized_content['stats']
                logs.append(f"Content structured: {stats_data['core']} CORE, {stats_data['secondary']} SECONDARY, {stats_data['filler']} CONTEXT")
                logs.append(f"Main content: {stats_data['main_content']}/{stats_data['total']} sentences")

        # Prepare data for LLM (excluding source/author to avoid bias)
        llm_data = {
            'title': article.title,
            'subtitle': article.subtitle or '',
            'published_date': article.published_date.strftime('%Y-%m-%d') if article.published_date else '',
            'category': article.category or '',
            'content': article.content,  # Full content (fallback)
            'categorized_content': categorized_content  # Categorized sentences for template
        }

        logs.append(f"Calling LLM for analysis...")

        # Call OpenAI for structured analysis
        result = openai_structured_output('article_analysis', llm_data)

        # Process extracted entities using sophisticated relevance calculation
        from db import NamedEntity, EntityType, EntityOrigin
        from sqlalchemy.dialects.sqlite import insert
        from db.models import article_entities
        from processors.enrich import calculate_local_relevance_with_classification

        # Count entity mentions
        entity_counts = {}
        entity_contexts = {}  # Empty for now, could be populated from result if needed
        entities_original = []

        for ent in result.entities:
            entity_counts[ent.text] = entity_counts.get(ent.text, 0) + 1
            entities_original.append((ent.text, EntityType[ent.type.value]))

        # Reuse clusters_info and sentences from filtering (already loaded if clusterized)
        # If not clusterized, these will be empty lists (handled gracefully)
        if not article.clusterized_at:
            clusters_info = []
            sentences = []

        # Calculate relevances using sophisticated algorithm
        final_relevances = calculate_local_relevance_with_classification(
            article=article,
            entity_counts=entity_counts,
            entity_contexts=entity_contexts,
            entities_original=entities_original,
            clusters_info=clusters_info,
            sentences=sentences,
            session=session
        )

        # Save to database
        for data in final_relevances:
            stmt = insert(article_entities).values(
                article_id=article.id,
                entity_id=data['entity_id'],
                mentions=data['mentions'],
                relevance=data['relevance'],
                origin=data['origin'],
                context_sentences=data.get('context_sentences', [])
            ).on_conflict_do_nothing()
            session.execute(stmt)

        stats['entities_extracted'] = len(final_relevances)
        logs.append(f"Extracted {stats['entities_extracted']} unique entities")
        if clusters_info:
            logs.append(f"Applied cluster boost to {len(clusters_info)} clusters")

        # Create ArticleAnalysis record
        analysis = ArticleAnalysis(
            article_id=article.id,
            # Semantic
            key_concepts=result.key_concepts,
            semantic_relations=[],  # Commented out in schema
            # Narrative
            narrative_frames=[f.value for f in result.narrative_frames],
            editorial_tone=result.editorial_tone.value,
            style_descriptors=[],  # Commented out in schema
            # Controversy/bias
            controversy_score=result.controversy_score,
            political_bias=result.political_bias,
            # Quality
            has_named_sources=0,  # Commented out in schema
            has_data_or_statistics=0,  # Commented out in schema
            has_multiple_perspectives=0,  # Commented out in schema
            quality_score=0,  # Commented out in schema
            # Content format and temporal relevance
            content_format=result.content_format.value,
            temporal_relevance=result.temporal_relevance.value,
            # Audience
            audience_education=result.audience_education.value,
            target_age_range=result.target_age_range.value,
            target_professions=[],  # Commented out in schema
            required_interests=[],  # Commented out in schema
            # Industry
            relevant_industries=[i.value for i in result.relevant_industries],
            # Geographic
            geographic_scope=result.geographic_scope.value,
            cultural_context="",  # Commented out in schema
            # Source diversity
            voices_represented=[],  # Commented out in schema
            source_diversity_score=0  # Commented out in schema
        )
        session.add(analysis)
        session.flush()

        stats['analysis_generated'] = 1
        logs.append(f"✓ Generated analysis (ID: {analysis.id})")
        logs.append(f"  Controversy: {result.controversy_score}, Bias: {result.political_bias}")
        logs.append(f"  Frames: {', '.join(f.value for f in result.narrative_frames)}")
        logs.append(f"  Tone: {result.editorial_tone.value}, Format: {result.content_format.value}, Temporal: {result.temporal_relevance.value}")

        # Update batch item
        batch_item.status = 'completed'
        batch_item.completed_at = datetime.utcnow()
        batch_item.logs = "\\n".join(logs)
        stats['processing_time'] = (datetime.utcnow() - start_time).total_seconds()
        batch_item.stats = stats
        session.flush()

        return stats

    except Exception as e:
        # Mark as failed
        batch_item.status = 'failed'
        batch_item.error_message = str(e)
        batch_item.completed_at = datetime.utcnow()
        batch_item.logs = "\\n".join(logs + [f"ERROR: {str(e)}"])
        session.flush()
        raise


def process_article_analysis_batch(batch_id, session):
    """
    Process all items in an article analysis batch.

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
        'analysis_generated': 0,
        'analysis_skipped': 0,
        'entities_extracted': 0,
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
            stats = process_article_analysis(article, item, session)

            # Aggregate stats
            for key in total_stats:
                if key in stats:
                    total_stats[key] += stats[key]

            batch.successful_items += 1
            batch.processed_items += 1

            if stats['analysis_generated']:
                print(f"  ✓ Analyzed article {article.id}: {article.title[:50]}...")
            else:
                print(f"  - Skipped article {article.id} (already analyzed)")

        except Exception as e:
            batch.failed_items += 1
            batch.processed_items += 1
            print(f"  ✗ Failed to analyze article {item.article_id}: {e}")

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
    print(f"  Analyses generated: {total_stats['analysis_generated']}")
    print(f"  Analyses skipped: {total_stats['analysis_skipped']}")
    print(f"  Entities extracted: {total_stats['entities_extracted']}")

    return batch.failed_items == 0
