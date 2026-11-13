"""CLI entrypoint for launching OmniCast Studio."""

from __future__ import annotations

import argparse
import os

import uvicorn

from omnicast.app import create_app
from omnicast.config import Settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run OmniCast Studio web server.")
    parser.add_argument("--host", default=None, help="Bind host (default: OMNICAST_HOST or 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (default: OMNICAST_PORT or 8080)")
    parser.add_argument("--mock", action="store_true", help="Use offline mock audio generator instead of OmniVoice")
    args = parser.parse_args(argv)

    if args.mock:
        os.environ["OMNICAST_MOCK"] = "1"

    settings = Settings.from_env()
    host = args.host or settings.host
    port = args.port or settings.port

    app = create_app(settings=settings)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
