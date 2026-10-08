"""Free images from Cloudflare Workers AI (FLUX.1 schnell).

The free plan gives 10,000 neurons a day. One image at 8 steps costs well
under 100 neurons, so a 40-scene video fits easily.
"""

import base64
import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor

import requests

MODEL = "@cf/black-forest-labs/flux-1-schnell"
EXTS = (".jpg", ".jpeg", ".png", ".webp")


def existing(out_dir, n):
    for ext in EXTS:
        p = os.path.join(out_dir, n + ext)
        if os.path.exists(p):
            return p
    return None


def one(i, prompt, out_dir, steps, seed_base):
    n = f"{i + 1:02d}"
    if existing(out_dir, n):
        return
    acct = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{MODEL}"
    seed = int(hashlib.md5(f"{seed_base}-{i}".encode()).hexdigest()[:7], 16)
    for attempt in range(5):
        try:
            r = requests.post(url, json={"prompt": prompt[:2048], "steps": steps, "seed": seed},
                              headers={"Authorization": f"Bearer {token}"}, timeout=120)
        except requests.RequestException as e:
            print(f"  image {n}: {e}"); time.sleep(5 * (attempt + 1)); continue
        if r.status_code == 200 and r.json().get("success"):
            img = r.json()["result"]["image"]
            with open(os.path.join(out_dir, n + ".jpg"), "wb") as f:
                f.write(base64.b64decode(img))
            print(f"  image {n} done")
            return
        print(f"  image {n}: HTTP {r.status_code} {r.text[:200]}")
        if r.status_code in (401, 403):
            raise SystemExit("Cloudflare refused the request (check token and account ID).")
        if r.status_code == 429 or "neuron" in r.text.lower():
            print("  daily free limit may be used up; waiting and retrying")
        time.sleep(10 * (attempt + 1))
    raise SystemExit(f"Cloudflare failed on image {n}")


def make_images(scenes, style, out_dir, steps=8, seed_base="video"):
    os.makedirs(out_dir, exist_ok=True)
    jobs = []
    for i, sc in enumerate(scenes):
        if sc.get("image"):           # you supplied your own image for this scene
            continue
        prompt = f"{style.strip()} {sc['image_prompt'].strip()}"
        jobs.append((i, prompt))
    with ThreadPoolExecutor(max_workers=3) as ex:
        for f in [ex.submit(one, i, p, out_dir, steps, seed_base) for i, p in jobs]:
            f.result()
    print("Images done")
