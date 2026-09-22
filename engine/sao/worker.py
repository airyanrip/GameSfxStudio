"""텍스트→효과음 AI 워커 (모델 선택식).

이 스크립트는 앱 본체와 별도 프로세스(engine/sao/venv, torch+diffusers 포함)로 실행된다.

  서버:   venv\\Scripts\\python worker.py --port 8879 [--mock]
  받기:   venv\\Scripts\\python worker.py --download --model sao        (HF_TOKEN 환경변수 필요: 토큰은 어디에도 저장하지 않음)
          venv\\Scripts\\python worker.py --download --model audioldm2  (로그인 불필요)

모델
  sao        Stable Audio Open 1.0 — Stability AI Community License(연 매출 US$1M 미만 상업 이용 가능). 44.1kHz 스테레오, 최대 ~47초.
             HuggingFace에서 무료 계정으로 라이선스에 동의하고 Read 토큰이 있어야 내려받는다(게이트, 자동 승인·무료).
  audioldm2  AudioLDM2-large — CC BY-NC-SA 4.0: 비상업 전용. 로그인 없이 내려받는다. 16kHz 모노, 최대 10초.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

MODELS: dict[str, dict] = {
    "sao": dict(repo="stabilityai/stable-audio-open-1.0", dir="model", gated=True, commercial=True, max_seconds=12.0,
                guidance=7.0, ignore=["model.safetensors", "*.ckpt", "model_config.json", "*.msgpack", "*.h5", "*.onnx"]),
    "audioldm2": dict(repo="cvssp/audioldm2-large", dir="model_audioldm2", gated=False, commercial=False, max_seconds=10.0,
                      guidance=3.5, ignore=["*.bin", "*.ckpt", "*.h5", "*.msgpack", "*.onnx", "*.md"]),
}


def model_dir(model: str) -> Path:
    return HERE / MODELS[model]["dir"]


def model_present(model: str) -> bool:
    return (model_dir(model) / "model_index.json").exists()


# ------------------------------------------------------------------ 모델 내려받기
def download(model: str) -> int:
    from huggingface_hub import HfApi, snapshot_download
    from huggingface_hub.utils import GatedRepoError, HfHubHTTPError

    spec = MODELS[model]
    token = os.environ.get("HF_TOKEN") or None
    if spec["gated"] and not token:
        print("ERROR 이 모델은 HuggingFace 토큰이 필요합니다.", flush=True)
        return 2
    ignore, target = spec["ignore"], model_dir(model)
    denied = ("ERROR 접근이 거부되었습니다(401/403). 토큰이 올바른 Read 토큰인지, 그리고 이 모델 페이지에서 "
              "라이선스에 동의했는지 확인하세요: https://huggingface.co/" + spec["repo"])
    try:
        info = HfApi().model_info(spec["repo"], token=token, files_metadata=True)
        total = sum((s.size or 0) for s in info.siblings if not any(Path(s.rfilename).match(p) for p in ignore)) or 1
    except (GatedRepoError, HfHubHTTPError) as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        print(denied if isinstance(exc, GatedRepoError) or code in (401, 403) else f"ERROR HuggingFace 응답 {code}", flush=True)
        return 3

    stop = threading.Event()

    def report() -> None:
        while not stop.is_set():
            done = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) if target.exists() else 0
            print(f"PROGRESS {min(done, total)} {total}", flush=True)
            stop.wait(1.5)

    threading.Thread(target=report, daemon=True).start()
    try:
        snapshot_download(spec["repo"], local_dir=str(target), token=token, ignore_patterns=ignore)
    except (GatedRepoError, HfHubHTTPError) as exc:
        stop.set()
        code = getattr(getattr(exc, "response", None), "status_code", None)
        print(denied if isinstance(exc, GatedRepoError) or code in (401, 403) else f"ERROR 다운로드 실패(HTTP {code}): {exc}", flush=True)
        return 3
    except Exception as exc:  # noqa: BLE001
        stop.set()
        print(f"ERROR 다운로드 실패: {exc}", flush=True)
        return 4
    stop.set()
    print(f"PROGRESS {total} {total}", flush=True)
    print("DONE", flush=True)
    return 0


# ------------------------------------------------------------------ 생성
class Generator:
    def __init__(self, mock: bool):
        self.mock = mock
        self.pipe = None
        self.loaded_model: str | None = None
        self.lock = threading.Lock()
        self.progress = {"step": 0, "steps": 0, "busy": False}
        self.device = "mock" if mock else "cpu"

    def _load(self, model: str) -> None:
        if self.loaded_model == model:
            return
        import torch

        self.unload()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        if model == "sao":
            from diffusers import StableAudioPipeline as Pipe
        else:
            from diffusers import AudioLDM2Pipeline as Pipe
        self.pipe = Pipe.from_pretrained(str(model_dir(model)), torch_dtype=dtype).to(self.device)
        self.loaded_model = model

    def unload(self) -> None:
        if self.pipe is not None:
            import torch

            self.pipe = None
            self.loaded_model = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def generate(self, model: str, prompt: str, negative: str, seconds: float, steps: int, guidance: float,
                 seed: int) -> tuple[np.ndarray, int]:
        """(오디오 float32 (n, ch), 샘플레이트)"""
        with self.lock:
            self.progress = {"step": 0, "steps": steps, "busy": True}
            try:
                if self.mock:
                    return self._mock(model, seconds, steps, seed)
                self._load(model)
                import torch

                gen = torch.Generator(self.device).manual_seed(seed)

                def cb(step: int, _timestep, _latents) -> None:  # diffusers 0.40 두 파이프라인 공통 콜백 형식
                    self.progress["step"] = step + 1

                common = dict(prompt=prompt, negative_prompt=negative or None, num_inference_steps=steps,
                              guidance_scale=guidance, num_waveforms_per_prompt=1, generator=gen,
                              callback=cb, callback_steps=1)
                if model == "sao":
                    audio = self.pipe(audio_end_in_s=seconds, **common).audios[0].T.float().cpu().numpy()  # (n, 2)
                    sr = 44100
                else:
                    audio = np.asarray(self.pipe(audio_length_in_s=seconds, **common).audios[0], dtype=np.float32)
                    audio = audio[:, None]                                                                  # (n, 1)
                    sr = 16000
                return audio[: int(seconds * sr)], sr
            finally:
                self.progress["busy"] = False

    def _mock(self, model: str, seconds: float, steps: int, seed: int) -> tuple[np.ndarray, int]:
        """모델 없이 파이프라인만 검증하기 위한 가짜 소리(감쇠 노이즈 + 저음)."""
        sr, ch = (44100, 2) if model == "sao" else (16000, 1)
        rng = np.random.default_rng(seed)
        n = int(seconds * sr)
        t = np.arange(n) / sr
        for i in range(steps):
            self.progress["step"] = i + 1
            time.sleep(0.01)
        body = rng.standard_normal((n, ch)) * np.exp(-t / 0.15)[:, None] * 0.5
        thump = np.sin(2 * np.pi * (60 + 80 * np.exp(-t / 0.03)) * t) * np.exp(-t / 0.2)
        return (body + thump[:, None] * 0.6).astype(np.float32), sr


def to_wav(audio: np.ndarray, sr: int) -> bytes:
    pcm = (np.clip(audio, -1, 1) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(audio.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class Req:  # 서버 모드에서 pydantic 모델로 교체됨(모듈 수준 이름이어야 FastAPI가 본문으로 해석한다)
    pass


def _make_request_model() -> None:
    global Req
    from pydantic import BaseModel, Field

    class _Req(BaseModel):
        model: str = "sao"
        prompt: str = Field(min_length=1, max_length=400)
        negative: str = ""
        seconds: float = Field(4.0, ge=0.5, le=12.0)
        steps: int = Field(80, ge=10, le=200)
        guidance: float = Field(0.0, ge=0.0, le=15.0)  # 0이면 모델 권장값
        seed: int = 0

    _Req.__name__ = "Req"
    Req = _Req


def _watch_parent(pid: int) -> None:
    """부모(앱) 프로세스가 사라지면 스스로 종료한다. 앱이 강제 종료돼도 워커가 VRAM(수 GB)을 쥔 채 남지 않게 한다.
    (Windows: 프로세스 핸들을 열어 살아있는지 확인. os.kill(pid, 0)은 Windows에서 CTRL_C 이벤트라 쓰면 안 된다.)"""
    import ctypes

    SYNCHRONIZE, WAIT_TIMEOUT = 0x00100000, 0x102
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        os._exit(0)  # 부모를 열 수 없다 = 이미 없음
    while kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT:
        time.sleep(2.0)
    os._exit(0)


def serve(port: int, mock: bool, parent_pid: int = 0) -> None:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import Response

    if parent_pid:
        threading.Thread(target=_watch_parent, args=(parent_pid,), daemon=True).start()
    _make_request_model()
    gen = Generator(mock)
    app = FastAPI()

    @app.get("/status")
    def status():
        return {"ok": True, "mock": mock, "device": gen.device, "loaded_model": gen.loaded_model,
                "models_present": {m: mock or model_present(m) for m in MODELS}, **gen.progress}

    @app.post("/generate")
    def generate(req: Req):
        if req.model not in MODELS:
            raise HTTPException(status_code=400, detail=f"알 수 없는 모델: {req.model}")
        if not mock and not model_present(req.model):
            raise HTTPException(status_code=409, detail="이 모델이 아직 내려받아지지 않았습니다.")
        spec = MODELS[req.model]
        seconds = min(req.seconds, spec["max_seconds"])
        guidance = req.guidance or spec["guidance"]
        try:
            audio, sr = gen.generate(req.model, req.prompt, req.negative, seconds, req.steps, guidance, req.seed)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"생성 실패: {type(exc).__name__}: {exc}") from exc
        return Response(content=to_wav(audio, sr), media_type="audio/wav", headers={"X-Seed": str(req.seed)})

    @app.post("/shutdown")
    def shutdown():
        threading.Timer(0.3, lambda: os._exit(0)).start()  # VRAM을 확실히 돌려주려고 프로세스째 종료
        return {"ok": True}

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8879)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--model", choices=list(MODELS), default="sao")
    ap.add_argument("--parent-pid", type=int, default=0)
    args = ap.parse_args()
    sys.exit(download(args.model) if args.download else (serve(args.port, args.mock, args.parent_pid) or 0))
