import traceback
from typing import Union
from SPARQLWrapper import SPARQLWrapper, JSON
import configparser
from rapidfuzz import fuzz
import os
import json
import requests
import ast
from dotenv import load_dotenv
from ratelimit import limits, sleep_and_retry

from georesolver.utils.LoggerHandler import setup_logger

logger = setup_logger("getCoordinates")

config = configparser.ConfigParser()
config.read("conf/global.conf")

load_dotenv(config["default"]["env_file"])

class PlaceTypeMapper:
    def __init__(self, mapping: dict):
        self.mapping = mapping

    def get_for_service(self, place_type, service) -> Union[str, None]:
        try:
            return self.mapping[place_type.lower()][service]
        except KeyError:
            return None

class TGNQuery:
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
    def __init__(self, endpoint: str = config["apis"]["tgn_endpoint"], lang: str = "en"):
        self.sparql = SPARQLWrapper(endpoint)
        self.sparql.setReturnFormat(JSON)
        self.lang = lang

    @sleep_and_retry
    @limits(calls=5, period=1)  # TGN allows 5 calls per second
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
                logger.error(f"Unexpected SPARQL result format for '{place_name}': {results}")
                return []
        except Exception as e:
            logger.error(f"Error querying TGN for '{place_name}': {str(e)}")
            return []

    def get_coordinates_lod_json(self, tgn_uri: str) -> tuple:
        json_url = tgn_uri + ".json"
        try:
            response = requests.get(json_url)
            if response.status_code == 200:
                data = response.json()

                for item in data.get("identified_by"):
                    if item.get("type") == "crm:E47_Spatial_Coordinates":
                        value = item.get("value")
                        coords = ast.literal_eval(value)
                        if isinstance(coords, list) and len(coords) == 2:
                            lon, lat = coords
                            return (lat, lon)

            return (None, None)
        except Exception as e:
            logger.error(f"Error fetching coordinates via JSON for {tgn_uri}: {e}")
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
                logger.info(f"Best match for '{place_name}': {label} ({ratio}%)")
                return self.get_coordinates_lod_json(uri)
        
        return (None, None)

class WHGQuery:
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
    def __init__(self, endpoint: str = config["apis"]["whg_endpoint"], search_domain: str = "/index", collection: str = ""):
        if not endpoint or not isinstance(endpoint, str):
            raise ValueError("Endpoint must be a non-empty string")
        self.collection = collection
        self.endpoint = endpoint.rstrip("/")
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
            logger.warning("place_type should be a string, defaulting to 'p' for place type.")
            place_type = "p"

        url = f"{self.endpoint}{self.search_domain}/?name={place_name}&ccodes={country_code}&fclass={place_type}&dataset={self.collection}"

        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error searching for '{place_name}': {str(e)}")
            return {"features": []}
        except ValueError as e:
            logger.error(f"Invalid JSON response for '{place_name}': {str(e)}")
            return {"features": []}


    def get_best_match(self, results: dict, place_name: str, fuzzy_threshold: float) -> tuple:

        logger.info(f"Finding best match for '{place_name}' in WHG results")

        try:
            if len(results["features"]) == 0:
                return (None, None)
            
            if len(results["features"]) == 1:
                coordinates = results["features"][0].get("geometry").get("coordinates")
                return coordinates[1], coordinates[0]

            for r in results["features"]:
                name = r.get("properties", {}).get("title", "")
                if not name:
                    continue
                
                ratio = fuzz.ratio(name.lower(), place_name.lower())
                logger.info(f"Comparing '{name}' with '{place_name}': {ratio}% similarity")
                if ratio >= fuzzy_threshold:
                    geometry = r.get("geometry", {})
                    if geometry.get("type") == "GeometryCollection":
                        logger.warning(f"Best match for '{place_name}' is a GeometryCollection. Taking the first valid point.")

                        coordinates = None
                        for geom in geometry.get("geometries", []):
                            if geom.get("type") == "Point":
                                coordinates = geom.get("coordinates")
                                break
                        if not coordinates:
                            logger.warning(f"No valid Point found in GeometryCollection for '{place_name}'.")
                            continue
                        
                    else:
                        coordinates = geometry.get("coordinates")
                    if coordinates and len(coordinates) == 2:
                        logger.info(f"Best match for '{place_name}': {name} ({ratio}%)")
                        return coordinates[1], coordinates[0] # Return (lat, lon). For some reason WHG returns (lon, lat) in coordinates

            return (None, None)
        
        except Exception as e:
            logger.error(f"Error processing results: {str(e)}")
            return (None, None)
        
