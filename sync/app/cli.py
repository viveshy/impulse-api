"""Entrypoint: run the catalog sync (populate/refresh)."""
import logging
import sys

from app.settings import settings
from app.sync import run_sync


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        result = run_sync()
    except Exception as e:  # noqa: BLE001 - top-level guard, report and fail
        logging.getLogger("impulse_sync").error("sync failed: %s", e)
        sys.exit(1)
    print(f"DONE - catalog refreshed at {settings.DB_PATH}: {result}")


if __name__ == "__main__":
    main()
