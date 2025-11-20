import os
import sys
import random
from datetime import datetime

# Add parent directory to path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader

from ai.training.loaders.category_loader import load_data_by_categories


def create_hierarchical_training_data(db_path):
    """
    Crea pares con diferentes niveles de similaridad:
    - Misma subcategoría: muy similares (0.95)
    - Misma categoría, diferente subcategoría: similares (0.7)
    - Diferente categoría: negativos (0.0)
    """
    hierarchy, all_categories = load_data_by_categories(db_path)
    train_examples = []

    for categoria, subcategorias in hierarchy.items():
        for subcategoria, noticias in subcategorias.items():

            # Solo procesar si hay suficientes noticias
            if len(noticias) < 2:
                continue

            for i, (titulo, body) in enumerate(noticias):
                titulo_clean = titulo.strip()
                body_clean = body.replace('\n', ' ')[:400]

                # 1. PAR POSITIVO FUERTE: Misma subcategoría
                if len(noticias) > 1:
                    # Seleccionar otra noticia de la MISMA subcategoría
                    similar_idx = random.choice([x for x in range(len(noticias)) if x != i])
                    similar_titulo, similar_body = noticias[similar_idx]

                    train_examples.append(InputExample(
                        texts=[
                            titulo_clean,
                            similar_titulo.strip() + ' ' + similar_body.replace('\n', ' ')[:300]
                        ],
                        label=0.95  # Muy similar
                    ))

                # 2. PAR POSITIVO MEDIO: Misma categoría, diferente subcategoría
                other_subcats = [s for s in subcategorias.keys() if s != subcategoria and len(subcategorias[s]) > 0]
                if other_subcats:
                    other_subcat = random.choice(other_subcats)
                    related = random.choice(subcategorias[other_subcat])

                    train_examples.append(InputExample(
                        texts=[
                            titulo_clean,
                            related[0].strip() + ' ' + related[1].replace('\n', ' ')[:300]
                        ],
                        label=0.7  # Relacionado pero no idéntico
                    ))

                # 3. PAR NEGATIVO FUERTE: Diferente categoría (100% garantizado diferente)
                different_categories = [c for c in all_categories if c != categoria]
                if different_categories:
                    neg_cat = random.choice(different_categories)
                    neg_subcat = random.choice(list(hierarchy[neg_cat].keys()))
                    negative = random.choice(hierarchy[neg_cat][neg_subcat])

                    train_examples.append(InputExample(
                        texts=[
                            titulo_clean,
                            negative[1].replace('\n', ' ')[:400]  # Solo body
                        ],
                        label=0.0  # Completamente diferente
                    ))

                # 4. Par título-body original
                train_examples.append(InputExample(
                    texts=[titulo_clean, body_clean],
                    label=1.0
                ))

    return train_examples


def train_embeddings(db_path, output_dir, base_model='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', epochs=4, batch_size=16):
    """
    Train embeddings model on news corpus.

    Args:
        db_path: Path to corpus database
        output_dir: Directory to save trained model
        base_model: Base sentence-transformers model to fine-tune
        epochs: Number of training epochs
        batch_size: Training batch size
    """
    print(f"🚀 Starting training with simple hierarchical strategy")
    print(f"📂 Database: {db_path}")
    print(f"🤖 Base model: {base_model}")
    print(f"📁 Output: {output_dir}\n")

    # Create training data
    print("📊 Creating training pairs...")
    train_examples = create_hierarchical_training_data(db_path)

    if not train_examples:
        print("❌ No training examples generated. Check database has articles with categories.")
        return

    print(f"✅ Generated {len(train_examples)} training pairs\n")

    # Load base model
    print(f"📥 Loading base model: {base_model}...")
    model = SentenceTransformer(base_model)

    # Create DataLoader
    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=batch_size)

    # Define loss function (Cosine Similarity Loss)
    train_loss = losses.CosineSimilarityLoss(model)

    # Create output directory with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    model_name = f"news-embeddings-simple-{timestamp}"
    full_output_path = os.path.join(output_dir, model_name)
    os.makedirs(full_output_path, exist_ok=True)

    # Train the model
    print(f"\n🎯 Training for {epochs} epochs...")
    print(f"   Batch size: {batch_size}")
    print(f"   Total steps: {len(train_dataloader) * epochs}\n")

    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=epochs,
        warmup_steps=int(len(train_dataloader) * 0.1),  # 10% warmup
        output_path=full_output_path,
        show_progress_bar=True
    )

    print(f"\n✅ Training complete!")
    print(f"📁 Model saved to: {full_output_path}")

    return full_output_path


if __name__ == '__main__':
    # Paths
    db_path = os.path.join(os.path.dirname(__file__), '../../corpus/raw_news.db')
    db_path = os.path.abspath(db_path)

    output_dir = os.path.join(os.path.dirname(__file__), '../../models/embeddings')
    output_dir = os.path.abspath(output_dir)

    # Check database exists
    if not os.path.exists(db_path):
        print(f"❌ Error: Database not found at {db_path}")
        print(f"   Run 'uv run news export corpus' first to create the corpus database")
        sys.exit(1)

    # Train model
    train_embeddings(
        db_path=db_path,
        output_dir=output_dir,
        base_model='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
        epochs=4,
        batch_size=16
    )
