from app.config import settings
from app.parameters.schema import BOM, COC


def save_bom(bom: BOM) -> None:
    dest = settings.bom_dir / f"{bom.bom_id}.json"
    dest.write_text(bom.model_dump_json(indent=2))


def load_bom(bom_id: str) -> BOM | None:
    path = settings.bom_dir / f"{bom_id}.json"
    if not path.exists():
        return None
    return BOM.model_validate_json(path.read_text())


def _load_all_boms() -> list[BOM]:
    return [BOM.model_validate_json(p.read_text()) for p in settings.bom_dir.glob("*.json")]


def list_boms() -> list[BOM]:
    return sorted(_load_all_boms(), key=lambda b: b.uploaded_at, reverse=True)


def get_active_bom(project_id: str) -> BOM | None:
    active = [b for b in _load_all_boms() if b.project_id == project_id and b.status == "active"]
    if not active:
        return None
    return max(active, key=lambda b: b.version)


def get_next_bom_version(project_id: str) -> tuple[int, BOM | None]:
    """Returns (next_version, prior_active_bom_or_None). Storage is flat
    JSON files scanned per call — fine at this scale; swap for an indexed
    DB if BOM volume grows."""
    prior = get_active_bom(project_id)
    return ((prior.version + 1) if prior else 1), prior


def save_coc(coc: COC) -> None:
    dest = settings.coc_dir / f"{coc.coc_id}.json"
    dest.write_text(coc.model_dump_json(indent=2))


def load_coc(coc_id: str) -> COC | None:
    path = settings.coc_dir / f"{coc_id}.json"
    if not path.exists():
        return None
    return COC.model_validate_json(path.read_text())


def list_cocs_for_bom(bom_id: str) -> list[COC]:
    cocs = [COC.model_validate_json(p.read_text()) for p in settings.coc_dir.glob("*.json")]
    cocs = [c for c in cocs if c.bom_id == bom_id]
    return sorted(cocs, key=lambda c: c.uploaded_at, reverse=True)
