"""
Extractor para diariolibre.com
"""

from bs4 import BeautifulSoup
import re
from . import html_to_markdown


# Selectores CSS para elementos del artículo
SELECTORS = {
    'title': 'h1',
    'subtitle': 'div.subtitle > p',
    'author': 'address.author strong',
    'date': 'time#detail-datetime',
    'location': 'time#detail-datetime a:first-child',
    'content': 'div.detail-body',
    'tags': 'div.tags-container a',
    'breadcrumb': 'ul.breadcrumb li'
}


def extract(html_content, url):
    """
    Extrae datos de artículos de Diario Libre.

    Args:
        html_content: HTML limpio del artículo
        url: URL original del artículo

    Returns:
        dict con datos del artículo
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Extraer campos básicos usando selectores
    titulo = html_to_markdown.extract_text_from_element(soup, SELECTORS['title'])
    subtitulo = html_to_markdown.extract_text_from_element(soup, SELECTORS['subtitle'])
    autor = html_to_markdown.extract_text_from_element(soup, SELECTORS['author'])
    lugar = html_to_markdown.extract_text_from_element(soup, SELECTORS['location'])

    # Extraer y parsear fecha
    fecha = extract_date(soup)

    # Extraer contenido del artículo
    contenido = ""
    detail_body = soup.select_one(SELECTORS['content'])
    if detail_body:
        contenido = html_to_markdown.extract_article_content(detail_body)

    # Extraer tags
    tags = html_to_markdown.extract_list_from_elements(soup, SELECTORS['tags'])

    # Extraer categoría del breadcrumb
    categoria = extract_category(soup)

    return {
        "title": titulo,
        "subtitle": subtitulo,
        "author": autor,
        "date": fecha,
        "location": lugar,
        "content": contenido,
        "tags": tags,
        "category": categoria
    }


def extract_date(soup):
    """
    Extrae y convierte la fecha de Diario Libre a formato RFC 3339.

    Args:
        soup: BeautifulSoup object del HTML

    Returns:
        str: Fecha en formato RFC 3339 o cadena vacía
    """
    time_tag = soup.select_one(SELECTORS['date'])
    if not time_tag:
        return ""

    # Buscar el texto de la fecha (ej: "nov. 15, 2025 | 12:01 a. m.")
    date_links = time_tag.find_all('a')
    if len(date_links) >= 2:
        fecha_texto = date_links[1].get_text(strip=True)
        return parse_diariolibre_date(fecha_texto)

    return ""


def extract_category(soup):
    """
    Extrae la categoría del breadcrumb.

    Args:
        soup: BeautifulSoup object del HTML

    Returns:
        str: Categoría en formato "Categoria/Subcategoria"
    """
    breadcrumb_ul = soup.select_one('ul.breadcrumb')
    if not breadcrumb_ul:
        return ""

    items = breadcrumb_ul.find_all('li')
    # Tomar los items después de "Portada"
    cat_items = [item.get_text(strip=True) for item in items[1:]]
    return "/".join(cat_items)


def parse_diariolibre_date(fecha_texto):
    """
    Convierte fecha de Diario Libre a formato RFC 3339.
    Entrada: "nov. 15, 2025 | 12:01 a. m."
    Salida: "2025-11-15T00:01:00-04:00"

    Args:
        fecha_texto: Texto de fecha en formato de Diario Libre

    Returns:
        str: Fecha en formato RFC 3339 (GMT-4) o cadena vacía si hay error
    """
    try:
        # Limpiar el texto
        fecha_texto_original = fecha_texto.strip()

        # Mapeo de meses en español
        meses = {
            'ene': 1, 'ene.': 1,
            'feb': 2, 'feb.': 2,
            'mar': 3, 'mar.': 3,
            'abr': 4, 'abr.': 4,
            'may': 5, 'may.': 5,
            'jun': 6, 'jun.': 6,
            'jul': 7, 'jul.': 7,
            'ago': 8, 'ago.': 8,
            'sep': 9, 'sep.': 9, 'sept': 9, 'sept.': 9,
            'oct': 10, 'oct.': 10,
            'nov': 11, 'nov.': 11,
            'dic': 12, 'dic.': 12
        }

        # Parsear con regex: "nov. 15, 2025 | 12:01 a. m."
        pattern = r'(\w+\.?)\s+(\d+),\s+(\d{4})'
        match = re.search(pattern, fecha_texto_original)

        if match:
            mes_texto = match.group(1).lower()
            dia = int(match.group(2))
            año = int(match.group(3))
            mes = meses.get(mes_texto, 1)

            # Para la hora, buscar en el texto original completo
            hora = 0
            minuto = 0

            # Buscar patrón de hora: "12:01 a. m." o "12:01 p. m."
            time_pattern = r'(\d+):(\d+)\s*(a\.|p\.)\s*m\.'
            time_match = re.search(time_pattern, fecha_texto_original)

            if time_match:
                hora = int(time_match.group(1))
                minuto = int(time_match.group(2))
                periodo = time_match.group(3)

                # Convertir a formato 24 horas
                if periodo == 'p.' and hora != 12:
                    hora += 12
                elif periodo == 'a.' and hora == 12:
                    hora = 0

            # Zona horaria de República Dominicana (GMT-4)
            return f"{año:04d}-{mes:02d}-{dia:02d}T{hora:02d}:{minuto:02d}:00-04:00"

        return ""
    except Exception as e:
        print(f"Error parseando fecha '{fecha_texto}': {e}")
        return ""
