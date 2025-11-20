import os
import sys

# Add parent directory to path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ai.training.loaders.category_loader import load_data_by_categories


def analyze_dataset_distribution(db_path):
    """Ver la distribución de tus datos"""
    if not os.path.exists(db_path):
        print(f"❌ Error: Database not found at {db_path}")
        print(f"   Run 'uv run news export corpus' first to create the corpus database")
        return

    hierarchy, _ = load_data_by_categories(db_path)

    if not hierarchy:
        print("❌ No se encontraron artículos con categorías en la base de datos")
        print("   Asegúrate de haber exportado artículos con: uv run news export corpus")
        return

    print("=== Distribución de datos ===\n")

    for cat, subcats in sorted(hierarchy.items()):
        total = sum(len(noticias) for noticias in subcats.values())
        print(f"\n📁 {cat}: {total} noticias")

        for subcat, noticias in sorted(subcats.items()):
            print(f"  ├─ {subcat}: {len(noticias)} noticias")

    # Calcular pares potenciales
    total_noticias = sum(
        len(noticias)
        for subcats in hierarchy.values()
        for noticias in subcats.values()
    )

    print(f"\n📊 Total noticias: {total_noticias}")
    print(f"📊 Pares potenciales (aprox): {total_noticias * 6}")  # 6 pares por noticia


if __name__ == '__main__':
    # Use correct path relative to project root
    db_path = os.path.join(os.path.dirname(__file__), '..', 'corpus', 'raw_news.db')
    db_path = os.path.abspath(db_path)

    print(f"📂 Loading database from: {db_path}\n")
    analyze_dataset_distribution(db_path)