class GeonamesQuery:
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
    def __init__(self, endpoint: str = config["apis"]["geonames_endpoint"]):
        self.endpoint = endpoint.rstrip('/')
        self.username = os.getenv('GEONAMES_USERNAME')
        if not self.username:
            raise ValueError("GEONAMES_USERNAME environment variable is required")

    @sleep_and_retry
    @limits(calls=30, period=1)  # Geonames allows 30 calls per second
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
            response = requests.get(
                f"{self.endpoint}/searchJSON",
                params=params
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error querying Geonames for '{place_name}': {str(e)}")
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
                    logger.info(f"Found match: '{name}' with similarity {ratio}%")

        if best_ratio >= fuzzy_threshold:
            return best_coords
        
        return (None, None)

class WikidataQuery:
    """
    A class to interact with the Wikidata MediaWiki API for geographic coordinates lookup.
    """

    def __init__(self, search_endpoint="https://www.wikidata.org/w/api.php", entitydata_endpoint="https://www.wikidata.org/wiki/Special:EntityData/"):
        self.search_endpoint = search_endpoint
        self.entitydata_endpoint = entitydata_endpoint

    @sleep_and_retry
    @limits(calls=30, period=1)  # Wikidata doesn't have a hard limit, but we set a conservative limit
    def places_by_name(self, place_name: str, country_code: str, place_type: Union[str, None] = None) -> list:
        """
        Search for entities using the Wikidata API.
        """

        params = {
            "action": "wbsearchentities",
            "search": place_name,
            "language": "en",
            "format": "json",
            "type": "item",
            "limit": 10
        }

        try:
            response = requests.get(self.search_endpoint, params=params, timeout=10)
            response.raise_for_status()
            search_results = response.json().get("search", [])
        except Exception as e:
            traceback_str = traceback.format_exc()
            logger.error(f"Error querying Wikidata search API for '{place_name}': {e} \n{traceback_str}")
            return []

        enriched_results = []

        for result in search_results:
            qid = result.get("id")
            label = result.get("label", "")

            try:
                data_url = f"{self.entitydata_endpoint}{qid}.json"
                entity_response = requests.get(data_url, timeout=10)
                entity_response.raise_for_status()
                entity_data = entity_response.json()["entities"][qid]
                claims = entity_data.get("claims", {})
            except Exception as e:
                logger.warning(f"Could not fetch entity data for {qid}: {e}")
                continue

            coords = self._extract_coordinates(claims)
            if coords is None:
                continue

            # Country filter
            if country_code and not self._match_country(claims, country_code):
                continue

            # Place type filter
            if place_type and not self._match_place_type(claims, place_type):
                continue

            enriched_results.append({
                "label": label,
                "qid": qid,
                "coordinates": coords
            })

        return enriched_results

    def get_best_match(self, results: dict, place_name: str, fuzzy_threshold: float) -> tuple:
        if not results:
            return (None, None)

        best_score = 0
        best_coords = None

        for result in results:
            label = result["label"]
            coords = result["coordinates"]
            score = max(fuzz.ratio(label.lower(), place_name.lower()), fuzz.partial_ratio(label.lower(), place_name.lower()))

            if score > best_score and score >= fuzzy_threshold:
                best_score = score
                best_coords = coords
                logger.info(f"Found Wikidata match: '{label}' with score {score}%")

        return best_coords if best_coords else (None, None)

    def _extract_coordinates(self, claims) -> tuple:
        try:
            coord_data = claims.get("P625", [])[0]["mainsnak"]["datavalue"]["value"]
            return (coord_data["latitude"], coord_data["longitude"])
        except Exception:
            return (None, None)

    def _match_country(self, claims, iso_code: str) -> bool:
        try:
            country_entity = claims.get("P17", [])[0]["mainsnak"]["datavalue"]["value"]["id"]
            country_data = requests.get(f"https://www.wikidata.org/wiki/Special:EntityData/{country_entity}.json").json()
            iso = country_data["entities"][country_entity]["claims"]["P297"][0]["mainsnak"]["datavalue"]["value"]
            return iso.upper() == iso_code.upper()
        except Exception:
            return False

    def _match_place_type(self, claims, expected_qid: str) -> bool:
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
    def __init__(self, services: list, places_map_json: str = "data/mappings/places_map.json",
                 threshold: float = 90):
        self.services = services
        self.places_map = self._load_places_map(places_map_json)
        self.threshold = threshold

    def _load_places_map(self, json_file: str) -> dict:
        try:
            with open(json_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading places map: {e}")
            raise ValueError(f"Could not load places map from {json_file}. Ensure the file exists and is valid JSON.")

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
                logger.info(f"Trying {service.__class__.__name__} for '{place_name}'")
                mapper = PlaceTypeMapper(self.places_map)
                service_key = service.__class__.__name__.lower().replace("query", "")

                resolved_type = None

                if place_type:
                    resolved_type = mapper.get_for_service(place_type, service_key)
                    if resolved_type is None and use_default_filter:
                        logger.warning(
                            f"Unrecognized place_type '{place_type}' for service '{service_key}', falling back to 'pueblo'."
                        )
                        resolved_type = mapper.get_for_service("pueblo", service_key)
                    elif resolved_type is None:
                        logger.info(
                            f"Skipping place_type filter for service '{service_key}' (unrecognized type: '{place_type}')."
                        )

                results = service.places_by_name(place_name, country_code, resolved_type)
                coords = service.get_best_match(results, place_name, fuzzy_threshold=self.threshold)
                if coords != (None, None):
                    logger.info(f"Resolved '{place_name}' via {service.__class__.__name__}: {coords}")
                    return coords
            except Exception as e:
                traceback_str = traceback.format_exc()
                logger.warning(f"{service.__class__.__name__} failed for '{place_name}': {e}\n{traceback_str}")
        logger.warning(f"Could not resolve '{place_name}' via any service.")
        return (None, None)

