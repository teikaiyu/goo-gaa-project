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

if [[ "${SKIP_TESTS:-}" != "1" ]]; then
  echo "==> tests"
  # A throwaway venv keeps the test dependencies out of the user's global Python.
  VENV="$(mktemp -d)/venv"
  uv run python -m venv "$VENV"
  "$VENV/bin/pip" install -q -r avatar_api/requirements-dev.txt
  (cd avatar_api && "$VENV/bin/python" -m pytest -q)
fi

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
# /health: public and cheap. (Not /healthz: Cloud Run's front end swallows that path.)
curl -fsS --max-time 30 "${URL}/health" >/dev/null && echo "health ok"
# Both endpoints must reject a request without the token (401), proving the lock is on.
for path in avatar research; do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 -X POST \
            -H 'content-type: application/json' -d '{}' "${URL}/${path}")"
  [[ "$code" == "401" ]] || { echo "FAIL: /${path} answered ${code} without a token (expected 401)" >&2; exit 1; }
done
echo "auth lock ok"
echo "deployed: ${URL}"
