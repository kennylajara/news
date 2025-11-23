# Procesamiento de Artículos

## Introducción

El sistema de procesamiento por lotes permite ejecutar diferentes tipos de procesamiento sobre artículos de forma eficiente y trazable.

## Tipos de Procesamiento

### Enriquecimiento de Artículos (`enrich_article`)

Proceso base que realiza clustering semántico de oraciones. La extracción de entidades se hace en `analyze_article` con OpenAI.

**Características**:
- **Clustering semántico** de oraciones con clasificación (core, secondary, filler)
- Genera embeddings con `paraphrase-multilingual-MiniLM-L12-v2`
- Clustering con UMAP + HDBSCAN
- Guarda en `article_clusters` y `article_sentences`
- Marca artículo como `cluster_enriched_at` y `enriched_at`
- Guarda logs detallados del procesamiento
- **Performance**: ~2-3 segundos por artículo

### Análisis Profundo de Artículos (`analyze_article`)

Proceso de análisis avanzado con OpenAI que extrae entidades nombradas y genera análisis detallado para el sistema de recomendaciones. **Requiere que los artículos ya estén enriquecidos** (con clustering completado).

**Características**:
- **Extracción de entidades con OpenAI**: Personas, organizaciones, ubicaciones, eventos, productos, NORP
- **Análisis profundo para recomendaciones**: Conceptos clave, relaciones semánticas, marcos narrativos
- **Structured Outputs**: Usa esquema Pydantic para garantizar formato consistente
- **Dos tablas generadas**:
  - `article_entities`: Entidades extraídas con menciones y relevancia
  - `article_analyses`: Análisis completo del artículo (tono, formato, audiencia, calidad, etc.)
- **Idempotente**: Detecta y salta artículos que ya tienen análisis
- **Manejo robusto de errores**: Fallas individuales no afectan otros artículos
- **Performance**: ~5-10 segundos por artículo (según modelo de OpenAI)

**Campos generados en `article_analyses`**:
- **Semántica**: `key_concepts`, `semantic_relations`
- **Narrativa**: `narrative_frames`, `editorial_tone`, `style_descriptors`
- **Controversia y sesgo**: `controversy_score` (0-100), `political_bias` (-100 a 100)
- **Calidad**: `quality_score` (0-100), `has_named_sources`, `has_data_or_statistics`, `has_multiple_perspectives`
- **Formato**: `content_format` (news/feature/opinion/analysis/interview/listicle), `temporal_relevance` (breaking/timely/evergreen)
- **Audiencia**: `audience_education`, `target_age_range`, `target_professions`, `required_interests`
- **Industria y geografía**: `relevant_industries`, `geographic_scope`, `cultural_context`
- **Diversidad**: `voices_represented`, `source_diversity_score` (0-100)

**Uso en sistema de recomendaciones**: Permite matching avanzado basado en:
- Tono editorial (neutral, crítico, celebratorio, etc.)
- Formato de contenido (noticias vs. análisis vs. opinión)
- Nivel educativo de la audiencia
- Industrias relevantes
- Calidad y sesgo político

### Generación de Flash News (`generate_flash_news`)

Proceso independiente que genera resúmenes narrativos desde clusters importantes usando OpenAI. **Requiere que los artículos ya estén enriquecidos** (con clustering completado).

**Lógica de selección de clusters**:
1. **Preferencia**: Clusters CORE (score >= 0.60, no ruido)
2. **Fallback**: Si no hay CORE, acepta clusters SECONDARY con score > 0.60 (incluyendo clusters de ruido con alta puntuación)

**Características**:
- **Generación con LLM**: Usa OpenAI Structured Outputs (GPT-4/5)
- **Embeddings automáticos** para resúmenes y búsqueda semántica
- **Idempotente**: Detecta y salta clusters que ya tienen flash news
- **Manejo robusto de errores**: Fallas individuales no afectan otros clusters
- **Stats detalladas**: core_clusters_found, high_score_secondary_clusters_found, flash_news_generated, flash_news_skipped
- **Performance**: ~10-15 segundos por cluster (según modelo de OpenAI)

**Nota**: Algunos artículos pueden tener un solo cluster semántico cohesivo que el algoritmo marca como "ruido" (label=-1) pero con score muy alto. El sistema ahora los aprovecha para generar flash news cuando no hay alternativas CORE.

## Comandos CLI

### Iniciar Procesamiento

Crea y ejecuta un batch de procesamiento para artículos de un dominio.

