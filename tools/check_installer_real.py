"""설치 도우미의 '진짜' 자동 설치를 빈 폴더에서 끝까지 검증한다(약 3~4GB 다운로드, 10~20분).

  1) 빈 engine 폴더에 worker.py / requirements-ai.txt 만 복사
  2) SetupManager 로 실제 설치(venv → PyTorch → 고정 라이브러리 → 확인)
  3) 새 환경에서 두 파이프라인 import + (모델이 있으면) 실제 생성

사용: .venv\\Scripts\\python tools\\check_installer_real.py <스크래치 폴더> [--model-dir <model_audioldm2 경로>]
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import installer  # noqa: E402

scratch = Path(sys.argv[1])
model_dir = Path(sys.argv[sys.argv.index("--model-dir") + 1]) if "--model-dir" in sys.argv else None
fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""), flush=True)
    fails += 0 if cond else 1


shutil.rmtree(scratch, ignore_errors=True)
eng = scratch / "engine_sao"
eng.mkdir(parents=True)
for f in ("worker.py", "requirements-ai.txt"):
    shutil.copy(ROOT / "engine" / "sao" / f, eng / f)

mgr = installer.SetupManager(eng)
check("fresh folder: engine reported NOT installed", not mgr.engine_state()["ok"] and not mgr.engine_state()["venv"])
t0 = time.time()
mgr.start_engine_install(allow_python_install=False)
last_step = -1
seen_log = 0
while True:
    job = mgr.job()
    if job["step"] != last_step:
        last_step = job["step"]
        print(f"  [{time.time() - t0:5.0f}s] step {job['step']}/{job['steps']}: {job['label']}", flush=True)
    if job["state"] != "running":
        break
    time.sleep(3)
print(f"install finished in {time.time() - t0:.0f}s with state={job['state']}", flush=True)
if job["state"] != "done":
    print("\n".join(job["log"][-25:]))
check("installer finished with state=done", job["state"] == "done", job.get("error", ""))
st = mgr.engine_state()
check("engine verified: torch + diffusers import", st["ok"], str(st))
check("CUDA available in the fresh venv (this PC has an NVIDIA GPU)", st["cuda"], str(st))
check("torch is the pinned 2.6.0", st["torch"].startswith("2.6.0"), st["torch"])
check("marker file written", (eng / ".engine_installed.json").exists())
r = subprocess.run([str(mgr.python), "-c", "from diffusers import AudioLDM2Pipeline, StableAudioPipeline; import transformers, huggingface_hub; "
                    "print(transformers.__version__, huggingface_hub.__version__)"], capture_output=True, text=True)
check("both pipelines import with the pinned set", r.returncode == 0 and r.stdout.split()[0] == "4.49.0", (r.stdout + r.stderr)[-300:])

if model_dir and model_dir.exists() and job["state"] == "done":
    subprocess.run(["cmd", "/c", "mklink", "/J", str(eng / "model_audioldm2"), str(model_dir)], capture_output=True)
    check("model junction created", (eng / "model_audioldm2" / "model_index.json").exists())
    proc = subprocess.Popen([str(mgr.python), str(eng / "worker.py"), "--port", "8891"], cwd=str(eng),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=installer.NO_WINDOW)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen("http://127.0.0.1:8891/status", timeout=2).read()
                break
            except OSError:
                time.sleep(1)
        body = json.dumps({"model": "audioldm2", "prompt": "single pistol gunshot, sharp crack", "seconds": 2.0, "steps": 20, "seed": 3}).encode()
        t1 = time.time()
        wav = urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8891/generate", data=body,
                                     headers={"Content-Type": "application/json"}), timeout=900).read()
        check("REAL generation from the freshly auto-installed environment", wav[:4] == b"RIFF" and len(wav) > 30000,
              f"{len(wav)} bytes")
        print(f"  generation took {time.time() - t1:.0f}s (includes model load)", flush=True)
    finally:
        try:
            urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8891/shutdown", data=b"", method="POST"), timeout=3).close()
        except OSError:
            pass
        proc.wait(timeout=15) if proc.poll() is None else None
print("FAILURES:", fails, flush=True)
sys.exit(1 if fails else 0)
