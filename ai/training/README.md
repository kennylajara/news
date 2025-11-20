# Training Scripts for News Embeddings

Este directorio contiene scripts para entrenar modelos de embeddings personalizados en el corpus de noticias.

## Prerequisitos

1. **Exportar corpus**: Primero debes exportar artículos desde la base de datos principal al corpus:
   ```bash
   # Exportar todos los artículos
   uv run news export corpus

   # O exportar con filtros
   uv run news export corpus --domain diariolibre.com --limit 1000
   ```

2. **Verificar distribución**: Es importante tener artículos de múltiples categorías y subcategorías:
   ```bash
   python ai/training/analysis.py
   ```

   Esto mostrará:
   - Número de noticias por categoría/subcategoría
   - Total de pares de entrenamiento potenciales

## Scripts Disponibles

### 1. `analysis.py` - Análisis del Corpus

Muestra la distribución de artículos por categoría y subcategoría.

```bash
python ai/training/analysis.py
```

**Salida esperada:**
```
=== Distribución de datos ===

📁 Política: 150 noticias
  ├─ Nacional: 80 noticias
  ├─ Internacional: 70 noticias

📁 Deportes: 100 noticias
  ├─ Béisbol: 50 noticias
  ├─ Fútbol: 30 noticias
  ├─ Baloncesto: 20 noticias

📊 Total noticias: 250
📊 Pares potenciales (aprox): 1500
```

### 2. `embeddings/simple.py` - Entrenamiento Jerárquico Simple

Estrategia de entrenamiento con niveles de similaridad:
- **Misma subcategoría**: label = 0.95 (muy similares)
- **Misma categoría, diferente subcategoría**: label = 0.7 (relacionados)
- **Diferente categoría**: label = 0.0 (negativos)
- **Título-contenido original**: label = 1.0 (idénticos)

```bash
python ai/training/embeddings/simple.py
```

**Parámetros configurables** (editar en el script):
- `base_model`: Modelo base a fine-tunear (default: `paraphrase-multilingual-MiniLM-L12-v2`)
- `epochs`: Número de épocas (default: 4)
- `batch_size`: Tamaño de batch (default: 16)

**Output**: Modelo guardado en `ai/models/embeddings/news-embeddings-simple-TIMESTAMP/`

### 3. `embeddings/controlled_ratios.py` - Entrenamiento Balanceado

Similar al simple pero con control fino de ratios entre tipos de pares.

```bash
python ai/training/embeddings/controlled_ratios.py
```

**Parámetros configurables**:
- `ratio_same_subcat`: Pares de misma subcategoría por artículo (default: 2)
- `ratio_same_cat`: Pares de misma categoría por artículo (default: 1)
- `ratio_different_cat`: Pares de categorías diferentes por artículo (default: 2)

**Output**: Modelo guardado en `ai/models/embeddings/news-embeddings-balanced-TIMESTAMP/`

## Recomendaciones

### Corpus Mínimo Recomendado

Para un entrenamiento efectivo:
- **Mínimo**: 100+ artículos con al menos 3 categorías diferentes
- **Óptimo**: 500+ artículos con 5+ categorías, cada una con 2+ subcategorías
- **Ideal**: 1000+ artículos con distribución balanceada

### Ajuste de Hiperparámetros

**Si tienes pocas noticias** (<200):
```python
epochs=2-3
batch_size=8
```

**Si tienes bastantes noticias** (200-1000):
```python
epochs=4-5
batch_size=16
```

**Si tienes muchas noticias** (>1000):
```python
epochs=3-4
batch_size=32
```

### Selección de Estrategia

**Usa `simple.py` si:**
- Tienes distribución desbalanceada de categorías
- Quieres más control automático
- Primer experimento

**Usa `controlled_ratios.py` si:**
- Necesitas ajustar balance de pares positivos/negativos
- Ya probaste simple y quieres optimizar
- Tienes problemas de overfitting o underfitting

## Uso del Modelo Entrenado

Una vez entrenado, puedes usar el modelo así:

```python
from sentence_transformers import SentenceTransformer

# Cargar modelo entrenado
model = SentenceTransformer('ai/models/embeddings/news-embeddings-simple-TIMESTAMP')

# Generar embeddings
texts = [
    "Elecciones presidenciales en República Dominicana",
    "Resultados del juego de béisbol de anoche"
]
embeddings = model.encode(texts)

# Calcular similitud
from sentence_transformers.util import cos_sim
similarity = cos_sim(embeddings[0], embeddings[1])
print(f"Similitud: {similarity.item():.4f}")
```

## Troubleshooting

### Error: "No training examples generated"
- **Causa**: Corpus vacío o sin categorías
- **Solución**: Ejecuta `uv run news export corpus` primero

### Error: "Database not found"
- **Causa**: No existe el archivo `ai/corpus/raw_news.db`
- **Solución**: Ejecuta `uv run news export corpus`

### Advertencia: "Only X categories found"
- **Causa**: Pocas categorías para entrenamiento efectivo
- **Solución**: Exporta más artículos de diferentes fuentes/categorías

### Error: "CUDA out of memory"
- **Causa**: Batch size muy grande para tu GPU
- **Solución**: Reduce `batch_size` a 8 o 4

## Estructura de Archivos

```
ai/training/
├── README.md                    # Este archivo
├── analysis.py                  # Análisis del corpus
├── loaders/
│   └── category_loader.py       # Carga datos por categoría
└── embeddings/
    ├── simple.py                # Entrenamiento jerárquico simple
    └── controlled_ratios.py     # Entrenamiento balanceado

ai/corpus/
└── raw_news.db                  # Base de datos del corpus

ai/models/embeddings/
└── news-embeddings-*-TIMESTAMP/ # Modelos entrenados
```

## Workflow Completo

1. **Poblar base de datos principal**:
   ```bash
   uv run news article fetch-cached --limit 500
   ```

2. **Exportar corpus**:
   ```bash
   uv run news export corpus
   ```

3. **Analizar distribución**:
   ```bash
   python ai/training/analysis.py
   ```

4. **Entrenar modelo**:
   ```bash
   python ai/training/embeddings/simple.py
   ```

5. **Usar modelo en tu aplicación**:
   ```python
   from sentence_transformers import SentenceTransformer
   model = SentenceTransformer('ai/models/embeddings/news-embeddings-simple-20251120_141530')
   ```
