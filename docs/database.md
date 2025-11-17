# Base de Datos

## Tecnología

- **Motor**: SQLite 3
- **ORM**: SQLAlchemy 2.0.44
- **Ubicación**: `data/news.db`

## Esquema

### Tabla: `sources`

Fuentes de noticias (medios digitales).

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY | ID auto-incremental |
| domain | VARCHAR(255) | UNIQUE, NOT NULL, INDEX | Dominio (ej: "diariolibre.com") |
| name | VARCHAR(255) | | Nombre descriptivo del medio |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Última actualización |

**Relaciones**:
- 1:N con `articles` (un source tiene muchos artículos)
- 1:N con `domain_processes` (un source tiene múltiples registros de procesamiento)

### Tabla: `domain_processes`

Rastrea la última vez que se ejecutó cada tipo de procesamiento por dominio.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| source_id | INTEGER | FOREIGN KEY, PRIMARY KEY | ID de la fuente |
| process_type | ENUM | PRIMARY KEY | Tipo de procesamiento |
| last_processed_at | DATETIME | NOT NULL | Última vez que se procesó |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Última actualización |

**Valores de `process_type`**:
- `enrich_article`: Enriquecimiento de artículos (clustering + NER)
- `generate_flash_news`: Generación de flash news con LLM

**Relaciones**:
- N:1 con `sources` (múltiples procesos pertenecen a un source)

**Restricciones**:
- PK compuesta: `(source_id, process_type)` - un solo registro por tipo de proceso por dominio
- `source_id` ON DELETE CASCADE (si se elimina el source, se eliminan sus procesos)

**Inicialización automática**:
- Cuando se crea un nuevo `Source`, automáticamente se crean registros en `domain_processes` para cada tipo de proceso
- La fecha inicial es `1970-01-01` (época Unix), equivalente a "nunca procesado"

### Tabla: `articles`

Artículos de noticias completos con metadata.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY | ID auto-incremental |
| hash | VARCHAR(64) | UNIQUE, NOT NULL, INDEX | SHA-256 completo de la URL |
| url | VARCHAR(2048) | NOT NULL | URL original del artículo |
| source_id | INTEGER | FOREIGN KEY, NOT NULL | ID de la fuente |
| title | VARCHAR(500) | NOT NULL | Título del artículo |
| subtitle | VARCHAR(1000) | | Subtítulo o bajada |
| author | VARCHAR(255) | | Nombre del autor |
| published_date | DATETIME | INDEX | Fecha de publicación original |
| location | VARCHAR(255) | | Ciudad de origen |
| category | VARCHAR(255) | | Categoría/Subcategoría |
| content | TEXT | NOT NULL | Contenido en formato Markdown |
| enriched_at | DATETIME | NULLABLE, INDEX | Fecha de enriquecimiento (NULL = no enriquecido) |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación en DB |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Última actualización |

**Relaciones**:
- N:1 con `sources` (muchos artículos pertenecen a un source)
- M:N con `tags` vía `article_tags` (muchos artículos tienen muchos tags)
- M:N con `named_entities` vía `article_entities` (muchos artículos tienen muchas entidades)

**Índices**:
- `hash` (UNIQUE): Para deduplicación rápida
- `(source_id, hash)` compuesto: Para búsquedas por dominio + deduplicación
- `published_date`: Para ordenar por fecha de publicación
- `created_at`: Para ordenar por fecha de ingreso
- `updated_at`: Para ordenar por última modificación

**Nota sobre URL**:
- No tiene restricción UNIQUE ni índice (la unicidad está garantizada por el hash)
- URLs pueden ser muy largas, indexarlas sería ineficiente
- El hash SHA-256 es único y se usa para deduplicación

### Tabla: `tags`

Tags únicos para categorización.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY | ID auto-incremental |
| name | VARCHAR(100) | UNIQUE, NOT NULL, INDEX | Nombre del tag |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Última actualización |

**Relaciones**:
- M:N con `articles` vía `article_tags`

### Tabla: `named_entities`

