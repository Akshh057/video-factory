"""Shake-free renderer.

Takes a timeline (scenes with image, start, end, words) plus a voice track
and writes the final MP4.

Why no shake: the old version used ffmpeg's zoompan, which rounds the crop
position to whole pixels, so the picture jumps by one pixel now and then.
Here every frame is drawn in Python with a floating point transform
(cv2.warpAffine), so the image moves by fractions of a pixel and the motion
stays smooth.
"""

import json
import math
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageFilter

W, H = 1920, 1080
FPS = 30
CANVAS = 1.15          # canvas is 15% bigger than the frame, room to move
ZOOM = 1.12            # how far a zoom goes (1.12 = 12% closer)
XFADE = 0.5            # crossfade length between scenes, seconds
TAIL = 1.2             # extra seconds on the last scene before fade out

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(os.path.dirname(HERE), "assets", "fonts")


# ---------- image prep ----------

def build_canvas(path):
    """Make one big still (CANVAS x frame size) from any image shape.

    16:9-ish images are cropped to fill. Square or tall images keep their
    whole picture in the middle with a blurred copy filling the sides.
    """
    cw, ch = round(W * CANVAS), round(H * CANVAS)
    img = Image.open(path).convert("RGB")
    iw, ih = img.size
    ratio = iw / ih
    target = cw / ch
    if abs(ratio - target) / target < 0.12:
        scale = max(cw / iw, ch / ih)
        img = img.resize((math.ceil(iw * scale), math.ceil(ih * scale)), Image.LANCZOS)
        x, y = (img.width - cw) // 2, (img.height - ch) // 2
        return np.asarray(img.crop((x, y, x + cw, y + ch)))
    # keep up to a 4:3 slice of the picture, blur-fill the rest
    keep = min(ratio, 4 / 3)
    if ratio > keep:
        nw = ih * keep
        x = (iw - nw) / 2
        img_main = img.crop((round(x), 0, round(x + nw), ih))
    else:
        nh = iw / keep
        y = (ih - nh) / 2
        img_main = img.crop((0, round(y), iw, round(y + nh)))
    bg_scale = max(cw / iw, ch / ih)
    bg = img.resize((math.ceil(iw * bg_scale), math.ceil(ih * bg_scale)), Image.LANCZOS)
    bx, by = (bg.width - cw) // 2, (bg.height - ch) // 2
    bg = bg.crop((bx, by, bx + cw, by + ch)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", bg.size, (0, 0, 0)), 0.35)
    ms = ch / img_main.height
    img_main = img_main.resize((round(img_main.width * ms), ch), Image.LANCZOS)
    bg.paste(img_main, ((cw - img_main.width) // 2, 0))
    return np.asarray(bg)


# ---------- motion ----------

def ease(t):
    t = min(max(t, 0.0), 1.0)
    # half linear, half sine ease: keeps moving, no hard start or stop
    return 0.5 * t + 0.5 * (0.5 - 0.5 * math.cos(math.pi * t))


MOVES = ["zoom_in", "pan_right", "zoom_out", "pan_left", "zoom_in_up", "pan_down"]


def transform(move, t, cw, ch):
    """Return (scale, cx, cy): canvas point (cx, cy) sits at frame centre."""
    smin = max(W / cw, H / ch)          # whole canvas visible
    e = ease(t)
    if move == "zoom_in":
        s = smin * (1 + (ZOOM - 1) * e); fx, fy = 0.5, 0.5
    elif move == "zoom_out":
        s = smin * (ZOOM - (ZOOM - 1) * e); fx, fy = 0.5, 0.5
    elif move == "zoom_in_up":
        s = smin * (1 + (ZOOM - 1) * e); fx, fy = 0.5, 0.5 - 0.35 * e
    elif move == "pan_right":
        s = smin * ZOOM; fx, fy = 0.1 + 0.8 * e, 0.5
    elif move == "pan_left":
        s = smin * ZOOM; fx, fy = 0.9 - 0.8 * e, 0.5
    else:  # pan_down
        s = smin * ZOOM; fx, fy = 0.5, 0.15 + 0.7 * e
    # how far the centre may move without showing an edge
    mx = cw / 2 - (W / 2) / s
    my = ch / 2 - (H / 2) / s
    cx = cw / 2 + (fx - 0.5) * 2 * mx
    cy = ch / 2 + (fy - 0.5) * 2 * my
    return s, cx, cy


def draw(canvas, move, t):
    ch, cw = canvas.shape[:2]
    s, cx, cy = transform(move, t, cw, ch)
    m = np.float32([[s, 0, W / 2 - s * cx], [0, s, H / 2 - s * cy]])
    return cv2.warpAffine(canvas, m, (W, H), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REFLECT)


# ---------- captions ----------

def ass_time(t):
    t = max(t, 0)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def chunk_words(words, max_words=4, max_chars=28):
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        text = " ".join(x["w"] for x in cur)
        end_punct = w["w"][-1:] in "।.,?!:"
        if len(cur) >= max_words or len(text) >= max_chars or end_punct:
            chunks.append(cur); cur = []
    if cur:
        chunks.append(cur)
    return chunks


def write_ass(scenes, path, font="Hind", size=84):
    gold = "&H0042C5F5&"   # #F5C542 in ASS (BGR) order
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,80,80,90,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for sc in scenes:
        for chunk in chunk_words(sc.get("words", [])):
            end_chunk = chunk[-1]["e"] + 0.15
            for i, w in enumerate(chunk):
                start = w["s"]
                end = chunk[i + 1]["s"] if i + 1 < len(chunk) else end_chunk
                parts = []
                for j, x in enumerate(chunk):
                    word = x["w"].replace("{", "").replace("}", "")
                    parts.append(f"{{\\c{gold}}}{word}{{\\c&H00FFFFFF&}}" if j == i else word)
                lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,,0,0,0,,{' '.join(parts)}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")


def gradient_png(path):
    """Dark band at the bottom so captions stay readable."""
    a = np.zeros((H, W, 4), np.uint8)
    band = 380
    ramp = np.linspace(0, 1, band) ** 1.6
    a[H - band:, :, 3] = (ramp * 170).astype(np.uint8)[:, None]
    Image.fromarray(a, "RGBA").save(path)


# ---------- main render ----------

def render(timeline_path, audio_path, out_path, music_path=None, preset="medium", crf=20):
    tl = json.load(open(timeline_path, encoding="utf-8"))
    scenes = tl["scenes"]
    total = scenes[-1]["end"] + TAIL
    nframes = int(math.ceil(total * FPS))
    work = os.path.dirname(os.path.abspath(out_path))
    ass = os.path.join(work, "captions.ass")
    grad = os.path.join(work, "gradient.png")
    write_ass(scenes, ass)
    gradient_png(grad)

    # each scene shows a little before and after its voice, for the crossfade
    spans = []
    for i, sc in enumerate(scenes):
        a = 0.0 if i == 0 else sc["start"] - XFADE / 2
        b = total if i == len(scenes) - 1 else scenes[i + 1]["start"] + XFADE / 2
        spans.append((a, b))

    vf = [
        f"[0:v][2:v]overlay=0:0[v1]",
        # complex shaping is needed so Hindi letters (like ि) join correctly
        f"[v1]ass=filename='{ass}':fontsdir='{FONTS}':shaping=complex[v2]",
        f"[v2]fade=t=in:st=0:d=0.6,fade=t=out:st={total - 1.0:.2f}:d=1.0,format=yuv420p[v]",
    ]
    if music_path:
        af = (f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[voice][key];"
              f"[3:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.12,"
              f"afade=t=in:d=2,afade=t=out:st={total - 2.5:.2f}:d=2.5[mus];"
              f"[mus][key]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[duck];"
              f"[voice][duck]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        af = f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a]"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", audio_path,
           "-loop", "1", "-i", grad]
    if music_path:
        cmd += ["-stream_loop", "-1", "-i", music_path]
    cmd += ["-filter_complex", ";".join(vf) + ";" + af,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-tune", "animation",
            "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}",
            "-movflags", "+faststart", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    cache = {}
    def canvas(i):
        if i not in cache:
            if len(cache) > 3:
                cache.pop(min(cache))
            cache[i] = build_canvas(scenes[i]["image"])
        return cache[i]

    for f in range(nframes):
        t = f / FPS
        active = [i for i, (a, b) in enumerate(spans) if a <= t < b] or [len(scenes) - 1]
        frames = []
        for i in active[:2]:
            a, b = spans[i]
            move = scenes[i].get("move") or MOVES[i % len(MOVES)]
            frames.append((i, draw(canvas(i), move, (t - a) / (b - a))))
        if len(frames) == 2:
            nxt = frames[1][0]
            alpha = (t - (scenes[nxt]["start"] - XFADE / 2)) / XFADE
            alpha = min(max(alpha, 0.0), 1.0)
            frame = cv2.addWeighted(frames[0][1], 1 - alpha, frames[1][1], alpha, 0)
        else:
            frame = frames[0][1]
        proc.stdin.write(np.ascontiguousarray(frame).tobytes())
        if f % (FPS * 30) == 0:
            print(f"  frame {f}/{nframes} ({100 * f // nframes}%)", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg failed")
    print(f"Video ready: {out_path} ({total:.1f}s)")


if __name__ == "__main__":
    render(*sys.argv[1:4], music_path=sys.argv[4] if len(sys.argv) > 4 else None)
