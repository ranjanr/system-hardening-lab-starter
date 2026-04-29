import os
import random
import time
from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

app = FastAPI(title="service-b")

# Observability setup for traces and metrics. The teaching logic starts in
# the /data handler below.
service_name = os.getenv("OTEL_SERVICE_NAME", "service-b")
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318")
provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(service_name)

FastAPIInstrumentor.instrument_app(app)
Instrumentator().instrument(app).expose(app)

FAILURE_RATE = float(os.getenv("FAILURE_RATE", "0.25"))
DELAY_MIN_MS = int(os.getenv("DELAY_MIN_MS", "500"))
DELAY_MAX_MS = int(os.getenv("DELAY_MAX_MS", "4000"))


@app.get("/health")
def health():
    return {"status": "ok", "service": "service-b"}


@app.get("/data")
def get_data():
    # Simulate variable latency so students can observe timeout and retry behavior.
    delay_ms = random.randint(DELAY_MIN_MS, DELAY_MAX_MS)
    time.sleep(delay_ms / 1000)

    with tracer.start_as_current_span("service-b-work") as span:
        span.set_attribute("service_b.delay_ms", delay_ms)
        # Random failures let students see how service-a behaves under stress.
        if random.random() < FAILURE_RATE:
            span.set_attribute("service_b.failure", True)
            raise HTTPException(status_code=503, detail="service-b simulated failure")

        payload = {
            "source": "service-b",
            "delay_ms": delay_ms,
            "message": "fresh response from downstream",
        }
        return payload
