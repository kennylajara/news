# AI/ML Directory - News Embeddings & Training

Este directorio contiene todo lo relacionado con machine learning y entrenamiento de modelos de embeddings para el proyecto de noticias.

## 📁 Estructura del Directorio

```
ai/
├── README.md                    # Este archivo
├── corpus/                      # Base de datos de corpus (texto plano)
│   └── raw_news.db              # SQLite con artículos en texto plano
├── models/                      # Modelos entrenados
│   └── embeddings/              # Modelos de embeddings
│       └── news-embeddings-*-TIMESTAMP/
└── training/                    # Scripts de entrenamiento
    ├── README.md                # Documentación detallada
    ├── analysis.py              # Análisis de distribución del corpus
    ├── loaders/
    │   └── category_loader.py   # Carga datos por categoría/subcategoría
    └── embeddings/
        ├── simple.py            # Entrenamiento jerárquico simple
        └── controlled_ratios.py # Entrenamiento con ratios controlados
```

## 🎯 Propósito

Este directorio permite entrenar modelos de embeddings personalizados que entienden mejor el dominio específico de noticias en español. Los modelos aprenden a:

- Distinguir entre diferentes categorías de noticias (política, deportes, economía, etc.)
- Reconocer noticias relacionadas dentro de la misma categoría
- Generar representaciones vectoriales optimizadas para búsqueda y clustering

## 🚀 Quick Start

### 1. Exportar Corpus

Primero, exporta artículos desde la base de datos principal al corpus:

```bash
# Desde el root del proyecto
uv run news export corpus --limit 500
```

Esto crea `ai/corpus/raw_news.db` con artículos en texto plano, separando categorías y subcategorías.

### 2. Analizar Distribución

Verifica que tienes suficientes artículos y categorías:

```bash
python ai/training/analysis.py
```

**Recomendado**: Al menos 100+ artículos con 3+ categorías diferentes.

### 3. Entrenar Modelo

Elige una estrategia de entrenamiento:

```bash
# Opción 1: Entrenamiento simple (recomendado para empezar)
python ai/training/embeddings/simple.py

# Opción 2: Entrenamiento con ratios controlados (para optimizar)
python ai/training/embeddings/controlled_ratios.py
```

El modelo se guarda en `ai/models/embeddings/news-embeddings-*-TIMESTAMP/`

### 4. Usar Modelo

```python
from sentence_transformers import SentenceTransformer

# Cargar modelo entrenado
model = SentenceTransformer('ai/models/embeddings/news-embeddings-simple-20251120_141530')

# Generar embeddings
texts = [
    "Presidente anuncia nuevas medidas económicas",
    "Equipo nacional gana campeonato de béisbol"
]
embeddings = model.encode(texts)

# Calcular similitud semántica
from sentence_transformers.util import cos_sim
similarity = cos_sim(embeddings[0], embeddings[1])
print(f"Similitud: {similarity.item():.4f}")  # Cercano a 0 = diferentes categorías
```

## 📊 Corpus Database (`corpus/raw_news.db`)

Base de datos SQLite optimizada para entrenamiento de ML:

### Schema

```sql
CREATE TABLE articles (
    id INTEGER PRIMARY KEY,
    hash TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    source_domain TEXT NOT NULL,
    source_name TEXT NOT NULL,

    title TEXT NOT NULL,
    subtitle TEXT,
    author TEXT,
    published_date TEXT,
    location TEXT,
    content TEXT NOT NULL,          -- ⭐ Texto plano (sin markdown)
    category TEXT,                   -- ⭐ Categoría principal
    subcategory TEXT,                -- ⭐ Subcategoría

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    exported_at TEXT NOT NULL
);
```

### Características

- ✅ **Texto plano**: Sin formato markdown (sin `**negritas**`, sin `[links](url)`)
- ✅ **Categorías separadas**: `category` y `subcategory` en columnas distintas
- ✅ **Índices optimizados**: Para búsquedas rápidas por categoría, fuente, fecha
- ✅ **Actualización inteligente**: Detecta duplicados por hash

### Comandos Útiles

```bash
# Ver estadísticas del corpus
uv run news export stats

# Exportar más artículos
uv run news export corpus --domain diariolibre.com --limit 1000

# Verificar contenido directamente
sqlite3 ai/corpus/raw_news.db "SELECT category, subcategory, COUNT(*) FROM articles GROUP BY category, subcategory"
```

## 🤖 Modelos Entrenados (`models/embeddings/`)

Los modelos entrenados se guardan aquí con timestamps para versionado.

### Convención de Nombres

```
news-embeddings-simple-20251120_141530/
news-embeddings-balanced-20251120_153045/
```

- `simple`: Entrenamiento jerárquico simple
- `balanced`: Entrenamiento con ratios controlados
- Timestamp: `YYYYMMDD_HHMMSS`

### Contenido del Directorio del Modelo

Cada modelo contiene:
- `config.json` - Configuración del modelo
- `pytorch_model.bin` - Pesos del modelo
- `tokenizer_config.json` - Configuración del tokenizer
- `vocab.txt` - Vocabulario
- Otros archivos de sentence-transformers

### Cargar Modelo

```python
from sentence_transformers import SentenceTransformer

# Por path absoluto
model = SentenceTransformer('/home/user/news/ai/models/embeddings/news-embeddings-simple-20251120_141530')

# Por path relativo (desde root del proyecto)
model = SentenceTransformer('ai/models/embeddings/news-embeddings-simple-20251120_141530')
```

## 📚 Training Scripts (`training/`)

Scripts para entrenar modelos personalizados.

