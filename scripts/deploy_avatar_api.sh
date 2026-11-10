#!/usr/bin/env bash
# Deploy avatar_api to Cloud Run. Safe to run by hand or from CI (same script, same result).
#
#   GCP_PROJECT=my-project scripts/deploy_avatar_api.sh
#
# Settings come from environment variables (nothing project-specific or secret is in this file):
#   GCP_PROJECT   required  Google Cloud project id
#   REGION        default asia-northeast1
#   SERVICE       default avatar-api
#   RUNTIME_SA    default avatar-api-sa@${GCP_PROJECT}.iam.gserviceaccount.com
#                 (needs roles/aiplatform.user + roles/secretmanager.secretAccessor)
#   SECRET_NAME   default api-token     Secret Manager secret that holds API_TOKEN
#   GOOGLE_CLIENT_ID          OAuth client ID (public) that lets users allow Lumo to read their YouTube.
#                 Without it the app still works, and Lumo says it could not connect to YouTube.
#   MAX_INSTANCES default 2             cost guard: caps how many copies can run at once
#   SKIP_TESTS    set to 1 to skip the pre-deploy test run
#
# Why this order: tests first (a red build must never reach production) -> deploy -> smoke test
# (a deploy that "succeeded" but serves errors fails the pipeline instead of being found by a user).
# Credentials: locally `gcloud auth login`; in CI use Workload Identity Federation (no key files).
set -euo pipefail

: "${GCP_PROJECT:?set GCP_PROJECT to your Google Cloud project id}"
REGION="${REGION:-asia-northeast1}"
SERVICE="${SERVICE:-avatar-api}"
RUNTIME_SA="${RUNTIME_SA:-avatar-api-sa@${GCP_PROJECT}.iam.gserviceaccount.com}"
SECRET_NAME="${SECRET_NAME:-api-token}"
MAX_INSTANCES="${MAX_INSTANCES:-2}"

# Always run from the repo root: the Docker build needs both avatar_api/ and images/.
cd "$(dirname "${BASH_SOURCE[0]}")/.."

command -v gcloud >/dev/null || { echo "gcloud not found (https://cloud.google.com/sdk)" >&2; exit 1; }
command -v flutter >/dev/null || { echo "flutter not found (brew install --cask flutter)" >&2; exit 1; }

if [[ "${SKIP_TESTS:-}" != "1" ]]; then
  echo "==> tests"
  # A throwaway venv keeps the test dependencies out of the user's global Python.
  VENV="$(mktemp -d)/venv"
  uv run python -m venv "$VENV"
  "$VENV/bin/pip" install -q -r avatar_api/requirements-dev.txt
  (cd avatar_api && "$VENV/bin/python" -m pytest -q)
  (cd lumo_app && flutter test)
fi

echo "==> building the iPhone web app"
# The Dockerfile copies lumo_app/build/web, so it must be fresh before the upload.
[[ -n "${GOOGLE_CLIENT_ID:-}" ]] || echo "note: GOOGLE_CLIENT_ID is not set -> Lumo cannot connect to YouTube"
(cd lumo_app && flutter build web --release --dart-define=GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-}")
echo "==> putting the app inside the Chrome extension (handed out as /lumo_extension.zip)"
lumo_extension/build.sh

echo "==> deploying ${SERVICE} to ${GCP_PROJECT}/${REGION}"
# --source . : Cloud Build builds the root Dockerfile, so no local Docker is needed.
# --allow-unauthenticated: the desktop app has no Google identity; the bearer token (API_TOKEN, from
#   Secret Manager) is the lock, and the service refuses to start serving without it.
gcloud run deploy "$SERVICE" \
  --project "$GCP_PROJECT" --region "$REGION" --source . \
  --service-account "$RUNTIME_SA" \
  --allow-unauthenticated \
  --max-instances "$MAX_INSTANCES" \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${GCP_PROJECT}" \
  --set-secrets "API_TOKEN=${SECRET_NAME}:latest" \
  --quiet

echo "==> smoke test"
URL="$(gcloud run services describe "$SERVICE" --project "$GCP_PROJECT" --region "$REGION" \
        --format 'value(status.url)')"
# Each check exits on failure itself: with `a && b`, set -e would NOT stop the script when `a` fails.
check() { curl -fsS --max-time 30 -o /dev/null "${URL}$1" || { echo "FAIL: GET $1" >&2; exit 1; }; }
check /health                # public and cheap. (Not /healthz: Cloud Run's front end swallows that path.)
check /                      # the iPhone web app
check /lumo/Lumo_smile.png   # Lumo's pictures
check /lumo_extension.zip    # the Chrome extension the app tells PC users to install
echo "health, app, images and extension ok"
# The desktop app's Gemini endpoints must reject a request without the token (401), proving the lock is on.
# (/patrol is open on purpose and capped per day instead: avatar_api/main.py limit_patrol.)
for path in avatar watch recap; do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 -X POST \
            -H 'content-type: application/json' -d '{}' "${URL}/${path}")"
  [[ "$code" == "401" ]] || { echo "FAIL: /${path} answered ${code} without a token (expected 401)" >&2; exit 1; }
done
echo "auth lock ok"
echo "deployed: ${URL}"
