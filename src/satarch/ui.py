import logging
from pathlib import Path
from typing import Optional
import folium
from folium.plugins import MarkerCluster, Draw
import json

from .models import Config, DetectionResult


logger = logging.getLogger(__name__)

TYPE_ICONS = {
    "roman_road": {"color": "red", "icon": "road"},
    "road_candidate": {"color": "orange", "icon": "road"},
    "insula": {"color": "blue", "icon": "home"},
    "enclosure": {"color": "purple", "icon": "stop"},
    "ndvi_anomaly": {"color": "green", "icon": "leaf"},
    "building_ruins": {"color": "gray", "icon": "home"},
    "structure_rectangular": {"color": "blue", "icon": "square"},
    "structure_circular": {"color": "purple", "icon": "circle"},
    "archaeological_site": {"color": "darkred", "icon": "info-sign"},
    "road_ancient": {"color": "red", "icon": "road"},
    "necropolis": {"color": "black", "icon": "star"},
}

TYPE_LABELS = {
    "roman_road": "Via Romana",
    "road_candidate": "Candidato strada",
    "insula": "Insula",
    "enclosure": "Recinto",
    "ndvi_anomaly": "Anomalia NDVI",
    "building_ruins": "Ruderi",
    "structure_rectangular": "Struttura rettangolare",
    "structure_circular": "Struttura circolare",
    "archaeological_site": "Sito archeologico",
    "road_ancient": "Strada antica",
    "necropolis": "Necropoli",
}


