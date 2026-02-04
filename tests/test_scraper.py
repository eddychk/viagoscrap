from viagoscrap.scraper import COOKIE_ACCEPT_SELECTORS, _extract_price


def test_extract_price_euro_symbol():
    text = "Zone 1\nA partir de 245 EUR\nTotal 250 \u20ac"
    assert _extract_price(text) == "245 EUR"


def test_extract_price_fallback_regex():
    text = "Billet Tomorrowland - Offre speciale 199,99 \u20ac taxes incluses"
    assert _extract_price(text) == "199,99 \u20ac"


def test_extract_price_returns_empty_when_missing_currency():
    assert _extract_price("Billet standard - quantite 2") == ""


def test_cookie_selectors_include_french_allow_all():
    assert "button:has-text('Tout autoriser')" in COOKIE_ACCEPT_SELECTORS
