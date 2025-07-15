from georesolver import (    GeoNamesQuery,
    TGNQuery,
    WikidataQuery,
    WHGQuery,
    PlaceResolver
)

def test_geonames_query():
    service = [GeoNamesQuery(), WHGQuery(), WikidataQuery(), TGNQuery()]

    resolver = PlaceResolver(service, threshold=75)

    place_name = "New York"
    country_code = "US"
    place_type = "city"

    coordinates = resolver.resolve(place_name, country_code, place_type)
    assert coordinates is not None, "1. Coordinates should not be None"
    assert isinstance(coordinates, dict), "2. Coordinates should be a dict"
    assert "latitude" in coordinates and "longitude" in coordinates, "3. Coordinates should contain latitude and longitude"
    assert coordinates["latitude"] == 40.71427 and coordinates["longitude"] == -74.00597, f"4. Coordinates {coordinates} do not match expected values for New York, US"