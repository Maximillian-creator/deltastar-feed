# Deltastar feeds → Stock Sync

Scrapt de storefront van leverancier **Deltastar** (`deltastar.nl`, Shopify) en
genereert twee XML-feeds voor [Stock Sync](https://stock-sync.com). Beide draaien
automatisch via GitHub Actions; je hoeft niets handmatig te doen.

| Feed | Script | Output | Doel | Schema |
|---|---|---|---|---|
| **Update-feed** | `scraper.py` | `deltastar_feed.xml` | Prijs + voorraad van **bestaande** producten bijwerken | 2× per dag (06:00 + 18:00 UTC) |
| **Add-feed** | `add_scraper.py` | `deltastar_add_feed.xml` | **Nieuwe** producten aanmaken met álle info | 1× per week (ma 04:00 UTC) |

## Add-feed sinds 25-11-2026: plat

De add-feed is **plat**: één `<product>` per variant, groeperen op `handle` (zoals alle andere
add-feeds; Stock Sync sloeg bij Kala een genest blok met één variant stil over). Verder
(`plat.py`, `merken.py`):
- merknaam in winkelspelling: NaturesPlus → Natures Plus, Doctor Wilson's → Dr. Wilson's,
  Designs for Health → Designs For Health, Vuzïmo → Vitalized; de merknaam staat ook als tag
  (merkpagina's als natures-plus lopen op die tag);
- zonder wat in `niet_toevoegen.txt` staat: SKU's die al in de winkel staan zonder (die) SKU,
  THT-partijen, en merk Vitalized (komt uit de eigen Vitalized-feed).

Stock Sync, "Add products": Parent node `products.product[*]`, **Variant node leeg**, identifier
`sku`, Variantgroep `handle` + Variant optie 1 `option1`, afbeeldingen `image_links`
(komma-gescheiden). Alleen nieuwe producten aanmaken; bestaande overslaan.

## Feed-URL's (Stock Sync)

```
Update:  https://raw.githubusercontent.com/Maximillian-creator/deltastar-feed/main/deltastar_feed.xml
Add:     https://raw.githubusercontent.com/Maximillian-creator/deltastar-feed/main/deltastar_add_feed.xml
```

## Waarom twee feeds?

`/products.json` van de leverancier is beperkt: **geen barcode, geen losse
ingrediënten/dosering/allergenen**. De add-feed combineert daarom drie bronnen
per product:

1. **`/products.json`** — titel, body_html, vendor, type, tags, opties (met namen),
   álle afbeeldingen, varianten
2. **JSON-LD op de live pagina** — barcode (`gtin13`) per variant + merk
3. **Accordeons op de live pagina** — Ingrediënten (tabel met %RI), Dosering,
   Allergenen, Waarschuwingen, Bewaren

## Velden in de add-feed

Per `<product>`: `handle, title, vendor, brand, product_type, tags, published,
btw, body_html, description, ingredienten, dosering, allergenen, waarschuwingen,
bewaren, option1_name…3`, een `<images>`-blok (alle afbeeldingen) en een
`<variants>`-blok met per variant: `sku, barcode, price, compare_at_price,
available, variant_title, option1…3, weight (g), image`.

> **Prijs** = leverancierprijs (excl. BTW) × BTW. BTW is 9 % bij de tag
> `vat-low`/`vat-liquid`, anders 21 % — identiek aan de update-feed.
>
> **Voorraad** zit bewust *niet* in de add-feed (alleen `available`): de
> daadwerkelijke voorraad loopt via de update-feed, zodat één bron de stand bepaalt.

## Stock Sync mapping (Add products)

Maak een **nieuwe** koppeling, type **"Add Products"** (niet de inventory/update-template).
Bronformaat = XML. Parent node `products.product[*]`, **Variant node leeg** (de feed is plat
sinds 25-11-2026), identifier `sku`. Onder "Combine rows into one product": Variantgroep
**`handle`** en Variant optie 1 **`option1`**.

**Productvelden** (staan in elke regel; Stock Sync neemt ze per handle één keer):

| Stock Sync veld | XPath |
|---|---|
| Handle | `handle` |
| Title | `title` |
| Body HTML / Description | `description` *(rijk: body + ingrediënten/dosering/allergenen)* — of `body_html` voor alleen het marketingblok |
| Vendor | `vendor` *(of `brand`)* |
| Type | `product_type` |
| Tags | `tags` |
| Published | `published` |
| Option1/2/3 Name | `option1_name` / `option2_name` / `option3_name` |
| Image Src *(meerdere)* | `image_links` *(komma-gescheiden)* |

**Variantvelden** (één regel = één variant):

| Stock Sync veld | XPath |
|---|---|
| Variant SKU | `sku` |
| Variant Barcode | `barcode` |
| Variant Price | `price` *(al incl. BTW)* |
| Variant Compare At Price | `compare_at_price` |
| Variant Option1/2/3 | `option1` / `option2` / `option3` |
| Variant Weight | `weight` *(eenheid: `weight_unit` = g)* |
| Variant Image | `image` |
| (Available) | `available` |

**Voorkom botsingen met de update-feed:**
- Zet de add-koppeling op **alleen nieuwe producten aanmaken** (geen updates van bestaande).
- **Map geen voorraad/quantity** in de add-feed — dat beheert de update-feed, zodat één
  bron de voorraad bepaalt. (Daarom zit in de add-feed alleen `available`, geen aantal.)
- `price` is al incl. BTW (×1,09 of ×1,21) — stel in Stock Sync géén extra BTW-opslag in.

## Lokaal draaien / testen

```bash
pip install requests
python add_scraper.py                       # volledige feed
TEST_HANDLE=<handle> python add_scraper.py  # één product (snel testen)
INSECURE_SSL=1 python add_scraper.py        # achter een SSL-onderscheppende proxy
```

`INSECURE_SSL` is alleen voor lokaal testen achter een bedrijfsproxy; in GitHub
Actions staat dit uit en wordt het certificaat netjes geverifieerd.
