import re
import time
from pathlib import Path

from playwright.sync_api import Playwright, sync_playwright, expect


PAUSA_SEGUNDOS = 1


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://www.portaltransparencia.cl/PortalPdT/directorio-de-organismos-regulados/?org=AO006")
    time.sleep(PAUSA_SEGUNDOS)
    page.get_by_role("link", name="Actos y resoluciones con efectos sobre terceros", exact=True).click()
    time.sleep(PAUSA_SEGUNDOS)
    page.get_by_role("link", name="Sanciones").click()
    time.sleep(PAUSA_SEGUNDOS)
    page.get_by_role("link", name="Prestadores").click()
    time.sleep(PAUSA_SEGUNDOS)

    years = page.get_by_role("link", name=re.compile(r"^20\d{2}$")).all_inner_texts()
    destination = Path(__file__).resolve().parent / "sanciones"
    destination.mkdir(parents=True, exist_ok=True)

    for year in years:
        year = year.strip()
        page.get_by_role("link", name=year, exact=True).click()
        time.sleep(PAUSA_SEGUNDOS)

        with page.expect_download() as download_info:
            page.get_by_role("button", name=re.compile("Descargar CSV")).click()
        time.sleep(PAUSA_SEGUNDOS)
        download = download_info.value
        file_path = destination / f"Sanciones_Prestadores_{year}.csv"
        download.save_as(file_path)
        print(f"Descargado: {file_path}")
        page.locator('a.breadcrumb-ta:text-is("Prestadores")').click()
        time.sleep(PAUSA_SEGUNDOS)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)