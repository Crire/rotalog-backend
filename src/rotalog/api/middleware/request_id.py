from uuid import UUID, uuid4


from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next): 
        receive_request_id = request.headers.get("X-Request-ID")
        request_id = self.resolve_request_id(receive_request_id)

        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return message

    @staticmethod
    def _resolve_request_id(received_request_id: str | None) -> str:
        if received_request_id:
            try:
                return str(UUID(receive_request_id))
            except ValueError:
                pass

            return str(uuid4())