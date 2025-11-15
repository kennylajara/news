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

### 5. Extractores

- **Un extractor por dominio**: `example.com` → `src/extractors/example_com.py`
- Debe implementar `extract(html_content, url) -> dict`
- Usar funciones helper de `html_to_markdown.py`
- **Contenido debe ser Markdown**, no HTML
- Retornar strings vacíos `""` o listas vacías `[]`, nunca `None`
- Ver `docs/extractors.md` para template completo

### 6. CLI Commands

- Usar **Click**
- Comandos agrupados: `article` y `domain`
- Output con colores: verde=éxito, rojo=error, amarillo=advertencia
- Confirmaciones para operaciones destructivas
- Ver `--help` siempre debe ser útil

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

### 10. Seguridad

- User-Agent header para evitar bloqueos
- No guardar credenciales en código
- Sanitizar HTML antes de parsear (ya implementado en `clean_html()`)

### 11. Git y Commits

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
- **[docs/extractors.md](docs/extractors.md)** - Guía completa para crear extractores

> Importante: Siempre actualizar la documentación técnica cuando se modifica código relacionado a lo que está documentado

## Comandos de Desarrollo

```bash
# Setup inicial
uv sync

# Ejecutar CLI
uv run news --help
uv run news article fetch "<URL>"
uv run news article list
uv run news domain stats

# Acceso directo a base de datos
sqlite3 data/news.db
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
