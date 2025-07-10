from georesolver import WHGQuery, PlaceResolver

def test_whg_query():
    service = [WHGQuery()]

    resolver = PlaceResolver(services=service, verbose=True)

    place_name = "London"
    country_code = "CA"
    place_type = "city"

    coordinates = resolver.resolve(place_name, country_code, place_type, use_default_filter=True)
    assert coordinates is not None, "Coordinates should not be None"
    assert coordinates.get("latitude") is not None and coordinates.get("longitude") is not None, "Coordinates should contain latitude and longitude"
    assert coordinates.get("source") == "WHG", "Source should be WHG"