```bash
uv run news process start -d <dominio> -t <tipo> -s <tamaño>
```

**Parámetros**:
- `-d, --domain`: Dominio a procesar (requerido)
- `-t, --type`: Tipo de procesamiento (requerido)
  - `enrich_article`: Clustering semántico de oraciones (sin OpenAI)
  - `analyze_article`: Extracción de entidades + análisis profundo (con OpenAI)
  - `generate_flash_news`: Generación de flash news con LLM (con OpenAI)
- `-s, --size`: Tamaño del batch (default: 10)

**Ejemplos**:
```bash
# Paso 1: Enriquecimiento base (clustering semántico)
uv run news process start -d diariolibre.com -t enrich_article -s 10

# Paso 2: Análisis profundo con OpenAI (extracción de entidades + análisis)
uv run news process start -d diariolibre.com -t analyze_article -s 10

# Paso 3: Generación de flash news (OpenAI)
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

   **FASE 2: Finalización**
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

### Proceso: `analyze_article`

Genera análisis profundo de artículos usando OpenAI para extracción de entidades y análisis multi-dimensional.

**Prerrequisitos**: Artículos que NO tengan registro en `article_analyses` (evita re-análisis innecesario)

**Proceso**:

1. **Selección de artículos**: LEFT JOIN con `article_analyses WHERE article_analyses.id IS NULL`
2. **Creación de batch y items**: Transacción atómica
3. **Procesamiento por artículo**:

   **FASE 1: Extracción de Entidades con OpenAI**
   - Llama OpenAI API con artículo completo (título, subtítulo, contenido, fecha, categoría)
   - Extrae entidades de **6 tipos**:
     - PERSON (personas)
     - ORG (organizaciones, compañías, instituciones)
     - GPE (países, ciudades, estados)
     - EVENT (eventos, huracanes, batallas, etc.)
     - PRODUCT (productos, servicios)
     - NORP (nacionalidades, grupos religiosos/políticos)
   - Cuenta menciones por entidad
   - **Auto-aprueba** todas las entidades: `is_approved=1`, `last_review_type='ai-assisted'`
   - Guarda en `named_entities` (permite mismo nombre con diferentes tipos)
   - Guarda relación artículo-entidad en `article_entities` con:
     - `mentions`: Número de menciones en el artículo
     - `relevance`: Calculada como `min(mentions / 10.0, 1.0)`
     - `origin`: `AI_ANALYSIS`

   **FASE 2: Análisis Multi-dimensional**
   - Extrae 13 factores de análisis del artículo:
     - **Semántica**: Conceptos clave
     - **Narrativa**: Frames narrativos, tono editorial
     - **Controversia/sesgo**: Puntaje de controversia, sesgo político
     - **Formato**: Tipo de contenido (noticia, opinión, análisis, etc.)
     - **Temporal**: Relevancia temporal (breaking, recent, timeless, etc.)
     - **Audiencia**: Nivel educativo, rango de edad
     - **Industria**: Industrias relevantes
     - **Geográfico**: Alcance geográfico
   - Guarda en `article_analysis` (tabla separada con FK a article_id)

   **FASE 3: Finalización**
   - Actualiza batch item con logs y estadísticas
   - Commit a base de datos

4. **Finalización del batch**: Actualiza estadísticas agregadas

**Performance**: ~10-15 segundos por artículo (depende de latencia OpenAI)

## Entidades Extraídas

El sistema extrae entidades usando **OpenAI** durante el proceso `analyze_article`:

### Extracción con OpenAI (`analyze_article`)

Extrae **6 tipos** de entidades con análisis semántico profundo:

| Tipo | Descripción |
|------|-------------|
| PERSON | Personas, incluyendo ficticias |
| ORG | Compañías, agencias, instituciones |
| GPE | Países, ciudades, estados |
| EVENT | Huracanes, batallas, guerras, eventos deportivos |
| PRODUCT | Objetos, vehículos, alimentos, servicios |
| NORP | Nacionalidades, grupos religiosos o políticos |

- **EntityOrigin**: `AI_ANALYSIS`
- **Auto-aprobación**: Todas las entidades se crean con `is_approved=1`, `last_review_type='ai-assisted'`

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

---

## Sistema de Desambiguación de Entidades

### Introducción

El sistema de desambiguación resuelve el problema de entidades ambiguas extraídas por OpenAI, donde el mismo texto puede referirse a múltiples personas/organizaciones diferentes. Por ejemplo:
- **"Luis"** puede ser → Luis Abinader (presidente) o Luis Fonsi (cantante)
- **"PRM"** puede ser → Partido Revolucionario Moderno o Performance Rights Management

### Clasificaciones de Entidades

Cada entidad en `named_entities` tiene un campo `classified_as` con uno de estos valores:

#### 1. **CANONICAL** (default)
Entidad principal o "verdadera".

**Características**:
- Es la entidad de referencia
- No puede tener `canonical_refs` salientes (pero puede recibir referencias de otras entidades)
- Acumula la relevancia de sus aliases y entidades ambiguas

**Ejemplo**: "Luis Abinader", "Partido Revolucionario Moderno"

#### 2. **ALIAS**
Variante o alias de una entidad canónica.

**Características**:
- Debe tener **exactamente 1** `canonical_ref`
- Su relevancia se **transfiere completamente** a la canónica
- Útil para abreviaturas, apodos, variantes de escritura

**Ejemplo**: "Luis" → alias de "Luis Abinader"

**Transferencia de relevancia**:
```
Artículo menciona: "Luis" (relevancia 0.8)
Sistema transfiere: "Luis Abinader" recibe +0.8 de relevancia
```

#### 3. **AMBIGUOUS**
Entidad ambigua que puede referirse a múltiples entidades canónicas.

**Características**:
- Debe tener **mínimo 2** `canonical_refs`
- Su relevancia se **divide equitativamente** entre las canónicas presentes en el artículo
- El sistema intenta resolver automáticamente usando contexto

**Ejemplo**: "Luis" → puede ser "Luis Abinader" o "Luis Fonsi"

**División de relevancia**:
```
Artículo menciona: "Luis" (relevancia 0.6), "el presidente" (alias de Luis Abinader)
Sistema detecta contexto: Solo Luis Abinader está presente
Resultado: Luis Abinader recibe +0.6 (no se divide)
```

#### 4. **NOT_AN_ENTITY**
Falso positivo de extracción (no es realmente una entidad).

**Características**:
- No puede tener `canonical_refs`
- Su relevancia siempre es **0.0** (ignorada completamente)
- Útil para limpiar detecciones erróneas del LLM

**Ejemplo**: "Día" detectado como entidad pero es palabra común

### Desambiguación Contextual Automática

Cuando el sistema encuentra una entidad **AMBIGUOUS** en un artículo, intenta resolverla automáticamente:

**Estrategia de resolución**:

1. **Búsqueda directa**: ¿Se menciona la canónica explícitamente?
   - Si el artículo menciona "Luis Abinader" → resuelto como "Luis Abinader"

2. **Búsqueda por referencias**: ¿Hay otros alias que apuntan a esta canónica?
   - Si el artículo menciona "el presidente" (ALIAS de "Luis Abinader") → resuelto como "Luis Abinader"

3. **Si no se puede resolver**:
   - Si tiene ≤ 10 canonicals → divide relevancia entre todas
   - Si tiene > 10 canonicals → ignora completamente (evita dilución excesiva)

**Límites de rendimiento**:
```python
MAX_CONTEXTUAL_RESOLUTION_REFS = 10  # Máximo para intentar resolución contextual
MAX_AMBIGUITY_THRESHOLD = 10  # Ignorar si tiene más de este número de canonicals
```

### Origen de Entidades (EntityOrigin)

El campo `article_entities.origin` distingue cómo llegó la entidad al artículo:

- **`AI_ANALYSIS`**: Detectada por OpenAI durante `analyze_article`
- **`CLASSIFICATION`**: Agregada automáticamente por el sistema de clasificación al resolver aliases/ambiguos

**Ejemplo**:
```
Artículo original (AI_ANALYSIS): "Luis" (3 menciones)
Clasificas: "Luis" como ALIAS de "Luis Abinader"
Sistema agrega artificialmente: "Luis Abinader" con origin=CLASSIFICATION
```

**Protección contra duplicación**: Si "Luis Abinader" ya fue detectado por AI_ANALYSIS, NO se agrega artificialmente otra vez (evita duplicar link juice).

### Clasificación Automática con IA

El sistema ofrece clasificación automatizada usando **LSH (Locality-Sensitive Hashing) + Comparación 1v1 con OpenAI**.

#### Comando: `ai-classify`

```bash
# Clasificar todas las entidades
uv run news entity ai-classify

