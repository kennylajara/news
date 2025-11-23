# Referencia de Comandos CLI

Referencia completa de todos los comandos disponibles en el CLI de News Portal.

## Paginación

Todos los comandos que listan resultados utilizan paginación automática cuando hay más de 20 elementos:
- La paginación usa el pager del sistema (generalmente `less`)
- Puedes desactivar la paginación con `--no-pager`
- Navegación: usa flechas, espacio, `q` para salir
- También funciona redirigiendo a archivo: `uv run news entity list > output.txt`

## Artículos

### `news article fetch <URL>`

Descarga y extrae un artículo desde una URL.

**Opciones:**
- `--cache-no-read`: Ignorar caché, siempre descargar desde HTTP
- `--cache-no-save`: No guardar en caché después de descargar

**Ejemplos:**
```bash
# Descarga normal (usa caché)
uv run news article fetch "https://www.diariolibre.com/actualidad/..."

# Forzar descarga fresca (ignora caché, pero sí guarda)
uv run news article fetch "URL" --cache-no-read

# Descargar sin cachear (útil para URLs temporales)
uv run news article fetch "URL" --cache-no-save

# Deshabilitar caché completamente
uv run news article fetch "URL" --cache-no-read --cache-no-save
```

### `news article list`

Lista artículos de la base de datos.

**Opciones:**
- `-l, --limit`: Número de artículos a mostrar (default: 10)
- `-s, --source`: Filtrar por dominio de fuente
- `-t, --tag`: Filtrar por tag
- `--enriched`: Mostrar solo artículos enriquecidos
- `--pending-enrich`: Mostrar solo artículos pendientes de enriquecer
- `--no-pager`: Desactivar paginación

**Ejemplos:**
```bash
uv run news article list
uv run news article list --limit 20
uv run news article list --source diariolibre.com
uv run news article list --tag "política"
uv run news article list --enriched
uv run news article list --pending-enrich
uv run news article list --source diariolibre.com --enriched
```

### `news article show <ID>`

Muestra detalles de un artículo específico.

**Opciones:**
- `-f, --full`: Mostrar contenido completo del artículo
- `-e, --entities`: Mostrar entidades extraídas

**Ejemplos:**
```bash
uv run news article show 1
uv run news article show 1 --full
uv run news article show 1 --entities
uv run news article show 1 --full --entities
```

**Información mostrada:**
- Metadatos (título, autor, fecha, ubicación, fuente, categoría)
- Estado de preprocesamiento
- Tags
- Entidades extraídas (si `--entities` y artículo preprocesado)
  - Nombre, tipo, número de menciones, relevancia
- Contenido (preview o completo según `--full`)

### `news article delete <ID>`

Elimina un artículo de la base de datos.

**Ejemplo:**
```bash
uv run news article delete 1
```

---

## Caché

El sistema de caché almacena el HTML original de las URLs descargadas en `data/cache.db`. Esto es útil durante desarrollo para evitar re-descargas.

### `news cache stats`

Muestra estadísticas del caché.

**Opciones:**
- `-d, --domain`: Filtrar por dominio específico

**Ejemplos:**
```bash
# Estadísticas globales
uv run news cache stats

# Estadísticas por dominio
uv run news cache stats --domain diariolibre.com
```

**Output:**
```
Cache statistics (all domains)

Total entries: 245
Total size: 12.45 MB
Oldest entry: 2025-01-10 14:23
Newest entry: 2025-01-17 09:15

Domains in cache: 3
  Use 'news cache domains' for details
```

### `news cache list`

Lista URLs cacheadas.

**Opciones:**
- `-d, --domain`: Filtrar por dominio
- `-l, --limit`: Número de URLs a mostrar (default: 20)
- `--no-pager`: Desactivar paginación

**Ejemplos:**
```bash
# Listar últimas 20 URLs
uv run news cache list

# Filtrar por dominio
uv run news cache list --domain diariolibre.com

# Ver más URLs
uv run news cache list --limit 50
```

