"""Descarga los PDF de los artículos enlazados en la portada de la RCHDT.

Instalación: python -m pip install httpx
Uso: python sesiones/sesion-02/descargar_articulos.py
"""

from __future__ import annotations

import argparse
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx


BASE_URL = "https://rchdt.uchile.cl"
PORTADA_URL = f"{BASE_URL}/index.php/RCHDT"
ARTICULO_RE = re.compile(r"^/index\.php/RCHDT/article/view/(\d+)/?$")
GALERA_RE = re.compile(r"^/index\.php/RCHDT/article/view/(\d+)/(\d+)/?$")
PDF_RE = re.compile(r"^/index\.php/RCHDT/article/download/(\d+)/(\d+)/?$")


class Enlaces(HTMLParser):
    """Recoge los enlaces y sus atributos class de una página HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        href = values.get("href")
        if href:
            self.links.append((href, values.get("class") or ""))


def enlaces(html: str) -> Enlaces:
    parser = Enlaces()
    parser.feed(html)
    return parser


def es_url_revista(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.netloc == "rchdt.uchile.cl"


def obtener_html(client: httpx.Client, url: str) -> str:
    if not es_url_revista(url):
        raise ValueError(f"URL fuera del dominio permitido: {url}")
    response = client.get(url)
    response.raise_for_status()
    if not es_url_revista(str(response.url)):
        raise ValueError("La redirección salió del dominio de la revista")
    if "html" not in response.headers.get("content-type", "").lower():
        raise ValueError(f"La respuesta no es HTML: {url}")
    return response.text


def obtener_articulos(html: str, pagina_url: str) -> list[str]:
    """Encuentra una sola URL de ficha por artículo en la portada."""
    encontrados: list[str] = []
    for href, _ in enlaces(html).links:
        url = urljoin(pagina_url, href)
        if es_url_revista(url) and ARTICULO_RE.fullmatch(urlparse(url).path):
            if url not in encontrados:
                encontrados.append(url)
    return encontrados


def nombre_archivo(texto: str) -> str:
    texto = re.sub(r"[^\w.-]+", "_", texto.strip(), flags=re.UNICODE).strip("_.")
    return (texto[:100] or "articulo") + ".pdf"


def obtener_datos_articulo(html: str, articulo_url: str) -> tuple[str, str]:
    """Lee el título y la galera desde <a class="obj_galley_link pdf">.

    Según articulo_derecho.html, ese enlace tiene una URL /article/view/{id}/{galera};
    para descargar se usa el endpoint OJS /article/download/{id}/{galera}.
    """
    articulo_match = ARTICULO_RE.fullmatch(urlparse(articulo_url).path)
    if not articulo_match:
        raise ValueError(f"URL de artículo inesperada: {articulo_url}")
    articulo_id = articulo_match.group(1)

    titulo = ""
    pdf_url = ""
    for href, clases in enlaces(html).links:
        url = urljoin(articulo_url, href)
        path = urlparse(url).path
        galera_match = GALERA_RE.fullmatch(path)
        if "obj_galley_link" in clases.split() and "pdf" in clases.split():
            if es_url_revista(url) and galera_match and galera_match.group(1) == articulo_id:
                pdf_url = url.replace("/article/view/", "/article/download/", 1)
        # El título se obtiene del meta citation_title, leído abajo del HTML.

    meta_re = re.compile(
        r'<meta\b(?=[^>]*\bname=["\']citation_title["\'])(?=[^>]*\bcontent=["\']([^"\']+)["\'])[^>]*>',
        re.IGNORECASE,
    )
    meta_match = meta_re.search(html)
    if meta_match:
        titulo = meta_match.group(1)
    if not titulo:
        titulo = f"articulo_{articulo_id}"

    pdf_match = PDF_RE.fullmatch(urlparse(pdf_url).path) if pdf_url else None
    if not pdf_match or pdf_match.group(1) != articulo_id:
        raise ValueError(f"No se encontró un enlace PDF válido para el artículo {articulo_id}")
    return titulo, pdf_url


def descargar_pdf(client: httpx.Client, url: str, destino: Path) -> None:
    if not es_url_revista(url) or not PDF_RE.fullmatch(urlparse(url).path):
        raise ValueError(f"URL de descarga PDF inesperada: {url}")
    with client.stream("GET", url) as response:
        response.raise_for_status()
        if not es_url_revista(str(response.url)):
            raise ValueError("La redirección del PDF salió del dominio de la revista")
        tipo = response.headers.get("content-type", "").lower()
        if "pdf" not in tipo:
            raise ValueError(f"El servidor no devolvió un PDF ({tipo or 'tipo desconocido'})")
        temporal = destino.with_suffix(destino.suffix + ".part")
        try:
            with temporal.open("wb") as archivo:
                inicio = b""
                for bloque in response.iter_bytes():
                    if not inicio:
                        inicio = bloque[:4]
                    archivo.write(bloque)
            if inicio != b"%PDF":
                raise ValueError("El contenido descargado no tiene firma PDF")
            temporal.replace(destino)
        finally:
            temporal.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", type=Path, default=Path("articulos_pdf"), help="Carpeta de destino")
    parser.add_argument("--pausa", type=float, default=1.0, help="Segundos entre solicitudes (predeterminado: 1)")
    args = parser.parse_args()
    if args.pausa < 0:
        parser.error("--pausa no puede ser negativa")

    args.salida.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "UAI-RCHDT-PDF-Downloader/1.0 (uso academico)"},
    ) as client:
        articulos = obtener_articulos(obtener_html(client, PORTADA_URL), PORTADA_URL)
        if not articulos:
            raise RuntimeError("No se encontraron fichas de artículos en la portada")
        print(f"Artículos encontrados: {len(articulos)}")

        exitos = 0
        for indice, url in enumerate(articulos):
            if indice:
                time.sleep(args.pausa)
            try:
                titulo, pdf_url = obtener_datos_articulo(obtener_html(client, url), url)
                destino = args.salida / nombre_archivo(titulo)
                if destino.exists():
                    print(f"Ya existe, se omite: {destino.name}")
                    exitos += 1
                    continue
                descargar_pdf(client, pdf_url, destino)
                print(f"Descargado: {destino.name}")
                exitos += 1
            except (httpx.HTTPError, OSError, ValueError) as error:
                print(f"Error en {url}: {error}")

        print(f"Proceso terminado: {exitos}/{len(articulos)} artículos disponibles en {args.salida.resolve()}")


if __name__ == "__main__":
    main()
