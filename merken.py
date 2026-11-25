"""Merknamen zoals de winkel ze gebruikt (25-11-2026).

Deltastar schrijft sommige merken anders dan onze winkel. Zonder omzetting krijgt een nieuw
product een tweede merknaam (zo staan er nu 29 producten onder "NaturesPlus" naast 182 onder
"Natures Plus", met elk een eigen merkpagina). De merkpagina's van de winkel lopen deels op een
tag met de merknaam (natures-plus, allergy-research-group, microbiome-labs,
pure-encapsulations, vitalized-supplementen); daarom krijgt elk product ook die tag.
"""

WINKELMERK = {
    "NaturesPlus": "Natures Plus",
    "Designs for Health": "Designs For Health",
    "Doctor Wilson's": "Dr. Wilson's",
    "Vuzïmo": "Vitalized",
}


def winkelmerk(merk: str | None) -> str:
    merk = (merk or "").strip()
    return WINKELMERK.get(merk, merk)


def met_merktag(tags: str | None, merk: str) -> str:
    """Tags als kommalijst, met de merknaam erbij als die er nog niet in staat."""
    lijst = [t.strip() for t in (tags or "").split(",") if t.strip()]
    if merk and merk.lower() not in (t.lower() for t in lijst):
        lijst.append(merk)
    return ", ".join(lijst)
