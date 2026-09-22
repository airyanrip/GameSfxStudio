"""절차적 효과음 합성 엔진(numpy).

효과음(spec) = 여러 개의 '레이어'(오실레이터/노이즈 + 엔벨로프 + 필터 + 변조)를 겹쳐 놓고,
그 합에 '마스터 이펙트'(피치/왜곡/비트크러시/에코/리버브/정규화)를 건 것.

    spec = {"seed": 1234, "layers": [ {...}, ... ], "master": {...}}

모든 값은 PARAM 스키마의 범위로 잘려(clamp) 들어오므로, 어떤 입력을 줘도 안전하게 렌더된다.
"""
from __future__ import annotations

import io
import math
import wave
from typing import Any

import numpy as np

from . import samples

WAVES = ["sine", "square", "saw", "triangle", "noise", "chip_noise", "metal", "sample"]
SAMPLE_RATES = [22050, 44100, 48000]
MAX_LAYERS = 16
MAX_SECONDS = 10.0


def _p(id_: str, default: Any, lo: float = 0, hi: float = 1, step: float = 0.01,
       scale: str = "lin", unit: str = "", group: str = "", type_: str = "float", options=None) -> dict:
    d = {"id": id_, "type": type_, "default": default, "group": group}
    if type_ == "float":
        d.update(min=lo, max=hi, step=step, scale=scale, unit=unit)
    if options:
        d["options"] = options
    return d


# 레이어 파라미터 (group은 UI에서 묶음 제목으로 쓰인다)
LAYER_PARAMS: list[dict] = [
    _p("enabled", True, type_="bool", group="basic"),
    _p("wave", "square", type_="enum", options=WAVES, group="basic"),
    _p("gain", 0.8, 0, 1.5, 0.01, group="basic"),
    _p("delay", 0.0, 0, 3, 0.005, scale="pow", unit="s", group="basic"),
    _p("repeat", 1, 1, 16, 1, unit="x", group="repeat"),
    _p("repeat_gap", 0.08, 0.02, 1.0, 0.005, scale="pow", unit="s", group="repeat"),
    _p("repeat_gain", 0.95, 0.5, 1.0, 0.01, group="repeat"),
    _p("repeat_jitter", 0.1, 0, 0.5, 0.01, group="repeat"),

    _p("freq", 440.0, 20, 8000, 1, scale="log", unit="Hz", group="pitch"),
    _p("slide", 0.0, -12, 12, 0.05, unit="oct/s", group="pitch"),
    _p("slide_accel", 0.0, -40, 40, 0.1, unit="oct/s²", group="pitch"),
    _p("arp_semitones", 0.0, -24, 24, 1, unit="st", group="pitch"),
    _p("arp_time", 0.1, 0.01, 1.5, 0.005, scale="pow", unit="s", group="pitch"),
    _p("vibrato_depth", 0.0, 0, 12, 0.05, unit="st", group="pitch"),
    _p("vibrato_rate", 8.0, 0.2, 60, 0.1, unit="Hz", group="pitch"),

    _p("duty", 0.5, 0.05, 0.95, 0.01, group="tone"),
    _p("duty_sweep", 0.0, -2, 2, 0.05, group="tone"),
    _p("fm_ratio", 1.0, 0.25, 12, 0.01, unit="x", group="tone"),
    _p("fm_depth", 0.0, 0, 12, 0.05, group="tone"),
    _p("noise_color", 0.0, 0, 2, 0.05, group="tone"),
    _p("spread", 0.8, 0, 1, 0.01, group="tone"),

    _p("sample", "", type_="asset", group="sample"),
    _p("sample_start", 0.0, 0, 20, 0.005, scale="pow", unit="s", group="sample"),
    _p("sample_pitch", 0.0, -24, 24, 0.1, unit="st", group="sample"),

    _p("attack", 0.005, 0, 2, 0.001, scale="pow", unit="s", group="envelope"),
    _p("sustain", 0.1, 0, 3, 0.005, scale="pow", unit="s", group="envelope"),
    _p("decay", 0.2, 0, 4, 0.005, scale="pow", unit="s", group="envelope"),
    _p("decay_curve", 1.0, 0.3, 5, 0.05, group="envelope"),
    _p("punch", 0.0, 0, 2, 0.01, group="envelope"),

    _p("lp_cutoff", 20000.0, 60, 20000, 1, scale="log", unit="Hz", group="filter"),
    _p("lp_sweep", 0.0, -10, 10, 0.05, unit="oct/s", group="filter"),
    _p("hp_cutoff", 20.0, 20, 8000, 1, scale="log", unit="Hz", group="filter"),
    _p("bp_amount", 0.0, 0, 1, 0.01, group="filter"),
    _p("bp_freq", 1500.0, 60, 16000, 1, scale="log", unit="Hz", group="filter"),
    _p("bp_q", 1.5, 0.5, 20, 0.1, group="filter"),
    _p("bp_sweep", 0.0, -8, 8, 0.05, unit="oct/s", group="filter"),

    _p("tremolo_depth", 0.0, 0, 1, 0.01, group="mod"),
    _p("tremolo_rate", 10.0, 0.2, 60, 0.1, unit="Hz", group="mod"),
]

