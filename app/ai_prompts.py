"""AI 효과음용 프롬프트 레시피. Stable Audio Open은 영어 프롬프트에 가장 잘 반응하므로,
카테고리·공간·거리를 고르거나 한국어로 적으면 영어 '영화 사운드 디자인' 프롬프트로 조립한다."""
from __future__ import annotations

import re

_TAIL = "cinematic sound design, high fidelity, professional recording, isolated sound effect, no music"

# id, 아이콘, 한글, 영문, 프롬프트 본문, 권장 길이(초), 보강용 합성 레이어 종류
RECIPES: list[dict] = [
    dict(id="pistol", icon="🔫", ko="권총", en="Pistol", seconds=2.5, boost="gun",
         prompt="single pistol gunshot, sharp loud crack, punchy low-end thump, snappy transient"),
    dict(id="revolver", icon="🤠", ko="리볼버", en="Revolver", seconds=3.0, boost="gun",
         prompt="single revolver gunshot, heavy booming crack, big magnum blast, long decaying tail"),
    dict(id="rifle", icon="🎯", ko="소총", en="Rifle", seconds=3.0, boost="gun",
         prompt="single assault rifle gunshot, aggressive sharp crack, deep body, echoing tail"),
    dict(id="shotgun", icon="💢", ko="샷건", en="Shotgun", seconds=3.0, boost="gun",
         prompt="single shotgun blast, massive boom, heavy low-end, powerful punch, rolling tail"),
    dict(id="machinegun", icon="🔥", ko="기관총 연사", en="Machine gun burst", seconds=3.5, boost="",
         prompt="machine gun burst of rapid gunshots, tight fast fire, mechanical rattle, shell casings"),
    dict(id="sniper", icon="🔭", ko="저격총", en="Sniper", seconds=4.5, boost="gun",
         prompt="single sniper rifle gunshot, distant echoing crack, long valley reverb tail"),
    dict(id="silenced", icon="🤫", ko="소음기 권총", en="Silenced pistol", seconds=1.8, boost="",
         prompt="silenced pistol shot, soft muffled thud, subtle mechanical slide click, quiet"),
    dict(id="explosion", icon="🌋", ko="대형 폭발", en="Big explosion", seconds=6.0, boost="explosion",
         prompt="huge explosion, deep sub bass boom, rolling rumble, debris falling, long thunderous tail"),
    dict(id="explosion_small", icon="💣", ko="소형 폭발", en="Small explosion", seconds=3.0, boost="explosion",
         prompt="grenade explosion, sharp blast, quick boom, scattering debris"),
    dict(id="sword_swing", icon="⚔️", ko="검 휘두르기", en="Sword swing", seconds=1.6, boost="",
         prompt="sword swing whoosh through the air, fast blade cut, sharp swish"),
    dict(id="sword_clash", icon="🤺", ko="검 부딪힘", en="Sword clash", seconds=2.5, boost="",
         prompt="two steel swords clashing, metallic clang, ringing overtones, sharp ring"),
    dict(id="sword_hit", icon="🩸", ko="검 베기 피격", en="Blade hit", seconds=1.6, boost="impact",
         prompt="sword slashing flesh, wet meaty slice impact, blade hit"),
    dict(id="punch", icon="🥊", ko="펀치·타격", en="Punch impact", seconds=1.4, boost="impact",
         prompt="heavy punch impact to the body, deep thud, dense meaty hit, cinematic fight"),
    dict(id="arrow", icon="🏹", ko="화살", en="Arrow", seconds=1.6, boost="",
         prompt="bow string release and arrow whoosh flying, then arrow thud impact"),
    dict(id="fireball", icon="☄️", ko="화염구", en="Fireball", seconds=3.5, boost="",
         prompt="fireball spell cast, roaring flames whoosh, crackling fire, explosive impact"),
    dict(id="lightning", icon="⚡", ko="번개 마법", en="Lightning", seconds=3.0, boost="",
         prompt="lightning bolt strike, electric crackle, sharp zap, thunder crack"),
    dict(id="ice", icon="🧊", ko="얼음 마법", en="Ice magic", seconds=3.0, boost="",
         prompt="ice magic spell, crystal freezing, glassy shatter, cold shimmering whoosh"),
    dict(id="shield", icon="🛡️", ko="방패 막기", en="Shield block", seconds=1.8, boost="impact",
         prompt="heavy shield block impact, metallic thud with wooden creak, armor rattle"),
    dict(id="footstep", icon="👣", ko="발걸음(자갈)", en="Footsteps", seconds=3.0, boost="",
         prompt="footsteps walking on gravel, crunchy steps, steady pace"),
    dict(id="door", icon="🚪", ko="문 열림(삐걱)", en="Door creak", seconds=3.0, boost="",
         prompt="heavy wooden door creaking open slowly, old hinges squeak, latch clunk"),
    dict(id="glass", icon="🪟", ko="유리 깨짐", en="Glass break", seconds=2.5, boost="",
         prompt="glass window shattering, sharp smash, shards falling and tinkling"),
    dict(id="thunder", icon="⛈️", ko="천둥", en="Thunder", seconds=7.0, boost="",
         prompt="loud thunderclap, deep rolling thunder rumble, distant storm"),
]

