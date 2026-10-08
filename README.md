# Video Factory

Push a script, get a finished video. You make the images in ChatGPT. GitHub makes the voice (ElevenLabs), syncs everything and renders the video (no shake, Hindi word-by-word captions).

## One-time setup

Add these secrets in GitHub: **Settings → Secrets and variables → Actions → New repository secret**

| Name | Where to get it |
| --- | --- |
| `ELEVENLABS_API_KEY` | ElevenLabs → profile → API Keys → Create. Give it Text to Speech access. |
| `ELEVENLABS_VOICE_ID` | ElevenLabs → Voices → open your voice → copy the Voice ID. |

## Make a video

1. Claude writes `videos/<name>/script.json` and `image-prompts.txt`.
2. Make the images in ChatGPT and upload them to `videos/<name>/images/` as `01.png`, `02.png` ... (on GitHub: open the folder → Add file → Upload files).
3. GitHub starts by itself. Watch it in the **Actions** tab. A 7 minute video takes about 20 to 30 minutes.
4. When it's green, open the run and download **videos** at the bottom. Inside: the `.mp4` and `images-preview.jpg` (all images on one page).

## Fix one scene

- **Bad image:** upload a new `07.png` over the old one.
- **Bad voice line:** fix the text in `script.json`, delete `audio/07.mp3` and `audio/07.json`, and push.
- **Just re-render:** Actions → Make video → Run workflow → type the folder name.

Everything that already exists is reused, so fixes cost almost nothing.

## Extras

- **Background music:** put `music.mp3` in the video folder (or `assets/music.mp3` for all videos). It plays quietly and drops under the voice.
- **Voice model:** change `"model_id"` in `script.json` (default `eleven_multilingual_v2`).
- **Camera move for a scene:** add `"move": "zoom_in"` (or `zoom_out`, `pan_left`, `pan_right`, `zoom_in_up`, `pan_down`) to that scene.

## Costs

- Images: made by you in ChatGPT. (Optional: set `"images": "auto"` in script.json and add Cloudflare secrets to make them for free automatically, lower quality.)
- Voice: your ElevenLabs credits, about 5,000 characters per video.
- GitHub: free minutes on the free plan.
