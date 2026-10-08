# Video Factory

Push a script, get a finished video. GitHub makes the voice (ElevenLabs), the images (Cloudflare, free) and renders the video (no shake, Hindi word-by-word captions).

## One-time setup

Add 4 secrets in GitHub: **Settings → Secrets and variables → Actions → New repository secret**

| Name | Where to get it |
| --- | --- |
| `ELEVENLABS_API_KEY` | ElevenLabs → profile → API Keys → Create. Give it Text to Speech access. |
| `ELEVENLABS_VOICE_ID` | ElevenLabs → Voices → open your voice → copy the Voice ID. |
| `CLOUDFLARE_API_TOKEN` | Cloudflare dashboard → My Profile → API Tokens → Create Token → "Workers AI" template. |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare dashboard → Account Home → the account's menu → Copy Account ID (also shown on the Workers & Pages page). |

## Make a video

1. Add `videos/<name>/script.json` (Claude writes it for you) and push.
2. GitHub starts by itself. Watch it in the **Actions** tab. A 7 minute video takes about 20 to 30 minutes.
3. When it's green, open the run and download **videos** at the bottom. Inside: the `.mp4` and `images-preview.jpg` (all images on one page).

## Fix one scene

- **Bad image:** delete `videos/<name>/images/07.jpg` and push. Only that image is made again.
- **Use your own image:** upload it as `videos/<name>/images/07.jpg` (or .png) and push.
- **Bad voice line:** fix the text in `script.json`, delete `audio/07.mp3` and `audio/07.json`, and push.
- **Just re-render:** Actions → Make video → Run workflow → type the folder name.

Everything that already exists is reused, so fixes cost almost nothing.

## Extras

- **Background music:** put `music.mp3` in the video folder (or `assets/music.mp3` for all videos). It plays quietly and drops under the voice.
- **Voice model:** change `"model_id"` in `script.json` (default `eleven_multilingual_v2`).
- **Camera move for a scene:** add `"move": "zoom_in"` (or `zoom_out`, `pan_left`, `pan_right`, `zoom_in_up`, `pan_down`) to that scene.

## Costs

- Images: Cloudflare free plan, 10,000 neurons a day. One video uses a few thousand.
- Voice: your ElevenLabs credits, about 5,000 characters per video.
- GitHub: free minutes on the free plan.
