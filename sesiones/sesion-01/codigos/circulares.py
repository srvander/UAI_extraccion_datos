import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


URL_INDICE = "https://www.sii.cl/normativa_legislacion/circulares/{year}/indcir{year}.htm"
PAUSA_SEGUNDOS = 1


def detectar_circulares(page, year):
    circulares = []
    enlaces = page.locator('a[href$=".pdf"]')

    for enlace in enlaces.all():
        titulo = enlace.inner_text().strip()
        numero = re.search(r"Circular\s+N[°º]\s*(\d+)", titulo, re.IGNORECASE)
        year_titulo = re.search(r"(\d{4})\s*$", titulo)
        href = enlace.get_attribute("href")

        if numero and year_titulo and year_titulo.group(1) == str(year) and href:
            circulares.append(
                {
                    "numero": numero.group(1),
                    "titulo": titulo,
                    "url": urljoin(page.url, href),
                }
            )

    return circulares


def main():
    year_actual = date.today().year
    url_indice_actual = URL_INDICE.format(year=year_actual)
    destino = Path(__file__).resolve().parent / "circulares"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url_indice_actual, wait_until="domcontentloaded")
        time.sleep(PAUSA_SEGUNDOS)

        opciones = page.locator("#sel_anyo option").evaluate_all(
            "options => options.map(option => option.value).filter(value => /^\\d{4}$/.test(value))"
        )
        if not opciones:
            raise RuntimeError("No se encontraron años en el selector de circulares del SII.")

        print("Años disponibles:", ", ".join(opciones))
        year = input("Ingrese el año de las circulares que desea descargar: ").strip()
        if year not in opciones:
            raise ValueError(f"Año no disponible. Seleccione uno de estos años: {', '.join(opciones)}")

        page.goto(URL_INDICE.format(year=year), wait_until="domcontentloaded")
        time.sleep(PAUSA_SEGUNDOS)
        circulares = detectar_circulares(page, year)

        if not circulares:
            print(f"No se encontraron circulares para {year}.")
        else:
            destino_year = destino / year
            destino_year.mkdir(parents=True, exist_ok=True)
            print(f"Se detectaron {len(circulares)} circulares para {year}:")

            for circular in circulares:
                print(f"  {circular['titulo']}")

            for circular in circulares:
                respuesta = context.request.get(circular["url"])
                time.sleep(PAUSA_SEGUNDOS)
                if not respuesta.ok:
                    print(f"Error HTTP {respuesta.status}: {circular['titulo']}")
                    continue

                archivo = destino_year / f"Circular_{year}_{circular['numero']}.pdf"
                archivo.write_bytes(respuesta.body())
                print(f"Descargada: {archivo.name}")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
