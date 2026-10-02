import asyncio
import hashlib
import mimetypes
import re
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

from pydoll.browser.chromium import Chrome


PAGE_URL = "https://harem-battle.club/wiki/Harem-Heroes/HH:Fluttering-Andra"
OUTPUT_DIR = Path(__file__).resolve().parent / "imagenes_fluttering_andra"


def download_image(url: str, index: int) -> Path:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; image-downloader/1.0)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get_content_type()
        if not content_type.startswith("image/"):
            raise ValueError(f"El servidor respondió con {content_type}, no con una imagen")

        parsed_path = unquote(urlparse(url).path)
        filename = Path(parsed_path).name
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename).strip(" .")
        extension = Path(filename).suffix or mimetypes.guess_extension(content_type) or ".img"
        stem = Path(filename).stem if Path(filename).suffix else f"image_{index:03d}"
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
        destination = OUTPUT_DIR / f"{stem}_{url_hash}{extension}"
        destination.write_bytes(response.read())
        return destination


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image_urls: set[str] = set()

    async with Chrome() as browser:
        page = await browser.start()
        print(f"Abriendo {PAGE_URL}")
        await page.go_to(PAGE_URL)

        source = await page.page_source()
        challenge_markers = (
            "Just a moment",
            "Un momento",
            "cdn-cgi/challenge-platform",
            "challenge-error-text",
            "cf-chl-",
        )
        if any(marker in source for marker in challenge_markers):
            print("Cloudflare mostró una página de comprobación; no se intentará eludirla.")
            return

        image_elements = await page.query(
            "img", timeout=10, find_all=True, raise_exc=False
        )
        for image in image_elements or []:
            for attribute in ("src", "data-src", "data-original", "data-lazy-src"):
                value = image.get_attribute(attribute)
                if value:
                    image_url = urljoin(PAGE_URL, value.strip())
                    if urlparse(image_url).scheme in {"http", "https"}:
                        image_urls.add(image_url)

    print(f"Imágenes encontradas: {len(image_urls)}")
    if not image_urls:
        print("No se encontraron imágenes en el DOM de la página.")
        return

    for index, image_url in enumerate(sorted(image_urls), start=1):
        try:
            path = await asyncio.to_thread(download_image, image_url, index)
            print(f"Descargada: {path.name}")
        except Exception as error:
            print(f"No se pudo descargar {image_url}: {error}")


if __name__ == "__main__":
    asyncio.run(main())