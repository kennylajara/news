# Sistema de Caché de URLs

El sistema de caché almacena el contenido HTML original de las URLs descargadas en una base de datos SQLite separada (`data/cache.db`). Esto permite reutilizar descargas durante desarrollo sin tener que volver a hacer peticiones HTTP.

## Motivación

Durante el desarrollo es común:

1. Borrar y recrear `news.db` para probar cambios de schema
2. Experimentar con diferentes extractores
3. Probar procesamiento de artículos sin re-descargar

Sin caché, cada vez tendríamos que volver a descargar todas las URLs. Con caché, el HTML original se preserva indefinidamente en `cache.db`.

## Arquitectura

### Bases de Datos Separadas

- **`data/news.db`**: Base de datos principal con artículos procesados, entidades, clusters, etc.
- **`data/cache.db`**: Base de datos de caché solo para contenido HTML crudo

**Ventaja**: Puedes borrar `news.db` sin perder las descargas originales.

### Esquema de cache.db

```sql
CREATE TABLE url_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash TEXT UNIQUE NOT NULL,          -- SHA-256 hash de la URL
    url TEXT NOT NULL,                      -- URL original
    domain TEXT NOT NULL,                   -- Dominio extraído (ej: diariolibre.com)
    content TEXT NOT NULL,                  -- HTML completo (o URL final si status 30x)
    status_code INTEGER NOT NULL,           -- HTTP status (200, 404, etc.)
    content_length INTEGER NOT NULL,        -- Tamaño en bytes
    created_at DATETIME NOT NULL,           -- Cuándo se guardó por primera vez
    accessed_at DATETIME NOT NULL           -- Última vez que se leyó del caché
);

-- Índices
CREATE UNIQUE INDEX idx_cache_url_hash ON url_cache(url_hash);
CREATE INDEX idx_cache_domain ON url_cache(domain);
CREATE INDEX idx_cache_created ON url_cache(created_at);
CREATE INDEX idx_cache_accessed ON url_cache(accessed_at);
CREATE INDEX idx_cache_domain_created ON url_cache(domain, created_at);
CREATE INDEX idx_cache_domain_accessed ON url_cache(domain, accessed_at);
```

### Manejo de Redirecciones HTTP

El sistema maneja redirecciones HTTP (301, 302, 303, 307, 308) de forma transparente y eficiente:

**Cuando se descarga una URL que redirige:**

1. Se guardan **DOS entradas** en la caché:
   - **Entrada de redirección**: URL original con status 30x y la URL final como contenido
   - **Entrada final**: URL final con status 200 y el HTML como contenido

2. Esto permite que ambas URLs funcionen independientemente sin duplicar contenido HTML

**Ejemplo:**

```
URL original: http://example.com/old-article
Redirige a:   http://example.com/new-article

Cache entries:
┌────────────────────────────────────────────────────────┐
│ Entry 1: http://example.com/old-article                │
│   status_code: 302                                     │
│   content: "http://example.com/new-article"            │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│ Entry 2: http://example.com/new-article                │
│   status_code: 200                                     │
│   content: "<html>... actual HTML content ..."         │
└────────────────────────────────────────────────────────┘
```

**Al leer del caché:**

- Si la URL tiene status 30x, el sistema automáticamente sigue la redirección
- Retorna el contenido HTML final con metadata indicando que fue redirigido
- El campo `was_redirected: true` indica que se siguió una redirección

**Ventajas:**

- ✅ Ambas URLs (original y final) funcionan correctamente
- ✅ No hay duplicación de contenido HTML
- ✅ Se preserva la cadena de redirección
- ✅ Permite hacer fetch de cualquiera de las dos URLs sin conflictos

### Flujo de Descarga con Caché

