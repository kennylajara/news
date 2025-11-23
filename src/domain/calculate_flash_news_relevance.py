"""
Calculate relevance scores for flash news.

This module provides the main orchestration function that:
1. Calculates multi-component relevance scores for flash news
2. Assigns priority tiers based on scores
3. Updates flash_news table with scores and components
"""

from datetime import datetime, timedelta
from typing import Optional, Dict
import math
import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session
from db.database import Database
from db.models import FlashNews, Article, NamedEntity, ArticleCluster, article_entities


# Configuration constants
FLASH_NEWS_RELEVANCE_WEIGHTS = {
    'entity_importance': 0.45,    # Figuras VIP
    'temporal_freshness': 0.25,   # Urgencia temporal
    'cluster_quality': 0.15,      # Calidad del resumen
    'topic_diversity': 0.10,      # Novedad temática
    'source_authority': 0.05      # Confiabilidad
}


class FlashNewsRelevanceCalculator:
    """
    Calculator for flash news relevance scores.

    Combines multiple signals to determine which flash news should be published.
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Initialize calculator with optional custom weights.

        Args:
            weights: Dict of component weights (must sum to 1.0)
        """
        self.weights = weights or FLASH_NEWS_RELEVANCE_WEIGHTS

        # Validate weights sum to 1.0
        weight_sum = sum(self.weights.values())
        if not (0.99 <= weight_sum <= 1.01):  # Allow small floating point errors
            raise ValueError(f"Weights must sum to 1.0, got {weight_sum}")

    def calculate_relevance(self, flash_news: FlashNews, session: Session) -> Dict:
        """
        Calculate comprehensive relevance score for a flash news.

        Args:
            flash_news: FlashNews object
            session: SQLAlchemy session

        Returns:
            dict with 'score', 'components', 'priority', 'calculated_at'
        """
        components = {
            'entity_importance': self._calculate_entity_importance(flash_news, session),
            'temporal_freshness': self._calculate_temporal_freshness(flash_news),
            'cluster_quality': self._calculate_cluster_quality(flash_news),
            'topic_diversity': self._calculate_topic_diversity(flash_news, session),
            'source_authority': self._calculate_source_authority(flash_news)
        }

        # Weighted sum
        final_score = sum(
            components[key] * self.weights[key]
            for key in components
        )

        # Derive priority tier
        priority = self._score_to_priority(final_score)

        return {
            'score': round(final_score, 4),
            'components': {k: round(v, 4) for k, v in components.items()},
            'priority': priority,
            'calculated_at': datetime.utcnow()
        }

    def _calculate_entity_importance(self, flash_news: FlashNews, session: Session) -> float:
        """
        Calculate importance based on entities in the article.

        Flash news about VIP entities (high PageRank) are more relevant.

        Uses COALESCE to handle entities without PageRank:
        - If entity has PageRank: use it
        - If not: use average of all entities with PageRank
        - If no entities have PageRank: use 0.6 (conservative default)
        """
        article = flash_news.cluster.article

        # Calculate fallback value for entities without PageRank
        avg_pagerank = session.query(
            func.avg(NamedEntity.global_relevance)
        ).filter(
            NamedEntity.global_relevance.isnot(None)
        ).scalar()

        fallback_value = avg_pagerank if avg_pagerank is not None else 0.6

        # Query top 5 entities by local relevance, using fallback for missing PageRank
        top_entities = session.query(
            article_entities.c.relevance,
            func.coalesce(NamedEntity.global_relevance, fallback_value).label('global_relevance')
        ).join(NamedEntity).filter(
            article_entities.c.article_id == article.id
        ).order_by(
            article_entities.c.relevance.desc()
        ).limit(5).all()

        if not top_entities:
            return 0.0

        # Product of local × global relevance (average of top 5)
        weighted_sum = sum(
            local * global_rel
            for local, global_rel in top_entities
        )

        avg_score = weighted_sum / len(top_entities)

        # BOOST: If any entity in top 5 or top 33% (whichever is smaller) has global_relevance > 0.8 (VIP)
        boost_threshold = min(5, max(1, math.ceil(len(top_entities) * 0.33)))
        boost_candidates = top_entities[:boost_threshold]
        max_global = max(global_rel for _, global_rel in boost_candidates)

        if max_global > 0.8:
            avg_score *= 1.3  # 30% boost for VIP news

        return min(avg_score, 1.0)

    def _calculate_temporal_freshness(self, flash_news: FlashNews, half_life_hours: float = 12.0) -> float:
        """
        Calculate freshness score with exponential decay.

        Flash news decay aggressively - news is perishable.
        """
        article = flash_news.cluster.article

        if not article.published_date:
            return 0.3  # Penalty if no date

        now = datetime.utcnow()
        hours_old = (now - article.published_date).total_seconds() / 3600

        # Adjust half-life based on temporal relevance
        # Note: article.analysis is a list (backref), get first element if exists
        analysis = article.analysis[0] if article.analysis else None
        if analysis:
            temporal_type = analysis.temporal_relevance
            if temporal_type == 'breaking':
                half_life_hours = 6   # Ultra urgent, fast decay
            elif temporal_type == 'timely':
                half_life_hours = 12  # Default
            elif temporal_type == 'evergreen':
                half_life_hours = 48  # More durable

        # Exponential decay: score = e^(-hours / half_life)
        score = np.exp(-hours_old / half_life_hours)

        # BOOST for breaking news very recent (<1 hour)
        if hours_old < 1 and analysis:
            if analysis.temporal_relevance == 'breaking':
                score = 1.0  # Maximum priority

        return float(score)

    def _calculate_cluster_quality(self, flash_news: FlashNews) -> float:
        """
        Calculate quality based on the CORE cluster that generated this flash news.

        Better clusters = better summaries.
        """
        cluster = flash_news.cluster

        # Base score from cluster (already calculated during clustering)
        base_score = cluster.score  # 0.0-1.0

        # Adjust by cluster size
        size_factor = 1.0
        if cluster.size < 3:
            size_factor = 0.8  # Penalize very small clusters
        elif cluster.size > 10:
            size_factor = 1.2  # Bonus for robust clusters

        final_score = base_score * size_factor

        return min(final_score, 1.0)

    def _calculate_topic_diversity(
        self,
        flash_news: FlashNews,
        session: Session,
        time_window_hours: int = 24
    ) -> float:
        """
        Calculate diversity score - penalize repetitive topics.

        Flash news about novel topics are more interesting.
        """
        if not flash_news.embedding:
            return 0.5  # Neutral if no embedding

        # Find other recent flash news (last 24h)
        cutoff = datetime.utcnow() - timedelta(hours=time_window_hours)

        recent_flash_news = session.query(FlashNews).filter(
            FlashNews.created_at >= cutoff,
            FlashNews.id != flash_news.id,  # Exclude self
            FlashNews.embedding.isnot(None)
        ).all()

        if not recent_flash_news:
            return 1.0  # First of the day, maximum novelty

        # Calculate cosine similarity with each recent flash news
        from sklearn.metrics.pairwise import cosine_similarity

        this_emb = np.array(flash_news.embedding).reshape(1, -1)

        similarities = []
        for other in recent_flash_news:
            other_emb = np.array(other.embedding).reshape(1, -1)
            sim = float(cosine_similarity(this_emb, other_emb)[0, 0])
            similarities.append(sim)

        # Diversity = 1 - max_similarity
        # If very similar to recent news → low diversity
        max_sim = max(similarities)
        diversity_score = 1 - max_sim

        # BOOST if completely unique (max_sim < 0.3)
        if max_sim < 0.3:
            diversity_score = 1.0

        return diversity_score

    def _calculate_source_authority(self, flash_news: FlashNews) -> float:
        """
        Calculate score based on source authority/trustworthiness.
        """
        article = flash_news.cluster.article
        source = article.source

        if not source or not hasattr(source, 'authority_score'):
            return 0.5  # Neutral default

        return source.authority_score

    def _score_to_priority(self, score: float) -> str:
        """
        Convert numerical score to priority tier.

        Tiers:
        - critical: >= 0.75 - Publish immediately
        - high: >= 0.55 - Publish in next batch
        - medium: >= 0.35 - Consider if space available
        - low: < 0.35 - Don't publish, archive
        """
        if score >= 0.75:
            return 'critical'
        elif score >= 0.55:
            return 'high'
        elif score >= 0.35:
            return 'medium'
        else:
            return 'low'


