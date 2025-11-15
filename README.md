# News Portal

Portal de resúmenes de noticias que extrae, procesa y almacena artículos de diferentes fuentes.

## Descripción

Este proyecto descarga noticias de diversos medios digitales, extrae su contenido de forma estructurada usando extractores especializados por dominio, y lo almacena en una base de datos SQLite.

## Características

- **Extracción automática**: Descarga y limpia HTML de artículos de noticias
- **Extractores por dominio**: Cada medio tiene su propio extractor especializado
- **Conversión a Markdown**: El contenido se procesa preservando formato (negritas, enlaces, títulos)
- **Base de datos SQLite**: Almacenamiento estructurado con relaciones (fuentes, artículos, tags)
- **Deduplicación**: No reprocesa artículos ya descargados
- **CLI completo**: Interfaz de línea de comandos con Click

## Estructura del Proyecto

```
news/
├── src/
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── article.py         # Comandos de gestión de artículos
│   │   └── domain.py          # Comandos de gestión de fuentes
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py          # Modelos SQLAlchemy (Source, Article, Tag)
│   │   └── database.py        # Clase Database con operaciones CRUD
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── base.py            # Clase base para extractores
│   │   ├── html_to_markdown.py # Utilidades de conversión HTML→Markdown
│   │   └── {domain}_{ext}.py    # Extractor específico por dominio
│   ├── cli.py                 # CLI principal (Click)
│   └── get_news.py            # Funciones de descarga y extracción
├── pyproject.toml             # Configuración del proyecto y dependencias
└── uv.lock                    # Lock file de dependencias
```

## Instalación

### Prerrequisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (administrador de paquetes rápido)

### Pasos

1. Instalar uv (si no lo tienes):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Clonar el repositorio:
```bash
git clone https://github.com/kennylajara/news.git
cd news
```

3. Sincronizar dependencias (uv crea automáticamente el entorno virtual):
```bash
uv sync
```

## Uso

El proyecto incluye una CLI completa construida con Click.

### Comandos principales

```bash
uv run news --help              # Ver ayuda general
uv run news article --help      # Ver comandos de artículos
uv run news domain --help       # Ver comandos de dominios
```

#### Artículos

```bash
# Descargar artículo
uv run news article fetch "<URL>"

# Listar artículos
uv run news article list                           # Últimos 10
uv run news article list --limit 20                # Con límite
uv run news article list --source diariolibre.com  # Por fuente
uv run news article list --tag "política"          # Por tag

# Ver artículo
uv run news article show <ID>         # Vista previa
uv run news article show <ID> --full  # Artículo completo

# Eliminar artículo
uv run news article delete <ID>
```

### Fuentes

```bash
# Listar fuentes
uv run news domain list
uv run news domain show <dominio>
uv run news domain stats

# Agregar fuente
uv run news domain add <dominio> --name "Nombre"

# Eliminar fuente
uv run news domain delete <dominio>
```

## Tecnologías

- **Python 3.12+**
- **uv**: Gestor de paquetes rápido
- **Click 8.3.0**: Framework para CLI
- **SQLAlchemy 2.0**: ORM para SQLite
- **BeautifulSoup4 + lxml**: Parsing de HTML
- **Requests**: Descarga HTTP

## Documentación

- **[Arquitectura](docs/architecture.md)** - Flujo de componentes, pipeline, patrones
- **[Base de Datos](docs/database.md)** - Esquema, operaciones CRUD, deduplicación
- **[Crear Extractores](docs/extractors.md)** - Guía completa con templates y ejemplos

## Fuentes Soportadas

- ✓ diariolibre.com

## Roadmap

- [ ] Agregar más extractores (periódicos dominicanos e internacionales)
- [ ] Sistema de resúmenes automáticos
- [ ] API REST para consulta de artículos
- [ ] Frontend para visualización
- [ ] Sistema de publicación automática
- [ ] Descarga asíncrona con aiohttp
