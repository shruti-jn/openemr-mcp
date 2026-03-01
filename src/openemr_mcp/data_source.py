"""Simplified data source resolver for the standalone MCP server.

Unlike the FastAPI app, there's no per-request context var — just the global env setting.
"""
import os
from typing import Optional


def get_effective_data_source() -> str:
    """Return the active data source: 'mock' | 'db' | 'api'."""
    return os.environ.get("OPENEMR_DATA_SOURCE", "mock").strip().lower()


def get_http_client():
    """Return an OpenEMR FHIR HTTP client configured from env vars."""
    from openemr_mcp.config import settings
    from openemr_mcp.auth import OAuth2TokenManager

    class _OpenEMRClient:
        """Minimal FHIR + REST client for OpenEMR, matching the interface used by repositories."""

        def __init__(self):
            self._token_manager = OAuth2TokenManager(settings)

        def _get_headers(self) -> dict:
            token = self._token_manager.get_token()
            return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        def get_fhir(self, resource_path: str, params: Optional[dict] = None) -> dict:
            """GET /apis/default/fhir/{resource_path}"""
            import httpx
            from openemr_mcp.services.safety import sanitize_drug_name
            base = settings.openemr_api_base_url.rstrip("/")
            url = f"{base}/fhir/{resource_path}"
            headers = self._get_headers()
            try:
                r = httpx.get(url, params=params, headers=headers, timeout=15.0)
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    return {}
                from openemr_mcp.repositories._errors import ToolError
                raise ToolError(f"FHIR API error: {exc.response.status_code}") from exc
            except Exception as exc:
                from openemr_mcp.repositories._errors import ToolError
                raise ToolError(f"FHIR API unreachable: {exc}") from exc

        def get_rest(self, path: str, params: Optional[dict] = None) -> dict:
            """GET /apis/default/{path}"""
            import httpx
            base = settings.openemr_api_base_url.rstrip("/")
            url = f"{base}/{path}"
            headers = self._get_headers()
            try:
                r = httpx.get(url, params=params, headers=headers, timeout=15.0)
                r.raise_for_status()
                return r.json()
            except Exception as exc:
                from openemr_mcp.repositories._errors import ToolError
                raise ToolError(f"REST API error: {exc}") from exc

    return _OpenEMRClient()
