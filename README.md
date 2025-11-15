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
├── data/
│   └── articles/           # Artículos descargados organizados por dominio
│       └── {domain}/
│           ├── {hash}.html # HTML limpio del artículo
│           └── {hash}.json # Datos extraídos en JSON
├── extractors/
│   ├── __init__.py
│   ├── base.py            # Clase base para extractores
│   ├── html_to_markdown.py # Utilidades de conversión HTML→Markdown
│   └── {domain}_com.py    # Extractor específico por dominio
├── get_news.py            # Script principal para descargar noticias
└── requirements.txt
```

## Instalación

1. Clonar el repositorio:
```bash
git clone <repository-url>
cd news
```

2. Crear y activar entorno virtual:
```bash
python3 -m venv .venv
source .venv/bin/activate  # En Linux/Mac
# o
.venv\Scripts\activate     # En Windows
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

## Uso

### Descargar una noticia

```bash
python get_news.py <URL>
```

**Ejemplo:**
```bash
python get_news.py "https://www.diariolibre.com/mundo/espana/2025/11/15/dominicanos-en-espana-pasan-de-controlar-narcopisos-a-mercenarios/3313400"
```

**Salida:**
```
URL: https://www.diariolibre.com/mundo/espana/2025/11/15/dominicanos-en-espana-pasan-de-controlar-narcopisos-a-mercenarios/3313400
Dominio: diariolibre.com
Hash: 8188211e
Descargando HTML...
Limpiando HTML...
HTML limpio guardado en: data/articles/diariolibre.com/8188211e.html

Buscando extractor para diariolibre.com...
✓ Extractor encontrado: extractors/diariolibre_com.py
Extrayendo datos del artículo...
✓ JSON generado exitosamente: data/articles/diariolibre.com/8188211e.json

Datos extraídos:
  Título: Grupos de españoles de origen dominicano pasan de controlar narcopisos a "mercen...
  Autor: Diario Libre
  Fecha: 2025-11-15T00:01:00-04:00
  Tags: 4 tags
  Contenido: 4555 caracteres

✓ Proceso completado exitosamente!
```

## Formato del JSON

Cada artículo extraído tiene la siguiente estructura:

```json
{
  "title": "Título del artículo",
  "subtitle": "Subtítulo o bajada",
  "author": "Nombre del autor",
  "date": "2025-11-15T00:01:00-04:00",
  "location": "Ciudad de origen",
  "content": "Contenido en Markdown con **negritas** y [enlaces](url)",
  "tags": ["tag1", "tag2", "tag3"],
  "category": "Categoría/Subcategoría",
  "_metadata": {
    "url": "URL original",
    "domain": "dominio.com",
    "hash": "8188211e"
  }
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

## Dominios Soportados

- ✓ diariolibre.com

## Roadmap

- [ ] Agregar más extractores (periódicos dominicanos e internacionales)
- [ ] Sistema de resúmenes automáticos
- [ ] API para consulta de artículos
- [ ] Frontend para visualización
- [ ] Base de datos para almacenamiento
- [ ] Sistema de publicación automática
