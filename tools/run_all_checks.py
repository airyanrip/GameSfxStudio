"""모든 자동 점검을 순서대로 실행하고 요약한다 (서버 기동·종료, 시험용 환경변수 포함).

  python tools/run_all_checks.py            → 엔진/총기 + API + AI(모의) + 설치 도우미 + 브라우저(UI) 점검
  python tools/run_all_checks.py --no-ui    → 브라우저(playwright/Edge) 점검 제외

UI 점검은 `uv`(https://docs.astral.sh/uv/)와 Microsoft Edge 가 있어야 한다. 실제 AI 모델·실제 설치 점검은
시간/용량이 커서 포함하지 않는다: tools/check_ai_models.py --real, tools/check_installer_real.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe") if (ROOT / ".venv" / "Scripts" / "python.exe").exists() else sys.executable
UV = shutil.which("uv")
NO_UI = "--no-ui" in sys.argv
SHOTS = Path(tempfile.mkdtemp(prefix="gamesfx_shots_"))
results: list[tuple[str, bool]] = []


def run(name: str, cmd: list[str], env: dict | None = None, timeout: int = 900) -> bool:
    print(f"\n=== {name}", flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT), env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})},
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    lines = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.startswith(("PASS", "FAIL", "FAILURES", "ALL OK", "SOME", "Traceback"))
             or "Error" in ln]
    bad = [ln for ln in lines if ln.startswith(("FAIL ", "Traceback")) or "Error" in ln]
    n_pass = sum(ln.startswith("PASS") for ln in lines)
    print("\n".join(bad[:12]) if bad else (f"{n_pass} checks passed" if n_pass else "OK (exit code 0)"), flush=True)
    ok = r.returncode == 0
    results.append((name, ok))
    return ok


class Server:
    """시험용 서버(8878)를 환경변수와 함께 켜고, 끝나면 AI 워커까지 정리한다."""

    def __init__(self, env: dict):
        self.env, self.proc = env, None

    def __enter__(self):
        for f in ("settings.json", "user_presets.json"):
            (ROOT / "data" / f).unlink(missing_ok=True)
        shutil.rmtree(ROOT / "data" / "samples", ignore_errors=True)
        self.proc = subprocess.Popen([PY, "-m", "uvicorn", "web_server:app", "--port", "8878", "--log-level", "warning"],
                                     cwd=str(ROOT / "app"), env={**os.environ, **self.env}, creationflags=0x08000000)
        for _ in range(60):
            try:
                urllib.request.urlopen("http://127.0.0.1:8878/api/settings", timeout=1).read()
                return self
            except OSError:
                time.sleep(0.5)
        raise RuntimeError("서버가 시작되지 않았습니다")

    def __exit__(self, *exc):
        try:
            urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8878/api/ai/stop", data=b"", method="POST"), timeout=5).close()
        except OSError:
            pass
        self.proc.terminate()
        self.proc.wait(timeout=15)
        for f in ("settings.json", "user_presets.json"):
            (ROOT / "data" / f).unlink(missing_ok=True)
        shutil.rmtree(ROOT / "data" / "samples", ignore_errors=True)


def ui(name: str, script: str, *extra: str, env=None) -> None:
    if NO_UI:
        return
    if not UV:
        print(f"\n=== {name}\n(건너뜀: uv 가 없습니다)")
        return
    run(name, [UV, "run", "--with", "playwright", "--with", "numpy", "python", f"tools/{script}", str(SHOTS), *extra], env)


def main() -> int:
    run("engine + presets", [PY, "tools/check_engine.py"])
    run("guns are distinguishable", [PY, "tools/check_guns.py"])
    with Server({"GAMESFX_AI_MOCK": "1"}):
        run("HTTP API", [PY, "tools/check_api.py", str(SHOTS / "export")])
        run("AI pipeline (mock worker)", [PY, "tools/check_ai_mock.py"])
        run("AI models + non-commercial tracking (mock)", [PY, "tools/check_ai_models.py"])
        ui("UI: workshop / library / settings", "ui_smoke.py")
        ui("UI: AI / learning / samples", "ui_ai_smoke.py", str(SHOTS / "refs"))
    with Server({"GAMESFX_SETUP_DRYRUN": "nopython"}):
        ui("UI: first-run setup wizard (simulated install)", "ui_setup_smoke.py")
    print("\n" + "=" * 50)
    for name, ok in results:
        print(("PASS  " if ok else "FAIL  ") + name)
    failed = [n for n, ok in results if not ok]
    print("ALL SUITES PASSED" if not failed else f"{len(failed)} SUITE(S) FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
