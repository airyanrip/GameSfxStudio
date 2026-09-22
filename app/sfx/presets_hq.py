"""고퀄리티(실사풍) 프리셋. 여러 겹의 '순간 크랙 + 몸통(저음) + 꼬리(공간)'으로 쌓고
룸 리버브(합성 임펄스 응답)와 컴프레서로 마무리한다. 턴제 RPG의 전투 연출용.
"""
from __future__ import annotations

from typing import Any


def L(**kw: Any) -> dict:
    return kw


HQ_PRESETS: list[dict] = [
    dict(id="hq_sword_swing", style="hq", icon="⚔️", ko="검 휘두르기", en="Sword Swing",
         tags="검 칼 휘두르기 휘두름 스윙 검격 공격 대검 sword swing whoosh swipe",
         spec={"layers": [
             L(wave="noise", noise_color=0.6, attack=0.09, sustain=0.02, decay=0.24, decay_curve=1.6,
               bp_amount=1.0, bp_freq=900, bp_q=2.2, bp_sweep=1.7, hp_cutoff=200, gain=1.0),
             L(wave="noise", noise_color=0.0, attack=0.1, sustain=0.01, decay=0.2, decay_curve=1.8,
               hp_cutoff=3500, lp_cutoff=9000, gain=0.22),
             L(wave="noise", noise_color=1.5, attack=0.1, sustain=0.02, decay=0.22, decay_curve=1.5,
               lp_cutoff=420, gain=0.35)],
             "master": {"room_mix": 0.12, "room_time": 0.4, "room_damp": 0.6, "comp": 0.2}}),

    dict(id="hq_sword_clash", style="hq", icon="🤺", ko="검 부딪힘(쇳소리)", en="Sword Clash",
         tags="검 부딪힘 쇳소리 금속 방패 막기 패링 칼날 클래시 sword clash clang metal parry block ring shield",
         spec={"layers": [
             L(wave="noise", noise_color=0.0, attack=0.0003, sustain=0.001, decay=0.035, decay_curve=2.0,
               hp_cutoff=2500, gain=1.0),
             L(wave="metal", freq=1450, spread=0.85, attack=0.0005, sustain=0.0, decay=0.95, decay_curve=2.0, gain=0.55),
             L(wave="metal", freq=2330, spread=0.95, attack=0.0005, sustain=0.0, decay=0.6, decay_curve=2.0, gain=0.3),
             L(wave="sine", freq=220, slide=-1.0, attack=0.0, sustain=0.005, decay=0.07, gain=0.5),
             L(wave="noise", noise_color=0.5, attack=0.001, sustain=0.005, decay=0.12, bp_amount=1.0, bp_freq=5000,
               bp_q=3.0, gain=0.35)],
             "master": {"room_mix": 0.18, "room_time": 0.7, "room_damp": 0.3, "comp": 0.3}}),

    dict(id="hq_slash_hit", style="hq", icon="🩸", ko="검 베기 피격", en="Blade Hit",
         tags="베기 베임 참격 칼 검 살 베는 slash cut stab blade flesh sword",
         spec={"layers": [
             L(wave="noise", noise_color=0.8, attack=0.001, sustain=0.005, decay=0.13, decay_curve=2.0,
               bp_amount=1.0, bp_freq=1800, bp_q=1.2, bp_sweep=-2.0, gain=1.0),
             L(wave="sine", freq=140, slide=-2.5, attack=0.0, sustain=0.01, decay=0.11, decay_curve=1.6, gain=0.8),
             L(wave="noise", noise_color=1.4, attack=0.001, sustain=0.01, decay=0.2, decay_curve=2.0,
               lp_cutoff=900, gain=0.5),
             L(wave="metal", freq=3000, spread=1.0, attack=0.0005, sustain=0.0, decay=0.25, decay_curve=2.0,
               gain=0.12)],
             "master": {"room_mix": 0.14, "room_time": 0.45, "room_damp": 0.5, "comp": 0.35}}),

    dict(id="hq_hit", style="hq", icon="🥊", ko="묵직한 타격", en="Heavy Impact",
         tags="타격 타격음 주먹 펀치 충격 임팩트 몸통 둔기 강타 묵직한 무거운 hit impact punch thud blunt smack heavy",
         spec={"layers": [
             L(wave="noise", noise_color=0.0, attack=0.0, sustain=0.001, decay=0.018, decay_curve=2.0,
               hp_cutoff=1500, gain=0.8),
             L(wave="sine", freq=110, slide=-3.5, attack=0.0, sustain=0.01, decay=0.17, decay_curve=1.7, gain=1.0),
             L(wave="noise", noise_color=1.2, attack=0.001, sustain=0.005, decay=0.17, decay_curve=2.0,
               lp_cutoff=1200, lp_sweep=-4.0, gain=0.7)],
             "master": {"room_mix": 0.12, "room_time": 0.35, "room_damp": 0.6, "comp": 0.4, "distortion": 0.05}}),

    dict(id="hq_hurt", style="hq", icon="🛡️", ko="피격(갑옷·몸)", en="Take Damage",
         tags="피격 피해 데미지 맞음 갑옷 다침 부상 hurt damage armor taking hit injured ouch",
         spec={"layers": [
             L(wave="noise", attack=0.0, sustain=0.001, decay=0.02, hp_cutoff=1200, gain=0.7),
             L(wave="sine", freq=95, slide=-3.0, attack=0.0, sustain=0.015, decay=0.22, decay_curve=1.7, gain=1.0),
             L(wave="noise", noise_color=1.0, attack=0.002, sustain=0.02, decay=0.24, decay_curve=2.0,
               lp_cutoff=1000, lp_sweep=-3.0, gain=0.7),
             L(wave="noise", noise_color=0.3, delay=0.02, attack=0.001, sustain=0.01, decay=0.14, decay_curve=1.6,
               bp_amount=1.0, bp_freq=3500, bp_q=4.0, gain=0.3),
             L(wave="metal", freq=1800, spread=1.0, delay=0.02, attack=0.0005, sustain=0.0, decay=0.3,
               decay_curve=2.0, gain=0.1)],
             "master": {"room_mix": 0.15, "room_time": 0.5, "room_damp": 0.55, "comp": 0.4, "distortion": 0.06}}),

    dict(id="hq_explosion", style="hq", icon="🌋", ko="대형 폭발", en="Big Explosion",
         tags="폭발 폭파 쾅 대폭발 폭탄 대포 화염 explosion explode bomb blast boom detonation fireball",
         spec={"layers": [
             L(wave="noise", noise_color=0.0, attack=0.0005, sustain=0.01, decay=0.13, decay_curve=2.0,
               hp_cutoff=1500, gain=0.7),
             L(wave="sine", freq=55, slide=-0.8, attack=0.004, sustain=0.05, decay=1.2, decay_curve=1.8, punch=0.5,
               gain=1.0),
             L(wave="noise", noise_color=1.0, attack=0.003, sustain=0.1, decay=1.4, decay_curve=2.0,
               lp_cutoff=4000, lp_sweep=-3.5, gain=1.0),
             L(wave="noise", noise_color=2.0, delay=0.02, attack=0.05, sustain=0.3, decay=1.6, decay_curve=1.5,
               lp_cutoff=250, lp_sweep=-0.5, gain=0.9),
             L(wave="chip_noise", freq=900, delay=0.35, attack=0.02, sustain=0.1, decay=1.0, decay_curve=2.0,
               hp_cutoff=1500, tremolo_depth=0.8, tremolo_rate=27, gain=0.22)],
             "master": {"room_mix": 0.4, "room_time": 2.2, "room_damp": 0.55, "room_predelay": 0.02,
                        "comp": 0.4, "distortion": 0.1}}),

    dict(id="hq_explosion_small", style="hq", icon="💣", ko="소형 폭발", en="Small Explosion",
         tags="소형 폭발 수류탄 펑 폭죽 작은 폭발 grenade pop small explosion firecracker blast burst",
         spec={"layers": [
             L(wave="noise", noise_color=0.0, attack=0.0003, sustain=0.005, decay=0.07, decay_curve=2.0,
               hp_cutoff=1800, gain=0.8),
             L(wave="sine", freq=90, slide=-1.5, attack=0.002, sustain=0.02, decay=0.4, decay_curve=1.8, gain=1.0),
             L(wave="noise", noise_color=0.9, attack=0.002, sustain=0.03, decay=0.5, decay_curve=2.0,
               lp_cutoff=4500, lp_sweep=-4.0, gain=1.0),
             L(wave="noise", noise_color=1.8, delay=0.01, attack=0.02, sustain=0.05, decay=0.55, decay_curve=1.6,
               lp_cutoff=300, gain=0.6)],
             "master": {"room_mix": 0.3, "room_time": 1.1, "room_damp": 0.5, "comp": 0.45, "distortion": 0.08}}),
]
