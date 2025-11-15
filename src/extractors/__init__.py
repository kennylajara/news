"""
Extractores de contenido para diferentes dominios de noticias.

Cada extractor debe implementar una función extract(html_content, url) que retorna
un diccionario con las siguientes claves:
- titulo: str
- subtitulo: str
- autor: str
- fecha: str (formato RFC 3339)
- contenido: str (markdown)
- tags: list[str]
- categoria: str
"""
