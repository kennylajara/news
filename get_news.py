#!/usr/bin/env python3
"""
Script para descargar noticias y extraer su contenido en formato JSON.
Uso: python get_news.py <URL>
"""

import sys
import os
import hashlib
import json
import requests
from urllib.parse import urlparse
from pathlib import Path
from bs4 import BeautifulSoup, Comment
import importlib


def get_domain(url):
    """Extrae el dominio de una URL"""
    parsed = urlparse(url)
    domain = parsed.netloc
    # Remover www. si existe
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain


def get_url_hash(url):
    """Genera los primeros 8 dígitos del hash SHA256 de una URL"""
    hash_object = hashlib.sha256(url.encode())
    return hash_object.hexdigest()[:8]


def clean_html(html_content):
    """Limpia el HTML removiendo elementos innecesarios"""
    soup = BeautifulSoup(html_content, 'lxml')

    # Eliminar etiquetas específicas y sus contenidos
    for tag in soup(['script', 'style', 'iframe', 'noscript',
                     'input', 'button', 'form', 'svg',
                     'img', 'figure', 'picture', 'nav',
                     'footer']):
        tag.decompose()

    # Eliminar comentarios HTML
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Unwrap etiquetas <font> (eliminar la etiqueta pero mantener su contenido)
    for font_tag in soup.find_all('font'):
        font_tag.unwrap()

    # Normalizar espacios no separables (nbsp) y otros espacios raros a espacios normales
    html_str = str(soup)
    # Reemplazar nbsp (U+00A0) con espacio normal
    html_str = html_str.replace('\u00a0', ' ')
    # Reemplazar otros espacios Unicode raros
    html_str = html_str.replace('\u2009', ' ')  # thin space
    html_str = html_str.replace('\u200a', ' ')  # hair space
    html_str = html_str.replace('\u202f', ' ')  # narrow no-break space
    soup = BeautifulSoup(html_str, 'lxml')

    # Extraer solo el body
    body = soup.find('body')
    if body:
        # Eliminar todos los atributos excepto id, class y href
        for tag in body.find_all(True):
            # Guardar id, class y href si existen
            preserved_attrs = {}
            if 'id' in tag.attrs:
                preserved_attrs['id'] = tag.attrs['id']
            if 'class' in tag.attrs:
                preserved_attrs['class'] = tag.attrs['class']
            if tag.name == 'a' and 'href' in tag.attrs:
                preserved_attrs['href'] = tag.attrs['href']

            # Reemplazar todos los atributos con solo los preservados
            tag.attrs = preserved_attrs

        # Eliminar etiquetas vacías (sin contenido de texto)
        # Repetir hasta que no haya más cambios
        while True:
            empty_tags = [tag for tag in body.find_all(True) if not tag.get_text(strip=True)]
            if not empty_tags:
                break
            for tag in empty_tags:
                tag.decompose()

        return str(body)

    # Si no hay body, devolver el contenido limpiado
    return str(soup)


def download_html(url):
    """Descarga el HTML de una URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error descargando URL: {e}")
        sys.exit(1)


def load_extractor(domain):
    """Carga el extractor específico para un dominio"""
    # Convertir dominio a nombre de módulo válido (reemplazar . por _)
    module_name = domain.replace('.', '_')

    try:
        # Intentar importar el módulo del extractor
        extractor_module = importlib.import_module(f'extractors.{module_name}')
        return extractor_module
    except ImportError:
        return None


def create_article_template():
    """Crea una plantilla JSON con las claves típicas de artículos de noticias"""
    return {
        "title": "",
        "subtitle": "",
        "author": "",
        "date": "",
        "location": "",
        "content": "",
        "tags": [],
        "category": ""
    }


def main():
    if len(sys.argv) != 2:
        print("Uso: python get_news.py <URL>")
        sys.exit(1)

    url = sys.argv[1]

    # Extraer dominio y hash
    domain = get_domain(url)
    url_hash = get_url_hash(url)

    print(f"URL: {url}")
    print(f"Dominio: {domain}")
    print(f"Hash: {url_hash}")

    # Crear directorio para el dominio
    domain_dir = Path(f"./data/articles/{domain}")
    domain_dir.mkdir(parents=True, exist_ok=True)

    # Definir rutas de archivos
    html_path = domain_dir / f"{url_hash}.html"
    json_path = domain_dir / f"{url_hash}.json"

    # Verificar si el JSON ya existe
    if json_path.exists():
        print(f"✓ El archivo JSON ya existe: {json_path}")
        print("No se procesará nuevamente.")
        sys.exit(0)

    # Verificar si el HTML ya existe
    if html_path.exists():
        print(f"✓ HTML ya descargado: {html_path}")
        print("Usando HTML existente para extracción...")
    else:
        # Descargar HTML
        print("Descargando HTML...")
        html_content = download_html(url)

        # Limpiar HTML
        print("Limpiando HTML...")
        cleaned_html = clean_html(html_content)

        # Guardar HTML limpio
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_html)
        print(f"HTML limpio guardado en: {html_path}")

    # Intentar cargar extractor para el dominio
    print(f"\nBuscando extractor para {domain}...")
    extractor = load_extractor(domain)

    if extractor is None:
        print(f"ERROR: No existe un extractor para el dominio '{domain}'")
        print(f"Crea el archivo: extractors/{domain.replace('.', '_')}.py")
        sys.exit(1)

    print(f"✓ Extractor encontrado: extractors/{domain.replace('.', '_')}.py")

    # Usar el extractor para procesar el HTML
    print("Extrayendo datos del artículo...")
    try:
        # Leer el HTML limpio que acabamos de guardar
        with open(html_path, 'r', encoding='utf-8') as f:
            html_for_extraction = f.read()

        article_data = extractor.extract(html_for_extraction, url)

        # Agregar metadata
        article_data["_metadata"] = {
            "url": url,
            "domain": domain,
            "hash": url_hash
        }

        # Guardar JSON
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(article_data, f, indent=2, ensure_ascii=False)

        print(f"✓ JSON generado exitosamente: {json_path}")
        print("\nDatos extraídos:")
        print(f"  Título: {article_data.get('title', 'N/A')[:80]}...")
        print(f"  Autor: {article_data.get('author', 'N/A')}")
        print(f"  Fecha: {article_data.get('date', 'N/A')}")
        print(f"  Tags: {len(article_data.get('tags', []))} tags")
        print(f"  Contenido: {len(article_data.get('content', ''))} caracteres")

    except Exception as e:
        print(f"ERROR al extraer datos: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n✓ Proceso completado exitosamente!")


if __name__ == "__main__":
    main()
