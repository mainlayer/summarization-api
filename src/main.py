"""
Summarization API — pay per call via Mainlayer.

Endpoints
---------
POST /summarize          $0.002 / call
POST /summarize/batch    $0.0015 / call
POST /summarize/url      $0.003 / call
GET  /models             FREE
GET  /health             FREE
"""
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.mainlayer import record_usage, verify_payment, _get_payment_token
from src.models import (
    BatchSummaryItem,
    BatchSummaryResponse,
    BatchSummarizeRequest,
    ModelInfo,
    ModelsResponse,
    SummaryResponse,
    SummarizeRequest,
    SummaryStyle,
    URLSummarizeRequest,
)
from src.summarizer import compute_compression_ratio, summarize

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Available models catalogue (static for this template)
# ---------------------------------------------------------------------------

AVAILABLE_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="extractive-v1",
        name="Extractive Summarizer v1",
        description=(
            "Fast extractive summarization. Selects the most informative "
            "sentences from the source text."
        ),
        max_input_tokens=4096,
        supported_styles=[SummaryStyle.bullet, SummaryStyle.paragraph, SummaryStyle.tldr],
    ),
    ModelInfo(
        id="abstractive-v1",
        name="Abstractive Summarizer v1",
        description=(
            "Abstractive summarization that paraphrases and condenses content "
            "into fluent prose. Ideal for long-form documents."
        ),
        max_input_tokens=16384,
        supported_styles=[SummaryStyle.paragraph, SummaryStyle.tldr],
    ),
    ModelInfo(
        id="bullets-v1",
        name="Bullet-Point Specialist v1",
        description=(
            "Optimised for structured bullet-point output. Great for meeting "
            "notes, articles, and reports."
        ),
        max_input_tokens=8192,
        supported_styles=[SummaryStyle.bullet],
    ),
]

DEFAULT_MODEL = "extractive-v1"


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Summarization API starting up")
    yield
    logger.info("Summarization API shutting down")


app = FastAPI(
    title="Summarization API",
    description=(
        "Text summarization API with pay-per-call billing via Mainlayer. "
        "$0.002 per summary — bullet points, paragraphs, or TL;DR."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "internal_server_error", "detail": "An unexpected error occurred."},
    )


# ---------------------------------------------------------------------------
# Free endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Meta"])
async def health():
    """Liveness probe — always returns 200."""
    return {"status": "ok"}


@app.get("/models", response_model=ModelsResponse, tags=["Meta"])
async def list_models():
    """
    List available summarization models.

    This endpoint is **free** — no payment token required.
    """
    return ModelsResponse(models=AVAILABLE_MODELS, default_model=DEFAULT_MODEL)


# ---------------------------------------------------------------------------
# Paid endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/summarize",
    response_model=SummaryResponse,
    status_code=status.HTTP_200_OK,
    tags=["Summarization"],
    summary="Summarize text  [$0.002/call]",
)
async def summarize_text(body: SummarizeRequest, request: Request):
    """
    Summarize a block of text.

    **Cost**: $0.002 per call (billed via Mainlayer).

    Pass your Mainlayer payment token in the `X-Mainlayer-Token` header.
    Set `MAINLAYER_DEV_MODE=true` to skip billing during development.
    """
    await verify_payment(request, "/summarize")

    summary = summarize(body.text, body.max_length, body.style)
    word_count = len(summary.split())
    compression = compute_compression_ratio(body.text, summary)

    token = _get_payment_token(request)
    await record_usage(
        "/summarize",
        token,
        {"style": body.style, "original_words": len(body.text.split())},
    )

    return SummaryResponse(
        summary=summary,
        word_count=word_count,
        compression_ratio=compression,
    )


@app.post(
    "/summarize/batch",
    response_model=BatchSummaryResponse,
    status_code=status.HTTP_200_OK,
    tags=["Summarization"],
    summary="Batch summarize texts  [$0.0015/call]",
)
async def summarize_batch(body: BatchSummarizeRequest, request: Request):
    """
    Summarize multiple texts in a single request (1–20 items).

    **Cost**: $0.0015 per call regardless of batch size.

    Pass your Mainlayer payment token in the `X-Mainlayer-Token` header.
    """
    await verify_payment(request, "/summarize/batch")

    results: list[BatchSummaryItem] = []
    for idx, item in enumerate(body.items):
        summary = summarize(item.text, item.max_length, item.style)
        word_count = len(summary.split())
        compression = compute_compression_ratio(item.text, summary)
        results.append(
            BatchSummaryItem(
                index=idx,
                summary=summary,
                word_count=word_count,
                compression_ratio=compression,
            )
        )

    token = _get_payment_token(request)
    await record_usage(
        "/summarize/batch",
        token,
        {"batch_size": len(body.items)},
    )

    return BatchSummaryResponse(results=results, total_items=len(results))


@app.post(
    "/summarize/url",
    response_model=SummaryResponse,
    status_code=status.HTTP_200_OK,
    tags=["Summarization"],
    summary="Summarize a URL  [$0.003/call]",
)
async def summarize_url(body: URLSummarizeRequest, request: Request):
    """
    Fetch a publicly accessible URL and summarize its text content.

    **Cost**: $0.003 per call (includes fetch + summarization).

    Pass your Mainlayer payment token in the `X-Mainlayer-Token` header.
    """
    await verify_payment(request, "/summarize/url")

    # Fetch the URL
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "SummarizationAPI/1.0 (+https://mainlayer.xyz)"},
        ) as client:
            response = await client.get(body.url)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Timed out fetching URL: {body.url}",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"URL returned HTTP {exc.response.status_code}: {body.url}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not fetch URL: {exc}",
        )

    # Extract plain text from HTML (very lightweight — strip tags)
    content_type = response.headers.get("content-type", "")
    raw_text = response.text

    if "html" in content_type:
        import re
        # Remove script/style blocks
        raw_text = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", raw_text, flags=re.DOTALL | re.IGNORECASE)
        # Strip all remaining tags
        raw_text = re.sub(r"<[^>]+>", " ", raw_text)
        # Collapse whitespace
        raw_text = re.sub(r"\s+", " ", raw_text).strip()

    if len(raw_text.strip()) < 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract meaningful text from the provided URL.",
        )

    # Summarize
    summary = summarize(raw_text, body.max_length, body.style)
    word_count = len(summary.split())
    compression = compute_compression_ratio(raw_text, summary)

    token = _get_payment_token(request)
    await record_usage(
        "/summarize/url",
        token,
        {"url": body.url, "style": body.style},
    )

    return SummaryResponse(
        summary=summary,
        word_count=word_count,
        compression_ratio=compression,
    )