# 마스터 파라미터
MASTER_PARAMS: list[dict] = [
    _p("volume", 1.0, 0, 1, 0.01, group="master"),
    _p("normalize", True, type_="bool", group="master"),
    _p("pitch", 0.0, -24, 24, 0.1, unit="st", group="master"),
    _p("distortion", 0.0, 0, 1, 0.01, group="master"),
    _p("bits", 16, 2, 16, 1, unit="bit", group="master"),
    _p("downsample", 1, 1, 32, 1, unit="x", group="master"),
    _p("echo_time", 0.15, 0.02, 0.8, 0.005, scale="pow", unit="s", group="space"),
    _p("echo_feedback", 0.35, 0, 0.9, 0.01, group="space"),
    _p("echo_mix", 0.0, 0, 1, 0.01, group="space"),
    _p("reverb_size", 0.5, 0, 1, 0.01, group="space"),
    _p("reverb_mix", 0.0, 0, 1, 0.01, group="space"),
    _p("room_mix", 0.0, 0, 1, 0.01, group="space"),
    _p("room_time", 0.8, 0.1, 4, 0.01, scale="pow", unit="s", group="space"),
    _p("room_damp", 0.5, 0, 1, 0.01, group="space"),
    _p("room_predelay", 0.01, 0, 0.1, 0.001, scale="pow", unit="s", group="space"),
    _p("comp", 0.0, 0, 1, 0.01, group="master"),
    _p("master_hp", 20.0, 20, 2000, 1, scale="log", unit="Hz", group="master"),
    _p("master_lp", 20000.0, 200, 20000, 1, scale="log", unit="Hz", group="master"),
    _p("fade_out", 0.008, 0, 2, 0.001, scale="pow", unit="s", group="master"),
]

_LAYER_BY_ID = {p["id"]: p for p in LAYER_PARAMS}
_MASTER_BY_ID = {p["id"]: p for p in MASTER_PARAMS}
LAYER_DEFAULTS = {p["id"]: p["default"] for p in LAYER_PARAMS}
MASTER_DEFAULTS = {p["id"]: p["default"] for p in MASTER_PARAMS}


def schema() -> dict:
    return {
        "layer": LAYER_PARAMS,
        "master": MASTER_PARAMS,
        "waves": WAVES,
        "sample_rates": SAMPLE_RATES,
        "max_layers": MAX_LAYERS,
    }


# ---------------------------------------------------------------- 정규화(clamp)

def _coerce(param: dict, value: Any) -> Any:
    t = param["type"]
    if t == "bool":
        return bool(value)
    if t == "enum":
        return value if value in param["options"] else param["default"]
    if t == "asset":
        return value if isinstance(value, str) and samples.valid_id(value) else ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return param["default"]
    if not math.isfinite(v):
        return param["default"]
    v = min(param["max"], max(param["min"], v))
    if param["id"] in ("bits", "downsample", "repeat"):
        v = int(round(v))
    return v