# Clasificar solo un tipo de entidad
uv run news entity ai-classify --type PERSON

# Ver qué haría sin ejecutar
uv run news entity ai-classify --dry-run

# Con verbose logging
uv run news entity ai-classify --verbose

# Ajustar umbral LSH (default 0.7)
uv run news entity ai-classify --lsh-threshold 0.8
```

#### Proceso de Clasificación AI

**FASE 1: Descubrimiento de Candidatos con LSH**
- Convierte nombres de entidades a caracteres individuales
- Genera MinHash signatures (128 permutaciones)
- Encuentra pares similares usando umbral configurable (default 0.7)
- **No requiere llamadas a API** - puramente algorítmico

**FASE 2: Comparación Semántica con OpenAI**
- Para cada par candidato, llama OpenAI para análisis semántico
- Carga pares ya comparados desde `entity_pair_comparisons`
- **Evita re-testar** pares ya procesados (ahorro de costos API)
- Analiza contexto, nombres, y tipos de entidad

**FASE 3: Aplicación de Clasificaciones**
El LLM puede clasificar una entidad como:
- **ALIAS**: Variante/abreviatura → llama `set_as_alias()`
- **AMBIGUOUS**: Puede referirse a múltiples → llama `set_as_ambiguous()`
- **NOT_AN_ENTITY**: Falso positivo → llama `set_as_not_entity()`
- **NO_CHANGE**: Son entidades diferentes → no hace nada

**FASE 4: Guardado de Comparaciones**
- Cada comparación se guarda en `entity_pair_comparisons`
- Incluye: relación (SAME/DIFFERENT/AMBIGUOUS), confianza, razonamiento
- Relación derivada de los cambios de clasificación
- Evita duplicados con índice único en `(entity_a_id, entity_b_id)`

**Beneficios del tracking de pares**:
- ✅ No re-testa pares ya comparados (ahorro de costos)
- ✅ Historial completo de decisiones del LLM
- ✅ Permite audit trail y revisión manual
- ✅ Puede usarse para entrenar modelos futuros

```sql
-- Ver todas las comparaciones
SELECT * FROM entity_pair_comparisons;