Entidades nombradas extraídas de artículos mediante NER (Named Entity Recognition).

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY | ID auto-incremental |
| name | VARCHAR(255) | UNIQUE, NOT NULL, INDEX | Nombre de la entidad |
| entity_type | ENUM | NOT NULL | Tipo de entidad |
| detected_types | JSON | NULLABLE | Lista de tipos detectados por spaCy para esta entidad |
| classified_as | ENUM | NOT NULL, DEFAULT 'canonical', INDEX | Clasificación para desambiguación |
| description | TEXT | NULLABLE | Descripción de la entidad |
| photo_url | VARCHAR(500) | NULLABLE | URL de la foto de la entidad |
| article_count | INTEGER | NOT NULL, DEFAULT 0 | Número de artículos que mencionan esta entidad |
| avg_local_relevance | FLOAT | NULLABLE, DEFAULT 0.0 | Promedio de relevancia local en artículos |
| diversity | INTEGER | NOT NULL, DEFAULT 0 | Número de entidades únicas con las que co-ocurre |
| pagerank | FLOAT | NULLABLE, DEFAULT 0.0 | Score PageRank raw (sin normalizar) |
| global_relevance | FLOAT | NULLABLE, DEFAULT 0.0, INDEX | PageRank normalizado (0.0-1.0, min-max scaled) |
| last_rank_calculated_at | DATETIME | NULLABLE, INDEX | Última vez que se calculó ranking global |
| needs_review | INTEGER | NOT NULL, DEFAULT 1, INDEX | 1=necesita revisión, 0=revisado y correcto |
| last_review | DATETIME | NULLABLE, INDEX | Última vez que la entidad fue revisada manualmente |
| trend | INTEGER | NOT NULL, DEFAULT 0 | Score de tendencia (-100 a 100) |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Última actualización |

**Valores de `classified_as`** (clasificación para desambiguación):
- `canonical`: Entidad principal/verdadera (default)
- `alias`: Variante o alias de otra entidad canónica
- `ambiguous`: Entidad ambigua que puede referirse a múltiples entidades canónicas
- `not_an_entity`: Falso positivo de NER (no es realmente una entidad)

**Valores de `entity_type`** (basados en etiquetas NER de spaCy):
- `person`: Personas, incluyendo ficticias
- `norp`: Nacionalidades, grupos religiosos o políticos
- `fac`: Edificios, aeropuertos, autopistas, puentes, etc.
- `org`: Compañías, agencias, instituciones, etc.
- `gpe`: Países, ciudades, estados
- `loc`: Ubicaciones no-GPE, cordilleras, cuerpos de agua
- `product`: Objetos, vehículos, alimentos, etc. (no servicios)
- `event`: Huracanes, batallas, guerras, eventos deportivos, etc.
- `work_of_art`: Títulos de libros, canciones, etc.
- `law`: Documentos nombrados convertidos en leyes
- `language`: Cualquier idioma nombrado
- `date`: Fechas absolutas o relativas o períodos
- `time`: Tiempos menores a un día
- `percent`: Porcentajes, incluyendo "%"
- `money`: Valores monetarios, incluyendo unidad
- `quantity`: Medidas, como peso o distancia
- `ordinal`: "primero", "segundo", etc.
- `cardinal`: Numerales que no caen en otro tipo

**Campos clave**:
- `detected_types`: Lista JSON de todos los tipos que spaCy ha detectado para esta entidad (útil para identificar inconsistencias)
- `classified_as`: Clasificación para desambiguación (canonical/alias/ambiguous/not_an_entity)
- `article_count`: Número de artículos que mencionan esta entidad (actualizado durante reranking)
- `avg_local_relevance`: Promedio de relevancia local en todos los artículos donde aparece
- `diversity`: Número de entidades únicas con las que co-ocurre (mide conectividad en el grafo)
- `needs_review`: Flag para revisión manual (1=necesita revisión, 0=ya revisado)
- `last_review`: Timestamp de última revisión manual
- `pagerank`: Score de PageRank sin normalizar
  - Distribución de probabilidad (suma total ≈ 1.0)
  - Usado para warm start en futuros cálculos
- `global_relevance`: Score de PageRank normalizado con min-max scaling (0.0-1.0)
  - Entidad con mayor PageRank = 1.0
  - Entidad con menor PageRank = 0.0
  - Resto escala proporcionalmente
  - Human-friendly y útil para cálculos avanzados
  - Solo para tipos: PERSON, ORG, FAC, GPE, LOC, EVENT, WORK_OF_ART, LAW, LANGUAGE, DATE
  - Otros tipos tienen 0.0
- `last_rank_calculated_at`: Timestamp del inicio del último cálculo de ranking
  - Usado para warm start: entidades existentes conservan su score `pagerank` anterior
  - Nuevas entidades se inicializan en el midpoint (promedio entre max y min) para convergencia más rápida
- `trend`: Reservado para uso futuro (cálculo de tendencias temporales)

### Tabla: `processing_batches`

