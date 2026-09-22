"""앱 전역 설정(언어, 샘플레이트, 미리듣기 볼륨, 자동 재생, 캐시 정리 예약)을 저장/조회한다."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sfx.engine import SAMPLE_RATES

DEFAULT_SETTINGS: dict[str, Any] = {
    "language": "ko",  # ko, en
    "sample_rate": 44100,  # 저장/내보내기 WAV 샘플레이트
    "preview_volume": 0.8,  # 0.0~1.0, 미리듣기 볼륨(프론트엔드에서만 사용)
    "auto_preview": True,  # 값을 바꿀 때마다 자동으로 다시 재생
    "reset_browser_cache_on_next_launch": False,
    "setup_seen": False,  # 첫 실행 설치 도우미를 이미 보여줬는가
}

_ALLOWED_LANGUAGES = {"ko", "en"}


class SettingsStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_SETTINGS)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_SETTINGS)
        merged = dict(DEFAULT_SETTINGS)
        merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
        return merged

    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.load()

        if "language" in updates:
            if updates["language"] not in _ALLOWED_LANGUAGES:
                raise ValueError(f"지원하지 않는 언어입니다: {updates['language']}")
            current["language"] = updates["language"]

        if "sample_rate" in updates:
            rate = int(updates["sample_rate"])
            if rate not in SAMPLE_RATES:
                raise ValueError(f"지원하지 않는 샘플레이트입니다: {rate}")
            current["sample_rate"] = rate

        if "preview_volume" in updates:
            current["preview_volume"] = max(0.0, min(1.0, float(updates["preview_volume"])))

        for key in ("auto_preview", "reset_browser_cache_on_next_launch", "setup_seen"):
            if key in updates:
                current[key] = bool(updates[key])

        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        return current
