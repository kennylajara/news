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
- `pre_process_articles`: Pre-procesamiento de artículos

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
| processed_at | DATETIME | NULLABLE, INDEX | Fecha de procesamiento (NULL = no procesado) |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación en DB |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Última actualización |

**Relaciones**:
- N:1 con `sources` (muchos artículos pertenecen a un source)
- M:N con `tags` vía `article_tags` (muchos artículos tienen muchos tags)

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
| description | TEXT | NULLABLE | Descripción de la entidad |
| photo_url | VARCHAR(500) | NULLABLE | URL de la foto de la entidad |
| relevance | INTEGER | NOT NULL, DEFAULT 0 | Score de relevancia (0-100) |
| trend | INTEGER | NOT NULL, DEFAULT 0 | Score de tendencia (-100 a 100) |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Fecha de creación |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | Última actualización |

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

**Uso futuro**:
- Esta tabla será utilizada para extraer y vincular entidades nombradas (personas, organizaciones, lugares, etc.) de los artículos
- Los scores de relevancia y tendencia se calcularán basados en menciones y frecuencia

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
