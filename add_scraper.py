"""
Deltastar ADD-feed scraper
==========================
Tweelingbroer van scraper.py, maar met een ander doel:

- scraper.py        → UPDATE-feed: prijs + voorraad van BESTAANDE producten
- add_scraper.py    → ADD-feed:    ALLE beschikbare productinfo om met
                      Stock Sync NIEUWE producten aan te maken

De storefront-JSON (/products.json) is beperkt: geen barcode, geen losse
ingrediënten/dosering/allergenen, maar wél meerdere afbeeldingen en opties.
Daarom combineren we per product drie bronnen:

  1. /products.json            → titel, body_html, vendor, type, tags,
                                  opties (met namen), álle afbeeldingen, varianten
  2. JSON-LD op de live pagina → barcode (gtin13) per variant + brand
  3. Accordeons op de live pagina → Ingrediënten (tabel met %RI), Dosering,
                                     Allergenen, Waarschuwingen, Bewaren

Output: deltastar_add_feed.xml — productgericht (geneste <images> en <variants>)
zodat Stock Sync in de "Add products"-modus alles kan mappen.

BTW-logica is identiek aan de update-feed (vat-low/vat-liquid = 9%, anders 21%).

Lokaal testen achter een SSL-onderscheppende proxy? Zet INSECURE_SSL=1.
Eén product testen? TEST_HANDLE=<handle>.
"""

import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
from html import unescape
import json
import time
import re
import os

BASE_URL = "https://deltastar.nl"
LOCALE = "/nl"
OUTPUT_FILE = "deltastar_add_feed.xml"
BTW_HOOG = 1.21
BTW_LAAG = 1.09
REQUEST_DELAY = 0.75

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StockSyncBot/1.0)",
    "Accept-Language": "nl-NL,nl;q=0.9",
}

# Lokaal achter een bedrijfsproxy kan de SSL-keten falen. In GitHub Actions
# nooit nodig; daar staat dit uit en verifiëren we netjes.
VERIFY_SSL = os.environ.get("INSECURE_SSL") != "1"
if not VERIFY_SSL:
    import urllib3
    urllib3.disable_warnings()

# Accordeon-secties die we van de live pagina plukken (kop -> xml-tag)
SECTIES = {
    "Dosering": "dosering",
    "Allergenen": "allergenen",
    "Waarschuwingen": "waarschuwingen",
    "Bewaren": "bewaren",
}