def calculate_flash_news_relevance(
    db: Database,
    session: Session,
    flash_news_id: Optional[int] = None,
    recalculate_all: bool = False,
    time_window_hours: int = 24,
    custom_weights: Optional[Dict[str, float]] = None
) -> Dict:
    """
    Calculate relevance scores for flash news.

    Args:
        db: Database instance
        session: SQLAlchemy session
        flash_news_id: Optional, calculate for specific flash news only
        recalculate_all: If True, recalculate all flash news (even if already calculated)
        time_window_hours: Time window for topic diversity calculation
        custom_weights: Optional custom weights for components

    Returns:
        Dict with statistics:
            - total_flash_news: Number of flash news processed
            - updated: Number updated
            - skipped: Number skipped (already calculated)
            - by_priority: Breakdown by priority tier
    """
    start_time = datetime.utcnow()

    # Initialize calculator
    calculator = FlashNewsRelevanceCalculator(weights=custom_weights)

    # Query flash news to process
    query = session.query(FlashNews)

    if flash_news_id:
        # Calculate for specific flash news
        query = query.filter(FlashNews.id == flash_news_id)
    elif not recalculate_all:
        # Only calculate for flash news without scores
        query = query.filter(FlashNews.relevance_calculated_at.is_(None))

    flash_news_list = query.all()

    if not flash_news_list:
        return {
            'total_flash_news': 0,
            'updated': 0,
            'skipped': 0,
            'by_priority': {},
            'processing_time': 0.0
        }

    # Process each flash news
    updated = 0
    by_priority = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}

    for fn in flash_news_list:
        result = calculator.calculate_relevance(fn, session)

        # Update flash news
        fn.relevance_score = result['score']
        fn.relevance_components = result['components']
        fn.priority = result['priority']
        fn.relevance_calculated_at = result['calculated_at']

        updated += 1
        by_priority[result['priority']] += 1

    session.commit()

    # Calculate statistics
    end_time = datetime.utcnow()
    processing_time = (end_time - start_time).total_seconds()

    return {
        'total_flash_news': len(flash_news_list),
        'updated': updated,
        'skipped': 0,  # Not used currently
        'by_priority': by_priority,
        'processing_time': processing_time
    }


