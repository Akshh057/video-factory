"""One command: script.json -> voice -> images -> finished video.

Usage: python factory/make_video.py videos/petrol-pump [--no-api]

--no-api skips the API steps and only renders from audio/ and images/
that already exist (useful for re-rendering).
"""

import json
import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from images import existing, make_images  # noqa: E402
from render import render  # noqa: E402
from voice import make_voice  # noqa: E402

SR = 44100
GAP = 0.25        # pause between scenes, seconds
SILENCE = 0.01    # amplitude treated as silence when trimming


def decode(mp3):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", mp3, "-f", "f32le", "-ac", "1",
                          "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def trim(a):
    loud = np.where(np.abs(a) > SILENCE)[0]
    if len(loud) == 0:
        return a, 0.0
    lead = max(loud[0] - int(0.05 * SR), 0)
    tail = min(loud[-1] + int(0.12 * SR), len(a))
    return a[lead:tail], lead / SR


def contact_sheet(paths, out):
    tw, th, cols = 384, 216, 6
    rows = math.ceil(len(paths) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20))
    for k, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail((tw, th))
        sheet.paste(im, ((k % cols) * tw + (tw - im.width) // 2, (k // cols) * th + (th - im.height) // 2))
    sheet.save(out, quality=85)


def main(folder, use_api=True):
    folder = folder.rstrip("/")
    name = os.path.basename(folder)
    cfg = json.load(open(os.path.join(folder, "script.json"), encoding="utf-8"))
    scenes = cfg["scenes"]
    audio_dir, img_dir = os.path.join(folder, "audio"), os.path.join(folder, "images")
    out_dir = os.path.join("out", name)
    os.makedirs(out_dir, exist_ok=True)

    if use_api:
        print(f"[1/3] Voice for {len(scenes)} scenes")
        make_voice(scenes, audio_dir, cfg.get("voice", {}))
        print(f"[2/3] Images for {len(scenes)} scenes")
        make_images(scenes, cfg.get("style", ""), img_dir, steps=cfg.get("image_steps", 8),
                    seed_base=name)

    print("[3/3] Building timeline and rendering")
    pieces, timeline, t = [], [], 0.0
    for i, sc in enumerate(scenes):
        n = f"{i + 1:02d}"
        img = os.path.join(folder, sc["image"]) if sc.get("image") else existing(img_dir, n)
        if not img:
            raise SystemExit(f"Missing image for scene {n}")
        audio, lead = trim(decode(os.path.join(audio_dir, n + ".mp3")))
        words = json.load(open(os.path.join(audio_dir, n + ".json"), encoding="utf-8"))["words"]
        dur = len(audio) / SR
        timeline.append({
            "image": img, "start": t, "end": t + dur, "move": sc.get("move"),
            "words": [{"w": w["w"], "s": t + w["s"] - lead, "e": t + w["e"] - lead} for w in words],
        })
        pieces += [audio, np.zeros(int(GAP * SR), np.float32)]
        t += dur + GAP
    voice = np.concatenate(pieces)
    wav = os.path.join(out_dir, "voice.wav")
    with wave.open(wav, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR)
        f.writeframes((np.clip(voice, -1, 1) * 32767).astype(np.int16).tobytes())
    tl_path = os.path.join(out_dir, "timeline.json")
    json.dump({"scenes": timeline}, open(tl_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    contact_sheet([s["image"] for s in timeline], os.path.join(out_dir, "images-preview.jpg"))

    music = next((p for p in (os.path.join(folder, "music.mp3"), "assets/music.mp3") if os.path.exists(p)), None)
    render(tl_path, wav, os.path.join(out_dir, f"{name}.mp4"), music_path=music)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0], use_api="--no-api" not in sys.argv)
