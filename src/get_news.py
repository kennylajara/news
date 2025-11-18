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
from db import Database


def get_domain(url):
    """Extrae el dominio de una URL"""
    parsed = urlparse(url)
    domain = parsed.netloc
    # Remover www. si existe
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain


def get_url_hash(url):
    """Genera el hash SHA256 completo de una URL"""
    hash_object = hashlib.sha256(url.encode())
    return hash_object.hexdigest()


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


def download_html(url, use_cache_read=True, use_cache_save=True, verbose=False):
    """
    Descarga el HTML de una URL, con soporte para caché.

    Args:
        url: URL to download
        use_cache_read: If True, try to read from cache first
        use_cache_save: If True, save to cache after download
        verbose: If True, print cache operations

    Returns:
        Dictionary with:
            - 'content': HTML content as string
            - 'final_url': Final URL after following redirects (may be same as original)
    """
    from db.cache import CacheDatabase

    cache_db = CacheDatabase()

    # Try cache first
    if use_cache_read:
        cached = cache_db.get_cached_content(url)
        if cached:
            # Check if cached response was successful
            if cached['status_code'] >= 400:
                error_msg = f"Cached response has error status: {cached['status_code']}"
                if verbose:
                    print(f"✗ {error_msg}")
                print(error_msg)
                sys.exit(1)

            if verbose:
                print(f"✓ Loaded from cache (saved {cached['created_at'].strftime('%Y-%m-%d %H:%M')}, status: {cached['status_code']})")

            # Return final URL (which may be different if was redirected)
            return {
                'content': cached['content'],
                'final_url': cached['url']  # This is already the final URL from cache
            }

    # Download from URL
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html_content = response.text

        # Note: requests follows redirects by default (301/302/303/307/308)
        # response.url contains the final URL after redirects
        # response.history contains intermediate redirect responses
        final_url = response.url
        was_redirected = final_url != url

        # Save to cache
        if use_cache_save:
            if was_redirected:
                # Save TWO cache entries:
                # 1. Original URL -> redirect entry (status 30x, content = final URL)
                redirect_status = response.history[0].status_code if response.history else 301
                cache_db.save_to_cache(url, final_url, status_code=redirect_status)

                # 2. Final URL -> actual content (status 200, content = HTML)
                cache_db.save_to_cache(final_url, html_content, status_code=response.status_code)

                if verbose:
                    print(f"✓ Saved to cache: redirect {url} -> {final_url}")
            else:
                # No redirect, save normally
                cache_db.save_to_cache(url, html_content, status_code=response.status_code)
                if verbose:
                    print("✓ Saved to cache")

        return {
            'content': html_content,
            'final_url': final_url
        }
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

    # Check cache for potential redirect BEFORE checking if article exists
    # This ensures we check the final URL, not the redirect URL
    from db.cache import CacheDatabase
    cache_db = CacheDatabase()
    cached = cache_db.get_cached_content(url)

    # If cached and was redirected, use the final URL for existence check
    final_url = url
    final_hash = url_hash
    if cached and cached.get('was_redirected'):
        final_url = cached['url']
        final_hash = get_url_hash(final_url)
        print(f"Redirect detected: {url} → {final_url}")

    # Verificar si el artículo ya existe en la base de datos (using final URL)
    db = Database()
    session = db.get_session()
    try:
        if db.article_exists(session, url=final_url, hash=final_hash):
            print(f"✓ El artículo ya existe en la base de datos")
            print("No se procesará nuevamente.")
            session.close()
            sys.exit(0)
    finally:
        session.close()

    # Descargar HTML
    print("Descargando HTML...")
    download_result = download_html(url)
    html_content = download_result['content']
    final_url = download_result['final_url']

    # If URL was redirected, update our variables to use the final URL
    if final_url != url:
        print(f"Siguiendo redirección: {url} → {final_url}")
        url = final_url
        domain = get_domain(final_url)
        url_hash = get_url_hash(final_url)

    # Limpiar HTML
    print("Limpiando HTML...")
    cleaned_html = clean_html(html_content)

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
        article_data = extractor.extract(cleaned_html, url)

        # Agregar metadata (using final URL after redirects)
        article_data["_metadata"] = {
            "url": url,  # This is now the final URL
            "domain": domain,
            "hash": url_hash
        }

        # Guardar en base de datos
        print("Guardando en base de datos...")
        db = Database()
        session = db.get_session()
        try:
            article = db.save_article(session, article_data, domain)
            session.commit()
            print(f"✓ Artículo guardado en base de datos (ID: {article.id})")
        except Exception as db_error:
            session.rollback()
            print(f"⚠ Error guardando en BD: {db_error}")
            raise
        finally:
            session.close()

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
