from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.api.routes import chat, documents, health
from app.core.config import get_settings

app = FastAPI(
    title="Wealth Intelligence Copilot",
    description="Wealth management research copilot — grounded answers from SEC filings and financial documents",
    version="0.1.0",
)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Browser visits to :8000/ go to interactive API docs."""
    return RedirectResponse(url="/docs", status_code=302)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    """Browsers request this automatically; no asset bundled yet."""
    return Response(status_code=204)


@app.get("/api", tags=["meta"])
async def api_index() -> JSONResponse:
    return JSONResponse(
        {
            "name": "Wealth Intelligence Copilot",
            "docs": "/docs",
            "health": "/api/health",
            "chat": "POST /api/chat",
        }
    )


@app.on_event("startup")
async def startup_check() -> None:
    cfg = get_settings()
    if not cfg.openai_configured:
        print(
            "WARNING: OPENAI_API_KEY missing or placeholder — "
            "chat will fail until .env is fixed and backend restarted."
        )
    else:
        print("OpenAI API key loaded from project .env")


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
