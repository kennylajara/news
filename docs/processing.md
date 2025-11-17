# Procesamiento de Artículos

## Introducción

El sistema de procesamiento por lotes permite ejecutar diferentes tipos de procesamiento sobre artículos de forma eficiente y trazable.

## Tipos de Procesamiento

### Enriquecimiento de Artículos (`enrich_article`)

Proceso base que incluye clustering semántico y extracción de entidades nombradas (NER). **No incluye llamadas a OpenAI**.

**Características**:
- **Clustering semántico** de oraciones con clasificación (core, secondary, filler)
- **NER con spaCy**: Modelo `es_core_news_sm` (español), 18 tipos de entidades
- **Relevancia ajustada por clusters**: Entidades en clusters core reciben boost (1.3x)
- Asocia entidades a artículos con conteo de menciones
- Calcula relevancia local (ver sección "Cálculo de Relevancia")
- Actualiza contador global de artículos por entidad
- Guarda logs detallados del procesamiento
- **Performance**: ~7-8 segundos por artículo (sin llamadas API)

### Generación de Flash News (`generate_flash_news`)

Proceso independiente que genera resúmenes narrativos desde clusters CORE usando OpenAI. **Requiere que los artículos ya estén enriquecidos** (con clustering completado).

**Características**:
- **Generación con LLM**: Usa OpenAI Structured Outputs (GPT-4/5)
- **Embeddings automáticos** para resúmenes y búsqueda semántica
- **Idempotente**: Detecta y salta clusters que ya tienen flash news
- **Manejo robusto de errores**: Fallas individuales no afectan otros clusters
- **Stats detalladas**: core_clusters_found, flash_news_generated, flash_news_skipped
- **Performance**: ~10-15 segundos por cluster (según modelo de OpenAI)

## Comandos CLI

### Iniciar Procesamiento

Crea y ejecuta un batch de procesamiento para artículos de un dominio.

```bash
uv run news process start -d <dominio> -t <tipo> -s <tamaño>
```

**Parámetros**:
- `-d, --domain`: Dominio a procesar (requerido)
- `-t, --type`: Tipo de procesamiento (requerido)
  - `enrich_article`: Clustering + NER (sin OpenAI)
  - `generate_flash_news`: Generación de flash news con LLM
- `-s, --size`: Tamaño del batch (default: 10)

**Ejemplos**:
```bash
# Paso 1: Enriquecimiento base (clustering + NER)
uv run news process start -d diariolibre.com -t enrich_article -s 10

# Paso 2: Generación de flash news (OpenAI)
uv run news process start -d diariolibre.com -t generate_flash_news -s 10
```

### Listar Batches

Muestra todos los batches de procesamiento con opciones de filtrado.

```bash
uv run news process list [opciones]
```

**Parámetros opcionales**:
- `-l, --limit`: Número de batches a mostrar (default: 20)
- `-s, --status`: Filtrar por estado (pending, processing, completed, failed)
- `-d, --domain`: Filtrar por dominio

**Ejemplos**:
```bash
# Listar últimos 20 batches
uv run news process list

# Listar batches completados
uv run news process list --status completed

# Listar batches de un dominio
uv run news process list --domain diariolibre.com

# Combinar filtros
uv run news process list --domain diariolibre.com --status failed --limit 10
```

### Ver Detalles de Batch

Muestra información detallada sobre un batch específico.

```bash
uv run news process show <batch_id> [--item <item_id>]
```

**Ejemplos**:
```bash
# Ver resumen del batch
uv run news process show 1

# Ver logs detallados de un item específico
uv run news process show 1 --item 5
```

**Información mostrada**:
- Metadatos del batch (source, tipo, estado)
- Progreso (total, procesados, exitosos, fallidos)
- Estadísticas agregadas
- Tiempos de ejecución y duración
- Resumen de items por estado
- Primeros 5 items fallidos (si hay)

## Flujo de Procesamiento

