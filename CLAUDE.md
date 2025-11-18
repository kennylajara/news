# CLAUDE.md

Este archivo proporciona reglas y buenas prácticas para Claude Code al trabajar en este repositorio.

## Reglas de Desarrollo

### 1. Documentación

- **Documentación técnica va en `docs/`**, no en README ni CLAUDE.md
- **README es para información general**: instalación, uso básico, enlaces a docs
- **CLAUDE.md es para reglas y prácticas**, no detalles técnicos
- Al agregar features complejas, actualizar documentación en `docs/`

### 2. Gestión de Versiones

- La versión se define **una sola vez** en `pyproject.toml`
- El CLI lee la versión vía `importlib.metadata.version("news")`
- **Nunca** hardcodear versiones en el código

### 3. Imports

- Este proyecto usa **layout `src/`**
- Los imports **NO incluyen** el prefijo `src.`
- ✅ Correcto: `from commands import article`
- ❌ Incorrecto: `from src.commands import article`

### 4. Base de Datos

- **SQLite es la única fuente de verdad** - no guardar JSON, HTML, etc.
- Usar métodos de `Database` class, no SQL crudo
- Siempre cerrar sesiones con `session.close()` o usar context managers
- Los comandos CLI ya manejan sesiones correctamente
- **TODAS las tablas deben tener `created_at` y `updated_at` indexados** - son campos críticos para búsquedas y ordenamiento

#### Sistema de Caché

- **Dos bases de datos separadas**:
  - `data/news.db` - Base de datos principal (artículos procesados, entidades, clusters, etc.)
  - `data/cache.db` - Caché de contenido HTML original de URLs
- **El caché es tu amigo durante desarrollo**:
  - Si necesitas recrear `news.db` para probar cambios de schema, **PRIMERO verifica el caché**
  - Usa `uv run news cache stats` para ver qué URLs ya están descargadas
  - Usa `uv run news cache domains` para ver qué dominios tienes cacheados
  - **NUNCA borres `cache.db` a menos que sea absolutamente necesario** - contiene descargas HTTP que pueden no estar disponibles después
- **Workflows recomendados**:
  ```bash
  # Antes de recrear news.db, verificar qué tienes en caché
  uv run news cache stats
  uv run news cache domains

  # Ver URLs cacheadas para un dominio específico
  uv run news cache list --domain diariolibre.com
  uv run news cache list --limit 50  # Ver más URLs

  # Recrear news.db y repoblar desde caché (MUY RÁPIDO)
  rm data/news.db
  # Copia las URLs del output de 'cache list' y úsalas:
  uv run news article fetch "<URL-del-cache>"  # Lee del caché automáticamente

  # Ver detalles de un URL específico (incluyendo preview del HTML)
  uv run news cache show "<URL>"
  ```
- **Cuándo forzar descarga fresca**:
  - Usa `--cache-no-read` solo si el sitio actualizó el contenido
  - Usa `--cache-no-save` para URLs temporales (con tokens, firmas, etc.)
- **Ver `docs/cache.md`** para detalles completos del sistema de caché

### 5. Extractores

- **Un extractor por dominio**: `example.com` → `src/extractors/example_com.py`
- Debe implementar `extract(html_content, url) -> dict`
- Usar funciones helper de `html_to_markdown.py`
- **Contenido debe ser Markdown**, no HTML
- Retornar strings vacíos `""` o listas vacías `[]`, nunca `None`
- Ver `docs/extractors.md` para template completo

### 6. CLI Commands

- Usar **Click**
- Comandos agrupados: `article`, `domain`, `entity`, `process`, y `flash`
- Output con colores: verde=éxito, rojo=error, amarillo=advertencia
- Confirmaciones para operaciones destructivas
- Ver `--help` siempre debe ser útil
- **TODOS los comandos que listan resultados DEBEN tener paginación**:
  - Usar `click.echo_via_pager()` cuando hay más de 20 resultados
  - Permitir override con variable de entorno o flag `--no-pager`
  - Formato de paginación: preparar output completo y pasar a pager
  - Ejemplo: `click.echo_via_pager(output_text)`

### 7. Dependencias

- Usar **uv** para gestión de paquetes, no pip
- `uv sync` para instalar/actualizar
- `uv add` para agregar nuevas dependencias
- Versiones específicas (ej: click==8.3.0)

### 8. Testing

- Actualmente **no hay suite de tests**
- Testing manual vía comandos CLI
- Al agregar tests en el futuro, usar pytest

### 9. Async/Performance

- Actualmente **single-threaded**, no async
- Descargas secuenciales solamente
- Si se agrega async en el futuro, considerar:
  - `aiohttp` para descargas
  - `asyncio` para concurrencia
  - Mantener API síncrona del CLI

