"""AI 효과음 생성(Stable Audio Open) 워커 관리: 상태 조회, 모델 내려받기, 워커 기동/종료, 생성 요청.

워커는 engine/sao/venv 의 파이썬으로 따로 실행되는 프로세스(engine/sao/worker.py)이며, 앱과는 127.0.0.1:8879 HTTP로만 통신한다.
토큰은 내려받기 프로세스의 환경변수로만 넘기고 어디에도 저장하거나 기록하지 않는다.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

PORT = 8879
BASE = f"http://127.0.0.1:{PORT}"


class AIError(Exception):
    pass


# 모델 목록(워커의 MODELS와 id·폴더가 같아야 한다). commercial=False 인 모델의 결과물은 출시(상업) 게임에 쓰면 안 된다.
MODELS: dict[str, dict] = {
    "sao": dict(name="Stable Audio Open 1.0", commercial=True, needs_token=True, dir="model", size_gb=4.7, max_seconds=12.0,
                license="Stability AI Community License — 연 매출 US$1M 미만이면 상업 이용 가능(무료)",
                license_url="https://huggingface.co/stabilityai/stable-audio-open-1.0",
                note="44.1kHz 스테레오, 최대 ~47초. HuggingFace 무료 계정으로 라이선스 동의 + Read 토큰 필요"),
    "audioldm2": dict(name="AudioLDM2-large", commercial=False, needs_token=False, dir="model_audioldm2", size_gb=6.0,
                      max_seconds=10.0, license="CC BY-NC-SA 4.0 — 비상업 전용(출시 게임에 사용 금지)",
                      license_url="https://huggingface.co/cvssp/audioldm2-large",
                      note="16kHz 모노, 최대 10초. 로그인 없이 내려받음. 음질은 Stable Audio Open보다 낮음"),
}


class AIManager:
    def __init__(self, engine_dir: Path):
        self.dir = Path(engine_dir)
        self.python = self.dir / "venv" / "Scripts" / "python.exe"
        self.worker = self.dir / "worker.py"
        self.model_dir = self.dir / "model"
        self._proc: subprocess.Popen | None = None
        self._dl: dict = {"state": "idle", "done": 0, "total": 0, "message": ""}
        self._dl_proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self.mock = bool(os.environ.get("GAMESFX_AI_MOCK"))

    # ---- 상태 ----
    @property
    def installed(self) -> bool:
        return self.python.exists() and self.worker.exists()

    def model_ready(self, model: str) -> bool:
        return self.mock or (self.dir / MODELS[model]["dir"] / "model_index.json").exists()

    def _worker_status(self) -> dict | None:
        try:
            with urllib.request.urlopen(BASE + "/status", timeout=1.5) as r:
                return json.loads(r.read())
        except (OSError, ValueError):
            return None

    def status(self) -> dict:
        w = self._worker_status()
        models = [{"id": k, **{f: v[f] for f in ("name", "commercial", "needs_token", "size_gb", "max_seconds", "license",
                                                    "license_url", "note")}, "ready": self.model_ready(k)}
                  for k, v in MODELS.items()]
        return {
            "installed": self.installed, "models": models, "model_ready": any(m["ready"] for m in models),
            "mock": self.mock, "worker_running": w is not None, "worker": w, "download": dict(self._dl),
        }

    # ---- 모델 내려받기 ----
    def start_download(self, model: str, token: str = "") -> None:
        if model not in MODELS:
            raise AIError(f"알 수 없는 모델입니다: {model}")
        token = token.strip()
        if MODELS[model]["needs_token"] and (not token.startswith("hf_") or len(token) < 20):
            raise AIError("HuggingFace 토큰 형식이 아닙니다. hf_ 로 시작하는 Read 토큰을 붙여넣으세요.")
        if not self.installed:
            raise AIError("AI 엔진이 설치되지 않았습니다. engine\\sao\\setup_ai.bat 을 먼저 실행하세요.")
        with self._lock:
            if self._dl["state"] == "running":
                raise AIError("이미 내려받는 중입니다.")
            self._dl = {"state": "running", "model": model, "done": 0, "total": 0, "message": "연결 중..."}
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HF_HUB_DISABLE_TELEMETRY": "1"}
        env.pop("HF_TOKEN", None)
        if token:
            env["HF_TOKEN"] = token  # 내려받기 프로세스의 환경변수로만 전달(저장·기록하지 않음)
        self._dl_proc = subprocess.Popen([str(self.python), str(self.worker), "--download", "--model", model], env=env,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                         encoding="utf-8", errors="replace", cwd=str(self.dir),
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._read_download, daemon=True).start()

    def _read_download(self) -> None:
        proc = self._dl_proc
        assert proc is not None and proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("PROGRESS"):
                _, done, total = line.split()
                self._dl.update(done=int(done), total=int(total), message="내려받는 중...")
            elif line.startswith("ERROR"):
                self._dl.update(state="error", message=line[6:])
            elif line == "DONE":
                self._dl.update(state="done", message="완료")
        proc.wait()
        if self._dl["state"] == "running":
            self._dl.update(state="error", message=f"내려받기가 중단되었습니다(코드 {proc.returncode}).")

    # ---- 워커 ----
    def start_worker(self, timeout: float = 240.0) -> None:
        if self._worker_status() is not None:
            return
        if not self.installed:
            raise AIError("AI 엔진이 설치되지 않았습니다. engine\\sao\\setup_ai.bat 을 먼저 실행하세요.")
        if not any(self.model_ready(m) for m in MODELS):
            raise AIError("AI 모델이 아직 없습니다. 설정 탭에서 내려받으세요.")
        cmd = [str(self.python), str(self.worker), "--port", str(PORT), "--parent-pid", str(os.getpid())]
        cmd += ["--mock"] if self.mock else []
        self._proc = subprocess.Popen(cmd, cwd=str(self.dir), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self._proc.poll() is not None:
                raise AIError("AI 워커가 시작 직후 종료되었습니다.")
            if self._worker_status() is not None:
                return
            time.sleep(0.5)
        raise AIError("AI 워커 시작 시간이 초과되었습니다.")

    def stop_worker(self) -> None:
        if self._worker_status() is not None:
            try:
                urllib.request.urlopen(urllib.request.Request(BASE + "/shutdown", data=b"", method="POST"), timeout=3).close()
            except OSError:
                pass
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def progress(self) -> dict:
        w = self._worker_status() or {}
        return {"step": w.get("step", 0), "steps": w.get("steps", 0), "busy": w.get("busy", False)}

    # ---- 생성 ----
    def generate(self, model: str, prompt: str, negative: str, seconds: float, steps: int, guidance: float,
                 seed: int) -> bytes:
        if model not in MODELS:
            raise AIError(f"알 수 없는 모델입니다: {model}")
        if not self.model_ready(model):
            raise AIError(f"{MODELS[model]['name']} 모델이 아직 없습니다. 설정 탭에서 내려받으세요.")
        self.start_worker()
        body = json.dumps({"model": model, "prompt": prompt, "negative": negative, "seconds": seconds, "steps": steps,
                           "guidance": guidance, "seed": seed}).encode()
        req = urllib.request.Request(BASE + "/generate", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get("detail", "")
            except ValueError:
                detail = ""
            raise AIError(detail or f"AI 워커 오류(HTTP {exc.code})") from exc
        except OSError as exc:
            raise AIError(f"AI 워커와 통신할 수 없습니다: {exc}") from exc


def trim_generated(audio: np.ndarray, sr: int) -> np.ndarray:
    """생성 결과의 앞뒤 무음을 잘라내고 끝에 짧은 페이드를 건다(모델은 지정 길이를 꽉 채워 무음/잡음을 붙이기 쉽다)."""
    mono = audio if audio.ndim == 1 else audio.mean(axis=1)
    peak = float(np.max(np.abs(mono))) or 1.0
    idx = np.nonzero(np.abs(mono) > peak * 0.003)[0]  # -50dB
    if len(idx) == 0:
        return audio
    start = max(0, int(idx[0]) - int(0.002 * sr))
    end = min(len(mono), int(idx[-1]) + int(0.05 * sr))
    out = audio[start:end].copy()
    fade = min(len(out), int(0.03 * sr))
    if fade:
        ramp = np.linspace(1, 0, fade)
        out[-fade:] *= ramp if out.ndim == 1 else ramp[:, None]
    return out
