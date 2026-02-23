import logging
from pathlib import Path
from typing import Optional
import json
from collections import defaultdict
import numpy as np
from scipy.spatial.distance import cdist

from .models import Config, DetectionResult


logger = logging.getLogger(__name__)


class ResultFuser:
    def __init__(self, config: Config):
        self.config = config
        self.iou_threshold = 0.3

    def fuse(
        self,
        classic_results: list[DetectionResult],
        ai_results: list[DetectionResult],
    ) -> list[DetectionResult]:
        """
        Combina risultati classici e AI, rimuovendo duplicati.
        """
        all_results = classic_results + ai_results

        if not all_results:
            return []

        all_results = self._apply_nms(all_results)

        all_results = self._score_results(all_results)

        all_results.sort(key=lambda x: x.confidence, reverse=True)

        return all_results

    def _apply_nms(
        self,
        results: list[DetectionResult],
    ) -> list[DetectionResult]:
        """
        Non-Maximum Suppression per rimuovere detections sovrapposte.
        """
        if len(results) <= 1:
            return results

        coords = np.array([[r.lat, r.lon] for r in results])

        distances = cdist(coords, coords)

        keep = []
        removed = set()

        sorted_indices = np.argsort([r.confidence for r in results])[::-1]

        for i in sorted_indices:
            if i in removed:
                continue

            keep.append(i)

            for j in sorted_indices:
                if i == j or j in removed:
                    continue

                dist = distances[i, j]

                if dist < 0.005:
                    removed.add(j)

        return [results[i] for i in keep]

    def _score_results(self, results: list[DetectionResult]) -> list[DetectionResult]:
        """
        Ricalcola confidence basandosi su:
        - Fonte (AI > classic)
        - Tipo di struttura
        - Co-occorrenza con altri findings
        """
        source_boost = {
            "ai_yolo": 0.15,
            "ai_simulated": 0.0,
            "classic_hough": 0.1,
            "classic_ndvi": 0.05,
            "classic_contour": 0.08,
        }

        type_weight = {
            "roman_road": 0.15,
            "insula": 0.12,
            "enclosure": 0.1,
            "road_candidate": 0.05,
            "ndvi_anomaly": 0.0,
        }

        for r in results:
            boost = source_boost.get(r.source, 0) + type_weight.get(r.type, 0)
            r.confidence = min(0.99, r.confidence + boost)

        return results

    def to_geojson(
        self,
        results: list[DetectionResult],
        output_path: Optional[Path] = None,
    ) -> dict:
        """
        Esporta risultati in GeoJSON.
        """
        features = []

        for r in results:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [r.lon, r.lat],
                },
                "properties": {
                    "type": r.type,
                    "confidence": round(r.confidence, 3),
                    "source": r.source,
                    "description": r.description,
                },
            }

            if r.bbox:
                feature["properties"]["bbox"] = r.bbox

            features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "features": features,
        }

        if output_path:
            with open(output_path, "w") as f:
                json.dump(geojson, f, indent=2)
            logger.info(f"Saved GeoJSON to {output_path}")

        return geojson

    def to_json(
        self,
        results: list[DetectionResult],
        output_path: Optional[Path] = None,
    ) -> list[dict]:
        """
        Esporta risultati in JSON semplice.
        """
        data = [
            {
                "lat": r.lat,
                "lon": r.lon,
                "type": r.type,
                "confidence": round(r.confidence, 3),
                "source": r.source,
                "description": r.description,
            }
            for r in results
        ]

        if output_path:
            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved results to {output_path}")

        return data


def fuse_results(
    classic: list[DetectionResult],
    ai: list[DetectionResult],
    config: Config,
) -> list[DetectionResult]:
    """Funzione di utilità per fondere risultati."""
    fuser = ResultFuser(config)
    return fuser.fuse(classic, ai)