```
┌─────────────────────────────────────────────────────────────┐
│ news article fetch "https://example.com/article"            │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │ Compute URL hash     │
              └──────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │ Check news.db        │
              │ (article exists?)    │
              └──────────────────────┘
                         │
                    Already exists? → Skip
                         │
                     Not found
                         │
                         ▼
              ┌──────────────────────┐
              │ Check cache.db       │◄────── --cache-no-read (skip this)
              │ (url_hash exists?)   │
              └──────────────────────┘
                         │
                    ┌────┴────┐
                    │         │
              Cache Hit   Cache Miss
                    │         │
                    ▼         ▼
          ┌─────────────┐  ┌─────────────┐
          │ Read HTML   │  │ HTTP GET    │
          │ from cache  │  │ Download    │
          └─────────────┘  └─────────────┘
                    │         │
                    │         ▼
                    │  ┌─────────────────┐
                    │  │ Save to cache   │◄── --cache-no-save (skip this)
                    │  └─────────────────┘
                    │         │
                    └────┬────┘
                         ▼
              ┌──────────────────────┐
              │ Clean HTML           │
              └──────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │ Extract article data │
              └──────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │ Save to news.db      │
              └──────────────────────┘
```

## Uso

### Comandos de Descarga

```bash
# Descarga normal (usa caché para lectura y escritura)
news article fetch "https://diariolibre.com/actualidad/ejemplo"

# Forzar descarga fresca (ignorar caché, pero sí guardar)
news article fetch "URL" --cache-no-read

# Descargar pero NO guardar en caché (útil para URLs temporales)
news article fetch "URL" --cache-no-save

# Deshabilitar caché completamente
news article fetch "URL" --cache-no-read --cache-no-save
```

### Comandos de Gestión

#### Listar URLs Cacheadas

```bash
# Listar últimas 20 URLs
news cache list

# Output:
# Cached URLs (3 shown):
#
# [1] https://www.diariolibre.com/actualidad/ejemplo-1
#     Hash: 7434b1cfe165bcbc...  |  Status: 200  |  Domain: www.diariolibre.com  |  Size: 196.1 KB  |  Cached: 2025-01-17 10:30
# [2] https://www.diariolibre.com/actualidad/ejemplo-2
#     Hash: 105bf8b9d126084d...  |  Status: 200  |  Domain: www.diariolibre.com  |  Size: 193.1 KB  |  Cached: 2025-01-17 10:25
# [3] https://www.diariolibre.com/actualidad/ejemplo-3
#     Hash: 3c493ea42dd7e790...  |  Status: 404  |  Domain: www.diariolibre.com  |  Size: 191.7 KB  |  Cached: 2025-01-17 10:20

# Filtrar por dominio
news cache list --domain diariolibre.com

# Ver más URLs
news cache list --limit 50

# Desactivar pager (útil para scripts)
news cache list --no-pager
```

**Uso típico**: Cuando necesitas recrear `news.db`, usa `cache list` para obtener las URLs que ya tienes descargadas y re-procesarlas rápidamente.

**Nota importante**: El status code se muestra con colores para fácil identificación:
- Verde (2xx): Respuesta exitosa
- Amarillo (3xx): Redirección
- Rojo (4xx/5xx): Error - estas URLs fallarán al intentar procesarlas

#### Ver Detalles de un URL

```bash
# Ver detalles completos + preview del HTML
news cache show "https://diariolibre.com/actualidad/ejemplo"

# Output:
# Cached URL Details
#
# URL: https://www.diariolibre.com/actualidad/ejemplo
# Domain: www.diariolibre.com
# Hash: 7434b1cfe165bcbc6ae8f6364d840dd5341fd0d4578c3c39db98e4f3726df560
# Status Code: 200
# Content Size: 191.74 KB
# Cached At: 2025-01-17 10:20:30
# Last Accessed: 2025-01-17 14:15:45
#
# Content preview (first 500 chars):
# ------------------------------------------------------------
# <!DOCTYPE html><html lang="es"><head><meta charset="utf-8">...
# ------------------------------------------------------------

# Puedes usar el hash completo
news cache show 7434b1cfe165bcbc6ae8f6364d840dd5341fd0d4578c3c39db98e4f3726df560

# O el hash parcial (copia directamente del output de 'cache list')
news cache show 7434b1cfe165bcbc
```

**Uso típico**: Verificar que el HTML de un URL específico está cacheado correctamente antes de usarlo. Con hash parcial es más rápido (solo copiar del listado).

#### Ver Estadísticas

```bash
# Estadísticas globales
news cache stats

# Output:
# Cache statistics (all domains)
#
# Total entries: 245
# Total size: 12.45 MB
# Oldest entry: 2025-01-10 14:23
# Newest entry: 2025-01-17 09:15
#
# Domains in cache: 3
#   Use 'news cache domains' for details

# Estadísticas por dominio
news cache stats --domain diariolibre.com

# Output:
# Cache statistics for domain: diariolibre.com
#
# Total entries: 198
# Total size: 9.87 MB
# Oldest entry: 2025-01-10 14:23
# Newest entry: 2025-01-17 09:15
```

