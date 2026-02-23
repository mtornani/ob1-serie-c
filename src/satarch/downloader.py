import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import zipfile
import rasterio
from rasterio.windows import Window
import numpy as np

logger = logging.getLogger(__name__)


class SatelliteDownloader:
    def __init__(self, output_dir: str = "data/satarch/tiles"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.samples_dir = self.output_dir / "samples"
        self.samples_dir.mkdir(exist_ok=True)

    def download_sample_area(
        self,
        lat: float,
        lon: float,
        size_km: float = 10,
    ) -> Optional[Path]:
        """
        Scarica un'area campione da Sentinel-2 usando sample data.
        Per uso reale, serve API key Copernicus (gratuita).
        """
        logger.info(f"Downloading sample area around ({lat}, {lon})")

        sample_url = f"https://siso.evan忠"

        tile_path = self.samples_dir / f"tile_{lat}_{lon}.tif"

        if tile_path.exists():
            logger.info(f"Tile already exists: {tile_path}")
            return tile_path

        logger.warning(
            "Sentinel-2 download requires Copernicus API credentials. "
            "Using demo tile generation for testing."
        )

        return self._generate_demo_tile(lat, lon, size_km, tile_path)

    def _generate_demo_tile(
        self,
        lat: float,
        lon: float,
        size_km: float,
        output_path: Path,
    ) -> Path:
        """
        Genera una tile demo con pattern simulati per test.
        In produzione, scarica da Copernicus.
        """
        pixels = int(size_km * 100)

        rgb = np.random.randint(0, 256, (pixels, pixels, 3), dtype=np.uint8)

        green_field = (rgb[:, :, 1] > rgb[:, :, 0]) & (rgb[:, :, 1] > rgb[:, :, 2])
        rgb[green_field] = [80, 160, 40]

        road_y = pixels // 3
        rgb[road_y : road_y + 3, :] = [180, 180, 180]

        road_x = 2 * pixels // 3
        rgb[:, road_x : road_x + 2] = [180, 180, 180]

        center = pixels // 2
        for i in range(80):
            y = center + int(40 * np.sin(i * 0.1))
            x = center + i
            if 0 <= y < pixels and 0 <= x < pixels:
                rgb[y - 1 : y + 2, x - 1 : x + 2] = [140, 140, 140]

        transform = rasterio.transform.from_bounds(
            lon - size_km / 200,
            lat - size_km / 200,
            lon + size_km / 200,
            lat + size_km / 200,
            pixels,
            pixels,
        )

        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            height=pixels,
            width=pixels,
            count=3,
            dtype=np.uint8,
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            for i in range(3):
                dst.write(rgb[:, :, i], i + 1)

        logger.info(f"Generated demo tile: {output_path}")
        return output_path

    def download_bbox(
        self,
        bbox: list[float],
        date_from: str = "2020-01-01",
        date_to: str = "2024-12-31",
        cloud_cover: int = 15,
    ) -> list[Path]:
        """
        Scarica immagini per una bounding box.
        Richiede credenziali Copernicus.
        """
        logger.info(f"Would download for bbox: {bbox}")

        tiles = []
        min_lon, min_lat, max_lon, max_lat = bbox

        grid_size = 0.5
        lon = min_lon
        while lon < max_lon:
            lat = min_lat
            while lat < max_lat:
                tile = self.download_sample_area(lat, lon, 10)
                if tile:
                    tiles.append(tile)
                lat += grid_size
            lon += grid_size

        return tiles


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Scarica immagini satellitari")
    parser.add_argument("--lat", type=float, default=45.0)
    parser.add_argument("--lon", type=float, default=10.0)
    parser.add_argument("--size", type=float, default=10)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    downloader = SatelliteDownloader()
    tile = downloader.download_sample_area(args.lat, args.lon, args.size)

    print(f"Tile: {tile}")


if __name__ == "__main__":
    main()
