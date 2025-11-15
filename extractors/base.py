"""
Clase base para extractores de contenido.
"""

from abc import ABC, abstractmethod


class BaseExtractor(ABC):
    """Clase base para todos los extractores de dominios."""

    @abstractmethod
    def extract(self, html_content, url):
        """
        Extrae datos del artículo desde HTML.

        Args:
            html_content: Contenido HTML limpio
            url: URL original del artículo

        Returns:
            dict con claves: titulo, subtitulo, autor, fecha, contenido, tags, categoria
        """
        pass
