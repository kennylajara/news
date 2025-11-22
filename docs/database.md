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
- `enrich_article`: Enriquecimiento de artículos (clustering semántico)
- `analyze_article`: Análisis de artículos con OpenAI (extracción de entidades + análisis temático)
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
| html_path | VARCHAR(500) | NULLABLE | Ruta al archivo HTML guardado (si existe) |
| cleaned_html_hash | VARCHAR(64) | NULLABLE | SHA-256 del HTML limpio (detección de cambios) |
| enriched_at | DATETIME | NULLABLE, INDEX | Fecha de enriquecimiento (NULL = no enriquecido) |
| cluster_enriched_at | DATETIME | NULLABLE, INDEX | Fecha de clustering semántico (NULL = sin clustering) |
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

### Tabla: `article_analyses`

Análisis profundo de artículos generado por OpenAI para sistema de recomendaciones.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY | ID auto-incremental |
| article_id | INTEGER | FOREIGN KEY, UNIQUE, NOT NULL, INDEX | ID del artículo (relación 1:1) |
| key_concepts | JSON | NOT NULL | Lista de conceptos clave (strings) |
| semantic_relations | JSON | NOT NULL | Lista de relaciones semánticas {subject, predicate, object} |
| narrative_frames | JSON | NOT NULL | Lista de marcos narrativos (enums) |
| editorial_tone | VARCHAR(50) | NOT NULL | Tono editorial |
| style_descriptors | JSON | NOT NULL | Lista de descriptores de estilo (strings) |
| controversy_score | INTEGER | NOT NULL | Score de controversia (0-100) |
| political_bias | INTEGER | NOT NULL | Sesgo político (-100 a 100) |
| has_named_sources | INTEGER | NOT NULL, DEFAULT 0 | Tiene fuentes nombradas (0=no, 1=sí) |
| has_data_or_statistics | INTEGER | NOT NULL, DEFAULT 0 | Contiene datos/estadísticas (0=no, 1=sí) |
| has_multiple_perspectives | INTEGER | NOT NULL, DEFAULT 0 | Presenta múltiples perspectivas (0=no, 1=sí) |
| quality_score | INTEGER | NOT NULL | Score de calidad (0-100) |
| content_format | VARCHAR(50) | NOT NULL | Formato de contenido |
| temporal_relevance | VARCHAR(50) | NOT NULL | Relevancia temporal |
| audience_education | VARCHAR(50) | NOT NULL | Nivel educativo del público objetivo |
| target_age_range | VARCHAR(50) | NOT NULL | Rango de edad objetivo |
| target_professions | JSON | NOT NULL | Lista de profesiones objetivo (strings) |
| required_interests | JSON | NOT NULL | Lista de intereses requeridos (strings) |
| relevant_industries | JSON | NOT NULL | Lista de industrias relevantes (strings) |
| geographic_scope | VARCHAR(50) | NOT NULL | Alcance geográfico |
| cultural_context | VARCHAR(100) | NOT NULL | Contexto cultural |
| voices_represented | JSON | NOT NULL | Lista de voces representadas {type, stance} |
| source_diversity_score | INTEGER | NOT NULL | Score de diversidad de fuentes (0-100) |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Última actualización |

**Valores de `content_format`**:
- `news`: Noticia estándar
- `feature`: Reportaje en profundidad
- `opinion`: Artículo de opinión
- `analysis`: Análisis experto
- `interview`: Entrevista
- `listicle`: Artículo tipo lista

**Valores de `temporal_relevance`**:
- `breaking`: Noticias de última hora
- `timely`: Relevante en el momento actual
- `evergreen`: Contenido atemporal

**Relaciones**:
- 1:1 con `articles` (un análisis pertenece a un artículo)

**Restricciones**:
- `article_id` UNIQUE: Solo un análisis por artículo
- `article_id` ON DELETE CASCADE: Si se elimina el artículo, se elimina el análisis

**Generación**:
- Proceso `analyze_article` usando OpenAI con Structured Outputs
- Extrae entidades nombradas Y genera análisis profundo
- Idempotente: detecta y salta artículos que ya tienen análisis

