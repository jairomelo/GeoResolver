from georesolver import PlaceResolver, GeoNamesQuery, WHGQuery, WikidataQuery, TGNQuery
import pandas as pd

def test_batch_resolver_series():
    service = [GeoNamesQuery(), WHGQuery(), WikidataQuery(), TGNQuery()]
    df = pd.DataFrame({
        "place": ["Berlín", "Madrid", "Roma", "Antequera"],
        "country": ["DE", "ES", "IT", "MX"],
        "type": ["city", "city", "city", "city"]
    })
    resolver = PlaceResolver(service, threshold=75, verbose=True, lang="es")  # Set language to Spanish
    results = resolver.resolve_batch(df, 
                                     place_column="place", 
                                     country_column="country", 
                                     place_type_column="type",
                                     return_df=False)  # Return list of dictionaries

    print(f"\n=== Series Results ===")
    print(f"Results type: {type(results)}")
    print(f"Results length: {len(results)}")
    for i, result in enumerate(results):
        place = df.iloc[i]['place']
        if result:
            print(f"{place}: ({result['latitude']}, {result['longitude']})")
        else:
            print(f"{place}: No result found")

    # Check if the results list is not empty
    assert len(results) > 0, "Results should not be empty"
    assert isinstance(results, list), "Results should be a list when return_df=False"
    
    # Check that we got results for each place
    assert len(results) == len(df), "Should have one result per input place"
    
    # Check that successful results are dictionaries with required keys
    for result in results:
        if result:  # Skip None results
            assert isinstance(result, dict), "Each result should be a dictionary"
            assert 'latitude' in result, "Result should contain latitude"
            assert 'longitude' in result, "Result should contain longitude"

def test_batch_resolver_dataframe():
    service = [GeoNamesQuery(), WHGQuery(), WikidataQuery(), TGNQuery()]
    df = pd.DataFrame({
        "place": ["Berlin", "Madrid", "Rome"],
        "country": ["DE", "ES", "IT"],
        "type": ["city", "city", "city"]
    })
    resolver = PlaceResolver(service, threshold=75, verbose=True)
    results_df = resolver.resolve_batch(df, 
                                       place_column="place", 
                                       country_column="country", 
                                       place_type_column="type",
                                       return_df=True)  # Return DataFrame with all metadata

    print(f"\n=== DataFrame Results ===")
    print("Results DataFrame:")
    print(results_df)
    print("\nIndividual results:")
    for idx in range(len(results_df)):
        row = results_df.iloc[idx]
        original_place = df.iloc[idx]['place']
        print(f"{original_place}: ({row['latitude']}, {row['longitude']}) - {row['source']}")

    # Check if the DataFrame has the expected structure
    assert isinstance(results_df, pd.DataFrame), "Results should be a DataFrame when return_df=True"
    assert len(results_df) == len(df), "Results DataFrame should have same number of rows as input"
    
    # Check that required columns are present
    required_columns = ['latitude', 'longitude', 'place', 'source', 'confidence']
    for col in required_columns:
        assert col in results_df.columns, f"Column '{col}' should be present in the DataFrame"
    
    # Check that latitude and longitude are not null (assuming successful resolution)
    assert not results_df['latitude'].isnull().any(), "Latitude should not contain null values"
    assert not results_df['longitude'].isnull().any(), "Longitude should not contain null values"

def test_batch_resolver_list():
    service = [GeoNamesQuery(), WHGQuery(), WikidataQuery(), TGNQuery()]
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
                                     return_df=False)  # Return list of dictionaries

    print(f"\n=== List Results ===")
    print(f"Results type: {type(results)}")
    print(f"Raw results: {results}")
    print("\nFormatted results:")
    for i, result in enumerate(results):
        place = df.iloc[i]['place']
        country = df.iloc[i]['country']
        if result:
            print(f"{place}, {country}: ({result['latitude']}, {result['longitude']})")
        else:
            print(f"{place}, {country}: No result found")

    # Check if the results is a list and not empty
    assert isinstance(results, list), "Results should be a list when return_df=False"
    assert len(results) > 0, "Results list should not be empty"
    assert len(results) == len(df), "Should have one result per input place"
    
    # Check if each successful result is a dictionary with latitude and longitude
    for result in results:
        if result:  # Skip None results
            assert isinstance(result, dict), "Each result should be a dictionary"
            assert 'latitude' in result, "Result should contain latitude"
            assert 'longitude' in result, "Result should contain longitude"
            assert isinstance(result['latitude'], (int, float)), "Latitude should be numeric"
            assert isinstance(result['longitude'], (int, float)), "Longitude should be numeric"


""" def test_batch_real_df(csv_path="tests/data/bautismos_cleaned.csv"):
    df = pd.read_csv(csv_path)

    df["country_code"] = "PE" 
    df["place_type"] = "city" 

    resolver = PlaceResolver([GeoNamesQuery(), WHGQuery()],
                            verbose=True, lang="es")
    results_df = resolver.resolve_batch(df,
                                        place_column="Descriptor Geográfico 2",
                                        country_column="country_code",
                                        place_type_column="place_type",
                                        show_progress=True)
    print(f"\n=== Real DataFrame Results ===")
    print("Results DataFrame:")
    print(results_df.head())

    assert isinstance(results_df, pd.DataFrame), "Results should be a DataFrame"
    assert 'latitude' in results_df.columns, "Results DataFrame should contain latitude"
    assert 'longitude' in results_df.columns, "Results DataFrame should contain longitude"
    
    # Check that we have at least some successful results
    successful_results = results_df.dropna(subset=['latitude', 'longitude'])
    assert len(successful_results) > 0, "Should have at least some successful coordinate resolutions"
    
    # Print some statistics about the results
    total_places = len(results_df)
    resolved_places = len(successful_results)
    resolution_rate = (resolved_places / total_places) * 100
    print(f"Resolution statistics: {resolved_places}/{total_places} places resolved ({resolution_rate:.1f}%)")
    
    # Show some examples of successful and failed resolutions
    print("\nSuccessful resolutions:")
    print(successful_results[['place', 'country_code', 'standardize_label', 'latitude', 'longitude', 'source']].head())

    failed_places = results_df[results_df['latitude'].isnull()]
    if len(failed_places) > 0:
        print(f"\nFailed to resolve {len(failed_places)} places:")
        print(failed_places['place'].unique()[:10])  # Show first 10 unresolved places """