### Proceso: `enrich_article`

1. **Selección de artículos**: Artículos con `enriched_at IS NULL`
2. **Creación de batch y items**: Transacción atómica en `processing_batches` y `batch_items`
3. **Procesamiento por artículo**:

   **FASE 1: Clustering Semántico**
   - Extrae oraciones del contenido (excluye headers markdown)
   - Genera embeddings con `paraphrase-multilingual-MiniLM-L12-v2`
   - Clustering con UMAP + HDBSCAN
   - Clasifica clusters en: core (≥0.60), secondary (0.30-0.60), filler (<0.30)
   - Guarda en `article_clusters` y `article_sentences`
   - Marca artículo como `cluster_enriched_at`

   **FASE 2: Named Entity Recognition**
   - Extrae entidades con spaCy desde título, subtítulo y contenido
   - Detecta 18 tipos de entidades (PERSON, ORG, GPE, etc.)
   - Cuenta menciones de cada entidad
   - Crea/actualiza registros en `named_entities`

   **FASE 2.1: Cluster Boost**
   - Aplica multiplicadores según presencia en clusters:
     - Cluster core: **1.3x**
     - Cluster secondary: **1.0x**
     - Resto (filler/sin cluster): **0.7x**

   **FASE 3: Normalización de Relevancia**
   - Calcula relevancia base (menciones/total)
   - Aplica bonos (título +50%, subtítulo +25%, posición, menciones extra)
   - Aplica cluster boost
   - Normaliza para que entidad más relevante = 1.0
   - Guarda en `article_entities` con menciones y relevancia

   **FASE 4: Finalización**
   - Marca artículo como enriquecido (`enriched_at`)
   - Actualiza batch item con logs y estadísticas
   - Commit a base de datos

4. **Finalización del batch**: Actualiza estadísticas agregadas

### Proceso: `generate_flash_news`

1. **Selección de artículos**: Artículos con `cluster_enriched_at IS NOT NULL` (ya tienen clusters)
2. **Creación de batch y items**: Transacción atómica
3. **Procesamiento por artículo**:

   **FASE 1: Obtención de Clusters CORE**
   - Query a `article_clusters` filtrando por `category = 'CORE'`
   - Si no hay clusters core, marca item como completado y continúa

   **FASE 2: Generación de Flash News por Cluster**
   - Para cada cluster core:
     - **Verificación de idempotencia**: Salta si ya existe flash news para ese cluster
     - **Obtención de oraciones**: Query a `article_sentences` ordenadas por índice
     - **Preparación de datos**: Diccionario con título, oraciones del cluster, score
     - **Llamada a LLM**:
       - Renderiza prompts Jinja2 (system + user)
       - Llama OpenAI API con Structured Outputs
       - Recibe resumen JSON (validado con Pydantic)
     - **Generación de embedding**: Embedding del resumen con mismo modelo que clustering
     - **Guardado**: Crea registro `FlashNews` (published=0)
   - **Manejo de errores**: Fallas en un cluster no afectan otros

   **FASE 3: Finalización**
   - Actualiza batch item con estadísticas:
     - `core_clusters_found`
     - `flash_news_generated`
     - `flash_news_skipped`
   - Commit a base de datos

4. **Finalización del batch**: Actualiza estadísticas agregadas

## Entidades Extraídas

Las entidades se clasifican en 18 tipos según las etiquetas de spaCy:

| Tipo | Descripción |
|------|-------------|
| PERSON | Personas, incluyendo ficticias |
| NORP | Nacionalidades, grupos religiosos o políticos |
| FAC | Edificios, aeropuertos, autopistas, puentes |
| ORG | Compañías, agencias, instituciones |
| GPE | Países, ciudades, estados |
| LOC | Ubicaciones no-GPE, cordilleras, cuerpos de agua |
| PRODUCT | Objetos, vehículos, alimentos |
| EVENT | Huracanes, batallas, guerras, eventos deportivos |
| WORK_OF_ART | Títulos de libros, canciones |
| LAW | Documentos convertidos en leyes |
| LANGUAGE | Idiomas nombrados |
| DATE | Fechas absolutas o relativas |
| TIME | Tiempos menores a un día |
| PERCENT | Porcentajes |
| MONEY | Valores monetarios |
| QUANTITY | Medidas de peso o distancia |
| ORDINAL | "primero", "segundo", etc. |
| CARDINAL | Numerales |

## Campos de Seguimiento

### ProcessingBatch

- `status`: pending, processing, completed, failed
- `total_items`: Total de artículos en el batch
- `processed_items`: Artículos procesados (exitosos + fallidos)
- `successful_items`: Artículos exitosos
- `failed_items`: Artículos fallidos
- `stats` (JSON): Estadísticas agregadas del batch
- `started_at`, `completed_at`: Timestamps de ejecución

### BatchItem

- `status`: pending, processing, completed, failed, skipped
- `logs` (TEXT): Logs detallados del procesamiento
- `stats` (JSON): Estadísticas del item individual
  - `entities_found`: Total de entidades encontradas
  - `entities_new`: Entidades nuevas creadas
  - `entities_existing`: Entidades existentes actualizadas
  - `processing_time`: Tiempo de procesamiento en segundos
- `error_message`: Mensaje de error si falló
- `started_at`, `completed_at`: Timestamps

## Métricas de Entidades

El sistema maneja dos niveles de métricas:

### Contador Global de Artículos (`named_entities.article_count`)

Campo INTEGER que cuenta en cuántos artículos aparece la entidad:
- Primera vez que se menciona (en cualquier artículo): `article_count = 1`
- Segunda vez (en otro artículo): `article_count = 2`
- Y así sucesivamente

Esto permite identificar las entidades más frecuentes del corpus completo.

### Menciones por Artículo (`article_entities.mentions`)

Campo INTEGER que cuenta cuántas veces aparece la entidad en un artículo específico.

**Ejemplo**:
- "Policía" aparece 3 veces en artículo A → `mentions = 3`
- "Policía" aparece 2 veces en artículo B → `mentions = 2`
- Resultado: `article_count = 2` (2 artículos)

## Cálculo de Relevancia

La relevancia (`article_entities.relevance`) es un score FLOAT que indica la importancia de una entidad dentro de un artículo específico.

### Fórmula

**Base Score** (en base 1):
```
base_score = menciones_de_esta_entidad / total_menciones_de_todas_las_entidades
```

**Ejemplo**:
- Artículo menciona: Alice (2), Bob (1), Charlie (1)
- Total menciones = 4
- Alice base_score = 2/4 = 0.5
- Bob base_score = 1/4 = 0.25
- Charlie base_score = 1/4 = 0.25

**Bonos** (sumados como porcentajes del base_score):

| Condición | Bono | Fórmula |
|-----------|------|---------|
| Aparece en título | +50% del base_score | `score += base_score * 0.5` |
| Aparece en subtítulo | +25% del base_score | `score += base_score * 0.25` |
| Primera mención en primer 20% del contenido | +30% del base_score | `score += base_score * 0.3` |
| Primera mención en primer 40% del contenido | +15% del base_score | `score += base_score * 0.15` |
| Más de 3 menciones | +10% del base_score por mención extra (cap +50%) | `score += base_score * (min(menciones-3, 5) * 0.1)` |

**Normalización**:
Después de calcular todos los scores, se normalizan para que la entidad más relevante del artículo tenga un score de 1.0:
```
normalization_factor = 1.0 / max_relevance
normalized_score = raw_score * normalization_factor
```

