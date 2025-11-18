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
- `src/get_news.py` - Orquestación principal: descargar → limpiar → extraer → guardar
- `src/db/database.py` - Fachada de base de datos con operaciones CRUD
- `src/db/models.py` - Modelos SQLAlchemy (Source, Article, Tag, NamedEntity, ArticleCluster, FlashNews, etc.)
- `src/db/cache.py` - Base de datos de caché para contenido HTML de URLs
- `src/extractors/{domain}_com.py` - Extractores de contenido específicos por dominio
- `src/domain/enrich_article.py` - Procesamiento: clustering semántico + NER
- `src/domain/generate_flash_news.py` - Generación de resúmenes narrativos con LLM

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

articles (N:1 source, M:N tags, M:N named_entities, 1:N article_clusters, 1:N article_sentences)
  ├─ id, hash (SHA-256, unique), url, source_id
  ├─ title, subtitle, author, published_date, location, category
  ├─ content (Markdown), enriched_at, cluster_enriched_at
  ├─ created_at, updated_at

tags (M:N articles via article_tags)
  ├─ id, name (unique), created_at, updated_at

article_tags (tabla de asociación)
  ├─ article_id, tag_id

named_entities (M:N articles via article_entities, M:N canonical refs via entity_canonical_refs, M:N group members via entity_group_members)
  ├─ id, name (unique), entity_type, detected_types, classified_as, is_group
  ├─ description, photo_url, article_count, avg_local_relevance, diversity
  ├─ pagerank, global_relevance, last_rank_calculated_at
  ├─ needs_review, last_review, trend, created_at, updated_at

article_entities (tabla de asociación con metadata)
  ├─ article_id, entity_id, mentions, relevance, origin, context_sentences

entity_canonical_refs (tabla de asociación para desambiguación)
  ├─ entity_id, canonical_id

articles_needs_rerank (tabla de tracking)
  ├─ article_id, created_at

entity_group_members (tabla de membresías con tracking temporal)
  ├─ id, group_id, member_id, role, since, until, created_at, updated_at

article_clusters (N:1 article, 1:1 flash_news)
  ├─ id, article_id, cluster_label, category, score, size
  ├─ centroid_embedding, sentence_indices, created_at, updated_at

article_sentences (N:1 article, N:1 article_clusters)
  ├─ id, article_id, sentence_index, sentence_text
  ├─ cluster_id, embedding, created_at

flash_news (1:1 article_clusters)
  ├─ id, cluster_id (unique), summary, embedding
  ├─ published, created_at, updated_at

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
│   ├── entity.py     # Comandos de entidades (list, show, stats)
│   └── flash.py      # Comandos de flash news (list, show, publish, stats)
├── db/               # Modelos de base de datos y operaciones
│   ├── models.py     # Modelos SQLAlchemy (news.db)
│   ├── database.py   # Fachada CRUD (news.db)
│   └── cache.py      # Base de datos de caché (cache.db)
├── domain/           # Lógica de procesamiento de dominio
│   ├── enrich_article.py       # Clustering + NER
│   └── generate_flash_news.py  # Generación LLM de resúmenes
├── llm/              # Integración con LLMs
│   ├── prompts/      # Prompts Jinja2 y schemas Pydantic
│   └── openai_structured_output.py  # Wrapper genérico
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
