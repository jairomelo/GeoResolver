from georesolver.resolver import TGNQuery, PlaceResolver

def test_tgn_query():
    service = [TGNQuery(lang="es")]

    resolver = PlaceResolver(services=service)

    place_name = "Aucará"
    country_code = "PE"
    place_type = "pueblo"

    coordinates = resolver.resolve(place_name, country_code, place_type)
    assert coordinates[0] is not None, "Coordinates should not be None"
    assert len(coordinates) == 2, "Coordinates should contain latitude and longitude"
    assert coordinates == (-14.25, -74.0833), "Coordinates do not match expected values for Aucará, Peru"