**Output:**
```
Cached URLs (3 shown):

[1] https://www.diariolibre.com/actualidad/ejemplo-1
    Hash: 7434b1cfe165bcbc...  |  Status: 200  |  Domain: www.diariolibre.com  |  Size: 196.1 KB  |  Cached: 2025-01-17 10:30
[2] https://www.diariolibre.com/actualidad/ejemplo-2
    Hash: 105bf8b9d126084d...  |  Status: 200  |  Domain: www.diariolibre.com  |  Size: 193.1 KB  |  Cached: 2025-01-17 10:25
[3] https://www.diariolibre.com/actualidad/ejemplo-3
    Hash: 3c493ea42dd7e790...  |  Status: 404  |  Domain: www.diariolibre.com  |  Size: 191.7 KB  |  Cached: 2025-01-17 10:20
```

**Notas:**
- El hash se muestra truncado (primeros 16 caracteres)
- Status code con colores: verde (2xx), amarillo (3xx), rojo (4xx/5xx)
- Los URLs con status 4xx/5xx fallarán si intentas usarlos con `article fetch`

### `news cache domains`

Lista todos los dominios en caché con estadísticas.

**Ejemplo:**
```bash
uv run news cache domains
```

**Output:**
```
Cached domains (3 total):

  diariolibre.com
    Entries: 198  |  Size: 9.87 MB

  listindiario.com
    Entries: 45  |  Size: 2.34 MB

  hoy.com.do
    Entries: 2  |  Size: 240.00 KB
```

### `news cache show <URL>`

Muestra detalles de un URL cacheado, incluyendo preview del contenido HTML.

**Argumentos:**
- `URL`: URL completa o hash del URL (completo o parcial, mínimo 8 caracteres)

**Ejemplos:**
```bash
# Por URL completa
uv run news cache show "https://example.com/article"

# Por hash completo
uv run news cache show 7434b1cfe165bcbc6ae8f6364d840dd5341fd0d4578c3c39db98e4f3726df560

# Por hash parcial (copia del output de 'cache list')
uv run news cache show 7434b1cfe165bcbc
```

**Output:**
```
Cached URL Details

URL: https://www.diariolibre.com/actualidad/ejemplo
Domain: www.diariolibre.com
Hash: 7434b1cfe165bcbc6ae8f6364d840dd5341fd0d4578c3c39db98e4f3726df560
Status Code: 200
Content Size: 191.74 KB
Cached At: 2025-01-17 10:20:30
Last Accessed: 2025-01-17 14:15:45

Content preview (first 500 chars):
------------------------------------------------------------
<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">...
------------------------------------------------------------
```

### `news cache clear`

Limpia entradas del caché.

**Opciones:**
- `-d, --domain`: Solo limpiar entradas de este dominio

**Ejemplos:**
```bash
# Limpiar TODO el caché (requiere confirmación)
uv run news cache clear

# Limpiar solo un dominio
uv run news cache clear --domain diariolibre.com
```

**Nota:** Este comando requiere confirmación interactiva (`Are you sure?`).

---

## Dominios/Fuentes

### `news domain list`

Lista todas las fuentes registradas.

**Ejemplo:**
```bash
uv run news domain list
```

### `news domain show <dominio>`

Muestra detalles de una fuente específica.

**Ejemplo:**
```bash
uv run news domain show diariolibre.com
```

### `news domain add <dominio>`

Agrega manualmente una fuente a la base de datos.

**Opciones:**
- `-n, --name`: Nombre descriptivo de la fuente

**Ejemplo:**
```bash
uv run news domain add example.com --name "Example News"
```

### `news domain delete <dominio>`

Elimina una fuente y todos sus artículos.

**Ejemplo:**
```bash
uv run news domain delete example.com
```

### `news domain stats`

Muestra estadísticas sobre todas las fuentes.

**Ejemplo:**
```bash
uv run news domain stats
```

**Información mostrada:**
- Total de artículos por fuente
- Artículos preprocesados por fuente
- Artículos pendientes de preprocesar por fuente
- Totales globales

---

## Procesamiento de Batches

### `news process start`

Crea y ejecuta un batch de procesamiento.

**Opciones:**
- `-d, --domain`: Dominio a procesar (requerido)
- `-t, --type`: Tipo de procesamiento (requerido)
  - `enrich_article`: Clustering semántico (sin OpenAI)
  - `analyze_article`: Extracción de entidades + análisis con OpenAI
  - `generate_flash_news`: Generación de flash news con LLM
