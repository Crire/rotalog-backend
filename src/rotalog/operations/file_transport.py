"""Transporte binário limitado; não faz I/O de storage ou SQL no event loop."""

from fastapi import Request

from rotalog.core.contracts import fail


async def receive_limited_body(request: Request, max_bytes: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared:
        try:
            size = int(declared)
        except ValueError:
            fail("FILE_SIZE_INVALID", "Content-Length inválido.", 422)
        if size < 0 or size > max_bytes:
            fail("FILE_SIZE_INVALID", "Arquivo excede o limite configurado.", 413)
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > max_bytes:
            fail("FILE_SIZE_INVALID", "Arquivo excede o limite configurado.", 413)
        content.extend(chunk)
    return bytes(content)