def normalize_spec(spec: dict | None) -> dict:
    """어떤 dict가 와도 기본값 채우고 범위로 자른 안전한 spec을 돌려준다."""
    spec = spec or {}
    out_layers = []
    for raw in list(spec.get("layers") or [])[:MAX_LAYERS]:
        raw = raw if isinstance(raw, dict) else {}
        out_layers.append({p["id"]: _coerce(p, raw.get(p["id"], p["default"])) for p in LAYER_PARAMS})
    if not out_layers:
        out_layers = [dict(LAYER_DEFAULTS)]
    raw_master = spec.get("master") if isinstance(spec.get("master"), dict) else {}
    master = {p["id"]: _coerce(p, raw_master.get(p["id"], p["default"])) for p in MASTER_PARAMS}
    try:
        seed = int(spec.get("seed", 1)) & 0x7FFFFFFF
    except (TypeError, ValueError):
        seed = 1
    return {"seed": seed, "layers": out_layers, "master": master}


# ---------------------------------------------------------------- DSP 부품

def _one_pole_lowpass(x: np.ndarray, cutoff: np.ndarray, sr: int, order: int = 2) -> np.ndarray:
    """시간에 따라 컷오프가 변하는 1극 로우패스를 order번 직렬로 건다(order=2 → 12dB/oct)."""
    coef = (1.0 - np.exp(-2.0 * math.pi * cutoff / sr)).tolist()
    xs = x.tolist()
    out = [0.0] * len(xs)
    y1 = y2 = 0.0
    if order == 1:
        for i, (v, a) in enumerate(zip(xs, coef)):
            y1 += a * (v - y1)
            out[i] = y1
    else:
        for i, (v, a) in enumerate(zip(xs, coef)):
            y1 += a * (v - y1)
            y2 += a * (y1 - y2)
            out[i] = y2
    return np.asarray(out, dtype=np.float64)


def _colored_noise(n: int, color: float, rng: np.random.Generator) -> np.ndarray:
    """color 0=백색, 1=핑크(1/f), 2=브라운(1/f²) — FFT에서 스펙트럼을 기울여 만든다."""
    white = rng.standard_normal(n)
    if color <= 0.01 or n < 8:
        return white / 3.0
    spec = np.fft.rfft(white)
    f = np.arange(len(spec), dtype=np.float64)
    f[0] = 1.0
    spec *= f ** (-color / 2.0)
    spec[0] = 0
    out = np.fft.irfft(spec, n)
    peak = np.max(np.abs(out)) or 1.0
    return out / peak


def _comb(x: np.ndarray, d: int, g: float) -> np.ndarray:
    """피드백 콤 필터 y[n] = x[n] + g*y[n-d] 를 d샘플 블록 단위로 벡터화."""
    y = x.copy()
    for start in range(d, len(y), d):
        end = min(start + d, len(y))
        y[start:end] += g * y[start - d:end - d]
    return y


def _allpass(x: np.ndarray, d: int, g: float) -> np.ndarray:
    y = -g * x
    if d < len(x):
        y[d:] += x[:-d]
    for start in range(d, len(y), d):
        end = min(start + d, len(y))
        y[start:end] += g * y[start - d:end - d]
    return y


def _svf_bandpass(x: np.ndarray, fc: np.ndarray, q: float, sr: int) -> np.ndarray:
    """TPT 상태변수 필터의 밴드패스(공진 Q, 시간에 따라 중심주파수 이동). 통과대역 이득 1."""
    g = np.tan(math.pi * np.clip(fc, 30.0, sr * 0.45) / sr)
    k = 1.0 / q
    a1 = 1.0 / (1.0 + g * (g + k))
    a2 = g * a1
    a3 = g * a2
    ic1 = ic2 = 0.0
    out = [0.0] * len(x)
    for i, (v, c1, c2, c3) in enumerate(zip(x.tolist(), a1.tolist(), a2.tolist(), a3.tolist())):
        v3 = v - ic2
        v1 = c1 * ic1 + c2 * v3
        v2 = ic2 + c2 * ic1 + c3 * v3
        ic1 = 2.0 * v1 - ic1
        ic2 = 2.0 * v2 - ic2
        out[i] = k * v1
    return np.asarray(out, dtype=np.float64)


