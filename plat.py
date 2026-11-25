"""
Deltastar ADD-feed plat maken (25-11-2026, Max: "alle vier, en push maar").

add_scraper.py bouwt per product een genest <variants>-blok. Stock Sync slaat zo'n blok met
één variant stil over (Kala, 24-09), en al onze andere add-feeds zijn plat. Daarom schrijft de
add-feed nu één <product> per variant, gegroepeerd via <handle>, met:
  - de merknaam zoals de winkel hem schrijft + die naam als tag (merken.py);
  - zonder wat in niet_toevoegen.txt staat: losse SKU's (al in de winkel zonder SKU, THT-partijen)
    en hele merken (Vitalized: komt uit de eigen Vitalized-feed, andere SKU, zelfde barcode).

add_scraper.py roept maak_plat() aan vóór het wegschrijven. Los draaien (`python plat.py`) zet
de huidige deltastar_add_feed.xml om zonder opnieuw te scrapen.
"""
from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom

from merken import met_merktag, winkelmerk

HIER = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HIER, "deltastar_add_feed.xml")
NIET = os.path.join(HIER, "niet_toevoegen.txt")

PRODUCTVELDEN = ["handle", "title", "vendor", "brand", "product_type", "tags", "published", "btw",
                 "body_html", "description", "ingredienten", "dosering", "allergenen", "waarschuwingen",
                 "bewaren", "option1_name", "option2_name", "option3_name"]
VARIANTVELDEN = ["sku", "barcode", "price", "compare_at_price", "available", "variant_title",
                 "option1", "option2", "option3", "weight", "weight_unit"]
VELDEN = PRODUCTVELDEN + VARIANTVELDEN + ["image", "image_links"]


def lees_niet(pad: str = NIET) -> dict[str, str]:
    """Eén SKU per regel, of 'merk: X' voor een heel merk; '#' erachter = de reden.
    Geeft {SKU: reden} en {'merk:<winkelmerk>': reden}."""
    niet = {}
    with open(pad, encoding="utf-8") as f:
        for nr, regel in enumerate(f, 1):
            code, _, reden = regel.partition("#")
            code = code.strip()
            if not code:
                continue
            if code.lower().startswith("merk:"):
                niet["merk:" + winkelmerk(code[5:])] = reden.strip()
                continue
            if " " in code:
                raise SystemExit(f"STOP: {pad} regel {nr}: één SKU per regel, gevonden {code!r}")
            niet[code.upper()] = reden.strip()
    return niet


def _prijs(tekst: str) -> float:
    try:
        return float(tekst)
    except ValueError:
        return 0.0


def _tekst(el: ET.Element, tag: str) -> str:
    return (el.findtext(tag) or "").strip()


def rijen(product: ET.Element) -> list[dict]:
    """Eén dict per variant, met de productvelden erbij en de winkelspelling van het merk."""
    merk = winkelmerk(_tekst(product, "vendor"))
    basis = {veld: _tekst(product, veld) for veld in PRODUCTVELDEN}
    basis["vendor"] = merk
    basis["brand"] = winkelmerk(_tekst(product, "brand")) or merk
    basis["tags"] = met_merktag(basis["tags"], merk)
    fotos = [_tekst(i, "src") for i in product.findall("images/image") if _tekst(i, "src")]
    basis["image_links"] = _tekst(product, "image_links") or ",".join(fotos)
    uit = []
    for v in product.findall("variants/variant"):
        rij = dict(basis)
        rij.update({veld: _tekst(v, veld) for veld in VARIANTVELDEN})
        if rij["option1"] in ("", "Default", "Default Title"):
            rij["option1"] = rij["variant_title"] = "Default Title"
        rij["image"] = _tekst(v, "image") or (fotos[0] if fotos else "")
        uit.append(rij)
    return uit


def maak_plat(genest: ET.Element, niet: dict[str, str]) -> tuple[ET.Element, list[str]]:
    """Genest -> plat. Geeft (root, overgeslagen) zodat de log laat zien wat er bewust uit is."""
    if genest.find("product/variants") is None and genest.find("product/sku") is not None:
        raise SystemExit("STOP: de feed is al plat; niets omgezet.")
    root, overgeslagen = ET.Element("products"), []
    for product in genest.iter("product"):
        for rij in rijen(product):
            sleutel = next((k for k in (rij["sku"].upper(), "merk:" + rij["vendor"]) if k in niet), None)
            if sleutel:
                overgeslagen.append(f"{rij['sku']} ({niet[sleutel] or 'niet_toevoegen.txt'})")
                continue
            if not _prijs(rij["price"]):
                # 25-11: CuraZyme Ultra stond op 0.00 (geen foto, niet leverbaar); zou voor €0 verschijnen
                overgeslagen.append(f"{rij['sku']} (prijs {rij['price'] or 'leeg'})")
                continue
            item = ET.SubElement(root, "product")
            for veld in VELDEN:
                ET.SubElement(item, veld).text = rij.get(veld, "")
    return root, overgeslagen


def schrijf(root: ET.Element, pad: str = FEED) -> None:
    tekst = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")
    regels = tekst.split("\n")
    regels[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    with open(pad, "w", encoding="utf-8") as f:
        f.write("\n".join(regels))


def main() -> None:
    root, overgeslagen = maak_plat(ET.parse(FEED).getroot(), lees_niet())
    schrijf(root)
    print(f"ADD-feed plat: {len(root.findall('product'))} regels -> {os.path.basename(FEED)}")
    if overgeslagen:
        print(f"bewust niet ({len(overgeslagen)}): " + "; ".join(overgeslagen))


if __name__ == "__main__":
    sys.exit(main())
