"""'내 프리셋': 참고 음원에서 배운 spec이나 직접 다듬은 소리를 이름·그룹과 함께 저장한다(data/user_presets.json).

같은 group에 여러 개를 모아두면(예: 'gun_cinematic' 에 총소리 여러 개) '그룹에서 무작위'로 매번 조금씩 다른
소리를 뽑아 실제 효과음 라이브러리처럼 쓸 수 있다.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from sfx import engine


class UserPresetStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def list(self) -> list[dict]:
        return self._read()

    def add(self, name: str, spec: dict, group: str = "", note: str = "") -> dict:
        name = name.strip()
        if not name or len(name) > 50:
            raise ValueError("프리셋 이름은 1~50자로 입력하세요.")
        rec = {"id": uuid.uuid4().hex[:10], "name": name, "group": group.strip()[:50], "note": note[:200],
               "spec": engine.normalize_spec(spec), "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        with self._lock:
            items = self._read()
            items.append(rec)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        return rec

    def delete(self, preset_id: str) -> None:
        with self._lock:
            items = [p for p in self._read() if p["id"] != preset_id]
            self.path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
