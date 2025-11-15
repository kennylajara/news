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
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | Fecha de creación |

**Relaciones**:
- 1:N con `articles` (un source tiene muchos artículos)

### Tabla: `articles`

Artículos de noticias completos con metadata.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY | ID auto-incremental |
| hash | VARCHAR(64) | UNIQUE, NOT NULL, INDEX | SHA-256 completo de la URL |
| url | VARCHAR(2048) | UNIQUE, NOT NULL, INDEX | URL original del artículo |
| source_id | INTEGER | FOREIGN KEY, NOT NULL, INDEX | ID de la fuente |
| title | VARCHAR(500) | NOT NULL | Título del artículo |
| subtitle | VARCHAR(500) | | Subtítulo o bajada |
| author | VARCHAR(255) | | Nombre del autor |
| published_date | DATETIME | | Fecha de publicación original |
| location | VARCHAR(255) | | Ciudad de origen |
| category | VARCHAR(255) | | Categoría/Subcategoría |
| content | TEXT | NOT NULL | Contenido en formato Markdown |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | Fecha de creación en DB |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | Última actualización |

**Relaciones**:
- N:1 con `sources` (muchos artículos pertenecen a un source)
- M:N con `tags` vía `article_tags` (muchos artículos tienen muchos tags)

**Índices**:
- `hash` (UNIQUE): Para deduplicación rápida
- `url` (UNIQUE): Para búsqueda directa
- `source_id`: Para filtrar por fuente

### Tabla: `tags`

Tags únicos para categorización.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| id | INTEGER | PRIMARY KEY | ID auto-incremental |
| name | VARCHAR(100) | UNIQUE, NOT NULL, INDEX | Nombre del tag |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | Fecha de creación |

**Relaciones**:
- M:N con `articles` vía `article_tags`

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

## Acceso Directo

Puedes acceder directamente a la base de datos:

```bash
sqlite3 data/news.db

# Comandos útiles
.tables                    # Listar tablas
.schema articles           # Ver esquema de tabla
SELECT * FROM articles;    # Consultar datos
.quit                      # Salir
```