- `-s, --size`: Tamaño del batch (default: 10)

**Ejemplos:**
```bash
# Paso 1: Enriquecimiento base (clustering)
uv run news process start -d diariolibre.com -t enrich_article -s 10

# Paso 2: Análisis con OpenAI (extracción de entidades + análisis profundo)
uv run news process start -d diariolibre.com -t analyze_article -s 10

# Paso 3: Generación de flash news (requiere artículos enriquecidos)
uv run news process start -d diariolibre.com -t generate_flash_news -s 10
```

### `news process list`

Lista batches de procesamiento con filtros.

**Opciones:**
- `-l, --limit`: Número de batches a mostrar (default: 20)
- `-s, --status`: Filtrar por estado (pending, processing, completed, failed)
- `-d, --domain`: Filtrar por dominio
- `--no-pager`: Desactivar paginación

**Ejemplos:**
```bash
uv run news process list
uv run news process list --limit 50
uv run news process list --status completed
uv run news process list --domain diariolibre.com
uv run news process list --domain diariolibre.com --status failed
```

### `news process show <batch_id>`

Muestra información detallada de un batch.

**Opciones:**
- `-i, --item`: ID de item específico para ver logs detallados

**Ejemplos:**
```bash
uv run news process show 1
uv run news process show 1 --item 5
```

**Información mostrada (batch):**
- Metadatos (fuente, tipo, estado)
- Progreso (total, procesados, exitosos, fallidos)
- Estadísticas agregadas (varía según tipo de proceso)
- Tiempos de ejecución y duración
- Resumen de items por estado
- Primeros 5 items fallidos con errores

**Información mostrada (item con `--item`):**
- Metadatos (batch, artículo, estado)
- Estadísticas del procesamiento
- Tiempos de ejecución y duración
- Mensaje de error (si falló)
- Logs completos del procesamiento

---

## Flash News

### `news flash list`

Lista flash news generados.

**Opciones:**
- `--article-id`: Filtrar por ID de artículo
- `--domain`: Filtrar por dominio
- `--published`: Mostrar solo publicados
- `--unpublished`: Mostrar solo no publicados
- `--limit`: Número de resultados (default: 50)
- `--no-pager`: Desactivar paginación

**Ejemplos:**
```bash
uv run news flash list
uv run news flash list --published
uv run news flash list --domain diariolibre.com
uv run news flash list --article-id 5
```

### `news flash show <id>`

Muestra detalles completos de un flash news.

**Ejemplo:**
```bash
uv run news flash show 1
```

**Información mostrada:**
- Estado de publicación
- Resumen completo generado por LLM
- Artículo fuente (título, URL, fecha)
- Información del cluster (categoría, score, tamaño)
- Oraciones del cluster usadas para generar el resumen

### `news flash publish <id>`

Marca un flash news como publicado.

**Ejemplo:**
```bash
uv run news flash publish 1
```

### `news flash unpublish <id>`

Marca un flash news como no publicado.

**Ejemplo:**
```bash
uv run news flash unpublish 1
```

### `news flash stats`

Muestra estadísticas de flash news.

**Opciones:**
- `--domain`: Filtrar por dominio

**Ejemplos:**
```bash
uv run news flash stats
uv run news flash stats --domain diariolibre.com
```

**Información mostrada:**
- Total de flash news
- Publicados vs no publicados (con porcentajes)
- Desglose por dominio

---

## Exportación

### `news export corpus`

Exporta artículos a una base de datos de corpus para tareas de ML/NLP.

**Opciones:**
- `-d, --domain`: Filtrar por dominio (ej: diariolibre.com)
- `-l, --limit`: Limitar número de artículos a exportar
- `--skip-enriched`: Solo exportar artículos sin enriquecimiento
- `-o, --output`: Ruta de la base de datos de salida (default: `ai/corpus/raw_news.db`)

**Ejemplos:**
```bash
# Exportar todos los artículos
uv run news export corpus

# Exportar artículos de un dominio específico
uv run news export corpus --domain diariolibre.com

# Exportar artículos limitados
uv run news export corpus --domain diariolibre.com --limit 100

# Exportar solo artículos no enriquecidos
uv run news export corpus --skip-enriched --limit 50

# Exportar a ubicación personalizada
uv run news export corpus --output /path/to/corpus.db
```

