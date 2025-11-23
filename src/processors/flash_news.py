"""
Flash news generation module.
Generates concise summaries from core article clusters using LLM.
"""

from datetime import datetime
from db import ProcessingBatch, BatchItem, Article, ArticleCluster, ArticleSentence, ClusterCategory, FlashNews
from processors.clustering import make_embeddings


def process_flash_news_article(article, batch_item, session):
    """
    Generate flash news for all core clusters in an article that don't have flash news yet.

    Args:
        article: Article object (must have clusterized_at set)
        batch_item: BatchItem object for tracking
        session: Database session

    Returns:
        dict: Statistics about processing
    """
    logs = []
    stats = {
        'core_clusters_found': 0,
        'flash_news_generated': 0,
        'flash_news_skipped': 0,
        'processing_time': 0
    }

    start_time = datetime.utcnow()
    batch_item.status = 'processing'
    batch_item.started_at = start_time
    session.flush()

    try:
        logs.append(f"Processing flash news for article {article.id}: {article.title[:50]}...")

        # Validate article has clusters
        if not article.clusterized_at:
            raise ValueError(f"Article {article.id} has not been cluster-enriched yet")

        # Get core clusters for this article
        core_clusters = (
            session.query(ArticleCluster)
            .filter(ArticleCluster.article_id == article.id)
            .filter(ArticleCluster.category == ClusterCategory.CORE)
            .all()
        )

        stats['core_clusters_found'] = len(core_clusters)
        logs.append(f"Found {len(core_clusters)} core clusters")

        if not core_clusters:
            logs.append("No core clusters found, nothing to process")
            batch_item.status = 'completed'
            batch_item.completed_at = datetime.utcnow()
            batch_item.logs = "\\n".join(logs)
            batch_item.stats = stats
            session.flush()
            return stats

        # Import LLM client
        try:
            from llm.openai_client import openai_structured_output
        except ImportError as e:
            raise ImportError(f"Could not import OpenAI client: {e}")

        # Process each core cluster
        for cluster in core_clusters:
            try:
                # Check if flash news already exists
                existing_flash = session.query(FlashNews).filter_by(cluster_id=cluster.id).first()
                if existing_flash:
                    logs.append(f"  Cluster {cluster.cluster_label}: flash news already exists (ID: {existing_flash.id}), skipping")
                    stats['flash_news_skipped'] += 1
                    continue

                # Get sentences for this cluster
                cluster_sentences = (
                    session.query(ArticleSentence)
                    .filter(ArticleSentence.cluster_id == cluster.id)
                    .order_by(ArticleSentence.sentence_index)
                    .all()
                )

                if not cluster_sentences:
                    logs.append(f"  Cluster {cluster.cluster_label}: no sentences found, skipping")
                    continue

                sentence_texts = [s.sentence_text for s in cluster_sentences]

                # Prepare data for LLM
                llm_data = {
                    'title': article.title,
                    'cluster_sentences': sentence_texts,
                    'cluster_score': cluster.score
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
                logs.append(f"  ✓ Cluster {cluster.cluster_label}: Generated flash news (ID: {flash_news.id})")
                logs.append(f"    Summary: {summary_text[:100]}...")

            except Exception as cluster_error:
                # Log error but continue processing other clusters
                logs.append(f"  ✗ Failed to generate flash news for cluster {cluster.cluster_label}: {str(cluster_error)}")
                continue

        # Update batch item
        batch_item.status = 'completed'
        batch_item.completed_at = datetime.utcnow()
        batch_item.logs = "\\n".join(logs)
        stats['processing_time'] = (datetime.utcnow() - start_time).total_seconds()
        batch_item.stats = stats
        session.flush()

        logs.append(f"Successfully processed article {article.id}: {stats['flash_news_generated']} flash news generated, {stats['flash_news_skipped']} skipped")

        return stats

    except Exception as e:
        # Mark as failed
        batch_item.status = 'failed'
        batch_item.error_message = str(e)
        batch_item.completed_at = datetime.utcnow()
        batch_item.logs = "\\n".join(logs + [f"ERROR: {str(e)}"])
        session.flush()
        raise


def process_flash_news_batch(batch_id, session):
    """
    Process all items in a flash news generation batch.

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
        'core_clusters_found': 0,
        'flash_news_generated': 0,
        'flash_news_skipped': 0,
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
            stats = process_flash_news_article(article, item, session)

            # Aggregate stats
            for key in total_stats:
                if key in stats:
                    total_stats[key] += stats[key]

            batch.successful_items += 1
            batch.processed_items += 1

            print(f"  ✓ Processed article {article.id}: {stats['flash_news_generated']} flash news generated")

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
    print(f"  Core clusters found: {total_stats['core_clusters_found']}")
    print(f"  Flash news generated: {total_stats['flash_news_generated']}")
    print(f"  Flash news skipped: {total_stats['flash_news_skipped']}")

    return batch.failed_items == 0
