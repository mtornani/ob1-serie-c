import logging
import argparse
from pathlib import Path

from .models import Config
from .downloader import SatelliteDownloader
from .classic import ClassicProcessor
from .detector import AIDetector
from .fuser import ResultFuser
from .ui import ResultViewer


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_scan(
    config_path: str = "config/satarch.yaml",
    lat: float = None,
    lon: float = None,
    size: float = 10,
    skip_download: bool = False,
    skip_ai: bool = False,
):
    """
    Esegue la scansione completa.
    """
    config = Config.load(config_path)
    logger.info(f"Starting SAT-ARCH scan for {config.name}")

    output_dir = Path(config.output["results_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    if lat is None:
        lat = (config.bbox[1] + config.bbox[3]) / 2
    if lon is None:
        lon = (config.bbox[0] + config.bbox[2]) / 2

    downloader = SatelliteDownloader(config.output["tiles_dir"])

    if not skip_download:
        logger.info(f"Downloading satellite data for ({lat}, {lon})")
        tile_path = downloader.download_sample_area(lat, lon, size)
    else:
        tiles = list(Path(config.output["tiles_dir"]).glob("*.tif"))
        if not tiles:
            logger.error("No tiles found. Run with download enabled.")
            return
        tile_path = tiles[0]

    logger.info(f"Processing tile: {tile_path}")

    classic_processor = ClassicProcessor(config)
    classic_results = classic_processor.process_tile(tile_path)
    logger.info(f"Classic processor found {len(classic_results)} detections")

    ai_results = []
    if not skip_ai:
        ai_detector = AIDetector(config)
        ai_results = ai_detector.process_tile(tile_path)
        logger.info(f"AI detector found {len(ai_results)} detections")

    fuser = ResultFuser(config)
    fused_results = fuser.fuse(classic_results, ai_results)
    logger.info(f"Fused results: {len(fused_results)} unique detections")

    viewer = ResultViewer(config)

    viewer.create_map(
        fused_results,
        output_dir / config.output["map_file"],
    )

    fuser.to_json(
        fused_results,
        output_dir / "results.json",
    )

    fuser.to_geojson(
        fused_results,
        output_dir / "results.geojson",
    )

    viewer.create_dashboard(fused_results, output_dir)

    logger.info(f"Results saved to {output_dir}")

    return fused_results


def main():
    parser = argparse.ArgumentParser(
        description="SAT-ARCH: Satellite Archaeology Scanner"
    )
    parser.add_argument(
        "--config", default="config/satarch.yaml", help="Config file path"
    )
    parser.add_argument("--lat", type=float, help="Latitude center")
    parser.add_argument("--lon", type=float, help="Longitude center")
    parser.add_argument("--size", type=float, default=10, help="Tile size in km")
    parser.add_argument(
        "--skip-download", action="store_true", help="Skip download, use existing tiles"
    )
    parser.add_argument("--skip-ai", action="store_true", help="Skip AI detection")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    run_scan(
        config_path=args.config,
        lat=args.lat,
        lon=args.lon,
        size=args.size,
        skip_download=args.skip_download,
        skip_ai=args.skip_ai,
    )


if __name__ == "__main__":
    main()