ENVIRONMENTS = {
    "": "",
    "dry": "dry close studio recording, no reverb",
    "indoor": "indoors in a concrete room, short reflective reverb",
    "hall": "inside a large empty hall, long reverberant echo",
    "outdoor": "outdoors in an open field, distant slapback echo",
    "cave": "inside a cave, huge cavernous reverb, long echo",
    "alley": "in a narrow city alley, bouncing echoes off walls",
}
DISTANCES = {"": "", "close": "recorded very close to the microphone, punchy and detailed",
             "far": "recorded from far away, distant, softened highs"}

NEGATIVE = ("music, speech, voice, vocals, singing, melody, humming, low quality, distorted, clipping, "
            "static hiss, background noise, muffled")

# 한국어 → 영어 사전(추가 설명 칸에 한국어로 적어도 동작하도록)
GLOSSARY = [
    ("아주", "very"), ("매우", "very"), ("큰", "big"), ("거대한", "huge"), ("작은", "small"), ("날카로운", "sharp"),
    ("묵직한", "heavy"), ("둔탁한", "dull thud"), ("가벼운", "light"), ("빠른", "fast"), ("느린", "slow"),
    ("긴 잔향", "long reverb tail"), ("짧은", "short"), ("잔향", "reverb"), ("메아리", "echo"), ("울리는", "resonant"),
    ("건조한", "dry"), ("금속", "metallic"), ("쇳소리", "metal clang"), ("나무", "wooden"), ("돌", "stone"),
    ("피", "blood"), ("살", "flesh"), ("갑옷", "armor"), ("방패", "shield"), ("검", "sword"), ("칼", "knife blade"),
    ("총", "gun"), ("권총", "pistol"), ("소총", "rifle"), ("폭발", "explosion"), ("불", "fire"), ("얼음", "ice"),
    ("번개", "lightning"), ("천둥", "thunder"), ("바람", "wind"), ("물", "water"), ("문", "door"), ("유리", "glass"),
    ("총소리", "gunshot"), ("폭발음", "explosion"), ("발소리", "footsteps"), ("타격음", "impact sound"), ("소리", "sound"),
    ("영화", "cinematic"), ("전투", "battle"), ("공포", "horror"), ("괴물", "monster"), ("마법", "magic"),
    ("저음", "deep bass"), ("고음", "high pitched"), ("파편", "debris"), ("먼", "distant"), ("가까운", "close"),
]


def recipe(recipe_id: str) -> dict | None:
    return next((r for r in RECIPES if r["id"] == recipe_id), None)


def translate(text: str) -> str:
    """사전 치환(긴 낱말부터). 이미 영어면 그대로 둔다."""
    out = text.strip()
    for ko, en in sorted(GLOSSARY, key=lambda kv: -len(kv[0])):
        if len(ko) == 1:  # 한 글자 낱말(피, 살, 문…)은 다른 단어 속에서 바뀌지 않게 '단독으로 쓰였을 때만' 치환
            out = re.sub(rf"(?<![가-힣]){ko}(?:[이가은는을를의과와에도로](?![가-힣]))?(?![가-힣])", f" {en} ", out)
        else:
            out = out.replace(ko, f" {en} ")
    return " ".join(out.split())


def build_prompt(recipe_id: str = "", env: str = "", distance: str = "", extra: str = "") -> str:
    parts: list[str] = []
    r = recipe(recipe_id)
    if r:
        parts.append(r["prompt"])
    if extra.strip():
        parts.append(translate(extra))
    for value in (ENVIRONMENTS.get(env, ""), DISTANCES.get(distance, "")):
        if value:
            parts.append(value)
    parts.append(_TAIL)
    return ", ".join(p for p in parts if p)


def public_recipes() -> dict:
    return {"recipes": [{k: r[k] for k in ("id", "icon", "ko", "en", "seconds", "boost")} for r in RECIPES],
            "environments": list(ENVIRONMENTS), "distances": list(DISTANCES), "negative": NEGATIVE}
