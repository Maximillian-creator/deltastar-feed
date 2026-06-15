"""
Deltastar scraper
- Haalt alle producten op via products.json (alle pagina's)
- Berekent prijs incl. 21% BTW
- Genereert één gecombineerde XML voor Stock Sync
- Slaat XML op in de repository (wordt automatisch gepusht door GitHub Actions)
"""

import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import os

BASE_URL = "https://deltastar.nl"
OUTPUT_FILE = "deltastar_feed.xml"
BTW = 1.21
REQUEST_DELAY = 0.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StockSyncBot/1.0)",
    "Accept-Language": "nl-NL,nl;q=0.9",
}


def fetch_all_products():
    products = []
    page = 1
    print("📦 Producten ophalen...")

    while True:
        url = f"{BASE_URL}/products.json?limit=250&page={page}"
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        batch = response.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        print(f"  Pagina {page}: {len(batch)} producten (totaal: {len(products)})")
        if len(batch) < 250:
            break
        page += 1
        time.sleep(REQUEST_DELAY)

    print(f"✅ {len(products)} producten gevonden\n")
    return products


def build_xml(products):
    root = ET.Element("products")

    for product in products:
        handle = product.get("handle", "")
        title = product.get("title", "")
        vendor = product.get("vendor", "")
        product_type = product.get("product_type", "")
        description_html = product.get("body_html", "") or ""
        tags = ", ".join(product.get("tags", []))
        images = product.get("images", [])
        image_url = images[0].get("src", "") if images else ""

        for variant in product.get("variants", []):
            sku = variant.get("sku", "")
            barcode = variant.get("barcode", "") or ""
            available = variant.get("available", False)
            quantity = variant.get("inventory_quantity", 0)
            raw_price = float(variant.get("price", "0"))
            price = round(raw_price * BTW, 2)
            raw_compare = variant.get("compare_at_price")
            compare_at_price = round(float(raw_compare) * BTW, 2) if raw_compare else ""

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
            add("compare_at_price", f"{compare_at_price:.2f}" if compare_at_price else "")
            add("available", "true" if available else "false")
            add("quantity", quantity if available else 0)
            add("handle", handle)
            add("image", variant_image)
            add("variant_title", variant.get("title", ""))
            add("option1", variant.get("option1", "") or "")
            add("option2", variant.get("option2", "") or "")
            add("weight", variant.get("weight", ""))
            add("weight_unit", variant.get("weight_unit", ""))

    return root


def save_xml(root, filepath):
    xml_str = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(xml_str).toprettyxml(indent="  ")
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
    print(f"\n📋 Feed URL voor Stock Sync:")
    print(f"https://raw.githubusercontent.com/Maximillian-creator/deltastar-feed/main/deltastar_feed.xml")


if __name__ == "__main__":
    main()
