from georesolver import GeoNamesQuery, PlaceResolver

def test_geonames_query():
    service = [GeoNamesQuery()]

    resolver = PlaceResolver(service, verbose=True, lang="es") # type: ignore

    place_name = "Nueva York"
    country_code = "US"
    place_type = "P"

    coordinates = resolver.resolve(place_name, country_code, place_type)
    assert coordinates is not None, "1. Coordinates should not be None"
    assert isinstance(coordinates, dict), "2. Coordinates should be a dict"
    assert "latitude" in coordinates and "longitude" in coordinates, "3. Coordinates should contain latitude and longitude"
    assert coordinates["latitude"] == 40.71427 and coordinates["longitude"] == -74.00597, f"4. Coordinates {coordinates} do not match expected values for New York, US" # type: ignore