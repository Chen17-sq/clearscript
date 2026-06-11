"""Provider listing + in-app API key management (OS keyring)."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from clearscript.api.deps import AppState, key_source


def build_router(state: AppState) -> APIRouter:
    router = APIRouter()

    @router.get("/api/providers")
    def list_providers() -> dict:
        c = state.cfg()
        return {
            "default": c.default_provider,
            "providers": [
                {
                    "name": p.name,
                    "type": p.type,
                    "default_model": p.default_model,
                    "models": p.models,
                    "has_key": (p.resolve_api_key() is not None) or p.type == "ollama",
                    "key_env": p.api_key_env,
                    "key_source": key_source(p),
                }
                for p in c.providers.values()
            ],
        }

    @router.post("/api/providers/{name}/api-key", status_code=201)
    def set_provider_api_key(name: str, payload: dict) -> dict:
        """Persist an API key for a provider into the OS keyring.

        Body: ``{"api_key": "sk-ant-..."}``. The key is stored under
        service ``clearscript`` + the provider's name, so it survives
        server restarts but is never written to disk by clearscript
        (the keyring backend handles that).

        Returns ``{ok: true, source: "keyring"}`` so the UI can show
        "saved to keyring" feedback. If the keyring backend fails (e.g.
        on a headless Linux box with no DBus), returns 500 with a
        descriptive message — the user can fall back to env var.
        """
        c = state.cfg()
        if name not in c.providers:
            raise HTTPException(404, f"Unknown provider {name!r}")
        raw_key = (payload or {}).get("api_key", "")
        # {"api_key": null} / numbers / lists used to reach .strip() and
        # blow up with a 500 — coerce non-strings to "missing".
        key = raw_key.strip() if isinstance(raw_key, str) else ""
        if not key:
            raise HTTPException(400, "Missing api_key in body")
        try:
            import keyring

            keyring.set_password("clearscript", name, key)
        except Exception as exc:
            raise HTTPException(
                500,
                f"Failed to save to keyring: {exc}. Fall back to env var "
                f"({c.providers[name].api_key_env or 'see README'}).",
            ) from exc
        return {"ok": True, "source": "keyring"}

    @router.delete("/api/providers/{name}/api-key", status_code=204)
    def delete_provider_api_key(name: str) -> Response:
        c = state.cfg()
        if name not in c.providers:
            raise HTTPException(404, f"Unknown provider {name!r}")
        try:
            import keyring

            with contextlib.suppress(keyring.errors.PasswordDeleteError):
                keyring.delete_password("clearscript", name)
        except Exception as exc:
            raise HTTPException(500, f"Failed to delete from keyring: {exc}") from exc
        return Response(status_code=204)

    return router
