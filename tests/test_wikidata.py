from georesolver import WikidataQuery, PlaceResolver

def test_wikidata_query():
    service = [WikidataQuery()]

    resolver = PlaceResolver(service)

    place_name = "New York"
    country_code = "US"
    place_type = "city"

    coordinates = resolver.resolve(place_name, country_code, place_type)
    assert coordinates[0] is not None, "Coordinates should not be None"
    assert isinstance(coordinates, tuple), "Coordinates should be a tuple"
    assert len(coordinates) == 2, "Coordinates should contain latitude and longitude"
    assert coordinates == (40.71277777777778, -74.00611111111111), f"Coordinates {coordinates} do not match expected values for New York, US"