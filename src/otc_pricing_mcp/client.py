"""HTTP client wrapper for the OTC Price Calculator API.

Provides a stateless, retry-capable wrapper around httpx for all API access.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from . import __version__
from .models import ApiResponse

logger = logging.getLogger(__name__)

# Default API endpoint
DEFAULT_BASE_URL = "https://calculator.otc-service.com/en/open-telekom-price-api/"

# Retry configuration
RETRIES = Retrying(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)


class OTCPricingClient:
    """HTTP client for the OTC Price Calculator API.

    Handles:
    - Request retry logic with exponential backoff
    - Custom User-Agent header
    - Reasonable timeout defaults
    - Response parsing and validation
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        user_agent: str | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: The API endpoint URL (default from env var OTC_PRICING_API_BASE
                     or DEFAULT_BASE_URL).
            timeout: Request timeout in seconds.
            user_agent: Custom User-Agent header. If None, uses default with version.
        """
        self.base_url = base_url
        self.timeout = timeout
        self.user_agent = user_agent or f"otc-pricing-mcp/{__version__}"
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        """Lazily create and return the httpx client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
            )
        return self._client

    def close(self) -> None:
        """Close the underlying httpx client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> OTCPricingClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()

    def get(
        self,
        params: dict[str, Any] | None = None,
    ) -> ApiResponse:
        """Perform a GET request to the API.

        Args:
            params: Query parameters (e.g., productType, serviceName, filterBy, limitMax).

        Returns:
            Parsed ApiResponse object.

        Raises:
            httpx.HTTPError: On network or HTTP errors (after retries).
            ValueError: On malformed response.
        """
        client = self._get_client()
        params = params or {}

        # Ensure productType is always "OTC"
        if "productType" not in params:
            params["productType"] = "OTC"

        for attempt in RETRIES:
            with attempt:
                response = client.get("/", params=params)
                response.raise_for_status()

                try:
                    data = response.json()
                except Exception as e:
                    raise ValueError(f"Failed to parse JSON response: {e}") from e

                # Validate structure
                if "response" not in data:
                    raise ValueError(
                        f"Expected 'response' key in API response, got: {list(data.keys())}"
                    )

                # Parse as ApiResponse
                try:
                    return ApiResponse(**data["response"])
                except Exception as e:
                    raise ValueError(f"Failed to parse API response: {e}") from e

        raise RuntimeError("Retries exhausted")  # pragma: no cover
