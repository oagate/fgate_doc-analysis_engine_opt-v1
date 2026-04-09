from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from api.analysis_schemas import AnalyzeDocumentRequest, AnalyzeDocumentResponse
from core.document_analysis_service import document_analysis_service

_KERNEL_SECRET = os.getenv("PYTHON_KERNEL_SECRET", "")
_IS_PRODUCTION = os.getenv("APP_ENV", "local") == "production"

_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "KERNEL_ALLOWED_ORIGINS",
        "http://localhost:8000,http://localhost:5173",
    ).split(",")
    if o.strip()
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Api",
    version="1.0.0",
    docs_url=None if _IS_PRODUCTION else "/docs",
    redoc_url=None if _IS_PRODUCTION else "/redoc",
    openapi_url=None if _IS_PRODUCTION else "/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    with logger.contextualize(request_id=request_id):
        response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def verify_secret(request: Request, call_next):
    if request.url.path in ("/health", "/"):
        return await call_next(request)

    if _KERNEL_SECRET:
        incoming = request.headers.get("X-Kernel-Secret", "")
        if not incoming or incoming != _KERNEL_SECRET:
            logger.warning(
                f"[Auth] Unauthorized | path={request.url.path} | "
                f"ip={request.client.host if request.client else 'unknown'}"
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized."},
            )

    return await call_next(request)


@app.get("/")
def root():
    return {
        "service": "Doc Analysis API",
        "version": "1.0.0",
        "analysis_types": ["full", "risk", "clauses", "compare"],
        "model": "deepseek-v3",
        "docs": "/docs" if not _IS_PRODUCTION else "disabled in production",
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "Doc Analysis API"}


@app.post("/analyze-document", response_model=AnalyzeDocumentResponse)
async def analyze_document(request: AnalyzeDocumentRequest):
    logger.info(
        f"[/analyze-document] | type={request.analysis_type} | "
        f"doc='{request.filename}' | chars={len(request.text):,}"
    )

    try:
        result = await document_analysis_service.analyze(request)
        return result

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    except Exception as exc:
        logger.exception(f"[/analyze-document] Unexpected error: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Analysis failed. Please try again.",
        )
