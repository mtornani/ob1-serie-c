import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.satarch import run_scan


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    run_scan(lat=45.0, lon=10.0, size=10)
