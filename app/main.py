import asyncio

from fastapi import FastAPI, Response
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="Prometheus Demo API")

slow_requests_total = Counter(
    "app_slow_requests_total",
    "Nombre de requetes lentes (>2s) traitees par l application",
    ["endpoint"],
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")


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
