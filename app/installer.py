"""처음 실행 설치 도우미: AI 엔진(Python venv + PyTorch + diffusers)을 사용자 동의를 받은 뒤 자동 설치한다.

설치하는 것과 원칙
  - Python 3.11~3.12: PC에 없을 때만, 사용자가 동의하면 python.org 공식 설치 파일(약 25MB)을 받아
    **PSF(Python Software Foundation) 디지털 서명을 검증한 뒤** 사용자 폴더에 조용히 설치한다(관리자 권한·PATH 변경 없음).
  - engine/sao/venv : 표준 venv
  - PyTorch 2.6.0 : NVIDIA GPU가 있으면 CUDA 12.4 빌드, 없으면 CPU 빌드
  - requirements-ai.txt : 검증된 정확한 버전 고정 목록
  - 설치는 항상 사용자의 명시적 요청으로만 시작하고, 진행 로그를 보여주며, 언제든 취소할 수 있다.
  - 이미 있는 Python/venv는 건드리지 않고 재사용한다. NVIDIA 드라이버처럼 자동 설치할 수 없는 것은 안내만 한다.

GAMESFX_SETUP_DRYRUN=1 이면 실제 설치 없이 단계만 흉내 낸다(화면 테스트용).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from paths import bundled_resource

PY_VERSIONS = ((3, 12), (3, 11))  # 우선순위 순서. numpy 2.4는 3.11+, torch 2.6은 3.13 휠이 없다
PY_INSTALLER_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
PY_INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "Python" / "Python311"
TORCH_VERSION = "2.6.0"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# 엔진 설치 + 모델 두 개를 모두 받았을 때 필요한 대략적인 여유 공간(GB)
NEEDED_GB = {"engine": 6.0, "models": 11.0}


# venv 폴더 경로 길이 한도. 설치 후 가장 깊은 파일(torch\include\ATen\ops\..._dispatch.h)이 상대 경로로 135자라서,
# Windows 기본 한도(MAX_PATH=260)를 넘지 않으려면 venv 루트는 124자 이하여야 한다. 여유를 두어 115자로 잡는다.
MAX_VENV_ROOT = 115


def long_paths_enabled() -> bool:
    """Windows 긴 경로 지원(LongPathsEnabled=1)이 켜져 있으면 260자 제한이 없다."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
            return bool(winreg.QueryValueEx(key, "LongPathsEnabled")[0])
    except (OSError, ImportError):
        return False


def _run(cmd: list[str], timeout: float = 20.0) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW,
                              encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None


def probe_python(exe: str | Path) -> tuple[int, int] | None:
    """exe가 '진짜 독립 설치본 Python 3.11~3.12'이면 (major, minor), 아니면 None.
    venv 안의 python(다른 프로젝트 것)은 사라질 수 있어 제외한다."""
    if "WindowsApps" in str(exe):  # Microsoft Store 스텁: 실행하면 스토어가 열리므로 건드리지 않는다
        return None
    r = _run([str(exe), "-c", "import sys;print(sys.version_info[0],sys.version_info[1],sys.prefix==sys.base_prefix)"])
    if r is None or r.returncode != 0:
        return None
    try:
        major, minor, standalone = r.stdout.split()
    except ValueError:
        return None
    ver = (int(major), int(minor))
    return ver if standalone == "True" and ver in PY_VERSIONS else None


def find_python() -> dict | None:
    """설치된 Python 3.11~3.12를 찾는다. {path, version, source} 또는 None."""
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roaming = Path(os.environ.get("APPDATA", ""))
    cands: list[tuple[str, str]] = []
    for major, minor in PY_VERSIONS:  # py 런처
        r = _run(["py", f"-{major}.{minor}", "-c", "import sys;print(sys.executable)"])
        if r and r.returncode == 0 and r.stdout.strip():
            cands.append((r.stdout.strip(), "py launcher"))
    tag = {"3.12": "Python312", "3.11": "Python311"}
    for v in tag.values():  # 표준 설치 위치
        for base in (local / "Programs" / "Python", Path("C:/Program Files"), Path("C:/")):
            cands.append((str(base / v / "python.exe"), "installed"))
    for pat in ("cpython-3.12*", "cpython-3.11*"):  # uv가 관리하는 독립 Python
        for p in sorted((roaming / "uv" / "python").glob(pat + "/python.exe"), reverse=True) if roaming.name else []:
            cands.append((str(p), "uv"))
    for name in ("python", "python3"):  # PATH
        found = shutil.which(name)
        if found:
            cands.append((found, "PATH"))
    seen: set[str] = set()
    for path, source in cands:
        key = os.path.normcase(path)
        if key in seen or not Path(path).exists():
            continue
        seen.add(key)
        ver = probe_python(path)
        if ver:
            return {"path": path, "version": f"{ver[0]}.{ver[1]}", "source": source}
    return None


