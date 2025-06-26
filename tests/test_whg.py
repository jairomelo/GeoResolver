from georesolver import WHGQuery, PlaceResolver

def test_whg_query():
    service = [WHGQuery()]

    resolver = PlaceResolver(services=service, verbose=True)

    place_name = "Cuicatlán"
    country_code = "MX"
    place_type = "pueblo"

    coordinates = resolver.resolve(place_name, country_code, place_type, use_default_filter=True)
    assert coordinates[0] is not None, "Coordinates should not be None"
    assert len(coordinates) == 2, "Coordinates should contain latitude and longitude"
    assert coordinates == (17.802777777, -96.959444444), "Coordinates do not match expected values for Cuicatlán, Mexico"