#### Listar Dominios

```bash
news cache domains

# Output:
# Cached domains (3 total):
#
#   diariolibre.com
#     Entries: 198  |  Size: 9.87 MB
#
#   listindiario.com
#     Entries: 45  |  Size: 2.34 MB
#
#   hoy.com.do
#     Entries: 2  |  Size: 240.00 KB
```

#### Limpiar Caché

```bash
# Limpiar TODO el caché (requiere confirmación)
news cache clear
# Are you sure you want to clear the cache? [y/N]: y
# ✓ Cleared 245 entries from cache

# Limpiar solo un dominio
news cache clear --domain diariolibre.com
# Are you sure you want to clear the cache? [y/N]: y
# ✓ Cleared 198 entries for domain 'diariolibre.com'

# Si no hay nada que limpiar
news cache clear --domain example.com
# No entries found for domain 'example.com'
```

## Implementación

### Clase CacheDatabase

Ubicación: `src/db/cache.py`

```python
from db.cache import CacheDatabase

cache_db = CacheDatabase()

# Leer del caché
cached = cache_db.get_cached_content(url)
if cached:
    html = cached['content']
    created = cached['created_at']

# Guardar en caché
cache_db.save_to_cache(url, html_content, status_code=200)

# Listar URLs cacheadas
entries = cache_db.list_entries(domain='diariolibre.com', limit=20)
for entry in entries:
    print(f"{entry['url']} - {entry['content_length']} bytes")

# Obtener por hash
cached = cache_db.get_by_hash(url_hash)

# Estadísticas
stats = cache_db.get_stats(domain='diariolibre.com')
# Returns: {total_entries, total_size_bytes, domains, oldest_entry, newest_entry}

# Limpiar
count = cache_db.clear_cache(domain='diariolibre.com')
```

### Función download_html

Ubicación: `src/get_news.py`

**Retorna un diccionario** con el contenido HTML y la URL final después de seguir redirecciones.

```python
from get_news import download_html

# Descarga con caché (default)
result = download_html(url)
html = result['content']        # HTML content
final_url = result['final_url'] # URL final después de redirecciones

# Descarga sin leer caché
result = download_html(url, use_cache_read=False)

# Descarga sin guardar en caché
result = download_html(url, use_cache_save=False)

# Modo verbose (imprime operaciones de caché)
result = download_html(url, verbose=True)
# Output:
# ✓ Loaded from cache (saved 2025-01-15 10:30, status: 200)
# ✓ Saved to cache: redirect http://... -> https://...

# Detectar si hubo redirección
if result['final_url'] != url:
    print(f"Redirected: {url} → {result['final_url']}")
```

**Valor de retorno:**
```python
{
    'content': str,      # HTML content
    'final_url': str     # Final URL after following redirects (may equal original URL)
}
```

## Casos de Uso

### Desarrollo de Extractores

Cuando estás desarrollando un extractor nuevo:

```bash
# 1. Descarga inicial de algunos artículos de ejemplo (se guarda en caché)
news article fetch "https://nuevositio.com/articulo-1"
news article fetch "https://nuevositio.com/articulo-2"
news article fetch "https://nuevositio.com/articulo-3"

# 2. Creas el extractor en extractors/nuevositio_com.py

# 3. Borras news.db para limpiar errores de intentos previos
rm data/news.db

# 4. Re-procesas TODOS los artículos del dominio desde caché (MUY RÁPIDO)
news article fetch-cached --domain nuevositio.com
# ✓ Created (ID: 1)
# ✓ Created (ID: 2)
# ✓ Created (ID: 3)

# 5. Encuentras un error, modificas el extractor

# 6. Re-procesas con --reindex para actualizar artículos
news article fetch-cached --domain nuevositio.com --reindex
# ↻ Updated (ID: 1)
# ↻ Updated (ID: 2)
# ↻ Updated (ID: 3)

# 7. Repites pasos 5-6 hasta que el extractor funcione perfecto

# Alternativamente, puedes usar fetch individual:
news article fetch "https://nuevositio.com/articulo-1" --reindex  # ← Lee del caché
```

