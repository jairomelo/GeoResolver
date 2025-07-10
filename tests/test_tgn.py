from georesolver import TGNQuery, PlaceResolver

def test_tgn_query():
    service = [TGNQuery()] 

    resolver = PlaceResolver(services=service, verbose=True, lang="en", flexible_threshold=True)

    place_name = "Rome"
    country_code = "IT"
    place_type = "pueblo"

    coordinates = resolver.resolve(place_name, country_code, place_type, use_default_filter=True)
    assert coordinates is not None, "Coordinates should not be None"
    assert coordinates.get("latitude") == 41.9, "Latitude does not match expected value for Rome, Italy"
    assert coordinates.get("longitude") == 12.483333, "Longitude does not match expected value for Rome, Italy"

