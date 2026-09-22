"""카테고리별 프리셋 효과음. 각 프리셋은 engine.normalize_spec 이 채워주므로 바꾼 값만 적는다."""
from __future__ import annotations

from typing import Any


def L(**kw: Any) -> dict:
    return kw


def note(semitones_from_a4: float) -> float:
    return 440.0 * 2 ** (semitones_from_a4 / 12)


# (id, 아이콘, 한글 이름, 영문 이름, 검색 키워드, spec)
_C5, _E5, _G5, _C6 = note(-9), note(-5), note(-2), note(3)
_G4, _Gb4, _F4, _E4 = note(-14), note(-15), note(-16), note(-17)

PRESETS: list[dict] = [
    dict(id="coin", icon="🪙", ko="동전·아이템 획득", en="Coin / Pickup",
         tags="동전 코인 아이템 획득 줍기 픽업 골드 재화 coin pickup item collect gold gem",
         spec={"layers": [
             L(wave="square", freq=988, arp_semitones=5, arp_time=0.07, attack=0.001, sustain=0.08, decay=0.28,
               duty=0.5, punch=0.3, gain=0.7),
             L(wave="triangle", freq=1976, arp_semitones=5, arp_time=0.07, attack=0.001, sustain=0.06, decay=0.22,
               gain=0.3)],
             "master": {"reverb_mix": 0.08, "reverb_size": 0.2}}),
    dict(id="jump", icon="🦘", ko="점프", en="Jump",
         tags="점프 도약 뛰기 jump hop leap bounce",
         spec={"layers": [
             L(wave="square", freq=250, slide=2.0, attack=0.002, sustain=0.05, decay=0.2, duty=0.4,
               lp_cutoff=6000, gain=0.7),
             L(wave="sine", freq=125, slide=2.0, attack=0.002, sustain=0.05, decay=0.2, gain=0.35)]}),
    dict(id="laser", icon="🔫", ko="레이저·발사", en="Laser / Shoot",
         tags="레이저 발사 총 슈팅 사격 광선 laser shoot shot gun pew blaster",
         spec={"layers": [
             L(wave="square", freq=1800, slide=-6, attack=0.001, sustain=0.03, decay=0.22, duty=0.3,
               lp_cutoff=9000, punch=0.4, gain=0.7),
             L(wave="noise", noise_color=0, attack=0.0, sustain=0.01, decay=0.05, hp_cutoff=3000, gain=0.25)]}),
    dict(id="explosion", icon="💥", ko="폭발", en="Explosion",
         tags="폭발 폭파 쾅 펑 폭탄 대포 explosion explode bomb blast boom",
         spec={"layers": [
             L(wave="noise", noise_color=1.4, attack=0.003, sustain=0.12, decay=1.0, decay_curve=2.0,
               lp_cutoff=3500, lp_sweep=-3, punch=0.8, gain=1.0),
             L(wave="sine", freq=90, slide=-1.3, attack=0.002, sustain=0.05, decay=0.55, decay_curve=1.5, gain=0.9),
             L(wave="noise", noise_color=0, attack=0.0, sustain=0.01, decay=0.25, decay_curve=2.5,
               hp_cutoff=2000, gain=0.3)],
             "master": {"reverb_mix": 0.25, "reverb_size": 0.6, "distortion": 0.15}}),
    dict(id="hit", icon="👊", ko="타격·충돌", en="Hit / Impact",
         tags="타격 충돌 때리기 펀치 공격 히트 임팩트 hit impact punch smack slap thud",
         spec={"layers": [
             L(wave="noise", noise_color=0.3, attack=0.0, sustain=0.01, decay=0.14, decay_curve=2.0,
               lp_cutoff=5000, lp_sweep=-4, punch=0.5, gain=0.9),
             L(wave="sine", freq=190, slide=-3, attack=0.0, sustain=0.02, decay=0.13, gain=0.9)],
             "master": {"distortion": 0.1}}),
    dict(id="hurt", icon="💢", ko="피격·데미지", en="Hurt / Damage",
         tags="피격 데미지 아야 맞음 다침 부상 hurt damage ouch injured pain",
         spec={"layers": [
             L(wave="saw", freq=420, slide=-2.5, attack=0.001, sustain=0.06, decay=0.3, vibrato_depth=0.6,
               vibrato_rate=28, lp_cutoff=4500, gain=0.7),
             L(wave="noise", attack=0.0, sustain=0.02, decay=0.14, lp_cutoff=3000, gain=0.35)],
             "master": {"bits": 10, "distortion": 0.08}}),
    dict(id="powerup", icon="⬆️", ko="파워업·버프", en="Power-up / Buff",
         tags="파워업 버프 강화 상승 업그레이드 파워 powerup power buff upgrade boost",
         spec={"layers": [
             L(wave="square", freq=300, slide=2.6, attack=0.005, sustain=0.22, decay=0.25, duty=0.35,
               vibrato_depth=0.3, vibrato_rate=20, lp_cutoff=7000, gain=0.6),
             L(wave="triangle", freq=600, slide=2.6, attack=0.005, sustain=0.22, decay=0.25, gain=0.35)],
             "master": {"echo_mix": 0.2, "echo_time": 0.11, "echo_feedback": 0.3}}),
    dict(id="magic", icon="✨", ko="마법·스킬", en="Magic / Spell",
         tags="마법 스킬 주문 마술 시전 반짝 spell magic skill cast sparkle charm",
         spec={"layers": [
             L(wave="sine", freq=880, slide=0.5, fm_ratio=2.01, fm_depth=3.0, tremolo_depth=0.3, tremolo_rate=14,
               attack=0.05, sustain=0.3, decay=0.7, gain=0.6),
             L(wave="sine", freq=1760, delay=0.05, attack=0.02, sustain=0.2, decay=0.6, gain=0.28),
             L(wave="noise", noise_color=1.0, hp_cutoff=4000, attack=0.2, sustain=0.1, decay=0.5, gain=0.14)],
             "master": {"reverb_mix": 0.3, "reverb_size": 0.6, "echo_mix": 0.2, "echo_time": 0.18,
                        "echo_feedback": 0.4}}),
    dict(id="swing", icon="🗡️", ko="휘두르기·휙", en="Swing / Whoosh",
         tags="휘두르기 휙 검 칼 스윙 바람 대시 회피 swing whoosh sword slash swoosh dash",
         spec={"layers": [
             L(wave="noise", noise_color=0.7, attack=0.07, sustain=0.02, decay=0.2, decay_curve=1.5,
               lp_cutoff=800, lp_sweep=6, hp_cutoff=300, gain=1.0)]}),
    dict(id="footstep", icon="👣", ko="발걸음", en="Footstep",
         tags="발걸음 발소리 걷기 걸음 달리기 footstep step walk run foot",
         spec={"layers": [
             L(wave="noise", noise_color=1.0, attack=0.0, sustain=0.01, decay=0.1, decay_curve=2.0,
               lp_cutoff=700, lp_sweep=-2, punch=0.6, gain=1.0),
             L(wave="sine", freq=90, slide=-1, attack=0.0, sustain=0.01, decay=0.08, gain=0.5)]}),
    dict(id="ui_click", icon="🖱️", ko="UI 클릭", en="UI Click",
         tags="클릭 버튼 누르기 탭 선택 click button tap press select ui",
         spec={"layers": [
             L(wave="square", freq=1800, attack=0.0005, sustain=0.005, decay=0.035, duty=0.5, gain=0.55),
             L(wave="sine", freq=900, attack=0.0005, sustain=0.005, decay=0.03, gain=0.3)]}),
    dict(id="ui_confirm", icon="✅", ko="UI 확인·성공", en="UI Confirm",
         tags="확인 승인 성공 완료 저장 ok confirm success accept done yes",
         spec={"layers": [
             L(wave="triangle", freq=660, attack=0.002, sustain=0.06, decay=0.12, gain=0.6),
             L(wave="triangle", freq=990, delay=0.08, attack=0.002, sustain=0.08, decay=0.22, gain=0.6)],
             "master": {"reverb_mix": 0.1, "reverb_size": 0.25}}),
    dict(id="ui_cancel", icon="❌", ko="UI 취소·오류", en="UI Cancel / Error",
         tags="취소 오류 에러 실패 금지 불가 cancel error fail deny wrong no invalid",
         spec={"layers": [
             L(wave="square", freq=300, attack=0.002, sustain=0.08, decay=0.1, lp_cutoff=2500, gain=0.55),
             L(wave="square", freq=220, delay=0.09, attack=0.002, sustain=0.08, decay=0.2, lp_cutoff=2500,
               gain=0.55)]}),
    dict(id="alarm", icon="🚨", ko="경고·알람", en="Alarm / Warning",
         tags="경고 알람 사이렌 위험 알림 경보 alarm warning siren alert danger",
         spec={"layers": [
             L(wave="square", freq=880, vibrato_depth=5, vibrato_rate=3.5, attack=0.01, sustain=0.9, decay=0.1,
               duty=0.4, lp_cutoff=5000, gain=0.6)]}),
    dict(id="door", icon="🚪", ko="문·기계", en="Door / Machine",
         tags="문 기계 철문 자물쇠 레버 열림 닫힘 door machine metal lock lever gate mechanism",
         spec={"layers": [
             L(wave="noise", noise_color=1.5, attack=0.002, sustain=0.03, decay=0.28, decay_curve=2.0,
               lp_cutoff=600, gain=0.9),
             L(wave="square", freq=70, slide=-0.5, attack=0.002, sustain=0.03, decay=0.2, lp_cutoff=800, gain=0.6),
             L(wave="noise", hp_cutoff=3000, delay=0.12, attack=0.0, sustain=0.005, decay=0.05, gain=0.5)],
             "master": {"reverb_mix": 0.15, "reverb_size": 0.35}}),
    dict(id="levelup", icon="🏆", ko="레벨업·승리", en="Level-up / Victory",
         tags="레벨업 승리 클리어 성공 팡파르 달성 levelup level victory win fanfare clear achievement",
         spec={"layers": [
             L(wave="square", freq=_C5, duty=0.25, attack=0.002, sustain=0.06, decay=0.1, gain=0.45),
             L(wave="square", freq=_E5, delay=0.09, duty=0.25, attack=0.002, sustain=0.06, decay=0.1, gain=0.45),
             L(wave="square", freq=_G5, delay=0.18, duty=0.25, attack=0.002, sustain=0.06, decay=0.1, gain=0.45),
             L(wave="square", freq=_C6, delay=0.27, duty=0.25, attack=0.002, sustain=0.12, decay=0.5,
               vibrato_depth=0.2, vibrato_rate=6, gain=0.5),
             L(wave="triangle", freq=_C6 / 2, delay=0.27, attack=0.002, sustain=0.12, decay=0.5, gain=0.4)],
             "master": {"echo_mix": 0.2, "echo_time": 0.14, "echo_feedback": 0.35, "reverb_mix": 0.12}}),
    dict(id="gameover", icon="💀", ko="게임오버·실패", en="Game Over / Fail",
         tags="게임오버 실패 패배 사망 죽음 gameover game over fail lose defeat death dead",
         spec={"layers": [
             L(wave="triangle", freq=_G4, attack=0.005, sustain=0.1, decay=0.12, lp_cutoff=3000, gain=0.6),
             L(wave="triangle", freq=_Gb4, delay=0.2, attack=0.005, sustain=0.1, decay=0.12, lp_cutoff=3000, gain=0.6),
             L(wave="triangle", freq=_F4, delay=0.4, attack=0.005, sustain=0.1, decay=0.12, lp_cutoff=3000, gain=0.6),
             L(wave="triangle", freq=_E4, slide=-0.35, delay=0.6, attack=0.005, sustain=0.3, decay=0.7,
               vibrato_depth=0.4, vibrato_rate=6, lp_cutoff=3000, gain=0.65)],
             "master": {"reverb_mix": 0.15, "reverb_size": 0.5}}),
    dict(id="heal", icon="💚", ko="회복·힐", en="Heal",
         tags="회복 힐 치유 치료 체력 재생 heal recover restore health regen cure",
         spec={"layers": [
             L(wave="sine", freq=660, slide=0.6, fm_ratio=2.0, fm_depth=0.4, attack=0.08, sustain=0.2, decay=0.5,
               gain=0.6),
             L(wave="sine", freq=990, slide=0.6, delay=0.1, attack=0.05, sustain=0.15, decay=0.5, gain=0.35),
             L(wave="noise", noise_color=1.0, hp_cutoff=5000, attack=0.15, sustain=0.05, decay=0.4, gain=0.1)],
             "master": {"reverb_mix": 0.3, "reverb_size": 0.55}}),
    dict(id="gacha", icon="🎰", ko="가챠·뽑기 연출", en="Gacha / Reveal",
         tags="가챠 뽑기 소환 등장 공개 보상 상자 gacha reveal summon draw gift chest loot",
         spec={"layers": [
             L(wave="noise", noise_color=0.5, attack=0.8, sustain=0.0, decay=0.05, lp_cutoff=600, lp_sweep=3.2,
               hp_cutoff=300, gain=0.55),
             L(wave="sine", freq=330, slide=0.9, attack=0.8, sustain=0.0, decay=0.05, gain=0.4),
             L(wave="sine", freq=1046.5, delay=0.85, fm_ratio=3.5, fm_depth=2.0, attack=0.002, sustain=0.05,
               decay=1.3, decay_curve=1.6, gain=0.5),
             L(wave="sine", freq=1318.5, delay=0.93, fm_ratio=3.5, fm_depth=1.6, attack=0.002, sustain=0.05,
               decay=1.2, decay_curve=1.6, gain=0.4),
             L(wave="sine", freq=1568, delay=1.01, fm_ratio=3.5, fm_depth=1.2, attack=0.002, sustain=0.05,
               decay=1.2, decay_curve=1.6, gain=0.4),
             L(wave="noise", noise_color=1.0, hp_cutoff=5000, delay=0.85, attack=0.0, sustain=0.03, decay=0.6,
               gain=0.2)],
             "master": {"reverb_mix": 0.35, "reverb_size": 0.7}}),
    dict(id="water", icon="💧", ko="물방울", en="Water Drop",
         tags="물방울 물 방울 첨벙 빗방울 water drop bloop bubble splash rain",
         spec={"layers": [
             L(wave="sine", freq=420, slide=7, attack=0.002, sustain=0.01, decay=0.13, decay_curve=1.4, gain=0.8),
             L(wave="sine", freq=840, slide=7, delay=0.005, attack=0.002, sustain=0.005, decay=0.08, gain=0.25)],
             "master": {"reverb_mix": 0.2, "reverb_size": 0.4}}),
]

from .presets_hq import HQ_PRESETS  # noqa: E402

from .presets_guns import GUN_PRESETS  # noqa: E402

_HQ_ORDER = ["hq_sword_swing", "hq_sword_clash", "hq_slash_hit", "hq_hit", "hq_hurt", "hq_pistol", "hq_revolver",
             "hq_rifle", "hq_shotgun", "hq_machinegun", "hq_sniper", "hq_silenced", "hq_casing", "hq_rack",
             "hq_explosion", "hq_explosion_small"]
_hq = {p["id"]: p for p in HQ_PRESETS + GUN_PRESETS}
PRESETS += [_hq[i] for i in _HQ_ORDER]  # 화면에 보이는 순서
PRESET_BY_ID = {p["id"]: p for p in PRESETS}


def public_list() -> list[dict]:
    """프론트에 내려줄 목록(정규화된 완성 spec 포함)."""
    from .engine import normalize_spec

    out = []
    for p in PRESETS:
        spec = normalize_spec({**p["spec"], "seed": 1})
        out.append({"id": p["id"], "style": p.get("style", "retro"), "icon": p["icon"], "ko": p["ko"], "en": p["en"], "spec": spec})
    return out