Trabajos de procesamiento por lotes para artículos.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY | ID auto-incremental |
| source_id | INTEGER | FOREIGN KEY, NOT NULL, INDEX | ID de la fuente a procesar |
| process_type | ENUM | NOT NULL, INDEX | Tipo de procesamiento |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'pending', INDEX | Estado del batch |
| total_items | INTEGER | NOT NULL, DEFAULT 0 | Total de artículos en el batch |
| processed_items | INTEGER | NOT NULL, DEFAULT 0 | Artículos procesados (exitosos + fallidos) |
| successful_items | INTEGER | NOT NULL, DEFAULT 0 | Artículos procesados exitosamente |
| failed_items | INTEGER | NOT NULL, DEFAULT 0 | Artículos que fallaron |
| error_message | TEXT | NULLABLE | Mensaje de error general si el batch falló |
| stats | JSON | NULLABLE | Estadísticas adicionales del batch (JSON) |
| started_at | DATETIME | NULLABLE, INDEX | Fecha de inicio del procesamiento |
| completed_at | DATETIME | NULLABLE, INDEX | Fecha de finalización |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Última actualización |

**Valores de `status`**:
- `pending`: Batch creado, esperando procesamiento
- `processing`: Batch en proceso
- `completed`: Batch completado exitosamente
- `failed`: Batch falló completamente

**Campo `stats` (JSON)**: Puede contener métricas como tiempo promedio de procesamiento, tipos de errores encontrados, etc.

**Relaciones**:
- N:1 con `sources` (múltiples batches pueden procesar la misma fuente)
- 1:N con `batch_items` (un batch contiene múltiples items)

**Índices**:
- `source_id`: Para filtrar batches por fuente
- `process_type`: Para filtrar por tipo de procesamiento
- `status`: Para buscar batches pendientes/en proceso
- `started_at`, `completed_at`: Para ordenar por tiempo de ejecución
- `created_at`, `updated_at`: Timestamps estándar

### Tabla: `batch_items`

Items individuales dentro de un batch de procesamiento.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY | ID auto-incremental |
| batch_id | INTEGER | FOREIGN KEY, NOT NULL, INDEX | ID del batch padre |
| article_id | INTEGER | FOREIGN KEY, NOT NULL, INDEX | ID del artículo a procesar |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'pending', INDEX | Estado del item |
| error_message | TEXT | NULLABLE | Mensaje de error específico del item |
| logs | TEXT | NULLABLE | Logs de procesamiento del item |
| stats | JSON | NULLABLE | Estadísticas específicas del item (JSON) |
| started_at | DATETIME | NULLABLE | Fecha de inicio del procesamiento |
| completed_at | DATETIME | NULLABLE | Fecha de finalización |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Última actualización |

**Valores de `status`**:
- `pending`: Item pendiente de procesamiento
- `processing`: Item en proceso
- `completed`: Item procesado exitosamente
- `failed`: Item falló durante el procesamiento
- `skipped`: Item saltado (ej: ya procesado anteriormente)

**Campo `logs` (TEXT)**: Logs detallados del procesamiento del item

**Campo `stats` (JSON)**: Puede contener métricas como:
- Tiempo de procesamiento
- Número de entidades extraídas
- Tokens procesados
- Cualquier otra métrica específica del tipo de procesamiento

**Relaciones**:
- N:1 con `processing_batches` (múltiples items pertenecen a un batch)
- N:1 con `articles` (múltiples items pueden referenciar el mismo artículo en diferentes batches)

**Índices**:
- `batch_id`: Para buscar todos los items de un batch
- `article_id`: Para buscar procesamiento histórico de un artículo
- `status`: Para filtrar items pendientes/fallidos
- `(batch_id, status)` compuesto: Para consultas de estado por batch
- `created_at`, `updated_at`: Timestamps estándar

**Restricciones**:
- `batch_id` ON DELETE CASCADE (si se elimina el batch, se eliminan sus items)
- `article_id` ON DELETE CASCADE (si se elimina el artículo, se eliminan sus registros de procesamiento)

### Tabla: `article_entities`

Tabla de asociación para la relación muchos-a-muchos entre artículos y entidades nombradas.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| article_id | INTEGER | FOREIGN KEY, PRIMARY KEY | ID del artículo |
| entity_id | INTEGER | FOREIGN KEY, PRIMARY KEY | ID de la entidad |
| mentions | INTEGER | NOT NULL, DEFAULT 1 | Número de menciones en el artículo |
| relevance | FLOAT | NOT NULL, DEFAULT 0.0, INDEX | Score de relevancia para este par artículo-entidad |
| origin | ENUM | NOT NULL, DEFAULT 'ner' | Origen de la entidad: 'ner' (detectada) o 'classification' (agregada) |
| context_sentences | JSON | NULLABLE | Lista de oraciones donde se encontró la entidad |

