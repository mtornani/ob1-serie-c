# SAT-ARCH: Satellite Archaeology Scanner

## Obiettivo
Rilevare strutture archeologiche romane e proto-romane nella Pianura Padana usando immagini satellitari免费 + AI.

## Stack
- Python 3.12
- Sentinelsat o custom download per Sentinel-2 (10m, gratuito)
- OpenCV per image processing classico
- YOLOv8 per object detection
- Folium per mappa interattiva

## Architettura

### 1. Downloader (`src/satarch/downloader.py`)
- Scarica immagini Sentinel-2 da Copernicus Open Access Hub
- Bbox configurabile (default: Pianura Padana)
- Filtro cloud < 15%
- Output: GeoTIFF

### 2. Processor Classico (`src/satarch/classic.py`)
- **Edge Detection**: Canny + Sobel
- **Hough Transform**: rileva linee parallele (strade romane), rettangoli (insulae)
- **NDVI Analysis**: anomalie vegetazione che indicano strutture sepolte
- **Color segmentation**: identifica terreni coltivati diversi

### 3. Processor AI (`src/satarch/detector.py`)
- YOLOv8 fine-tuned su siti archeologici (modello pre-addestrato)
- Rileva: strade, mura, edifici, necropoli
- Output: bounding boxes con confidence

### 4. Fuser (`src/satarch/fuser.py`)
- Combina risultati classici + AI
- Deduplicazione con NMS
- Scoring basato su:
  - Confidenza AI
  - Presenza pattern geometrici multipli
  - Correlazione anomalie NDVI

### 5. UI (`src/satarch/ui.py`)
- Mappa Folium con marker colorati per tipo
- Popup con dettagli + screenshot
- Filtri per tipo struttura
- Esportazione GeoJSON

## Configurazione (`config/satarch.yaml`)
```yaml
area:
  bbox: [7.0, 44.0, 12.5, 46.5]  # Pianura Padana
sentinel:
  product_type: S2
  cloud_cover: 15
  date_range: ["2020-01-01", "2024-12-31"]
detection:
  hough_threshold: 100
  ndvi_threshold: 0.3
ai:
  model: yolov8x
  conf_threshold: 0.5
```

## Output
- `data/satarch/results.json` - risultati strutturati
- `data/satarch/map.html` - mappa interattiva
- `data/satarch/tiles/` - immagini processate

## Workflow
1. Download aree con copertura satellite recente
2. Processa con metodi classici in parallelo
3. Run AI detector su tile
4. Combina e filtra risultati
5. Genera mappa HTML con export GeoJSON
