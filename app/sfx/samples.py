"""샘플(녹음 조각) 저장소: data/samples/<id>.wav — 모노 16bit로 정규화해 보관한다.

id는 내용 해시라 같은 소리를 여러 번 올려도 한 벌만 저장된다. spec의 sample 레이어는 이 id로 소리를 가리킨다.
(sample 레이어를 쓰는 효과음을 다른 PC로 옮길 땐 완성된 WAV를 내보내면 되고, spec 재편집이 필요하면 samples 폴더도 함께 옮긴다.)
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np

MAX_SAMPLE_SECONDS = 30.0
_ID_RE = re.compile(r"[0-9a-f]{16}")
_dir: Path | None = None


def init(directory: Path) -> None:
    global _dir
    _dir = Path(directory)
    _dir.mkdir(parents=True, exist_ok=True)
    _load.cache_clear()


def valid_id(value: str) -> bool:
    return bool(_ID_RE.fullmatch(value))


def _path(sample_id: str) -> Path | None:
    return _dir / f"{sample_id}.wav" if _dir is not None and valid_id(sample_id) else None


def decode_wav(data: bytes) -> tuple[np.ndarray, int]:
    """PCM 8/16/24/32bit WAV → (모노 float32, 샘플레이트). 형식이 다르면 ValueError."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            ch, width, sr, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"WAV 파일을 읽을 수 없습니다: {exc}") from exc
    if frames < 2 or sr < 8000:
        raise ValueError("소리가 너무 짧거나 샘플레이트가 너무 낮습니다.")
    if width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        v = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        x = v.astype(np.float32) / (1 << 23)
    elif width == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float32) / (1 << 31)
    else:
        raise ValueError("지원하지 않는 WAV 비트 깊이입니다.")
    if ch > 1:
        x = x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    if len(x) / sr > MAX_SAMPLE_SECONDS:
        raise ValueError(f"샘플은 {MAX_SAMPLE_SECONDS:.0f}초 이하여야 합니다.")
    return x.astype(np.float32), sr


def encode_wav(x: np.ndarray, sr: int) -> bytes:
    # 읽을 때(decode_wav)가 /32768 이므로 쓸 때도 *32768 로 맞춰야 '읽고 다시 쓰기'가 바이트까지 똑같다.
    # (비대칭이면 같은 파일을 다시 올릴 때 1 LSB씩 달라져 내용 해시가 바뀌고, 비상업 표시가 떨어져 나간다)
    pcm = np.clip(np.rint(x * 32768.0), -32768, 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _meta_path(sample_id: str) -> Path | None:
    return _dir / f"{sample_id}.json" if _dir is not None and valid_id(sample_id) else None


def meta(sample_id: str) -> dict:
    """샘플의 출처/라이선스 표시({source, model, license}). 없으면 {}."""
    path = _meta_path(sample_id)
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def is_noncommercial(sample_id: str) -> bool:
    return meta(sample_id).get("license") == "nc"


def spec_uses_noncommercial(spec: dict) -> bool:
    """spec의 샘플 레이어 중 비상업 라이선스 샘플이 하나라도 있는가(= 이 효과음은 출시물에 쓰면 안 됨)."""
    return any(isinstance(layer, dict) and layer.get("sample") and is_noncommercial(str(layer["sample"]))
               for layer in (spec or {}).get("layers", []))


def save(data: bytes, meta_info: dict | None = None) -> dict:
    """WAV 바이트를 정규화해 저장하고 {id, duration, sample_rate, noncommercial}를 돌려준다.
    meta_info로 출처/라이선스를 남기며, 한 번 비상업(nc)으로 표시된 샘플은 같은 내용을 다시 올려도 nc를 유지한다."""
    if _dir is None:
        raise RuntimeError("샘플 저장소가 초기화되지 않았습니다.")
    x, sr = decode_wav(data)
    wav = encode_wav(x, sr)
    _dir.mkdir(parents=True, exist_ok=True)  # 실행 중에 폴더가 지워져도 저장이 죽지 않게
    sample_id = hashlib.sha1(wav).hexdigest()[:16]
    (_dir / f"{sample_id}.wav").write_bytes(wav)
    if meta_info:
        merged = {**meta(sample_id), **meta_info}
        if is_noncommercial(sample_id):
            merged["license"] = "nc"
        _meta_path(sample_id).write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
    return {"id": sample_id, "duration": round(len(x) / sr, 3), "sample_rate": sr,
            "noncommercial": is_noncommercial(sample_id)}


@lru_cache(maxsize=32)
def _load(sample_id: str) -> tuple[np.ndarray, int] | None:
    path = _path(sample_id)
    if path is None or not path.exists():
        return None
    return decode_wav(path.read_bytes())


def info(sample_id: str) -> dict | None:
    got = _load(sample_id)
    return None if got is None else {"id": sample_id, "duration": round(len(got[0]) / got[1], 3), "sample_rate": got[1],
                                     "noncommercial": is_noncommercial(sample_id)}


def resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """푸리에 방식 리샘플(대역 제한 유지). 다운샘플 때 앨리어싱이 생기지 않는다."""
    if sr_from == sr_to:
        return x
    n_new = max(2, int(round(len(x) * sr_to / sr_from)))
    spec = np.fft.rfft(x)
    out = np.zeros(n_new // 2 + 1, dtype=np.complex128)
    k = min(len(spec), len(out))
    out[:k] = spec[:k]
    return np.fft.irfft(out, n_new) * (n_new / len(x))


def load_resampled(sample_id: str, sr: int) -> np.ndarray | None:
    got = _load(sample_id)
    if got is None:
        return None
    x, sr_from = got
    return resample(x, sr_from, sr).astype(np.float64)


def get(sample_id: str) -> tuple[np.ndarray, int] | None:
    """저장된 샘플 원본(모노 float32, 샘플레이트). 없으면 None."""
    return _load(sample_id)


def decode_stereo(data: bytes) -> tuple[np.ndarray, int]:
    """16bit PCM WAV → (float32 (n, ch), 샘플레이트). AI 생성물처럼 채널을 유지하고 싶을 때."""
    with wave.open(io.BytesIO(data)) as w:
        ch, width, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError("16bit WAV만 지원합니다.")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return x.reshape(-1, ch), sr
