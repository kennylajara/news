"""
Entity ranking using PageRank algorithm.

Calculates global relevance scores for entities based on their co-occurrence
in articles, weighted by local relevance scores. The intuition is that entities
mentioned together in articles form a weighted directed graph, where:

- Edge weight from B → A = relevance_local(A) in that article
- This means you "link stronger" to more central figures in each article

Calculates global relevance for multiple entity types:
PERSON, ORG, FAC, GPE, LOC, EVENT, WORK_OF_ART, LAW, LANGUAGE, DATE
"""

import numpy as np
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Set, Tuple, Optional
from db.models import EntityType


class EntityRankCalculator:
    """Calculate global entity relevance using PageRank algorithm."""

    # Entity types to calculate global relevance for
    RANKED_TYPES = {
        EntityType.PERSON,
        EntityType.ORG,
        EntityType.FAC,
        EntityType.GPE,
        EntityType.LOC,
        EntityType.EVENT,
        EntityType.WORK_OF_ART,
        EntityType.LAW,
        EntityType.LANGUAGE,
        EntityType.DATE
    }

    def __init__(
        self,
        damping: float = 0.85,
        max_iter: int = 1000,
        tol: float = 1e-6,
        min_relevance_threshold: float = 0.3,
        time_decay_days: Optional[int] = None,
        timeout_seconds: float = 30.0,
        initial_scores: Optional[Dict[str, float]] = None
    ):
        """
        Initialize PageRank calculator.

        Args:
            damping: Damping factor (0-1). Standard is 0.85.
            max_iter: Maximum iterations for convergence (default: 1000).
            tol: Convergence tolerance.
            min_relevance_threshold: Ignore co-occurrences where both entities
                have relevance below this threshold (reduces noise).
            time_decay_days: If set, apply exponential decay to older articles.
                Articles older than this get less weight.
            timeout_seconds: Graceful timeout in seconds (default: 30.0).
                If exceeded, stops iteration and returns current state.
            initial_scores: Optional dict of entity -> previous score for warm start.
                New entities not in dict will be initialized to midpoint of existing scores.
        """
        self.damping = damping
        self.max_iter = max_iter
        self.tol = tol
        self.min_relevance_threshold = min_relevance_threshold
        self.time_decay_days = time_decay_days
        self.timeout_seconds = timeout_seconds
        self.initial_scores = initial_scores or {}

    def build_graph(
        self,
        articles: List[Dict]
    ) -> Tuple[Dict[str, Dict[str, float]], Set[str]]:
        """
        Build weighted directed graph from article co-occurrences.

        Args:
            articles: List of dicts with keys:
                - entities: List[Tuple[str, EntityType]] - (name, entity_type)
                - relevances: List[float] - Local relevance scores
                - published_date: Optional[datetime] - Article date

        Returns:
            Tuple of (graph, all_entities):
                - graph: Dict mapping entity -> {target_entity -> weight}
                - all_entities: Set of all entity names
        """
        graph = defaultdict(lambda: defaultdict(float))
        all_entities = set()

        for article in articles:
            entities = article['entities']  # List of (name, type) tuples
            relevances = article['relevances']
            published_date = article.get('published_date')

            # Filter to only ranked entity types
            filtered = [
                (name, rel) for (name, etype), rel in zip(entities, relevances)
                if etype in self.RANKED_TYPES
            ]

            if len(filtered) < 2:
                # Need at least 2 entities to create edges
                continue

            entity_names = [name for name, _ in filtered]
            entity_relevances = [rel for _, rel in filtered]

            # Calculate time weight if applicable
            time_weight = 1.0
            if self.time_decay_days and published_date:
                days_old = (datetime.utcnow() - published_date).days
                if days_old > 0:
                    # Exponential decay
                    time_weight = np.exp(-days_old / self.time_decay_days)

            # Document normalization factor (always normalize)
            doc_factor = 1.0 / len(entity_names)

            # Build edges: each entity points to all others
            for i, entity_from in enumerate(entity_names):
                all_entities.add(entity_from)

                for j, entity_to in enumerate(entity_names):
                    if i == j:
                        continue

                    # Apply relevance threshold
                    if (entity_relevances[i] < self.min_relevance_threshold and
                        entity_relevances[j] < self.min_relevance_threshold):
                        continue

                    # Edge weight = relevance of target entity
                    # (you link stronger to more important entities)
                    weight = entity_relevances[j] * doc_factor * time_weight

                    graph[entity_from][entity_to] += weight

        return graph, all_entities

    def calculate_pagerank(
        self,
        articles: List[Dict]
    ) -> Tuple[Dict[str, float], Dict[str, float], int]:
        """
        Calculate PageRank scores for all entities.

        Args:
            articles: List of article dicts (see build_graph for format)

        Returns:
            Tuple of (raw_scores, normalized_scores, iterations):
                - raw_scores: Dict mapping entity name -> raw PageRank score
                - normalized_scores: Dict mapping entity name -> normalized score (0.0-1.0)
                - iterations: Number of iterations until convergence
        """
        graph, entities = self.build_graph(articles)

        if not entities:
            return {}, {}, 0

        entities = sorted(entities)  # Consistent ordering
        n = len(entities)

        # Map entities to indices
        entity_to_idx = {e: i for i, e in enumerate(entities)}

        # Build weighted adjacency matrix
        M = np.zeros((n, n))

        for entity_from, targets in graph.items():
            idx_from = entity_to_idx[entity_from]
            total_weight = sum(targets.values())

            if total_weight > 0:
                for entity_to, weight in targets.items():
                    idx_to = entity_to_idx[entity_to]
                    # Normalize by total outgoing weight
                    M[idx_to, idx_from] = weight / total_weight

        # Handle dangling nodes (entities with no outgoing edges)
        dangling_mask = (M.sum(axis=0) == 0)
        dangling_indices = np.where(dangling_mask)[0]

        # Calculate midpoint for new entities
        if not self.initial_scores:
            midpoint = 1.0 / n  # Default if no previous scores
        else:
            scores_array = np.array(list(self.initial_scores.values()))
            if len(scores_array) > 0:
                midpoint = (scores_array.max() + scores_array.min()) / 2.0

        # Initialize PageRank vector with warm start if available
        pr = np.zeros(n)
        for i, entity in enumerate(entities):
            if entity in self.initial_scores:
                pr[i] = self.initial_scores[entity]
            else:
                # New entities get midpoint for faster convergence
                pr[i] = midpoint

        # Normalize initial vector
        if pr.sum() > 0:
            pr = pr / pr.sum()
        else:
            pr = np.ones(n) / n

        # PageRank iteration with graceful timeout
        iterations = 0
        start_time = time.time()

        for iteration in range(self.max_iter):
            iterations = iteration + 1

            # Contribution from dangling nodes (distributed uniformly)
            dangling_contrib = 0.0
            if len(dangling_indices) > 0:
                dangling_contrib = self.damping * pr[dangling_indices].sum() / n

            # Standard PageRank formula
            pr_new = (1 - self.damping) / n + self.damping * (M @ pr) + dangling_contrib

            # Normalize (ensures sum = 1.0)
            pr_new = pr_new / pr_new.sum()

            # Check convergence
            if np.abs(pr_new - pr).sum() < self.tol:
                break

            pr = pr_new

            # Graceful timeout check (doesn't raise error, just stops iterating)
            elapsed_time = time.time() - start_time
            if elapsed_time >= self.timeout_seconds:
                break

        # Min-max normalization with NumPy (more efficient than Python)
        pr_min = pr.min()
        pr_max = pr.max()

        if pr_max - pr_min > 0:
            pr_normalized = (pr - pr_min) / (pr_max - pr_min)
        else:
            # All scores are the same, set all to 1.0
            pr_normalized = np.ones(n)

        # Single conversion to Python dicts
        raw_scores = {entity: float(pr[idx]) for entity, idx in entity_to_idx.items()}
        normalized_scores = {entity: float(pr_normalized[idx]) for entity, idx in entity_to_idx.items()}

        return raw_scores, normalized_scores, iterations

    def calculate_complementary_metrics(
        self,
        articles: List[Dict]
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate additional metrics for entities.

        Returns dict with keys:
            - article_count: Number of articles entity appears in
            - avg_local_relevance: Average local relevance across articles
            - total_local_relevance: Sum of all local relevances
            - diversity: Number of unique entities co-occurring with
        """
        metrics = defaultdict(lambda: {
            'article_count': 0,
            'total_local_relevance': 0.0,
            'co_occurrences': set()
        })

        for article in articles:
            entities = article['entities']  # List of (name, type) tuples
            relevances = article['relevances']

            # Filter to ranked types
            filtered = [
                (name, rel) for (name, etype), rel in zip(entities, relevances)
                if etype in self.RANKED_TYPES
            ]

            entity_names = [name for name, _ in filtered]
            entity_relevances = [rel for _, rel in filtered]

            for i, entity_name in enumerate(entity_names):
                metrics[entity_name]['article_count'] += 1
                metrics[entity_name]['total_local_relevance'] += entity_relevances[i]

                # Track co-occurrences
                for j, other_entity in enumerate(entity_names):
                    if i != j:
                        metrics[entity_name]['co_occurrences'].add(other_entity)

        # Calculate averages and diversity
        result = {}
        for entity, m in metrics.items():
            freq = m['article_count']
            result[entity] = {
                'article_count': freq,
                'avg_local_relevance': m['total_local_relevance'] / freq if freq > 0 else 0.0,
                'total_local_relevance': m['total_local_relevance'],
                'diversity': len(m['co_occurrences'])
            }

        return result
