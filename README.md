# System Hardening Lab Starter Repo

This starter repo supports a class session on system hardening and scale. It includes:

- `service-a`: upstream API that calls `service-b`
- `service-b`: slow / flaky downstream service
- Redis for caching
- Jaeger for traces
- Prometheus for metrics
- Grafana for dashboards
- Optional local policy-guarded `agent/`

## What students should focus on

If you are reading the code for the first time, start here:

1. `service-b/app.py`
   This is the intentionally slow and flaky downstream service.
2. `service-a/app.py`
   This is the upstream API that adds retry, circuit breaker, and cache behavior.
3. `docker-compose.yml`
   This is where the lab features are turned on and off with environment variables.

You can treat the OpenTelemetry, Prometheus, Jaeger, and Grafana setup as support code for the lab. The main resilience logic is in the request flow between `service-a` and `service-b`.

## Quick start

Prerequisites:

- Docker Desktop or Docker Engine with `docker compose`
- At least a few GB of free RAM for the full stack
- The ports `3000`, `6379`, `8000`, `8001`, `9090`, and `16686` available on your laptop

```bash
docker compose up --build
```

The first startup may take a few minutes because Docker needs to build the Python images and pull the observability containers.

## Ports

- Service A: http://localhost:8000/api/data
- Service B: http://localhost:8001/data
- Jaeger: http://localhost:16686
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000  (`admin` / `admin`)

## Common student issues

- `docker: command not found`
  Docker is not installed or is not on your shell path yet.
- `port is already allocated`
  Another app is already using one of the lab ports.
- Requests fail right after startup
  Wait 15 to 30 seconds and try again. `depends_on` starts containers in order, but it does not wait for every service to be fully ready.
- Laptop feels slow
  Grafana, Prometheus, Jaeger, Redis, and two Python services are all running at once. This is expected on smaller laptops.

## How to use this repo in class

Start with all resilience features disabled in `docker-compose.yml`:

- `ENABLE_RETRY=false`
- `ENABLE_CIRCUIT_BREAKER=false`
- `ENABLE_CACHE=false`

Then enable the features step by step and observe the difference in:

- response time
- failure rate
- trace topology
- metrics in Prometheus / Grafana

Suggested feature toggle order in `docker-compose.yml`:

1. `ENABLE_RETRY=true`
2. `ENABLE_CIRCUIT_BREAKER=true`
3. `ENABLE_CACHE=true`

## Suggested tutorial flow

1. Baseline: observe random latency and failures.
2. Add timeout + retry.
3. Add circuit breaker.
4. Add Redis cache.
5. Inspect traces in Jaeger and metrics in Prometheus / Grafana.
6. Optional: run `python agent/simple_agent.py "fetch app data"` and test guardrails.

## Code map

`service-b/app.py`

- `/data` sleeps for a random time and sometimes returns `503`
- this simulates a slow or unreliable dependency

`service-a/app.py`

- `do_downstream_call()` makes the request to `service-b`
- `do_downstream_call_with_retry()` adds retry behavior
- `call_with_optional_patterns()` turns retry and circuit breaker on or off
- `/api/data` is the main endpoint students should trace through

`agent/simple_agent.py`

- a tiny local script that blocks a few unsafe prompts
- then calls `http://localhost:8000/api/data`
- this script runs on the host machine, not inside Docker

## Example load test command

```bash
for i in {1..15}; do curl -s http://localhost:8000/api/data; echo; done
```

If you want a simpler version that also works in shells without brace expansion:

```bash
for i in $(seq 1 15); do curl -s http://localhost:8000/api/data; echo; done
```

## Notes

- The lab stack is intentionally small and local-first.
- The production blueprint in the slide deck is richer than this local lab.
- The agent example is a lightweight teaching scaffold, not a production AI agent.
- If you want to run the optional agent, install Python 3 and `requests` on your laptop first.
