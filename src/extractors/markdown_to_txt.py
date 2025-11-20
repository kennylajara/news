"""
Módulo para convertir Markdown a texto plano.

Remueve todo el formato Markdown y extrae solo el texto puro,
preservando la estructura básica de párrafos y líneas.
"""

import re


def remove_markdown_formatting(text):
    """
    Convierte texto Markdown a texto plano, removiendo todo el formato.

    Args:
        text: String de texto en formato Markdown

    Returns:
        String de texto plano sin formato
    """
    if not text:
        return ""

    # Remover headers (# ## ### etc)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remover enlaces [texto](url) -> texto
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # Remover negritas **texto** o __texto__ -> texto
    text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)

    # Remover itálicas *texto* o _texto_ -> texto
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)

    # Remover blockquotes (> texto)
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)

    # Remover viñetas de listas (- texto, * texto)
    # NO text = re.sub(r'^[\-\*]\s+', '', text, flags=re.MULTILINE)

    # NO Remover listas numeradas (1. texto)
    # text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)

    # Remover código inline `código`
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Remover bloques de código ```código```
    text = re.sub(r'```[\s\S]*?```', '', text)

    # Limpiar espacios múltiples (preservar saltos de línea)
    text = re.sub(r' +', ' ', text)

    # Limpiar líneas vacías extras (3 o más -> 2)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def markdown_to_plain_text(markdown_content):
    """
    Convierte contenido Markdown completo a texto plano.

    Alias para remove_markdown_formatting() con nombre más descriptivo.

    Args:
        markdown_content: String de contenido en formato Markdown

    Returns:
        String de texto plano
    """
    return remove_markdown_formatting(markdown_content)
