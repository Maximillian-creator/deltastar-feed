"""
Deltastar scraper
- Haalt alle producten op via products.json (alle pagina's)
- Scrapt de inclusief-BTW prijs van de live productpagina
- Genereert één gecombineerde XML voor Stock Sync
"""

import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re
import os

BASE_URL = "https://deltastar.nl"
LOCALE = "/nl"
OUTPUT_FILE = "docs/deltastar_feed.xml"
REQUEST_DELAY = 1.0  # seconden tussen requests (vriendelijk voor hun server)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StockSyncBot/1.0)",
    "Accept-Language": "nl-NL,nl;q=0.9",
}


def fetch_all_products():
    """Haalt alle producten op via de Shopify JSON API (alle pagina's)."""
    products = []
    page = 1

    print("📦 Producten ophalen via JSON API...")

    while True:
        url = f"{BASE_URL}/products.json?limit=250&page={page}"
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        data = response.json()
        batch = data.get("products", [])

        if not batch:
            break

        products.extend(batch)
        print(f"  Pagina {page}: {len(batch)} producten opgehaald (totaal: {len(products)})")

        if len(batch) < 250:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    print(f"✅ Totaal {len(products)} producten gevonden\n")
    return products


def fetch_live_price(handle):
    """Haalt de inclusief-BTW prijs op van de live productpagina via og:price meta-tag."""
    url = f"{BASE_URL}{LOCALE}/products/{handle}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        # Zoek de og:price:amount meta-tag
        match = re.search(
            r'<meta[^>]+property=["\']og:price:amount["\'][^>]+content=["\']([^"\']+)["\']',
            response.text
        )
        if match:
            price_str = match.group(1).replace(",", ".")
            return float(price_str)

        # Fallback: zoek ook in omgekeerde attribuut volgorde
        match = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:price:amount["\']',
            response.text
        )
        if match:
            price_str = match.group(1).replace(",", ".")
            return float(price_str)

    except Exception as e:
        print(f"    ⚠️  Prijs ophalen mislukt voor {handle}: {e}")

    return None


def build_xml(products):
    """Bouwt de XML feed op voor Stock Sync."""

    root = ET.Element("products")

    total = len(products)
    prices_fetched = 0
    prices_fallback = 0

    for i, product in enumerate(products, 1):
        handle = product.get("handle", "")
        title = product.get("title", "")
        vendor = product.get("vendor", "")
        product_type = product.get("product_type", "")
        description_html = product.get("body_html", "") or ""
        tags = ", ".join(product.get("tags", []))

        # Afbeelding (eerste afbeelding)
        images = product.get("images", [])
        image_url = images[0].get("src", "") if images else ""

        # Live prijs ophalen
        print(f"  [{i}/{total}] {title[:50]}...")
        live_price = fetch_live_price(handle)

        if live_price:
            prices_fetched += 1
        else:
            prices_fallback += 1

        # Per variant een regel in de XML
        for variant in product.get("variants", []):
            sku = variant.get("sku", "")
            barcode = variant.get("barcode", "") or ""
            available = variant.get("available", False)
            quantity = variant.get("inventory_quantity", 0)
            compare_at_price = variant.get("compare_at_price") or ""

            # Prijs: live (incl BTW) > fallback JSON prijs
            if live_price is not None:
                price = live_price
            else:
                raw_price = variant.get("price", "0")
                price = float(raw_price) * 1.21  # 21% BTW als fallback

            # Variant-specifieke afbeelding
            variant_image_id = variant.get("image_id")
            variant_image = image_url
            for img in images:
                if img.get("id") == variant_image_id:
                    variant_image = img.get("src", image_url)
                    break

            item = ET.SubElement(root, "product")

            def add(tag, value):
                el = ET.SubElement(item, tag)
                el.text = str(value) if value is not None else ""

            add("sku", sku)
            add("barcode", barcode)
            add("title", title)
            add("vendor", vendor)
            add("product_type", product_type)
            add("description", description_html)
            add("tags", tags)
            add("price", f"{price:.2f}")
            add("compare_at_price", compare_at_price)
            add("available", "true" if available else "false")
            add("quantity", quantity if available else 0)
            add("handle", handle)
            add("image", variant_image)
            add("variant_title", variant.get("title", ""))
            add("option1", variant.get("option1", "") or "")
            add("option2", variant.get("option2", "") or "")
            add("weight", variant.get("weight", ""))
            add("weight_unit", variant.get("weight_unit", ""))

        time.sleep(REQUEST_DELAY)

    print(f"\n✅ XML gebouwd: {prices_fetched} live prijzen, {prices_fallback} fallback (JSON +21%)")
    return root


def save_xml(root, filepath):
    """Slaat de XML op als mooi geformatteerd bestand."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    xml_str = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(xml_str).toprettyxml(indent="  ")

    # Verwijder de eerste XML-declaratie regel (minidom voegt die toe)
    lines = pretty.split("\n")
    if lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"💾 XML opgeslagen: {filepath}")


def main():
    print("🚀 Deltastar scraper gestart\n")
    start = time.time()

    products = fetch_all_products()
    root = build_xml(products)
    save_xml(root, OUTPUT_FILE)

    elapsed = time.time() - start
    print(f"\n⏱️  Klaar in {elapsed:.0f} seconden")


if __name__ == "__main__":
    main()
