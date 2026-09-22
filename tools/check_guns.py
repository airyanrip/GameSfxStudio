"""총기 프리셋이 '서로 구분되는지'를 수치로 점검한다(귀로 듣는 것의 대용 지표).

  1) 특징 순서: 크랙 밝기(스펙트럼 중심), 저음 비율, 꼬리 길이, 발 수가 총기별로 의도한 순서인가
  2) 분리도: 서로 다른 총기 사이의 스펙트럼 거리 / 같은 총기를 변형(mutate)한 것끼리의 거리 (클수록 잘 구분됨)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from sfx import engine, presets, variation  # noqa: E402

SR = 44100
GUNS = ["hq_pistol", "hq_revolver", "hq_rifle", "hq_shotgun", "hq_machinegun", "hq_sniper", "hq_silenced"]
SPEC = {p["id"]: p["spec"] for p in presets.PRESETS}


def band_db(x: np.ndarray, lo: float, hi: float) -> float:
    m = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return float(10 * np.log10(m[(f >= lo) & (f < hi)].sum() + 1e-12))


def count_shots(x: np.ndarray, window_s: float = 0.5) -> int:
    """발사 순간에는 반드시 고음 크랙이 있으므로, 고음(>2.5kHz) 에너지 곡선이 직전 50ms 최소보다 10dB 이상 솟는 지점을
    한 발로 센다. (저음 노이즈의 잔물결·룸 리버브의 출렁임은 고음 크랙이 아니라서 세지 않는다.)"""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    spec[f < 2500] = 0
    hf = np.fft.irfft(spec, len(x))
    hop = int(0.004 * SR)
    n = len(hf) // hop
    e = 20 * np.log10(np.sqrt((hf[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    e -= e.max()
    out = [0]
    for i in range(1, min(n, int(window_s / 0.004))):
        if e[i] > -22 and e[i] - e[max(0, i - 12):i].min() > 10 and i - out[-1] > 10:
            out.append(i)
    return len(out)


def features(x: np.ndarray) -> dict:
    """crack_hf: 첫 30ms의 고음(3k~12k) 대 중음(0.4k~3k) 비 [dB] — 클수록 날카로운 크랙
    low_mid: 첫 250ms의 저음(40~180Hz) 대 중고음(0.4k~4k) 비 [dB] — 클수록 묵직한 '쿵'
    tail_s : 피크에서 -40dB까지 걸린 시간, shots: 첫 0.5초 안의 발 수"""
    i0 = int(np.nonzero(np.abs(x) > 0.1 * np.abs(x).max())[0][0])   # 시작 지점(소리가 처음 들리는 곳)
    w, h = x[i0: i0 + int(0.03 * SR)], x[i0: i0 + int(0.25 * SR)]
    env = np.sqrt(np.convolve(x ** 2, np.ones(441) / 441, "same"))
    db = 20 * np.log10(env / (env.max() + 1e-12) + 1e-9)
    ip = int(np.argmax(env))
    after = np.nonzero(db[ip:] < -40)[0]
    return {"crack_hf": band_db(w, 3000, 12000) - band_db(w, 400, 3000),
            "low_mid": band_db(h, 40, 180) - band_db(h, 400, 4000),
            "tail_s": (after[0] if len(after) else len(db) - ip) / SR, "shots": count_shots(x)}


def band_vec(x: np.ndarray, bands: int = 24) -> np.ndarray:
    head = x[: int(0.5 * SR)]
    spec = np.abs(np.fft.rfft(head * np.hanning(len(head)))) ** 2
    f = np.fft.rfftfreq(len(head), 1 / SR)
    edges = np.geomspace(50, 16000, bands + 1)
    v = np.array([10 * np.log10(spec[(f >= edges[i]) & (f < edges[i + 1])].mean() + 1e-12) for i in range(bands)])
    return v - v.mean()


def main() -> int:
    ok = True
    rend = {g: engine.render(SPEC[g], SR) for g in GUNS}
    feat = {g: features(x) for g, x in rend.items()}
    print(f"{'gun':16}{'crack HF dB':>12}{'low-mid dB':>11}{'tail s':>8}{'shots':>7}")
    for g in GUNS:
        r = feat[g]
        print(f"{g:16}{r['crack_hf']:12.1f}{r['low_mid']:11.1f}{r['tail_s']:8.2f}{r['shots']:7d}")

    def check(name: str, cond: bool) -> None:
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name)
        ok &= cond

    c = {g: feat[g]["crack_hf"] for g in GUNS}
    check("crack brightness: rifle > pistol > revolver, shotgun (heavy guns are duller)", c["hq_rifle"] > c["hq_pistol"] > max(c["hq_revolver"], c["hq_shotgun"]))
    check("crack brightness: silenced puff is duller than pistol crack", c["hq_silenced"] < c["hq_pistol"] - 1.0)
    lo = {g: feat[g]["low_mid"] for g in GUNS}
    check("low-end weight: shotgun > revolver > pistol", lo["hq_shotgun"] > lo["hq_revolver"] > lo["hq_pistol"])
    check("low-end weight: revolver > rifle", lo["hq_revolver"] > lo["hq_rifle"])
    t = {g: feat[g]["tail_s"] for g in GUNS}
    check("tail length: sniper > rifle > pistol", t["hq_sniper"] > t["hq_rifle"] > t["hq_pistol"])
    check("tail length: silenced shorter than pistol", t["hq_silenced"] < t["hq_pistol"])
    check("machine gun has >= 6 distinct shots in 0.5s", feat["hq_machinegun"]["shots"] >= 6)
    check("single-shot guns detect exactly 1 shot", all(feat[g]["shots"] == 1 for g in ("hq_pistol", "hq_revolver", "hq_rifle", "hq_shotgun")))
    check("silenced = soft puff + slide clack (2 events)", feat["hq_silenced"]["shots"] == 2)
    check("sniper = shot + distant echo (2 events in 0.5s)", feat["hq_sniper"]["shots"] == 2)

    # 분리도: 총기 간 거리 vs 같은 총기 변형 간 거리
    vec = {g: band_vec(x) for g, x in rend.items()}
    between = [np.mean(np.abs(vec[a] - vec[b])) for i, a in enumerate(GUNS) for b in GUNS[i + 1:]]
    within = []
    for g in GUNS:
        vs = [band_vec(engine.render(s, SR)) for s in variation.variations(SPEC[g], 4, 0.3, seed=7)]
        within += [np.mean(np.abs(vs[i] - vs[j])) for i in range(4) for j in range(i + 1, 4)]
    ratio = np.mean(between) / np.mean(within)
    print(f"spectral distance: between guns {np.mean(between):.2f} dB (min {min(between):.2f}) | within same gun (mutate 30%) {np.mean(within):.2f} dB | separability x{ratio:.1f}")
    check("guns are farther from each other than variations of one gun are (x1.5+)", ratio >= 1.5)
    check("closest pair of different guns is still clearly apart (>= 1.5 dB)", min(between) >= 1.5)
    print("ALL OK" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
