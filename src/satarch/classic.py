import logging
from pathlib import Path
from typing import Optional
import numpy as np
import cv2
import rasterio
from rasterio.windows import Window
from scipy import ndimage

from .models import Config, DetectionResult


logger = logging.getLogger(__name__)


class ClassicProcessor:
    def __init__(self, config: Config):
        self.config = config
        self.detection = config.detection

    def process_tile(self, tile_path: Path) -> list[DetectionResult]:
        """
        Processa una tile con metodi classici.
        """
        logger.info(f"Processing tile: {tile_path}")

        results = []

        with rasterio.open(tile_path) as src:
            data = src.read([1, 2, 3])
            transform = src.transform

            rgb = np.stack([data[0], data[1], data[2]], axis=2)

            if src.count >= 8:
                nir = data[7]
                red = data[3]
                ndvi = self._calculate_ndvi(nir, red)
                results.extend(self._detect_ndvi_anomalies(ndvi, transform))

            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

            results.extend(self._detect_roman_roads(gray, transform))
            results.extend(self._detect_insulae(gray, transform))
            results.extend(self._detect_enclosures(gray, transform))

        logger.info(f"Found {len(results)} classic detections")
        return results

    def _calculate_ndvi(self, nir: np.ndarray, red: np.ndarray) -> np.ndarray:
        """Calcola NDVI: (NIR - RED) / (NIR + RED)"""
        nir = nir.astype(float)
        red = red.astype(float)

        denominator = nir + red
        ndvi = np.where(denominator != 0, (nir - red) / denominator, 0)

        return np.clip(ndvi, -1, 1)

    def _detect_ndvi_anomalies(
        self,
        ndvi: np.ndarray,
        transform,
    ) -> list[DetectionResult]:
        """
        Rileva anomalie NDVI che potrebbero indicare strutture sepolte.
        Strutture sepolte spesso mostrano NDVI diverso dal terreno circostante.
        """
        threshold = self.detection["ndvi_threshold"]
        lower = self.detection.get("ndvi_lower_threshold", -0.1)

        mask = (ndvi > lower) & (ndvi < threshold)

        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)

        labeled, num_features = ndimage.label(mask)

        results = []
        for i in range(1, num_features + 1):
            positions = np.where(labeled == i)
            if len(positions[0]) < 10:
                continue

            row, col = np.mean(positions[0]), np.mean(positions[1])

            lon, lat = transform * (col, row)

            confidence = min(0.9, 0.3 + (len(positions[0]) / 1000))

            results.append(
                DetectionResult(
                    lat=lat,
                    lon=lon,
                    type="ndvi_anomaly",
                    confidence=confidence,
                    source="classic_ndvi",
                    description=f"Anomalia NDVI: {len(positions[0])} pixel",
                )
            )

        return results

    def _detect_roman_roads(
        self,
        gray: np.ndarray,
        transform,
    ) -> list[DetectionResult]:
        """
        Rileva strade romane: linee parallele dritte.
        """
        canny_low = self.detection["canny_low"]
        canny_high = self.detection["canny_high"]

        edges = cv2.Canny(gray, canny_low, canny_high)

        hough_thresh = self.detection["hough_threshold"]
        min_length = self.detection.get("hough_min_line_length", 50)
        max_gap = self.detection.get("hough_max_line_gap", 10)

        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=hough_thresh,
            minLineLength=min_length,
            maxLineGap=max_gap,
        )

        if lines is None:
            return []

        results = []
        for line in lines:
            x1, y1, x2, y2 = line[0]

            length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            if length < min_length:
                continue

            angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
            if angle > 5 and angle < 175:
                continue

            col = (x1 + x2) / 2
            row = (y1 + y2) / 2

            lon, lat = transform * (col, row)

            results.append(
                DetectionResult(
                    lat=lat,
                    lon=lon,
                    type="road_candidate",
                    confidence=min(0.8, 0.4 + length / 500),
                    source="classic_hough",
                    description=f"Linea retta: {int(length)}m",
                    bbox=[x1, y1, x2, y2],
                )
            )

        results = self._filter_parallel_roads(results)

        return results

    def _filter_parallel_roads(
        self,
        roads: list[DetectionResult],
    ) -> list[DetectionResult]:
        """
        Filtra linee parallele (strade romane tipiche).
        """
        if len(roads) < 2:
            return roads

        parallel = []
        for i, r1 in enumerate(roads):
            for r2 in roads[i + 1 :]:
                dist = np.sqrt((r1.lat - r2.lat) ** 2 + (r1.lon - r2.lon) ** 2)

                if dist < 0.01:
                    avg_conf = (r1.confidence + r2.confidence) / 2

                    parallel.append(
                        DetectionResult(
                            lat=(r1.lat + r2.lat) / 2,
                            lon=(r1.lon + r2.lon) / 2,
                            type="roman_road",
                            confidence=min(0.95, avg_conf + 0.2),
                            source="classic_hough",
                            description="Doppia linea parallela - possibile via romana",
                        )
                    )

        return parallel

    def _detect_insulae(
        self,
        gray: np.ndarray,
        transform,
    ) -> list[DetectionResult]:
        """
        Rileva insulae (blocchi romani): rettangoli.
        """
        edges = cv2.Canny(gray, 50, 150)

        contours, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        results = []
        for cnt in contours:
            if cv2.contourArea(cnt) < 1000:
                continue

            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

            if len(approx) == 4:
                x, y, w, h = cv2.boundingRect(approx)
                aspect_ratio = float(w) / h if h > 0 else 0

                if 0.7 < aspect_ratio < 1.3:
                    col = x + w // 2
                    row = y + h // 2

                    lon, lat = transform * (col, row)

                    results.append(
                        DetectionResult(
                            lat=lat,
                            lon=lon,
                            type="insula",
                            confidence=min(0.85, 0.5 + cv2.contourArea(cnt) / 20000),
                            source="classic_contour",
                            description=f"Struttura rettangolare: {int(w)}x{int(h)}m",
                            bbox=[x, y, x + w, y + h],
                        )
                    )

        return results

    def _detect_enclosures(
        self,
        gray: np.ndarray,
        transform,
    ) -> list[DetectionResult]:
        """
        Rileva recinti: forme chiuse (circoli, ovali).
        """
        edges = cv2.Canny(gray, 50, 150)

        contours, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        results = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 500:
                continue

            peri = cv2.arcLength(cnt, True)
            if peri == 0:
                continue

            circularity = 4 * np.pi * area / (peri * peri)

            if circularity > 0.7:
                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])

                    lon, lat = transform * (cx, cy)

                    results.append(
                        DetectionResult(
                            lat=lat,
                            lon=lon,
                            type="enclosure",
                            confidence=min(0.9, circularity * 0.9),
                            source="classic_contour",
                            description=f"Struttura circolare, area: {int(area)}mq",
                        )
                    )

        return results


def process_tile(tile_path: Path, config: Config) -> list[DetectionResult]:
    """Funzione di utilità per processare una tile."""
    processor = ClassicProcessor(config)
    return processor.process_tile(tile_path)
