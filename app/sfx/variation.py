"""프리셋을 흔들어 새 소리를 만드는 도구: 변형(mutate) / 랜덤 / 설명(텍스트)→프리셋."""
from __future__ import annotations

import copy
import math
import random
import re

import numpy as np

from .engine import LAYER_PARAMS, MASTER_PARAMS, normalize_spec
from .presets import PRESET_BY_ID, PRESETS

_TIME_KEYS = ("attack", "sustain", "decay", "delay", "arp_time")


def _jitter(param: dict, value: float, amount: float, rng: np.random.Generator) -> float:
    """로그 스케일 파라미터는 배율로, 선형 파라미터는 범위 비율로 흔든다."""
    if param["scale"] == "log" or param["id"] in _TIME_KEYS:
        if value <= 0:
            return value
        return value * math.exp(rng.normal(0, amount * 0.45))
    span = param["max"] - param["min"]
    return value + rng.normal(0, amount * span * 0.12)


_LAYER_MUTABLE = {"repeat_gap", "repeat_gain", "bp_freq", "bp_q", "bp_sweep", "spread", "freq", "slide", "slide_accel", "arp_semitones", "arp_time", "vibrato_depth", "duty", "fm_depth",
                  "noise_color", "attack", "sustain", "decay", "decay_curve", "punch", "lp_cutoff", "lp_sweep",
                  "gain", "delay"}


def mutate(spec: dict, amount: float = 0.4, seed: int | None = None) -> dict:
    """spec의 수치 파라미터를 amount(0~1)만큼 무작위로 흔든다. 파형 종류·on/off는 유지."""
    amount = max(0.0, min(1.0, float(amount)))
    spec = normalize_spec(copy.deepcopy(spec))
    rng = np.random.default_rng(seed)
    for layer in spec["layers"]:
        for p in LAYER_PARAMS:
            if p["id"] in _LAYER_MUTABLE and p["type"] == "float":
                layer[p["id"]] = _jitter(p, layer[p["id"]], amount, rng)
    m = spec["master"]
    m["pitch"] += rng.normal(0, amount * 2.0)
    for key in ("echo_mix", "reverb_mix", "room_mix"):
        if m[key] > 0:
            m[key] *= math.exp(rng.normal(0, amount * 0.3))
    spec["seed"] = int(rng.integers(1, 2**31 - 1))
    return normalize_spec(spec)


def randomize(category: str | None = None, seed: int | None = None, amount: float = 0.6) -> tuple[str, dict]:
    rnd = random.Random(seed)
    if category not in PRESET_BY_ID:
        category = rnd.choice(PRESETS)["id"]
    base = normalize_spec(PRESET_BY_ID[category]["spec"])
    return category, mutate(base, amount, seed)


def variations(spec: dict, count: int = 8, amount: float = 0.3, seed: int | None = None) -> list[dict]:
    rng = np.random.default_rng(seed)
    return [mutate(spec, amount, int(rng.integers(1, 2**31 - 1))) for _ in range(max(1, min(count, 24)))]


def time_scale(spec: dict, k: float) -> dict:
    """모든 시간 관련 값을 k배(길게/짧게)."""
    spec = normalize_spec(copy.deepcopy(spec))
    for layer in spec["layers"]:
        for key in _TIME_KEYS:
            layer[key] *= k
    return normalize_spec(spec)


# ---- 설명(텍스트) → 프리셋 ------------------------------------------------

_MODIFIERS = [
    (r"큰|거대|묵직|무거운|낮은|굵은|\b(?:big|huge|large|heavy|deep|low)\b", "pitch", -5.0),
    (r"작은|가벼운|높은|얇은|\b(?:small|tiny|light|high|thin)\b", "pitch", +5.0),
    (r"짧은|짧게|빠른|빠르게|\b(?:short|quick|fast|snappy)\b", "time", 0.6),
    (r"(?<![가-힣])긴(?![가-힣])|길게|느린|느리게|\b(?:long|slow)\b", "time", 1.7),
    (r"메아리|울리는|동굴|성당|\b(?:echo|reverb|cave|hall|cathedral)\b", "reverb", 0.4),
    (r"레트로|8비트|칩튠|\b(?:retro|8-?bit|chiptune)\b", "bits", 8),
    (r"거친|더러운|왜곡|\b(?:distorted|gritty|dirty|harsh)\b", "dist", 0.35),
]


def from_text(text: str) -> dict:
    """한글/영어 설명에서 가장 알맞은 프리셋을 골라 수식어(크기·길이·울림 등)를 반영한다."""
    text = (text or "").strip().lower()
    # '리얼/실사'라 했으면 고퀄리티, '8비트/레트로'라 했으면 레트로 프리셋을 우선한다(말이 없으면 고퀄리티가 동점 우선)
    want = None
    if re.search(r"리얼|실사|현실|고퀄|사실적|영화|\b(?:realistic|real|hq|cinematic|high.?quality)\b", text):
        want = "hq"
    elif re.search(r"레트로|8비트|칩튠|\b(?:retro|8-?bit|chiptune)\b", text):
        want = "retro"
    scores = []
    for p in PRESETS:
        words = set(p["tags"].lower().split())  # 중복 태그로 점수가 부풀지 않게
        score = sum(1 for w in words if w in text)
        # 조사가 붙은 한글("폭발음이", "동전을")도 잡히도록 부분 일치도 반영
        score += sum(0.5 for w in words if len(w) >= 2 and w not in text and w in text.replace(" ", ""))
        if score > 0:
            style = p.get("style", "retro")
            score += 1.5 if want == style else (0.25 if want is None and style == "hq" else 0)
        scores.append((score, p["id"]))
    best_score, best_id = max(scores, key=lambda s: s[0])
    matched = best_score > 0
    if not matched:
        best_id = random.choice(PRESETS)["id"]
    spec = normalize_spec(PRESET_BY_ID[best_id]["spec"])

    applied = []
    for pattern, kind, val in _MODIFIERS:
        if not re.search(pattern, text):
            continue
        if kind == "pitch":
            spec["master"]["pitch"] += val
        elif kind == "time":
            spec = time_scale(spec, val)
        elif kind == "reverb":
            spec["master"]["reverb_mix"] = max(spec["master"]["reverb_mix"], val)
            spec["master"]["reverb_size"] = max(spec["master"]["reverb_size"], 0.7)
        elif kind == "bits":
            spec["master"]["bits"] = val
            spec["master"]["downsample"] = 2
        elif kind == "dist":
            spec["master"]["distortion"] = max(spec["master"]["distortion"], val)
        applied.append(kind)

    return {"category": best_id, "matched": matched, "modifiers": applied, "spec": normalize_spec(spec)}