**Uso**:
- Permite matching avanzado para sistema de recomendaciones
- Filtrado por tono, formato, audiencia, industria, etc.
- Búsqueda por conceptos clave y relaciones semánticas

**Índices**:
- `article_id` (UNIQUE): Garantiza un solo análisis por artículo
- `created_at`: Para ordenamiento cronológico

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
| name | VARCHAR(255) | NOT NULL, INDEX | Nombre de la entidad |
| name_length | INTEGER | NOT NULL, INDEX | Longitud del nombre (para ordenamiento) |
| entity_type | ENUM | NOT NULL, INDEX | Tipo de entidad |
| detected_types | JSON | NULLABLE | Lista de tipos detectados por spaCy para esta entidad |
| classified_as | ENUM | NOT NULL, DEFAULT 'canonical', INDEX | Clasificación para desambiguación |
| is_group | INTEGER | NOT NULL, DEFAULT 0, INDEX | Flag de grupo (0=no, 1=yes) - solo para CANONICAL |
| description | TEXT | NULLABLE | Descripción de la entidad |
| photo_url | VARCHAR(500) | NULLABLE | URL de la foto de la entidad |
| article_count | INTEGER | NOT NULL, DEFAULT 0 | Número de artículos que mencionan esta entidad |
| avg_local_relevance | FLOAT | NULLABLE, DEFAULT 0.0 | Promedio de relevancia local en artículos |
| diversity | INTEGER | NOT NULL, DEFAULT 0 | Número de entidades únicas con las que co-ocurre |
| pagerank | FLOAT | NULLABLE, DEFAULT 0.0 | Score PageRank raw (sin normalizar) |
| global_relevance | FLOAT | NULLABLE, DEFAULT 0.0, INDEX | PageRank normalizado (0.0-1.0, min-max scaled) |
| last_rank_calculated_at | DATETIME | NULLABLE, INDEX | Última vez que se calculó ranking global |
| last_review_type | VARCHAR(20) | NOT NULL, DEFAULT 'none', INDEX | Tipo de última revisión (none/algorithmic/ai-assisted/manual) |
| is_approved | INTEGER | NOT NULL, DEFAULT 0, INDEX | Estado de aprobación (0=pendiente, 1=aprobado) |
| last_review | DATETIME | NULLABLE, INDEX | Última vez que la entidad fue revisada |
| trend | INTEGER | NOT NULL, DEFAULT 0 | Score de tendencia (-100 a 100) |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Última actualización |

**Valores de `classified_as`** (clasificación para desambiguación):
- `canonical`: Entidad principal/verdadera (default)
- `alias`: Variante o alias de otra entidad canónica
- `ambiguous`: Entidad ambigua que puede referirse a múltiples entidades canónicas
- `not_an_entity`: Falso positivo (no es realmente una entidad)

**Valores de `entity_type`** (extraídos por OpenAI en `analyze_article`):
- `PERSON`: Personas (individuos específicos)
- `ORG`: Organizaciones (empresas, agencias, instituciones, partidos políticos)
- `GPE`: Ubicaciones geopolíticas (países, ciudades, estados)
- `EVENT`: Eventos (huracanes, batallas, conferencias, festivales)
- `PRODUCT`: Productos (objetos, vehículos, servicios, software)
- `NORP`: Nacionalidades, grupos religiosos o políticos

**Nota**: Los tipos están en mayúsculas según la nomenclatura de OpenAI. El sistema de extracción anterior (spaCy) usaba 18 tipos, pero fue removido en favor de extracción AI más precisa.

**Campos clave**:
- `name_length`: Longitud del nombre, usado para ordenar entidades por especificidad (nombres más largos = más específicos)
- `detected_types`: Lista JSON de todos los tipos detectados para esta entidad (útil para identificar inconsistencias o multi-clasificación)
- `classified_as`: Clasificación para desambiguación (canonical/alias/ambiguous/not_an_entity)
- `is_group`: Flag de grupo (solo significativo para entidades CANONICAL)
  - 0 = Entidad individual normal (persona, organización)
  - 1 = Entidad de grupo (banda, equipo, consejo) que puede tener miembros
