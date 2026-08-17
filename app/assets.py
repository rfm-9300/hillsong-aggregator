"""Intro / ending clips used to package the final sermon video."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.config import ASSETS_DIR, ensure_dirs

Kind = Literal["intro", "outro"]
KINDS: tuple[Kind, ...] = ("intro", "outro")


@dataclass
class Asset:
    id: str
    kind: Kind
    filename: str
    path: str
    title: str
    created_at: str

    @property
    def file_path(self) -> Path:
        return Path(self.path)

    @property
    def exists(self) -> bool:
        return self.file_path.is_file()

    @property
    def display_title(self) -> str:
        return (self.title or "").strip() or self.filename or self.id


@dataclass
class EditConfig:
    assets: list[Asset]
    active_intro_id: str | None
    active_outro_id: str | None

    def assets_of(self, kind: Kind) -> list[Asset]:
        return [a for a in self.assets if a.kind == kind]

    def get(self, asset_id: str | None) -> Asset | None:
        if not asset_id:
            return None
        for asset in self.assets:
            if asset.id == asset_id:
                return asset
        return None

    @property
    def active_intro(self) -> Asset | None:
        asset = self.get(self.active_intro_id)
        return asset if asset and asset.kind == "intro" and asset.exists else None

    @property
    def active_outro(self) -> Asset | None:
        asset = self.get(self.active_outro_id)
        return asset if asset and asset.kind == "outro" and asset.exists else None


def edit_path() -> Path:
    from app.config import DATA_DIR

    return DATA_DIR / "edit.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_edit() -> EditConfig:
    ensure_dirs()
    path = edit_path()
    if not path.is_file():
        return EditConfig(assets=[], active_intro_id=None, active_outro_id=None)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return EditConfig(assets=[], active_intro_id=None, active_outro_id=None)
    if not isinstance(raw, dict):
        return EditConfig(assets=[], active_intro_id=None, active_outro_id=None)

    assets: list[Asset] = []
    for item in raw.get("assets") or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind not in KINDS:
            continue
        asset_id = str(item.get("id") or "").strip()
        file_path = str(item.get("path") or "").strip()
        if not asset_id or not file_path:
            continue
        assets.append(
            Asset(
                id=asset_id,
                kind=kind,  # type: ignore[arg-type]
                filename=str(item.get("filename") or Path(file_path).name),
                path=file_path,
                title=str(item.get("title") or ""),
                created_at=str(item.get("created_at") or ""),
            )
        )

    intro_id = raw.get("active_intro_id")
    outro_id = raw.get("active_outro_id")
    return EditConfig(
        assets=assets,
        active_intro_id=str(intro_id) if intro_id else None,
        active_outro_id=str(outro_id) if outro_id else None,
    )


def save_edit(config: EditConfig) -> None:
    ensure_dirs()
    payload: dict[str, Any] = {
        "active_intro_id": config.active_intro_id,
        "active_outro_id": config.active_outro_id,
        "assets": [
            {
                "id": asset.id,
                "kind": asset.kind,
                "filename": asset.filename,
                "path": asset.path,
                "title": asset.title,
                "created_at": asset.created_at,
            }
            for asset in config.assets
        ],
    }
    path = edit_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def add_asset(*, kind: Kind, source: Path, filename: str, title: str = "") -> Asset:
    if kind not in KINDS:
        raise ValueError(f"Unknown asset kind: {kind}")
    ensure_dirs()
    asset_id = uuid.uuid4().hex
    suffix = source.suffix.lower() or ".mp4"
    dest = ASSETS_DIR / f"{kind}_{asset_id}{suffix}"
    shutil.copy2(source, dest)
    asset = Asset(
        id=asset_id,
        kind=kind,
        filename=filename,
        path=str(dest),
        title=(title or Path(filename).stem).strip(),
        created_at=_utc_now(),
    )
    config = load_edit()
    config.assets.append(asset)
    if kind == "intro" and not config.active_intro_id:
        config.active_intro_id = asset.id
    if kind == "outro" and not config.active_outro_id:
        config.active_outro_id = asset.id
    save_edit(config)
    return asset


def set_active(kind: Kind, asset_id: str | None) -> EditConfig:
    config = load_edit()
    if asset_id:
        asset = config.get(asset_id)
        if asset is None or asset.kind != kind:
            raise ValueError(f"No {kind} asset with id {asset_id}")
    if kind == "intro":
        config.active_intro_id = asset_id
    else:
        config.active_outro_id = asset_id
    save_edit(config)
    return config


def delete_asset(asset_id: str) -> None:
    config = load_edit()
    asset = config.get(asset_id)
    if asset is None:
        raise ValueError("Asset not found")
    config.assets = [a for a in config.assets if a.id != asset_id]
    if config.active_intro_id == asset_id:
        config.active_intro_id = None
    if config.active_outro_id == asset_id:
        config.active_outro_id = None
    save_edit(config)
    try:
        asset.file_path.unlink(missing_ok=True)
    except OSError:
        pass


def active_package_paths() -> tuple[Path | None, Path | None, dict[str, str | None]]:
    """Return (intro, outro, meta) for the currently selected branding clips."""
    config = load_edit()
    intro = config.active_intro
    outro = config.active_outro
    meta = {
        "intro_id": intro.id if intro else None,
        "outro_id": outro.id if outro else None,
        "intro_title": intro.display_title if intro else None,
        "outro_title": outro.display_title if outro else None,
    }
    return (
        intro.file_path if intro else None,
        outro.file_path if outro else None,
        meta,
    )