def fetch_with_retry(url, max_retries=3):
    """Fetch een URL met retry-logica bij fouten."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15, verify=VERIFY_SSL)
            response.raise_for_status()
            return response
        except Exception as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 30  # 30s, 60s, 90s
                print(f"    ⚠️  Fout ({e}), opnieuw proberen in {wait}s...")
                time.sleep(wait)
            else:
                print(f"    ❌ Mislukt na {max_retries} pogingen: {e}")
                raise


def fetch_all_products():
    """Alle producten via de JSON-API (alle pagina's)."""
    products = []
    page = 1
    print("📦 Producten ophalen via JSON API...")

    while True:
        url = f"{BASE_URL}/products.json?limit=250&page={page}"
        response = fetch_with_retry(url)
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


def clean_text(html_fragment):
    """Strip HTML-tags en normaliseer witruimte tot leesbare platte tekst."""
    if not html_fragment:
        return ""
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_accordion(html, heading):
    """
    Haal de paneeltekst op die achter een accordeon-kop (<h2>) hoort.
    Pakt het eerste 'custom-accordion__panel' na de kop tot </details>.
    """
    m = re.search(
        rf'<h2[^>]*accordion__title[^>]*>\s*{re.escape(heading)}\s*</h2>',
        html, re.IGNORECASE,
    )
    if not m:
        return None
    rest = html[m.end():]
    panel = re.search(r'custom-accordion__panel[^"]*"\s*[^>]*>(.*?)</details>',
                      rest, re.DOTALL)
    if not panel:
        return None
    return clean_text(panel.group(1)) or None


def _num_value(match):
    """Haal het getal uit data-value; strip een nutteloze '.0' (150.0 -> 150)."""
    v = match.group(1)
    return v[:-2] if v.endswith(".0") else v


def extract_ingredienten(html):
    """
    Haal de ingrediëntentabel (met dosering + %RI) op. Deze kop bevat een svg + 'ë',
    dus we pakken de tabel direct via zijn class.

    Let op: de tabel gebruikt custom-elementen waarvan de échte waarde in
    data-value staat (de tekstinhoud is leeg):
      - <custom-italicized-text data-value="Vitamin C ...">  -> ingrediëntnaam
      - <custom-formatted-number data-value="150.0">         -> hoeveelheid / %RI
    Zonder die af te vangen verdwijnen alle getallen (was een bug: "mg % RI: % %").
    De mobiele duplicaat-cel (<p class="show-in-mobile">) verwijderen we om
    dubbele %RI-waarden te voorkomen.
    """
    m = re.search(r'<table[^>]*ingredients-table[^>]*>.*?</table>', html, re.DOTALL)
    if not m:
        return None
    table = m.group(0)
    table = re.sub(r'<p class="show-in-mobile".*?</p>', " ", table, flags=re.DOTALL)
    table = re.sub(
        r'<custom-formatted-number data-value="([^"]*)"></custom-formatted-number>',
        _num_value, table,
    )
    table = re.sub(
        r'<custom-italicized-text data-value="([^"]*)"></custom-italicized-text>',
        r"\1", table,
    )
    return clean_text(table) or None


def fetch_product_extras(handle):
    """
    Haalt van de live productpagina alles op wat in /products.json ontbreekt:
    - barcode (gtin13) per variant-id  (uit JSON-LD offers)
    - brand                            (uit JSON-LD)
    - ingrediënten / dosering / allergenen / waarschuwingen / bewaren
    """
    url = f"{BASE_URL}{LOCALE}/products/{handle}"
    extras = {
        "found": True,           # False = productpagina bestaat niet (404) -> overslaan
        "brand": None,
        "gtin_by_variant": {},   # {variant_id(str): gtin13}
        "ingredienten": None,
        "dosering": None,
        "allergenen": None,
        "waarschuwingen": None,
        "bewaren": None,
    }

    # Live pagina ophalen. Een 404 betekent een "spook"-product: het staat wel in
    # products.json maar wordt niet verkocht op de storefront -> niet herhalen,
    # markeren als niet-gevonden zodat build_xml het overslaat. Transiënte fouten
    # (netwerk/5xx) één keer herproberen; daarna meenemen zonder extra's.
    html = None
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15, verify=VERIFY_SSL)
            if resp.status_code == 404:
                extras["found"] = False
                return extras
            resp.raise_for_status()
            html = resp.text
            break
        except Exception as e:
            if getattr(getattr(e, "response", None), "status_code", None) == 404:
                extras["found"] = False
                return extras
            if attempt == 0:
                print(f"    ⚠️  Live pagina fout bij {handle} ({e}), 1x opnieuw...")
                time.sleep(30)
            else:
                print(f"    ⚠️  Live pagina blijft falen bij {handle}: {e}")
                return extras  # found blijft True: niet onterecht droppen bij netwerkfout

    # --- JSON-LD: brand + barcode per variant ---
    for block in re.findall(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL,
    ):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("@type") != "Product":
            continue
        brand = data.get("brand")
        if isinstance(brand, dict):
            extras["brand"] = brand.get("name")
        elif isinstance(brand, str):
            extras["brand"] = brand
        for offer in data.get("offers", []) or []:
            gtin = offer.get("gtin13") or offer.get("gtin") or offer.get("gtin12")
            vid = re.search(r"variant=(\d+)", offer.get("url", "") or "")
            if gtin and vid:
                extras["gtin_by_variant"][vid.group(1)] = gtin

    # --- Accordeon-secties ---
    extras["ingredienten"] = extract_ingredienten(html)
    for kop, tag in SECTIES.items():
        extras[tag] = extract_accordion(html, kop)

    return extras


def build_description_html(body_html, extras):
    """
    Combineert body_html + secties tot één rijke HTML-beschrijving.
    body_html wordt hier al ontdaan van dubbele escaping (unescape) zodat
    ElementTree het nog exact één keer escapet — Stock Sync unescapet één keer
    terug en krijgt geldige HTML (geen '&amp;amp;').
    """
    parts = []
    if body_html:
        parts.append(unescape(body_html))
    labels = [
        ("ingredienten", "Ingrediënten"),
        ("dosering", "Dosering"),
        ("allergenen", "Allergenen"),
        ("waarschuwingen", "Waarschuwingen"),
        ("bewaren", "Bewaren"),
    ]
    for key, label in labels:
        if extras.get(key):
            parts.append(f"<p><strong>{label}:</strong> {extras[key]}</p>")
    return "\n".join(parts)


def add_child(parent, tag, value):
    """Voegt een kind-element toe; None -> lege string."""
    el = ET.SubElement(parent, tag)
    el.text = "" if value is None else str(value)
    return el


