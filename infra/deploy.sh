#!/bin/bash
#
# ExodusAI Deployment Script
# Builds and deploys to Google Cloud Run + Firebase Hosting.
#
# Usage:
#   export GOOGLE_CLOUD_PROJECT=your-project-id
#   ./deploy.sh
#

set -euo pipefail

# Configuration
PROJECT="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT environment variable}"
REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
SERVICE_NAME="exodusai-backend"
REPO_NAME="exodusai"
IMAGE_NAME="backend"
TAG="${IMAGE_TAG:-latest}"

REGISTRY="${REGION}-docker.pkg.dev/${PROJECT}/${REPO_NAME}/${IMAGE_NAME}:${TAG}"

echo "=== ExodusAI Deployment ==="
echo "Project:  ${PROJECT}"
echo "Region:   ${REGION}"
echo "Image:    ${REGISTRY}"
echo ""

# 1. Ensure Artifact Registry exists
echo "--- Creating Artifact Registry (if needed) ---"
gcloud artifacts repositories describe "${REPO_NAME}" \
    --location="${REGION}" --project="${PROJECT}" 2>/dev/null || \
gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${PROJECT}" \
    --description="ExodusAI Docker images"

# 2. Build and push Docker image
echo ""
echo "--- Building Docker image ---"
cd "$(dirname "$0")/../backend"
docker build -t "${REGISTRY}" .

echo ""
echo "--- Pushing to Artifact Registry ---"
docker push "${REGISTRY}"

# 3. Deploy to Cloud Run
echo ""
echo "--- Deploying to Cloud Run ---"
gcloud run deploy "${SERVICE_NAME}" \
    --image="${REGISTRY}" \
    --platform=managed \
    --region="${REGION}" \
    --project="${PROJECT}" \
    --allow-unauthenticated \
    --port=8080 \
    --timeout=3600 \
    --session-affinity \
    --cpu=2 \
    --memory=2Gi \
    --min-instances=0 \
    --max-instances=5 \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT},FEED_MODE=simulation,TRAFFIC_MODE=mock" \
    --set-secrets="GOOGLE_API_KEY=exodusai-google-api-key:latest,ROUTES_API_KEY=exodusai-routes-api-key:latest"

# 4. Get the service URL
echo ""
echo "--- Deployment Complete ---"
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" --project="${PROJECT}" \
    --format='value(status.url)')
echo "Backend URL: ${SERVICE_URL}"

# 5. Deploy frontend (if Firebase is configured)
echo ""
if command -v firebase &> /dev/null && [ -f "$(dirname "$0")/../firebase.json" ]; then
    echo "--- Deploying frontend to Firebase ---"
    cd "$(dirname "$0")/.."
    firebase deploy --only hosting --project="${PROJECT}"
else
    echo "--- Skipping Firebase deploy (firebase CLI not found or firebase.json missing) ---"
    echo "To deploy the frontend, serve the frontend/ directory via Firebase Hosting or any static host."
    echo "Update the WebSocket URL in the frontend to point to: ${SERVICE_URL}"
fi

echo ""
echo "=== Done ==="
