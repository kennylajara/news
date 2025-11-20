import sqlite3
from collections import defaultdict


def load_data_by_categories(db_path):
    """Organiza noticias por categoría y subcategoría desde la base de datos de corpus"""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("""
        SELECT title, content, category, subcategory
        FROM articles
        WHERE category IS NOT NULL
    """)

    # Estructura: {categoria: {subcategoria: [(titulo, body), ...]}}
    hierarchy = defaultdict(lambda: defaultdict(list))
    all_categories = set()

    for title, content, category, subcategory in cursor:
        # Si no hay subcategoría, usar "General" como default
        subcat = subcategory if subcategory else "General"
        hierarchy[category][subcat].append((title, content))
        all_categories.add(category)

    conn.close()
    return hierarchy, list(all_categories)
