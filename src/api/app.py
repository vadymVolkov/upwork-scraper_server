"""FastAPI app for api.scriptium.com."""

from __future__ import annotations

from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.errors import register_exception_handlers
from src.api.security import require_api_key
from src.core.runner import ScraperService, ensure_payload

app = FastAPI(
    title="Scriptium Upwork API",
    version="1.0.0",
    description="REST API service for Upwork scraper",
)
service = ScraperService()


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


register_exception_handlers(app)


@app.get("/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/auth/login", dependencies=[Depends(require_api_key)])
async def login(payload: dict):
    data = ensure_payload(payload)
    result = await service.login(data)
    return {"success": True, "data": result}


@app.post("/v1/search", dependencies=[Depends(require_api_key)])
async def search(payload: dict):
    data = ensure_payload(payload)
    jobs = await service.search(data, require_query=True)
    return {"success": True, "count": len(jobs), "jobs": jobs}


@app.post("/v1/collect-urls", dependencies=[Depends(require_api_key)])
async def collect_urls(payload: dict):
    data = ensure_payload(payload)
    result = await service.collect_urls(data, bestmatch=False)
    return {"success": True, "data": result}


@app.post("/v1/collect-bestmatch-urls", dependencies=[Depends(require_api_key)])
async def collect_bestmatch_urls(payload: dict):
    data = ensure_payload(payload)
    result = await service.collect_urls(data, bestmatch=True)
    return {"success": True, "data": result}


@app.post("/v1/parse-job-urls", dependencies=[Depends(require_api_key)])
async def parse_job_urls(payload: dict):
    data = ensure_payload(payload)
    result = await service.parse_urls(data, bestmatch=False)
    return {"success": True, "data": result}


@app.post("/v1/parse-bestmatch-urls", dependencies=[Depends(require_api_key)])
async def parse_bestmatch_urls(payload: dict):
    data = ensure_payload(payload)
    result = await service.parse_urls(data, bestmatch=True)
    return {"success": True, "data": result}


@app.post("/v1/pull-jobs", dependencies=[Depends(require_api_key)])
async def pull_jobs(payload: dict):
    data = ensure_payload(payload)
    result = service.pull_jobs(data, bestmatch=False)
    return JSONResponse({"success": True, "count": len(result), "jobs": result})


@app.post("/v1/pull-bestmatch-jobs", dependencies=[Depends(require_api_key)])
async def pull_bestmatch_jobs(payload: dict):
    data = ensure_payload(payload)
    result = service.pull_jobs(data, bestmatch=True)
    return JSONResponse({"success": True, "count": len(result), "jobs": result})
