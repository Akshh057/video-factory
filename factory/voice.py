"""Voiceover from the ElevenLabs API, one request per scene.

One request per scene gives exact scene timing. previous_text / next_text
keep the voice flowing naturally between scenes. The API also returns the
time of every character, which we turn into word timings for captions.
"""

import base64
import json
import os
import time

import requests

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"


def words_from_alignment(al):
    """Group character timings into words."""
    words, cur, s, e = [], "", None, None
    for ch, cs, ce in zip(al["characters"], al["character_start_times_seconds"],
                          al["character_end_times_seconds"]):
        if ch.isspace():
            if cur:
                words.append({"w": cur, "s": s, "e": e})
            cur, s = "", None
            continue
        if s is None:
            s = cs
        cur += ch
        e = ce
    if cur:
        words.append({"w": cur, "s": s, "e": e})
    return words


def make_voice(scenes, out_dir, voice_cfg):
    """Writes out_dir/NN.mp3 and NN.json (word timings). Skips scenes already done."""
    os.makedirs(out_dir, exist_ok=True)
    key = os.environ["ELEVENLABS_API_KEY"]
    voice_id = voice_cfg.get("voice_id") or os.environ["ELEVENLABS_VOICE_ID"]
    body_base = {"model_id": voice_cfg.get("model_id", "eleven_multilingual_v2")}
    if voice_cfg.get("voice_settings"):
        body_base["voice_settings"] = voice_cfg["voice_settings"]
    if voice_cfg.get("seed") is not None:
        body_base["seed"] = voice_cfg["seed"]
    used = 0
    for i, sc in enumerate(scenes):
        n = f"{i + 1:02d}"
        mp3, js = os.path.join(out_dir, n + ".mp3"), os.path.join(out_dir, n + ".json")
        if os.path.exists(mp3) and os.path.exists(js):
            continue
        body = dict(body_base, text=sc["text"])
        if i > 0:
            body["previous_text"] = scenes[i - 1]["text"]
        if i + 1 < len(scenes):
            body["next_text"] = scenes[i + 1]["text"]
        for attempt in range(4):
            r = requests.post(API.format(voice=voice_id), json=body, timeout=120,
                              headers={"xi-api-key": key, "Content-Type": "application/json"})
            if r.status_code == 200:
                break
            print(f"  voice scene {n}: HTTP {r.status_code} {r.text[:200]}")
            if r.status_code in (401, 402, 403, 422):
                raise SystemExit("ElevenLabs refused the request (check key, voice ID, model or credits).")
            time.sleep(5 * (attempt + 1))
        else:
            raise SystemExit(f"ElevenLabs failed on scene {n}")
        data = r.json()
        with open(mp3, "wb") as f:
            f.write(base64.b64decode(data["audio_base64"]))
        words = words_from_alignment(data["alignment"]) if data.get("alignment") else []
        with open(js, "w", encoding="utf-8") as f:
            json.dump({"text": sc["text"], "words": words}, f, ensure_ascii=False)
        used += len(sc["text"])
        print(f"  voice scene {n} done")
    print(f"Voice done ({used} new characters used)")
