from georesolver import WikidataQuery, PlaceResolver

def test_wikidata_query():
    service = [WikidataQuery()]

    resolver = PlaceResolver(service, verbose=True, lang="en")

    place_name = "New York"
    country_code = "US"
    place_type = "city"

    result = resolver.resolve(place_name, country_code, place_type)
    assert result is not None, "Result should not be None"
    assert isinstance(result, dict), "Result should be a dictionary"
    
    # Test the standardized response format
    assert result['latitude'] is not None, "Latitude should not be None"
    assert result['longitude'] is not None, "Longitude should not be None"
    assert result['source'] == "Wikidata", "Source should be Wikidata"
    assert result['country_code'] == country_code, f"Country code should be {country_code}"
    assert result['standardize_label'], "Should have a standardized label"
    assert result['uri'].startswith("https://www.wikidata.org/entity/"), "Should have a valid Wikidata URI"
    
    # Test approximate coordinates for New York City
    expected_lat, expected_lon = 40.71277777777778, -74.00611111111111
    assert abs(result['latitude'] - expected_lat) < 0.1, f"Latitude {result['latitude']} should be close to {expected_lat}"
    assert abs(result['longitude'] - expected_lon) < 0.1, f"Longitude {result['longitude']} should be close to {expected_lon}"