def gpu_info() -> dict | None:
    r = _run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"], 6)
    if r and r.returncode == 0 and r.stdout.strip():
        parts = [p.strip() for p in r.stdout.strip().splitlines()[0].split(",")]
        if len(parts) >= 3:
            try:
                return {"name": parts[0], "vram_gb": round(float(parts[1]) / 1024, 1), "driver": parts[2]}
            except ValueError:
                pass
    return None


def verify_signature(path: Path) -> tuple[bool, str]:
    """Authenticode 서명이 유효하고 서명자가 Python Software Foundation인지 확인한다."""
    ps = ("$s = Get-AuthenticodeSignature -LiteralPath '{}'; "
          "Write-Output $s.Status; Write-Output $s.SignerCertificate.Subject").format(str(path).replace("'", "''"))
    r = _run(["powershell", "-NoProfile", "-Command", ps], 60)
    if r is None or r.returncode != 0:
        return False, "서명 확인을 실행하지 못했습니다."
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    ok = len(lines) >= 2 and lines[0] == "Valid" and "Python Software Foundation" in lines[1]
    return ok, (lines[1] if ok else f"서명이 올바르지 않습니다({' / '.join(lines[:2])}).")


def ensure_engine_files(engine_dir: Path) -> None:
    """exe 하나만 받은 사용자를 위해: exe 안에 들어 있는 worker.py / requirements-ai.txt 를 engine/sao/ 에 풀어 놓는다.
    항상 exe와 같은 버전으로 맞춘다(소스 실행 때는 번들이 없으므로 아무것도 하지 않는다)."""
    src = bundled_resource("engine_bundle")
    if not src.is_dir():
        return
    engine_dir.mkdir(parents=True, exist_ok=True)
    for name in ("worker.py", "requirements-ai.txt"):
        s, d = src / name, engine_dir / name
        if s.exists() and (not d.exists() or d.read_bytes() != s.read_bytes()):
            shutil.copy2(s, d)


