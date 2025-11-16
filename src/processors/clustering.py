"""
Semantic clustering of article sentences.
Adapted for Spanish news articles with separate title embedding.
"""

import re
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import normalize
import umap
import hdbscan
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict

# Config
EMB_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
POS_WEIGHT = 0.15

# Load model globally (singleton pattern for performance)
_model = None


def get_embedding_model():
    """Get or initialize the sentence transformer model."""
    global _model
    if _model is None:
        print(f"Loading sentence embedding model: {EMB_MODEL}...")
        _model = SentenceTransformer(EMB_MODEL)
    return _model


def extract_sentences(markdown_content):
    """
    Extract sentences from Markdown content.
    Handles Spanish punctuation and Markdown formatting.
    Excludes markdown headers (subtitles) from clustering.

    Args:
        markdown_content: String with Markdown-formatted article content

    Returns:
        List of sentence strings
    """
    # Remove Markdown formatting
    # Remove header lines completely (including the text)
    text = re.sub(r'^#+\s+.*$', '', markdown_content, flags=re.MULTILINE)
    # Remove bold/italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Remove links but keep text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Remove list markers
    text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)

    # Split by sentence-ending punctuation (Spanish aware)
    # Include ¿? and ¡! patterns
    sentences = re.split(r'(?<=[.!?])\s+', text)

    # Clean and filter sentences
    cleaned = []
    for s in sentences:
        s = s.strip()
        # Skip very short sentences (<5 words) or empty
        if len(s) > 0 and len(s.split()) >= 5:
            # Normalize whitespace
            s = ' '.join(s.split())
            cleaned.append(s)

    return cleaned


def make_embeddings(sentences, model_name=EMB_MODEL):
    """
    Generate embeddings for sentences.

    Args:
        sentences: List of sentence strings
        model_name: Name of sentence-transformers model to use

    Returns:
        numpy array of shape (N, embedding_dim) with L2 normalized embeddings
    """
    model = get_embedding_model()
    embs = model.encode(sentences, show_progress_bar=False, convert_to_numpy=True)
    embs = normalize(embs, norm='l2')
    return embs


def add_position_feature(embs, positions, pos_weight=POS_WEIGHT):
    """
    Add position feature to embeddings.

    Args:
        embs: numpy array of embeddings (N, D)
        positions: array of positions (0..N-1)
        pos_weight: weight for position feature

    Returns:
        numpy array with position column appended (N, D+1)
    """
    pos_norm = (np.array(positions) - np.min(positions)) / (np.ptp(positions) if np.ptp(positions) > 0 else 1)
    pos_col = (pos_norm[:, None] * pos_weight)
    return np.hstack([embs, pos_col])


def cluster_article(sentences, title_embedding):
    """
    Cluster sentences from an article using semantic similarity.
    Title embedding is used separately for lead comparison.

    Args:
        sentences: List of sentence strings (WITHOUT title)
        title_embedding: numpy array (1, D) - embedding of the article title

    Returns:
        tuple: (cluster_infos, labels, probs)
            - cluster_infos: list of dicts with cluster metadata
            - labels: array of cluster labels for each sentence
            - probs: array of membership probabilities
    """
    N = len(sentences)
    if N == 0:
        return [], np.array([]), np.array([])

    positions = list(range(N))
    embs = make_embeddings(sentences)
    embs_pos = add_position_feature(embs, positions)

    # UMAP dimensionality reduction
    n_components = 16 if N >= 40 else 8
    reducer = umap.UMAP(n_neighbors=min(15, N-1), n_components=min(n_components, N-1),
                       metric='cosine', random_state=42)
    X_reduced = reducer.fit_transform(embs_pos)

    # HDBSCAN params
    min_cluster_size = max(2, int(0.05 * N))
    min_samples = max(1, min_cluster_size // 2)

    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size,
                                min_samples=min_samples,
                                metric='euclidean',
                                cluster_selection_method='eom')
    labels = clusterer.fit_predict(X_reduced)
    probs = getattr(clusterer, 'probabilities_', np.ones_like(labels, dtype=float))

    # Build clusters
    clusters = defaultdict(list)
    for i, lab in enumerate(labels):
        clusters[lab].append(i)

    # Article-level embeddings for scoring
    article_emb = np.mean(embs, axis=0, keepdims=True)  # centroid of all sentences

    # Compute cluster info and scores
    cluster_infos = []
    for lab, idxs in clusters.items():
        idxs_arr = np.array(idxs)
        size = len(idxs)
        size_norm = size / N
        centroid = np.mean(embs[idxs_arr], axis=0, keepdims=True)

        # Use title embedding for lead similarity
        sim_to_lead = float(cosine_similarity(centroid, title_embedding)[0, 0])
        sim_to_article = float(cosine_similarity(centroid, article_emb)[0, 0])
        avg_pos = np.mean(idxs_arr) / max(1, N-1)  # 0..1
        position_score = 1.0 - avg_pos  # earlier = higher
        cohesion = float(np.mean(probs[idxs_arr])) if probs is not None else 1.0

        # normalize similarities from [-1,1] to [0,1]
        sim_to_lead_norm = (sim_to_lead + 1) / 2
        sim_to_article_norm = (sim_to_article + 1) / 2

        # importance scoring weights
        w_size, w_sim_lead, w_centroid_sim, w_position, w_cohesion = 0.35, 0.30, 0.20, 0.10, 0.05
        score = (w_size * size_norm +
                 w_sim_lead * sim_to_lead_norm +
                 w_centroid_sim * sim_to_article_norm +
                 w_position * position_score +
                 w_cohesion * cohesion)

        cluster_infos.append({
            "label": lab,
            "indices": idxs,
            "size": size,
            "score": score,
            "centroid": centroid.tolist()[0],  # Convert to list for JSON storage
            "sim_to_lead": sim_to_lead,
            "sim_to_article": sim_to_article,
            "position_score": position_score,
            "cohesion": cohesion
        })

    # classify clusters
    for info in cluster_infos:
        lab = info["label"]
        s = info["score"]
        if lab == -1:  # noise cluster
            info["category"] = "filler" if s < 0.35 else "secondary"
        else:
            if s >= 0.60:
                info["category"] = "core"
            elif s >= 0.30:
                info["category"] = "secondary"
            else:
                info["category"] = "filler"

    # sort by score (descending)
    cluster_infos = sorted(cluster_infos, key=lambda x: x["score"], reverse=True)
    return cluster_infos, labels, probs
