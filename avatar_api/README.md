# avatar_api (Cloud Run)

`POST /avatar` turns the user's state into the avatar's mood, words and (optionally) a picture.

## API
Request (aggregates only - never URLs / app names / window titles):
```json
{ "social_seconds": 3000, "total_seconds": 4000, "local_hour": 23, "goal": "study", "include_image": true }
```
Response:
```json
{ "mood": "grumpy", "message": "...", "action": "...",
  "image_base64": "<bytes>|null", "image_mime": "image/png|null",
  "image_source": "file|generated|null", "source": "gemini|fallback" }
```
`mood` is one of `happy | uneasy | grumpy | angry`, decided in `mood.py` (tune `THRESHOLDS`).
`source: "fallback"` means Google was unreachable and prewritten lines were used.

## Avatar pictures (for the designer)
The pictures live in the repo-root **`images/`** folder. Which file shows for which mood is a table
(`MOOD_IMAGES` in `images.py`), so the designer's names stay as they are:

| Mood | Shown when (default thresholds) | File |
|---|---|---|
| happy | under 15 min on social media | `Lumo_happy.png` |
| uneasy | 15-45 min | `Lumo_disappointed.png` |
| grumpy | 45-90 min | `Lumo_annoyed.png` |
| angry | 90 min or more | `Lumo_angry.png` |

Not mapped yet (kept for later): `Lumo_calm.png` (idle), `Lumo_smile.png` (greeting), `Lumo_cheering.png` (achievement).

- To change which picture a mood uses, edit `MOOD_IMAGES` (one line per mood).
- Fallback: a plain `images/<mood>.<ext>` (e.g. `happy.png`) also works; the mapped name wins if both exist.
- Extensions: `.png`, `.webp`, `.jpg`, `.jpeg`, `.gif` (animated GIF works).
- Names are matched case-insensitively, so a file that works on macOS also works in the Linux container.
- Other files are ignored. A missing picture returns `image_base64: null` (not an error).
- A test (`test_repo_images_cover_every_mood`) fails if a mood has no picture in `images/`, so a rename is caught early.
- The files are baked into the Cloud Run image, so **a new picture needs a redeploy**.
- Keep each file small; it is sent as base64 inside the JSON (about 340-360 KB per response for the current ~270 KB PNGs).

## Files
| File | Role |
|---|---|
| `mood.py` | Pure logic: seconds -> mood, fallback lines. **Edit this to change the personality.** |
| `schemas.py` | Request/response contract |
| `images.py` | `MOOD_IMAGES` table (mood -> file) and the file lookup |
| `gemini.py` | All Google calls (text; optional image generation) |
| `main.py` | Endpoint, token check, graceful degradation |
| `../Dockerfile` | Cloud Run image. At the repo root so it can copy `images/` |

## Environment variables
| Name | Meaning |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | Your GCP project ID (required for Gemini) |
| `VERTEX_LOCATION` | Default `global` (all Gemini 3.x models work there; only 3.5 also in `asia-northeast1`). |
| `TEXT_MODEL` | Default `gemini-3.5-flash`. `gemini-2.5-flash` is **retired** (404). Models retire, so re-check before the demo. |
| `IMAGE_MODEL` | Default `gemini-3.1-flash-image` (works in `global` / `us-central1`, not Tokyo). Only used if generation is enabled. |
| `API_TOKEN` | Shared secret. **Required on Cloud Run** (the service refuses to run open). |
| `IMAGES_DIR` | Where the pictures are. Default: repo-root `images/` locally, `/app/images` in the container. |
| `ENABLE_IMAGE_GENERATION` | `1` = if no file exists for a mood, generate a picture with Gemini (costs money; off by default). |

## Run locally
```
cd avatar_api
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/uvicorn main:app --port 8080          # works without GCP: returns fallback lines
```
With real Gemini locally: `gcloud auth application-default login`, then set `GOOGLE_CLOUD_PROJECT`.

## Deploy (when you are ready; this creates billable cloud resources)
Run from the **repo root** (not from `avatar_api/`), so the build can see `images/`:
```
gcloud run deploy avatar-api --source . --region asia-northeast1 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<project>,API_TOKEN=<long-random-string>
```
Then grant the Cloud Run service account the **Vertex AI User** role, and set a budget alert.
Prefer Secret Manager over `--set-env-vars` for `API_TOKEN` once it works.

## POST /research (memo pre-research)
Body `{"note": "<=300 chars"}` -> `{summary, next_step, source}`. Uses Gemini with Google Search grounding (`RESEARCH_GROUNDING=0` turns search off). On any Google failure it answers 200 with `source: "fallback"` and empty text, and the desktop app retries later. The memo is never logged. Same bearer token as `/avatar`.

## Deploy from a script (hand or CI)
`GCP_PROJECT=<project> scripts/deploy_avatar_api.sh` - tests, then `gcloud run deploy`, then a smoke test (see the header of the script for all settings).

## Not done yet
- **Video** (Veo): long-running job (minutes) and costly; needs an async flow, not this request/response.
- Rate limiting, and sharing the picture cache across instances (e.g. Cloud Storage).
