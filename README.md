# Deltastar feeds → Stock Sync

Scrapt de storefront van leverancier **Deltastar** (`deltastar.nl`, Shopify) en
genereert twee XML-feeds voor [Stock Sync](https://stock-sync.com). Beide draaien
automatisch via GitHub Actions; je hoeft niets handmatig te doen.

| Feed | Script | Output | Doel | Schema |
|---|---|---|---|---|
| **Update-feed** | `scraper.py` | `deltastar_feed.xml` | Prijs + voorraad van **bestaande** producten bijwerken | elke 6 uur |
| **Add-feed** | `add_scraper.py` | `deltastar_add_feed.xml` | **Nieuwe** producten aanmaken met álle info | 1× per dag |

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

Wijs in Stock Sync de XPath-paden toe, o.a.:

- Product: `product/handle`, `product/title`, `product/body_html` (of `description`),
  `product/vendor`, `product/tags`, `product/option1_name`
- Afbeeldingen (repeating): `product/images/image/src`
- Varianten (repeating): `product/variants/variant/sku`, `.../barcode`,
  `.../price`, `.../compare_at_price`, `.../weight`, `.../option1`

## Lokaal draaien / testen

```bash
pip install requests
python add_scraper.py                       # volledige feed
TEST_HANDLE=<handle> python add_scraper.py  # één product (snel testen)
INSECURE_SSL=1 python add_scraper.py        # achter een SSL-onderscheppende proxy
```

`INSECURE_SSL` is alleen voor lokaal testen achter een bedrijfsproxy; in GitHub
Actions staat dit uit en wordt het certificaat netjes geverifieerd.