**Ejemplo completo**:
```
Artículo con: Alice (2 menciones), Bob (1), Charlie (1)
Total menciones = 4

Alice:
- base_score = 2/4 = 0.5
- Aparece en título → 0.5 + (0.5 * 0.5) = 0.75
- Primera mención en primer 20% → 0.75 + (0.5 * 0.3) = 0.9
- raw_score = 0.9

Bob:
- base_score = 1/4 = 0.25
- raw_score = 0.25

Charlie:
- base_score = 1/4 = 0.25
- raw_score = 0.25

Normalización (max = 0.9):
- Alice: 0.9 * (1.0/0.9) = 1.0
- Bob: 0.25 * (1.0/0.9) = 0.278
- Charlie: 0.25 * (1.0/0.9) = 0.278
```

## Acceso a Información

### A través de la CLI

La mayoría de consultas comunes están disponibles a través de comandos CLI. Ver [Referencia de Comandos](commands.md) para la documentación completa.

**Ejemplos:**
- Ver batches: `uv run news process list`
- Ver detalles de batch: `uv run news process show <batch_id>`
- Ver logs de item: `uv run news process show <batch_id> --item <item_id>`
- Ver flash news: `uv run news flash list`
- Ver detalles de flash news: `uv run news flash show <id>`
- Ver estadísticas de flash news: `uv run news flash stats`
- Ver entidades más relevantes: `uv run news entity list`
- Ver artículos enriquecidos: `uv run news article list --enriched`
- Ver artículos pendientes: `uv run news article list --pending-enrich`
- Ver entidades de artículo: `uv run news article show <id> --entities`
- Ver artículos que mencionan entidad: `uv run news entity show "<nombre>"`
- Ver estadísticas: `uv run news domain stats`

### Consultas SQL Avanzadas

Para análisis avanzados, puedes acceder directamente a la base de datos:

```bash
sqlite3 data/news.db
```

**Tendencias temporales de entidades**:
```sql
SELECT
    ne.name,
    ne.entity_type,
    DATE(a.published_date) as date,
    COUNT(*) as mentions_count,
    SUM(ae.mentions) as total_mentions
FROM article_entities ae
JOIN named_entities ne ON ae.entity_id = ne.id
JOIN articles a ON ae.article_id = a.id
WHERE a.published_date IS NOT NULL
GROUP BY ne.id, DATE(a.published_date)
ORDER BY date DESC, mentions_count DESC;
```

**Co-ocurrencia de entidades** (entidades que aparecen juntas):
```sql
SELECT
    ne1.name as entity1,
    ne2.name as entity2,
    COUNT(*) as co_occurrences
FROM article_entities ae1
JOIN article_entities ae2 ON ae1.article_id = ae2.article_id AND ae1.entity_id < ae2.entity_id
JOIN named_entities ne1 ON ae1.entity_id = ne1.id
JOIN named_entities ne2 ON ae2.entity_id = ne2.id
GROUP BY ae1.entity_id, ae2.entity_id
ORDER BY co_occurrences DESC
LIMIT 20;
```

**Entidades por tipo de artículo** (categoría):
```sql
SELECT
    a.category,
    ne.entity_type,
    COUNT(DISTINCT ne.id) as unique_entities,
    SUM(ae.mentions) as total_mentions
FROM articles a
JOIN article_entities ae ON a.id = ae.article_id
JOIN named_entities ne ON ae.entity_id = ne.id
WHERE a.category IS NOT NULL
GROUP BY a.category, ne.entity_type
ORDER BY a.category, total_mentions DESC;
```

**Performance de procesamiento por batch**:
```sql
SELECT
    pb.id,
    pb.source_id,
    s.domain,
    pb.total_items,
    pb.successful_items,
    pb.failed_items,
    (pb.successful_items * 100.0 / pb.total_items) as success_rate,
    (JULIANDAY(pb.completed_at) - JULIANDAY(pb.started_at)) * 86400 as duration_seconds,
    ((JULIANDAY(pb.completed_at) - JULIANDAY(pb.started_at)) * 86400) / pb.total_items as avg_seconds_per_item
FROM processing_batches pb
JOIN sources s ON pb.source_id = s.id
WHERE pb.completed_at IS NOT NULL
ORDER BY pb.created_at DESC;
```