**Restricciones**:
- PK compuesta: `(article_id, entity_id)`
- `article_id` ON DELETE CASCADE
- `entity_id` ON DELETE CASCADE

**Campos adicionales**:
- `mentions`: Conteo directo de cuántas veces aparece la entidad en el artículo
- `relevance`: Score calculado (FLOAT, 0.0 a 1.0) que considera:
  - **Base score**: Proporción de menciones de esta entidad vs total de menciones en el artículo
  - **Bonos** (sumados como % del base_score):
    - +50% si aparece en el título
    - +25% si aparece en el subtítulo
    - +30% si aparece en el primer 20% del contenido
    - +15% si aparece en el primer 40% del contenido
    - +10% por cada mención adicional más allá de 3 (cap en +50%)
  - **Normalización**: El score se normaliza para que la entidad más relevante del artículo tenga 1.0

**Campos adicionales desde el commit de desambiguación**:
- `origin`: Distingue entre entidades detectadas por NER vs agregadas por clasificación
  - `ner`: Detectada originalmente por spaCy
  - `classification`: Agregada automáticamente por el sistema de clasificación (ej: canonical de un alias)
- `context_sentences`: Oraciones donde aparece la entidad (útil para revisión manual)

**Índices**:
- `article_id`: Para buscar todas las entidades de un artículo
- `(article_id, origin)` compuesto: Para recalculación eficiente (filtrar solo NER)
- `entity_id`: Para buscar todos los artículos que mencionan una entidad
- `relevance`: Para ordenar por relevancia

### Tabla: `entity_canonical_refs`

Tabla de asociación many-to-many para referencias canónicas entre entidades (desambiguación).

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| entity_id | INTEGER | FOREIGN KEY, PRIMARY KEY | ID de la entidad (alias/ambiguous) |
| canonical_id | INTEGER | FOREIGN KEY, PRIMARY KEY | ID de la entidad canónica |

**Propósito**: Relaciona entidades ALIAS y AMBIGUOUS con sus entidades canónicas.

**Ejemplos de uso**:
- ALIAS: "Luis" → "Luis Abinader" (1 canonical_ref)
- AMBIGUOUS: "Luis" → ["Luis Abinader", "Luis Fonsi"] (2+ canonical_refs)

**Restricciones**:
- PK compuesta: `(entity_id, canonical_id)` (evita duplicados)
- `entity_id` ON DELETE CASCADE (si se elimina la entidad, se eliminan sus referencias)
- `canonical_id` ON DELETE RESTRICT (no se puede eliminar canonical si tiene referencias)

**Índices**:
- `entity_id`: Para buscar canonicals de una entidad
- `canonical_id`: Para buscar qué entidades apuntan a una canonical

**Relaciones**:
- N:M entre `named_entities` (self-join)

### Tabla: `articles_needs_rerank`

Tabla de tracking para artículos que necesitan recalcular relevancia local tras cambios de clasificación.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| article_id | INTEGER | FOREIGN KEY, PRIMARY KEY | ID del artículo que necesita recálculo |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Cuándo se marcó para recálculo |

**Propósito**: Cuando clasificas una entidad (ej: marcas "Luis" como ALIAS de "Luis Abinader"), todos los artículos que mencionan "Luis" se marcan aquí para recalcular su relevancia local.

**Flujo**:
1. Usuario clasifica entidad con `news entity classify-*`
2. Sistema marca automáticamente todos los artículos afectados en esta tabla
3. Usuario ejecuta `news entity recalculate-local` para procesar
4. Sistema recalcula relevancia y limpia registros procesados

**Restricciones**:
- PK: `article_id` (un artículo solo se marca una vez)
- `article_id` ON DELETE CASCADE (si se elimina el artículo, se elimina el tracking)

**Índices**:
- `article_id`: PK (búsqueda rápida)
- `created_at`: Para ordenar por antigüedad

### Tabla: `article_tags`

Tabla de asociación para la relación muchos-a-muchos entre artículos y tags.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| article_id | INTEGER | FOREIGN KEY, PRIMARY KEY | ID del artículo |
| tag_id | INTEGER | FOREIGN KEY, PRIMARY KEY | ID del tag |

