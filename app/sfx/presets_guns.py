"""총기 프리셋: 종류마다 '귀로 구분되도록' 실제 총기의 음향적 차이를 반영해 따로 설계했다.

  권총      짧고 건조한 크랙 + 얇은 쿵, 실내 슬랩
  리볼버    더 낮고 긴 '쿵'(대구경), 실린더의 금속 울림, 넓은 폭풍
  소총      초음속 '탁' 소리(고음 스냅)가 앞서고 저음은 짧음, 야외 먼 메아리
  샷건      넓은 저역 폭음 + 두꺼운 롤링 꼬리, 뒤이은 펌프 장전(금속 2회)
  기관총    연사(반복 레이어, 발마다 새 노이즈·간격 흔들림)
  저격총    거대한 크랙 + 깊은 쿵, 계곡 같은 여러 겹 메아리, 볼트 액션 장전
  소음기    크랙 없이 먹먹한 '푹' + 슬라이드 기계음
  탄피·장전 금속 튕김 / 슬라이드 랙
"""
from __future__ import annotations

from typing import Any


def L(**kw: Any) -> dict:
    return kw


def _click(delay: float, freq: float = 2200, gain: float = 0.5) -> list[dict]:
    """금속 '철컥' 한 번: 짧은 광대역 클릭 + 금속 울림."""
    return [
        L(wave="noise", noise_color=0.0, delay=delay, attack=0.0, sustain=0.001, decay=0.03, decay_curve=2.0,
          bp_amount=1.0, bp_freq=3500, bp_q=5.0, gain=gain),
        L(wave="metal", freq=freq, spread=1.0, delay=delay, attack=0.0, sustain=0.0, decay=0.14, decay_curve=2.2,
          gain=gain * 0.35),
    ]