-- Ver solo entidades consideradas iguales
SELECT * FROM entity_pair_comparisons WHERE relationship = 'SAME';

-- Ver comparaciones con baja confianza
SELECT * FROM entity_pair_comparisons WHERE confidence < 0.7;
```

### Comandos de Clasificación Manual

Si necesitas clasificar manualmente (alternativa o complemento a `ai-classify`):

#### Listar entidades pendientes de revisión
```bash
uv run news entity list --needs-review
```

#### Revisar entidad específica
```bash
uv run news entity review <entity_id>
```

Muestra contexto de la entidad y opciones interactivas para clasificar.

#### Clasificar como CANONICAL
```bash
uv run news entity classify-canonical <entity_id>
```

#### Clasificar como ALIAS
```bash
uv run news entity classify-alias <entity_id> <canonical_id>
```

**Ejemplo**:
```bash
# "Luis" (ID: 123) es alias de "Luis Abinader" (ID: 45)
uv run news entity classify-alias 123 45
```

#### Clasificar como AMBIGUOUS
```bash
uv run news entity classify-ambiguous <entity_id> <canonical_id_1> <canonical_id_2> [...]
```

**Ejemplo**:
```bash
# "Luis" puede ser Luis Abinader (45) o Luis Fonsi (67)
uv run news entity classify-ambiguous 123 45 67
```

#### Clasificar como NOT_AN_ENTITY
```bash
uv run news entity classify-not-entity <entity_id>
```

### Recalculación de Relevancia Local

Después de clasificar entidades, **debes recalcular** la relevancia local de los artículos afectados:

```bash
# Recalcular todos los artículos marcados
uv run news entity recalculate-local

# Recalcular con límite
uv run news entity recalculate-local --limit 100

# Recalcular artículo específico
uv run news entity recalculate-local --article-id 456
```

**Proceso interno**:
1. Lee artículos de `articles_needs_rerank`
2. Para cada artículo:
   - Carga entidades originales (filtra por `origin=AI_ANALYSIS`)
   - Borra todas las relaciones `article_entities`
   - Recalcula relevancia con clasificaciones actuales
   - Inserta nuevas relevances con `origin` flags
3. Limpia artículos procesados de `articles_needs_rerank`

**Stats mostradas**:
- Articles processed/failed
- Total entities
- Entities ignored (ALIAS/AMBIGUOUS/NOT_AN_ENTITY)
- Entities artificial (from classifications)

### Tabla de Tracking

**`articles_needs_rerank`**: Artículos que necesitan recálculo.

Cuando clasificas una entidad, el sistema **automáticamente** marca todos los artículos que la mencionan:

```python
# Método interno llamado por todos los set_as_*()
def _mark_articles_for_rerank(self, session):
    # Inserta en articles_needs_rerank todos los artículos
    # que contienen esta entidad
