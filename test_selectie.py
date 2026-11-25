"""Pint de selectie-feed vast (25-11-2026). Draaien: python -m pytest -q test_selectie.py"""
import xml.etree.ElementTree as ET

import pytest

import merken
import selectie

BRON = """<products>
 <product><handle>source-of-life</handle><title>Source of Life - 90 tablets</title>
  <vendor>NaturesPlus</vendor><brand>NaturesPlus</brand><tags>vat-high</tags><published>true</published>
  <images><image><position>1</position><src>https://x/a.jpg</src></image>
          <image><position>2</position><src>https://x/b.jpg</src></image></images>
  <variants>
   <variant><sku>NP-1</sku><barcode>111</barcode><price>10.00</price><available>true</available>
            <variant_title>Default</variant_title><option1>Default</option1><image></image></variant>
  </variants></product>
 <product><handle>ionic-zinc</handle><title>Ionic Zinc</title><vendor>Trace Minerals</vendor>
  <brand>Trace Minerals</brand><tags>vat-liquid</tags><published>true</published>
  <images><image><position>1</position><src>https://x/z.jpg</src></image></images>
  <variants>
   <variant><sku>TM-1</sku><price>18.19</price><available>true</available>
            <variant_title>59 mL</variant_title><option1>59 mL</option1></variant>
   <variant><sku>TMD01</sku><price>39.95</price><available>true</available>
            <variant_title>237 mL</variant_title><option1>237 mL</option1></variant>
  </variants></product>
 <product><handle>biocidin</handle><title>Biocidin</title><vendor>Biocidin Botanicals</vendor>
  <variants><variant><sku>BI-1</sku><price>72.30</price></variant></variants></product>
</products>"""


def _lijst(tmp_path, tekst):
    pad = tmp_path / "selectie.txt"
    pad.write_text(tekst, encoding="utf-8")
    return selectie.lees_lijst(str(pad))


def test_winkelspelling_en_merktag():
    assert merken.winkelmerk("NaturesPlus") == "Natures Plus"
    assert merken.winkelmerk(" Trace Minerals ") == "Trace Minerals"
    assert merken.met_merktag("vat-high", "Natures Plus") == "vat-high, Natures Plus"
    assert merken.met_merktag("vat-high, natures plus", "Natures Plus") == "vat-high, natures plus"
    assert merken.met_merktag("", "MethylPro") == "MethylPro"


def test_alleen_gekozen_merken_plat_en_uitzondering(tmp_path):
    merk, weg = _lijst(tmp_path, "merk: NaturesPlus  # Deltastar-spelling mag\nmerk: Trace Minerals\n-tmd01\n")
    assert merk == ["Natures Plus", "Trace Minerals"] and weg == {"TMD01"}
    rijen, per_merk, over = selectie.kies(ET.fromstring(BRON), merk, weg)
    assert [r["sku"] for r in rijen] == ["NP-1", "TM-1"]                # Biocidin niet gekozen, TMD01 weg
    assert per_merk == {"Natures Plus": 1, "Trace Minerals": 1} and over == ["TMD01 Ionic Zinc"]
    np_ = rijen[0]
    assert np_["vendor"] == np_["brand"] == "Natures Plus"
    assert np_["tags"] == "vat-high, Natures Plus"
    assert np_["option1"] == np_["variant_title"] == "Default Title"
    assert np_["image"] == "https://x/a.jpg" and np_["image_links"] == "https://x/a.jpg,https://x/b.jpg"
    assert np_["published"] == "true"                                   # Max 25-11: blijft true


def test_feed_is_plat_zonder_variants_blok(tmp_path):
    merk, weg = _lijst(tmp_path, "merk: Trace Minerals\n")
    rijen, _, _ = selectie.kies(ET.fromstring(BRON), merk, weg)
    root = selectie.bouw(rijen)
    assert root.find(".//variants") is None and root.find(".//images") is None
    assert [p.findtext("handle") for p in root.iter("product")] == ["ionic-zinc", "ionic-zinc"]
    assert [p.findtext("option1") for p in root.iter("product")] == ["59 mL", "237 mL"]


def test_tikfout_in_merk_stopt(tmp_path):
    merk, weg = _lijst(tmp_path, "merk: Trace Mineral\n")
    with pytest.raises(SystemExit):
        selectie.kies(ET.fromstring(BRON), merk, weg)


def test_onbekende_regel_en_lege_lijst_stoppen(tmp_path):
    with pytest.raises(SystemExit):
        _lijst(tmp_path, "Trace Minerals\n")
    with pytest.raises(SystemExit):
        _lijst(tmp_path, "# alleen commentaar\n-TMD01\n")


def test_echte_selectie_txt_is_geldig():
    merk, weg = selectie.lees_lijst()
    assert "Trace Minerals" in merk and "Natures Plus" in merk and "MethylPro" in merk
    assert {"TMD01", "NP-3774"} <= weg