GUN_PRESETS: list[dict] = [
    dict(id="hq_pistol", style="hq", icon="🔫", ko="권총 발사", en="Pistol Shot",
         tags="권총 총소리 총 발사 사격 총성 핸드건 pistol gunshot gun shot handgun fire shoot 9mm",
         spec={"layers": [
             L(wave="noise", attack=0.0002, sustain=0.001, decay=0.035, decay_curve=2.5, bp_amount=0.55,
               bp_freq=3800, bp_q=0.9, gain=1.0),
             L(wave="noise", noise_color=0.3, attack=0.0003, sustain=0.003, decay=0.09, decay_curve=2.2,
               lp_cutoff=6500, lp_sweep=-6.0, gain=0.7),
             L(wave="sine", freq=170, slide=-7.0, attack=0.0, sustain=0.003, decay=0.09, decay_curve=2.2, gain=0.75),
             L(wave="noise", noise_color=0.8, delay=0.02, attack=0.002, sustain=0.0, decay=0.28, decay_curve=2.8,
               lp_cutoff=3000, lp_sweep=-3.0, gain=0.2)],
             "master": {"room_mix": 0.3, "room_time": 0.55, "room_damp": 0.55, "room_predelay": 0.006,
                        "comp": 0.5, "distortion": 0.06}}),

    dict(id="hq_revolver", style="hq", icon="🤠", ko="리볼버 발사", en="Revolver Shot",
         tags="리볼버 매그넘 대구경 총소리 총 발사 revolver magnum gunshot gun shot",
         spec={"layers": [
             L(wave="noise", attack=0.0002, sustain=0.002, decay=0.05, decay_curve=2.3, bp_amount=0.6, bp_freq=1800,
               bp_q=0.7, gain=0.55),
             L(wave="noise", noise_color=0.6, attack=0.0004, sustain=0.008, decay=0.18, decay_curve=2.0,
               lp_cutoff=2800, lp_sweep=-4.5, gain=0.95),
             L(wave="sine", freq=95, slide=-4.0, attack=0.0, sustain=0.01, decay=0.22, decay_curve=1.8, gain=0.8),
             L(wave="noise", noise_color=1.3, attack=0.001, sustain=0.005, decay=0.3, decay_curve=2.0,
               lp_cutoff=500, gain=0.5),
             L(wave="metal", freq=2100, spread=0.95, attack=0.0, sustain=0.0, decay=0.12, decay_curve=2.0, gain=0.12),
             L(wave="noise", noise_color=1.0, delay=0.03, attack=0.003, sustain=0.0, decay=0.7, decay_curve=2.6,
               lp_cutoff=2400, lp_sweep=-2.2, gain=0.28)],
             "master": {"room_mix": 0.38, "room_time": 0.9, "room_damp": 0.5, "room_predelay": 0.01,
                        "comp": 0.55, "distortion": 0.1}}),

    dict(id="hq_rifle", style="hq", icon="🎯", ko="소총 발사", en="Rifle Shot",
         tags="소총 라이플 돌격소총 총소리 총 발사 사격 rifle assault gunshot shot fire ar15",
         spec={"layers": [
             L(wave="noise", attack=0.0001, sustain=0.0005, decay=0.03, decay_curve=3.0, bp_amount=0.7,
               bp_freq=6500, bp_q=0.8, gain=1.0),
             L(wave="noise", attack=0.0, sustain=0.0005, decay=0.014, decay_curve=2.0, hp_cutoff=5000, gain=1.1),
             L(wave="noise", noise_color=0.4, attack=0.0003, sustain=0.004, decay=0.12, decay_curve=2.0,
               lp_cutoff=5500, lp_sweep=-5.0, gain=0.45),
             L(wave="sine", freq=130, slide=-6.0, attack=0.0, sustain=0.003, decay=0.1, decay_curve=2.0, gain=0.45),
             L(wave="noise", noise_color=1.0, delay=0.05, attack=0.003, sustain=0.0, decay=1.3, decay_curve=2.6,
               lp_cutoff=2200, lp_sweep=-2.0, gain=0.3)],
             "master": {"echo_mix": 0.25, "echo_time": 0.22, "echo_feedback": 0.45, "room_mix": 0.3, "room_time": 1.5,
                        "room_damp": 0.6, "room_predelay": 0.02, "comp": 0.55, "distortion": 0.1}}),

    dict(id="hq_shotgun", style="hq", icon="💢", ko="샷건 발사 + 장전", en="Shotgun Blast + Pump",
         tags="샷건 산탄총 산탄 총소리 총 발사 펌프 shotgun blast scattergun boomstick pump fire",
         spec={"layers": [
             L(wave="noise", noise_color=0.5, attack=0.0004, sustain=0.02, decay=0.3, decay_curve=1.9,
               lp_cutoff=2000, lp_sweep=-3.5, gain=0.3),
             L(wave="noise", attack=0.0002, sustain=0.002, decay=0.08, decay_curve=2.0, bp_amount=0.5, bp_freq=1600,
               bp_q=0.6, gain=0.3),
             L(wave="sine", freq=58, slide=-3.0, attack=0.0, sustain=0.02, decay=0.36, decay_curve=1.7, gain=1.5),
             L(wave="noise", noise_color=1.4, attack=0.002, sustain=0.03, decay=0.5, decay_curve=1.8,
               lp_cutoff=320, gain=1.4),
             L(wave="noise", noise_color=1.2, delay=0.05, attack=0.004, sustain=0.0, decay=0.9, decay_curve=2.5,
               lp_cutoff=1800, lp_sweep=-2.0, gain=0.2),
             *_click(0.62, 1900, 0.45), *_click(0.82, 1500, 0.55)],
             "master": {"room_mix": 0.4, "room_time": 1.3, "room_damp": 0.55, "room_predelay": 0.015,
                        "comp": 0.6, "distortion": 0.12}}),

    dict(id="hq_machinegun", style="hq", icon="🔥", ko="기관총 연사", en="Machine Gun Burst",
         tags="기관총 연사 기관단총 자동 총소리 총 발사 machine gun burst smg automatic rapid fire full auto",
         spec={"layers": [
             L(wave="noise", attack=0.0002, sustain=0.0005, decay=0.03, decay_curve=2.5, bp_amount=0.6, bp_freq=4200,
               bp_q=0.9, gain=1.0, repeat=9, repeat_gap=0.075, repeat_gain=0.97, repeat_jitter=0.12),
             L(wave="noise", noise_color=0.4, attack=0.0003, sustain=0.002, decay=0.065, decay_curve=2.2,
               lp_cutoff=5500, lp_sweep=-6.0, gain=0.7, repeat=9, repeat_gap=0.075, repeat_gain=0.97,
               repeat_jitter=0.12),
             L(wave="sine", freq=200, slide=-8.0, attack=0.0, sustain=0.002, decay=0.05, decay_curve=2.0, gain=0.6,
               repeat=9, repeat_gap=0.075, repeat_gain=0.97, repeat_jitter=0.12),
             L(wave="noise", noise_color=0.9, delay=0.4, attack=0.004, sustain=0.0, decay=0.7, decay_curve=2.5,
               lp_cutoff=2600, lp_sweep=-2.5, gain=0.3)],
             "master": {"room_mix": 0.3, "room_time": 0.7, "room_damp": 0.55, "room_predelay": 0.008,
                        "comp": 0.65, "distortion": 0.1}}),

    dict(id="hq_sniper", style="hq", icon="🔭", ko="저격총 발사 + 볼트", en="Sniper Shot + Bolt",
         tags="저격총 저격 스나이퍼 총소리 총 발사 볼트 sniper long range rifle gunshot bolt action distant echo",
         spec={"layers": [
             L(wave="noise", attack=0.0001, sustain=0.001, decay=0.05, decay_curve=2.5, bp_amount=0.65,
               bp_freq=5500, bp_q=0.7, gain=1.0),
             L(wave="noise", noise_color=0.5, attack=0.0004, sustain=0.006, decay=0.2, decay_curve=2.0,
               lp_cutoff=3500, lp_sweep=-4.0, gain=0.9),
             L(wave="sine", freq=80, slide=-3.0, attack=0.0, sustain=0.01, decay=0.35, decay_curve=1.8, gain=1.0),
             L(wave="noise", noise_color=1.0, delay=0.06, attack=0.005, sustain=0.0, decay=2.2, decay_curve=2.4,
               lp_cutoff=1800, lp_sweep=-1.5, gain=0.3),
             *_click(1.3, 1500, 0.45), *_click(1.55, 1200, 0.5)],
             "master": {"echo_mix": 0.35, "echo_time": 0.42, "echo_feedback": 0.5, "room_mix": 0.45,
                        "room_time": 2.4, "room_damp": 0.6, "room_predelay": 0.03, "comp": 0.5, "distortion": 0.08}}),

    dict(id="hq_silenced", style="hq", icon="🤫", ko="소음기 권총", en="Silenced Pistol",
         tags="소음기 사일렌서 권총 총소리 총 발사 조용한 silenced suppressed pistol shot quiet subsonic",
         spec={"layers": [
             L(wave="noise", noise_color=0.7, attack=0.001, sustain=0.002, decay=0.07, decay_curve=2.0,
               bp_amount=1.0, bp_freq=1400, bp_q=1.2, gain=0.8),
             L(wave="sine", freq=140, slide=-3.0, attack=0.0, sustain=0.002, decay=0.06, decay_curve=2.0, gain=0.5),
             L(wave="noise", delay=0.045, attack=0.0, sustain=0.0005, decay=0.012, hp_cutoff=3000, gain=0.5),
             L(wave="metal", freq=2800, spread=1.0, delay=0.045, attack=0.0, sustain=0.0, decay=0.07,
               decay_curve=2.0, gain=0.15)],
             "master": {"room_mix": 0.12, "room_time": 0.35, "room_damp": 0.6, "comp": 0.3}}),

    dict(id="hq_casing", style="hq", icon="🪙", ko="탄피 튕김", en="Shell Casing Drop",
         tags="탄피 튕김 바닥 금속 떨어지는 casing shell drop brass bounce ping",
         spec={"layers": [
             L(wave="metal", freq=4200, spread=0.9, attack=0.0, sustain=0.0, decay=0.35, decay_curve=2.2, gain=0.5,
               repeat=4, repeat_gap=0.075, repeat_gain=0.6, repeat_jitter=0.25),
             L(wave="noise", attack=0.0, sustain=0.0005, decay=0.008, hp_cutoff=4000, gain=0.4, repeat=4,
               repeat_gap=0.075, repeat_gain=0.6, repeat_jitter=0.25)],
             "master": {"room_mix": 0.2, "room_time": 0.4, "room_damp": 0.4, "comp": 0.2}}),

    dict(id="hq_rack", style="hq", icon="🔧", ko="장전·슬라이드", en="Reload / Slide Rack",
         tags="장전 슬라이드 철컥 재장전 노리쇠 총 reload rack slide cock chamber click mechanical",
         spec={"layers": [
             *_click(0.0, 2400, 0.55),
             L(wave="sine", freq=300, slide=-2.0, attack=0.0, sustain=0.001, decay=0.04, gain=0.35),
             *_click(0.17, 1800, 0.8),
             L(wave="sine", freq=220, slide=-2.0, delay=0.17, attack=0.0, sustain=0.002, decay=0.06, gain=0.5)],
             "master": {"room_mix": 0.15, "room_time": 0.4, "room_damp": 0.5, "comp": 0.35}}),
]