def _compress(x: np.ndarray, amount: float, sr: int) -> np.ndarray:
    """컴프레서(amount 0~1). 어택 8ms로 '첫 순간(크랙·타격)은 통과'시키고 그 뒤 몸통·꼬리만 눌러 펀치를 만든다.
    (어택이 0이면 순간음부터 눌려 소리가 뭉개지고, 정규화 후 꼬리만 커져 '쉬익' 하는 덩어리가 된다.)"""
    thr = 10 ** ((-3.0 - 21.0 * amount) / 20.0)
    expo = 1.0 - 1.0 / (1.0 + 7.0 * amount)
    att = math.exp(-1.0 / (0.008 * sr))
    rel = math.exp(-1.0 / (0.12 * sr))
    env = 0.0
    out = [0.0] * len(x)
    for i, v in enumerate(x.tolist()):
        a = abs(v)
        c = att if a > env else rel
        env = a + (env - a) * c
        out[i] = v * ((thr / env) ** expo if env > thr else 1.0)
    return np.asarray(out, dtype=np.float64)


def _room_ir(sr: int, rt60: float, damp: float, predelay: float, seed: int) -> np.ndarray:
    """합성 룸 임펄스 응답: 초기 반사 + 대역별로 다르게 감쇠하는 확산 꼬리(고음이 먼저 죽음)."""
    rng = np.random.default_rng([seed, 7])
    n = max(256, int((rt60 * 0.95 + 0.05) * sr))
    t = np.arange(n) / sr
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.maximum(np.fft.rfftfreq(n, 1.0 / sr), 1.0)
    m_low = 1.0 / (1.0 + (f / 400.0) ** 4)
    m_high = 1.0 / (1.0 + (3000.0 / f) ** 4)
    m_mid = np.clip(1.0 - m_low - m_high, 0.0, 1.0)

    def band(mask, rt):
        return np.fft.irfft(spec * mask, n) * np.exp(-6.9078 * t / max(rt, 0.05))

    ir = (band(m_low, rt60 * 1.15) + band(m_mid, rt60)
          + band(m_high, rt60 * (1.0 - 0.8 * damp)) * (1.0 - 0.5 * damp))
    ir *= 1.0 - np.exp(-t / 0.012)  # 꼬리는 서서히 조밀해진다
    ir /= np.max(np.abs(ir)) or 1.0
    for ms, amp in ((7, 0.9), (11, -0.75), (17, 0.6), (23, -0.5), (31, 0.4), (43, -0.3)):
        idx = int(ms * sr / 1000)
        if idx < n:
            ir[idx] += amp * 2.5
    ir /= math.sqrt(float(np.sum(ir * ir))) or 1.0
    return np.concatenate([np.zeros(int(predelay * sr)), ir])


def _fft_convolve(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    n = len(x) + len(h) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(h, size), size)[:n]


# ---------------------------------------------------------------- 레이어 렌더

def _apply_filters(sig: np.ndarray, p: dict, sr: int) -> np.ndarray:
    """레이어 필터 체인: 밴드패스 → 로우패스(스윕) → 하이패스."""
    n = len(sig)
    t = np.arange(n) / sr
    if p["bp_amount"] > 0.001:
        fc = p["bp_freq"] * np.power(2.0, p["bp_sweep"] * t)
        sig = (1.0 - p["bp_amount"]) * sig + p["bp_amount"] * _svf_bandpass(sig, fc, p["bp_q"], sr)
    if p["lp_cutoff"] < 19000 or p["lp_sweep"] != 0:
        cutoff = np.clip(p["lp_cutoff"] * np.power(2.0, p["lp_sweep"] * t), 30.0, sr * 0.45)
        if not (np.all(cutoff > sr * 0.44)):
            sig = _one_pole_lowpass(sig, cutoff, sr)
    if p["hp_cutoff"] > 25:
        sig = sig - _one_pole_lowpass(sig, np.full(n, p["hp_cutoff"]), sr, order=1)
    return sig


