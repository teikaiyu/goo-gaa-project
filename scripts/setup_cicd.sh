#!/usr/bin/env bash
# One-time setup so GitHub Actions can deploy to Cloud Run WITHOUT any key file.
# Run once by a project OWNER (it creates a service account and grants roles):
#
#   GCP_PROJECT=goo-gaa-513906 scripts/setup_cicd.sh
#
# What it makes:
#   - github-deployer@ : the service account the workflow acts as (deploy-only roles)
#   - a Workload Identity pool + GitHub provider that trusts tokens from THIS repo only
# Then it prints the 3 values to set as GitHub repository variables. Safe to re-run.
set -euo pipefail

: "${GCP_PROJECT:?set GCP_PROJECT to your Google Cloud project id}"
REPO="${REPO:-teikaiyu/goo-gaa-project}"     # only this GitHub repo may deploy
RUNTIME_SA="${RUNTIME_SA:-avatar-api-sa@${GCP_PROJECT}.iam.gserviceaccount.com}"
DEPLOY_SA_NAME="github-deployer"
DEPLOY_SA="${DEPLOY_SA_NAME}@${GCP_PROJECT}.iam.gserviceaccount.com"
POOL="github"
PROVIDER="github-oidc"
g() { gcloud --project "$GCP_PROJECT" --quiet "$@"; }

echo "==> APIs"
g services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  youtube.googleapis.com  # the app reads the user's YouTube with the user's own permission

echo "==> deployer service account"
g iam service-accounts describe "$DEPLOY_SA" >/dev/null 2>&1 ||
  g iam service-accounts create "$DEPLOY_SA_NAME" --display-name "GitHub Actions deployer"

# Only what `gcloud run deploy --source .` and the smoke test need.
for role in roles/run.admin roles/cloudbuild.builds.editor roles/storage.admin \
            roles/artifactregistry.writer roles/serviceusage.serviceUsageConsumer; do
  g projects add-iam-policy-binding "$GCP_PROJECT" --member "serviceAccount:${DEPLOY_SA}" \
    --role "$role" --condition None >/dev/null
done
# Deploying "as" the runtime account needs permission to use that account (and only that one).
g iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member "serviceAccount:${DEPLOY_SA}" --role roles/iam.serviceAccountUser >/dev/null

echo "==> Workload Identity Federation (GitHub -> Google, no keys)"
g iam workload-identity-pools describe "$POOL" --location global >/dev/null 2>&1 ||
  g iam workload-identity-pools create "$POOL" --location global --display-name "GitHub"
g iam workload-identity-pools providers describe "$PROVIDER" --location global \
    --workload-identity-pool "$POOL" >/dev/null 2>&1 ||
  g iam workload-identity-pools providers create-oidc "$PROVIDER" --location global \
    --workload-identity-pool "$POOL" --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition "assertion.repository == '${REPO}'"  # other repos are refused

NUMBER="$(g projects describe "$GCP_PROJECT" --format 'value(projectNumber)')"
POOL_ID="projects/${NUMBER}/locations/global/workloadIdentityPools/${POOL}"
g iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/${REPO}" >/dev/null

echo
echo "Done. Set these in GitHub: ${REPO} > Settings > Secrets and variables > Actions > Variables"
echo "  GCP_PROJECT  = ${GCP_PROJECT}"
echo "  WIF_PROVIDER = ${POOL_ID}/providers/${PROVIDER}"
echo "  DEPLOY_SA    = ${DEPLOY_SA}"
