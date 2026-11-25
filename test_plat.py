"""Pint de platte add-feed vast (25-11-2026). Draaien: python -m pytest -q test_plat.py"""
import xml.etree.ElementTree as ET

import pytest

import merken
import plat

GENEST = """<products>
 <product><handle>source-of-life</handle><title>Source of Life - 90 tablets</title>
  <vendor>NaturesPlus</vendor><brand>NaturesPlus</brand><tags>vat-high</tags><published>true</published>
  <description>&lt;p&gt;tekst&lt;/p&gt;</description>
  <images><image><position>1</position><src>https://x/a.jpg</src></image>
          <image><position>2</position><src>https://x/b.jpg</src></image></images>
  <image_links>https://x/a.jpg,https://x/b.jpg</image_links>
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


def test_winkelspelling_en_merktag():
    assert merken.winkelmerk("NaturesPlus") == "Natures Plus"
    assert merken.winkelmerk("Doctor Wilson's") == "Dr. Wilson's"
    assert merken.winkelmerk(" Trace Minerals ") == "Trace Minerals"
    assert merken.met_merktag("vat-high", "Natures Plus") == "vat-high, Natures Plus"
    assert merken.met_merktag("vat-high, natures plus", "Natures Plus") == "vat-high, natures plus"
    assert merken.met_merktag("", "MethylPro") == "MethylPro"


def test_plat_alle_merken_zonder_uitzonderingen():
    root, over = plat.maak_plat(ET.fromstring(GENEST), {"TMD01": "staat er al"})
    assert root.find(".//variants") is None and root.find(".//images") is None
    rijen = root.findall("product")
    assert [r.findtext("sku") for r in rijen] == ["NP-1", "TM-1", "BI-1"]     # alle merken, TMD01 eruit
    assert over == ["TMD01 (staat er al)"]
    np_ = rijen[0]
    assert np_.findtext("vendor") == np_.findtext("brand") == "Natures Plus"
    assert np_.findtext("tags") == "vat-high, Natures Plus"
    assert np_.findtext("option1") == np_.findtext("variant_title") == "Default Title"
    assert np_.findtext("image") == "https://x/a.jpg"
    assert np_.findtext("image_links") == "https://x/a.jpg,https://x/b.jpg"
    assert np_.findtext("published") == "true"                              # Max 25-11: blijft true
    assert np_.findtext("description") == "<p>tekst</p>"
    zink = [r for r in rijen if r.findtext("handle") == "ionic-zinc"]
    assert [r.findtext("option1") for r in zink] == ["59 mL"]
    assert zink[0].findtext("image_links") == "https://x/z.jpg"              # uit <images> als het veld ontbreekt


def test_al_platte_feed_niet_nog_eens_omzetten():
    root, _ = plat.maak_plat(ET.fromstring(GENEST), {})
    with pytest.raises(SystemExit):
        plat.maak_plat(root, {})


def test_niet_lijst(tmp_path):
    pad = tmp_path / "niet.txt"
    pad.write_text("# kop\ntmd01   # reden\n\nNP-3774\n", encoding="utf-8")
    assert plat.lees_niet(str(pad)) == {"TMD01": "reden", "NP-3774": ""}
    pad.write_text("merk: Vuzïmo  # eigen feed\n", encoding="utf-8")
    assert plat.lees_niet(str(pad)) == {"merk:Vitalized": "eigen feed"}
    pad.write_text("TMD01 NP-3774\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        plat.lees_niet(str(pad))


def test_echte_niet_lijst():
    niet = plat.lees_niet()
    assert {"TMD01", "NP-3774", "NS-329870", "NS-329931", "VP-330-SALE", "VP-332-SALE",
            "merk:Vitalized"} <= set(niet)


def test_heel_merk_eruit():
    root, over = plat.maak_plat(ET.fromstring(GENEST), {"merk:Biocidin Botanicals": "eigen feed"})
    assert [r.findtext("sku") for r in root.findall("product")] == ["NP-1", "TM-1", "TMD01"]
    assert over == ["BI-1 (eigen feed)"]


def test_prijs_nul_gaat_er_niet_in():
    genest = GENEST.replace("<price>72.30</price>", "<price>0.00</price>")
    root, over = plat.maak_plat(ET.fromstring(genest), {})
    assert "BI-1" not in [r.findtext("sku") for r in root.findall("product")]
    assert over == ["BI-1 (prijs 0.00)"]
