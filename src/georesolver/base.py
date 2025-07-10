from abc import ABC, abstractmethod
from typing import Union, Optional, Dict, Any
from ratelimit import limits, sleep_and_retry
import requests
import requests_cache
from georesolver.utils.LoggerHandler import setup_logger

class BaseQuery(ABC):
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
    def _limited_get(self, 
                     url: str, 
                     params: Optional[Dict[str, Any]] = None) -> requests.Response:
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

    @abstractmethod
    def places_by_name(self, 
                       place_name: str, 
                       country_code: Optional[str], 
                       place_type: Optional[str] = None, 
                       lang: Optional[str] = None) -> Union[dict, list]:
        """
        Search for places by name. Must be implemented by subclasses.
        
        Parameters:
            place_name (str): Name of the place to search for
            country_code (Optional[str]): ISO 3166-1 alpha-2 country code
            place_type (Optional[str]): Optional place type filter
            lang (Optional[str]): Language code for place type

        Returns:
            Union[dict, list]: Search results in service-specific format
        """
        pass

    @abstractmethod
    def get_best_match(self, 
                       results: Union[dict, list], 
                       place_name: str, 
                       fuzzy_threshold: float, 
                       lang: Optional[str] = None) -> Union[dict, None]:
        """
        Get the best matching place from the results based on name similarity.
        
        Parameters:
            results (Union[dict, list]): Results from places_by_name query
            place_name (str): Original place name to match against
            fuzzy_threshold (float): Minimum similarity score (0-100) for a match
            lang (Optional[str]): Language code for place type
        
        Returns:
            dictionary: A dictionary containing 
                {
                "place": place_name, "standardize_label": str, "latitude": float, "longitude": float, "source": str, 
                "id": str, "uri": str, "country_code": str, "confidence": float, "threshold": fuzzy_threshold,
                "match_type": str
                }
        """
        pass