def _render_sample_layer(p: dict, sr: int) -> np.ndarray:
    """녹음된 샘플(AI 생성물·직접 녹음·구매 라이브러리)을 레이어로: 잘라내기, 피치, 페이드, 필터, 지연."""
    x = samples.load_resampled(p["sample"], sr)
    if x is None or len(x) < 2:
        return np.zeros(0)
    x = x[int(p["sample_start"] * sr):]
    if abs(p["sample_pitch"]) > 1e-3:
        ratio = 2.0 ** (p["sample_pitch"] / 12.0)
        x = np.interp(np.arange(max(2, int(len(x) / ratio))) * ratio, np.arange(len(x)), x)
    x = x[: int(MAX_SECONDS * sr)]
    n = len(x)
    if n < 2:
        return np.zeros(0)
    env = np.ones(n)
    na = min(n, int(p["attack"] * sr))
    if na:
        env[:na] = np.linspace(0, 1, na, endpoint=False)
    nd = min(n, int(p["decay"] * sr))  # 샘플은 '끝에서 decay초 동안' 페이드아웃한다
    if nd:
        env[n - nd:] *= (1.0 - np.linspace(0, 1, nd, endpoint=False)) ** p["decay_curve"]
    if p["tremolo_depth"] > 0:
        env *= 1.0 - p["tremolo_depth"] * (0.5 + 0.5 * np.sin(2 * math.pi * p["tremolo_rate"] * np.arange(n) / sr))
    sig = _apply_filters(x * env, p, sr) * p["gain"]
    lead = int(p["delay"] * sr)
    return np.concatenate([np.zeros(lead), sig]) if lead else sig


def _render_layer(p: dict, sr: int, rng: np.random.Generator) -> np.ndarray:
    if p["wave"] == "sample":
        return _render_sample_layer(p, sr)
    a, s, d = p["attack"], p["sustain"], p["decay"]
    n = int((a + s + d) * sr)
    if n < 2:
        return np.zeros(0)
    t = np.arange(n) / sr

    # --- 주파수 곡선(옥타브/반음 단위로 합산)
    semis = 12.0 * (p["slide"] * t + 0.5 * p["slide_accel"] * t * t)
    if p["vibrato_depth"] > 0:
        semis += p["vibrato_depth"] * np.sin(2 * math.pi * p["vibrato_rate"] * t)
    if p["arp_semitones"] != 0:
        semis += np.where(t >= p["arp_time"], p["arp_semitones"], 0.0)
    freq = np.clip(p["freq"] * np.power(2.0, semis / 12.0), 10.0, sr * 0.45)

    wave_type = p["wave"]
    if wave_type == "noise":
        sig = _colored_noise(n, p["noise_color"], rng)
    elif wave_type == "metal":
        # 금속 막대/종의 비조화 배음. spread 0=정수배음(맑음) → 1=실제 금속 막대 비율(쇳소리)
        bar = (1.0, 2.756, 5.404, 8.933, 13.344)
        amps = (1.0, 0.6, 0.4, 0.25, 0.15)
        sig = np.zeros(n)
        for i, (r, amp) in enumerate(zip(bar, amps)):  # (주의: a는 어택 시간이라 덮어쓰면 안 된다)
            ratio = (i + 1) + p["spread"] * (r - (i + 1))
            part_freq = freq * ratio
            ph = np.cumsum(part_freq) / sr
            sig += amp * np.sin(2 * math.pi * ph) * np.exp(-t * (1.5 + 5.0 * i)) * (part_freq < sr * 0.45)
        sig /= 2.4
    else:
        phase = np.cumsum(freq) / sr  # 사이클 단위
        if p["fm_depth"] > 0:
            mod = np.cumsum(freq * p["fm_ratio"]) / sr
            phase = phase + p["fm_depth"] * np.sin(2 * math.pi * mod) / (2 * math.pi)
        frac = phase % 1.0
        if wave_type == "sine":
            sig = np.sin(2 * math.pi * phase)
        elif wave_type == "square":
            duty = np.clip(p["duty"] + p["duty_sweep"] * t, 0.05, 0.95)
            sig = np.where(frac < duty, 1.0, -1.0)
        elif wave_type == "saw":
            sig = 2.0 * frac - 1.0
        elif wave_type == "triangle":
            sig = 4.0 * np.abs(frac - 0.5) - 1.0
        else:  # chip_noise: 주파수 속도로 값이 바뀌는 NES식 노이즈
            idx = np.floor(phase).astype(np.int64)
            table = rng.uniform(-1, 1, int(idx[-1]) + 2)
            sig = table[idx]

    # --- 엔벨로프: 어택(선형) → 서스테인(+펀치) → 디케이((1-x)^curve)
    na, ns = int(a * sr), int(s * sr)
    nd = n - na - ns
    env = np.empty(n)
    env[:na] = np.linspace(0, 1, na, endpoint=False)
    if ns:
        env[na:na + ns] = 1.0 + p["punch"] * (1.0 - np.linspace(0, 1, ns, endpoint=False))
    if nd > 0:
        env[na + ns:] = (1.0 - np.linspace(0, 1, nd, endpoint=False)) ** p["decay_curve"]
    if p["tremolo_depth"] > 0:
        env *= 1.0 - p["tremolo_depth"] * (0.5 + 0.5 * np.sin(2 * math.pi * p["tremolo_rate"] * t))
    sig = sig * env

    sig = _apply_filters(sig, p, sr)

    sig = sig * p["gain"]
    lead = int(p["delay"] * sr)
    return np.concatenate([np.zeros(lead), sig]) if lead else sig


