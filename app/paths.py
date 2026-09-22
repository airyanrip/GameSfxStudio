"""실행 위치(일반 파이썬 스크립트 vs PyInstaller onefile exe)에 따라
프로젝트 루트와 리소스 경로를 일관되게 계산한다.
"""
from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    """projects/, data/ 처럼 '실행 파일과 나란히' 있어야 하는 데이터의 기준 경로.

    onefile exe로 패키징된 경우 sys.executable이 실제 exe 위치
    (예: F:\\GameSfxStudio\\GameSfxStudio.exe)이므로 이를 기준으로 삼는다.
    일반 파이썬 실행이면 이 파일의 상위 폴더(app/)의 부모를 기준으로 삼는다.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_resource(relative: str) -> Path:
    """static/ 처럼 exe 안에 '내장'되는 읽기 전용 리소스의 경로.

    PyInstaller onefile exe는 실행 시 임시 폴더(sys._MEIPASS)에 리소스를 풀어놓으므로
    그 경로를 사용해야 한다.
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS"))
    else:
        base = Path(__file__).resolve().parent
    return base / relative
