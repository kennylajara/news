"""
Calculate global relevance for entities using PageRank.

This module provides the main orchestration function that:
1. Queries enriched articles from the database
2. Prepares data for PageRank algorithm
3. Executes PageRank calculation
4. Updates entity metrics in database
"""

from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.database import Database
from db.models import Article, NamedEntity, EntityType, Base, PageRankExecution
from domain.entity_rank import EntityRankCalculator
from pathlib import Path


def _save_pagerank_execution_log(
    start_time: datetime,
    end_time: datetime,
    source_domain: Optional[str],
    damping: float,
    min_relevance_threshold: float,
    time_decay_days: Optional[int],
    total_articles: int,
    pagerank_scores: Dict[str, float],
    normalized_scores: Dict[str, float],
    top_entities: List[tuple],
    stats: Dict
):
    """
    Save PageRank execution log to separate logs database.

    Uses llm_logs.db to avoid conflicts with main application database.
    """
    try:
        # Ensure data directory exists
        Path("data").mkdir(parents=True, exist_ok=True)

        # Create separate engine for logs database
        engine = create_engine('sqlite:///data/llm_logs.db', echo=False)

        # Create tables if they don't exist
        Base.metadata.create_all(engine)

        # Create session
        SessionLocal = sessionmaker(bind=engine)
        log_session = SessionLocal()

        try:
            # Create log entry
            log_entry = PageRankExecution(
                started_at=start_time,
                completed_at=end_time,
                duration_seconds=stats['duration_seconds'],
                damping=damping,
                max_iter=1000,  # From EntityRankCalculator default
                tolerance=1e-6,  # From EntityRankCalculator default
                min_relevance_threshold=min_relevance_threshold,
                time_decay_days=time_decay_days,
                timeout_seconds=30.0,  # From EntityRankCalculator default
                source_domain=source_domain,
                total_articles=total_articles,
                total_entities=stats['total_entities'],
                graph_edges=stats['graph_edges'],
                graph_density=stats['graph_density'],
                matrix_memory_mb=stats['matrix_memory_mb'],
                matrix_nnz=stats['matrix_nnz'],
                matrix_sparsity=stats['matrix_sparsity'],
                iterations=stats['iterations'],
                converged=1 if stats['converged'] else 0,
                convergence_delta=stats['convergence_delta'],
                entities_ranked=stats['entities_ranked'],
                min_score=stats['min_score'],
                max_score=stats['max_score'],
                mean_score=stats['mean_score'],
                median_score=stats['median_score'],
                std_dev_score=stats['std_dev_score'],
                top_entities=[{'name': name, 'score': score} for name, score in top_entities],
                success=1,
                error_message=None
            )

            log_session.add(log_entry)
            log_session.commit()

        except Exception as e:
            # Silently fail - logging shouldn't crash the main application
            log_session.rollback()
            import sys
            print(f"Warning: Failed to save PageRank execution log: {e}", file=sys.stderr)

        finally:
            log_session.close()
            engine.dispose()

    except Exception as e:
        # Silently fail at outer level too
        import sys
        print(f"Warning: Failed to create PageRank log session: {e}", file=sys.stderr)