def build_xml(products):
    root = ET.Element("products")
    total = len(products)
    skipped = []

    for i, product in enumerate(products, 1):
        handle = product.get("handle", "")
        title = product.get("title", "")
        vendor = product.get("vendor", "")
        product_type = product.get("product_type", "") or ""
        body_html = product.get("body_html", "") or ""
        tags = product.get("tags", [])
        tags_str = ", ".join(tags)
        options = product.get("options", [])
        images = product.get("images", [])

        # BTW bepalen (identiek aan update-feed)
        is_low_vat = any(t in tags for t in ["vat-low", "vat-liquid"])
        btw = BTW_LAAG if is_low_vat else BTW_HOOG
        btw_label = "9%" if btw == BTW_LAAG else "21%"

        print(f"  [{i}/{total}] {title[:55]:<55} (BTW {btw_label})")
        extras = fetch_product_extras(handle)

        # Spook-product: staat in products.json maar de live verkooppagina geeft
        # 404 -> wordt niet verkocht op de storefront. Overslaan.
        if not extras.get("found", True):
            print(f"        ⏭️  Overgeslagen (geen verkooppagina / 404)")
            skipped.append(title)
            time.sleep(REQUEST_DELAY)
            continue

        full_description = build_description_html(body_html, extras)

        # Optienamen (Title/Smaak/Inhoud...) — products.json levert deze wél
        opt_names = {1: "", 2: "", 3: ""}
        for opt in options:
            pos = opt.get("position")
            if pos in opt_names:
                opt_names[pos] = opt.get("name", "")

        item = ET.SubElement(root, "product")
        add_child(item, "handle", handle)
        add_child(item, "title", title)
        add_child(item, "vendor", vendor)
        add_child(item, "brand", extras.get("brand") or vendor)
        add_child(item, "product_type", product_type)
        add_child(item, "tags", tags_str)
        add_child(item, "published", "true")
        add_child(item, "btw", btw_label)
        add_child(item, "body_html", unescape(body_html))
        add_child(item, "description", full_description)
        add_child(item, "ingredienten", extras.get("ingredienten"))
        add_child(item, "dosering", extras.get("dosering"))
        add_child(item, "allergenen", extras.get("allergenen"))
        add_child(item, "waarschuwingen", extras.get("waarschuwingen"))
        add_child(item, "bewaren", extras.get("bewaren"))
        add_child(item, "option1_name", opt_names[1])
        add_child(item, "option2_name", opt_names[2])
        add_child(item, "option3_name", opt_names[3])

        # --- Alle afbeeldingen ---
        # Twee vormen: genest (overzicht) én één komma-gescheiden veld.
        # Stock Sync pakt uit een geneste node maar één <src>; uit een komma-lijst
        # importeert het álle afbeeldingen. Map in Stock Sync daarom 'image_links'.
        images_el = ET.SubElement(item, "images")
        for img in images:
            img_el = ET.SubElement(images_el, "image")
            add_child(img_el, "position", img.get("position", ""))
            add_child(img_el, "src", img.get("src", ""))
        image_srcs = [img.get("src", "") for img in images if img.get("src")]
        add_child(item, "image_links", ",".join(image_srcs))
        first_image = images[0].get("src", "") if images else ""

        # --- Varianten ---
        variants_el = ET.SubElement(item, "variants")
        for variant in product.get("variants", []):
            vid = str(variant.get("id", ""))
            sku = variant.get("sku", "") or ""
            barcode = extras["gtin_by_variant"].get(vid, "")

            raw_price = float(variant.get("price", "0") or 0)
            price = round(raw_price * btw, 2)
            raw_compare = variant.get("compare_at_price")
            compare_at_price = round(float(raw_compare) * btw, 2) if raw_compare else ""

            available = variant.get("available", False)
            grams = variant.get("grams", "") or ""

            # Variant-afbeelding: featured_image, anders eerste productafbeelding
            v_img = first_image
            feat = variant.get("featured_image")
            if isinstance(feat, dict) and feat.get("src"):
                v_img = feat["src"]

            v_el = ET.SubElement(variants_el, "variant")
            add_child(v_el, "sku", sku)
            add_child(v_el, "barcode", barcode)
            add_child(v_el, "price", f"{price:.2f}")
            add_child(v_el, "compare_at_price",
                      f"{compare_at_price:.2f}" if compare_at_price else "")
            add_child(v_el, "available", "true" if available else "false")
            add_child(v_el, "variant_title", variant.get("title", "") or "")
            add_child(v_el, "option1", variant.get("option1", "") or "")
            add_child(v_el, "option2", variant.get("option2", "") or "")
            add_child(v_el, "option3", variant.get("option3", "") or "")
            add_child(v_el, "weight", grams)
            add_child(v_el, "weight_unit", "g")
            add_child(v_el, "image", v_img)

        time.sleep(REQUEST_DELAY)

    if skipped:
        print(f"\n⏭️  {len(skipped)} spook-product(en) overgeslagen (404 / niet verkocht):")
        for t in skipped:
            print(f"     - {t}")

    return root


def save_xml(root, filepath):
    xml_str = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(xml_str).toprettyxml(indent="  ")
    lines = pretty.split("\n")
    if lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n💾 XML opgeslagen: {filepath}")


def main():
    print("🚀 Deltastar ADD-feed scraper gestart\n")
    start = time.time()

    products = fetch_all_products()

    # Eén product testen via TEST_HANDLE=<handle>
    test_handle = os.environ.get("TEST_HANDLE")
    if test_handle:
        products = [p for p in products if p.get("handle") == test_handle]
        print(f"🧪 TEST-modus: alleen '{test_handle}' ({len(products)} gevonden)\n")

    root = build_xml(products)
    save_xml(root, OUTPUT_FILE)

    elapsed = time.time() - start
    print(f"⏱️  Klaar in {elapsed:.0f} seconden ({len(products)} producten)")
    print("\n📋 Feed-URL voor Stock Sync (Add products):")
    print("https://raw.githubusercontent.com/Maximillian-creator/deltastar-feed/main/deltastar_add_feed.xml")


if __name__ == "__main__":
    main()
