# Crear un Extractor

## Introducción

Los extractores son plugins que se auto-descubren por nombre de dominio. Cada medio tiene su propio extractor que sabe cómo extraer contenido de su HTML específico.

## Convención de Nombres

- Dominio: `example.com` → Archivo: `src/extractors/example_com.py`
- Regla: Reemplazar puntos por guiones bajos

## Interfaz Requerida

Cada extractor debe implementar una función `extract(html_content, url)` que retorne un diccionario.

### Template Completo

```python
"""
Extractor para example.com
"""

from bs4 import BeautifulSoup
from . import html_to_markdown

# Define selectores CSS para este sitio
SELECTORS = {
    'title': 'h1.headline',
    'subtitle': '.deck',
    'author': '.byline .author',
    'date': 'time.published',
    'location': '.dateline',
    'content': '.article-body',
    'tags': 'a.tag',
    'breadcrumb': 'nav.breadcrumb li'
}

def extract(html_content, url):
    """
    Extrae datos de artículos de example.com

    Args:
        html_content (str): HTML limpio del artículo
        url (str): URL original del artículo

    Returns:
        dict: Datos del artículo con las siguientes claves:
            - title (str): Título del artículo
            - subtitle (str): Subtítulo o bajada
            - author (str): Nombre del autor
            - date (str): Fecha en formato RFC 3339 ("2025-11-15T00:01:00-04:00")
            - location (str): Ciudad de origen del artículo
            - content (str): Contenido en formato Markdown
            - tags (list): Lista de tags/etiquetas
            - category (str): Categoría/Subcategoría
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Extraer campos básicos usando funciones helper
    title = html_to_markdown.extract_text_from_element(soup, SELECTORS['title'])
    subtitle = html_to_markdown.extract_text_from_element(soup, SELECTORS['subtitle'])
    author = html_to_markdown.extract_text_from_element(soup, SELECTORS['author'])
    location = html_to_markdown.extract_text_from_element(soup, SELECTORS['location'])

    # Extraer contenido y convertir a Markdown
    content_elem = soup.select_one(SELECTORS['content'])
    content = html_to_markdown.extract_article_content(content_elem) if content_elem else ""

    # Extraer lista de tags
    tags = html_to_markdown.extract_list_from_elements(soup, SELECTORS['tags'])

    # Extraer categoría desde breadcrumb
    category = extract_category(soup)

    # Parsear fecha (específico del sitio)
    date = parse_date(soup)

    return {
        "title": title,
        "subtitle": subtitle,
        "author": author,
        "date": date,
        "location": location,
        "content": content,
        "tags": tags,
        "category": category
    }

def parse_date(soup):
    """
    Parsea la fecha del artículo al formato RFC 3339.
    Esta función es específica para cada medio.
    """
    date_elem = soup.select_one(SELECTORS['date'])
    if not date_elem:
        return ""

    # Implementar lógica específica del sitio
    # Ejemplo: extraer atributo datetime o parsear texto
    return date_elem.get('datetime', '')

def extract_category(soup):
    """
    Extrae la categoría desde el breadcrumb o metadatos.
    """
    breadcrumb_items = soup.select(SELECTORS['breadcrumb'])
    if len(breadcrumb_items) > 1:
        return " / ".join([item.get_text(strip=True) for item in breadcrumb_items[1:]])
    return ""
```

## Funciones Helper Disponibles

El módulo `html_to_markdown.py` proporciona funciones reutilizables:

### `extract_text_from_element(soup, selector)`
Extrae texto de un solo elemento.

```python
title = html_to_markdown.extract_text_from_element(soup, 'h1.headline')
```

### `extract_list_from_elements(soup, selector)`
Extrae texto de múltiples elementos y retorna una lista.

```python
tags = html_to_markdown.extract_list_from_elements(soup, 'a.tag')
# Retorna: ["política", "economía", "internacional"]
```

### `extract_article_content(element)`
Convierte HTML a Markdown preservando formato.

```python
content_elem = soup.select_one('.article-body')
content = html_to_markdown.extract_article_content(content_elem)
# Retorna Markdown con **negritas**, [enlaces](url), etc.
```

### `process_inline_formatting(element)`
Convierte `<strong>`, `<em>`, `<a>` a sintaxis Markdown.

## Formato de Fecha

Las fechas deben estar en formato RFC 3339:
- `"2025-11-15T00:01:00-04:00"` (con timezone)
- `"2025-11-15T00:01:00"` (sin timezone, asume UTC)

## Consideraciones Importantes

1. **Selectores CSS son frágiles**: Si la extracción falla, probablemente el sitio cambió su estructura HTML
2. **Parseo de fecha es específico del sitio**: Cada extractor debe manejar el formato de fecha de su fuente
3. **Contenido debe ser Markdown**: Usar helpers `html_to_markdown`, no retornar HTML crudo
4. **Retornar strings vacíos**: Si un campo no existe, retornar `""` o `[]` para listas, nunca `None`

## Detectar Automáticamente

Una vez creado el archivo `src/extractors/{domain}_com.py`, el sistema lo detectará automáticamente al descargar artículos de ese dominio. No se requiere registro manual.

## Ejemplo Real

Ver `src/extractors/diariolibre_com.py` para un ejemplo completo de extractor en funcionamiento.