**Formato de la base de datos de corpus:**
- Base de datos SQLite separada optimizada para ML/NLP
- Contenido en texto plano (sin markdown)
- Campos separados de categoría y subcategoría
- Ideal para entrenamiento de modelos, análisis de texto, etc.

**Características:**
- Preserva metadata original (título, autor, fecha, fuente)
- Convierte contenido markdown a texto plano
- Separa categoría/subcategoría en campos independientes
- Incluye hash SHA-256 para deduplicación
- Muestra progreso durante la exportación

---

## Entidades

### `news entity list`

Lista entidades nombradas extraídas.

**Opciones:**
- `-l, --limit`: Número de entidades a mostrar (default: 20)
- `-t, --type`: Filtrar por tipo de entidad
  - Tipos válidos: PERSON, ORG, GPE, EVENT, PRODUCT, NORP, FAC, LOC
- `-r, --min-relevance`: Relevancia global mínima
- `--no-pager`: Desactivar paginación

**Ejemplos:**
```bash
uv run news entity list
uv run news entity list --limit 50
uv run news entity list --type PERSON
uv run news entity list --min-relevance 5
uv run news entity list --type ORG --min-relevance 10
```

**Información mostrada:**
- Nombre de la entidad
- Tipo
- Relevancia global (número de artículos que la mencionan)
- Número de artículos donde aparece
- Descripción (si existe)

### `news entity show <nombre>`

Muestra detalles de una entidad y artículos que la mencionan.

**Opciones:**
- `-l, --limit`: Número de artículos a mostrar (default: 10)
- `--no-pager`: Desactivar paginación

**Ejemplos:**
```bash
uv run news entity show "Luis Abinader"
uv run news entity show "Policía" --limit 20
```

**Información mostrada:**
- Metadatos de la entidad (ID, tipo, relevancia, trend)
- Descripción y foto (si existen)
- Fechas de creación y actualización
- Lista de artículos que la mencionan (ordenados por relevancia)
  - Título del artículo
  - Fecha de publicación
  - Número de menciones en ese artículo
  - Relevancia en ese artículo

### `news entity search <query>`

Busca entidades por nombre (coincidencia parcial).

**Opciones:**
- `-l, --limit`: Número de resultados a mostrar (default: 10)
- `--no-pager`: Desactivar paginación

**Ejemplos:**
```bash
uv run news entity search "Luis"
uv run news entity search "Policía" --limit 5
```

**Información mostrada:**
- Nombre de la entidad
- Tipo
- Relevancia global
- Número de artículos donde aparece

### `news entity rerank`

Calcula relevancia global (PageRank) de entidades basado en co-ocurrencias.

**Opciones:**
- `--domain TEXT`: Filtrar artículos por dominio (testing)
- `--damping FLOAT`: Factor de amortiguación (default: 0.85)
- `--threshold FLOAT`: Umbral mínimo de relevancia (default: 0.3)
- `--time-decay INT`: Decay temporal en días (opcional)
- `--show-stats`: Mostrar estadísticas detalladas

**Ejemplos:**
```bash
# Calcular ranking global
uv run news entity rerank

# Solo artículos de un dominio
uv run news entity rerank --domain diariolibre.com

# Ajustar parámetros
uv run news entity rerank --damping 0.9 --threshold 0.4

# Con estadísticas
uv run news entity rerank --show-stats
```

### `news entity review <entity_id>`

Inicia revisión interactiva de una entidad para clasificación.

**Ejemplo:**
```bash
uv run news entity review 123
```

**Información mostrada:**
- Metadatos de la entidad (ID, nombre, tipo, clasificación actual)
- Referencias canónicas (si las tiene)
- Artículos donde aparece (top 5)
- Oraciones de contexto donde fue detectada
- Opciones interactivas para clasificar

### `news entity classify-canonical <entity_id>`

Marca una entidad como CANONICAL (entidad principal/verdadera).

**Ejemplo:**
```bash
uv run news entity classify-canonical 45
```

### `news entity classify-alias <entity_id> <canonical_id>`

Marca una entidad como ALIAS de otra entidad canónica.