- `article_count`: Número de artículos que mencionan esta entidad (actualizado durante reranking)
- `avg_local_relevance`: Promedio de relevancia local en todos los artículos donde aparece
- `diversity`: Número de entidades únicas con las que co-ocurre (mide conectividad en el grafo)
- `last_review_type`: Tipo de última revisión aplicada a la entidad
  - `none`: Sin revisión (entidad recién creada)
  - `algorithmic`: Revisión automática por algoritmo
  - `ai-assisted`: Revisión asistida por IA (OpenAI)
  - `manual`: Revisión manual por usuario
- `is_approved`: Estado de aprobación de la entidad
  - 0 = Pendiente de revisión/aprobación
  - 1 = Aprobada (confiable para uso en producción)
- `last_review`: Timestamp de última revisión
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

**Restricciones**:
- UNIQUE INDEX en `(name, entity_type)`: Permite mismo nombre con diferentes tipos (ej: "Apple" como PERSON y ORG)

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

**Campo `origin`**: Distingue entre entidades extraídas vs agregadas por desambiguación
- `ai_analysis`: Detectada por OpenAI durante `analyze_article`
- `classification`: Agregada automáticamente por el sistema de clasificación (ej: canonical de un alias)

**Campo `context_sentences`**: Oraciones donde aparece la entidad (útil para revisión manual)

**Índices**:
- `article_id`: Para buscar todas las entidades de un artículo
- `(article_id, origin)` compuesto: Para recalculación eficiente (filtrar solo AI_ANALYSIS)
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

### Tabla: `entity_group_members`

Tabla para gestionar membresías de grupos con tracking temporal.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | ID único de la membresía |
| group_id | INTEGER | FOREIGN KEY, NOT NULL | ID del grupo (entidad con is_group=1) |
| member_id | INTEGER | FOREIGN KEY, NOT NULL | ID del miembro |
| role | VARCHAR(100) | NULLABLE | Rol dentro del grupo (ej: "vocalist", "CEO", "minister") |
| since | DATETIME | NULLABLE, INDEX | Fecha de inicio (NULL = desconocido/siempre) |
| until | DATETIME | NULLABLE, INDEX | Fecha de fin (NULL = presente/activo) |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | Fecha de creación del registro |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | Última actualización |

**Propósito**: Relaciona grupos con sus miembros con información temporal.

**Ejemplos de uso:**
- Romeo Santos en Aventura: `(group_id=AVENTURA, member_id=ROMEO, since=1997-01-01, until=2011-07-01, role="vocalist")`
- Wisin en Wisin & Yandel (activo): `(group_id=WISIN_YANDEL, member_id=WISIN, since=1998-01-01, until=NULL)`

**Restricciones:**
- PK: `id` (auto-incremental, permite múltiples períodos para el mismo par group-member)
- `group_id` ON DELETE CASCADE (si se elimina el grupo, se eliminan sus membresías)
- `member_id` ON DELETE CASCADE (si se elimina el miembro, se eliminan sus membresías)

**Validación de overlaps:**
- El sistema valida que no haya períodos superpuestos para el mismo `(group_id, member_id)`
- Una persona no puede estar en el grupo dos veces al mismo tiempo
- Validación implementada en `NamedEntity.add_member()` método

**Índices:**
- `group_id`: Para buscar miembros de un grupo
- `member_id`: Para buscar grupos de un miembro
- `(group_id, member_id, since, until)`: Para queries temporales eficientes

**Relaciones:**
- N:M entre `named_entities` (self-join con is_group=1)

### Tabla: `entity_pair_comparisons`

Tabla de tracking de comparaciones AI 1v1 entre pares de entidades para evitar re-testing.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | ID único de la comparación |
| entity_a_id | INTEGER | FOREIGN KEY, NOT NULL | ID de la primera entidad del par |
| entity_b_id | INTEGER | FOREIGN KEY, NOT NULL | ID de la segunda entidad del par |
| relationship | VARCHAR(20) | NOT NULL | Resultado de la comparación |
| confidence | FLOAT | NOT NULL | Nivel de confianza (0.0-1.0) |
| reasoning | TEXT | NULLABLE | Razonamiento del LLM |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | Última actualización |

**Propósito**: Cachear resultados de comparaciones AI para evitar consultas duplicadas a OpenAI.

