# Arquitectura

## Flujo de Componentes

```
Usuario → CLI (Click) → get_news.py → Extractor (plugin) → Database (SQLite)
```

### Archivos Clave

- `src/cli.py` - Punto de entrada del CLI, enruta a grupos de comandos
- `src/commands/article.py` - Comandos de gestión de artículos
- `src/commands/domain.py` - Comandos de gestión de fuentes/dominios
- `src/get_news.py` - Orquestación principal: descargar → limpiar → extraer → guardar
- `src/db/database.py` - Fachada de base de datos con operaciones CRUD
- `src/db/models.py` - Modelos SQLAlchemy (Source, Article, Tag)
- `src/extractors/{domain}_com.py` - Extractores de contenido específicos por dominio

## Pipeline de Descarga de Artículos

1. **Descarga**: HTTP GET con encabezado User-Agent
2. **Limpieza**: Eliminar scripts, estilos, formularios, comentarios; normalizar espacios; preservar solo atributos id/class/href
3. **Extracción**: Cargar extractor específico del dominio vía importación dinámica
4. **Parseo**: Usar selectores CSS para extraer datos estructurados, convertir HTML → Markdown
5. **Almacenamiento**: Guardar en SQLite con relaciones (source, tags)

## Base de Datos

### Esquema

```
sources (1:N articles)
  ├─ id, domain (unique), name, created_at

articles (N:1 source, M:N tags)
  ├─ id, hash (SHA-256, unique), url (unique), source_id
  ├─ title, subtitle, author, published_date, location, category
  ├─ content (Markdown), created_at, updated_at

tags (M:N articles via article_tags)
  ├─ id, name (unique), created_at

article_tags (tabla de asociación)
  ├─ article_id, tag_id
```

### Deduplicación

Se usa hash SHA-256 de la URL para prevenir re-descargas. El hash es único e indexado para búsquedas rápidas.

## Patrones Importantes

1. **Carga dinámica de extractores**: Los extractores se importan en tiempo de ejecución según el dominio
2. **Patrón get-or-create**: Los métodos de base de datos auto-crean Sources y Tags si no existen
3. **Cascade deletes**: Eliminar Source remueve todos sus Articles; eliminar Article remueve asociaciones de tags
4. **Deduplicación**: Verifica `article_exists(url, hash)` antes de descargar
5. **Limpieza de HTML**: Pre-procesamiento agresivo elimina ruido antes de la extracción

## Estructura del Proyecto

```
src/
├── commands/          # Grupos de comandos CLI (article, domain)
├── db/               # Modelos de base de datos y operaciones
├── extractors/       # Extractores de contenido específicos por dominio
├── cli.py            # Punto de entrada principal del CLI
└── get_news.py       # Lógica principal de descarga/extracción
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