```

### Métodos Helper del Modelo

**IMPORTANTE**: Los cambios de clasificación **deben hacerse** mediante estos métodos (no directamente):

```python
# En src/db/models.py clase NamedEntity

entity.set_as_canonical(session)
entity.set_as_alias(canonical_entity, session)
entity.set_as_ambiguous([canonical1, canonical2], session)
entity.set_as_not_entity(session)
```

**Estos métodos garantizan**:
- Validación de restricciones (conteo de canonical_refs)
- Limpieza de relaciones existentes
- Marcado automático de artículos para rerank
- Consistencia de datos

### Flujo Completo de Desambiguación

#### Opción 1: Clasificación Automática con IA (Recomendado)

```bash
# 1. Extraer entidades de artículos con OpenAI
uv run news process start -t analyze_article

# 2. Ejecutar clasificación AI-assisted
uv run news entity ai-classify --verbose

# Output:
# 🔍 Starting AI-assisted entity classification...
# 📊 Found 150 entities to classify (type: ALL)
# 🔍 LSH candidate discovery...
# ✓ Found 45 candidate pairs (threshold: 0.7)
#
# 🤖 AI semantic comparison (1v1)...
# ✓ Compared 45 pairs, classified 12 entities
#
# 📝 Classification summary:
#    • 8 entities → ALIAS
#    • 2 entities → AMBIGUOUS
#    • 2 entities → NOT_AN_ENTITY
#
# ✅ Classification complete!

# 3. Recalcular relevancia local (si hubo cambios)
uv run news entity recalculate-local

# 4. Recalcular relevancia global (PageRank)
uv run news entity rerank

# 5. Ver entidades más relevantes
uv run news entity list --order-by global_rank --limit 20
```

#### Opción 2: Clasificación Manual

**Ejemplo real**: Desambiguar "Luis" manualmente

```bash
# 1. Identificar entidad ambigua
uv run news entity search "Luis"

# Output:
# ID: 123 | Name: Luis | Type: PERSON | Articles: 45

# 2. Buscar candidatos canónicos
uv run news entity search "Luis Abinader"
uv run news entity search "Luis Fonsi"

# Output:
# ID: 45 | Name: Luis Abinader | Type: PERSON | Articles: 120
# ID: 67 | Name: Luis Fonsi | Type: PERSON | Articles: 8

# 3. Clasificar como AMBIGUOUS
uv run news entity classify-ambiguous 123 45 67

# Output:
# ✓ Marked 'Luis' as AMBIGUOUS with 2 canonical references
# ✓ 45 articles marked for local relevance recalculation

# 4. Recalcular relevancia local
uv run news entity recalculate-local --limit 50

# Output:
# 🔄 Recalculating local entity relevance...
# 📊 Found 45 articles to process
# ...
# ✅ Recalculation complete!
#    • Articles processed: 45
#    • Entities artificial: 67 (from AMBIGUOUS resolution)

# 5. Recalcular relevancia global (PageRank)
uv run news entity rerank

# 6. Verificar resultados
uv run news entity show "Luis Abinader"
uv run news entity show "Luis Fonsi"
```

### Validación de Consistencia

Verificar manualmente la consistencia de una entidad:

```python
from db import Database, NamedEntity

db = Database()
session = db.get_session()

entity = session.query(NamedEntity).filter_by(id=123).first()
is_valid, errors = entity.validate_classification(session)

if not is_valid:
    for error in errors:
        print(f"ERROR: {error}")