**Valores de `relationship`**:
- `SAME`: Las entidades son la misma persona/organización/lugar (entity_a es alias de entity_b)
- `DIFFERENT`: Las entidades son completamente diferentes
- `AMBIGUOUS`: No se puede determinar con certeza (requiere más contexto)

**Restricciones**:
- PK: `id` (auto-incremental)
- UNIQUE INDEX: `(entity_a_id, entity_b_id)` - evita comparar el mismo par dos veces
- `entity_a_id` ON DELETE CASCADE (si se elimina la entidad, se eliminan sus comparaciones)
- `entity_b_id` ON DELETE CASCADE (si se elimina la entidad, se eliminan sus comparaciones)

**Orden de IDs**: La restricción UNIQUE asume que `entity_a_id < entity_b_id` (normalización implementada en la lógica de negocio)

**Índices**:
- `(entity_a_id, entity_b_id)`: UNIQUE INDEX para búsqueda rápida y prevención de duplicados
- `created_at`: Para ordenar por antigüedad

**Uso en clasificación AI**:
1. LSH identifica candidatos similares (threshold de similitud de embeddings)
2. Sistema verifica si el par ya fue comparado en esta tabla
3. Si existe: reutiliza resultado (evita llamada a OpenAI)
4. Si no existe: llama a OpenAI y guarda resultado
5. Aplica clasificación basada en `relationship` y `confidence`

**Relaciones**:
- N:1 con `named_entities` (vía `entity_a_id`)
- N:1 con `named_entities` (vía `entity_b_id`)

### Tabla: `entity_tokens`

Índice inverso de tokens de entidades para matching eficiente por tokens individuales.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | ID único del token |
| entity_id | INTEGER | FOREIGN KEY, NOT NULL, INDEX | ID de la entidad a la que pertenece |
| token | VARCHAR(100) | NOT NULL | Token original con formato (ej: "J.C.E.", "Junta") |
| token_normalized | VARCHAR(100) | NOT NULL, INDEX | Token normalizado (minúsculas, sin acentos, sin puntos) |
| position | INTEGER | NOT NULL | Posición en el nombre de la entidad (0-indexed) |
| is_stopword | INTEGER | NOT NULL, DEFAULT 0 | Flag de stopword (0=no, 1=sí) |
| seems_like_initials | INTEGER | NOT NULL, DEFAULT 0, INDEX | Flag de iniciales (0=no, 1=sí) - todas mayúsculas, token único |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | Fecha de creación |

**Propósito**: Permite matching eficiente de entidades por tokens individuales durante clasificación automática.

**Ejemplos de tokenización:**
```
"Luis Abinader" → [
  {token: "Luis", token_normalized: "luis", position: 0, is_stopword: 0, seems_like_initials: 0},
  {token: "Abinader", token_normalized: "abinader", position: 1, is_stopword: 0, seems_like_initials: 0}
]

"J.C.E." → [
  {token: "J.C.E.", token_normalized: "jce", position: 0, is_stopword: 0, seems_like_initials: 1}
]

"Ministerio de Economía" → [
  {token: "Ministerio", token_normalized: "ministerio", position: 0, is_stopword: 0, seems_like_initials: 0},
  {token: "de", token_normalized: "de", position: 1, is_stopword: 1, seems_like_initials: 0},
  {token: "Economía", token_normalized: "economia", position: 2, is_stopword: 0, seems_like_initials: 0}
]
```

**Uso en clasificación**:
- Buscar candidatos que compartan tokens normalizados
- Identificar iniciales (ej: "JCE" → "Junta Central Electoral")
- Filtrar stopwords para mejorar precisión
- Ordenar por posición para matching contextual

**Restricciones**:
- `entity_id` ON DELETE CASCADE (si se elimina la entidad, se eliminan sus tokens)

**Índices**:
- `entity_id`: Para buscar todos los tokens de una entidad
- `(token_normalized, entity_id)`: COMPOSITE INDEX para búsqueda rápida por token
- `seems_like_initials`: Para filtrar entidades que parecen iniciales

**Relaciones**:
- N:1 con `named_entities`

### Tabla: `entity_classification_suggestions`

