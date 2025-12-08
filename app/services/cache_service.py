# app/services/cache_service.py
import hashlib
import json
from sqlalchemy.orm import Session
from app.core.database import ProcessedImage
from app.utils.logging import logger, console


def generate_cache_key(image: str, landmarks: list, seg_map: str) -> str:
    data = f"{image[:100]}{json.dumps(landmarks[:5])}{seg_map[:100]}"
    return hashlib.sha256(data.encode()).hexdigest()


def get_cached_result(cache_key: str, db: Session):
    try:
        row = db.query(ProcessedImage).filter_by(cache_key=cache_key).first()
        if not row:
            console.log(f"[yellow]○ Cache MISS for {cache_key[:12]}[/yellow]")
            return None
        console.log(f"[green]✓ Cache HIT for {cache_key[:12]}[/green]")
        return json.loads(row.svg_result)
    except Exception as e:
        logger.error(f"Cache lookup error: {e}")
        return None


def cache_result(cache_key: str, payload: dict, db: Session) -> bool:
    try:
        row = ProcessedImage(cache_key=cache_key, svg_result=json.dumps(payload))
        db.add(row)
        db.commit()
        console.log(f"[green]✓ Cached result for {cache_key[:12]}[/green]")
        return True
    except Exception as e:
        logger.error(f"Cache store error: {e}")
        db.rollback()
        return False
  