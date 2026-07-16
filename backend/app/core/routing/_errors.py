"""Shared exception tuple for voice routing network/LLM calls.

The route layer must never raise to the caller (design §8.5: any failure
degrades to `delegate`). The base narrow set (per AGENTS.md) does NOT cover
HTTP/LLM SDK errors (`httpx.HTTPError`, `openai.APIError`) which inherit from
`Exception`, not `OSError`. We collect them optionally (they are real deps in
this stack) so a down LM Studio degrades cleanly instead of leaking an
unhandled task exception through the voice WebSocket handler.
"""

from __future__ import annotations


def _build() -> tuple[type[BaseException], ...]:
    excs: list[type[BaseException]] = [
        ValueError,
        OSError,  # covers built-in ConnectionError / TimeoutError
        RuntimeError,
        TypeError,
        KeyError,
        AttributeError,
    ]
    try:
        import httpx

        excs.append(httpx.HTTPError)
    except ImportError:
        pass
    try:
        import openai

        excs.append(openai.APIError)
    except ImportError:
        pass
    return tuple(excs)


ROUTE_EXCEPTIONS: tuple[type[BaseException], ...] = _build()