**Restricciones**:
- `article_id` ON DELETE CASCADE (si se elimina el artículo, se elimina la asociación)
- `tag_id` ON DELETE CASCADE (si se elimina el tag, se elimina la asociación)

## Deduplicación

Los artículos se deduplican usando dos mecanismos:

1. **Hash SHA-256 de la URL**: Previene re-procesamiento de la misma URL
2. **URL única**: Restricción de base de datos para garantizar unicidad

Antes de descargar, se verifica con `database.article_exists(url, hash)`.

## Operaciones CRUD

### Clase `Database` (`src/db/database.py`)

```python
from db.database import Database

db = Database()  # Usa data/news.db por defecto
session = db.get_session()

# Crear/Obtener source
source = db.get_or_create_source(session, "example.com", "Example News")

# Guardar artículo
article_data = {
    "title": "Título",
    "content": "Contenido en Markdown",
    "tags": ["política", "economía"]
    # ...
}
article = db.save_article(session, article_data, "example.com")

# Listar artículos
articles = db.list_articles(session, limit=10)

# Buscar por fuente
articles = db.list_articles(session, source_domain="diariolibre.com")

# Buscar por tag
articles = db.list_articles(session, tag="política")

# Obtener artículo
article = db.get_article(session, article_id=1)

# Eliminar artículo
db.delete_article(session, article_id=1)

session.close()
```

## Patrón Get-or-Create

Los métodos `get_or_create_source()` y `get_or_create_tag()` implementan el patrón:
1. Buscar por nombre/dominio
2. Si no existe, crear nuevo
3. Retornar el objeto

Esto simplifica la lógica y evita duplicados.

## Cascade Deletes

- Eliminar un `Source` → Se eliminan todos sus `Articles`
- Eliminar un `Article` → Se eliminan sus asociaciones en `article_tags`
- Eliminar un `Tag` → Se eliminan sus asociaciones en `article_tags`

### Tabla: `flash_news`

Resúmenes narrativos generados automáticamente desde clusters core usando LLM.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY | ID auto-incremental |
| cluster_id | INTEGER | FOREIGN KEY, UNIQUE, NOT NULL, INDEX | ID del cluster (relación 1:1) |
| summary | TEXT | NOT NULL | Resumen narrativo del cluster (2-3 oraciones) |
| embedding | JSON | NULLABLE | Vector embedding del resumen (lista de floats) |
| published | INTEGER | NOT NULL, DEFAULT 0, INDEX | Estado: 0=no publicado, 1=publicado |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Última actualización |

**Relaciones**:
- 1:1 con `article_clusters` (un flash news pertenece a un cluster core)
- Indirecto: `flash_news` → `article_clusters` → `articles`

**Restricciones**:
- `cluster_id` UNIQUE: Solo un flash news por cluster
- `cluster_id` ON DELETE CASCADE: Si se elimina el cluster, se elimina el flash news
- `published` es INTEGER (0/1) porque SQLite no tiene BOOLEAN nativo

**Generación**:
- Proceso independiente `generate_flash_news` (separado de `enrich_article`)
- Solo se generan para clusters con `category='CORE'`
- Usa OpenAI API con Structured Outputs (Pydantic validation)
- Embedding generado con `sentence-transformers` (mismo modelo que clustering)
- Idempotente: detecta y salta clusters que ya tienen flash news

**Uso**:
- `published=0`: Flash news generada pero no publicada
- `published=1`: Flash news lista para mostrar públicamente
- Embedding permite búsqueda semántica de noticias similares

**Índices**:
- `cluster_id` (UNIQUE): Garantiza un solo flash news por cluster
- `published`: Permite filtrado rápido por estado
- `created_at`: Para ordenamiento cronológico

**Ejemplo de consulta**:
```sql
-- Flash news no publicadas con info del artículo
SELECT
    fn.id,
    fn.summary,
    a.title,
    a.published_date,
    s.domain
FROM flash_news fn
JOIN article_clusters ac ON fn.cluster_id = ac.id
JOIN articles a ON ac.article_id = a.id
JOIN sources s ON a.source_id = s.id
WHERE fn.published = 0
ORDER BY fn.created_at DESC;
```

## Acceso Directo

Puedes acceder directamente a la base de datos:

```bash
sqlite3 data/news.db

# Comandos útiles
.tables                    # Listar tablas
.schema articles           # Ver esquema de tabla
.schema flash_news         # Ver esquema de flash news
SELECT * FROM articles;    # Consultar datos
.quit                      # Salir
```
