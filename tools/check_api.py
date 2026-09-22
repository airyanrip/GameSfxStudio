"""실행 중인 서버(127.0.0.1:8878)에 대한 API 통합 점검. 임시 프로젝트를 만들고 끝에 지운다.

사용: .venv\\Scripts\\python tools\\check_api.py [내보내기 테스트용 임시 폴더]
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import wave
import zipfile
from pathlib import Path

BASE = "http://127.0.0.1:8878"
PROJECT = "__selftest__"
fails = 0


def call(method: str, path: str, body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = r.read()
            return r.status, (payload if raw else json.loads(payload)), r.headers
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload), e.headers
        except ValueError:
            return e.code, payload, e.headers


def check(name: str, cond: bool, extra: str = "") -> None:
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    fails += 0 if cond else 1


def main() -> int:
    export_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
    call("DELETE", f"/api/projects/{PROJECT}")

    st, schema, _ = call("GET", "/api/sfx/schema")
    check("schema has 36 presets", st == 200 and len(schema["presets"]) == 36, str(st))
    spec = schema["presets"][0]["spec"]

    st, wav, hdr = call("POST", "/api/sfx/render", {"spec": spec}, raw=True)
    with wave.open(io.BytesIO(wav)) as w:
        ok = w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() in (22050, 44100, 48000) and w.getnframes() > 100
    check("render returns valid mono 16-bit WAV", st == 200 and ok)
    check("render X-Duration header", float(hdr["X-Duration"]) > 0.05)

    st, wav2, _ = call("POST", "/api/sfx/render", {"spec": spec}, raw=True)
    check("render is deterministic", wav == wav2)
    st, wav3, _ = call("POST", "/api/sfx/render", {"spec": spec, "sample_rate": 22050}, raw=True)
    with wave.open(io.BytesIO(wav3)) as w:
        check("sample_rate override honoured", w.getframerate() == 22050)

    st, _, _ = call("POST", "/api/sfx/render", {"spec": {"layers": [{"freq": "abc", "attack": -9}], "master": {"pitch": 1e9}}}, raw=True)
    check("garbage spec is clamped, not a 500", st == 200, str(st))
    st, _, _ = call("POST", "/api/sfx/render", {"nope": 1})
    check("missing spec → 422", st == 422, str(st))

    st, r, _ = call("POST", "/api/sfx/randomize", {"category": "explosion", "seed": 5})
    check("randomize", st == 200 and r["category"] == "explosion" and r["spec"]["layers"])
    st, r, _ = call("POST", "/api/sfx/mutate", {"spec": spec, "amount": 0.5})
    check("mutate changes spec", st == 200 and r["spec"] != spec)
    st, r, _ = call("POST", "/api/sfx/variations", {"spec": spec, "count": 8, "amount": 0.3})
    check("variations x8 all distinct", st == 200 and len({json.dumps(s, sort_keys=True) for s in r["specs"]}) == 8)
    st, r, _ = call("POST", "/api/sfx/from_text", {"text": "짧은 동전 소리"})
    check("from_text 짧은 동전 → coin", st == 200 and r["category"] == "coin" and "time" in r["modifiers"], str(r))
    st, r, _ = call("POST", "/api/sfx/from_text", {"text": "big explosion in a cave"})
    check("from_text english → explosion", st == 200 and r["category"] in ("explosion", "hq_explosion"), str(r))
    st, r, _ = call("POST", "/api/sfx/from_text", {"text": "slow door"})
    check("english 'slow' does not trigger 'low' pitch", "pitch" not in r["modifiers"] and r["category"] == "door", str(r))
    st, _, _ = call("POST", "/api/sfx/from_text", {"text": "  "})
    check("empty description → 400", st == 400)

    st, _, _ = call("POST", "/api/projects", {"name": PROJECT})
    check("create project", st == 200)
    st, _, _ = call("POST", "/api/projects", {"name": PROJECT})
    check("duplicate project → 400", st == 400)
    for bad in ("../evil", "a/b", "CON", ".hidden", "x" * 60, "a:b"):
        st, _, _ = call("POST", "/api/projects", {"name": bad})
        check(f"bad project name rejected: {bad[:12]}", st in (400, 404), str(st))

    p = f"/api/projects/{PROJECT}"
    st, a, _ = call("POST", f"{p}/sounds", {"name": "coin_01", "spec": spec, "category": "coin"})
    check("save sound", st == 200 and a["duration"] > 0 and "spec" not in a, str(a))
    st, b, _ = call("POST", f"{p}/sounds", {"name": "coin_01", "spec": spec, "category": "coin"})
    check("second sound with same name saved", st == 200 and b["id"] != a["id"])
    st, _, _ = call("POST", f"{p}/sounds", {"name": "bad/name", "spec": spec})
    check("bad sound name rejected", st == 400)
    st, _, _ = call("POST", f"/api/projects/nope_project/sounds", {"name": "x", "spec": spec})
    check("save into missing project → 404", st == 404, str(st))

    st, lst, _ = call("GET", f"{p}/sounds")
    check("list sounds (2, no spec)", st == 200 and len(lst) == 2 and all("spec" not in s for s in lst))
    st, full, _ = call("GET", f"{p}/sounds/{a['id']}")
    check("get sound includes spec", st == 200 and full["spec"]["layers"])
    st, over, _ = call("POST", f"{p}/sounds", {"name": "coin_renamed", "spec": full["spec"], "sound_id": a["id"]})
    check("overwrite keeps id", st == 200 and over["id"] == a["id"] and over["name"] == "coin_renamed")
    st, ren, _ = call("PUT", f"{p}/sounds/{b['id']}", {"name": "coin_02"})
    check("rename", st == 200 and ren["name"] == "coin_02")
    st, w, _ = call("GET", f"{p}/sounds/{a['id']}/audio", raw=True)
    check("audio download is RIFF", st == 200 and w[:4] == b"RIFF")
    st, _, _ = call("GET", f"{p}/sounds/..%2F..%2Fproject/audio")
    check("sound id traversal rejected", st in (400, 404), str(st))

    st, r, _ = call("POST", f"{p}/export", {"dir": str(export_dir)})
    files = sorted(f.name for f in export_dir.glob("*.wav"))
    check("export to folder", st == 200 and r["count"] == 2 and files == ["coin_02.wav", "coin_renamed.wav"], f"{r} {files}")
    st, r, _ = call("POST", f"{p}/export", {"dir": "relative\\path"})
    check("relative export dir rejected", st == 400)
    st, z, _ = call("GET", f"{p}/export.zip", raw=True)
    check("zip export", st == 200 and sorted(zipfile.ZipFile(io.BytesIO(z)).namelist()) == files)

    st, projs, _ = call("GET", "/api/projects")
    check("project list shows count", any(x["name"] == PROJECT and x["count"] == 2 for x in projs))
    st, _, _ = call("DELETE", f"{p}/sounds/{b['id']}")
    st, lst, _ = call("GET", f"{p}/sounds")
    check("delete sound", len(lst) == 1)

    st, s0, _ = call("GET", "/api/settings")
    st, s1, _ = call("PUT", "/api/settings", {"sample_rate": 22050, "preview_volume": 7})
    check("settings clamp + save", st == 200 and s1["sample_rate"] == 22050 and s1["preview_volume"] == 1.0)
    st, _, _ = call("PUT", "/api/settings", {"sample_rate": 12345})
    check("invalid sample rate → 400", st == 400)
    call("PUT", "/api/settings", {"sample_rate": s0["sample_rate"], "preview_volume": s0["preview_volume"]})

    call("DELETE", f"{p}")
    st, projs, _ = call("GET", "/api/projects")
    check("project deleted", not any(x["name"] == PROJECT for x in projs))
    print("FAILURES:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
