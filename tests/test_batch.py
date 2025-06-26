from georesolver import PlaceResolver, GeonamesQuery, WHGQuery, WikidataQuery, TGNQuery
import pandas as pd

def test_batch_resolver_series():
    service = [GeonamesQuery(), WHGQuery(), WikidataQuery(), TGNQuery()]
    df = pd.DataFrame({
        "place": ["Berlin", "Madrid", "Rome"],
        "country": ["DE", "ES", "IT"],
        "type": ["city", "city", "city"]
    })
    resolver = PlaceResolver(service, threshold=75, verbose=True)
    results = resolver.resolve_batch(df, 
                                     place_column="place", 
                                     country_column="country", 
                                     place_type_column="type")

    print(f"\n=== Series Results ===")
    print(f"Results type: {type(results)}")
    print(f"Results:\n{results}")
    for i, coord in enumerate(results):
        place = df.iloc[i]['place']
        print(f"{place}: {coord}")

    # Check if the results pd.Series is not empty
    assert len(results) > 0, "Results should not be empty"

def test_batch_resolver_dataframe():
    service = [GeonamesQuery(), WHGQuery(), WikidataQuery(), TGNQuery()]
    df = pd.DataFrame({
        "place": ["Berlin", "Madrid", "Rome"],
        "country": ["DE", "ES", "IT"],
        "type": ["city", "city", "city"]
    })
    resolver = PlaceResolver(service, threshold=75, verbose=True)
    df[["lat", "lon"]] = resolver.resolve_batch(df, 
                                     place_column="place", 
                                     country_column="country", 
                                     place_type_column="type",
                                     return_split=True)
    
    print(f"\n=== DataFrame Results ===")
    print("Final DataFrame with coordinates:")
    print(df)
    print("\nIndividual results:")
    for _, row in df.iterrows():
        print(f"{row['place']} ({row['country']}): ({row['lat']}, {row['lon']})")

    # Check if the latitude and longitude columns are added
    assert "lat" in df.columns, "Latitude column should be present in the DataFrame"
    assert "lon" in df.columns, "Longitude column should be present in the DataFrame"
    assert not df[["lat", "lon"]].isnull().values.any(), "Latitude and Longitude columns should not contain NaN values"
    assert len(df) == 3, "DataFrame should contain 3 rows"

def test_batch_resolver_list():
    service = [GeonamesQuery(), WHGQuery(), WikidataQuery(), TGNQuery()]
    df = pd.DataFrame({
        "place": ["Berlin", "Madrid", "Rome"],
        "country": ["DE", "ES", "IT"],
        "type": ["city", "city", "city"]
    })
    resolver = PlaceResolver(service, threshold=75, verbose=True)
    results = resolver.resolve_batch(df, 
                                     place_column="place", 
                                     country_column="country", 
                                     place_type_column="type",
                                     return_list=True)
    
    print(f"\n=== List Results ===")
    print(f"Results type: {type(results)}")
    print(f"Raw results: {results}")
    print("\nFormatted results:")
    for i, coord in enumerate(results):
        place = df.iloc[i]['place']
        country = df.iloc[i]['country']
        print(f"{place}, {country}: {coord}")

    # Check if the results is a list and not empty
    assert isinstance(results, list), "Results should be a list"
    assert len(results) > 0, "Results list should not be empty"
    
    # Check if each result is a tuple of length 2 (lat, lon)
    for result in results:
        assert isinstance(result, tuple), "Each result should be a tuple"
        assert len(result) == 2, "Each result tuple should contain latitude and longitude"