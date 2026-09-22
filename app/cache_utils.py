"""앱 창(Edge 프로필) 캐시 크기 조회/초기화."""
from __future__ import annotations

import shutil
from pathlib import Path


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def cache_info(data_dir: Path) -> dict:
    return {"browser_cache_bytes": _dir_size(data_dir / "app_window_profile")}


def reset_browser_cache_now(data_dir: Path) -> bool:
    """브라우저가 프로필 폴더를 쓰는 동안은 지울 수 없으므로 앱 시작 시 창을 띄우기 전에만 호출한다."""
    profile_dir = data_dir / "app_window_profile"
    if not profile_dir.exists():
        return True
    try:
        shutil.rmtree(profile_dir)
        return True
    except OSError:
        return False