Sugerencias de clasificación AI para auditoría y revisión manual.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | ID único de la sugerencia |
| entity_id | INTEGER | FOREIGN KEY, NOT NULL, INDEX | ID de la entidad clasificada |
| suggested_classification | VARCHAR(20) | NOT NULL | Clasificación sugerida (canonical/alias/ambiguous/not_an_entity) |
| suggested_canonical_ids | JSON | NULLABLE | Array de IDs canónicos (para alias/ambiguous) |
| confidence | FLOAT | NOT NULL, INDEX | Nivel de confianza (0.0-1.0) |
| reasoning | TEXT | NOT NULL | Explicación del LLM para la clasificación |
| alternative_classification | VARCHAR(20) | NULLABLE | Clasificación alternativa (si el LLM estaba indeciso) |
| alternative_confidence | FLOAT | NULLABLE | Confianza de la alternativa |
| applied | INTEGER | NOT NULL, DEFAULT 0, INDEX | Estado de aplicación (0=solo sugerencia, 1=aplicada) |
| approved_by_user | INTEGER | NULLABLE, INDEX | Aprobación del usuario (NULL=pendiente, 0=rechazada, 1=aprobada) |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | Fecha de creación |

**Propósito**: Registra todas las sugerencias de clasificación AI para auditoría, análisis y mejora del sistema.

**Flujo de uso**:
1. Sistema AI analiza entidad y genera sugerencia
2. Se guarda en esta tabla con `applied=0`, `approved_by_user=NULL`
3. Usuario revisa sugerencia (comando `news entity review`)
4. Usuario aprueba (`approved_by_user=1`) o rechaza (`approved_by_user=0`)
5. Si se aprueba, la clasificación se aplica (`applied=1`)

**Valores de `suggested_classification`**:
- `canonical`: Entidad es única y válida
- `alias`: Entidad es alias/variante de otra(s) canónica(s)
- `ambiguous`: Entidad puede referirse a múltiples entidades canónicas
- `not_an_entity`: Falso positivo (no es realmente una entidad)

**Campo `reasoning`**: Contiene la explicación del LLM en texto natural, útil para:
- Entender por qué el sistema tomó esa decisión
- Detectar patrones en errores del modelo
- Mejorar prompts de clasificación

**Restricciones**:
- `entity_id` ON DELETE CASCADE (si se elimina la entidad, se eliminan sus sugerencias)

**Índices**:
- `entity_id`: Para ver todas las sugerencias de una entidad
- `applied`: Para filtrar sugerencias pendientes de aplicar
- `confidence`: Para ordenar por nivel de confianza
- `approved_by_user`: Para filtrar por estado de revisión

**Relaciones**:
- N:1 con `named_entities`

**Uso para mejora del sistema**:
```sql
-- Sugerencias con baja confianza que fueron aprobadas (modelo conservador)
SELECT * FROM entity_classification_suggestions
WHERE confidence < 0.7 AND approved_by_user = 1;

-- Sugerencias con alta confianza que fueron rechazadas (modelo equivocado)
SELECT * FROM entity_classification_suggestions
WHERE confidence > 0.9 AND approved_by_user = 0;
```

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

# Guardar artículo (falla si ya existe con mismo hash)
article_data = {
    "title": "Título",
    "content": "Contenido en Markdown",
    "tags": ["política", "economía"],
    "_metadata": {
        "url": "https://example.com/article",
        "domain": "example.com",
        "hash": "abc123..."
    }
}
article = db.save_article(session, article_data, "example.com")

# Guardar o actualizar artículo (upsert - recomendado)
article, was_updated = db.save_or_update_article(session, article_data, "example.com")
if was_updated:
    print(f"Article {article.id} updated")
else:
    print(f"Article {article.id} created")

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

## Upsert de Artículos

### `save_or_update_article()`

Este método implementa el patrón "upsert" (create or update) para artículos:

**Comportamiento:**
1. Busca artículo existente por **hash** o **URL**
2. Si existe: **actualiza** todos los campos (título, contenido, tags, etc.) y marca `updated_at`
3. Si no existe: **crea** nuevo artículo
4. Retorna tupla `(Article, was_updated: bool)`

