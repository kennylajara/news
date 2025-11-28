# Arquitectura

## Flujo de Componentes

```
Usuario → CLI (Click) → get_news.py → Cache DB (opcional) → HTTP Download → Extractor (plugin) → Main Database (SQLite)
```

### Archivos Clave

- `src/cli.py` - Punto de entrada del CLI, enruta a grupos de comandos
- `src/commands/article.py` - Comandos de gestión de artículos
- `src/commands/domain.py` - Comandos de gestión de fuentes/dominios
- `src/commands/process.py` - Comandos de procesamiento por batches (clustering, NER, flash news)
- `src/commands/entity.py` - Comandos de gestión de entidades nombradas
- `src/commands/flash.py` - Comandos de gestión de flash news
- `src/commands/cache.py` - Comandos de gestión de caché de URLs
- `src/commands/export.py` - Comandos de exportación de datos (corpus, etc.)
- `src/commands/email.py` - Comandos de gestión de correos electrónicos
- `src/get_news.py` - Orquestación principal: descargar → limpiar → extraer → guardar
- `src/db/database.py` - Fachada de base de datos con operaciones CRUD
- `src/db/models.py` - Modelos SQLAlchemy (Source, Article, Tag, NamedEntity, ArticleCluster, FlashNews, etc.)
- `src/db/cache.py` - Base de datos de caché para contenido HTML de URLs
- `src/extractors/{domain}_com.py` - Extractores de contenido específicos por dominio
- `src/processors/enrich.py` - Enriquecimiento: clustering semántico de oraciones
- `src/processors/article_analysis.py` - Análisis profundo con OpenAI (extracción de entidades + análisis temático)
- `src/processors/flash_news.py` - Generación de resúmenes narrativos con LLM
- `src/processors/clustering.py` - Funciones de clustering semántico (UMAP + HDBSCAN)
- `src/processors/entity_ai_classification.py` - Clasificación AI de entidades (LSH + pairwise)
- `src/processors/entity_lsh_matcher.py` - Matching de entidades similares con LSH
- `src/processors/tokenization.py` - Tokenización de entidades para matching
- `src/domain/entity_rank.py` - Cálculo de PageRank para entidades
- `src/domain/calculate_global_relevance.py` - Cálculo de relevancia global
- `src/email_system/client.py` - Cliente SMTP para envío de correos
- `src/email_system/renderer.py` - Renderizado de templates Jinja2 para emails
- `src/email_system/service.py` - Servicio de alto nivel para emails
- `src/email_system/logging.py` - Sistema de logging de correos enviados
- `src/llm/logging.py` - Sistema de logging de llamadas a APIs de LLM

## Pipeline de Descarga de Artículos

1. **Verificación de Caché**: Verificar si existe en cache.db (a menos que se use `--cache-no-read`)
2. **Descarga**: HTTP GET con encabezado User-Agent (si no está en caché)
3. **Guardado en Caché**: Guardar HTML original en cache.db (a menos que se use `--cache-no-save`)
4. **Limpieza**: Eliminar scripts, estilos, formularios, comentarios; normalizar espacios; preservar solo atributos id/class/href
5. **Extracción**: Cargar extractor específico del dominio vía importación dinámica
6. **Parseo**: Usar selectores CSS para extraer datos estructurados, convertir HTML → Markdown
7. **Almacenamiento**: Guardar en news.db con relaciones (source, tags)

## Base de Datos

### Esquema

