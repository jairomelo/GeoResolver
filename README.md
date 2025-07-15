![PyPI - Version](https://img.shields.io/pypi/v/georesolver)
![Python Versions](https://img.shields.io/pypi/pyversions/georesolver)
![CI](https://github.com/jairomelo/GeoResolver/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/pypi/l/georesolver)
![Downloads](https://static.pepy.tech/badge/georesolver)
[![Documentation](https://img.shields.io/badge/docs-online-blue)](https://jairomelo.com/Georesolver/)
[![Issues](https://img.shields.io/github/issues/jairomelo/Georesolver)](https://github.com/jairomelo/Georesolver/issues)


# GeoResolver

GeoResolver is a lightweight Python library for resolving place names into geographic coordinates and related metadata using multiple gazetteer services, including [GeoNames](https://www.geonames.org/), [WHG](https://whgazetteer.org/), [Wikidata](https://www.wikidata.org/wiki/Wikidata:Main_Page), and [TGN](https://www.getty.edu/research/tools/vocabularies/tgn/).

The library provides a unified interface and standardized response format across sources, making it easier to disambiguate, enrich, or geocode place names—especially in datasets, archival collections, and manually curated records.

> **GeoResolver is particularly useful for historical geocoding and legacy datasets**, where place names may be inconsistent, ambiguous, or obsolete. It is not intended to replace tools like Geopy for general-purpose geocoding. Instead, GeoResolver complements them by offering a targeted approach based on authoritative gazetteers, tailored for academic, historical, and archival contexts.

## How it works

The logic behind GeoResolver is straightforward:

Given a place name as input, the library queries one or more gazetteers in sequence, searching for the closest match using a fuzzy matching algorithm. If a sufficiently good match is found, it returns the coordinates of the place. If not, it moves on to the next gazetteer, continuing until a match is found or all gazetteers have been queried.

If no match is found in any gazetteer, the library returns a `None` value.

A fuzziness threshold can be configured to control how strict the match should be. The default threshold is 90, meaning the library only accepts matches that are at least 90% similar to the input. Lowering the threshold allows more lenient matches; raising it makes the match stricter.

It's possible to be even more flexible by enabling a flexible threshold for short place names. This is useful when you want to allow some places (like 'Rome', or 'Lima') to match without reducing the threshold for longer names.

To improve precision, you can filter by country code and place type for deambiguation or to narrow down results. 

Some services allow specifying place types using localized terms, which can be useful when working with multilingual datasets.

GeoResolver includes a basic mapping of common place types in `data/mappings/places_map.json`. You can also pass a custom mapping to the `PlaceResolver` class to support additional types or override defaults. This is useful for adapting the resolution logic to domain-specific vocabularies or legacy data.

## How to use

To use GeoResolver, install the library via `pip`. It’s recommended to use a virtual environment to avoid conflicts with other packages:

```bash
pip install georesolver
```

### Geonames configuration

To use the GeoNames service, you must create a free account at [GeoNames](https://www.geonames.org/login) and obtain a username. This username is required to make API requests.

> **Warning**: It's possible to use the username `demo` for testing purposes, but this user has very limited quota and it's possible to hit the limit quickly, especially with batch requests.

You can provide your username in one of two ways:

**Environment variable**

Create a `.env` file in your project directory:

```
GEONAMES_USERNAME=your_geonames_username
```

**Pass it explicitly**

```python
from georesolver import GeoNamesQuery

geonames_query = GeoNamesQuery(geonames_username="your_geonames_username")
```

### Basic Example Usage

The most straightforward way to use the library is through the `PlaceResolver` class. By default, `PlaceResolver` queries all available services — *GeoNames*, *WHG*, *TGN*, and *Wikidata* — in that order.

To resolve a place name, call the `.resolve()` method with the name and (optionally) a country code and place type. If no filters are specified, the first sufficiently similar match across all services is returned.

```python
from georesolver import PlaceResolver

# Initialize the resolver (uses all services by default)
resolver = PlaceResolver()

# Resolve a place name
result = resolver.resolve("London", country_code="GB", place_type="inhabited places")
if result:
    print(f"Coordinates: {result['latitude']}, {result['longitude']}")
    print(f"Source: {result['source']}")
    print(f"Confidence: {result['confidence']}")
else:
    print("No match found")
```

Sample output:

```bash
Coordinates: 51.50853, -0.12574
Source: WHG
Confidence: 100.0
```

### Enhanced Return Format

Starting with v0.2.0, the `resolve()` method returns a structured dictionary with comprehensive metadata:

```python
{
    "place": "London",
    "standardize_label": "London",
    "language": "en",
    "latitude": 51.50853,
    "longitude": -0.12574,
    "source": "GeoNames",
    "id": 2643743,
    "uri": "http://sws.geonames.org/2643743/",
    "country_code": "GB",
    "part_of": "",
    "part_of_uri": "",
    "confidence": 95.5,
    "threshold": 90,
    "match_type": "exact"
}
```

### Customizing Services

You can control which services `PlaceResolver` uses and configure them individually. For example:

```python
from georesolver import PlaceResolver, GeoNamesQuery, TGNQuery

geonames = GeoNamesQuery(geonames_username="your_geonames_username")
tgn = TGNQuery()

resolver = PlaceResolver(
    services=[geonames, tgn], 
    threshold=80, 
    flexible_threshold=True,  # Use flexible threshold for short place names
    flexible_threshold_value=70,  # Lower threshold for short names
    lang="es",  # Spanish language support
    verbose=True
)
```

This gives you more control over the resolution logic, including match strictness (`threshold`), flexible thresholding for short place names, language preferences, and logging verbosity (`verbose=True`).

### Batch Resolution

GeoResolver supports batch resolution from a `pandas.DataFrame`, making it easy to process large datasets.

You can use the `resolve_batch` method to apply place name resolution to each row of a DataFrame. This method supports optional columns for country code and place type, and can return results in different formats.

```python
import pandas as pd
from georesolver import PlaceResolver, GeoNamesQuery

# Sample data
df = pd.DataFrame({
    "place_name": ["London", "Madrid", "Rome"],
    "country_code": ["GB", "ES", "IT"],
    "place_type": ["city", "city", "city"]
})

# Initialize the resolver
resolver = PlaceResolver(services=[GeoNamesQuery(geonames_username="your_username")], verbose=True)

# Resolve in batch, return structured results as a DataFrame
result_df = resolver.resolve_batch(df,
    place_column="place_name",
    country_column="country_code",
    place_type_column="place_type",
    show_progress=False
)

print(result_df.columns.tolist())
# Output: ['place', 'standardize_label', 'language', 'latitude', 'longitude', 'source', 'place_id', 'place_uri', 'country_code', 'part_of', 'part_of_uri', 'confidence', 'threshold', 'match_type']
```

This returns a new DataFrame with columns for all resolved place attributes including coordinates, source information, and confidence scores.


#### Return options

The `resolve_batch` method returns a `pandas.DataFrame` by default, but you can also return a list of dictionaries that can be useful for JSON serialization.

```python
# Return results as a list of dictionaries
results = resolver.resolve_batch(df, 
                                place_column="place_name", 
                                country_column="country_code", 
                                place_type_column="place_type", 
                                return_df=False,  # Return list of dictionaries
                                show_progress=False)

print(results[:2])
```

Example output:

```python
[
    {
        "place": "London",
        "standardize_label": "London",
        "language": "en",
        "latitude": 51.50853,
        "longitude": -0.12574,
        "source": "GeoNames",
        "id": 2643743,
        "uri": "http://sws.geonames.org/2643743/",
        "country_code": "GB",
        "part_of": "",
        "part_of_uri": "",
        "confidence": 100.0,
        "threshold": 90,
        "match_type": "exact"
    },
    {
        "place": "Madrid",
        "standardize_label": "Madrid",
        "language": "en",
        "latitude": 40.4165,
        "longitude": -3.70256,
        "source": "GeoNames",
        "id": 3117735,
        "uri": "http://sws.geonames.org/3117735/",
        "country_code": "ES",
        "part_of": "",
        "part_of_uri": "",
        "confidence": 100.0,
        "threshold": 90,
        "match_type": "exact"
    }
]
```

## Custom Place Type Mapping

Different gazetteers use different terms to classify place types (e.g., "populated place", "settlement", "city", "pueblo"). To unify these differences, GeoResolver uses a configurable place type mapping that standardizes input values before querying services.

By default, GeoResolver uses a built-in mapping stored at `data/mappings/places_map.json`. This file maps normalized place types (like "city") to the equivalent terms used by each service.

Example mapping entry:

```json
"city": {
    "geonames": "PPL",
    "wikidata": "Q515",
    "tgn": "cities",
    "whg": "p"
  },
```

You can provide your own mapping by passing a JSON file path to `PlaceResolver`:

```python
resolver = PlaceResolver(
    services=[GeoNamesQuery(geonames_username="your_username")],
    places_map_json="path/to/your_custom_mapping.json"
)
```

This is useful when working with domain-specific vocabularies, legacy datasets, or non-English place type terms. You can also use it simply to override the default mapping with your own preferences.

Each service-specific list should contain valid place type codes or labels expected by that gazetteer.

## Wikidata Integration

This library queries the Wikidata MediaWiki API via the endpoint:
`https://www.wikidata.org/w/api.php`

It does not use the SPARQL endpoint (`https://query.wikidata.org/sparql`), as this approach is faster and more reliable for simple place lookups. The library performs entity searches by name and retrieves coordinates, country (P17), and administrative data from the entity information.

**Enhanced in v0.2.0**: WikidataQuery now provides better country and administrative entity data retrieval, with improved matching against the BaseQuery interface for consistency across all services.

> ⚠️ **Performance Note**: Wikidata API queries involve multiple HTTP requests per place (search + entity data). This process is relatively slow and not recommended for bulk resolution. Consider using GeoNames or WHG for large-scale batch processing.

## Contributing

Contributions are welcome! If you encounter a bug, need additional functionality, or have suggestions for improvement, feel free to open an issue or submit a pull request.

## License

This project is licensed under a GNU General Public License v3.0. See the [LICENSE](LICENSE) file for details.

## Acknowledgements

This library relies on open data sources and public APIs provided by GeoNames, WHG, Wikidata, and TGN. Special thanks to the maintainers of these projects for their commitment to accessible geographic knowledge.
