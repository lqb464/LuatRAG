import hmac
import unicodedata
from dataclasses import dataclass

from fastapi import Request
from starlette.responses import JSONResponse

from backend.core.config import Settings
from src.errors import ServiceError


@dataclass(frozen=True)
class User:
    id: str
    email: str | None = None


def request_user(request: Request) -> User:
    settings: Settings = request.app.state.settings
    supplied = request.headers.get("x-luatrag-bff-secret", "")
    trusted_bff = bool(settings.bff_secret) and hmac.compare_digest(
        supplied.encode(), settings.bff_secret.encode()
    )
    if settings.production and not trusted_bff:
        raise ServiceError(401, "authentication_required", "Vui lòng đăng nhập để tiếp tục.")
    user_id = request.headers.get("oai-authenticated-user-id")
    if user_id and (trusted_bff or not settings.production):
        return User(user_id, request.headers.get("oai-authenticated-user-email"))
    if not settings.production and request.url.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
        "testserver",
    }:
        return User("local-development-user", "local@luatrag.test")
    raise ServiceError(401, "authentication_required", "Vui lòng đăng nhập để tiếp tục.")


def assert_same_origin(request: Request) -> None:
    settings: Settings = request.app.state.settings
    origin = request.headers.get("origin")
    expected = f"{request.url.scheme}://{request.url.netloc}"
    fetch_site = request.headers.get("sec-fetch-site", "").lower()
    if (origin and origin not in {settings.frontend_origin, expected}) or fetch_site in {
        "cross-site",
        "same-site",
    }:
        raise ServiceError(403, "origin_rejected", "Nguồn gửi yêu cầu không hợp lệ.")


def clean_filename(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    return " ".join(
        "".join("-" if ord(char) < 32 or char in '\\/:<>"|?*' else char for char in value).split()
    )[:180]


class BodyLimitMiddleware:
    """Bound streamed input before JSON or multipart parsing allocates an unbounded body."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = 10 * 1024 * 1024 + 256 * 1024 if scope["path"] == "/api/sources" else 32_000
        headers = dict(scope.get("headers", []))
        raw_length = headers.get(b"content-length")
        try:
            length = int(raw_length) if raw_length is not None else 0
            if length < 0:
                raise ValueError
        except ValueError:
            response = JSONResponse(
                {
                    "error": {
                        "code": "invalid_content_length",
                        "message": "Kích thước yêu cầu không hợp lệ.",
                    }
                },
                status_code=400,
            )
            return await response(scope, receive, send)
        messages = []
        total = 0
        if length <= limit:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                total += len(message.get("body", b""))
                if total > limit:
                    break
                messages.append(message)
                if not message.get("more_body", False):
                    break
        if length > limit or total > limit:
            response = JSONResponse(
                {"error": {"code": "payload_too_large", "message": "Nội dung yêu cầu quá lớn."}},
                status_code=413,
            )
            return await response(scope, receive, send)
        cursor = iter(messages)

        async def bounded_receive():
            try:
                return next(cursor)
            except StopIteration:
                return await receive()

        await self.app(scope, bounded_receive, send)
