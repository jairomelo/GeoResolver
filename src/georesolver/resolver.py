import traceback
from typing import Union, Optional, Dict, Any, List
from SPARQLWrapper import SPARQLWrapper, JSON
from rapidfuzz import fuzz
import os
import json
from importlib.resources import files
import requests
import requests_cache
import pandas as pd
from tqdm import tqdm
import ast
from dotenv import load_dotenv
from ratelimit import limits, sleep_and_retry

from georesolver.utils.LoggerHandler import setup_logger

load_dotenv(".env")

TGN_ENDPOINT = "http://vocab.getty.edu/sparql"
WHG_ENDPOINT = "https://whgazetteer.org/api"
GEONAMES_ENDPOINT = "http://api.geonames.org"
WIKIDATA_ENDPOINT = "https://www.wikidata.org/w/api.php"
ENTITYDATA_ENDPOINT = "https://www.wikidata.org/wiki/Special:EntityData/"

class BaseQuery:
    """
    Base class for geolocation API services.
    Handles caching, rate limiting, and basic GET requests.
    """

    def __init__(
        self,
        base_url: str,
        cache_name: str = "geo_cache",
        cache_expiry: int = 86400,  # 1 day
        rate_limit: tuple = (30, 1),  # 30 calls per 1 second
        enable_cache: bool = True,
        verbose: bool = False
    ):
        self.logger = setup_logger(self.__class__.__name__, verbose)
        self.base_url = base_url.rstrip("/")
        self.calls, self.period = rate_limit

        if enable_cache:
            requests_cache.install_cache(cache_name, expire_after=cache_expiry)
            self.logger.info(f"Installed cache '{cache_name}' (expires after {cache_expiry}s)")

    @sleep_and_retry
    @limits(calls=30, period=1)
    def _limited_get(self, url: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        """
        Internal method to perform a GET request with rate limiting.
        """
        full_url = f"{self.base_url}{url}" if not url.startswith("http") else url
        try:
            response = requests.get(full_url, params=params)
            response.raise_for_status()
            if getattr(response, "from_cache", False):
                self.logger.info(f"[CACHE HIT] {response.url}")
            else:
                self.logger.info(f"[API CALL] {response.url}")
            return response
        except requests.RequestException as e:
            self.logger.error(f"Request failed for URL: {full_url}, params: {params}, error: {e}")
            raise


class PlaceTypeMapper:
    def __init__(self, mapping: dict):
        self.mapping = mapping

    def get_for_service(self, place_type, service) -> Union[str, None]:
        try:
            return self.mapping[place_type.lower()][service]
        except KeyError:
            return None

class TGNQuery(BaseQuery):
    """
    A class to interact with the Getty Thesaurus of Geographic Names (TGN) SPARQL endpoint.
    
    This class provides methods to search and retrieve geographic coordinates for places
    using the Getty TGN linked open data service. It supports fuzzy matching of place names
    and filtering by country and place type.

    Attributes:
        sparql (SPARQLWrapper): SPARQL endpoint wrapper instance for TGN queries
        lang (str): Language code for the place type (default: "en")

    Example:
        >>> tgn = TGNQuery("http://vocab.getty.edu/sparql")
        >>> results = tgn.places_by_name("Madrid", "Spain", "ciudad")
        >>> coordinates = tgn.get_best_match(results, "Madrid")
    """
    def __init__(self,  lang: str = "en"):
        super().__init__(base_url=TGN_ENDPOINT)
        self.sparql = SPARQLWrapper(self.base_url)
        self.sparql.setReturnFormat(JSON)
        self.lang = lang

    @sleep_and_retry
    @limits(calls=10, period=1)
    def places_by_name(self, place_name: str, country_code: str, place_type: Union[str, None] = None) -> Union[dict, list]:
        """
        Search for places using the TGN SPARQL endpoint.
        
        Parameters:
            place_name (str): Name of the place to search for
            country_code (str): Country code or name
            place_type (str): Optional type of place (e.g., 'ciudad', 'pueblo')
        """


        type_filter = f'?p gvp:placeType [rdfs:label "{place_type}"@{self.lang}].' if place_type else ''

        query = f"""
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX luc: <http://www.ontotext.com/owlim/lucene#>
            PREFIX gvp: <http://vocab.getty.edu/ontology#>
            PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>
            PREFIX tgn: <http://vocab.getty.edu/tgn/>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

            SELECT * {{
                ?p skos:inScheme tgn:; luc:term "{place_name}"; gvp:prefLabelGVP [xl:literalForm ?pLab].
                ?pp1 skos:inScheme tgn:; luc:term "{country_code}"; gvp:prefLabelGVP [xl:literalForm ?pp1Lab].
                ?p gvp:broaderPartitiveExtended ?pp1.
                {type_filter}
            }}
        """
        
        try:
            self.sparql.setQuery(query)
            results = self.sparql.query().convert()
            if isinstance(results, dict) and "results" in results and "bindings" in results["results"]:
                return results["results"]["bindings"]
            else:
                self.logger.error(f"Unexpected SPARQL result format for '{place_name}': {results}")
                return []
        except Exception as e:
            self.logger.error(f"Error querying TGN for '{place_name}': {str(e)}")
            return []

    def get_coordinates_lod_json(self, tgn_uri: str) -> tuple:
        json_url = tgn_uri + ".json"
        try:
            response = self._limited_get(json_url) 
            data = response.json()
            for item in data.get("identified_by", []):
                if item.get("type") == "crm:E47_Spatial_Coordinates":
                    coords = ast.literal_eval(item.get("value"))
                    if isinstance(coords, list) and len(coords) == 2:
                        lon, lat = coords
                        return lat, lon
            return (None, None)
        except Exception as e:
            self.logger.error(f"Error fetching coordinates via JSON for {tgn_uri}: {e}")
            return (None, None)

    def get_best_match(self, results: dict, place_name: str, fuzzy_threshold: float) -> tuple:
        if not results:
            return (None, None)
        
        if len(results) == 1:
            return self.get_coordinates_lod_json(results[0].get("p", {}).get("value", ""))

        for r in results:
            label = r.get("pLab", {}).get("value", "")
            uri = r.get("p", {}).get("value", "")
            ratio = fuzz.ratio(label.lower(), place_name.lower())
            if ratio >= fuzzy_threshold:
                self.logger.info(f"Best match for '{place_name}': {label} ({ratio}%)")
                return self.get_coordinates_lod_json(uri)
        
        return (None, None)

class WHGQuery(BaseQuery):
    """
    A class to interact with the World Historical Gazetteer (WHG) API.

    This class provides methods to search and retrieve geographic coordinates for historical
    places using the WHG API. It supports filtering by country code and feature class,
    and includes functionality to find the best matching place from multiple results.

    Attributes:
        endpoint (str): The base URL for the WHG API
        search_domain (str): The API endpoint path for searches. Default is "/index"
        collection (str): The WHG collection to search in (default: "")

    Example:
        >>> whg = WHGQuery("https://whgazetteer.org/api")
        >>> results = whg.places_by_name("Cuicatlán", country_code="MX", place_type="p")
        >>> coordinates = whg.get_best_match(results, place_type="pueblo", country_code="MX")
    """
    def __init__(self, search_domain: str = "index", dataset: str = ""):
        super().__init__(base_url=WHG_ENDPOINT)
        self.dataset = dataset
        self.search_domain = search_domain

    @sleep_and_retry
    @limits(calls=5, period=1)  # There's no official rate limit for WHG, but we set a conservative limit
    def places_by_name(self, place_name: str, country_code: str, place_type: str = "p") -> dict:
        """
        Search for place using the World Historical Gazetteer API https://docs.whgazetteer.org/content/400-Technical.html#api
        
        Parameters:
            place_name (str): Any string with the name of the place. This keyword includes place names variants.
            country_code (str): ISO 3166-1 alpha-2 country code.
            place_type (str): Feature class according to Linked Places Format. Default is 'p' for place. Look at https://github.com/LinkedPasts/linked-places-format for more places classes.
        """
        
        if not place_name or not isinstance(place_name, str):
            raise ValueError("place_name must be a non-empty string")
        if country_code and (not isinstance(country_code, str) or len(country_code) != 2):
            raise ValueError("country_code must be a valid 2-letter country code")
        if not place_type:
            self.logger.warning("place_type should be a string, defaulting to 'p' for place type.")
            place_type = "p"

        url = f"{self.base_url}/{self.search_domain}/?name={place_name}&ccodes={country_code}&fclass={place_type}&dataset={self.dataset}"

        try:
            response = self._limited_get(url)
            results = response.json()
            return self._post_filtering(results, country_code=country_code)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error searching for '{place_name}': {str(e)}")
            return {"features": []}
        except ValueError as e:
            self.logger.error(f"Invalid JSON response for '{place_name}': {str(e)}")
            return {"features": []}


    def get_best_match(self, results: dict, place_name: str, fuzzy_threshold: float) -> tuple:

        self.logger.info(f"Finding best match for '{place_name}' in WHG results")

        try:
            features = results.get("features", [])
            if not features:
                return None, None

            for r in features:
                name = r.get("properties", {}).get("title", "")
                if not name:
                    continue
                
                ratio = fuzz.ratio(name.lower(), place_name.lower())
                self.logger.info(f"Comparing '{name}' with '{place_name}': {ratio}% similarity")
                if ratio >= fuzzy_threshold:
                    geometry = r.get("geometry", {})
                    if geometry.get("type") == "GeometryCollection":
                        self.logger.warning(f"Best match for '{place_name}' is a GeometryCollection. Taking the first valid point.")

                        coordinates = None
                        for geom in geometry.get("geometries", []):
                            if geom.get("type") == "Point":
                                coordinates = geom.get("coordinates")
                                break
                        if not coordinates:
                            self.logger.warning(f"No valid Point found in GeometryCollection for '{place_name}'.")
                            continue
                        
                    else:
                        coordinates = geometry.get("coordinates")
                    if coordinates and len(coordinates) == 2:
                        self.logger.info(f"Best match for '{place_name}': {name} ({ratio}%)")
                        return coordinates[1], coordinates[0] # Convert from GeoJSON (lon, lat) to (lat, lon)

            return (None, None)
        
        except Exception as e:
            self.logger.error(f"Error processing results: {str(e)}")
            return (None, None)

    def _post_filtering(
    self,
    results: dict,
    country_code: Optional[str] = None
) -> dict:
        """
        Post-process the WHG API results to filter by country code. This extra step is necessary
        because the WHG API does a soft filtering by country code, but it does not guarantee that
        all results will match the provided country code.
        """
        if not results.get("features"):
            return {"features": []}

        filtered = []
        for feature in results["features"]:
            props = feature.get("properties", {})
            ccodes = props.get("ccodes", [])
            if len(ccodes) == 0:
                ccodes = feature.get("ccodes", [])

            # Check country code
            if country_code and country_code.upper() not in ccodes:
                continue

            filtered.append(feature)

        return {"features": filtered}

class GeonamesQuery(BaseQuery):
    """
    A class to interact with the Geonames API.

    This class provides methods to search and retrieve geographic coordinates for places
    using the Geonames API. It supports filtering by country and feature class.

    Attributes:
        endpoint (str): The base URL for the Geonames API
        username (str): Geonames API username for authentication

    Example:
        >>> geonames = GeonamesQuery("http://api.geonames.org", username="your_username")
        >>> results = geonames.places_by_name("Madrid", country="ES")
        >>> coordinates = geonames.get_best_match(results, "Madrid")
    """
    def __init__(self, geonames_username: Union[str, None] = None):
        super().__init__(base_url=GEONAMES_ENDPOINT)
        if geonames_username:
            self.username = geonames_username
        else:
            self.username = os.getenv("GEONAMES_USERNAME")
        if not self.username:
            raise ValueError("Geonames username must be provided either as an argument or via the GEONAMES_USERNAME environment variable.")

    def places_by_name(self, place_name: str, country_code: str, place_type: Union[str, None] = None) -> dict:
        """
        Search for places using the Geonames API.
        
        Parameters:
            place_name (str): Name of the place to search for
            country_code (str): Optional ISO 3166-1 alpha-2 country code
            place_type (str): Optional feature class (A: country, P: city/village, etc.).
                              Additional types can be added in the data/mappings/geonames_place_map.json file.
        """

        params = {
            'q': place_name,
            'username': self.username,
            'maxRows': 10,
            'type': 'json',
            'style': 'FULL'
        }
        
        if country_code:
            params['country'] = country_code
        
        if place_type:
            params['featureClass'] = place_type.lower()

        try:
            response = self._limited_get(
                "/searchJSON",
                params=params
            )
            return response.json()
        except Exception as e:
            self.logger.error(f"Error querying Geonames for '{place_name}': {str(e)}")
            return {"geonames": []}

    def get_best_match(self, results: dict, place_name: str, fuzzy_threshold: float) -> tuple:
        """
        Get the best matching place from the results based on name similarity.
        
        Parameters:
            results (dict): Results from places_by_name query
            place_name (str): Original place name to match against
            fuzzy_threshold (float): Minimum similarity score (0-100) for a match
        
        Returns:
            tuple: (latitude, longitude) or (None, None) if no match found
        """
        if not results.get("geonames"):
            return (None, None)

        geonames = results["geonames"]
        if len(geonames) == 1:
            return (float(geonames[0]["lat"]), float(geonames[0]["lng"]))

        best_ratio = 0
        best_coords = (None, None)
        
        for place in geonames:
            name = place.get("name", "")
            alternate_names = place.get("alternateNames", [])
            all_names = [name] + [n.get("name", "") for n in alternate_names]
            
            for n in all_names:
                partial_ratio = fuzz.partial_ratio(place_name.lower(), n.lower())
                regular_ratio = fuzz.ratio(place_name.lower(), n.lower())
                ratio = max(partial_ratio, regular_ratio)
                
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_coords = (float(place["lat"]), float(place["lng"]))
                    self.logger.info(f"Found match: '{name}' with similarity {ratio}%")

        if best_ratio >= fuzzy_threshold:
            return best_coords
        
        return (None, None)

class WikidataQuery(BaseQuery):
    """
    A class to interact with the Wikidata MediaWiki API for geographic coordinates lookup.
    """

    def __init__(self,
                 search_endpoint=WIKIDATA_ENDPOINT,
                 entitydata_endpoint=ENTITYDATA_ENDPOINT):
        super().__init__(base_url=search_endpoint)
        self.search_endpoint = search_endpoint
        self.entitydata_endpoint = entitydata_endpoint

    @sleep_and_retry
    @limits(calls=30, period=1)
    def places_by_name(self, place_name: str, country_code: str, place_type: Union[str, None] = None) -> list:
        params = {
            "action": "wbsearchentities",
            "search": place_name,
            "language": "en",
            "format": "json",
            "type": "item",
            "limit": 10
        }

        try:
            response = self._limited_get(self.search_endpoint, params=params)
            search_results = response.json().get("search", [])
        except Exception as e:
            self.logger.error(f"Error querying Wikidata for '{place_name}': {e}")
            return []

        enriched_results = []

        for result in search_results:
            qid = result.get("id")
            label = result.get("label", "")

            # Fetch entity data
            entity_data = self._fetch_entity_data(qid)
            if not entity_data:
                continue

            claims = entity_data.get("claims", {})
            coords = self._extract_coordinates(claims)
            if not coords or coords == (None, None):
                continue

            if country_code and not self._match_country(claims, country_code):
                continue

            if place_type and not self._match_place_type(claims, place_type):
                continue

            enriched_results.append({
                "label": label,
                "qid": qid,
                "coordinates": coords
            })

        return enriched_results

    def _fetch_entity_data(self, qid: str) -> dict:
        try:
            url = f"{self.entitydata_endpoint}{qid}.json"
            response = self._limited_get(url)
            return response.json()["entities"][qid]
        except Exception as e:
            self.logger.warning(f"Failed to fetch entity data for {qid}: {e}")
            return {}

    def get_best_match(self, results: dict, place_name: str, fuzzy_threshold: float = 90) -> tuple:
        if not results:
            return (None, None)

        best_score = 0
        best_coords = None

        for result in results:
            label = result["label"]
            coords = result["coordinates"]
            score = max(fuzz.ratio(label.lower(), place_name.lower()),
                        fuzz.partial_ratio(label.lower(), place_name.lower()))

            if score > best_score and score >= fuzzy_threshold:
                best_score = score
                best_coords = coords
                self.logger.info(f"Wikidata match: '{label}' → {score}%")

        return best_coords if best_coords else (None, None)

    def _extract_coordinates(self, claims: dict) -> tuple:
        try:
            coord_data = claims.get("P625", [])[0]["mainsnak"]["datavalue"]["value"]
            return coord_data["latitude"], coord_data["longitude"]
        except Exception:
            return (None, None)

    def _match_country(self, claims: dict, iso_code: str) -> bool:
        try:
            country_entity = claims.get("P17", [])[0]["mainsnak"]["datavalue"]["value"]["id"]
            url = f"{self.entitydata_endpoint}{country_entity}.json"
            response = self._limited_get(url)
            country_data = response.json()
            wikidata_iso = country_data["entities"][country_entity]["claims"]["P297"][0]["mainsnak"]["datavalue"]["value"]
            return wikidata_iso.upper() == iso_code.upper()
        except Exception:
            return False

    def _match_place_type(self, claims: dict, expected_qid: str) -> bool:
        try:
            types = [c["mainsnak"]["datavalue"]["value"]["id"] for c in claims.get("P31", [])]
            return expected_qid in types
        except Exception:
            return False

        
class PlaceResolver:
    """
    A unified resolver that queries multiple geolocation services in order
    and returns the first match with valid coordinates.
    """
    def __init__(self, services: Optional[List[BaseQuery]] = None, places_map_json: Union[str, None] = None, threshold: float = 90, verbose: bool = False):
        
        self.logger = setup_logger(self.__class__.__name__, verbose)
        
        if services is None or not isinstance(services, list) or len(services) == 0:
            services = [
                GeonamesQuery(),
                WHGQuery(),
                TGNQuery(),
                WikidataQuery()
            ]

        self.services = services
        self.places_map = self._load_places_map(places_map_json)
        self.threshold = threshold

        for service in self.services:
            service.logger = setup_logger(service.__class__.__name__, verbose)
            self.logger.debug(f"Updated logger for {service.__class__.__name__} with verbose={verbose}")

    def _load_places_map(self, custom_path=None):
        try:
            if custom_path:
                with open(custom_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                resource_path = files("georesolver").joinpath("data/mappings/places_map.json")
                with resource_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading places map: {e}")
            return {}


    def resolve(self, place_name: str, country_code: Union[str, None] = None, place_type: Union[str, None] = None,
               use_default_filter: bool = False) -> tuple:
        """
        Try resolving the place coordinates using multiple sources.

        Args:
            place_name (str): The place name to search
            country_code (str): ISO country code (optional)
            place_type (str): Place type (optional)
            use_default_filter (bool): If True, apply a default filter as fallback in case the place_type is not found.
                                        If no place_type is provided, no filtering will be applied.

        Returns:
            tuple: (lat, lon) or (None, None) if not found
        """
        for service in self.services:
            try:
                self.logger.info(f"Trying {service.__class__.__name__} for '{place_name}'")
                mapper = PlaceTypeMapper(self.places_map)
                service_key = service.__class__.__name__.lower().replace("query", "")

                resolved_type = None

                if place_type:
                    resolved_type = mapper.get_for_service(place_type, service_key)
                    if resolved_type is None and use_default_filter:
                        self.logger.warning(
                            f"Unrecognized place_type '{place_type}' for service '{service_key}', falling back to 'pueblo'."
                        )
                        resolved_type = mapper.get_for_service("pueblo", service_key)
                    elif resolved_type is None:
                        self.logger.info(
                            f"Skipping place_type filter for service '{service_key}' (unrecognized type: '{place_type}')."
                        )

                results = service.places_by_name(place_name, country_code, resolved_type)
                coords = service.get_best_match(results, place_name, fuzzy_threshold=self.threshold)
                if coords != (None, None):
                    self.logger.info(f"Resolved '{place_name}' via {service.__class__.__name__}: {coords}")
                    return coords
            except Exception as e:
                traceback_str = traceback.format_exc()
                self.logger.warning(f"{service.__class__.__name__} failed for '{place_name}': {e}\n{traceback_str}")
        self.logger.warning(f"Could not resolve '{place_name}' via any service.")
        return (None, None)

    def resolve_batch(
            self,
            df: pd.DataFrame,
            place_column: str = "place_name",
            country_column: Union[str, None] = None,
            place_type_column: Union[str, None] = None,
            use_default_filter: bool = False,
            return_split: bool = False,
            return_list: bool = False,
            show_progress: bool = True
    ) -> Union[pd.Series, pd.DataFrame, List[tuple]]:
        """
        Resolve coordinates for a batch of places from a DataFrame.

        Args:
            df (pd.DataFrame): Input DataFrame with place names and optional country/type columns.
            place_column (str): Column name for place names.
            country_column (str): Column name for country codes (optional).
            place_type_column (str): Column name for place types (optional).
            return_split (bool): If True, return separate 'lat' and 'lon' columns.
            return_list (bool): If True, return a list of (lat, lon) tuples instead of a Series or DataFrame.

        Raises:
            ValueError: If the input DataFrame is not valid or required columns are missing.

        Returns:
            pd.Series or pd.DataFrame: A Series of (lat, lon) tuples or a DataFrame with 'lat' and 'lon' columns.
        """
        if not isinstance(df, pd.DataFrame):
            raise ValueError("Input must be a pandas DataFrame")

        if place_column not in df.columns:
            raise ValueError(f"Column '{place_column}' not found in DataFrame")

        if country_column and country_column not in df.columns:
            raise ValueError(f"Column '{country_column}' not found in DataFrame")

        if place_type_column and place_type_column not in df.columns:
            raise ValueError(f"Column '{place_type_column}' not found in DataFrame")
        
        if show_progress:
            df_iter = tqdm(df.iterrows(), total=len(df))
        else:
            df_iter = df.iterrows()

        results = []
        for _, row in df_iter:
            place_name = row.get(place_column, "")
            country_code = row.get(country_column) if country_column else None
            place_type = row.get(place_type_column) if place_type_column else None

            coords = self.resolve(
                place_name=place_name,
                country_code=country_code,
                place_type=place_type,
                use_default_filter=use_default_filter
            )

            results.append(coords)
            
        if return_split:
            return pd.DataFrame(results, columns=["lat", "lon"], index=df.index)
        elif return_list:
            return [coord if isinstance(coord, tuple) and len(coord) == 2 else (None, None) for coord in results]
        else:
            return pd.Series(results, name="coordinates")