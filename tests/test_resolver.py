from georesolver import (    GeonamesQuery,
    TGNQuery,
    WikidataQuery,
    WHGQuery,
    PlaceResolver
)

def test_geonames_query():
    service = [GeonamesQuery(), WHGQuery(), WikidataQuery(), TGNQuery()]

    resolver = PlaceResolver(service, threshold=75)

    place_name = "New York"
    country_code = "US"
    place_type = "city"

    coordinates = resolver.resolve(place_name, country_code, place_type)
    assert coordinates[0] is not None, "Coordinates should not be None"
    assert isinstance(coordinates, tuple), "Coordinates should be a tuple"
    assert len(coordinates) == 2, "Coordinates should contain latitude and longitude"