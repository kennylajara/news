# News Portal

Portal de resúmenes de noticias que extrae, procesa y publica artículos de diferentes fuentes.

## Descripción

Este proyecto descarga noticias de diversos medios digitales, extrae su contenido de forma estructurada y lo convierte a formato JSON para su posterior procesamiento y publicación.

## Características

- **Extracción automática**: Descarga y limpia HTML de artículos de noticias
- **Extractores por dominio**: Cada medio tiene su propio extractor especializado
- **Conversión a Markdown**: El contenido se procesa preservando formato (negritas, enlaces, títulos)
- **Formato estructurado**: Genera JSON con campos estándar (título, autor, fecha, ubicación, contenido, tags, categoría)
- **Deduplicación**: No reprocesa artículos ya descargados

## Estructura del Proyecto

```
news/
├── commands/
│   ├── __init__.py
│   ├── article.py         # Comandos de gestión de artículos
│   └── domain.py          # Comandos de gestión de fuentes
├── db/
│   ├── __init__.py
│   ├── models.py          # Modelos SQLAlchemy (Source, Article, Tag)
│   └── database.py        # Clase Database con operaciones CRUD
├── extractors/
│   ├── __init__.py
│   ├── base.py            # Clase base para extractores
│   ├── html_to_markdown.py # Utilidades de conversión HTML→Markdown
│   └── {domain}_com.py    # Extractor específico por dominio
├── cli.py                 # CLI principal (Click)
├── get_news.py            # Funciones de descarga y extracción
├── pyproject.toml         # Configuración del proyecto y dependencias
└── uv.lock                # Lock file de dependencias
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

### Gestión de Artículos

**Descargar un artículo:**
```bash
uv run news article fetch "<URL>"
```

**Listar artículos:**
```bash
uv run news article list                    # Últimos artículos
uv run news article list --limit 20         # Con límite
uv run news article list --source diariolibre.com  # Por fuente
uv run news article list --tag "España"     # Por tag
```

**Ver detalles:**
```bash
uv run news article show <ID>
```

**Eliminar:**
```bash
uv run news article delete <ID>
```

### Gestión de Fuentes

**Listar fuentes:**
```bash
uv run news domain list
uv run news domain show <dominio>
uv run news domain stats
```

**Agregar fuente:**
```bash
uv run news domain add <dominio> --name "Nombre"
```

**Eliminar fuente:**
```bash
uv run news domain delete <dominio>
```

## Formato de Datos

Los artículos se almacenan en una base de datos SQLite (`data/news.db`) con la siguiente estructura:

### Tablas principales:

- **sources**: Fuentes de noticias (dominio, nombre)
- **articles**: Artículos completos con metadata
- **tags**: Tags únicos
- **article_tags**: Relación muchos-a-muchos entre artículos y tags

### Esquema de Article:

```python
{
  "hash": "sha256_completo",  # SHA-256 completo de la URL
  "url": "URL original",
  "title": "Título del artículo",
  "subtitle": "Subtítulo o bajada",
  "author": "Nombre del autor",
  "published_date": "2025-11-15 00:01:00",
  "location": "Ciudad de origen",
  "content": "Contenido en Markdown con **negritas** y [enlaces](url)",
  "category": "Categoría/Subcategoría",
  "tags": ["tag1", "tag2", "tag3"]  # Relación M:N
}
```

## Crear un Nuevo Extractor

Para agregar soporte a un nuevo medio:

1. Crear archivo `extractors/{domain}_com.py` (reemplazar puntos por guiones bajos)

2. Implementar función `extract(html_content, url)`:

```python
"""
Extractor para ejemplo.com
"""

from bs4 import BeautifulSoup
from . import html_to_markdown

SELECTORS = {
    'title': 'h1.article-title',
    'subtitle': 'p.subtitle',
    'author': 'span.author-name',
    'date': 'time',
    'location': 'span.location',
    'content': 'div.article-body',
    'tags': 'a.tag',
    'breadcrumb': 'nav.breadcrumb li'
}

def extract(html_content, url):
    """
    Extrae datos de artículos de ejemplo.com

    Args:
        html_content: HTML limpio del artículo
        url: URL original del artículo

    Returns:
        dict con datos del artículo
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Extraer campos básicos
    title = html_to_markdown.extract_text_from_element(soup, SELECTORS['title'])
    subtitle = html_to_markdown.extract_text_from_element(soup, SELECTORS['subtitle'])
    author = html_to_markdown.extract_text_from_element(soup, SELECTORS['author'])
    location = html_to_markdown.extract_text_from_element(soup, SELECTORS['location'])

    # Extraer contenido
    content_element = soup.select_one(SELECTORS['content'])
    content = html_to_markdown.extract_article_content(content_element) if content_element else ""

    # Extraer tags
    tags = html_to_markdown.extract_list_from_elements(soup, SELECTORS['tags'])

    return {
        "title": title,
        "subtitle": subtitle,
        "author": author,
        "date": "",  # Implementar parseo de fecha específico
        "location": location,
        "content": content,
        "tags": tags,
        "category": ""  # Implementar extracción de categoría
    }
```

3. El extractor será detectado y usado automáticamente

## Dependencias

- **requests**: Descarga de HTML
- **beautifulsoup4**: Parsing y manipulación de HTML
- **lxml**: Parser rápido para BeautifulSoup
- **sqlalchemy**: ORM para base de datos SQLite
- **click**: Framework para CLI (interfaz de línea de comandos)

## Dominios Soportados

- ✓ diariolibre.com

## Roadmap

- [ ] Agregar más extractores (periódicos dominicanos e internacionales)
- [ ] Sistema de resúmenes automáticos
- [ ] API para consulta de artículos
- [ ] Frontend para visualización
- [ ] Base de datos para almacenamiento
- [ ] Sistema de publicación automática
