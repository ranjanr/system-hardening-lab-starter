import json
import os
from typing import Any, Dict, Optional

import pybreaker
import redis
import requests
from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

app = FastAPI(title="service-a")

# Observability setup for traces and metrics. Students can skim this first
# and focus on the request flow lower in the file.
service_name = os.getenv("OTEL_SERVICE_NAME", "service-a")
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318")
provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(service_name)

FastAPIInstrumentor.instrument_app(app)
RequestsInstrumentor().instrument()
Instrumentator().instrument(app).expose(app)

SERVICE_B_URL = os.getenv("SERVICE_B_URL", "http://service-b:8001/data")
REQUEST_TIMEOUT_SEC = float(os.getenv("REQUEST_TIMEOUT_SEC", "1.5"))
CACHE_TTL_SEC = int(os.getenv("CACHE_TTL_SEC", "30"))
ENABLE_RETRY = os.getenv("ENABLE_RETRY", "false").lower() == "true"
ENABLE_CIRCUIT_BREAKER = os.getenv("ENABLE_CIRCUIT_BREAKER", "false").lower() == "true"
ENABLE_CACHE = os.getenv("ENABLE_CACHE", "false").lower() == "true"

redis_client: Optional[redis.Redis] = None
if ENABLE_CACHE:
    redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=int(os.getenv("REDIS_PORT", "6379")), decode_responses=True)

breaker = pybreaker.CircuitBreaker(
    fail_max=int(os.getenv("CIRCUIT_FAIL_MAX", "3")),
    reset_timeout=int(os.getenv("CIRCUIT_RESET_TIMEOUT_SEC", "10")),
)


class DownstreamCallError(Exception):
    pass


def cache_get(key: str) -> Optional[Dict[str, Any]]:
    if not redis_client:
        return None
    value = redis_client.get(key)
    return json.loads(value) if value else None


def cache_set(key: str, payload: Dict[str, Any]):
    if redis_client:
        redis_client.setex(key, CACHE_TTL_SEC, json.dumps(payload))


def do_downstream_call() -> Dict[str, Any]:
    # Baseline behavior: make one request to service-b and fail if it errors or times out.
    try:
        response = requests.get(SERVICE_B_URL, timeout=REQUEST_TIMEOUT_SEC)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise DownstreamCallError(str(exc)) from exc


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.25, min=0.25, max=2),
    retry=retry_if_exception_type(DownstreamCallError),
    reraise=True,
)
def do_downstream_call_with_retry() -> Dict[str, Any]:
    return do_downstream_call()


def call_with_optional_patterns() -> Dict[str, Any]:
    # This function is the lab switchboard. Compose the request path based on
    # which resilience features are enabled in docker-compose.yml.
    call_func = do_downstream_call_with_retry if ENABLE_RETRY else do_downstream_call

    if ENABLE_CIRCUIT_BREAKER:
        protected = breaker.call
        return protected(call_func)
    return call_func()


@app.get("/health")
def health():
    state = str(breaker.current_state) if ENABLE_CIRCUIT_BREAKER else "disabled"
    return {"status": "ok", "service": "service-a", "circuit_breaker": state}


@app.get("/api/data")
def api_data():
    cache_key = "service-b:data"

    with tracer.start_as_current_span("service-a-handler") as span:
        span.set_attribute("resilience.retry", ENABLE_RETRY)
        span.set_attribute("resilience.circuit_breaker", ENABLE_CIRCUIT_BREAKER)
        span.set_attribute("resilience.cache", ENABLE_CACHE)

        if ENABLE_CACHE:
            cached = cache_get(cache_key)
            if cached:
                span.set_attribute("cache.hit", True)
                return {
                    "path": "cache",
                    "payload": cached,
                    "message": "response served from Redis cache",
                }
            span.set_attribute("cache.hit", False)

        try:
            # No cached answer was found, so call the downstream service through
            # the currently enabled resilience path.
            payload = call_with_optional_patterns()
            if ENABLE_CACHE:
                cache_set(cache_key, payload)
            return {
                "path": "live",
                "payload": payload,
                "message": "response served from downstream service",
            }
        except pybreaker.CircuitBreakerError:
            fallback = cache_get(cache_key)
            if fallback:
                return {
                    "path": "fallback-cache",
                    "payload": fallback,
                    "message": "circuit open, served stale cache",
                }
            raise HTTPException(status_code=503, detail="circuit breaker is open and no fallback is available")
        except DownstreamCallError as exc:
            # If the live call failed, try serving a previously cached response.
            fallback = cache_get(cache_key)
            if fallback:
                return {
                    "path": "degraded-cache",
                    "payload": fallback,
                    "message": "downstream failed, served cached response",
                }
            raise HTTPException(status_code=503, detail=f"downstream call failed: {exc}")
