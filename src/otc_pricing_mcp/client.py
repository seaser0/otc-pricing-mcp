"""HTTP client wrapper for the OTC Price Calculator API.

Provides a stateless, retry-capable wrapper around httpx for all API access.
Includes comprehensive logging and metrics for debugging and monitoring.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from . import __version__, observability
from .models import ApiResponse

logger = observability.get_logger(__name__)

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
        """Perform a GET request to the API with logging and metrics.

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

        service = params.get("serviceName", "unknown")
        request_id = observability.get_request_id()
        start_time = time.time()

        logger.debug(
            "upstream_request_start",
            service=service,
            request_id=request_id,
            params={k: v for k, v in params.items() if k not in ["productType"]},
        )

        attempt_count = 0
        last_error: Exception | None = None

        for attempt in RETRIES:
            with attempt:
                attempt_count += 1
                try:
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
                        api_response = ApiResponse(**data["response"])
                    except Exception as e:
                        raise ValueError(f"Failed to parse API response: {e}") from e

                    # Record success metrics
                    duration = time.time() - start_time
                    observability.metrics.upstream_requests_total.labels(
                        service=service, status="success"
                    ).inc()
                    observability.metrics.upstream_duration_seconds.labels(service=service).observe(
                        duration
                    )

                    logger.debug(
                        "upstream_request_success",
                        service=service,
                        request_id=request_id,
                        status_code=response.status_code,
                        duration_seconds=duration,
                        attempt=attempt_count,
                        items_returned=api_response.stats.count if api_response.stats else 0,
                    )

                    return api_response

                except httpx.HTTPStatusError as e:
                    # Re-raise with a sanitised message that omits the upstream
                    # URL — the raw httpx message includes the full URL and query
                    # string, which leaks internal API details (issue #34).
                    status = e.response.status_code
                    clean = httpx.HTTPStatusError(
                        f"upstream HTTP {status}",
                        request=e.request,
                        response=e.response,
                    )
                    last_error = clean
                    logger.warning(
                        "upstream_request_http_error",
                        service=service,
                        request_id=request_id,
                        error=f"upstream HTTP {status}",
                        status_code=status,
                        attempt=attempt_count,
                    )
                    raise clean from None
                except httpx.HTTPError as e:
                    last_error = e
                    logger.warning(
                        "upstream_request_http_error",
                        service=service,
                        request_id=request_id,
                        error=str(e),
                        status_code=None,
                        attempt=attempt_count,
                    )
                    raise
                except Exception as e:
                    last_error = e
                    logger.error(
                        "upstream_request_parse_error",
                        service=service,
                        request_id=request_id,
                        error=str(e),
                        error_type=type(e).__name__,
                        attempt=attempt_count,
                    )
                    raise

        # Record error metrics
        duration = time.time() - start_time
        observability.metrics.upstream_requests_total.labels(service=service, status="error").inc()
        observability.metrics.upstream_duration_seconds.labels(service=service).observe(duration)

        logger.error(
            "upstream_request_failed",
            service=service,
            request_id=request_id,
            error=str(last_error) if last_error else "Unknown error",
            error_type=type(last_error).__name__ if last_error else "Unknown",
            attempts=attempt_count,
            duration_seconds=duration,
        )

        raise RuntimeError("Retries exhausted")  # pragma: no cover