```

**Restricciones validadas**:
- CANONICAL: 0 canonical_refs salientes
- ALIAS: Exactamente 1 canonical_ref
- AMBIGUOUS: Mínimo 2 canonical_refs
- NOT_AN_ENTITY: 0 canonical_refs

---

## Sistema de Grupos de Entidades

### Introducción

El sistema de grupos permite representar entidades colectivas (bandas, equipos, consejos) que tienen miembros individuales. Los grupos tienen tracking temporal de membresías con fechas de inicio/fin y roles.

### Concepto

Un grupo es una entidad canónica marcada con `is_group=1` que puede tener relaciones con otras entidades (sus miembros) a través de la tabla `entity_group_members`.

**Características:**
- Solo entidades CANONICAL pueden ser grupos
- Los miembros pueden ser cualquier entidad (incluso otros grupos)
- Cada membresía tiene fecha de inicio/fin opcional
- Se valida que no haya overlaps (períodos superpuestos) para el mismo miembro

**Casos de uso:**
- **Música:** "Wisin & Yandel" → [Wisin, Yandel]
- **Política:** "Consejo de Ministros" → [Ministro de Salud, Ministro de Educación, ...]
- **Empresas:** "Microsoft" → [Satya Nadella, Bill Gates, ...]

### Estructura de Datos

#### Flag `is_group`
```python
# En NamedEntity
is_group = Column(Integer, nullable=False, default=0, index=True)
# 0 = Entidad individual
# 1 = Grupo que puede tener miembros
```

#### Tabla `entity_group_members`
```sql
CREATE TABLE entity_group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER REFERENCES named_entities(id) ON DELETE CASCADE,
    member_id INTEGER REFERENCES named_entities(id) ON DELETE CASCADE,
    role VARCHAR(100),           -- Opcional: "vocalist", "CEO", etc.
    since DATETIME,              -- Fecha de inicio (NULL = desconocido/siempre)
    until DATETIME,              -- Fecha de fin (NULL = presente/activo)
    created_at DATETIME,
    updated_at DATETIME
);
```

**Características:**
- PK auto-incremental (permite múltiples períodos para el mismo member)
- Sin unique constraint (permite que un miembro salga y vuelva a entrar)
- Validación de overlaps a nivel de aplicación

### Gestión de Grupos

#### Marcar como grupo
```bash
# Solo entidades CANONICAL pueden ser grupos
uv run news entity set-group <entity_id>
```

#### Desmarcar como grupo
```bash
# Requiere que no tenga miembros
uv run news entity unset-group <entity_id>
```

#### Agregar miembro
```bash
# Miembro actualmente activo (since=NULL, until=NULL)
uv run news entity add-member <group_id> <member_id>

# Con rol y fechas
uv run news entity add-member 100 101 \
    --role "vocalist" \
    --since 1997-01-01 \
    --until 2011-07-01
```

**Validación:**
- El grupo debe tener `is_group=1`
- El miembro debe existir en la base de datos
- No puede haber overlap con membresías existentes

#### Remover miembro
```bash
# Marca la fecha de salida (actualiza until del registro activo)
uv run news entity remove-member <group_id> <member_id>

# Con fecha específica
uv run news entity remove-member 100 101 --until 2011-07-01
```

#### Listar miembros
```bash
# Todos los miembros (todos los períodos)
uv run news entity list-members <group_id>

# Miembros activos en fecha específica
uv run news entity list-members 100 --active-at 2008-01-01

# Con detalles de fechas y roles
uv run news entity list-members 100 --show-dates
```

### Queries Temporales

#### Obtener miembros activos en una fecha
```python
# En código (usando métodos helper)
article_date = article.published_date
active_members = group.get_active_members_at(article_date, session)

# SQL equivalente
SELECT ne.*
FROM named_entities ne
JOIN entity_group_members egm ON ne.id = egm.member_id
WHERE egm.group_id = :group_id
  AND (egm.since IS NULL OR egm.since <= :date)
  AND (egm.until IS NULL OR egm.until >= :date)
```

#### Obtener grupos de un miembro en una fecha
```python
active_groups = member.get_active_groups_at(article_date, session)
```

### Ejemplo Completo

**Escenario:** Aventura (grupo musical)

```bash
# 1. Buscar entidades
uv run news entity search "Aventura"  # ID: 100
uv run news entity search "Romeo Santos"  # ID: 101
uv run news entity search "Henry Santos"  # ID: 102

# 2. Marcar Aventura como grupo
uv run news entity set-group 100

# 3. Agregar miembros históricos
uv run news entity add-member 100 101 \
    --role "lead vocalist" \
    --since 1997-01-01 \
    --until 2011-07-01  # Romeo salió en 2011

uv run news entity add-member 100 102 \
    --role "vocalist" \
    --since 1997-01-01  # Henry sigue activo (until=NULL)

# 4. Ver miembros en diferentes fechas
uv run news entity list-members 100 --active-at 2008-01-01
# Output: Romeo Santos, Henry Santos (ambos activos)

uv run news entity list-members 100 --active-at 2024-01-01
# Output: Henry Santos (solo Henry activo)

# 5. Ver información del grupo
uv run news entity show "Aventura"
# Output incluye: Group: Yes (2 member(s))