**Detección inteligente de cambios de contenido:**
- Compara el `cleaned_html_hash` (SHA-256 del HTML limpio) entre el artículo existente y el nuevo
- Si el hash **es diferente** o no existe: resetea `enriched_at` y `cluster_enriched_at` (requiere re-procesamiento)
- Si el hash **es idéntico**: preserva el estado de enriquecimiento (evita re-procesamiento innecesario)
- Se puede forzar el reseteo con `force_reprocess=True` (útil al mejorar algoritmos de enriquecimiento: NER, clustering, ...)

**Ventajas sobre `save_article()`:**
- ✅ No falla si el artículo ya existe (idempotente)
- ✅ Permite re-procesar artículos sin errores
- ✅ Útil para actualizar contenido que cambió en el sitio
- ✅ Indica si fue creación o actualización
- ✅ Evita re-enriquecimiento innecesario cuando el contenido no cambió

**Cuándo usar cada uno:**

| Método | Cuándo usar |
|--------|-------------|
| `save_article()` | Cuando **sabes** que el artículo no existe |
| `save_or_update_article()` | Cuando **no sabes** si existe (recomendado para comandos CLI) |

**Ejemplo:**

```python
# Escenario: Re-procesar artículos desde caché
article_data = {
    "title": "Título actualizado",
    "content": "Nuevo contenido",
    "tags": ["tag1", "tag2"],
    "_metadata": {
        "url": "https://example.com/article",
        "domain": "example.com",
        "hash": "abc123def456...",
        "cleaned_html_hash": "def789abc123..."  # SHA-256 del HTML limpio
    }
}

# Primera vez: crea
article, was_updated = db.save_or_update_article(session, article_data, "example.com")
print(f"Created: {article.id}")  # was_updated = False

# Segunda vez (mismo hash/URL, mismo contenido): actualiza pero preserva enriquecimiento
article, was_updated = db.save_or_update_article(session, article_data, "example.com")
print(f"Updated: {article.id}")  # was_updated = True, enriched_at preservado

# Tercera vez (contenido cambió): actualiza y resetea enriquecimiento
article_data["_metadata"]["cleaned_html_hash"] = "xyz999..."  # Hash diferente
article, was_updated = db.save_or_update_article(session, article_data, "example.com")
print(f"Updated: {article.id}")  # enriched_at = None (requiere re-procesamiento)

# Forzar reseteo (útil al mejorar algoritmos)
article, was_updated = db.save_or_update_article(
    session, article_data, "example.com", force_reprocess=True
)
# enriched_at = None (incluso si el contenido no cambió)
```

**Campos actualizados:**
- `title`, `subtitle`, `author`, `published_date`, `location`
- `content`, `category`, `cleaned_html_hash`
- `tags` (se reemplazan completamente)
- `updated_at` (automático)

**Campos actualizados condicionalmente:**
- `enriched_at`, `cluster_enriched_at`: se resetean a NULL solo si:
  - El contenido cambió (hashes diferentes), **O**
  - Se especificó `force_reprocess=True`

**Campos NO actualizados:**
- `id` (preserva el ID original)
- `created_at` (preserva fecha de creación original)

## Cascade Deletes

- Eliminar un `Source` → Se eliminan todos sus `Articles`
- Eliminar un `Article` → Se eliminan sus asociaciones en `article_tags`
- Eliminar un `Tag` → Se eliminan sus asociaciones en `article_tags`

### Tabla: `article_clusters`

Clusters semánticos de oraciones dentro de un artículo (core, secondary, filler).

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | ID único del cluster |
| article_id | INTEGER | FOREIGN KEY, NOT NULL, INDEX | ID del artículo al que pertenece |
| cluster_label | INTEGER | NOT NULL | Etiqueta del cluster (0, 1, 2... o -1 para ruido) |
| category | ENUM | NOT NULL, INDEX | Categoría del cluster (core/secondary/filler) |
| score | FLOAT | NOT NULL, DEFAULT 0.0, INDEX | Score de importancia (0.0-1.0) |
| size | INTEGER | NOT NULL, DEFAULT 0 | Número de oraciones en el cluster |
| centroid_embedding | JSON | NULLABLE | Vector embedding del centroide (lista de floats) |
| sentence_indices | JSON | NOT NULL | Lista de índices de oraciones [0, 3, 5...] |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Última actualización |

