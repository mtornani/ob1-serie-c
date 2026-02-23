import logging
from pathlib import Path
from typing import Optional
import numpy as np
import cv2
import rasterio

from .models import Config, DetectionResult


logger = logging.getLogger(__name__)

try:
    from ultralytics import YOLO

    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    logger.warning("YOLO not available. Install with: pip install ultralytics")


CLASS_NAMES = {
    0: "building_ruins",
    1: "wall",
    2: "road_ancient",
    3: "structure_circular",
    4: "structure_rectangular",
    5: " necropolis",
    6: "archaeological_site",
}


class AIDetector:
    def __init__(self, config: Config):
        self.config = config
        self.ai_config = config.ai
        self.model = None

        if YOLO_AVAILABLE:
            model_name = self.ai_config.get("model", "yolov8x")
            try:
                self.model = YOLO(f"{model_name}.pt")
                logger.info(f"Loaded YOLO model: {model_name}")
            except Exception as e:
                logger.warning(f"Could not load YOLO model: {e}")

    def process_tile(self, tile_path: Path) -> list[DetectionResult]:
        """
        Processa una tile con YOLO.
        """
        if not self.model:
            logger.warning("YOLO not available, using simulated detections")
            return self._simulate_detections(tile_path)

        logger.info(f"Running AI detection on: {tile_path}")

        results = []

        with rasterio.open(tile_path) as src:
            data = src.read([1, 2, 3])
            transform = src.transform
            rgb = np.stack([data[0], data[1], data[2]], axis=2)
            rgb = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        try:
            detections = self.model(
                rgb,
                conf=self.ai_config.get("conf_threshold", 0.5),
                iou=self.ai_config.get("iou_threshold", 0.4),
                verbose=False,
            )[0]

            for det in detections.boxes:
                x1, y1, x2, y2 = det.xyxy[0].cpu().numpy()
                conf = float(det.conf[0].cpu())
                cls_id = int(det.cls[0].cpu())

                col = (x1 + x2) / 2
                row = (y1 + y2) / 2

                lon, lat = transform * (col, row)

                class_name = CLASS_NAMES.get(cls_id, f"class_{cls_id}")

                results.append(
                    DetectionResult(
                        lat=lat,
                        lon=lon,
                        type=class_name,
                        confidence=conf,
                        source="ai_yolo",
                        description=f"{class_name} (AI, conf: {conf:.2f})",
                        bbox=[int(x1), int(y1), int(x2), int(y2)],
                        tile_path=str(tile_path),
                    )
                )

        except Exception as e:
            logger.error(f"YOLO inference failed: {e}")
            return self._simulate_detections(tile_path)

        logger.info(f"AI found {len(results)} detections")
        return results

    def _simulate_detections(self, tile_path: Path) -> list[DetectionResult]:
        """
        Simula detections per test senza modello YOLO.
        """
        import random

        random.seed(42)

        results = []

        with rasterio.open(tile_path) as src:
            transform = src.transform
            width = src.width
            height = src.height

        for _ in range(random.randint(1, 4)):
            col = random.randint(100, width - 100)
            row = random.randint(100, height - 100)
            lon, lat = transform * (col, row)

            types = [
                "building_ruins",
                "road_ancient",
                "structure_rectangular",
                "archaeological_site",
            ]

            results.append(
                DetectionResult(
                    lat=lat,
                    lon=lon,
                    type=random.choice(types),
                    confidence=random.uniform(0.5, 0.9),
                    source="ai_simulated",
                    description="Simulated detection for testing",
                )
            )

        return results


def process_tile(tile_path: Path, config: Config) -> list[DetectionResult]:
    """Funzione di utilità per processare una tile con AI."""
    detector = AIDetector(config)
    return detector.process_tile(tile_path)
