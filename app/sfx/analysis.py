"""참고 음원에서 '배우기': 녹음된 소리를 분석해 그것과 닮은 합성 spec(레이어+마스터)을 찾아낸다.

1) 분석: 에너지 곡선(어택/감쇠/꼬리), 초반·후반 스펙트럼, 저음 피크와 피치 하강, 잔향(RT60) 추정
2) 초기 추정: 크랙(고음 노이즈) + 몸통(저음 스윕) + 바디(중저음 노이즈) + 꼬리(감쇠 노이즈) + 룸 잔향
3) 정밀 조정: 합성 결과와 참고 음원의 다중 해상도 로그 스펙트로그램·에너지 곡선 거리를 줄이도록
   (1+λ) 진화 전략으로 수치 파라미터를 반복 조정(시간 예산 안에서)

결과 spec은 슬라이더로 계속 다듬을 수 있고, 같은 계열 소리를 여러 번 '배워' 내 프리셋으로 저장하면 그 스타일이 쌓인다.
※ 라이선스가 있는 음원(직접 녹음·구매한 라이브러리)만 넣을 것 — 결과 spec이 원본과 닮게 만들어진다.
"""
from __future__ import annotations

import copy
import math
import time
from typing import Callable

import numpy as np

from . import engine

FIT_SR = 22050  # 맞추는 동안은 낮은 샘플레이트로 빠르게 렌더한다
MAX_REF_SECONDS = 6.0


# ---------------------------------------------------------------- 특징 추출

def _frames_rms(x: np.ndarray, sr: int, hop_ms: float = 5.0) -> np.ndarray:
    hop = max(1, int(sr * hop_ms / 1000))
    n = len(x) // hop
    if n == 0:
        return np.zeros(1)
    return np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)


