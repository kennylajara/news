"""
Módulo reutilizable para convertir HTML a Markdown.

Proporciona funciones genéricas para extraer y formatear contenido de artículos HTML
a formato Markdown, independientemente del sitio web de origen.
"""

import re
from bs4 import BeautifulSoup, NavigableString


def ensure_period(text):
    """
    Asegura que el texto termine con punto final si no tiene puntuación de cierre.

    Args:
        text: String de texto

    Returns:
        Texto con punto final si es necesario
    """
    if not text:
        return text

    text = text.strip()
    if not text:
        return text

    # Puntuación de cierre válida
    ending_punctuation = ('.', '!', '?', '…', ':', ';', ')', ']', '"', "'", '»')

    # Si no termina con puntuación de cierre, agregar punto
    if not text.endswith(ending_punctuation):
        return text + '.'

    return text


def normalize_inline_spaces(element):
    """
    Normaliza espacios en etiquetas inline.
    Mueve espacios finales fuera de las etiquetas de cierre y espacios iniciales fuera de apertura.
    Ej: <strong>palabra </strong>texto -> <strong>palabra</strong> texto
    """
    from bs4 import NavigableString

    for tag in element.find_all(['strong', 'em', 'a']):
        # Obtener contenido de texto directo del tag
        if tag.string:
            text = str(tag.string)
            modified = False

            # Si comienza con espacio(s)
            if text.startswith(' '):
                stripped = text.lstrip()
                spaces = text[:len(text) - len(stripped)]
                # Agregar espacios antes del tag
                if tag.previous_sibling:
                    if isinstance(tag.previous_sibling, str):
                        tag.previous_sibling.replace_with(tag.previous_sibling + spaces)
                    else:
                        tag.insert_before(NavigableString(spaces))
                else:
                    tag.insert_before(NavigableString(spaces))
                text = stripped
                modified = True

            # Si termina con espacio(s)
            if text.endswith(' '):
                stripped = text.rstrip()
                spaces = text[len(stripped):]
                # Agregar espacios después del tag
                if tag.next_sibling:
                    if isinstance(tag.next_sibling, str):
                        tag.next_sibling.replace_with(spaces + tag.next_sibling)
                    else:
                        tag.insert_after(NavigableString(spaces))
                else:
                    tag.insert_after(NavigableString(spaces))
                text = stripped
                modified = True

            # Solo reemplazar si hubo modificación
            if modified:
                tag.string.replace_with(text)


def process_inline_formatting(element):
    """Procesa formato inline (negritas, enlaces, énfasis)."""
    # Primero normalizar espacios
    normalize_inline_spaces(element)

    result = []

    # Procesar solo los hijos directos, no todos los descendants
    for child in element.children:
        if isinstance(child, str):
            text = str(child)
            if text.strip():
                result.append(text)
        elif hasattr(child, 'name'):
            if child.name == 'strong':
                text = child.get_text(strip=True)
                if text:
                    result.append(f"**{text}**")
            elif child.name == 'em':
                text = child.get_text(strip=True)
                if text:
                    result.append(f"*{text}*")
            elif child.name == 'a':
                text = child.get_text(strip=True)
                href = child.get('href', '')
                if text and href:
                    result.append(f"**[{text}]({href})**")
                elif text:
                    result.append(text)
            else:
                # Para otros tags, extraer texto simple
                text = child.get_text(strip=True)
                if text:
                    result.append(text)

    # Unir sin agregar espacios extra
    text = ''.join(result)
    # Limpiar espacios múltiples pero preservar espacios normales
    text = re.sub(r' +', ' ', text)
    # Eliminar espacios antes de puntuación
    text = re.sub(r' +([.,;:!?\)])', r'\1', text)
    # Eliminar espacios después de paréntesis de apertura
    text = re.sub(r'\( +', r'(', text)

    return text.strip()


def process_paragraph(p_element):
    """Procesa un párrafo preservando formato inline (negritas, enlaces)."""
    text = process_inline_formatting(p_element)
    return ensure_period(text)


def extract_article_content(detail_body, exclude_classes=None):
    """
    Extrae el contenido del artículo como markdown, excluyendo elementos incrustados.

    Args:
        detail_body: Elemento BeautifulSoup que contiene el cuerpo del artículo
        exclude_classes: Lista de clases CSS a excluir (ej: ['nota-incrustada', 'social-embed'])

    Returns:
        str: Contenido del artículo en formato Markdown
    """
    if exclude_classes is None:
        exclude_classes = ['nota-incrustada', 'component', 'social-embed', 'tags-container', 'author-info']

    content_parts = []

    for element in detail_body.children:
        # Saltar elementos de navegación y notas incrustadas
        if hasattr(element, 'attrs'):
            classes = element.get('class', [])
            if any(cls in classes for cls in exclude_classes):
                continue
            if element.name == 'div' and any(cls in classes for cls in exclude_classes):
                continue

        # Procesar según tipo de elemento
        if hasattr(element, 'name'):
            if element.name == 'p':
                text = element.get_text(strip=True)
                if text:
                    # Preservar negritas y enlaces
                    processed = process_paragraph(element)
                    if processed:
                        content_parts.append(processed)

            elif element.name == 'h2':
                # Procesar h2 con formato inline para preservar espacios
                text = process_inline_formatting(element)
                text = ensure_period(text)
                if text:
                    content_parts.append(f"\n## {text}\n")

            elif element.name == 'h3':
                text = element.get_text(strip=True)
                text = ensure_period(text)
                if text:
                    content_parts.append(f"\n### {text}\n")

            elif element.name == 'ul' and 'list-text' in element.get('class', []):
                # Lista con viñetas
                items = element.find_all('li')
                for item in items:
                    text = process_inline_formatting(item)
                    text = ensure_period(text)
                    if text:
                        content_parts.append(f"- {text}\n")

    # Unir todo el contenido con doble salto de línea entre párrafos
    full_content = "\n\n".join(content_parts)

    # Limpiar líneas vacías extras (3 o más -> 2)
    full_content = re.sub(r'\n{3,}', '\n\n', full_content)

    return full_content.strip()


def extract_text_from_element(element, selector):
    """
    Extrae texto de un elemento usando un selector CSS.

    Args:
        element: Elemento BeautifulSoup base
        selector: Selector CSS

    Returns:
        str: Texto extraído o cadena vacía
    """
    found = element.select_one(selector)
    if found:
        return found.get_text(strip=True)
    return ""


def extract_list_from_elements(element, selector):
    """
    Extrae lista de textos de múltiples elementos usando un selector CSS.

    Args:
        element: Elemento BeautifulSoup base
        selector: Selector CSS

    Returns:
        list: Lista de textos extraídos
    """
    elements = element.select(selector)
    return [elem.get_text(strip=True) for elem in elements if elem.get_text(strip=True)]