# ---------------------------------------------------------------- 마스터 이펙트

def _apply_master(x: np.ndarray, m: dict, sr: int, seed: int = 1) -> np.ndarray:
    # 피치(재생 속도) — 길이도 함께 변한다
    if abs(m["pitch"]) > 1e-3:
        ratio = 2.0 ** (m["pitch"] / 12.0)
        new_n = max(2, int(len(x) / ratio))
        x = np.interp(np.arange(new_n) * ratio, np.arange(len(x)), x)

    # 이펙트 꼬리가 잘리지 않게 여백 추가
    tail = 0.0
    if m["echo_mix"] > 0.001:
        taps = min(8, 1 + int(math.log(0.02) / math.log(max(m["echo_feedback"], 0.05))))
        tail = max(tail, m["echo_time"] * taps)
    if m["reverb_mix"] > 0.001:
        tail = max(tail, 0.4 + 1.6 * m["reverb_size"])
    if m["room_mix"] > 0.001:
        tail = max(tail, m["room_predelay"] + m["room_time"] * 0.95)
    if tail:
        x = np.concatenate([x, np.zeros(int(tail * sr))])
    x = x[: int(MAX_SECONDS * sr)]

    peak = np.max(np.abs(x)) if len(x) else 0.0
    if peak > 1e-9 and (m["distortion"] > 0 or m["bits"] < 16):
        x = x / peak  # 왜곡 전에 기준 레벨을 맞춘다

    if m["distortion"] > 0.001:
        k = 1.0 + m["distortion"] * 30.0
        x = np.tanh(k * x) / math.tanh(k)
    if m["bits"] < 16:
        levels = 2.0 ** (m["bits"] - 1)
        x = np.round(x * levels) / levels
    if m["downsample"] > 1:
        k = int(m["downsample"])
        x = np.repeat(x[::k], k)[: len(x)]

    if m["echo_mix"] > 0.001:
        d = max(1, int(m["echo_time"] * sr))
        wet = _comb(x, d, m["echo_feedback"]) - x
        x = x + m["echo_mix"] * wet

    if m["reverb_mix"] > 0.001:
        scale = 0.5 + m["reverb_size"]
        fb = 0.66 + 0.26 * m["reverb_size"]
        acc = np.zeros_like(x)
        for ms in (29.7, 37.1, 41.1, 43.7):
            acc += _comb(x, max(1, int(ms * scale * sr / 1000)), fb)
        wet = acc / 4.0
        for ms in (5.0, 1.7):
            wet = _allpass(wet, max(1, int(ms * sr / 1000)), 0.7)
        x = x + m["reverb_mix"] * 1.4 * wet

    if m["room_mix"] > 0.001:
        ir = _room_ir(sr, m["room_time"], m["room_damp"], m["room_predelay"], seed)
        x = x + m["room_mix"] * 1.5 * _fft_convolve(x, ir)[: len(x)]
    if m["comp"] > 0.001:
        x = _compress(x, m["comp"], sr)
    if m["master_hp"] > 25:
        x = x - _one_pole_lowpass(x, np.full(len(x), m["master_hp"]), sr, order=1)
    if m["master_lp"] < 19000:
        x = _one_pole_lowpass(x, np.full(len(x), m["master_lp"]), sr)

    # 들리지 않는 끝부분(-54dB 미만)은 잘라 파일이 불필요하게 길어지지 않게 한다
    if len(x):
        loud = np.nonzero(np.abs(x) > np.max(np.abs(x)) * 0.002)[0]
        if len(loud):
            x = x[: min(len(x), int(loud[-1]) + int(0.01 * sr))].copy()

    # 클릭 방지 페이드
    n = len(x)
    if n:
        fi = min(n, max(1, int(0.0008 * sr)))
        x[:fi] *= np.linspace(0, 1, fi, endpoint=False)
        fo = min(n, max(1, int(m["fade_out"] * sr)))
        x[n - fo:] *= np.linspace(1, 0, fo)

    peak = np.max(np.abs(x)) if n else 0.0
    if m["normalize"] and peak > 1e-9:
        x = x / peak * (10 ** (-1.0 / 20))  # -1 dBFS
    x = x * m["volume"]
    return np.clip(x, -1.0, 1.0)