**Parámetros:**
- `entity_id`: ID de la entidad a clasificar como alias
- `canonical_id`: ID de la entidad canónica a la que apunta

**Ejemplo:**
```bash
# "Luis" (ID: 123) es alias de "Luis Abinader" (ID: 45)
uv run news entity classify-alias 123 45
```

**Efecto:**
- La entidad se marca como ALIAS
- Se crea relación en `entity_canonical_refs`
- Se marcan artículos para recálculo en `articles_needs_rerank`
- La relevancia del alias se transferirá a la canónica tras recalcular

### `news entity classify-ambiguous <entity_id> <canonical_id_1> <canonical_id_2> [...]`

Marca una entidad como AMBIGUOUS (puede referirse a múltiples entidades canónicas).

**Parámetros:**
- `entity_id`: ID de la entidad ambigua
- `canonical_id_1, canonical_id_2, ...`: IDs de las entidades canónicas (mínimo 2)

**Ejemplo:**
```bash
# "Luis" puede ser Luis Abinader (45) o Luis Fonsi (67)
uv run news entity classify-ambiguous 123 45 67
```

**Efecto:**
- La entidad se marca como AMBIGUOUS
- Se crean múltiples relaciones en `entity_canonical_refs`
- Se marcan artículos para recálculo
- La relevancia se dividirá entre las canónicas presentes tras recalcular

### `news entity classify-not-entity <entity_id>`

Marca una entidad como NOT_AN_ENTITY (falso positivo de extracción).

**Ejemplo:**
```bash
# "Día" fue detectado erróneamente como entidad
uv run news entity classify-not-entity 234
```

**Efecto:**
- La entidad se marca como NOT_AN_ENTITY
- Se limpian todas sus referencias canónicas
- Se marcan artículos para recálculo
- Su relevancia será 0.0 tras recalcular (ignorada completamente)

### `news entity set-group <entity_id>`

Marca una entidad como grupo.

**Ejemplo:**
```bash
uv run news entity set-group 100
```

**Restricción:** Solo entidades CANONICAL pueden ser grupos.

### `news entity unset-group <entity_id>`

Desmarca una entidad como grupo.

**Ejemplo:**
```bash
uv run news entity unset-group 100
```

**Restricción:** La entidad no debe tener miembros.

### `news entity add-member <group_id> <member_id>`

Agrega un miembro a un grupo.

**Opciones:**
- `--role TEXT`: Rol dentro del grupo
- `--since YYYY-MM-DD`: Fecha de inicio
- `--until YYYY-MM-DD`: Fecha de fin

**Ejemplos:**
```bash
# Miembro actualmente activo
uv run news entity add-member 100 101

# Con rol
uv run news entity add-member 100 101 --role "vocalist"

# Con período temporal
uv run news entity add-member 100 101 --since 1997-01-01 --until 2011-07-01
```

### `news entity remove-member <group_id> <member_id>`

Marca un miembro como que dejó el grupo (establece fecha `until`).

**Opciones:**
- `--until YYYY-MM-DD`: Fecha de salida (default: hoy)

**Ejemplos:**
```bash
# Salida hoy
uv run news entity remove-member 100 101

# Salida en fecha específica
uv run news entity remove-member 100 101 --until 2011-07-01
```

### `news entity list-members <group_id>`

Lista miembros de un grupo.

**Opciones:**
- `--active-at YYYY-MM-DD`: Filtrar miembros activos en fecha específica
- `--show-dates`: Mostrar fechas de membresía

**Ejemplos:**
```bash
# Lista todos los miembros
uv run news entity list-members 100

# Miembros activos en 2008
uv run news entity list-members 100 --active-at 2008-01-01

# Con fechas
uv run news entity list-members 100 --show-dates
```

### `news entity recalculate-local`

Recalcula relevancia local de artículos tras cambios de clasificación.

**Opciones:**
- `-l, --limit`: Procesar solo N artículos
- `-a, --article-id`: Recalcular solo un artículo específico

**Ejemplos:**
```bash
# Recalcular todos los artículos marcados
uv run news entity recalculate-local

# Recalcular con límite
uv run news entity recalculate-local --limit 100

# Recalcular artículo específico
uv run news entity recalculate-local --article-id 456
```