# 6. Ver información de un miembro
uv run news entity show "Romeo Santos"
# Output incluye: Member of 1 group(s)
```

### Boost de Relevancia (Futuro)

**Estado actual:** Los grupos NO afectan la relevancia de miembros ni viceversa.

**Implementación futura:** Cuando se implemente boost bidireccional:
- Mencionar grupo → boost a miembros activos en la fecha del artículo
- Mencionar miembro → boost al grupo si era miembro activo
- Boost con conservación de suma (no infla relevancia total)

Ver diseño detallado en discusiones de desarrollo.

---

## Relevancia Global de Entidades (PageRank)

### Concepto

El sistema calcula la importancia global de entidades usando el algoritmo **PageRank** aplicado a un grafo de co-ocurrencias. La intuición es que entidades mencionadas juntas en artículos forman una red de relaciones, donde:

- **Nodos**: Entidades (personas, organizaciones, lugares, etc.)
- **Aristas dirigidas ponderadas**: Co-ocurrencia en artículos
  - Peso del enlace B → A = `relevance_local(A)` en ese artículo
  - Esto significa que "enlazas más fuerte" a las figuras centrales de cada artículo

**Ejemplo**: Si "Luis Abinader" (relevancia 1.0) y "Ministerio de Salud" (relevancia 0.76) aparecen en el mismo artículo:
- Ministerio → Abinader: peso 1.0 (Abinader es más central)
- Abinader → Ministerio: peso 0.76 (Ministerio es secundario)

### Tipos de Entidades Rankeadas

El cálculo de PageRank se aplica **solo** a los siguientes tipos de entidades:

- `PERSON`: Personas
- `ORG`: Organizaciones, instituciones
- `FAC`: Edificios, infraestructura
- `GPE`: Lugares geopolíticos (países, ciudades)
- `LOC`: Ubicaciones geográficas
- `EVENT`: Eventos nombrados
- `WORK_OF_ART`: Obras de arte
- `LAW`: Leyes y documentos legales
- `LANGUAGE`: Idiomas
- `DATE`: Fechas

Los demás tipos (MONEY, PERCENT, QUANTITY, etc.) mantienen `global_relevance = 0.0`.

### Algoritmo

**PageRank Iterativo**:
```
1. Inicialización:
   - Si existe ranking previo: usar scores `pagerank` anteriores (warm start)
   - Nuevas entidades: inicializar en midpoint = (max + min) / 2 (convergencia más rápida)
   - Normalizar vector inicial

2. Iteración (hasta convergencia, max 1000 iteraciones, o timeout 30s):
   PR_new(i) = (1-d)/N + d * Σ(PR(j) * w(j→i) / Σw(j→k))

   Donde:
   - d = damping factor (0.85 por defecto)
   - N = número total de entidades
   - w(j→i) = peso del enlace de j a i

3. Normalizar: Σ PR(i) = 1.0

4. Verificar convergencia: |PR_new - PR| < 1e-6

5. Verificar timeout: Si han pasado 30s, terminar gracefully
   (No genera error, simplemente guarda el estado actual)

6. Post-procesamiento:
   - Guardar resultado raw como `pagerank`
   - Normalizar con min-max scaling → `global_relevance` (0.0-1.0)
```

**Dos Métricas de Ranking**:
- **`pagerank`**: Score raw (distribución de probabilidad, suma ≈ 1.0)
  - Usado para warm start en futuros cálculos
  - Preserva la distribución original del algoritmo
- **`global_relevance`**: Score normalizado con min-max scaling (0.0-1.0)
  - Entidad más importante = 1.0
  - Entidad menos importante = 0.0
  - Human-friendly, fácil de interpretar
  - Útil para cálculos avanzados y comparaciones

**Manejo de Dangling Nodes**:
- Entidades sin enlaces salientes distribuyen su probabilidad uniformemente

**Ajustes del Algoritmo**:
- **Max iteraciones**: 1000 (suficiente para convergencia en la mayoría de casos)
- **Timeout graceful**: 30 segundos (no genera error, guarda estado actual)
- **Threshold de relevancia**: Ignorar co-ocurrencias débiles (default: 0.3)
- **Normalización por documento**: Siempre activa (divide peso por # entidades/artículo)
- **Time decay**: Dar menos peso a artículos antiguos (exponencial, opcional)

### Métricas Calculadas

Se calculan y almacenan las siguientes métricas en `named_entities`:

- **pagerank**: Score PageRank raw (suma ≈ 1.0 entre todas las entidades)
- **global_relevance**: PageRank normalizado 0.0-1.0 (min-max scaled)
- **article_count**: Número de artículos donde aparece
- **avg_local_relevance**: Promedio de relevancia local
- **diversity**: Número de entidades únicas con las que co-ocurre

### Comando CLI

```bash
uv run news entity rerank [OPTIONS]
```

**Opciones**:
- `--domain TEXT`: Filtrar artículos por dominio (testing)
- `--damping FLOAT`: Factor de amortiguación (default: 0.85)
- `--threshold FLOAT`: Umbral mínimo de relevancia (default: 0.3)
- `--time-decay INT`: Decay temporal en días (opcional)
- `--show-stats`: Mostrar estadísticas detalladas

**Ejemplos**:
```bash
# Calcular ranking global para todas las entidades
uv run news entity rerank