# ---------------------------------------------------------------- 공개 API

def render(spec: dict, sample_rate: int = 44100) -> np.ndarray:
    """spec → float32 모노 파형(-1..1)."""
    sr = sample_rate if sample_rate in SAMPLE_RATES else 44100
    spec = normalize_spec(spec)
    layers = []
    for i, lp in enumerate(spec["layers"]):
        if not lp["enabled"]:
            continue
        reps = int(lp["repeat"])
        jit = np.random.default_rng([spec["seed"], i, 999]).uniform(-1, 1, (reps, 2)) * lp["repeat_jitter"]
        for k in range(reps):
            if reps == 1:
                pk = lp
            else:  # k번째 반복: 앞선 반복 뒤에 (간격±흔들림) 만큼 늦게, 음량은 점점 줄고 ±흔들림
                pk = dict(lp, delay=lp["delay"] + k * lp["repeat_gap"] * (1 + 0.5 * jit[k, 0]) * (1.0 if k else 0.0),
                          gain=lp["gain"] * (lp["repeat_gain"] ** k) * (1 + jit[k, 1]))
            rng = np.random.default_rng([spec["seed"], i, k])
            layers.append(_render_layer(pk, sr, rng))
    total = max((len(l) for l in layers), default=0)
    if total < 2:
        return np.zeros(int(0.05 * sr), dtype=np.float32)
    mix = np.zeros(total)
    for l in layers:
        mix[: len(l)] += l
    return _apply_master(mix, spec["master"], sr, spec["seed"]).astype(np.float32)


def to_wav_bytes(samples: np.ndarray, sample_rate: int = 44100) -> bytes:
    pcm = (np.clip(samples, -1, 1) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def render_wav(spec: dict, sample_rate: int = 44100) -> tuple[bytes, float]:
    """(WAV 바이트, 길이[초])"""
    sr = sample_rate if sample_rate in SAMPLE_RATES else 44100
    samples = render(spec, sr)
    return to_wav_bytes(samples, sr), len(samples) / sr