class ResultViewer:
    def __init__(self, config: Config):
        self.config = config

    def create_map(
        self,
        results: list[DetectionResult],
        output_path: Optional[Path] = None,
    ) -> folium.Map:
        """
        Crea una mappa Folium con i risultati.
        """
        if not results:
            logger.warning("No results to display")
            center = [
                (self.config.bbox[1] + self.config.bbox[3]) / 2,
                (self.config.bbox[0] + self.config.bbox[2]) / 2,
            ]
            m = folium.Map(location=center, zoom_start=6)
            return m

        lats = [r.lat for r in results]
        lons = [r.lon for r in results]
        center = [sum(lats) / len(lats), sum(lons) / len(lons)]

        m = folium.Map(location=center, zoom_start=10)

        folium.TileLayer("Esri World Imagery").add_to(m)

        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri",
            name="Satellite",
        ).add_to(m)

        folium.LayerControl().add_to(m)

        by_type = {}
        for r in results:
            if r.type not in by_type:
                by_type[r.type] = []
            by_type[r.type].append(r)

        for type_name, detections in by_type.items():
            feature_group = folium.FeatureGroup(
                name=TYPE_LABELS.get(type_name, type_name)
            )

            icon_info = TYPE_ICONS.get(type_name, {"color": "gray", "icon": "info"})

            for r in detections:
                color = icon_info["color"]
                icon_name = icon_info["icon"]

                popup_html = f"""
                <div style="width: 200px">
                    <h4 style="margin: 0">{TYPE_LABELS.get(r.type, r.type)}</h4>
                    <b>Confidenza:</b> {r.confidence:.1%}<br>
                    <b>Fonte:</b> {r.source}<br>
                    <b>Desc:</b> {r.description}<br>
                    <b>Coord:</b> {r.lat:.5f}, {r.lon:.5f}
                </div>
                """

                folium.Marker(
                    location=[r.lat, r.lon],
                    popup=folium.Popup(popup_html, max_width=250),
                    tooltip=f"{r.type} ({r.confidence:.0%})",
                    icon=folium.Icon(color=color, icon=icon_name, prefix="fa"),
                ).add_to(feature_group)

            feature_group.add_to(m)

        if output_path:
            m.save(str(output_path))
            logger.info(f"Saved map to {output_path}")

        return m

    def create_dashboard(
        self,
        results: list[DetectionResult],
        output_dir: Path,
    ) -> None:
        """
        Crea una dashboard HTML completa.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        map_path = output_dir / "map.html"
        self.create_map(results, map_path)

        summary = self._create_summary(results)

        by_source = {}
        by_type = {}
        for r in results:
            by_source[r.source] = by_source.get(r.source, 0) + 1
            by_type[r.type] = by_type.get(r.type, 0) + 1

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>SAT-ARCH: Risultati Archeologia Satellitare</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body {{ padding: 20px; background: #1a1a2e; color: #eee; }}
        .card {{ background: #16213e; border: none; margin-bottom: 20px; }}
        .card-header {{ background: #0f3460; font-weight: bold; }}
        .stat-number {{ font-size: 2em; font-weight: bold; color: #e94560; }}
        .type-badge {{ 
            padding: 5px 10px; margin: 2px; border-radius: 15px;
            font-size: 0.8em;
        }}
        .conf-high {{ background: #28a745; }}
        .conf-medium {{ background: #ffc107; color: #000; }}
        .conf-low {{ background: #dc3545; }}
    </style>
</head>
<body>
    <div class="container-fluid">
        <h1><i class="fas fa-satellite"></i> SAT-ARCH: Scanner Archeologia Satellitare</h1>
        <p class="lead">{self.config.name} - {len(results)} anomalie rilevate</p>
        
        <div class="row">
            <div class="col-md-3">
                <div class="card">
                    <div class="card-header">Totale Rilevazioni</div>
                    <div class="card-body text-center">
                        <div class="stat-number">{len(results)}</div>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <div class="card-header">Alta Confidenza</div>
                    <div class="card-body text-center">
                        <div class="stat-number">{sum(1 for r in results if r.confidence >= 0.7)}</div>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <div class="card-header">Rilevazioni AI</div>
                    <div class="card-body text-center">
                        <div class="stat-number">{sum(1 for r in results if "ai" in r.source)}</div>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <div class="card-header">Tipi Rilevati</div>
                    <div class="card-body text-center">
                        <div class="stat-number">{len(by_type)}</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="row">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">Per Tipo</div>
                    <div class="card-body">
                        {"".join(f'<span class="type-badge" style="background: {TYPE_ICONS.get(t, {"color": "gray"})["color"]}">{TYPE_LABELS.get(t, t)}: {c}</span>' for t, c in sorted(by_type.items(), key=lambda x: -x[1]))}
                    </div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">Per Fonte</div>
                    <div class="card-body">
                        {"".join(f'<span class="type-badge bg-secondary">{s}: {c}</span>' for s, c in sorted(by_source.items(), key=lambda x: -x[1]))}
                    </div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">Mappa Interattiva</div>
            <div class="card-body p-0">
                <iframe src="map.html" style="width: 100%; height: 600px; border: none;"></iframe>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">Dettaglio Rilevazioni</div>
            <div class="card-body">
                <table class="table table-dark table-striped">
                    <thead>
                        <tr>
                            <th>Tipo</th>
                            <th>Confidenza</th>
                            <th>Fonte</th>
                            <th>Coordinate</th>
                            <th>Descrizione</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(f'<tr><td>{TYPE_LABELS.get(r.type, r.type)}</td><td><span class="conf-{"high" if r.confidence >= 0.7 else "medium" if r.confidence >= 0.5 else "low"}">{r.confidence:.1%}</span></td><td>{r.source}</td><td>{r.lat:.5f}, {r.lon:.5f}</td><td>{r.description}</td></tr>' for r in sorted(results, key=lambda x: -x.confidence)[:50])}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>"""

        index_path = output_dir / "index.html"
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"Dashboard created at {index_path}")

    def _create_summary(self, results: list[DetectionResult]) -> dict:
        """Crea un sommario dei risultati."""
        return {
            "total": len(results),
            "high_confidence": sum(1 for r in results if r.confidence >= 0.7),
            "by_type": {},
            "by_source": {},
        }


def create_viewer(config: Config) -> ResultViewer:
    return ResultViewer(config)