def select_flash_news_for_newsletter(
    session: Session,
    min_count: int = 1,
    max_count: int = 5,
    low_score: float = 0.55,
    high_score: float = 0.75,
    max_per_source: int = 2,
    mark_as_published: bool = False
) -> list:
    """
    Select flash news for publication in newsletter with flexible criteria.

    Selection rules:
    1. CRITICAL (score >= high_score): Always publish, even if exceeds max_count
    2. NORMAL (low_score <= score < high_score): Publish if space available (min_count to max_count)
    3. FILLER (score < low_score): Only publish if needed to reach min_count
    4. Diversification: No more than max_per_source per source
    5. Not already published (published=0)

    Logic:
    - Guarantee min_count flash news (even if below low_score)
    - Respect max_count UNLESS all exceed high_score
    - Prioritize high scores, then normal scores, then fillers

    Args:
        session: SQLAlchemy session
        min_count: Minimum number of flash news to publish (default: 1)
        max_count: Maximum number of flash news, unless all exceed high_score (default: 5)
        low_score: Minimum score for normal publication (default: 0.55)
        high_score: Score threshold to bypass max_count limit (default: 0.75)
        max_per_source: Maximum flash news per source (default: 2)
        mark_as_published: If True, mark selected flash news as published

    Returns:
        List of FlashNews objects selected for publication
    """
    # Get all unpublished flash news ordered by score
    all_candidates = session.query(FlashNews).filter(
        FlashNews.published == 0,
        FlashNews.relevance_score.isnot(None)
    ).order_by(
        FlashNews.relevance_score.desc()
    ).all()

    if not all_candidates:
        return []

    # Categorize candidates
    critical = []  # score >= high_score
    normal = []    # low_score <= score < high_score
    filler = []    # score < low_score

    for fn in all_candidates:
        if fn.relevance_score >= high_score:
            critical.append(fn)
        elif fn.relevance_score >= low_score:
            normal.append(fn)
        else:
            filler.append(fn)

    # Selection with diversification
    selected = []
    source_counts = {}

    def can_add(fn):
        """Check if flash news can be added (respects source diversification)"""
        source_id = fn.cluster.article.source_id
        return source_counts.get(source_id, 0) < max_per_source

    def add_flash_news(fn):
        """Add flash news to selected and update source counts"""
        selected.append(fn)
        source_id = fn.cluster.article.source_id
        source_counts[source_id] = source_counts.get(source_id, 0) + 1

    # PHASE 1: Add all CRITICAL (bypass max_count)
    for fn in critical:
        if can_add(fn):
            add_flash_news(fn)

    # PHASE 2: Add NORMAL up to max_count
    for fn in normal:
        if len(selected) >= max_count:
            break
        if can_add(fn):
            add_flash_news(fn)

    # PHASE 3: Add FILLER to reach min_count (if needed)
    if len(selected) < min_count:
        for fn in filler:
            if len(selected) >= min_count:
                break
            if can_add(fn):
                add_flash_news(fn)

    # Mark as published if requested
    if mark_as_published:
        for fn in selected:
            fn.published = 1
            fn.updated_at = datetime.utcnow()
        session.commit()

    return selected