class SetupManager:
    def __init__(self, engine_dir: Path):
        # resolve(): Windows 8.3 짧은 이름 경로(AISW_A~1 등)를 실제 긴 경로로 바꾼다. 짧은 이름을 그대로 venv/ensurepip에 넘기면
        # "Actual environment location may have moved" 오류로 가상환경 만들기가 실패한다.
        self.dir = Path(engine_dir).resolve()
        self.python = self.dir / "venv" / "Scripts" / "python.exe"
        self.marker = self.dir / ".engine_installed.json"
        # 시험 모드: 1=실제 설치 없이 단계만 흉내(엔진은 '없음'에서 시작), nopython=Python도 없는 PC를 흉내
        self.dry_mode = os.environ.get("GAMESFX_SETUP_DRYRUN", "")
        self.dry = bool(self.dry_mode)
        self._dry_done = False
        self._job: dict = {"state": "idle", "step": 0, "steps": 0, "label": "", "log": []}
        self._proc: subprocess.Popen | None = None
        self._cancel = threading.Event()
        self._engine_check: tuple[float, dict] | None = None

    # ------------------------------------------------------------ 상태
    def engine_state(self) -> dict:
        """venv에서 torch/diffusers를 실제로 불러보고 결과를 30초간 캐시한다."""
        if self.dry:
            return {"venv": self._dry_done, "ok": self._dry_done, "cuda": True, "torch": "2.6.0 (test)", "diffusers": "test"}
        now = time.time()
        if self._engine_check and now - self._engine_check[0] < 30:
            return self._engine_check[1]
        state = {"venv": self.python.exists(), "ok": False, "cuda": False, "torch": "", "diffusers": ""}
        if state["venv"]:
            r = _run([str(self.python), "-c",
                      "import torch,diffusers,transformers;print(torch.__version__);print(torch.cuda.is_available());print(diffusers.__version__)"], 90)
            if r and r.returncode == 0:
                lines = r.stdout.split()
                if len(lines) >= 3:
                    state.update(ok=True, torch=lines[0], cuda=lines[1] == "True", diffusers=lines[2])
        self._engine_check = (now, state)
        return state

    def path_check(self) -> dict:
        n = len(str(self.dir / "venv"))
        return {"len": n, "max": MAX_VENV_ROOT, "ok": n <= MAX_VENV_ROOT or long_paths_enabled()}

    def status(self) -> dict:
        free = shutil.disk_usage(self.dir if self.dir.exists() else Path.cwd()).free / 1e9
        return {
            "platform_ok": sys.platform == "win32",
            "gpu": gpu_info(),
            "path": self.path_check(),
            "python": None if self.dry_mode == "nopython" else find_python(),
            "engine": self.engine_state(),
            "disk_free_gb": round(free, 1), "needed_gb": NEEDED_GB,
            "job": self.job(),
            "python_installer": {"url": PY_INSTALLER_URL, "size_mb": 25, "signer": "Python Software Foundation"},
            "dry_run": self.dry,
        }

    def job(self) -> dict:
        j = dict(self._job)
        j["log"] = list(self._job["log"][-60:])
        return j

    # ------------------------------------------------------------ 설치
    def _log(self, line: str) -> None:
        line = line.rstrip()
        if line:
            self._job["log"].append(line[:400])
            del self._job["log"][:-500]

    def start_engine_install(self, allow_python_install: bool) -> None:
        if self._job["state"] == "running":
            raise RuntimeError("이미 설치가 진행 중입니다.")
        if sys.platform != "win32":
            raise RuntimeError("자동 설치는 Windows에서만 지원합니다.")
        pc = self.path_check()
        if not self.dry and not pc["ok"]:
            raise RuntimeError(
                f"프로그램 폴더 경로가 너무 깁니다({pc['len']}자, 한도 {pc['max']}자). Windows 경로 길이 제한 때문에 PyTorch를 설치할 수 없어요. "
                "프로그램 폴더를 C:\\GameSfxStudio 처럼 짧은 경로로 옮긴 뒤 다시 실행하세요.")
        self._cancel.clear()
        self._job = {"state": "running", "step": 0, "steps": 6, "label": "준비 중", "log": [], "error": ""}
        threading.Thread(target=self._install_engine, args=(allow_python_install,), daemon=True).start()

    def cancel(self) -> None:
        self._cancel.set()
        if self._proc and self._proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(self._proc.pid), "/T", "/F"], capture_output=True,
                           creationflags=NO_WINDOW)

    def _step(self, n: int, label: str) -> None:
        if self._cancel.is_set():
            raise InterruptedError
        self._job.update(step=n, label=label)
        self._log(f"=== [{n}/{self._job['steps']}] {label}")

    def _stream(self, cmd: list[str], cwd: Path | None = None) -> None:
        self._log("$ " + " ".join(cmd)[:300])
        self._proc = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
                                      env={**os.environ, "PYTHONIOENCODING": "utf-8", "PIP_DISABLE_PIP_VERSION_CHECK": "1"})
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            self._log(re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line))
        code = self._proc.wait()
        if self._cancel.is_set():
            raise InterruptedError
        if code != 0:
            raise RuntimeError(f"명령이 실패했습니다(코드 {code}): {' '.join(cmd)[:120]}")

    def _install_python(self) -> dict:
        dst = Path(tempfile.gettempdir()) / "gamesfx-python-3.11.9-amd64.exe"
        self._log(f"Python 설치 파일 내려받는 중: {PY_INSTALLER_URL}")
        with urllib.request.urlopen(PY_INSTALLER_URL, timeout=60) as r, open(dst, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while chunk := r.read(1 << 20):
                if self._cancel.is_set():
                    raise InterruptedError
                f.write(chunk)
                done += len(chunk)
                self._job["label"] = f"Python 내려받는 중 {done / 1e6:.0f}/{total / 1e6:.0f} MB"
        ok, detail = verify_signature(dst)
        if not ok:
            dst.unlink(missing_ok=True)
            raise RuntimeError("Python 설치 파일의 디지털 서명을 확인하지 못해 설치하지 않았습니다: " + detail)
        self._log(f"서명 확인 완료: {detail}")
        self._log(f"Python 3.11 설치 중(사용자 폴더, 관리자 권한 불필요): {PY_INSTALL_DIR}")
        self._stream([str(dst), "/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_launcher=0", "Include_test=0",
                      "Include_doc=0", "Shortcuts=0", f"TargetDir={PY_INSTALL_DIR}"])
        dst.unlink(missing_ok=True)
        found = find_python()
        if not found:
            raise RuntimeError("Python을 설치했지만 찾을 수 없습니다.")
        return found

    def _install_engine(self, allow_python_install: bool) -> None:
        j = self._job
        try:
            if self.dry:
                return self._dry_run()
            self._step(1, "Python 확인")
            py = find_python()
            if py:
                self._log(f"Python {py['version']} 사용: {py['path']}")
            elif allow_python_install:
                py = self._install_python()
            else:
                raise RuntimeError("Python 3.11~3.12가 없습니다. 'Python 자동 설치'에 동의하거나 python.org에서 직접 설치해주세요.")
            if not (self.dir / "requirements-ai.txt").exists():
                raise RuntimeError("engine/sao/requirements-ai.txt 를 찾을 수 없습니다(프로그램 폴더가 손상되었습니다).")

            self._step(2, "가상환경 만들기")
            if self.python.exists() and _run([str(self.python), "-c", "import sys"]):
                self._log("기존 가상환경을 재사용합니다.")
            else:
                shutil.rmtree(self.dir / "venv", ignore_errors=True)
                self._stream([py["path"], "-m", "venv", str(self.dir / "venv")])
            vpy = str(self.python)

            self._step(3, "pip 준비")
            self._stream([vpy, "-m", "pip", "install", "--upgrade", "pip"])

            gpu = gpu_info()
            self._step(4, "PyTorch 설치 (" + ("CUDA 12.4, NVIDIA GPU용, 약 2.5GB" if gpu else "CPU용 — NVIDIA GPU 없음") + ")")
            index = "https://download.pytorch.org/whl/" + ("cu124" if gpu else "cpu")
            self._stream([vpy, "-m", "pip", "install", f"torch=={TORCH_VERSION}", f"torchaudio=={TORCH_VERSION}",
                          "--index-url", index])

            self._step(5, "AI 라이브러리 설치 (diffusers, transformers …)")
            self._stream([vpy, "-m", "pip", "install", "-r", str(self.dir / "requirements-ai.txt")])

            self._step(6, "설치 확인")
            self._engine_check = None
            st = self.engine_state()
            if not st["ok"]:
                raise RuntimeError("설치는 끝났지만 torch/diffusers를 불러오지 못했습니다. 로그를 확인하세요.")
            self._log(f"확인 완료: torch {st['torch']} (CUDA {'사용 가능' if st['cuda'] else '없음 — CPU로 동작(느림)'}), diffusers {st['diffusers']}")
            self.marker.write_text(json.dumps({"torch": st["torch"], "cuda": st["cuda"], "diffusers": st["diffusers"],
                                               "python": py["version"]}), encoding="utf-8")
            j.update(state="done", label="설치 완료")
        except InterruptedError:
            j.update(state="cancelled", label="취소됨")
            self._log("사용자가 취소했습니다.")
        except Exception as exc:  # noqa: BLE001 - 어떤 실패든 화면에 이유를 보여준다
            j.update(state="error", error=str(exc), label="실패")
            self._log("오류: " + str(exc))
        finally:
            self._engine_check = None

    def _dry_run(self) -> None:
        for n, label in enumerate(["Python 확인", "가상환경 만들기", "pip 준비", "PyTorch 설치", "AI 라이브러리 설치", "설치 확인"], 1):
            self._step(n, label)
            for i in range(5):
                if self._cancel.is_set():
                    raise InterruptedError
                self._log(f"(시험) {label} … {i + 1}/5")
                time.sleep(0.25)
        self._dry_done = True
        self._job.update(state="done", label="설치 완료(시험)")
