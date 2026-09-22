"""프로젝트(게임 하나 = 효과음 묶음)와 그 안에 저장된 효과음(spec json + wav)을 관리한다.

    projects/<이름>/project.json         {name, description, export_dir, created_at, updated_at}
    projects/<이름>/sounds/<id>.json     {id, name, category, tags, spec, sample_rate, duration, ...}
    projects/<이름>/sounds/<id>.wav
"""
from __future__ import annotations

import io
import json
import re
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from sfx import engine, samples

_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _validate_name(name: str, what: str) -> None:
    if not name:
        raise ValueError(f"{what} 이름을 입력하세요.")
    if _UNSAFE_CHARS.search(name):
        raise ValueError(f'{what} 이름에는 \\ / : * ? " < > | 문자를 쓸 수 없습니다.')
    if name.startswith(".") or name != name.rstrip(" ."):
        raise ValueError(f"{what} 이름을 그렇게 지을 수 없습니다.")
    if len(name) > 50:
        raise ValueError(f"{what} 이름은 50자 이하로 지어주세요.")
    if name.upper() in _RESERVED:
        raise ValueError(f"'{name}'은(는) Windows 예약어라 쓸 수 없습니다.")


def safe_filename(name: str) -> str:
    """효과음 이름을 내보내기용 파일명(확장자 제외)으로 바꾼다."""
    s = _UNSAFE_CHARS.sub("_", name).strip(" .") or "sfx"
    return f"_{s}" if s.upper() in _RESERVED else s[:80]


class ProjectStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- 프로젝트 ----
    def project_dir(self, name: str) -> Path:
        _validate_name(name, "프로젝트")
        return self.root / name

    def _sounds_dir(self, name: str) -> Path:
        return self.project_dir(name) / "sounds"

    def list_projects(self) -> list[dict]:
        out = []
        for p in sorted(self.root.iterdir(), key=lambda p: p.name.lower()):
            meta = p / "project.json"
            if p.is_dir() and meta.exists():
                data = json.loads(meta.read_text(encoding="utf-8"))
                data["count"] = len(list((p / "sounds").glob("*.json"))) if (p / "sounds").exists() else 0
                out.append(data)
        return out

    def exists(self, name: str) -> bool:
        return (self.project_dir(name) / "project.json").exists()

    def create_project(self, name: str, description: str = "") -> dict:
        name = name.strip()
        d = self.project_dir(name)
        if d.exists():
            raise ValueError(f"이미 '{name}' 프로젝트가 존재합니다.")
        (d / "sounds").mkdir(parents=True)
        data = {"name": name, "description": description, "export_dir": "", "created_at": _now(), "updated_at": _now()}
        self._write_meta(name, data)
        return data

    def load_project(self, name: str) -> dict:
        path = self.project_dir(name) / "project.json"
        if not path.exists():
            raise FileNotFoundError(f"'{name}' 프로젝트를 찾을 수 없습니다.")
        return json.loads(path.read_text(encoding="utf-8"))

    def update_project(self, name: str, description: str | None = None, export_dir: str | None = None) -> dict:
        data = self.load_project(name)
        if description is not None:
            data["description"] = description
        if export_dir is not None:
            export_dir = export_dir.strip()
            if export_dir and not Path(export_dir).is_absolute():
                raise ValueError("내보내기 폴더는 C:\\... 처럼 전체 경로로 적어주세요.")
            data["export_dir"] = export_dir
        data["updated_at"] = _now()
        self._write_meta(name, data)
        return data

    def delete_project(self, name: str) -> None:
        d = self.project_dir(name)
        if d.exists() and (d / "project.json").exists():
            shutil.rmtree(d)

    def _write_meta(self, name: str, data: dict) -> None:
        (self.project_dir(name) / "project.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 효과음 ----
    def _sound_paths(self, project: str, sound_id: str) -> tuple[Path, Path]:
        if not re.fullmatch(r"[0-9a-f]{6,32}", sound_id):
            raise ValueError("잘못된 효과음 ID입니다.")
        d = self._sounds_dir(project)
        return d / f"{sound_id}.json", d / f"{sound_id}.wav"

    def list_sounds(self, project: str) -> list[dict]:
        d = self._sounds_dir(project)
        if not d.exists():
            return []
        items = []
        for f in d.glob("*.json"):
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            rec.pop("spec", None)  # 목록에서는 무거운 spec 제외(개별 조회 때 반환)
            items.append(rec)
        return sorted(items, key=lambda r: r.get("created_at", ""), reverse=True)

    def get_sound(self, project: str, sound_id: str) -> dict:
        meta_path, _ = self._sound_paths(project, sound_id)
        if not meta_path.exists():
            raise FileNotFoundError("효과음을 찾을 수 없습니다.")
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def save_sound(self, project: str, name: str, spec: dict, sample_rate: int, category: str = "",
                   tags: list[str] | None = None, sound_id: str | None = None) -> dict:
        """새 효과음을 저장하거나(sound_id 없음) 기존 것을 덮어쓴다(sound_id 있음)."""
        name = name.strip()
        _validate_name(name, "효과음")
        if not self.exists(project):
            raise FileNotFoundError(f"'{project}' 프로젝트를 찾을 수 없습니다.")
        spec = engine.normalize_spec(spec)
        wav_bytes, duration = engine.render_wav(spec, sample_rate)

        if sound_id:
            meta_path, wav_path = self._sound_paths(project, sound_id)
            old = self.get_sound(project, sound_id)
            created = old.get("created_at", _now())
        else:
            sound_id = uuid.uuid4().hex[:10]
            meta_path, wav_path = self._sound_paths(project, sound_id)
            created = _now()

        rec = {"id": sound_id, "name": name, "category": category, "tags": tags or [], "spec": spec,
               "sample_rate": sample_rate, "duration": round(duration, 3), "created_at": created,
               "updated_at": _now(), "noncommercial": samples.spec_uses_noncommercial(spec)}
        wav_path.write_bytes(wav_bytes)
        meta_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        return {k: v for k, v in rec.items() if k != "spec"}

    def rename_sound(self, project: str, sound_id: str, name: str) -> dict:
        name = name.strip()
        _validate_name(name, "효과음")
        rec = self.get_sound(project, sound_id)
        rec["name"] = name
        rec["updated_at"] = _now()
        meta_path, _ = self._sound_paths(project, sound_id)
        meta_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        return {k: v for k, v in rec.items() if k != "spec"}

    def delete_sound(self, project: str, sound_id: str) -> None:
        for p in self._sound_paths(project, sound_id):
            p.unlink(missing_ok=True)

    def sound_wav_path(self, project: str, sound_id: str) -> Path:
        return self._sound_paths(project, sound_id)[1]

    # ---- 내보내기 ----
    def _export_entries(self, project: str) -> list[tuple[str, Path]]:
        """(내보낼 파일명, 원본 wav 경로). 같은 이름은 _2, _3 … 을 붙여 구분한다."""
        used: dict[str, int] = {}
        entries = []
        for rec in sorted(self.list_sounds(project), key=lambda r: r.get("created_at", "")):
            base = safe_filename(rec["name"])
            key = base.lower()
            used[key] = used.get(key, 0) + 1
            fname = f"{base}.wav" if used[key] == 1 else f"{base}_{used[key]}.wav"
            wav = self.sound_wav_path(project, rec["id"])
            if wav.exists():
                entries.append((fname, wav))
        return entries

    def export_to_folder(self, project: str, target: str | None = None) -> dict:
        proj = self.load_project(project)
        target = (target or proj.get("export_dir") or "").strip()
        dest = Path(target) if target else self.project_dir(project) / "export"
        if not dest.is_absolute():
            raise ValueError("내보내기 폴더는 C:\\... 처럼 전체 경로로 적어주세요.")
        dest.mkdir(parents=True, exist_ok=True)
        entries = self._export_entries(project)
        for fname, src in entries:
            shutil.copy2(src, dest / fname)
        nc = [r["name"] for r in self.list_sounds(project) if r.get("noncommercial")]
        return {"dir": str(dest), "count": len(entries), "noncommercial": len(nc), "noncommercial_names": nc[:20]}

    def export_zip(self, project: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for fname, src in self._export_entries(project):
                z.write(src, fname)
        return buf.getvalue()
