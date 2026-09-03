from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from backend.api.routes import router
from backend.core.config import Settings
from backend.core.security import BodyLimitMiddleware, ServiceError, assert_same_origin
from backend.src.store import Store
from src.rag.corpus import Corpus
from src.rag.gemini import GeminiError, generate_legal_answer


def create_app(settings: Settings | None = None, *, generator=None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(settings.data_dir)
        app.state.store.initialize()
        app.state.corpus = Corpus(settings.corpus_path)
        yield

    app = FastAPI(
        title="LuatRAG API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if settings.production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.production else "/openapi.json",
    )
    app.state.settings = settings

    async def default_generator(**kwargs):
        return await generate_legal_answer(
            api_key=settings.gemini_api_key, model=settings.gemini_model, **kwargs
        )

    app.state.generator = generator or default_generator
    app.include_router(router)
    app.add_middleware(BodyLimitMiddleware)

    @app.exception_handler(ServiceError)
    async def service_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": str(error)}}, status_code=error.status
        )

    @app.exception_handler(GeminiError)
    async def gemini_error(_request, error):
        status = 429 if error.code == "rate_limited" else 422 if error.code == "blocked" else 502
        return JSONResponse(
            {"error": {"code": error.code, "message": str(error), "retryable": error.retryable}},
            status_code=status,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _error):
        return JSONResponse(
            {"error": {"code": "invalid_request", "message": "Dữ liệu yêu cầu không hợp lệ."}},
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def internal_error(_request, _error):
        return JSONResponse(
            {"error": {"code": "internal_error", "message": "LuatRAG gặp lỗi khi xử lý yêu cầu."}},
            status_code=500,
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            try:
                assert_same_origin(request)
            except ServiceError as error:
                return await service_error(request, error)
        response = await call_next(request)
        response.headers["x-content-type-options"] = "nosniff"
        if request.url.path.startswith("/api/"):
            response.headers["cache-control"] = "no-store"
        return response

    return app


app = create_app()
