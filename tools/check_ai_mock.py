"""AI 경로 점검(모의 워커): 앱 서버를 GAMESFX_AI_MOCK=1 로 켠 상태에서 실행한다. 진짜 모델 품질은 검증하지 않고,
워커 기동·생성 작업·무음 트림·샘플 저장·샘플 레이어 렌더·워커 종료 흐름만 확인한다."""
import io, json, sys, time, urllib.request, wave

BASE = "http://127.0.0.1:8878"
fails = 0

def call(method, path, body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            p = r.read(); return r.status, (p if raw else json.loads(p))
    except urllib.error.HTTPError as e:
        p = e.read()
        try: return e.code, json.loads(p)
        except ValueError: return e.code, p

def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else "")); fails += 0 if cond else 1

st, s = call("GET", "/api/ai/status")
check("status: installed + model_ready(mock)", st == 200 and s["installed"] and s["model_ready"] and s["mock"], str(s))
check("worker not running yet", not s["worker_running"])
st, r = call("GET", "/api/ai/recipes"); check("recipes listed", st == 200 and len(r["recipes"]) >= 20)
st, r = call("POST", "/api/ai/generate", {})
check("empty request rejected", st == 400, str(r))

t0 = time.time()
st, r = call("POST", "/api/ai/generate", {"recipe": "pistol", "env": "indoor", "distance": "close", "extra": "아주 날카로운", "seconds": 2.0, "steps": 30, "count": 2, "seed": 100})
check("generate accepted", st == 200, str(r))
jid = r["job_id"]
st, r2 = call("POST", "/api/ai/generate", {"recipe": "pistol"})
check("second job while running -> 409", st == 409, str(r2))
job = None
for _ in range(240):
    st, job = call("GET", f"/api/ai/jobs/{jid}")
    if job["status"] != "running": break
    time.sleep(0.5)
check("job finished OK", job["status"] == "done", str(job))
print("   prompt:", job["prompt"])
check("prompt contains recipe+translated extra+env", "pistol gunshot" in job["prompt"] and "very" in job["prompt"] and "sharp" in job["prompt"] and "concrete room" in job["prompt"])
check("2 candidates, distinct seeds", len(job["results"]) == 2 and job["results"][0]["seed"] != job["results"][1]["seed"])
res = job["results"][0]
check("mock 2.0s clip trimmed shorter than requested", 0.1 < res["duration"] < 1.9, str(res))
st, wav = call("GET", f"/api/samples/{res['id']}", raw=True)
with wave.open(io.BytesIO(wav)) as w:
    check("stored sample is mono 16-bit 44.1k", w.getnchannels() == 1 and w.getframerate() == 44100)
spec = {"layers": [{"wave": "sample", "sample": res["id"], "gain": 1.0, "decay": 0.05}], "master": {"room_mix": 0.2, "comp": 0.3}}
st, out = call("POST", "/api/sfx/render", {"spec": spec}, raw=True)
with wave.open(io.BytesIO(out)) as w:
    dur = w.getnframes() / w.getframerate()
check("sample layer renders via API", st == 200 and 0.5 * res["duration"] < dur < res["duration"] + 3, f"{dur} vs {res['duration']}")
st, s = call("GET", "/api/ai/status"); check("worker running after job", s["worker_running"] and s["worker"]["mock"])
st, _ = call("POST", "/api/ai/stop")
time.sleep(1.5)
st, s = call("GET", "/api/ai/status"); check("worker stopped by /api/ai/stop", not s["worker_running"], str(s["worker"]))
print("elapsed %.1fs | FAILURES: %d" % (time.time() - t0, fails)); sys.exit(1 if fails else 0)