**Propósito**: Agrupa oraciones semánticamente similares dentro de un artículo para identificar temas principales, secundarios y relleno.

**Valores de `category`**:
- `core`: Tema principal del artículo (lo más importante)
- `secondary`: Temas relacionados importantes
- `filler`: Información contextual, relleno o menos relevante

**Proceso de generación** (en `enrich_article`):
1. Extraer todas las oraciones del artículo
2. Generar embeddings con `paraphrase-multilingual-MiniLM-L12-v2`
3. Reducir dimensionalidad con UMAP
4. Clustering con HDBSCAN
5. Clasificar clusters por importancia (core/secondary/filler)
6. Guardar cluster con centroide e índices de oraciones

**Campo `cluster_label`**:
- `-1`: Ruido (oraciones que no pertenecen a ningún cluster coherente)
- `0, 1, 2...`: Clusters identificados

**Campo `score`**: Importancia del cluster (0.0 a 1.0)
- Calculado basado en: tamaño, cohesión semántica, posición en artículo
- Clusters `core` tienen scores más altos

**Restricciones**:
- `article_id` ON DELETE CASCADE (si se elimina el artículo, se eliminan sus clusters)

**Índices**:
- `article_id`: Para buscar todos los clusters de un artículo
- `category`: Para filtrar por tipo de cluster
- `score`: Para ordenar por importancia

**Relaciones**:
- N:1 con `articles`
- 1:N con `article_sentences`
- 1:1 con `flash_news` (solo clusters CORE pueden tener flash news)

**Uso típico**:
```sql
-- Obtener tema principal de un artículo
SELECT * FROM article_clusters
WHERE article_id = 123 AND category = 'core'
ORDER BY score DESC
LIMIT 1;
```

### Tabla: `article_sentences`

Oraciones individuales de un artículo con su asignación de cluster y embedding.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY, AUTO_INCREMENT | ID único de la oración |
| article_id | INTEGER | FOREIGN KEY, NOT NULL, INDEX | ID del artículo al que pertenece |
| sentence_index | INTEGER | NOT NULL | Posición en el artículo (0-based) |
| sentence_text | TEXT | NOT NULL | Texto de la oración |
| cluster_id | INTEGER | FOREIGN KEY, NULLABLE, INDEX | ID del cluster asignado (NULL si es ruido) |
| embedding | JSON | NULLABLE | Vector embedding de la oración (lista de floats) |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación |

**Propósito**: Almacena cada oración del artículo con su embedding semántico y asignación de cluster.

**Proceso de generación** (en `enrich_article`):
1. Dividir contenido del artículo en oraciones (tokenización)
2. Generar embedding para cada oración (sentence-transformers)
3. Ejecutar clustering (UMAP + HDBSCAN)
4. Asignar cada oración a su cluster correspondiente
5. Guardar oración con su embedding y cluster_id

**Campo `cluster_id`**:
- `NULL`: Oración clasificada como ruido (no pertenece a ningún cluster coherente)
- `ID`: Oración pertenece al cluster especificado

**Campo `embedding`**: Vector de alta dimensión (ej: 384 floats) que representa el significado semántico de la oración
- Permite búsqueda semántica
- Permite reclustering sin reprocesar

**Restricciones**:
- `article_id` ON DELETE CASCADE (si se elimina el artículo, se eliminan sus oraciones)
- `cluster_id` ON DELETE SET NULL (si se elimina el cluster, oraciones quedan huérfanas)

**Índices**:
- `article_id`: Para buscar todas las oraciones de un artículo
- `(article_id, sentence_index)`: COMPOSITE para ordenar oraciones por posición
- `cluster_id`: Para buscar todas las oraciones de un cluster

**Relaciones**:
- N:1 con `articles`
- N:1 con `article_clusters`

**Uso típico**:
```sql
-- Obtener oraciones del tema principal de un artículo
SELECT s.sentence_text
FROM article_sentences s
JOIN article_clusters c ON s.cluster_id = c.id
WHERE c.article_id = 123 AND c.category = 'core'
ORDER BY s.sentence_index;
```

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
