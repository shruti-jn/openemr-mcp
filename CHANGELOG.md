# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-05-01

### Added

- MCP server with 17 clinical tools for OpenEMR integration
- Patient search, appointments, and medication lookup
- Drug interaction checking via RxNorm
- FDA adverse event and drug label queries via openFDA
- Symptom lookup via Infermedica
- Drug safety flag CRUD operations
- Lab trends, vital trends, and questionnaire trends
- Health trajectory aggregation
- Visit preparation briefs
- Multi-source data layer: mock, MySQL, and FHIR R4 API
- OAuth2 token management with thread-safe caching
- Pydantic response schemas for all tools
- Evaluation suite with 62 test cases
- Mock data for zero-dependency local development

### Fixed

- Use `.get()` for `term` key in openFDA interaction response
- Update GitHub URLs to `shruti-jn`

### Changed

- Standardize auth config, add strict error handling and observability

[0.1.0]: https://github.com/shruti-jn/openemr-mcp/releases/tag/v0.1.0
