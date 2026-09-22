"""AI 모델 선택 + 비상업 라이선스 추적 점검 (실행 중인 서버 127.0.0.1:8878 필요).

  기본(모의 워커, GAMESFX_AI_MOCK=1 서버):  python tools/check_ai_models.py
  실제 모델(AudioLDM2 설치되어 있어야 함, 모의 아닌 서버): python tools/check_ai_models.py --real

확인 항목: 모델 목록/상업 여부, 비상업 모델로 만든 샘플의 nc 표시, 그 샘플을 쓴 효과음의 자동 표시(직접 올린 샘플과 대조),
내보낼 때 경고 개수, 상업 모델 결과는 표시되지 않음.
"""
import io, json, sys, tempfile, time, urllib.request, wave
from pathlib import Path

BASE = "http://127.0.0.1:8878"
REAL = "--real" in sys.argv
PROJECT = "__aimodels__"
fails = 0


def call(method, path, body=None, raw=False, ctype="application/json"):
    data = body if isinstance(body, (bytes, bytearray)) else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            p = r.read(); return r.status, (p if raw else json.loads(p))
    except urllib.error.HTTPError as e:
        p = e.read()
        try: return e.code, json.loads(p)
        except ValueError: return e.code, p


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else "")); fails += 0 if cond else 1


def run_job(model, steps, seconds, count=1):
    st, r = call("POST", "/api/ai/generate", {"model": model, "recipe": "pistol", "seconds": seconds, "steps": steps, "count": count, "seed": 7})
    assert st == 200, (st, r)
    for _ in range(1800):
        st, job = call("GET", f"/api/ai/jobs/{r['job_id']}")
        if job["status"] != "running":
            return job
        time.sleep(0.5)
    raise TimeoutError


def main():
    st, s = call("GET", "/api/ai/status")
    ms = {m["id"]: m for m in s["models"]}
    check("two models listed", set(ms) == {"sao", "audioldm2"}, str(list(ms)))
    check("sao is commercial-OK, needs token", ms["sao"]["commercial"] and ms["sao"]["needs_token"])
    check("audioldm2 is non-commercial, no token", (not ms["audioldm2"]["commercial"]) and (not ms["audioldm2"]["needs_token"]))
    check("mock mode: both ready" if not REAL else "real mode: audioldm2 ready", ms["audioldm2"]["ready"] and (REAL or ms["sao"]["ready"]))
    check("real mode: sao not installed (needs token)" if REAL else "unknown model rejected",
          (not ms["sao"]["ready"]) if REAL else call("POST", "/api/ai/generate", {"model": "nope", "recipe": "pistol"})[0] == 400)

    if REAL:
        st, r = call("POST", "/api/ai/generate", {"model": "sao", "recipe": "pistol"})
        check("generating with the not-installed sao model is refused with a clear message", st == 409 and "sao" not in str(r).lower() or st == 409, str(r))
        st, r = call("POST", "/api/ai/download", {"model": "sao", "token": ""})
        check("sao download without token is refused", st == 400, str(r))

    job = run_job("audioldm2", steps=30 if REAL else 20, seconds=2.0)
    check("audioldm2 job finished", job["status"] == "done", str(job))
    res = job["results"][0]
    check("job + result flagged non-commercial", job["noncommercial"] and res["noncommercial"], str(res))
    st, info = call("GET", f"/api/samples/{res['id']}/info")
    check("sample info reports noncommercial", info["noncommercial"] is True)

    # 직접 올린(상업 안전) 샘플은 표시되지 않아야 한다
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100); w.writeframes((b"\x00\x20\x00\xe0") * 5000)
    st, mine = call("POST", "/api/samples", buf.getvalue(), ctype="audio/wav")
    check("user-uploaded sample is NOT flagged", st == 200 and mine["noncommercial"] is False, str(mine))

    call("DELETE", f"/api/projects/{PROJECT}")
    call("POST", "/api/projects", {"name": PROJECT})
    p = f"/api/projects/{PROJECT}"
    nc_spec = {"layers": [{"wave": "sample", "sample": res["id"], "gain": 1.0, "decay": 0.05}], "master": {}}
    ok_spec = {"layers": [{"wave": "sample", "sample": mine["id"], "gain": 1.0, "decay": 0.05}], "master": {}}
    mix_spec = {"layers": [{"wave": "sine", "freq": 80, "sustain": 0.1}, {"wave": "sample", "sample": res["id"]}], "master": {}}
    st, a = call("POST", f"{p}/sounds", {"name": "ai_nc", "spec": nc_spec})
    st, b = call("POST", f"{p}/sounds", {"name": "mine_ok", "spec": ok_spec})
    st, c = call("POST", f"{p}/sounds", {"name": "layered_nc", "spec": mix_spec})
    check("sound using nc sample is auto-flagged", a["noncommercial"] is True)
    check("sound using own sample is not flagged", b["noncommercial"] is False)
    check("nc sample layered under synth still flags the sound", c["noncommercial"] is True)
    st, lst = call("GET", f"{p}/sounds")
    check("library list carries the flag", {x["name"]: x["noncommercial"] for x in lst} == {"ai_nc": True, "mine_ok": False, "layered_nc": True})
    out = Path(tempfile.mkdtemp())
    st, ex = call("POST", f"{p}/export", {"dir": str(out)})
    check("export warns with the number of non-commercial sounds", st == 200 and ex["noncommercial"] == 2 and ex["count"] == 3, str(ex))
    check("re-saving (overwrite) keeps the flag", call("POST", f"{p}/sounds", {"name": "ai_nc", "spec": nc_spec, "sound_id": a["id"]})[1]["noncommercial"] is True)
    # 우회 방지: AI(비상업)가 만든 샘플을 파일로 받아 그대로 다시 '직접 올려도' 비상업 표시가 유지되어야 한다
    st, ai_wav = call("GET", f"/api/samples/{res['id']}", raw=True)
    st, again = call("POST", "/api/samples", ai_wav, ctype="audio/wav")
    check("re-uploading an AI (nc) sample does not launder the flag", st == 200 and again["id"] == res["id"] and again["noncommercial"] is True, str(again))
    st, hit = call("POST", "/api/samples", buf.getvalue(), ctype="audio/wav")
    check("own sample stays unflagged after re-upload", hit["noncommercial"] is False)

    if not REAL:  # 모의 서버: 상업 모델(sao) 결과는 표시되지 않아야 한다
        job2 = run_job("sao", steps=20, seconds=1.5)
        r2 = job2["results"][0]
        check("commercial model (sao) result is NOT flagged", job2["status"] == "done" and not r2["noncommercial"] and not job2["noncommercial"], str(job2)[:200])
        st, d = call("POST", f"{p}/sounds", {"name": "sao_ok", "spec": {"layers": [{"wave": "sample", "sample": r2["id"]}], "master": {}}})
        check("sound made from sao sample is not flagged", d["noncommercial"] is False)
    if REAL:
        with wave.open(io.BytesIO(call("GET", f"/api/samples/{res['id']}", raw=True)[1])) as w:
            check("real audioldm2 clip stored as mono 16k, non-silent", w.getnchannels() == 1 and w.getframerate() == 16000 and w.getnframes() > 8000)

    call("DELETE", f"/api/projects/{PROJECT}")
    call("POST", "/api/ai/stop")
    print("FAILURES:", fails); sys.exit(1 if fails else 0)


main()