```
sources (1:N articles, 1:N domain_processes, 1:N processing_batches)
  ├─ id, domain (unique), name, created_at, updated_at

articles (N:1 source, M:N tags, M:N named_entities, 1:N article_clusters, 1:N article_sentences, 1:1 article_analyses)
  ├─ id, hash (SHA-256, unique), url, source_id
  ├─ title, subtitle, author, published_date, location, category
  ├─ content (Markdown), html_path, cleaned_html_hash
  ├─ clusterized_at, created_at, updated_at

tags (M:N articles via article_tags)
  ├─ id, name (unique), created_at, updated_at

article_tags (tabla de asociación)
  ├─ article_id, tag_id

named_entities (M:N articles via article_entities, M:N canonical refs via entity_canonical_refs, M:N group members via entity_group_members, 1:N entity_tokens)
  ├─ id, name, name_length, entity_type, detected_types, classified_as, is_group
  ├─ description, photo_url, article_count, avg_local_relevance, diversity
  ├─ pagerank, global_relevance, last_rank_calculated_at
  ├─ last_review_type, is_approved, last_review, trend, created_at, updated_at

article_entities (tabla de asociación con metadata)
  ├─ article_id, entity_id, mentions, relevance, origin, context_sentences

entity_canonical_refs (tabla de asociación para desambiguación)
  ├─ entity_id, canonical_id

articles_needs_rerank (tabla de tracking)
  ├─ article_id, created_at

entity_group_members (tabla de membresías con tracking temporal)
  ├─ id, group_id, member_id, role, since, until, created_at, updated_at

entity_tokens (N:1 named_entities - índice inverso para matching)
  ├─ id, entity_id, token, token_normalized, position
  ├─ is_stopword, seems_like_initials, created_at

entity_pair_comparisons (tracking de comparaciones AI 1v1)
  ├─ id, entity_a_id, entity_b_id, relationship, confidence
  ├─ reasoning, created_at, updated_at

entity_classification_suggestions (sugerencias AI para auditoría)
  ├─ id, entity_id, suggested_classification, suggested_canonical_ids
  ├─ confidence, reasoning, alternative_classification, alternative_confidence
  ├─ applied, approved_by_user, created_at

article_clusters (N:1 article, 1:1 flash_news)
  ├─ id, article_id, cluster_label, category, score, size
  ├─ centroid_embedding, sentence_indices, created_at, updated_at

article_sentences (N:1 article, N:1 article_clusters)
  ├─ id, article_id, sentence_index, sentence_text
  ├─ cluster_id, embedding, created_at

flash_news (1:1 article_clusters)
  ├─ id, cluster_id (unique), summary, embedding
  ├─ published, created_at, updated_at

article_analyses (1:1 articles - análisis profundo para recomendaciones)
  ├─ id, article_id (unique), key_concepts, semantic_relations, narrative_frames
  ├─ editorial_tone, style_descriptors, controversy_score, political_bias
  ├─ has_named_sources, has_data_or_statistics, has_multiple_perspectives, quality_score
  ├─ content_format, temporal_relevance, audience_education, target_age_range
  ├─ target_professions, required_interests, relevant_industries
  ├─ geographic_scope, cultural_context, voices_represented, source_diversity_score
  ├─ created_at, updated_at

domain_processes (N:1 source)
  ├─ source_id, process_type, last_processed_at, created_at, updated_at

processing_batches (N:1 source, 1:N batch_items)
  ├─ id, source_id, process_type, status
  ├─ total_items, processed_items, successful_items, failed_items
  ├─ error_message, stats (JSON), started_at, completed_at
  ├─ created_at, updated_at

batch_items (N:1 processing_batches, N:1 articles)
  ├─ id, batch_id, article_id, status
  ├─ error_message, logs, stats (JSON)
  ├─ started_at, completed_at, created_at, updated_at
```

### Deduplicación

Se usa hash SHA-256 de la URL para prevenir re-descargas. El hash es único e indexado para búsquedas rápidas.

## Sistema de Caché de URLs

El sistema incluye una base de datos de caché separada (`data/cache.db`) para almacenar el contenido HTML original de las URLs descargadas. Esto es especialmente útil durante desarrollo cuando se borra y re-crea la base de datos principal.

### Características:

- **Caché persistente**: Contenido HTML se guarda en SQLite separado
- **Indexado por hash**: URL hash SHA-256 para búsqueda rápida
- **Metadata**: Guarda domain, status_code, content_length, created_at, accessed_at
- **Control granular**: Flags `--cache-no-read` y `--cache-no-save` en comandos
- **Por defecto habilitado**: Todas las descargas usan caché automáticamente
- **Gestión**: Comandos `news cache stats`, `news cache domains`, `news cache clear`

### Esquema de cache.db:

```
url_cache
  ├─ id (PK)
  ├─ url_hash (SHA-256, unique, indexed)
  ├─ url (text)
  ├─ domain (indexed)
  ├─ content (text, HTML original)
  ├─ status_code (int)
  ├─ content_length (int)
  ├─ created_at (indexed)
  ├─ accessed_at (indexed, actualizado en cada lectura)
```

### Uso:

```bash
# Fetch normal (usa caché)
news article fetch "https://example.com/article"

# Forzar descarga fresca (ignorar caché)
news article fetch "https://example.com/article" --cache-no-read

# Descargar pero no guardar en caché
news article fetch "https://example.com/article" --cache-no-save

# Ver estadísticas de caché
news cache stats
news cache stats --domain diariolibre.com

# Limpiar caché
news cache clear --domain diariolibre.com
```

### Esquema de llm_logs.db (base de datos de logs):

Base de datos separada para logging de operaciones del sistema. Contiene:

