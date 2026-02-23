from dataclasses import dataclass
from typing import Optional
import yaml


@dataclass
class Config:
    bbox: list[float]
    name: str
    sentinel: dict
    detection: dict
    ai: dict
    output: dict
    patterns: dict

    @classmethod
    def load(cls, path: str = "config/satarch.yaml") -> "Config":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(
            bbox=data["area"]["bbox"],
            name=data["area"]["name"],
            sentinel=data["sentinel"],
            detection=data["detection"],
            ai=data["ai"],
            output=data["output"],
            patterns=data["patterns"],
        )


@dataclass
class DetectionResult:
    lat: float
    lon: float
    type: str
    confidence: float
    source: str
    description: str
    bbox: Optional[list] = None
    tile_path: Optional[str] = None
