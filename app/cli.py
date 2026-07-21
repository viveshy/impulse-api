"""Entrypoint: `uv run serve`."""
import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
        reload=os.getenv("RELOAD", "1") == "1",
    )
