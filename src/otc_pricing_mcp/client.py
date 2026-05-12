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


class UpstreamError(RuntimeError):
    """Raised when the upstream OTC API returns an error.

    The message is intentionally short and does NOT include the full upstream
    URL (which would leak the internal endpoint and our query-string into the
    MCP error channel — see #34). Callers / observers can correlate via the
    structlog `upstream_request_http_error` log line if needed.
    """


def _strip_ghost_eu_ch2_rows(api_response: ApiResponse) -> int:
    """Drop region=eu-ch2 rows from a public-catalog (client=1) response.

    The public catalog returns 75 'ghost' rows tagged region=eu-ch2 but priced
    in EUR — for 35 of them the matching real entry exists in client=2 with the
    same numerical amount but CHF currency, i.e. the currency label is wrong;
    the remaining 40 are 0.00 EUR free-tier stubs. Surfacing them silently
    misrepresents Swiss pricing (#52). Real eu-ch2 prices come from client=2
    (set by callers via region='eu-ch2', see #50/#51).

    Mutates `api_response.result` in place. Returns the number of rows dropped
    (for logging/observability).
    """
    dropped = 0
    result = api_response.result
    if isinstance(result, dict):
        for svc, items in result.items():
            if not items:
                continue
            kept = [it for it in items if it.get("region") != "eu-ch2"]
            dropped += len(items) - len(kept)
            result[svc] = kept
    elif isinstance(result, list):
        kept_list = [it for it in result if it.get("region") != "eu-ch2"]
        dropped = len(result) - len(kept_list)
        api_response.result = kept_list
    return dropped


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

                    # When the caller did not explicitly request client=2,
                    # drop region=eu-ch2 ghost rows whose currency label is
                    # wrong (#52). Real Swiss CHF pricing is fetched by
                    # passing client=2 (set automatically by query_pricing /
                    # estimate_monthly_cost when the caller targets Swiss).
                    if params.get("client") != "2":
                        dropped = _strip_ghost_eu_ch2_rows(api_response)
                        if dropped:
                            logger.debug(
                                "ghost_eu_ch2_rows_stripped",
                                service=service,
                                request_id=request_id,
                                dropped=dropped,
                            )

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

                except httpx.HTTPError as e:
                    last_error = e
                    status = (
                        getattr(e.response, "status_code", None) if hasattr(e, "response") else None
                    )
                    logger.warning(
                        "upstream_request_http_error",
                        service=service,
                        request_id=request_id,
                        error=str(e),
                        status_code=status,
                        attempt=attempt_count,
                    )
                    # Sanitised re-raise: the default httpx message includes
                    # the full upstream URL with our query-string, which leaks
                    # internals into the MCP error channel (#34). Replace with
                    # a short, intent-preserving message.
                    if status is not None:
                        if status == 500 and "serviceName" in str(getattr(e, "request", "")):
                            raise UpstreamError(
                                f"Service '{service}' not in OTC catalog "
                                f"(or upstream rejected the request). "
                                f"Use list_services() to discover available services."
                            ) from None
                        raise UpstreamError(
                            f"upstream HTTP {status} for service {service!r}"
                        ) from None
                    raise UpstreamError(f"upstream HTTP error for service {service!r}") from None
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
