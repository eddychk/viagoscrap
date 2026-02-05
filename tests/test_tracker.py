from viagoscrap.tracker import is_price_drop, parse_price


def test_parse_price_eur_symbol():
    value, currency = parse_price("A partir de 245,90 €")
    assert value == 245.90
    assert currency == "EUR"


def test_parse_price_usd_symbol():
    value, currency = parse_price("From $199.50")
    assert value is None
    assert currency is None


def test_parse_price_without_numeric():
    value, currency = parse_price("Prix indisponible")
    assert value is None
    assert currency is None


def test_price_drop_detection():
    assert is_price_drop(120.0, 99.0) is True
    assert is_price_drop(120.0, 120.0) is False
    assert is_price_drop(None, 99.0) is False
