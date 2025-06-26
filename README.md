![PyPI - Version](https://img.shields.io/pypi/v/georesolver)
![Python Versions](https://img.shields.io/pypi/pyversions/georesolver)
![License](https://img.shields.io/pypi/l/georesolver)
![Downloads](https://static.pepy.tech/badge/georesolver)
[![Documentation](https://img.shields.io/badge/docs-online-blue)](https://jairomelo.com/Georesolver/)
[![Issues](https://img.shields.io/github/issues/jairomelo/Georesolver)](https://github.com/jairomelo/Georesolver/issues)


# Georesolver

GeoResolver is a lightweight Python library for resolving place names into geographic coordinates using multiple gazetteer services, including [GeoNames](https://www.geonames.org/), [WHG](https://whgazetteer.org/), [Wikidata](https://www.wikidata.org/wiki/Wikidata:Main_Page), and [TGN](https://www.getty.edu/research/tools/vocabularies/tgn/).

The goal is to provide a simple interface for converting place names into latitude and longitude coordinates. The library was created to address the common need in datasets, archival collections, and manually curated records to disambiguate or complete place names, and to efficiently resolve them into coordinates.

## How it works

The logic behind GeoResolver is straightforward:

Given a place name as input, the library queries one or more gazetteers in sequence, searching for the closest match using a fuzzy matching algorithm. If a sufficiently good match is found, it returns the coordinates of the place. If not, it moves on to the next gazetteer, continuing until a match is found or all gazetteers have been queried.

If no match is found in any gazetteer, the library returns a `(None, None)` tuple.

A fuzziness threshold can be configured to control how strict the match should be. The default threshold is 90, meaning the library only accepts matches that are at least 90% similar to the input. Lowering the threshold allows more lenient matches; raising it makes the match stricter.

To improve precision, you can filter by country code and place type. This is particularly helpful for disambiguating places with the same name (e.g., “London, CA” vs. “London, UK”).

Some services (notably TGN) allow specifying place types using localized terms (e.g., "ciudad" or "city"), which can be useful when working with multilingual datasets.

GeoResolver includes a basic mapping of common place types in `data/mappings/places_map.json`. You can also pass a custom mapping to the `PlaceResolver` class to support additional types or override defaults. This is useful for adapting the resolution logic to domain-specific vocabularies or legacy data.

## How to use

To use GeoResolver, install the library via `pip`. It’s recommended to use a virtual environment to avoid conflicts with other packages:

```bash
pip install georesolver
```

### Geonames configuration

To use the GeoNames service, you must create a free account at [GeoNames](https://www.geonames.org/login) and obtain a username. This username is required to make API requests.

You can provide your username in one of two ways:

**Environment variable**

Create a `.env` file in your project directory:

```
GEONAMES_USERNAME=your_geonames_username
```

**Pass it explicitly**

```python
from georesolver import GeonamesQuery

geonames_query = GeonamesQuery(username="your_geonames_username")
```

### Basic Example Usage

The most straightforward way to use the library is through the `PlaceResolver` class. By default, `PlaceResolver` queries all available services — *GeoNames*, *WHG*, *TGN*, and *Wikidata* — in that order.

To resolve a place name, call the `.resolve()` method with the name and (optionally) a country code and place type. If no filters are specified, the first sufficiently similar match across all services is returned.

```python
from georesolver import PlaceResolver

# Initialize the resolver (uses all services by default)
resolver = PlaceResolver()

# Resolve a place name
lat, lon = resolver.resolve("London", country_code="GB", place_type="city")
print(f"Coordinates: {lat}, {lon}")
```

Sample output:

```bash
Coordinates: 51.50853, -0.12574
```

### Customizing Services

You can control which services `PlaceResolver` uses and configure them individually. For example:

```python
from georesolver import PlaceResolver, GeonamesQuery, TGNQuery

geonames = GeonamesQuery(geonames_username="your_geonames_username")
tgn = TGNQuery(lang="es")

resolver = PlaceResolver(services=[geonames, tgn], threshold=80, verbose=True)
```

This gives you full control over the resolution logic, including match strictness (`threshold`) and logging verbosity (`verbose=True`).

### Batch Resolution

GeoResolver supports batch resolution from a `pandas.DataFrame`, making it easy to process large datasets.

You can use the `resolve_batch` method to apply place name resolution to each row of a DataFrame. This method supports optional columns for country code and place type, and can return results in different formats.

```python
import pandas as pd
from georesolver import PlaceResolver, GeonamesQuery

# Sample data
df = pd.DataFrame({
    "place_name": ["London", "Madrid", "Rome"],
    "country_code": ["GB", "ES", "IT"],
    "place_type": ["city", "city", "city"]
})

# Initialize the resolver
resolver = PlaceResolver(services=[GeonamesQuery(username="your_username")], verbose=True)

# Resolve in batch, return coordinates as a new column
df["coordinates"] = resolver.resolve_batch(df,
    place_column="place_name",
    country_column="country_code",
    place_type_column="place_type"
)
```

This returns a new column coordinates with (lat, lon) tuples.

#### Return options

You can customize the output format using `return_split` or `return_list`:

- `return_split=True`: returns two separate columns "lat" and "lon"
- `return_list=True`: returns a list of (lat, lon) tuples instead of a Series or DataFrame

```python
# Separate lat/lon columns
df[["lat", "lon"]] = resolver.resolve_batch(
    df,
    place_column="place_name",
    country_column="country_code",
    place_type_column="place_type",
    return_split=True
)
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
    services=[GeonamesQuery(username="your_username")],
    places_map_json="path/to/your_custom_mapping.json"
)
```

This is useful when working with domain-specific vocabularies, legacy datasets, or non-English place type terms. You can also use it simply to override the default mapping with your own preferences.

Each service-specific list should contain valid place type codes or labels expected by that gazetteer.

## Wikidata Note

This library queries the Wikidata MediaWiki API via the endpoint:
`https://www.wikidata.org/w/api.php`

It does not use the SPARQL endpoint (`https://query.wikidata.org/sparql`), as this approach is faster and more reliable for simple place lookups. The library performs entity searches by name and retrieves coordinates, country (P17), and type (P31) from the entity data.

> ⚠️ Wikidata API queries involve multiple HTTP requests per place (search + entity data). This process is relatively slow and not recommended for bulk resolution.

## Contributing

Contributions are welcome! If you encounter a bug, need additional functionality, or have suggestions for improvement, feel free to open an issue or submit a pull request.

## License

This project is licensed under a GNU General Public License v3.0. See the [LICENSE](LICENSE) file for details.

## Acknowledgements

This library relies on open data sources and public APIs provided by GeoNames, WHG, Wikidata, and TGN. Special thanks to the maintainers of these projects for their commitment to accessible geographic knowledge.
