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
from georesolver.utils.LoggerHandler import setup_logger

logger = setup_logger("getCoordinates")

config = configparser.ConfigParser()
config.read("conf/global.conf")

load_dotenv(config["default"]["env_file"])

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

    def get_best_match(self, results: dict, place_name: str, fuzzy_threshold: float = 90) -> tuple:
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

class HGISQuery:
    """
    A class to interact with the World Historical Gazetteer (WHG) API.

    This class provides methods to search and retrieve geographic coordinates for historical
    places using the WHG API. It supports filtering by country code and feature class,
    and includes functionality to find the best matching place from multiple results.

    Attributes:
        collection (str): The WHG collection to search in (default: 'lugares13k_rel')
        endpoint (str): The base URL for the WHG API
        search_domain (str): The API endpoint path for searches. Default is "/index"

    Example:
        >>> hgis = HGISQuery("https://whgazetteer.org/api")
        >>> results = hgis.places_by_name("Cuicatlán", ccode="MX", fclass="p")
        >>> coordinates = hgis.get_best_match(results, placetype="pueblo", ccode="MX")
    """
    def __init__(self, endpoint: str = config["apis"]["hgis_endpoint"], search_domain: str = "/index"):
        if not endpoint or not isinstance(endpoint, str):
            raise ValueError("Endpoint must be a non-empty string")
        self.collection = "lugares13k_rel"
        self.endpoint = endpoint.rstrip("/")
        self.search_domain = search_domain

    def places_by_name(self, place_name: str, ccode: Union[str, None] = None, fclass: str = 'p') -> dict:
        """
        Search for place using the World Historical Gazetteer API https://docs.whgazetteer.org/content/400-Technical.html#api
        
        Parameters:
            place_name (str): Any string with the name of the place. This keyword includes place names variants.
            ccode (str): ISO 3166-1 alpha-2 country code.
            fclass (str): Feature class according to Linked Places Format. Default is 'p' for place. Look at https://github.com/LinkedPasts/linked-places-format for more places classes.         
        """
        
        if not place_name or not isinstance(place_name, str):
            raise ValueError("place_name must be a non-empty string")
        if ccode and (not isinstance(ccode, str) or len(ccode) != 2):
            raise ValueError("ccode must be a valid 2-letter country code")
        
        
        url = f"{self.endpoint}{self.search_domain}/?name={place_name}&dataset={self.collection}&ccodes={ccode}&fclass={fclass}"
        
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


    def get_best_match(self, results: dict, placetype: Union[str, None] = None, ccode: Union[str, None] = None) -> tuple:

        try:
            if len(results["features"]) == 0:
                return (None, None)
            
            if len(results["features"]) == 1:
                coordinates = results["features"][0].get("geometry").get("coordinates")
                return coordinates[1], coordinates[0]

            for r in results["features"]:
                placetypes = r.get("properties", {}).get("placetypes", [])
                ccodes = r.get("properties", {}).get("ccodes", [])
                if placetype and ccode:
                    if placetype.capitalize() in placetypes and ccode in ccodes:
                        coordinates = r["geometry"]["coordinates"]
                        return coordinates[1], coordinates[0]

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

    def places_by_name(self, place_name: str, country_code: Union[str, None] = None, place_type: Union[str, None] = None) -> dict:
        """
        Search for places using the Geonames API.
        
        Parameters:
            place_name (str): Name of the place to search for
            country_code (str): Optional ISO 3166-1 alpha-2 country code
            place_type (str): Optional feature class (A: country, P: city/village, etc.).
                              Additional types can be added in the data/mappings/geonames_place_map.json file.
        """
        # Map common place types to Geonames feature classes
        place_type_map = json.load(open("data/mappings/geonames_place_map.json"))

        params = {
            'q': place_name,
            'username': self.username,
            'maxRows': 10,
            'type': 'json',
            'style': 'FULL'
        }
        
        if country_code:
            params['country'] = country_code
        
        if place_type and place_type.lower() in place_type_map:
            params['featureClass'] = place_type_map[place_type.lower()]

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

    def get_best_match(self, results: dict, place_name: str, fuzzy_threshold: float = 75) -> tuple:
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
    A class to interact with the Wikidata API for geographic coordinates lookup.
    
    This class provides methods to search and retrieve geographic coordinates for places
    using the Wikidata API. It supports filtering by country and place type.

    Attributes:
        endpoint (str): The base URL for the Wikidata API
    """
    def __init__(self, endpoint: str = config["apis"]["wikidata_endpoint"]):
        self.endpoint = endpoint

    def places_by_name(self, place_name: str, country_code: Union[str, None] = None, place_type: Union[str, None] = None) -> dict:
        """
        Search for places using the Wikidata API.
        
        Parameters:
            place_name (str): Name of the place to search for
            country_code (str): Optional ISO 3166-1 alpha-2 country code
            place_type (str): Optional type of place (e.g., 'pueblo', 'city', 'village', 'municipality')
        """
        # Map common place types to Wikidata Q-numbers
        place_type_map = json.load(open("data/mappings/wikidata_place_map.json"))

        place_type_id = place_type_map.get(place_type.lower()) if place_type else None
        
        query = f"""
        SELECT DISTINCT ?place ?placeLabel ?coordinates WHERE {{
          ?place rdfs:label ?placeLabel;
                 wdt:P625 ?coordinates.
          FILTER(REGEX(LCASE(?placeLabel), LCASE("{place_name}"), "i"))  # Changed to REGEX for partial matches
          FILTER(LANG(?placeLabel) IN ("es", "en"))  # Accept both Spanish and English labels
          {f'?place wdt:P17 ?country. ?country wdt:P297 "{country_code}".' if country_code else ''}
          {f'?place wdt:P31/wdt:P279* wd:{place_type_id}.' if place_type_id else ''}
        }}
        LIMIT 10
        """

        try:
            response = requests.get(
                self.endpoint,
                params={
                    'format': 'json',
                    'query': query
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error querying Wikidata for '{place_name}': {str(e)}")
            return {"results": {"bindings": []}}

    def get_best_match(self, results: dict, place_name: str, fuzzy_threshold: float = 75) -> tuple:
        """
        Get the best matching place from the results based on name similarity.
        
        Parameters:
            results (dict): Results from places_by_name query
            place_name (str): Original place name to match against
            fuzzy_threshold (float): Minimum similarity score (0-100) for a match
        
        Returns:
            tuple: (latitude, longitude) or (None, None) if no match found
        """
        if not results.get("results", {}).get("bindings"):
            return (None, None)

        bindings = results["results"]["bindings"]
        if len(bindings) == 1:
            coords = bindings[0].get("coordinates", {}).get("value", "")
            return self._parse_coordinates(coords)

        best_ratio = 0
        best_coords = None
        
        for binding in bindings:
            label = binding.get("placeLabel", {}).get("value", "")
            coords = binding.get("coordinates", {}).get("value", "")
            
            partial_ratio = fuzz.partial_ratio(place_name.lower(), label.lower())
            regular_ratio = fuzz.ratio(place_name.lower(), label.lower())
            ratio = max(partial_ratio, regular_ratio)
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_coords = coords
                logger.info(f"Found match: '{label}' with similarity {ratio}%")

        if best_ratio >= fuzzy_threshold and best_coords is not None:
            return self._parse_coordinates(best_coords)
        
        return (None, None)

    def _parse_coordinates(self, coord_string: str) -> tuple:
        """
        Parse Wikidata coordinate string into (latitude, longitude) tuple.
        """
        try:
            coord_string = coord_string.replace("Point(", "").replace(")", "")
            lon, lat = map(float, coord_string.split())
            return (lat, lon)
        except Exception as e:
            logger.error(f"Error parsing coordinates '{coord_string}': {str(e)}")
            return (None, None)
        
class PlaceResolver:
    """
    A unified resolver that queries multiple geolocation services in order
    and returns the first match with valid coordinates.
    """
    def __init__(self, services: list):
        self.services = services

    def resolve(self, place_name: str, country_code: Union[str, None] = None, place_type: Union[str, None] = None) -> tuple:
        """
        Try resolving the place coordinates using multiple sources.

        Args:
            place_name (str): The place name to search
            country_code (str): ISO country code (optional)
            place_type (str): Place type (optional)

        Returns:
            tuple: (lat, lon) or (None, None) if not found
        """
        for service in self.services:
            try:
                logger.info(f"Trying {service.__class__.__name__} for '{place_name}'")
                results = service.places_by_name(place_name, country_code, place_type)
                coords = service.get_best_match(results, place_name)
                if coords != (None, None):
                    logger.info(f"Resolved '{place_name}' via {service.__class__.__name__}: {coords}")
                    return coords
            except Exception as e:
                traceback_str = traceback.format_exc()
                logger.warning(f"{service.__class__.__name__} failed for '{place_name}': {e}\n{traceback_str}")
        logger.warning(f"Could not resolve '{place_name}' via any service.")
        return (None, None)


if __name__ == "__main__":
    # use example
    services = [
        TGNQuery("http://vocab.getty.edu/sparql"),
        HGISQuery("https://whgazetteer.org/api"),
        GeonamesQuery("http://api.geonames.org"),
        WikidataQuery("https://www.wikidata.org/w/api.php")
    ]
    
    resolver = PlaceResolver(services)
    place_name = "Cuicatlán"
    country_code = "MX"
    place_type = "pueblo"
    
    coordinates = resolver.resolve(place_name, country_code, place_type)
    print("Resolved coordinates:", coordinates)