# Solo artículos de un dominio (testing)
uv run news entity rerank --domain diariolibre.com

# Ajustar parámetros del algoritmo
uv run news entity rerank --damping 0.9 --threshold 0.4

# Con decay temporal y estadísticas
uv run news entity rerank --time-decay 30 --show-stats
```

**Output esperado**:
```
🔄 Calculating global entity relevance...

📊 Loading data:
   • 1,234 enriched articles
   • 567 entities to rank

⚙️  Executing PageRank...
   • Damping: 0.85
   • Threshold: 0.3

✅ Global relevance calculated successfully!

   • Converged in 23 iterations
   • Processing time: 2.45s
   • Entities ranked: 567

🏆 Top 10 entities by global relevance:

    1. Luis Abinader - 0.084723
    2. Joe Biden - 0.062384
    3. Ministerio de Salud - 0.051234
    ...

💾 Updated database

💡 View ranked entities with:
   news entity list --order-by global_rank
```

### Ver Resultados

**Listar por ranking global**:
```bash
uv run news entity list --order-by global_rank --limit 20
```

**Ver detalles de entidad**:
```bash
uv run news entity show "Luis Abinader"
```

Output incluye:
- Global Rank: `0.084723 (#1 of 567)`
- Avg Local Relevance: `0.856`
- Diversity: `123 co-occurring entities`

### Consultas SQL

**Top entidades por PageRank**:
```sql
SELECT
    name,
    entity_type,
    pagerank,
    global_relevance,
    article_count,
    avg_local_relevance,
    diversity
FROM named_entities
WHERE global_relevance > 0
ORDER BY global_relevance DESC
LIMIT 20;
```

**Distribución de scores**:
```sql
SELECT
    entity_type,
    COUNT(*) as total,
    AVG(global_relevance) as avg_rank,
    MAX(global_relevance) as max_rank,
    SUM(CASE WHEN global_relevance > 0.01 THEN 1 ELSE 0 END) as influential
FROM named_entities
WHERE global_relevance > 0
GROUP BY entity_type
ORDER BY avg_rank DESC;
```

**Entidades con mayor conectividad**:
```sql
SELECT
    name,
    entity_type,
    diversity,
    article_count,
    global_relevance
FROM named_entities
WHERE diversity > 0
ORDER BY diversity DESC
LIMIT 20;
```

### Frecuencia de Actualización

El ranking global **no se calcula automáticamente**. Se debe ejecutar manualmente con `news entity rerank`.

**Recomendaciones**:
- **Diario**: Para portales de noticias en producción
- **Después de procesar lotes grandes**: Si se agregan 100+ artículos nuevos
- **Semanal**: Para desarrollo/testing

### Validación

Después de calcular el ranking, verificar:

1. **Suma de probabilidades**: `SUM(pagerank) ≈ 1.0` (distribución de PageRank)
2. **Normalización**: `MAX(global_relevance) = 1.0` y `MIN(global_relevance) = 0.0`
3. **Top entidades coherentes**: Presidentes, ministros, organizaciones principales deben tener scores altos
4. **Convergencia**: El algoritmo debe converger en <100 iteraciones típicamente
   - Si llega a 1000 iteraciones o 30s timeout, revisar datos de entrada
5. **Distribución**: La entidad más importante debe tener `global_relevance = 1.0`

### Consideraciones de Performance

- **~1000 entidades**: Matriz 1000×1000, procesa en <5 segundos
- **10k+ entidades**: Considerar:
  - Usar sparse matrices (`scipy.sparse`)
  - Filtrar por tiempo (últimos N meses)
  - Incrementar threshold de relevancia

**Memoria estimada**:
- 1000 entidades: ~8 MB (matriz densa)
- 10000 entidades: ~800 MB