### Testing de Cambios de Schema

```bash
# 1. Tienes 100 artículos descargados (en cache.db)

# 2. Haces cambios a models.py

# 3. Recreas base de datos
rm data/news.db

# 4. Re-procesas todos los artículos (lee del caché, muy rápido)
# Sin caché: 100 HTTP requests, ~3 minutos
# Con caché: 0 HTTP requests, ~10 segundos
```

### Procesar Múltiples Artículos desde Caché

El comando `fetch-cached` permite procesar múltiples artículos directamente desde el caché sin descargar nada:

```bash
# Procesar todos los artículos del caché (solo crea nuevos, salta existentes)
news article fetch-cached

# Output:
# Loading cached URLs...
# Found 50 cached URL(s)
#
# Processing 50 article(s)...
#
# [1/50] https://example.com/article-1
#   ✓ Created (ID: 1)
# [2/50] https://example.com/article-2
#   ⊘ Already exists, skipping
# ...
#
# Summary:
#   Created: 25
#   Skipped: 25

# Re-procesar TODOS los artículos (actualiza existentes)
news article fetch-cached --reindex

# Output:
# [1/50] https://example.com/article-1
#   ↻ Updated (ID: 1)
# [2/50] https://example.com/article-2
#   ↻ Updated (ID: 2)
# ...
#
# Summary:
#   Updated: 50

# Filtrar por dominio
news article fetch-cached --domain diariolibre.com

# Limitar cantidad
news article fetch-cached --limit 20

# Combinar filtros
news article fetch-cached --domain diariolibre.com --limit 10 --reindex
```

**Casos de uso comunes:**

1. **Repoblar news.db después de recrearlo:**
   ```bash
   rm data/news.db
   news article fetch-cached
   # → Procesa todos los artículos del caché (MUY RÁPIDO)
   ```

2. **Actualizar extractores y re-procesar:**
   ```bash
   # Modificas extractors/example_com.py
   news article fetch-cached --domain example.com --reindex
   # → Re-procesa solo artículos de ese dominio con el extractor nuevo
   ```

3. **Importación inicial (primera vez):**
   ```bash
   news article fetch-cached
   # → Solo procesa artículos que no existen en news.db
   ```

4. **Sincronización completa (actualizar todo):**
   ```bash
   news article fetch-cached --reindex
   # → Actualiza TODOS los artículos existentes con el contenido del caché
   ```

### Forzar Re-descarga

Si un sitio actualiza un artículo y quieres obtener la versión fresca:

```bash
# Forzar descarga fresca (actualiza caché + news.db)
news article fetch "URL" --reindex
```

### URLs Temporales

Para URLs que no quieres cachear (ej: URLs firmadas con tokens):

```bash
news article fetch "https://example.com/article?token=xyz123" --dont-cache
```

## Ventajas

1. **Velocidad**: Re-procesamiento instantáneo sin HTTP requests
2. **Desarrollo**: Iteración rápida en extractores
3. **Costos**: Evita re-descargas innecesarias
4. **Confiabilidad**: No dependes de que el sitio siga disponible
5. **Offline**: Puedes trabajar sin conexión

## Limitaciones

1. **No detecta cambios**: Si un artículo cambia en el sitio, el caché no se actualiza automáticamente
   - Solución: Usar `--cache-no-read` para forzar re-descarga
2. **Espacio en disco**: El caché crece indefinidamente
   - Solución: Usar `news cache clear --domain` periódicamente
3. **No expira**: Entradas permanecen para siempre
   - Esto es intencional para desarrollo

## Variables de Entorno

```bash
# .env
CACHE_DB_PATH=data/cache.db  # Ubicación de la base de datos de caché
```

Default: `data/cache.db`

## Notas de Implementación

- El campo `accessed_at` se actualiza cada vez que se lee del caché (útil para futuras estrategias LRU)
- El hash SHA-256 es el mismo que se usa en `news.db` para deduplicación de artículos
- La tabla tiene índices compuestos para queries eficientes por dominio + fecha
- Usar `--cache-no-save` no afecta lecturas: si existe en caché, se usará
- El caché es completamente transparente: si falla, cae back a HTTP request normal
