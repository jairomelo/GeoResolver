import traceback
from typing import Union, Optional, Dict, List
from SPARQLWrapper import SPARQLWrapper, JSON
from rapidfuzz import fuzz
import os
import json
from importlib.resources import files
import requests
import pandas as pd
import pycountry
from tqdm import tqdm
import ast
from dotenv import load_dotenv
from ratelimit import limits, sleep_and_retry

from georesolver.utils.LoggerHandler import setup_logger
from georesolver.base import BaseQuery

load_dotenv(".env")

TGN_ENDPOINT = "http://vocab.getty.edu/sparql"
WHG_ENDPOINT = "https://whgazetteer.org/api"
GEONAMES_ENDPOINT = "http://api.geonames.org"
WIKIDATA_ENDPOINT = "https://www.wikidata.org/w/api.php"
ENTITYDATA_ENDPOINT = "https://www.wikidata.org/wiki/Special:EntityData/"


class PlaceTypeMapper:
    def __init__(self, mapping: dict):
        self.mapping = mapping

    def get_for_service(self, place_type, service) -> Union[str, None]:
        try:
            return self.mapping[place_type.lower()][service]
        except KeyError:
            return None


class GeoNamesQuery(BaseQuery):
    """
    A class to interact with the GeoNames API.

    This class provides methods to search and retrieve geographic coordinates for places
    using the GeoNames API. It supports filtering by country and feature class.

    Attributes:
        endpoint (str): The base URL for the GeoNames API
        username (str): GeoNames API username for authentication

    Example:
        >>> geonames = GeoNamesQuery("http://api.geonames.org", username="your_username")
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
            raise ValueError("GeoNames username must be provided either as an argument or via the GEONAMES_USERNAME environment variable.")

    def places_by_name(self, place_name: str, country_code: Optional[str], place_type: Optional[str] = None, lang: Optional[str] = None) -> dict:
        """
        Search for places using the GeoNames API.
        
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
            self.logger.error(f"Error querying GeoNames for '{place_name}': {str(e)}")
            return {"geonames": []}
        
    def _post_filtering(
        self,
        results: dict,
        place_name: str,
        fuzzy_threshold: float,
        confidence: float,
        lang: Optional[str] = "en") -> dict:
        """
        Returns the dictionary customized to the GeoNames API results.
        """

        standardize_label = ""

        if lang:
            self.logger.info(f"Post-filtering GeoNames results for '{place_name}' with language '{lang}'")

            standardize_label = next((name for name in results.get("alternateNames", []) if name["lang"] == lang), {}).get("name", "")

            if not standardize_label:
                standardize_label = results["toponymName"]

        return {
                "place": place_name,
                "standardize_label": standardize_label,
                "language": lang,
                "latitude": float(results["lat"]),
                "longitude": float(results["lng"]),
                "source": "GeoNames",
                "id": results["geonameId"],
                "uri": f"http://sws.geonames.org/{results['geonameId']}/",
                "country_code": results.get("countryCode", ""),
                "part_of": "",
                "part_of_uri": "",
                "confidence": confidence,
                "threshold": fuzzy_threshold,
                "match_type": "exact" if confidence == 100 else "fuzzy"
            }
        

    def get_best_match(self, results: Union[dict, list], place_name: str, fuzzy_threshold: float, lang: Optional[str] = None) -> Union[dict, None]:
        """
        Get the best matching place from the results based on name similarity.
        
        Parameters:
            results (Union[dict, list]): Results from places_by_name query
            place_name (str): Original place name to match against
            fuzzy_threshold (float): Minimum similarity score (0-100) for a match
        
        Returns:
            dictionary: A dictionary containing {
            "place": str, "standardize_label": str, "latitude": float, "longitude": float, "source": "GeoNames", 
            "id": str, "uri": str, "country_code": str, "confidence": float, "threshold": fuzzy_threshold,
            "match_type": str
            }
        """
        if not isinstance(results, dict) or not results.get("geonames"):
            return None

        geonames = results["geonames"]
        if len(geonames) == 1:
            result = geonames[0]
            return self._post_filtering(result, place_name, fuzzy_threshold, 100, lang)

        best_ratio = 0
        best_coords = None
        
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
                    best_coords = self._post_filtering(place, place_name, fuzzy_threshold, ratio, lang)
                    self.logger.info(f"Found match: '{name}' with similarity {ratio}%")

        if best_ratio >= fuzzy_threshold:
            return best_coords
        
        return None

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
    def __init__(self, 
                 search_domain: str = "index", 
                 dataset: str = ""):
        super().__init__(base_url=WHG_ENDPOINT)
        self.dataset = dataset
        self.search_domain = search_domain

    @sleep_and_retry
    @limits(calls=5, period=1)  # There's no official rate limit for WHG, but we set a conservative limit
    def places_by_name(self, 
                       place_name: str, 
                       country_code: Optional[str], 
                       place_type: Optional[str] = "p",
                       lang: Optional[str] = None) -> Union[dict, list]:
        """
        Search for place using the World Historical Gazetteer API https://docs.whgazetteer.org/content/400-Technical.html#api
        
        Parameters:
            place_name (str): Any string with the name of the place. This keyword includes place names variants.
            country_code (str): ISO 3166-1 alpha-2 country code.
            place_type (str): Feature class according to Linked Places Format. Default is 'p' for place. Look at https://github.com/LinkedPasts/linked-places-format for more places classes.
        """
        
        if not place_type:
            self.logger.debug("No place_type provided, defaulting to 'p' for place type.")
            place_type = "p"

        # Build URL with optional country code
        url = f"{self.base_url}/{self.search_domain}/?name={place_name}&fclass={place_type}&dataset={self.dataset}"
        if country_code:
            url += f"&ccodes={country_code}"

        try:
            response = self._limited_get(url)
            results = response.json()
            if country_code:
                return self._post_filtering_search(results, country_code=country_code)
            return results
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error searching for '{place_name}': {str(e)}")
            return {"features": []}
        except ValueError as e:
            self.logger.error(f"Invalid JSON response for '{place_name}': {str(e)}")
            return {"features": []}


    def get_best_match(self, 
                       results: Union[dict, list], 
                       place_name: str, 
                       fuzzy_threshold: float,
                       lang: Optional[str] = None) -> Union[dict, None]:

        self.logger.info(f"Finding best match for '{place_name}' in WHG results")
        self.logger.debug(f"Results: {results}")

        try:
            features = results.get("features", []) if isinstance(results, dict) else []
            if not features:
                return None

            for r in features:
                name = r.get("properties", {}).get("title", "")
                if not name:
                    continue
                
                ratio = fuzz.ratio(name.lower(), place_name.lower())
                self.logger.info(f"Comparing '{name}' with '{place_name}': {ratio}% similarity")
                if ratio >= fuzzy_threshold:
                    return self._post_filtering(
                        results=r,
                        place_name=place_name,
                        fuzzy_threshold=fuzzy_threshold,
                        confidence=ratio,
                        lang=lang
                    )

            return None
        
        except Exception as e:
            self.logger.error(f"Error processing results: {str(e)}")
            return None

    def _post_filtering_search(
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

    def get_coordinates_lod_json(self, geometry: dict, place_name: str) -> Union[list, None]:
        """
        Extracts geographic coordinates from the WHG API response.
        """

        if geometry.get("type") == "GeometryCollection":
            self.logger.warning(f"Best match for '{place_name}' is a GeometryCollection. Taking the first valid point.")

            coordinates = None
            for geom in geometry.get("geometries", []):
                if geom.get("type") == "Point":
                    coordinates = geom.get("coordinates")
                    break
            if not coordinates:
                self.logger.warning(f"No valid Point found in GeometryCollection for '{place_name}'.")
                return None
        else:
            return geometry.get("coordinates", [])

    def _post_filtering(
            self,
            results: dict,
            place_name: str,
            fuzzy_threshold: float,
            confidence: float,
            lang: Optional[str] = "en") -> Union[dict, None]:
        """
        Returns the dictionary customized to the WHG API results.
        """
        self.logger.debug(f"Post-filtering WHG results for '{place_name}' with language '{lang}'\n{results}")

        geometry = results.get("geometry", {})
        coordinates = self.get_coordinates_lod_json(geometry, place_name)
        if coordinates and len(coordinates) == 2:
            name = results.get("properties", {}).get("title", "")
            self.logger.info(f"Best match for '{place_name}': {name} ({confidence}%)")
            return {
                "place": place_name,
                "standardize_label": name,
                "language": lang,
                "latitude": float(coordinates[1]),
                "longitude": float(coordinates[0]),
                "source": "WHG",
                "id": results.get("properties", {}).get("index_id", ""),
                "uri": f"https://whgazetteer.org/places/{results.get('properties', {}).get('index_id', '')}/portal/",
                "country_code": results.get("properties", {}).get("ccodes", [])[0] if results.get("properties", {}).get("ccodes") else "",
                "part_of": "",
                "part_of_uri": "",
                "confidence": confidence,
                "threshold": fuzzy_threshold,
                "match_type": "exact" if confidence == 100 else "fuzzy"
            }

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
    def __init__(self):
        super().__init__(base_url=TGN_ENDPOINT)
        self.sparql = SPARQLWrapper(self.base_url)
        self.sparql.setReturnFormat(JSON)

    @sleep_and_retry
    @limits(calls=10, period=1)
    def places_by_name(self, place_name: str, country_code: Optional[str], place_type: Optional[str] = None, lang: Optional[str] = "en") -> Union[dict, list]:
        """
        Search for places using the TGN SPARQL endpoint.
        
        Parameters:
            place_name (str): Name of the place to search for
            country_code (str): Country code or name
            place_type (str): Optional type of place (e.g., 'ciudad', 'pueblo')
        """

        country_name = ""

        if country_code:
            country = pycountry.countries.get(alpha_2=country_code)
            if country:
                country_name = country.name
            else:
                country_name = country_code

        type_filter = f'?p gvp:placeType [rdfs:label "{place_type}"@{lang}].' if place_type else ''

        query = f"""
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX luc: <http://www.ontotext.com/owlim/lucene#>
            PREFIX gvp: <http://vocab.getty.edu/ontology#>
            PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>
            PREFIX tgn: <http://vocab.getty.edu/tgn/>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

            SELECT DISTINCT ?p ?pLab ?context WHERE {{
                ?p skos:inScheme tgn:;
                    luc:term "{place_name}";
                    gvp:prefLabelGVP [xl:literalForm ?pLab];
                    gvp:parentString ?context.

                {type_filter}
                
                FILTER(CONTAINS(?context, "{country_name}"))
            }}
        """
        
        self.logger.debug(f"Executing SPARQL {query} for TGN with place name '{place_name}' and country code '{country_code}'")

        try:
            self.sparql.setQuery(query)
            results = self.sparql.query().convert()
            self.logger.debug(f"SPARQL query results for '{place_name}': {results}")

            if isinstance(results, dict) and "results" in results and "bindings" in results["results"]:
                return results["results"]["bindings"]
            else:
                self.logger.error(f"Unexpected SPARQL result format for '{place_name}': {results}")
                return []
        except Exception as e:
            self.logger.error(f"Error querying TGN for '{place_name}': {str(e)}")
            return []

    def get_coordinates_lod_json(self, data: dict) -> dict:
        
        for item in data.get("identified_by", []):
            if item.get("type") == "crm:E47_Spatial_Coordinates":
                coords = ast.literal_eval(item.get("value"))
                if isinstance(coords, list) and len(coords) == 2:
                    lon, lat = coords
                    return {"latitude": lat, "longitude": lon}
        return {"latitude": None, "longitude": None}
        
    def _post_filtering(
        self,
        tgn_uri: str,
        place_name: str,
        fuzzy_threshold: float,
        confidence: float,
        lang: Optional[str] = "en") -> dict:

        json_url = tgn_uri + ".json"
        try:
            response = self._limited_get(json_url)
            results = response.json()
        except Exception as e:
            self.logger.error(f"Error fetching TGN data for {place_name}: {e}")
            return {}

        coordinates = self.get_coordinates_lod_json(results)
        if coordinates["latitude"] is None or coordinates["longitude"] is None:
            self.logger.warning(f"No valid coordinates found for {place_name} in TGN results.")


        return {
                "place": place_name,
                "standardize_label": results.get("_label", ""),
                "language": lang,
                "latitude": float(coordinates["latitude"]),
                "longitude": float(coordinates["longitude"]),
                "source": "TGN",
                "id": results.get("id", ""),
                "uri": results.get("id", ""),
                "country_code": "",
                "part_of": results.get("part_of", [{}])[0].get("_label", ""),
                "part_of_uri": results.get("part_of", [{}])[0].get("id", ""),
                "confidence": confidence,
                "threshold": fuzzy_threshold,
                "match_type": "exact" if confidence == 100 else "fuzzy"
            }

    def get_best_match(self, results: Union[dict, list], place_name: str, fuzzy_threshold: float, lang: Optional[str] = "en") -> Union[dict, None]:
        if not results:
            self.logger.debug(f"No results found for '{place_name}' in TGN.")
            return None

        self.logger.debug(f"Finding best match for '{place_name}' in TGN {results}")

        if len(results) == 1:
            return self._post_filtering(results[0].get("p", {}).get("value", ""),
                                        place_name=place_name,
                                        fuzzy_threshold=fuzzy_threshold,
                                        confidence=100,
                                        lang=lang)

        for r in results:
            label = r.get("pLab", {}).get("value", "")
            uri = r.get("p", {}).get("value", "")
            ratio = fuzz.ratio(label.lower(), place_name.lower())
            self.logger.info(f"Comparing '{label}' with '{place_name} {uri}': {ratio}% similarity")
            if ratio >= fuzzy_threshold:
                self.logger.info(f"Best match for '{place_name}': {label} ({ratio}%)")
                return self._post_filtering(uri,
                                            place_name=place_name,
                                            fuzzy_threshold=fuzzy_threshold,
                                            confidence=ratio,
                                            lang=lang)

        self.logger.debug(f"No suitable match found for '{place_name}' in TGN.")
        return None


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
    def places_by_name(self, 
                       place_name: str, 
                       country_code: Optional[str], 
                       place_type: Optional[str] = None,
                       lang: Optional[str] = "en") -> Union[dict, list]:
        
        params = {
            "action": "wbsearchentities",
            "search": place_name,
            "language": lang,
            "format": "json",
            "type": "item",
            "limit": 10
        }

        try:
            response = self._limited_get(self.search_endpoint, params=params)
            search_results = response.json().get("search", [])
            self.logger.debug(f"Wikidata search results for '{place_name}': {search_results}")
        except Exception as e:
            self.logger.error(f"Error querying Wikidata for '{place_name}': {e}")
            return []

        if not search_results:
            return []

        qids = [result.get("id") for result in search_results if result.get("id")]
        self.logger.debug(f"Found {len(qids)} QIDs for '{place_name}': {qids}")
        if not qids:
            return []

        # Batch fetch entity data for all QIDs
        entities_data = self._batch_fetch_entities(qids)
        
        # Extract all country QIDs and administrative entity QIDs to batch fetch them too
        country_qids = set()
        admin_qids = set()
        for qid in entities_data:
            claims = entities_data[qid].get("claims", {})
            try:
                country_qid = claims.get("P17", [])[0]["mainsnak"]["datavalue"]["value"]["id"]
                country_qids.add(country_qid)
            except (IndexError, KeyError):
                pass
            try:
                admin_qid = claims.get("P131", [])[0]["mainsnak"]["datavalue"]["value"]["id"]
                admin_qids.add(admin_qid)
            except (IndexError, KeyError):
                pass
        
        # Batch fetch country and administrative entity data
        country_data = {}
        admin_data = {}
        if country_qids:
            country_data = self._batch_fetch_entities(list(country_qids))
        if admin_qids:
            admin_data = self._batch_fetch_entities(list(admin_qids))
           
        enriched_results = []
        for result in search_results:
            qid = result.get("id")
            label = result.get("label", "")
            
            if qid not in entities_data:
                continue
                
            entity_data = entities_data[qid]
            claims = entity_data.get("claims", {})
            
            coords = self._extract_coordinates(claims)
            if not coords or coords == (None, None):
                continue

            # Get country info for this place
            place_country_qid, place_country_iso = self._get_place_country_info(claims, country_data)

            # Get administrative entity info for this place
            admin_qid, admin_label = self._get_place_admin_info(claims, admin_data, lang)

            if country_code and not self._match_country_optimized(place_country_iso, country_code):
                continue

            if place_type and not self._match_place_type(claims, place_type):
                continue

            # Store all needed data for post-filtering
            enriched_results.append({
                "label": label,
                "qid": qid,
                "coordinates": coords,
                "entity_data": entity_data,
                "claims": claims,
                "country_qid": place_country_qid,
                "country_iso": place_country_iso,
                "admin_qid": admin_qid,
                "admin_label": admin_label
            })

        return enriched_results

    def _batch_fetch_entities(self, qids: List[str]) -> Dict[str, dict]:
        """
        Batch fetch entity data for multiple QIDs using wbgetentities API.
        This significantly reduces the number of HTTP requests compared to individual fetches.
        """
        entities_data = {}
        
        # Process QIDs in chunks of 50 (Wikidata API limit)
        chunk_size = 50
        for i in range(0, len(qids), chunk_size):
            chunk = qids[i:i + chunk_size]
            
            params = {
                "action": "wbgetentities",
                "ids": "|".join(chunk),
                "format": "json",
                "props": "labels|claims"  # Only fetch what we need
            }
            
            try:
                response = self._limited_get(self.search_endpoint, params=params)
                result = response.json()
                
                if "entities" in result:
                    entities_data.update(result["entities"])
                    
            except Exception as e:
                self.logger.warning(f"Failed to batch fetch entities {chunk}: {e}")
                # Fallback to individual fetching for this chunk
                for qid in chunk:
                    entity_data = self._fetch_entity_data(qid)
                    if entity_data:
                        entities_data[qid] = entity_data
        
        return entities_data

    def _get_place_country_info(self, claims: dict, country_data: Dict[str, dict]) -> tuple:
        """
        Extract country QID and ISO code for a place using pre-fetched country data.
        Returns (country_qid, country_iso_code)
        """
        try:
            country_qid = claims.get("P17", [])[0]["mainsnak"]["datavalue"]["value"]["id"]
            if country_qid in country_data:
                country_claims = country_data[country_qid].get("claims", {})
                iso_code = country_claims.get("P297", [{}])[0].get("mainsnak", {}).get("datavalue", {}).get("value", "")
                return country_qid, iso_code.upper() if iso_code else ""
            return country_qid, ""
        except (IndexError, KeyError):
            return "", ""

    def _get_place_admin_info(self, claims: dict, admin_data: Dict[str, dict], lang: Optional[str]) -> tuple:
        """
        Extract administrative entity QID and label for a place using pre-fetched admin data.
        Returns (admin_qid, admin_label)
        """
        try:
            admin_qid = claims.get("P131", [])[0]["mainsnak"]["datavalue"]["value"]["id"]
            if admin_qid in admin_data and lang:
                admin_labels = admin_data[admin_qid].get("labels", {})
                admin_label = admin_labels.get(lang, {}).get("value", "")
                return admin_qid, admin_label
            return admin_qid, ""
        except (IndexError, KeyError):
            return "", ""

    def _match_country_optimized(self, place_country_iso: str, target_country_code: str) -> bool:
        """
        Optimized country matching using pre-extracted ISO codes.
        """
        if not place_country_iso or not target_country_code:
            return False
        return place_country_iso.upper() == target_country_code.upper()

    def _fetch_entity_data(self, qid: str) -> dict:
        try:
            url = f"{self.entitydata_endpoint}{qid}.json"
            response = self._limited_get(url)
            return response.json()["entities"][qid]
        except Exception as e:
            self.logger.warning(f"Failed to fetch entity data for {qid}: {e}")
            return {}

    def get_best_match(self, 
                       results: Union[dict, list], 
                       place_name: str, 
                       fuzzy_threshold: float,
                       lang: Optional[str] = None) -> Union[dict, None]:
        if not results:
            return None

        best_score = 0
        best_result = None

        for result in results:
            label = result["label"]
            score = max(fuzz.ratio(label.lower(), place_name.lower()),
                        fuzz.partial_ratio(label.lower(), place_name.lower()))

            if score > best_score and score >= fuzzy_threshold:
                best_score = score
                best_result = result
                self.logger.info(f"Wikidata match: '{label}' → {score}%")

        if best_result:
            return self._post_filtering(
                results=best_result,
                place_name=place_name,
                fuzzy_threshold=fuzzy_threshold,
                confidence=best_score,
                lang=lang
            )
        
        return None

    def _post_filtering(self,
                       results: dict,
                       place_name: str,
                       fuzzy_threshold: float,
                       confidence: float,
                       lang: Optional[str] = "en") -> dict:
        """
        Returns the dictionary customized to the Wikidata API results.
        """
        qid = results.get("qid", "")
        label = results.get("label", "")
        coords = results.get("coordinates", (None, None))
        entity_data = results.get("entity_data", {})
        claims = results.get("claims", {})
        
        # Use pre-extracted country and administrative entity information
        country_code = results.get("country_iso", "")
        admin_qid = results.get("admin_qid", "")
        admin_label = results.get("admin_label", "")
        
        # Build part_of_uri if we have admin_qid
        part_of_uri = f"https://www.wikidata.org/entity/{admin_qid}" if admin_qid else ""

        return {
            "place": place_name,
            "standardize_label": label,
            "language": lang,
            "latitude": float(coords[0]) if coords[0] is not None else None,
            "longitude": float(coords[1]) if coords[1] is not None else None,
            "source": "Wikidata",
            "id": qid,
            "uri": f"https://www.wikidata.org/entity/{qid}",
            "country_code": country_code,
            "part_of": admin_label,
            "part_of_uri": part_of_uri,
            "confidence": confidence,
            "threshold": fuzzy_threshold,
            "match_type": "exact" if confidence == 100 else "fuzzy"
        }

    def _extract_coordinates(self, claims: dict) -> tuple:
        try:
            coord_data = claims.get("P625", [])[0]["mainsnak"]["datavalue"]["value"]
            return coord_data["latitude"], coord_data["longitude"]
        except Exception:
            return (None, None)

    def _match_country(self, claims: dict, iso_code: str) -> bool:
        # DEPRECATED: Use _match_country_optimized instead
        # This method is kept for backward compatibility but should not be used
        # in the optimized workflow as it makes individual HTTP requests
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

    Args:
            services (Optional[List[BaseQuery]]): List of geolocation service instances to use.
            places_map_json (Union[str, None]): Path to a custom places mapping JSON file.
            lang (Optional[str]): Language code for place type filtering.
            threshold (float): Fuzzy matching threshold for place name similarity.
            flexible_threshold (bool): If True, use a lower threshold for shorter place names.
            flexible_threshold_value (float): The threshold value to use when flexible_threshold is True.
                                                If no value is provided, it defaults to 70.
            verbose (bool): If True, enable verbose logging.

    """
    def __init__(self, 
                 services: Optional[List[BaseQuery]] = None, 
                 places_map_json: Union[str, None] = None, 
                 lang: Optional[str] = None, 
                 threshold: float = 90,
                 flexible_threshold: bool = False,
                 flexible_threshold_value: float = 70, 
                 verbose: bool = False):

        self.logger = setup_logger(self.__class__.__name__, verbose)
        
        if services is None or not isinstance(services, list) or len(services) == 0:
            services = [
                GeoNamesQuery(),
                WHGQuery(),
                TGNQuery(),
                WikidataQuery()
            ]

        self.services = services
        self.places_map = self._load_places_map(places_map_json)
        self.lang = lang if lang else "en"

        if not (0 <= threshold <= 100):
            raise ValueError("threshold must be between 0 and 100")
        
        self.threshold = threshold

        self.flexible_threshold = flexible_threshold
        if self.flexible_threshold:
            if not (0 <= flexible_threshold_value <= 100):
                raise ValueError("flexible_threshold_value must be between 0 and 100")
            
            self.flexible_threshold_value = flexible_threshold_value
        
        

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


    def resolve(self, 
                place_name: str, 
                country_code: Union[str, None] = None, 
                place_type: Union[str, None] = None,
               use_default_filter: bool = False) -> Union[dict, None]:
        """
        Try resolving the place coordinates using multiple sources.

        Args:
            place_name (str): The place name to search
            country_code (str): ISO 3166-1 alpha-2 country code (optional)
            place_type (str): Place type (optional)
            use_default_filter (bool): If True, apply a default filter as fallback in case the place_type is not found.
                                        If no place_type is provided, no filtering will be applied.

        Returns:
            tuple: (lat, lon) or (None, None) if not found
        """

        if not place_name or not isinstance(place_name, str):
            self.logger.error("place_name must be a non-empty string")
            return None

        place_name = place_name.strip()

        try:
            if pycountry.countries.get(alpha_2=country_code) is None and country_code is not None:
                self.logger.warning(f"Invalid country code: {country_code}\nLook at the correct ISO 3166-1 alpha-2 country codes at https://www.iso.org/iso-3166-country-codes.html")
                country_code = None
        except Exception as e:
            self.logger.info(f"Error occurred while validating country code: {e}")

        if self.flexible_threshold and len(place_name) < 5:
            self.logger.warning(
                f"Using flexible threshold for short place name: '{place_name}'"
            )
            threshold = self.flexible_threshold_value
        else:
            threshold = self.threshold

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
                        self.logger.debug(
                            f"Skipping place_type filter for service '{service_key}' (unrecognized type: '{place_type}')."
                        )

                results = service.places_by_name(place_name, country_code, resolved_type, lang=self.lang)
                result = service.get_best_match(results, place_name, fuzzy_threshold=threshold, lang=self.lang)
                if result:
                    self.logger.info(f"Resolved '{place_name}' via {service.__class__.__name__}: {result}")
                    return result
            except Exception as e:
                traceback_str = traceback.format_exc()
                self.logger.warning(f"{service.__class__.__name__} failed for '{place_name}': {e}\n{traceback_str}")
        self.logger.warning(f"Could not resolve '{place_name}' via any service.")
        return None

    def resolve_batch(
            self,
            df: pd.DataFrame,
            place_column: str = "place_name",
            country_column: Union[str, None] = None,
            place_type_column: Union[str, None] = None,
            use_default_filter: bool = False,
            return_df: bool = True,
            show_progress: bool = True
    ) -> Union[pd.DataFrame, List[dict]]:
        """
        Resolve coordinates for a batch of places from a DataFrame.
        
        This method optimizes API calls by processing only unique combinations of 
        place_name, country_code, and place_type, then mapping results back to the original DataFrame.

        Args:
            df (pd.DataFrame): Input DataFrame with place names and optional country/type columns.
            place_column (str): Column name for place names.
            country_column (str): Column name for country codes (optional).
            place_type_column (str): Column name for place types (optional).
            use_default_filter (bool): If True, apply a default filter as fallback.
            return_df (bool): If True, return a DataFrame with separate columns for each attribute. Otherwise, return a list of dictionaries.
            show_progress (bool): If True, show a progress bar during processing.

        Raises:
            ValueError: If the input DataFrame is not valid or required columns are missing.

        Returns:
            pd.DataFrame: A DataFrame with resolved coordinates and metadata.
            List[dict]: A list of dictionaries with resolved coordinates and metadata if return_df is False.
        """

        if not isinstance(df, pd.DataFrame):
            raise ValueError("Input must be a pandas DataFrame")

        if place_column not in df.columns:
            raise ValueError(f"Column '{place_column}' not found in DataFrame")

        if country_column and country_column not in df.columns:
            raise ValueError(f"Column '{country_column}' not found in DataFrame")

        if place_type_column and place_type_column not in df.columns:
            raise ValueError(f"Column '{place_type_column}' not found in DataFrame")
        
        # Create a copy of the input DataFrame to avoid modifying the original
        df_copy = df.copy()
        
        # Handle NaN and empty values in place_column
        df_copy[place_column] = df_copy[place_column].fillna("").astype(str)
        
        # Filter out rows with empty place names
        valid_mask = df_copy[place_column].str.strip() != ""
        df_valid = df_copy[valid_mask].copy()
        
        if df_valid.empty:
            self.logger.warning("No valid place names found in the DataFrame")
            if return_df:
                # Return empty results DataFrame with proper structure
                empty_results = pd.DataFrame({
                    "place": None, "standardize_label": None, "language": None,
                    "latitude": None, "longitude": None, "source": None,
                    "id": None, "uri": None, "country_code": None,
                    "part_of": None, "part_of_uri": None, "confidence": None,
                    "threshold": None, "match_type": None
                }, index=df.index)
                return empty_results
            else:
                # Return list of None values, properly typed for the Union return type
                return [None] * len(df)  # type: ignore
        
        # Create unique combinations for processing
        lookup_columns = [place_column]
        if country_column:
            df_valid[country_column] = df_valid[country_column].fillna("")
            lookup_columns.append(country_column)
        if place_type_column:
            df_valid[place_type_column] = df_valid[place_type_column].fillna("")
            lookup_columns.append(place_type_column)
        
        # Get unique combinations
        unique_combinations = df_valid[lookup_columns].drop_duplicates().reset_index(drop=True)
        
        # Log optimization info
        original_count = len(df_valid)
        unique_count = len(unique_combinations)
        reduction_pct = ((original_count - unique_count) / original_count * 100) if original_count > 0 else 0
        self.logger.info(f"Processing {unique_count} unique combinations instead of {original_count} rows "
                        f"({reduction_pct:.1f}% reduction in API calls)")
        
        # Process unique combinations
        if show_progress:
            unique_iter = tqdm(unique_combinations.iterrows(), 
                             total=len(unique_combinations),
                             desc="Resolving unique places")
        else:
            unique_iter = unique_combinations.iterrows()

        # Store results for unique combinations
        unique_results = {}
        
        for _, row in unique_iter:
            place_name = row[place_column].strip()
            country_code = row.get(country_column, None) if country_column else None
            place_type = row.get(place_type_column, None) if place_type_column else None
            
            # Convert empty strings to None for consistency
            country_code = country_code if country_code and country_code.strip() else None
            place_type = place_type if place_type and place_type.strip() else None
            
            # Create a key for the combination
            key = (place_name, country_code or "", place_type or "")
            
            result = self.resolve(
                place_name=place_name,
                country_code=country_code,
                place_type=place_type,
                use_default_filter=use_default_filter
            )
            
            unique_results[key] = result
        
        # Map results back to original DataFrame
        results = []
        for idx in df.index:
            if idx in df_valid.index:
                row = df_valid.loc[idx]
                place_name = row[place_column].strip()
                country_code = row.get(country_column, None) if country_column else None
                place_type = row.get(place_type_column, None) if place_type_column else None
                
                # Convert empty strings to None for key matching
                country_code = country_code if country_code and country_code.strip() else None
                place_type = place_type if place_type and place_type.strip() else None
                
                key = (place_name, country_code or "", place_type or "")
                result = unique_results.get(key)
            else:
                # For rows with invalid place names, return None
                result = None
            
            results.append(result)

        if return_df:
            # Fill None results with a default structure before creating DataFrame
            default_result = {
                "place": None, "standardize_label": None, "language": None, 
                "latitude": None, "longitude": None, "source": None, 
                "id": None, "uri": None, "country_code": None, 
                "part_of": None, "part_of_uri": None, "confidence": None, 
                "threshold": None, "match_type": None
            }
            
            # Expand dictionary results into separate columns
            expanded_results = []
            for result in results:
                if result is None:
                    expanded_results.append(default_result)
                else:
                    expanded_results.append(result)
            
            results_df = pd.DataFrame(expanded_results, index=df.index)
            return results_df
        else:
            return results