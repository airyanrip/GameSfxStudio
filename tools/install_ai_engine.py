"""AI 엔진 설치(명령줄 버전) — 앱의 '설치 도우미'와 같은 설치 로직(app/installer.py)을 그대로 쓴다.

  python tools/install_ai_engine.py          → 무엇을 설치할지 보여주고 물어본 뒤 진행
  python tools/install_ai_engine.py --yes    → 묻지 않고 진행(Python 자동 설치 포함)
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import installer  # noqa: E402


def ask(question: str) -> bool:
    if "--yes" in sys.argv:
        return True
    return input(question + " [y/N] ").strip().lower() in ("y", "yes")


def main() -> int:
    mgr = installer.SetupManager(ROOT / "engine" / "sao")
    st = mgr.status()
    print("== AI engine setup ==")
    print(f"GPU     : {st['gpu']['name'] + ' (' + str(st['gpu']['vram_gb']) + ' GB)' if st['gpu'] else 'none found (will use the slow CPU build)'}")
    print(f"Python  : {st['python']['version'] + ' at ' + st['python']['path'] if st['python'] else 'not found'}")
    print(f"Disk    : {st['disk_free_gb']} GB free (engine ~{st['needed_gb']['engine']} GB, with models ~{st['needed_gb']['models']} GB)")
    if st["engine"]["ok"]:
        print(f"Already installed: torch {st['engine']['torch']}, CUDA {st['engine']['cuda']}. Nothing to do.")
        return 0
    if not st["path"]["ok"]:
        print(f"ERROR: the program folder path is too long ({st['path']['len']} > {st['path']['max']}). Move it to a short path like C:\\GameSfxStudio.")
        return 2
    allow_python = False
    if not st["python"]:
        print("Python 3.11-3.12 is missing. The official python.org installer (about 25 MB) can be downloaded, "
              "its signature verified, and installed for the current user only (no admin rights).")
        if not ask("Install Python 3.11 automatically?"):
            print("Cancelled. Install Python 3.11 from https://www.python.org/downloads/ and run this again.")
            return 1
        allow_python = True
    print("This will create engine\\sao\\venv and install PyTorch 2.6.0 + diffusers/transformers (about 3-4 GB download).")
    if not ask("Continue?"):
        print("Cancelled.")
        return 1
    mgr.start_engine_install(allow_python)
    shown = 0
    while True:
        job = mgr.job()
        for line in job["log"][shown - len(job["log"]):] if shown < len(job["log"]) else []:
            print(line)
        shown = len(job["log"])
        if job["state"] != "running":
            break
        time.sleep(1)
    print("\nRESULT:", job["state"], job.get("error", ""))
    if job["state"] == "done":
        print("Next: start the app and download an AI model in Settings > AI models.")
    return 0 if job["state"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