## Flash News

### Descripción

Flash news son resúmenes narrativos concisos generados automáticamente desde los clusters semánticos identificados como "core" (núcleo) de los artículos. Cada flash news:

- Resume las ideas principales de un cluster core (2-3 oraciones)
- Es autocontenida y comprensible sin contexto adicional
- Usa tono periodístico profesional en español
- Incluye un embedding vectorial para búsqueda semántica
- Tiene estado publicado/no publicado

### Generación Automática

El proceso de generación usa **OpenAI Structured Outputs** con:

1. **Templates Jinja2 separados**:
   - `{task}_system_prompt.md.jinja` - Instrucciones para el LLM
   - `{task}_user_prompt.md.jinja` - Datos específicos del cluster

2. **Schema Pydantic** (`{task}.py`):
   - Valida la respuesta del LLM
   - Garantiza formato JSON correcto

3. **Wrapper genérico reutilizable** (`src/llm/openai_client.py`):
   - Función `openai_structured_output(task_name, data)`
   - Carga dinámicamente templates y schemas
   - Renderiza prompts con datos del cluster
   - Llama OpenAI API con validación estricta

### Configuración Requerida

Para usar la generación de flash news, necesitas configurar OpenAI API.

Ver **[README.md](../README.md)** sección "Instalación" para instrucciones completas de configuración de variables de entorno (`.env` file).

### Consultas SQL para Flash News

**Listar flash news no publicadas**:
```sql
SELECT
    fn.id,
    fn.summary,
    a.title as article_title,
    ac.score as cluster_score,
    fn.created_at
FROM flash_news fn
JOIN article_clusters ac ON fn.cluster_id = ac.id
JOIN articles a ON ac.article_id = a.id
WHERE fn.published = 0
ORDER BY fn.created_at DESC;
```

**Estadísticas de flash news por fuente**:
```sql
SELECT
    s.domain,
    COUNT(fn.id) as total_flash_news,
    SUM(fn.published) as published,
    COUNT(fn.id) - SUM(fn.published) as unpublished
FROM flash_news fn
JOIN article_clusters ac ON fn.cluster_id = ac.id
JOIN articles a ON ac.article_id = a.id
JOIN sources s ON a.source_id = s.id
GROUP BY s.domain
ORDER BY total_flash_news DESC;
```

**Flash news con embeddings para búsqueda**:
```sql
SELECT
    fn.id,
    fn.summary,
    LENGTH(fn.embedding) as embedding_size,
    a.title
FROM flash_news fn
JOIN article_clusters ac ON fn.cluster_id = ac.id
JOIN articles a ON ac.article_id = a.id
WHERE fn.embedding IS NOT NULL;
```

### Crear Nuevas Tareas LLM

Para agregar una nueva tarea de procesamiento con LLM:

1. **Crear schema Pydantic** (`src/llm/prompts/{task}.py`):
```python
from pydantic import BaseModel, Field

class StructuredOutput(BaseModel):
    campo1: str = Field(description="Descripción del campo")
    campo2: list[str] = Field(description="...")
```

2. **Crear prompt del sistema** (`src/llm/prompts/{task}_system_prompt.md.jinja`):
```jinja
Eres un experto en...

Directrices:
- Instrucción 1
- Instrucción 2
```

3. **Crear prompt del usuario** (`src/llm/prompts/{task}_user_prompt.md.jinja`):
```jinja
**Datos de entrada:**
{{ variable1 }}
{{ variable2 }}

Genera...
```

4. **Usar en código**:
```python
from llm.openai_client import openai_structured_output

data = {'variable1': 'valor', 'variable2': 'otro valor'}
result = openai_structured_output('nombre_de_tarea', data)
print(result.campo1)
```

