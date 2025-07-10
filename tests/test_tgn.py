from georesolver import TGNQuery, PlaceResolver

def test_tgn_query():
    service = [TGNQuery()]  # Set language to Spanish

    resolver = PlaceResolver(services=service, verbose=True, lang="es")

    place_name = "Antequera"
    country_code = "MX"
    place_type = None

    coordinates = resolver.resolve(place_name, country_code, place_type, use_default_filter=True)
    assert coordinates[0] is not None, "Coordinates should not be None"
    assert len(coordinates) == 2, "Coordinates should contain latitude and longitude"
    assert coordinates == (-14.25, -74.0833), "Coordinates do not match expected values for Aucará, Peru"