```
llm_api_calls (logs de llamadas a APIs de LLM)
  ├─ id (PK)
  ├─ call_type (tipo de llamada: structured_output, chat_completion)
  ├─ task_name (nombre del task: article_analysis, etc.)
  ├─ model (modelo usado: gpt-5-nano, etc.)
  ├─ started_at, completed_at, duration_seconds
  ├─ input_tokens, output_tokens, total_tokens
  ├─ system_prompt, user_prompt, messages (JSON)
  ├─ response_raw, parsed_output (JSON)
  ├─ success (1=success, 0=error)
  ├─ error_message, context_data (JSON)

email_logs (logs de correos enviados)
  ├─ id (PK)
  ├─ template_id (FK a EmailTemplate, nullable)
  ├─ recipient (email del destinatario)
  ├─ subject (asunto del correo)
  ├─ status (PENDING, SENT, FAILED)
  ├─ error_message (si falló)
  ├─ context_data (variables del template, JSON)
  ├─ sent_at (timestamp de envío)
  ├─ created_at, updated_at

pagerank_executions (logs de ejecuciones de PageRank)
  ├─ id (PK)
  ├─ started_at, completed_at, duration_seconds
  ├─ damping, max_iter, tolerance, min_relevance_threshold
  ├─ total_articles, total_entities, graph_edges
  ├─ iterations, converged, entities_ranked
  ├─ success, error_message
```

**Nota**: Los templates de email se guardan en la base de datos principal (`news.db`) en la tabla `email_templates`, pero los logs de envío van en `llm_logs.db` para mantener separadas las operaciones de negocio del logging del sistema.

### Uso de logs:

```bash
# Ver logs de LLM
news llm logs --limit 20
news llm logs --task article_analysis
news llm logs --status error

# Ver logs de emails
news email logs --limit 20
news email logs --status failed
news email logs --recipient user@example.com
```

## Patrones Importantes

1. **Carga dinámica de extractores**: Los extractores se importan en tiempo de ejecución según el dominio
2. **Patrón get-or-create**: Los métodos de base de datos auto-crean Sources y Tags si no existen
3. **Cascade deletes**: Eliminar Source remueve todos sus Articles; eliminar Article remueve asociaciones de tags
4. **Deduplicación de artículos**: Verifica `article_exists(url, hash)` antes de guardar en news.db
5. **Caché de HTML**: Verifica cache.db antes de HTTP request para evitar re-descargas
6. **Limpieza de HTML**: Pre-procesamiento agresivo elimina ruido antes de la extracción

## Estructura del Proyecto

```
src/
├── commands/          # Grupos de comandos CLI
│   ├── article.py    # Comandos de artículos (fetch, list, show, delete)
│   ├── cache.py      # Comandos de caché (stats, list-domains, clear)
│   ├── domain.py     # Comandos de dominios (list, stats)
│   ├── process.py    # Comandos de procesamiento (start, list, show)
│   ├── entity.py     # Comandos de entidades (list, show, stats, ai-classify)
│   ├── flash.py      # Comandos de flash news (list, show, publish, stats)
│   ├── export.py     # Comandos de exportación (corpus)
│   └── email.py      # Comandos de correos (send, send-template, logs)
├── db/               # Modelos de base de datos y operaciones
│   ├── models.py     # Modelos SQLAlchemy (news.db)
│   ├── database.py   # Fachada CRUD (news.db)
│   ├── cache.py      # Base de datos de caché (cache.db)
│   └── export.py     # Funciones de exportación de datos
├── processors/       # Procesamiento de artículos y entidades
│   ├── enrich.py                    # Enriquecimiento: clustering semántico
│   ├── article_analysis.py          # Análisis profundo con OpenAI
│   ├── flash_news.py                # Generación LLM de resúmenes
│   ├── clustering.py                # UMAP + HDBSCAN clustering
│   ├── entity_ai_classification.py  # Clasificación AI de entidades
│   ├── entity_lsh_matcher.py        # LSH matching de entidades
│   └── tokenization.py              # Tokenización de entidades
├── domain/           # Lógica de negocio de dominio
│   ├── entity_rank.py              # PageRank para entidades
│   └── calculate_global_relevance.py  # Cálculo de relevancia global
├── llm/              # Integración con LLMs
│   ├── prompts/      # Prompts Jinja2 y schemas Pydantic
│   ├── openai_client.py  # Wrapper genérico para OpenAI
│   └── logging.py    # Sistema de logging de llamadas a LLM
├── email_system/     # Sistema de envío de correos
│   ├── client.py     # Cliente SMTP
│   ├── renderer.py   # Renderizado de templates Jinja2
│   ├── service.py    # Servicio de alto nivel
│   ├── logging.py    # Sistema de logging de correos
│   └── templates/    # Templates de email (.jinja)
├── extractors/       # Extractores específicos por dominio
│   ├── html_to_markdown.py      # Helpers de conversión
│   └── {domain}_com.py          # Extractores por sitio
├── cli.py            # Punto de entrada principal del CLI
├── get_news.py       # Lógica de descarga/extracción
└── settings.py       # Gestión de configuración y variables de entorno
```

### Configuración

- `pyproject.toml` - Dependencias, versión, configuración de build
- Layout `src/`: Archivos fuente instalados desde src/, pero los imports no incluyen el prefijo `src.`

## Gestión de Versiones

La versión se define una sola vez en `pyproject.toml`:
```toml
[project]
version = "0.1.0"
```

El CLI lee la versión vía `importlib.metadata.version("news")` - no se necesita duplicación.
