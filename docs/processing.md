# Procesamiento de Artículos

## Introducción

El sistema de procesamiento por lotes permite ejecutar diferentes tipos de procesamiento sobre artículos de forma eficiente y trazable.

## Tipos de Procesamiento

### Enriquecimiento de Artículos (`enrich_article`)

Extrae entidades nombradas (NER - Named Entity Recognition) de los artículos usando spaCy.

**Características**:
- Modelo: `es_core_news_sm` (español)
- Extrae 18 tipos de entidades (personas, organizaciones, lugares, etc.)
- Asocia entidades a artículos con conteo de menciones
- **Calcula relevancia local** (ver sección "Cálculo de Relevancia")
- Actualiza contador global de artículos por entidad
- Guarda logs detallados del procesamiento

## Comandos CLI

### Iniciar Procesamiento

Crea y ejecuta un batch de procesamiento para artículos de un dominio.

```bash
uv run news domain process start -d <dominio> -t <tipo> -s <tamaño>
```

**Parámetros**:
- `-d, --domain`: Dominio a procesar (requerido)
- `-t, --type`: Tipo de procesamiento (requerido)
  - `enrich_article`: Enriquecimiento con NER
- `-s, --size`: Tamaño del batch (default: 10)

**Ejemplo**:
```bash
uv run news domain process start -d diariolibre.com -t enrich_article -s 10
```

### Listar Batches

Muestra todos los batches de procesamiento con opciones de filtrado.

```bash
uv run news domain process list [opciones]
```

**Parámetros opcionales**:
- `-l, --limit`: Número de batches a mostrar (default: 20)
- `-s, --status`: Filtrar por estado (pending, processing, completed, failed)
- `-d, --domain`: Filtrar por dominio

**Ejemplos**:
```bash
# Listar últimos 20 batches
uv run news domain process list

# Listar batches completados
uv run news domain process list --status completed

# Listar batches de un dominio
uv run news domain process list --domain diariolibre.com

# Combinar filtros
uv run news domain process list --domain diariolibre.com --status failed --limit 10
```

### Ver Detalles de Batch

Muestra información detallada sobre un batch específico.

```bash
uv run news domain process show <batch_id>
```

**Ejemplo**:
```bash
uv run news domain process show 1
```

**Información mostrada**:
- Metadatos del batch (source, tipo, estado)
- Progreso (total, procesados, exitosos, fallidos)
- Estadísticas agregadas
- Tiempos de ejecución y duración
- Resumen de items por estado
- Primeros 5 items fallidos (si hay)

## Flujo de Procesamiento

1. **Selección de artículos**: Se seleccionan artículos no enriquecidos (`enriched_at IS NULL`)
2. **Creación de batch**: Se crea un registro en `processing_batches`
3. **Creación de items**: Se crean registros en `batch_items` para cada artículo (transacción atómica)
4. **Procesamiento**:
   - Por cada artículo:
     - Se extrae el texto (título + contenido)
     - Se ejecuta NER con spaCy
     - Se crean/actualizan entidades en `named_entities`
     - Se asocian entidades al artículo en `article_entities` con menciones y relevancia
     - Se marca el artículo como enriquecido (`enriched_at`)
     - Se guardan logs y estadísticas
5. **Finalización**: Se actualiza el batch con estadísticas finales

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
- Ver batches: `uv run news domain process list`
- Ver detalles de batch: `uv run news domain process show <batch_id>`
- Ver logs de item: `uv run news domain process show <batch_id> --item <item_id>`
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