def _stft_logmag(x: np.ndarray, n_fft: int, hop: int) -> np.ndarray:
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    win = np.hanning(n_fft)
    n = 1 + (len(x) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(n)[:, None]
    mag = np.abs(np.fft.rfft(x[idx] * win, axis=1))
    return np.log10(mag + 1e-5)


def _band_edges(sr: int, bands: int = 20) -> np.ndarray:
    return np.geomspace(60, sr * 0.45, bands + 1)


def _band_energy_db(x: np.ndarray, sr: int, bands: int = 20) -> np.ndarray:
    """구간 x의 대역별 에너지(dB) — 스펙트럼 모양 비교/추정용."""
    if len(x) < 64:
        return np.full(bands, -120.0)
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    freqs = np.fft.rfftfreq(len(x), 1.0 / sr)
    edges = _band_edges(sr, bands)
    out = np.empty(bands)
    for i in range(bands):
        m = (freqs >= edges[i]) & (freqs < edges[i + 1])
        out[i] = 10 * np.log10(np.mean(spec[m]) + 1e-12) if m.any() else -120.0
    return out


def analyze(x: np.ndarray, sr: int) -> dict:
    """참고 음원의 핵심 특징을 뽑는다(UI에 요약으로 보여줄 값 포함)."""
    x = x[: int(MAX_REF_SECONDS * sr)].astype(np.float64)
    x = x - np.mean(x)
    peak = float(np.max(np.abs(x))) or 1.0
    x = x / peak
    rms = _frames_rms(x, sr, 5.0)
    env_db = 20 * np.log10(rms / (np.max(rms) or 1.0) + 1e-9)
    hop_s = 0.005
    i_peak = int(np.argmax(rms))
    # 어택: 피크의 10%(-20dB)에서 90% 도달까지
    lo = np.nonzero(rms[: i_peak + 1] >= 0.1 * rms[i_peak])[0]
    attack = max(0.0003, (i_peak - (lo[0] if len(lo) else 0)) * hop_s)
    # 감쇠: 피크 이후 -40dB까지 걸린 시간
    below = np.nonzero(env_db[i_peak:] <= -40)[0]
    decay40 = (below[0] if len(below) else len(env_db) - i_peak) * hop_s
    # 유효 길이: -60dB까지
    below60 = np.nonzero(env_db[i_peak:] <= -60)[0]
    length = (i_peak + (below60[0] if len(below60) else len(env_db) - i_peak)) * hop_s

    t0 = max(0, int(i_peak * hop_s * sr - 0.002 * sr))
    early = x[t0: t0 + int(0.04 * sr)]              # 초반 40ms: 크랙·타격
    mid = x[t0 + int(0.04 * sr): t0 + int(0.25 * sr)]
    late = x[t0 + int(0.25 * sr): t0 + int(1.2 * sr)]
    bands_early = _band_energy_db(early, sr)
    bands_mid = _band_energy_db(mid, sr)

    def centroid(seg: np.ndarray) -> float:
        if len(seg) < 64:
            return 0.0
        m = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        f = np.fft.rfftfreq(len(seg), 1.0 / sr)
        return float((m * f).sum() / (m.sum() + 1e-12))

    # 저음 피크(50~400Hz) 위치와 그 하강 폭 — 총·폭발의 '쿵'
    seg = x[t0: t0 + int(0.25 * sr)]
    low_hz, low_slide = 0.0, 0.0
    if len(seg) > 1024:
        lp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        f = np.fft.rfftfreq(len(seg), 1.0 / sr)
        m = (f >= 35) & (f <= 400)
        if m.any() and lp[m].max() > 0.05 * lp.max():
            low_hz = float(f[m][np.argmax(lp[m])])
            a, b = seg[: len(seg) // 2], seg[len(seg) // 2:]
            fa = _dominant_low(a, sr)
            fb = _dominant_low(b, sr)
            if fa > 0 and fb > 0:
                low_slide = float(math.log2(fb / fa) / (len(seg) / 2 / sr))  # 옥타브/초

    # 잔향 꼬리: 감쇠 후반부(-20~-50dB) 기울기로 RT60 추정
    seg_db = env_db[i_peak:]
    rt60 = 0.0
    sel = np.nonzero((seg_db <= -20) & (seg_db >= -50))[0]
    if len(sel) > 6:
        slope = np.polyfit(sel * hop_s, seg_db[sel], 1)[0]  # dB/s (음수)
        if slope < -3:
            rt60 = float(min(4.0, 60.0 / -slope))

    return {
        "duration": round(len(x) / sr, 3), "attack": round(attack, 4), "decay40": round(decay40, 3),
        "length": round(length, 3), "centroid_early": round(centroid(early)), "centroid_mid": round(centroid(mid)),
        "centroid_late": round(centroid(late)), "low_hz": round(low_hz, 1), "low_slide": round(low_slide, 2),
        "rt60": round(rt60, 2), "bands_early": bands_early.tolist(), "bands_mid": bands_mid.tolist(),
        "_x": x, "_sr": sr, "_rms": rms, "_i_peak": i_peak,
    }


def _dominant_low(seg: np.ndarray, sr: int) -> float:
    if len(seg) < 512:
        return 0.0
    m = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1.0 / sr)
    sel = (f >= 30) & (f <= 400)
    return float(f[sel][np.argmax(m[sel])]) if sel.any() and m[sel].max() > 0 else 0.0


# ---------------------------------------------------------------- 초기 추정

def initial_spec(feat: dict) -> dict:
    """분석값에서 '크랙 + 몸통 + 바디 + 꼬리 + 룸' 구조의 시작 spec을 만든다."""
    L = lambda **kw: kw  # noqa: E731
    c_early, c_mid, c_late = feat["centroid_early"], feat["centroid_mid"], feat["centroid_late"]
    length = min(4.0, max(0.15, feat["length"]))
    decay40 = min(3.0, max(0.05, feat["decay40"]))
    attack = min(0.05, max(0.0003, feat["attack"]))

    layers = [
        # 크랙: 순간적인 광대역/고음 노이즈
        L(wave="noise", noise_color=0.0, attack=0.0002, sustain=0.001, decay=min(0.12, max(0.02, decay40 * 0.15)),
          decay_curve=2.2, bp_amount=0.6, bp_freq=float(np.clip(c_early, 800, 9000)), bp_q=0.8, gain=1.0),
        # 바디: 중저음 노이즈가 시간에 따라 어두워짐
        L(wave="noise", noise_color=0.8, attack=attack, sustain=0.01, decay=min(1.5, max(0.08, decay40 * 0.6)),
          decay_curve=2.0, lp_cutoff=float(np.clip(c_mid * 2.0 + 500, 800, 12000)), lp_sweep=-3.0, gain=0.8),
        # 꼬리: 길고 어두운 감쇠
        L(wave="noise", noise_color=1.0, delay=0.02, attack=0.004, sustain=0.0, decay=length, decay_curve=2.5,
          lp_cutoff=float(np.clip(max(c_late, 300) * 2.0, 400, 6000)), lp_sweep=-1.5, gain=0.35),
    ]
    if feat["low_hz"] > 0:
        layers.append(L(wave="sine", freq=float(np.clip(feat["low_hz"] * 1.4, 35, 400)),
                        slide=float(np.clip(feat["low_slide"] - 2.0, -8, 0)), attack=0.0, sustain=0.01,
                        decay=min(1.2, max(0.06, decay40 * 0.5)), decay_curve=1.8, gain=0.9))
    rt = feat["rt60"]
    master = {"comp": 0.35}
    if rt > 0.25:
        master.update(room_mix=float(np.clip(0.15 + rt * 0.2, 0.15, 0.55)), room_time=float(np.clip(rt, 0.3, 3.5)),
                      room_damp=0.5)
    return engine.normalize_spec({"seed": 1, "layers": layers, "master": master})


# ---------------------------------------------------------------- 정밀 조정

# (레이어 인덱스 무관) 조정 대상 파라미터와 흔드는 방식
_TUNE_LAYER = ["gain", "attack", "sustain", "decay", "decay_curve", "lp_cutoff", "lp_sweep", "hp_cutoff",
               "bp_freq", "bp_q", "bp_amount", "freq", "slide", "noise_color", "delay"]
_TUNE_MASTER = ["comp", "room_mix", "room_time", "room_damp", "distortion", "master_lp"]
_LOGISH = {"attack", "sustain", "decay", "lp_cutoff", "hp_cutoff", "bp_freq", "freq", "room_time", "delay", "master_lp"}


def _prepare_target(x: np.ndarray, sr: int) -> dict:
    x = engine_resample(x, sr, FIT_SR)
    return {"x": x, "specs": {n: _stft_logmag(x, n, n // 4) for n in (256, 1024)}, "env": _frames_rms(x, FIT_SR, 5.0)}


def engine_resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    from . import samples
    return samples.resample(x, sr_from, sr_to)


def _loss(spec: dict, tgt: dict) -> float:
    y = engine.render(spec, FIT_SR).astype(np.float64)
    peak = np.max(np.abs(y)) or 1.0
    y = y / peak * (np.max(np.abs(tgt["x"])) or 1.0)
    total = 0.0
    for n, ref in tgt["specs"].items():
        got = _stft_logmag(y, n, n // 4)
        k = max(len(got), len(ref))
        g = np.pad(got, ((0, k - len(got)), (0, 0)), constant_values=-5)
        r = np.pad(ref, ((0, k - len(ref)), (0, 0)), constant_values=-5)
        total += float(np.mean(np.abs(g - r)))
    e = _frames_rms(y, FIT_SR, 5.0)
    e_ref = tgt["env"]
    k = max(len(e), len(e_ref))
    de = 20 * np.log10(np.pad(e, (0, k - len(e)), constant_values=1e-6) + 1e-6) \
        - 20 * np.log10(np.pad(e_ref, (0, k - len(e_ref)), constant_values=1e-6) + 1e-6)
    return total + 0.02 * float(np.mean(np.abs(np.clip(de, -60, 60))))


def _perturb(spec: dict, rng: np.random.Generator, scale: float) -> dict:
    cand = copy.deepcopy(spec)
    param_defs = {p["id"]: p for p in engine.LAYER_PARAMS}
    master_defs = {p["id"]: p for p in engine.MASTER_PARAMS}
    for _ in range(int(rng.integers(1, 4))):
        if rng.random() < 0.8:
            layer = cand["layers"][int(rng.integers(len(cand["layers"])))]
            key = _TUNE_LAYER[int(rng.integers(len(_TUNE_LAYER)))]
            defs, holder = param_defs[key], layer
            if layer["wave"] == "noise" and key in ("freq", "slide"):
                continue
            if layer["wave"] != "noise" and key == "noise_color":
                continue
        else:
            key = _TUNE_MASTER[int(rng.integers(len(_TUNE_MASTER)))]
            defs, holder = master_defs[key], cand["master"]
        v = float(holder[key])
        if key in _LOGISH and v > 0:
            v *= math.exp(rng.normal(0, 0.45 * scale))
        else:
            v += rng.normal(0, (defs["max"] - defs["min"]) * 0.12 * scale)
        holder[key] = v
    return engine.normalize_spec(cand)


def fit(x: np.ndarray, sr: int, budget_s: float = 25.0, seed: int = 1,
        progress: Callable[[float, float], None] | None = None, init: dict | None = None) -> dict:
    """참고 음원 x에 가장 가까운 spec을 찾는다. 반환: {spec, loss0, loss, iterations, features}"""
    feat = analyze(x, sr)
    tgt = _prepare_target(feat["_x"], sr)
    best = init or initial_spec(feat)
    best_loss = _loss(best, tgt)
    loss0 = best_loss
    rng = np.random.default_rng(seed)
    t_start = time.time()
    it = 0
    while time.time() - t_start < budget_s:
        frac = (time.time() - t_start) / budget_s
        scale = 1.0 - 0.75 * frac            # 처음엔 크게, 끝으로 갈수록 미세 조정
        cand = _perturb(best, rng, scale)
        cl = _loss(cand, tgt)
        it += 1
        if cl < best_loss:
            best, best_loss = cand, cl
        if progress and it % 5 == 0:
            progress(frac, best_loss)
    if progress:
        progress(1.0, best_loss)
    public = {k: v for k, v in feat.items() if not k.startswith("_")}
    return {"spec": best, "loss0": round(loss0, 4), "loss": round(best_loss, 4), "iterations": it, "features": public}