def calculate_global_relevance(
    db: Database,
    session: Session,
    source_domain: Optional[str] = None,
    damping: float = 0.85,
    min_relevance_threshold: float = 0.3,
    time_decay_days: Optional[int] = None
) -> Dict:
    """
    Calculate global relevance for all entities using PageRank.

    Args:
        db: Database instance
        session: SQLAlchemy session
        source_domain: Optional, filter articles by domain (for testing)
        damping: PageRank damping factor (default: 0.85)
        min_relevance_threshold: Ignore weak co-occurrences (default: 0.3)
        time_decay_days: Apply time decay to older articles (optional)

    Returns:
        Dict with statistics:
            - total_articles: Number of articles processed
            - total_entities: Number of entities ranked
            - iterations: Number of PageRank iterations
            - top_entities: List of top 10 entities with scores
            - convergence_time: Time taken for calculation
    """
    start_time = datetime.utcnow()
    calculation_started_at = start_time  # Timestamp when calculation started

    # Step 1: Get previous pagerank scores for warm start
    previous_scores = {}
    last_calculation = session.query(NamedEntity.last_rank_calculated_at)\
        .filter(NamedEntity.last_rank_calculated_at.isnot(None))\
        .order_by(NamedEntity.last_rank_calculated_at.desc())\
        .first()

    if last_calculation and last_calculation[0]:
        # Get pagerank scores (unnormalized) from previous calculation for warm start
        prev_entities = session.query(NamedEntity.name, NamedEntity.pagerank)\
            .filter(NamedEntity.last_rank_calculated_at == last_calculation[0])\
            .all()
        previous_scores = {name: score for name, score in prev_entities if score is not None}

    # Step 2: Query enriched articles with their entities
    query = session.query(
        Article.id,
        Article.published_date,
        NamedEntity.name,
        NamedEntity.entity_type
    ).join(
        Article.entities
    ).filter(
        Article.clusterized_at.isnot(None),
        NamedEntity.entity_type.in_(EntityRankCalculator.RANKED_TYPES)
    )

    # Filter by domain if specified
    if source_domain:
        from db.models import Source
        query = query.join(Article.source).filter(Source.domain == source_domain)

    # Get article-entity associations with relevance scores
    # We need to join through article_entities to get relevance
    from db.models import article_entities
    results = session.query(
        Article.id,
        Article.published_date,
        NamedEntity.name,
        NamedEntity.entity_type,
        article_entities.c.relevance
    ).select_from(Article)\
        .join(article_entities, Article.id == article_entities.c.article_id)\
        .join(NamedEntity, NamedEntity.id == article_entities.c.entity_id)\
        .filter(
            Article.clusterized_at.isnot(None),
            NamedEntity.entity_type.in_(EntityRankCalculator.RANKED_TYPES)
        )

    if source_domain:
        from db.models import Source
        results = results.join(Article.source).filter(Source.domain == source_domain)

    results = results.order_by(Article.id).all()

    if not results:
        return {
            'total_articles': 0,
            'total_entities': 0,
            'iterations': 0,
            'top_entities': [],
            'convergence_time': 0.0
        }

    # Step 3: Group by article
    articles_data = {}
    for article_id, published_date, entity_name, entity_type, relevance in results:
        if article_id not in articles_data:
            articles_data[article_id] = {
                'entities': [],
                'relevances': [],
                'published_date': published_date
            }

        articles_data[article_id]['entities'].append((entity_name, entity_type))
        articles_data[article_id]['relevances'].append(relevance)

    articles = list(articles_data.values())

    # Step 4: Calculate PageRank (returns both raw and normalized scores)
    calculator = EntityRankCalculator(
        damping=damping,
        max_iter=1000,
        tol=1e-6,
        min_relevance_threshold=min_relevance_threshold,
        time_decay_days=time_decay_days,
        timeout_seconds=30.0,
        initial_scores=previous_scores
    )

    pagerank_scores, normalized_scores, iterations, stats = calculator.calculate_pagerank(articles)

    # Step 5: Calculate complementary metrics
    complementary_metrics = calculator.calculate_complementary_metrics(articles)

    # Step 6: Update database
    for entity_name, raw_score in pagerank_scores.items():
        metrics = complementary_metrics.get(entity_name, {})
        normalized_score = normalized_scores.get(entity_name, 0.0)

        session.query(NamedEntity)\
            .filter(NamedEntity.name == entity_name)\
            .update({
                'pagerank': raw_score,
                'global_relevance': normalized_score,
                'article_count': metrics.get('article_count', 0),
                'avg_local_relevance': metrics.get('avg_local_relevance', 0.0),
                'diversity': metrics.get('diversity', 0),
                'last_rank_calculated_at': calculation_started_at
            })

    # Set unranked entities (not in RANKED_TYPES) to have 0.0 pagerank and global_relevance
    # and update their last_rank_calculated_at too
    session.query(NamedEntity)\
        .filter(~NamedEntity.entity_type.in_(EntityRankCalculator.RANKED_TYPES))\
        .update({
            'pagerank': 0.0,
            'global_relevance': 0.0,
            'last_rank_calculated_at': calculation_started_at
        })

    session.commit()

    # Step 7: Prepare statistics
    end_time = datetime.utcnow()
    convergence_time = (end_time - start_time).total_seconds()

    # Get top 10 entities (by normalized score for display)
    top_entities = sorted(normalized_scores.items(), key=lambda x: x[1], reverse=True)[:10]

    # Step 8: Save execution log to llm_logs.db
    _save_pagerank_execution_log(
        start_time=start_time,
        end_time=end_time,
        source_domain=source_domain,
        damping=damping,
        min_relevance_threshold=min_relevance_threshold,
        time_decay_days=time_decay_days,
        total_articles=len(articles),
        pagerank_scores=pagerank_scores,
        normalized_scores=normalized_scores,
        top_entities=top_entities,
        stats=stats
    )

    return {
        'total_articles': len(articles),
        'total_entities': len(pagerank_scores),
        'iterations': iterations,
        'top_entities': [
            {'name': name, 'score': score}
            for name, score in top_entities
        ],
        'convergence_time': convergence_time,
        'calculation_started_at': calculation_started_at
    }
