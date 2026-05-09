"""Entry point: launches FastAPI backend + Flet desktop UI."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
import time
from pathlib import Path

import structlog
import uvicorn

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Code Review Assistant")
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Run API server only (no desktop UI, for Docker/headless)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override API server port",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Override API server host",
    )
    return parser.parse_args()


def start_api_server(host: str, port: int, ready_event: threading.Event) -> None:
    """Run the FastAPI server in a background thread."""
    from src.api_server import app

    async def _run() -> None:
        config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)

        # Signal ready after startup
        original_startup = server.startup

        async def patched_startup(sockets=None) -> None:
            await original_startup(sockets=sockets)
            ready_event.set()

        server.startup = patched_startup
        await server.serve()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run())
    except Exception as e:
        logger.error("API server crashed", error=str(e))
        ready_event.set()  # Unblock UI even on failure


def wait_for_api(port: int, timeout: float = 15.0) -> bool:
    """Wait for the API server to become available."""
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def main() -> None:
    args = parse_args()

    from src.config import settings

    host = args.host or settings.api_host
    port = args.port or settings.api_port

    logger.info("Starting Code Review Assistant", port=port, ui=not args.no_ui)

    # Ensure data directory exists
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "exports").mkdir(parents=True, exist_ok=True)

    if args.no_ui:
        # Headless mode: just run the API server (blocking)
        logger.info("Running in headless mode", host=host, port=port)
        from src.api_server import app

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=settings.log_level.lower(),
            access_log=True,
        )
    else:
        # Desktop mode: start API in background, launch Flet UI
        ready_event = threading.Event()

        api_thread = threading.Thread(
            target=start_api_server,
            args=(host, port, ready_event),
            daemon=True,
            name="api-server",
        )
        api_thread.start()

        logger.info("Waiting for API server to start...")
        ready_event.wait(timeout=15.0)
        time.sleep(0.5)  # Small extra buffer

        if not wait_for_api(port, timeout=10.0):
            logger.warning("API server may not be ready yet — launching UI anyway")

        logger.info("Launching desktop UI")
        from src.ui.app import launch_ui

        launch_ui(api_port=port)


if __name__ == "__main__":
    main()
