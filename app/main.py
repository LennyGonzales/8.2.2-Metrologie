import asyncio
import json
import logging
import sys
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

APP_NAME = "demo-api"


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "service": APP_NAME,
        }
        for field in (
            "request_id",
            "route",
            "method",
            "status_code",
            "duration_ms",
            "event",
            "action",
            "client_error",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False)


logger = logging.getLogger(APP_NAME)
logger.setLevel(logging.INFO)
logger.handlers.clear()
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(JsonLogFormatter())
logger.addHandler(stream_handler)
logger.propagate = False

app = FastAPI(title="Prometheus + ELK Demo API")

slow_requests_total = Counter(
    "app_slow_requests_total",
    "Nombre de requetes lentes (>2s) traitees par l application",
    ["endpoint"],
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")


def log_event(level: int, message: str, **fields) -> None:
    logger.log(level, message, extra=fields)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    started_at = datetime.now(timezone.utc)

    response = await call_next(request)

    duration_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
    status_code = response.status_code
    level = logging.ERROR if status_code >= 500 else logging.WARNING if status_code >= 400 else logging.INFO

    log_event(
        level,
        "HTTP request handled",
        request_id=request_id,
        route=request.url.path,
        method=request.method,
        status_code=status_code,
        duration_ms=duration_ms,
        event="http_request",
        client_error=status_code >= 400,
    )

    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/ok")
async def ok():
    return {"message": "success"}


@app.get("/slow")
async def slow():
    await asyncio.sleep(2.5)
    slow_requests_total.labels(endpoint="/slow").inc()
    log_event(
        logging.INFO,
        "Slow endpoint completed",
        route="/slow",
        event="slow_response",
        action="latency_check",
    )
    return {"message": "slow response"}


@app.get("/bad-request")
async def bad_request():
    return Response(
        content='{"error":"bad request"}',
        status_code=400,
        media_type="application/json",
    )


@app.get("/not-found")
async def not_found():
    return Response(
        content='{"error":"not found"}',
        status_code=404,
        media_type="application/json",
    )


@app.get("/error")
async def error():
    return Response(
        content='{"error":"internal"}',
        status_code=500,
        media_type="application/json",
    )


@app.get("/crash")
async def crash():
    return Response(
        content='{"error":"unavailable"}',
        status_code=503,
        media_type="application/json",
    )