### 10. Variables de Entorno y Configuración

- **Usar `src/settings.py`** para acceder a variables de entorno
- **Nunca** acceder directamente a `os.getenv()` desde otros módulos
- Usar función `get_setting(key, default)` que protege contra modificación accidental
- **Archivo `.env` NO se commitea** - solo `.env.example`
- Variables sensibles: `OPENAI_API_KEY`, `DEBUG`, etc.
- Al agregar nueva configuración, actualizar `.env.example`

### 11. LLM y Structured Outputs

- **Modelo usado**: `gpt-5`, `gpt-5-mini` o `gpt-5-nano` (modelo más reciente, eficiente y económico que gpt-4o)
  - Configurable vía `OPENAI_MODEL` en `.env`
  - Default en `src/settings.py` es `gpt-5-nano`
- **Estructura de prompts**: Dos archivos Jinja separados
  - `{task}_system_prompt.md.jinja` - Instrucciones para el LLM
  - `{task}_user_prompt.md.jinja` - Datos específicos del contexto
- **Schema Pydantic**: `{task}.py` con clase `StructuredOutput`
- **Ubicación**: Todos en `src/llm/prompts/`
- **Wrapper genérico**: Usar `openai_structured_output(task_name, data)`
- **Manejo de errores**: LLM puede fallar, no debe romper todo el procesamiento
- **Rate limits**: Considerar límites de la API de OpenAI

### 12. Seguridad

- User-Agent header para evitar bloqueos
- **API keys en `.env`**, nunca en código
- Sanitizar HTML antes de parsear (ya implementado en `clean_html()`)

### 13. Git y Commits

- Este proyecto **requiere commits firmados con GPG**
- Claude Code **NO puede firmar commits**
- Workflow para commits:
  1. Claude prepara el stage de git (por ejemplo con `git add`)
  2. Claude genera el mensaje de commit
  3. **El usuario debe copiar y pegar el mensaje en su consola** para firmar el commit
  4. El usuario ejecuta: `git commit -S -m "mensaje"`
- **NUNCA** intentar hacer commit directamente desde Claude Code
- **NUNCA** deshabilitar GPG signing (`commit.gpgsign false`)

## Documentación Técnica

Para detalles técnicos, consultar:

- **[docs/architecture.md](docs/architecture.md)** - Arquitectura del sistema, flujo de datos, patrones
- **[docs/database.md](docs/database.md)** - Esquema de base de datos, operaciones CRUD
- **[docs/cache.md](docs/cache.md)** - Sistema de caché de URLs (LEER ANTES DE RECREAR news.db)
- **[docs/extractors.md](docs/extractors.md)** - Guía completa para crear extractores
- **[docs/processing.md](docs/processing.md)** - Sistema de batches, NER, clustering y flash news

> Importante: Siempre actualizar la documentación técnica cuando se modifica código relacionado a lo que está documentado

## Comandos de Desarrollo

```bash
# Setup inicial
uv sync
cp .env.example .env  # Configurar API keys

# Ejecutar CLI
uv run news --help
uv run news article fetch "<URL>"
uv run news article list
uv run news domain stats

# Gestión de caché (ÚTIL PARA DESARROLLO)
uv run news cache stats                        # Ver estadísticas generales
uv run news cache domains                 # Ver dominios cacheados
uv run news cache list                         # Ver URLs cacheadas (últimas 20)
uv run news cache list --domain example.com    # Filtrar por dominio
uv run news cache list --limit 50              # Ver más URLs
uv run news cache show "<URL>"                 # Ver detalles + preview HTML
uv run news cache clear --domain example.com   # Limpiar caché de un dominio

# Procesar artículos con IA
# Paso 1: Enriquecimiento base (clustering + NER)
uv run news process start -d diariolibre.com -t enrich_article -s 10

# Paso 2: Generación de flash news (OpenAI)
uv run news process start -d diariolibre.com -t generate_flash_news -s 10

# Ver flash news generados
uv run news flash list

# Calcular relevancia global de entidades (PageRank)
uv run news entity rerank
uv run news entity list --order-by global_rank --limit 20

# Acceso directo a base de datos
sqlite3 data/news.db
sqlite3 data/cache.db  # Ver URLs cacheadas
```

## Notas Importantes

- Este proyecto es para un **hackathon**:
  - Priorizar velocidad de desarrollo
  - Abraza los breaking changes
- Los **selectores CSS son frágiles** - si extracción falla, revisar HTML del sitio
- **Parseo de fecha es específico del sitio** - cada extractor maneja su formato
- No hay sistema de migraciones todavía - cambios en schema requieren recrear DB

## Contexto del Proyecto

Leer el [README](/README.md).
