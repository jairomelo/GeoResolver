from georesolver import GeonamesQuery, PlaceResolver

def test_geonames_query():
    service = [GeonamesQuery()]

    resolver = PlaceResolver(service, verbose=True)

    place_name = "New York"
    country_code = "US"
    place_type = "P"

    coordinates = resolver.resolve(place_name, country_code, place_type)
    assert coordinates[0] is not None, "Coordinates should not be None"
    assert isinstance(coordinates, tuple), "Coordinates should be a tuple"
    assert len(coordinates) == 2, "Coordinates should contain latitude and longitude"
    assert coordinates == (40.71427, -74.00597), f"Coordinates {coordinates} do not match expected values for New York, US"