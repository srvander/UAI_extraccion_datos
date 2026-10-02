"""Ejemplo acotado de scraping de la Revista Chilena de Derecho y Tecnología.

Dependencia: python -m pip install httpx
Uso: python sesiones/sesion-02/scraper_revista_derecho.py --limit 3
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx


BASE = "https://rchdt.uchile.cl"
ISSUE_URL = f"{BASE}/index.php/RCHDT/issue/current"
ARTICLE_PATH = re.compile(r"^/index\.php/RCHDT/article/view/(\d+)/?$")
PDF_PATH = re.compile(r"^/index\.php/RCHDT/article/download/(\d+)/\d+(?:/\d+)?/?$")
FIELDS = ["titulo", "autores", "doi", "url_articulo", "url_pdf"]


class PageLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.meta: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag == "meta" and values.get("name") and values.get("content"):
            self.meta.setdefault(values["name"].lower(), []).append(values["content"])


def parse_page(html: str) -> PageLinks:
    page = PageLinks()
    page.feed(html)
    return page


def permitted_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.netloc == "rchdt.uchile.cl"


def article_urls(html: str, page_url: str, limit: int) -> list[str]:
    found: list[str] = []
    for href in parse_page(html).links:
        url = urljoin(page_url, href)
        if permitted_url(url) and ARTICLE_PATH.fullmatch(urlparse(url).path):
            if url not in found:
                found.append(url)
        if len(found) >= limit:
            break
    return found


def first(meta: dict[str, list[str]], name: str) -> str:
    return meta.get(name, [""])[0]


def article_row(html: str, article_url: str) -> dict[str, str]:
    page = parse_page(html)
    match = ARTICLE_PATH.fullmatch(urlparse(article_url).path)
    if not match:
        raise ValueError("URL de artículo inesperada")
    article_id = match.group(1)
    pdf = first(page.meta, "citation_pdf_url")
    pdf_url = urljoin(article_url, pdf) if pdf else ""
    if pdf_url:
        pdf_match = PDF_PATH.fullmatch(urlparse(pdf_url).path)
        if not permitted_url(pdf_url) or not pdf_match or pdf_match.group(1) != article_id:
            raise ValueError("La URL PDF no corresponde al artículo")
    titulo = first(page.meta, "citation_title")
    if not titulo:
        raise ValueError("No se encontró citation_title; revisa el HTML antes de seguir")
    return {
        "titulo": titulo,
        "autores": "; ".join(page.meta.get("citation_author", [])),
        "doi": first(page.meta, "citation_doi"),
        "url_articulo": article_url,
        "url_pdf": pdf_url,
    }


def get_html(client: httpx.Client, url: str) -> str:
    if not permitted_url(url):
        raise ValueError("El enlace sale del dominio de la revista")
    response = client.get(url)
    response.raise_for_status()
    if not permitted_url(str(response.url)):
        raise ValueError("La redirección sale del dominio de la revista")
    if "html" not in response.headers.get("content-type", "").lower():
        raise ValueError("La respuesta no es HTML")
    return response.text


def download_one(client: httpx.Client, url: str, path: Path) -> None:
    if not permitted_url(url) or not PDF_PATH.fullmatch(urlparse(url).path):
        raise ValueError("URL PDF inesperada")
    with client.stream("GET", url) as response:
        response.raise_for_status()
        if not permitted_url(str(response.url)):
            raise ValueError("La redirección PDF sale del dominio de la revista")
        if "pdf" not in response.headers.get("content-type", "").lower():
            raise ValueError("La respuesta no es PDF")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > 15_000_000:
                raise ValueError("PDF mayor al límite didáctico de 15 MB")
            chunks.append(chunk)
    content = b"".join(chunks)
    if not content.startswith(b"%PDF"):
        raise ValueError("El archivo recibido no parece un PDF")
    path.write_bytes(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=3, help="Artículos a consultar (1 a 10)")
    parser.add_argument("--output", type=Path, default=Path("resultados_revista.csv"))
    parser.add_argument("--download-one", action="store_true", help="Descarga solo el primer PDF")
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        parser.error("--limit debe estar entre 1 y 10")

    with httpx.Client(
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": "UAI-LegalAnalytics-Clase/1.0 (ejemplo educativo)"},
    ) as client:
        issue_html = get_html(client, ISSUE_URL)
        urls = article_urls(issue_html, ISSUE_URL, args.limit)
        if not urls:
            raise RuntimeError("No se encontraron artículos; revisa la estructura del sitio")
        rows = []
        for url in urls:
            time.sleep(1.5)
            row = article_row(get_html(client, url), url)
            rows.append(row)
            print(f"Leído: {row['titulo']}")

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"CSV: {args.output.resolve()}")

        if args.download_one:
            pdf_url = rows[0]["url_pdf"]
            if not pdf_url:
                raise RuntimeError("La ficha del primer artículo no informa una URL PDF")
            time.sleep(1.5)
            pdf_path = args.output.with_suffix(".pdf")
            download_one(client, pdf_url, pdf_path)
            print(f"PDF: {pdf_path.resolve()}")


if __name__ == "__main__":
    main()
