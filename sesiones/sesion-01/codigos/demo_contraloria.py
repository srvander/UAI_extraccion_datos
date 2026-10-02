import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://contraloria.cl/")
    page.goto("https://www.contraloria.cl/portalweb/web/cgr/")
    page.get_by_role("button", name="BUSCAR").click()
    page.get_by_role("search", name="Escribe tu busqueda").fill("bonificaciones salud")
    page.get_by_role("button", name="Dictámenes").click()
    page.get_by_role("button", name="Dictámenes 99+").click()
    page.get_by_role("button", name="Dictámenes 99+").click()
    page.get_by_role("button", name="D373N26,29-07-2026 | ,").click()
    with page.expect_download() as download_info:
        with page.expect_popup() as page1_info:
            page.get_by_title("descargar pdf").click()
        page1 = page1_info.value
    
    # descarga como dictamen    
    download = download_info.value
    download.save_as("dictamen.pdf")
    page1.close()
    page.close()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
