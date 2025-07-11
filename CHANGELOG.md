# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.2.1] - 2025-07-10

### Added
- "inhabited places" place type mapping to places_map.json for better place type coverage

### Documentation
- Updated README to reflect new version output format and improved explanations
- Enhanced documentation clarity for historical geocoding use cases

---

## [v0.2.0] - 2025-07-10

### Added
- Enhanced PlaceResolver with flexible threshold for short place names
- Language support to BaseQuery and GeoNamesQuery classes
- `part_of` and `part_of_uri` fields to GeoNamesQuery results for hierarchical location data
- `pycountry` dependency for improved country code validation and name conversion
- Comprehensive validation for place_name and country_code parameters
- Enhanced WikidataQuery with country and administrative entity data retrieval capabilities
- Comprehensive changelog documentation

### Changed
- **BREAKING**: Moved BaseQuery class outside of resolver.py for better modularity
- **BREAKING**: Updated method signatures and return types to match base class interface
- **BREAKING**: Large refactor of core architecture and data structures
- Updated PlaceResolver to improve return types and handling of DataFrame outputs
- Refactored WHGQuery to return enhanced, structured results
- Improved TGNQuery SPARQL queries for better data retrieval
- Updated GeoNamesQuery to handle alternate names more effectively
- Enhanced TGNQuery methods for improved data retrieval and consistency
- Reorganized service classes for better code clarity and maintainability
- Updated library documentation to emphasize utility for historical geocoding

### Fixed
- WHGQuery country_code filtering now properly handled in post-processing
- TGNQuery and PlaceResolver now correctly return None for no matches found
- TGNQuery now uses consistent post-filtering method pattern
- Corrected GeoNames place type mappings for villages and cities
- Enhanced TGNQuery SPARQL query reliability
- Improved validation and error handling across all query classes
- WikidataQuery now properly matches BaseQuery abstract methods

### Tests
- Enhanced batch resolver tests for result validation and output formatting
- Updated test_whg_query to use London and validate coordinates structure
- Added Spanish language support tests for batch resolver functionality
- Corrected country code for Rome in TGNQuery tests
- Enhanced test coverage for new language support features
- Updated WikidataQuery tests for response validation

### Documentation
- Updated README to emphasize GeoResolver's utility for historical geocoding
- Improved method documentation and examples

### Internal
- Changed info logs to debug logs for default place_type handling
- Refactored BaseQuery class to use abstract methods for place queries
- Formatted method signatures for improved readability
- Code style improvements and consistency enhancements

---

## [v0.1.4] - 2025-06-30

Previous stable release. See git history for details of earlier versions.

[Unreleased]: https://github.com/jairomelo/georesolver/compare/v0.1.4...HEAD
[v0.1.4]: https://github.com/jairomelo/georesolver/releases/tag/v0.1.4