### `analysis.py`

Analiza la distribución de artículos por categoría/subcategoría.

**Uso**: `python ai/training/analysis.py`

**Output**:
```
📁 Política: 150 noticias
  ├─ Nacional: 80 noticias
  ├─ Internacional: 70 noticias

📁 Deportes: 100 noticias
  ├─ Béisbol: 50 noticias
  ├─ Fútbol: 30 noticias

📊 Total noticias: 250
📊 Pares potenciales (aprox): 1500
```

### `embeddings/simple.py`

Entrenamiento jerárquico simple con niveles de similaridad:
- Misma subcategoría: 0.95
- Misma categoría: 0.7
- Diferente categoría: 0.0
- Título-contenido: 1.0

**Uso**: `python ai/training/embeddings/simple.py`

### `embeddings/controlled_ratios.py`

Entrenamiento con control fino de ratios entre tipos de pares.

**Uso**: `python ai/training/embeddings/controlled_ratios.py`

**Ventaja**: Permite ajustar balance de pares positivos/negativos.

Ver [`training/README.md`](training/README.md) para documentación detallada.

## 🔧 Configuración Avanzada

### Cambiar Modelo Base

Edita los scripts de entrenamiento y cambia:

```python
base_model='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
```

Opciones recomendadas:
- `paraphrase-multilingual-MiniLM-L12-v2` (default, rápido, 118M params)
- `distiluse-base-multilingual-cased-v2` (más pequeño, 135M params)
- `paraphrase-multilingual-mpnet-base-v2` (más grande, mejor calidad, 278M params)

### Ajustar Hiperparámetros

```python
train_embeddings(
    db_path=db_path,
    output_dir=output_dir,
    base_model='...',
    epochs=4,           # Más epochs = mejor aprendizaje (pero riesgo overfitting)
    batch_size=16       # Más grande = más rápido (pero más memoria)
)
```

### GPU vs CPU

Los scripts detectan automáticamente CUDA. Para forzar CPU:

```python
import os
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
```

## 📈 Workflow Completo

```bash
# 1. Poblar base de datos principal desde caché
uv run news article fetch-cached --limit 500

# 2. Exportar al corpus (texto plano)
uv run news export corpus

# 3. Verificar distribución
python ai/training/analysis.py

# 4. Entrenar modelo
python ai/training/embeddings/simple.py

# 5. Verificar modelo guardado
ls -lh ai/models/embeddings/

# 6. Usar en tu aplicación
python -c "from sentence_transformers import SentenceTransformer; \
           model = SentenceTransformer('ai/models/embeddings/news-embeddings-simple-...'); \
           print(model.encode(['Test']))"
```

## 🐛 Troubleshooting

### "No training examples generated"
- **Causa**: Corpus vacío o sin categorías
- **Solución**: `uv run news export corpus`

### "Database not found"
- **Causa**: `ai/corpus/raw_news.db` no existe
- **Solución**: `uv run news export corpus`

### "Only X categories found"
- **Causa**: Pocas categorías para entrenamiento efectivo
- **Solución**: Exporta más artículos de diferentes fuentes

### "CUDA out of memory"
- **Causa**: Batch size muy grande para GPU
- **Solución**: Reduce `batch_size` a 8 o 4

### Modelo no mejora
- **Causa**: Datos muy similares o distribución desbalanceada
- **Solución**:
  - Verifica distribución con `analysis.py`
  - Exporta más artículos de categorías diferentes
  - Prueba `controlled_ratios.py` con ratios ajustados

## 📖 Recursos Adicionales

- [Sentence-Transformers Documentation](https://www.sbert.net/)
- [Training Overview](https://www.sbert.net/docs/training/overview.html)
- [Cosine Similarity Loss](https://www.sbert.net/docs/package_reference/losses.html#cosinesimilarityloss)

## 🎯 Casos de Uso

### 1. Búsqueda Semántica

```python
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer('ai/models/embeddings/news-embeddings-simple-...')

# Corpus de noticias
corpus = [
    "Presidente anuncia reforma tributaria",
    "Equipo nacional clasifica al mundial",
    "Nuevo presupuesto nacional aprobado"
]

# Query del usuario
query = "impuestos y economía"

# Generar embeddings
corpus_embeddings = model.encode(corpus)
query_embedding = model.encode(query)

# Buscar más similares
hits = util.semantic_search(query_embedding, corpus_embeddings, top_k=3)

for hit in hits[0]:
    print(f"{corpus[hit['corpus_id']]} (score: {hit['score']:.4f})")
```

### 2. Clustering de Noticias

```python
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans

model = SentenceTransformer('ai/models/embeddings/news-embeddings-simple-...')

# Artículos
articles = [...]
embeddings = model.encode(articles)

# Clustering
kmeans = KMeans(n_clusters=5)
clusters = kmeans.fit_predict(embeddings)

# Agrupar
from collections import defaultdict
groups = defaultdict(list)
for idx, cluster_id in enumerate(clusters):
    groups[cluster_id].append(articles[idx])
```

### 3. Deduplicación

```python
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer('ai/models/embeddings/news-embeddings-simple-...')

def find_duplicates(articles, threshold=0.85):
    embeddings = model.encode(articles)
    cos_sim = util.cos_sim(embeddings, embeddings)

    duplicates = []
    for i in range(len(articles)):
        for j in range(i+1, len(articles)):
            if cos_sim[i][j] > threshold:
                duplicates.append((i, j, cos_sim[i][j].item()))

    return duplicates
```

---

**Para documentación detallada de entrenamiento**, ver [`training/README.md`](training/README.md)
