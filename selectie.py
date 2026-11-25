"""
Deltastar SELECTIE-feed: alleen de merken die Max wil toevoegen, plat voor Stock Sync.

Bron: deltastar_add_feed.xml (alle producten, varianten genest). Uit: deltastar_add_selectie.xml,
één <product> per variant, gegroepeerd via <handle>, zoals de andere add-feeds (Holland Pharma,
Kala): Stock Sync slaat een genest <variants>-blok met één variant stil over (Kala, 24-09).

Welke merken en welke uitzonderingen staan in selectie.txt. Stock Sync "Add products" maakt
alleen aan wat nog niet in de winkel staat (identifier = sku); bestaande producten blijven
ongemoeid.

Draaien: python selectie.py   (ook in de add-feed-workflow, na add_scraper.py)
"""
from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from xml.dom import minidom

from merken import met_merktag, winkelmerk

HIER = os.path.dirname(os.path.abspath(__file__))
BRON = os.path.join(HIER, "deltastar_add_feed.xml")
UIT = os.path.join(HIER, "deltastar_add_selectie.xml")
LIJST = os.path.join(HIER, "selectie.txt")

PRODUCTVELDEN = ["handle", "title", "vendor", "brand", "product_type", "tags", "published", "btw",
                 "description", "ingredienten", "dosering", "allergenen", "waarschuwingen", "bewaren",
                 "option1_name", "option2_name"]
VARIANTVELDEN = ["sku", "barcode", "price", "compare_at_price", "available", "variant_title",
                 "option1", "option2", "weight", "weight_unit"]


def lees_lijst(pad: str = LIJST) -> tuple[list[str], set[str]]:
    """'merk: X' = alle producten van dat merk; '-SKU' = deze variant niet. # = commentaar."""
    merken, weg = [], set()
    with open(pad, encoding="utf-8") as f:
        for nr, regel in enumerate(f, 1):
            regel = regel.split("#", 1)[0].strip()
            if not regel:
                continue
            if regel.lower().startswith("merk:"):
                merken.append(winkelmerk(regel[5:]))
            elif regel.startswith("-"):
                weg.add(regel[1:].strip().upper())
            else:
                raise SystemExit(f"STOP: {pad} regel {nr} onbekend: {regel!r} (verwacht 'merk: X' of '-SKU')")
    if not merken:
        raise SystemExit(f"STOP: {pad} noemt geen enkel merk.")
    return merken, weg


def _tekst(el: ET.Element, tag: str) -> str:
    return (el.findtext(tag) or "").strip()


def plat(product: ET.Element) -> list[dict]:
    """Eén dict per variant, met de productvelden erbij en de winkelspelling van het merk."""
    merk = winkelmerk(_tekst(product, "vendor"))
    basis = {veld: _tekst(product, veld) for veld in PRODUCTVELDEN}
    basis["vendor"] = merk
    basis["brand"] = winkelmerk(_tekst(product, "brand")) or merk
    basis["tags"] = met_merktag(basis["tags"], merk)
    fotos = [_tekst(i, "src") for i in product.findall("images/image") if _tekst(i, "src")]
    rijen = []
    for v in product.findall("variants/variant"):
        rij = dict(basis)
        rij.update({veld: _tekst(v, veld) for veld in VARIANTVELDEN})
        if rij["option1"] in ("", "Default"):
            rij["option1"] = rij["variant_title"] = "Default Title"
        rij["image"] = _tekst(v, "image") or (fotos[0] if fotos else "")
        rij["image_links"] = ",".join(fotos)
        rijen.append(rij)
    return rijen


def kies(bron: ET.Element, merken: list[str], weg: set[str]) -> tuple[list[dict], Counter, list[str]]:
    rijen, per_merk, overgeslagen = [], Counter(), []
    for product in bron.iter("product"):
        for rij in plat(product):
            if rij["vendor"] not in merken:
                continue
            if rij["sku"].upper() in weg:
                overgeslagen.append(f"{rij['sku']} {rij['title']}")
                continue
            rijen.append(rij)
            per_merk[rij["vendor"]] += 1
    leeg = [m for m in merken if not per_merk[m]]
    if leeg:
        # stil wegfilteren mag niet: een tikfout in selectie.txt geeft anders een feed zonder dat merk
        raise SystemExit(f"STOP: geen enkel product voor {', '.join(leeg)} in de add-feed. "
                         f"Klopt de merknaam in selectie.txt? Gevonden merken: "
                         f"{', '.join(sorted({winkelmerk(_tekst(p, 'vendor')) for p in bron.iter('product')}))}")
    return rijen, per_merk, overgeslagen


def bouw(rijen: list[dict]) -> ET.Element:
    root = ET.Element("products")
    for rij in rijen:
        item = ET.SubElement(root, "product")
        for veld in PRODUCTVELDEN + VARIANTVELDEN + ["image", "image_links"]:
            ET.SubElement(item, veld).text = rij.get(veld, "")
    return root


def schrijf(root: ET.Element, pad: str = UIT) -> None:
    tekst = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")
    regels = tekst.split("\n")
    regels[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    with open(pad, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(regels))


def main() -> None:
    merken, weg = lees_lijst()
    rijen, per_merk, overgeslagen = kies(ET.parse(BRON).getroot(), merken, weg)
    schrijf(bouw(rijen))
    print(f"SELECTIE-feed: {len(rijen)} varianten van {len(per_merk)} merken -> {os.path.basename(UIT)}")
    for merk in merken:
        print(f"  {merk}: {per_merk[merk]}")
    if overgeslagen:
        print(f"  bewust niet (selectie.txt): {'; '.join(overgeslagen)}")
    print("https://raw.githubusercontent.com/Maximillian-creator/deltastar-feed/main/deltastar_add_selectie.xml")


if __name__ == "__main__":
    sys.exit(main())
