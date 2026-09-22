"""엔진 자가검증: 모든 프리셋을 렌더해 유한값/피크/길이/렌더시간을 점검하고, 스펙트로그램 PNG를 저장한다.

사용: .venv\\Scripts\\python tools\\check_engine.py [출력폴더]
(PNG 저장은 matplotlib이 있을 때만; 없으면 수치 검증만 한다)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import numpy as np  # noqa: E402

from sfx import engine, presets, variation  # noqa: E402


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    failures = 0
    rendered = []
    print(f"{'id':11} {'len(s)':>7} {'peak':>6} {'rms':>6} {'ms':>5}  centroid(Hz)")
    for p in presets.PRESETS:
        spec = engine.normalize_spec(p["spec"])
        t0 = time.perf_counter()
        x = engine.render(spec, 44100)
        ms = (time.perf_counter() - t0) * 1000
        ok = np.all(np.isfinite(x)) and 0.02 < len(x) / 44100 < engine.MAX_SECONDS and 0.3 < np.max(np.abs(x)) <= 1.0
        mag = np.abs(np.fft.rfft(x))
        cent = float((mag * np.fft.rfftfreq(len(x), 1 / 44100)).sum() / max(mag.sum(), 1e-9))
        print(f"{p['id']:11} {len(x)/44100:7.2f} {np.max(np.abs(x)):6.2f} {np.sqrt(np.mean(x**2)):6.3f} {ms:5.0f}  {cent:8.0f}"
              + ("" if ok else "   <-- FAIL"))
        failures += 0 if ok else 1
        rendered.append((p["id"], x))

    # 변형/랜덤/텍스트/극단값 견고성
    for i in range(30):
        _, s = variation.randomize(None, seed=i, amount=1.0)
        x = engine.render(s)
        if not np.all(np.isfinite(x)):
            print("randomize NaN", i)
            failures += 1
    for bad in ({}, {"layers": []}, {"layers": [{"freq": "abc", "wave": "zzz", "attack": -5, "decay": 999}]},
                {"layers": [{}] * 20, "master": {"pitch": 1e9, "echo_mix": 1, "reverb_mix": 1, "bits": 0}}):
        x = engine.render(bad)
        if not np.all(np.isfinite(x)) or len(x) / 44100 > engine.MAX_SECONDS + 0.01:
            print("robustness fail", bad)
            failures += 1
    r = variation.from_text("아주 큰 폭발음 동굴에서")
    print("from_text →", r["category"], r["matched"], r["modifiers"])
    assert r["category"] == "hq_explosion", r["category"]

    if out_dir:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("(matplotlib 없음 → PNG 생략)")
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            cols = 4
            rows = (len(rendered) + cols - 1) // cols
            fig, axes = plt.subplots(rows, cols, figsize=(cols * 4, rows * 2.4))
            for ax, (name, x) in zip(axes.flat, rendered):
                ax.specgram(x, NFFT=512, Fs=44100, noverlap=384, cmap="magma", vmin=-120)
                ax.set_ylim(0, 12000)
                ax.set_title(name, fontsize=9)
            fig.tight_layout()
            fig.savefig(out_dir / "spectrograms.png", dpi=80)
            print("saved", out_dir / "spectrograms.png")
    print("FAILURES:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
