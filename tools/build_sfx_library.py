"""고음질 실음원 SFX 라이브러리를 패키지에 내장하기 위한 정리 스크립트.

- 원본: 세션에서 이미 확보한 Freesound CC0 프리뷰(사용자 work_senior_father12/sfx, sfx_extra)
- 처리: 48kHz 모노, -18 LUFS 정규화, 용도별 길이로 트림, 앞뒤 페이드
- 결과: sfx_library/*.mp3  +  sfx_library/credits.json
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

BASE = Path("/workspace")
SRC = BASE / "work_senior_father12" / "sfx"
EXTRA = BASE / "work_senior_father12" / "sfx_extra"
OUT = BASE / "work_mac_studio" / "sfx_library"
FF = "/usr/local/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v9.0.2"

# (한글 태그, 출력파일, 원본, 트림초, 루프여부, 설명, freesound id)
ITEMS = [
    ("문 쾅", "door_slam.mp3", EXTRA / "door_slam_462665.mp3", 4.2, False,
     "Angry Door - Wooden Entrance Open Close Slam Hard A", "462665"),
    ("문 닫기", "door_close.mp3", EXTRA / "door_close_872998.mp3", 2.0, False,
     "Door_Close_01", "872998"),
    ("문 삐걱", "door_creak.mp3", SRC / "door_creak_764798.mp3", 8.0, False,
     "Creaking Old Door [Open & Close]", "764798"),
    ("발자국", "footsteps.mp3", SRC / "steps_walk2.mp3", 12.0, False,
     "Footsteps on wooden floor", "-"),
    ("비", "rain_night.mp3", SRC / "night_rain_547892.mp3", 40.0, True,
     "steady night rain", "547892"),
    ("시계", "clock_tick.mp3", SRC / "clock_830193.mp3", 30.0, True,
     "Wall Clock Ticking", "830193"),
    ("찻잔", "cup_clink.mp3", SRC / "cup_clink.mp3", 1.6, False,
     "Ceramic cup clink", "-"),
    ("숟가락", "spoon_clink.mp3", SRC / "cup_clink2.mp3", 1.2, False,
     "Small ceramic/metal clink", "-"),
    ("종이 넘김", "page_flip.mp3", SRC / "page_flip_166193.mp3", 3.0, False,
     "Pages Flipping.wav", "166193"),
    ("종이 바스락", "paper_pages.mp3", SRC / "pages_481077.mp3", 12.0, True,
     "Book - Handling and flipping through pages", "481077"),
    ("천 바스락", "cloth_rustle.mp3", SRC / "cloth_rustle_481075.mp3", 10.0, False,
     "Foley - Cotton clothes rustling", "481075"),
    ("가쁜 숨", "breath_pant.mp3", SRC / "pant_321669.mp3", 8.0, False,
     "Heavy Breathing Man/Boy", "321669"),
    ("헉", "breath_gasp.mp3", SRC / "surprise_breath_729308.mp3", 6.0, False,
     "Surprise breath", "729308"),
    ("숨죽임", "breath_huff.mp3", SRC / "huff_542078.mp3", 6.0, False,
     "huff and puff", "542078"),
    ("한숨", "sigh.mp3", SRC / "sigh_318090.mp3", 5.0, False,
     "Sigh_5_Male_Deep", "318090"),
    ("심장박동", "heartbeat.mp3", SRC / "heartbeat_249716.mp3", 12.0, True,
     "SLOW HEARTBEAT", "249716"),
    ("병원 룸톤", "hospital_room.mp3", SRC / "hospital_room_670070.mp3", 30.0, True,
     "Room Tone, Empty Hospital", "670070"),
    ("냄비 보글", "pot_simmer.mp3", SRC / "simmer_730089.mp3", 25.0, True,
     "Simmer", "730089"),
    ("핸드폰 진동", "phone_vibrate.mp3", EXTRA / "phone_vibrate_wood_708216.mp3", 6.0, False,
     "Smart Phone Vibration - Short - Wood Surface", "708216"),
    ("바람", "wind_howl.mp3", SRC / "wind_howl_546871.mp3", 20.0, True,
     "ATM INT Wind Howl Cold Winter", "546871"),
    ("바람 창", "wind_window.mp3", SRC / "wind_window_577339.mp3", 20.0, True,
     "Wind through window", "577339"),
    ("침대 시트", "bed_rustle.mp3", SRC / "bed_rustle_856380.mp3", 10.0, False,
     "Bed sheets and blanket rustling", "856380"),
    ("장판", "floor_squeak.mp3", SRC / "floor_squeak_196126.mp3", 8.0, False,
     "linoleum floor squeaks", "196126"),
    ("테이프", "tape_peel.mp3", SRC / "tape_peel_642316.mp3", 6.0, False,
     "Cellotape Peeling Perc 01", "642316"),
    ("가방", "bag_rustle.mp3", SRC / "bag_rustle.mp3", 6.0, False,
     "plastic bag rustle", "-"),
    ("상자", "cardboard.mp3", SRC / "cardboard_864763.mp3", 8.0, False,
     "Dragging Cardboard Box", "864763"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    credits = []
    for tag, name, src, trim, loop, title, sid in ITEMS:
        if not src.exists():
            print("MISSING", src)
            continue
        dst = OUT / name
        fade = 1.0 if loop else 0.03
        af = (f"loudnorm=I=-18:TP=-2:LRA=11,atrim=0:{trim},asetpts=PTS-STARTPTS,"
              f"afade=t=in:st=0:d={fade},afade=t=out:st={max(0, trim - fade):.2f}:d={fade}")
        r = subprocess.run([FF, "-y", "-v", "error", "-i", str(src), "-af", af,
                            "-ar", "48000", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "96k", str(dst)],
                           capture_output=True, text=True)
        if not dst.exists():
            print("FAIL", name, r.stderr[-200:])
            continue
        credits.append({"tag": tag, "file": name, "title": title,
                        "freesound_id": sid, "license": "Creative Commons 0 (CC0)",
                        "loop": loop, "seconds": trim})
        print(f"{name:22s} {dst.stat().st_size/1024:7.1f} KB")
    (OUT / "credits.json").write_text(json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