**Proceso:**
1. Lee artículos de `articles_needs_rerank`
2. Para cada artículo:
   - Carga entidades originales (solo `origin=AI_ANALYSIS`)
   - Borra relaciones `article_entities`
   - Recalcula relevancia con clasificaciones actuales
   - Inserta nuevas relevances con flags de origen
3. Limpia artículos procesados

**Información mostrada:**
- Artículos procesados/fallidos
- Total de entidades procesadas
- Entidades ignoradas (ALIAS/AMBIGUOUS/NOT_AN_ENTITY)
- Entidades artificiales (agregadas por clasificación)

---

## Tipos de Entidades

Los siguientes tipos de entidades son extraídos por OpenAI durante el proceso `analyze_article`:

| Tipo | Descripción |
|------|-------------|
| PERSON | Personas (individuos específicos) |
| ORG | Organizaciones (empresas, agencias, instituciones, partidos políticos) |
| GPE | Ubicaciones geopolíticas (países, ciudades, estados) |
| EVENT | Eventos (huracanes, batallas, conferencias, festivales) |
| PRODUCT | Productos (objetos, vehículos, servicios, software) |
| NORP | Nacionalidades, grupos religiosos o políticos |

---

## Flujos de Trabajo Comunes

### Agregar y procesar artículos de un nuevo dominio

```bash
# 1. Agregar la fuente
uv run news domain add example.com --name "Example News"

# 2. Descargar artículos
uv run news article fetch "https://example.com/article1"
uv run news article fetch "https://example.com/article2"

# 3. Verificar artículos pendientes
uv run news article list --source example.com --pending-enrich

# 4. Procesar artículos - Paso 1: Clustering
uv run news process start -d example.com -t enrich_article -s 10

# 5. Procesar artículos - Paso 2: Extracción de entidades con OpenAI
uv run news process start -d example.com -t analyze_article -s 10

# 6. Generar flash news
uv run news process start -d example.com -t generate_flash_news -s 10

# 7. Ver progreso de batches
uv run news process list --domain example.com

# 8. Ver flash news generados
uv run news flash list --domain example.com

# 9. Ver estadísticas actualizadas
uv run news domain stats
```

### Analizar entidades extraídas

```bash
# 1. Ver top entidades
uv run news entity list --limit 30

# 2. Ver solo personas relevantes
uv run news entity list --type PERSON --min-relevance 5

# 3. Ver detalles de una entidad específica
uv run news entity show "Luis Abinader"

# 4. Buscar entidades relacionadas
uv run news entity search "Luis"

# 5. Ver artículo con sus entidades
uv run news article show 1 --entities
```

### Clasificar y desambiguar entidades

```bash
# 1. Buscar entidad ambigua
uv run news entity search "Luis"

# Output: ID: 123 | Name: Luis | Type: PERSON | Articles: 45

# 2. Buscar candidatos canónicos
uv run news entity search "Luis Abinader"
uv run news entity search "Luis Fonsi"

# Output:
# ID: 45 | Name: Luis Abinader | Type: PERSON | Articles: 120
# ID: 67 | Name: Luis Fonsi | Type: PERSON | Articles: 8

# 3. Revisar contexto de la entidad
uv run news entity review 123

# 4. Clasificar según corresponda:

# Opción A: Es alias de una sola entidad
uv run news entity classify-alias 123 45

# Opción B: Es ambigua (puede ser varias)
uv run news entity classify-ambiguous 123 45 67

# Opción C: Es falso positivo
uv run news entity classify-not-entity 123

# 5. Recalcular relevancia local de artículos afectados
uv run news entity recalculate-local

# 6. Recalcular relevancia global (PageRank)
uv run news entity rerank

# 7. Verificar resultados
uv run news entity show "Luis Abinader"
uv run news entity show "Luis Fonsi"
```

### Monitorear procesamiento

```bash
# 1. Ver batches recientes
uv run news process list --limit 10

# 2. Ver batches fallidos
uv run news process list --status failed

# 3. Ver detalles de batch específico
uv run news process show 5

# 4. Ver logs de item fallido
uv run news process show 5 --item 12

# 5. Ver estadísticas de flash news
uv run news flash stats
```
