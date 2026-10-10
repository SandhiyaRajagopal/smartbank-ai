# Builds the Dockerfile with Cloud Build and deploys it to Cloud Run.
#   .\deploy\deploy.ps1
# Prerequisites (one-time): gcloud login, project set, APIs enabled, service account
# + secrets created - see DEPLOY.md.

$PROJECT = (& gcloud.cmd config get-value project 2>$null)
$REGION = "asia-south1"                      # Mumbai - where the service runs
$SERVICE = "smartbank-ai"
$SA = "smartbank-run@$PROJECT.iam.gserviceaccount.com"            # identity the app runs as
$BUILD_SA = "projects/$PROJECT/serviceAccounts/smartbank-build@$PROJECT.iam.gserviceaccount.com"  # identity Cloud Build uses
if (-not $PROJECT) { throw "No gcloud project set. Run: gcloud config set project <id>" }

$envVars = @(
    "USE_VERTEXAI=true",                     # Gemini via Vertex AI, authenticated by the service account
    "GCP_PROJECT=$PROJECT",
    "GCP_LOCATION=global",                   # Vertex endpoint serving gemini-3.8-flash
    "GEMINI_MODEL=gemini-3.8-flash",
    "GEMINI_EMBEDDING_MODEL=gemini-embedding-001",
    "LANGSMITH_TRACING=true",
    "LANGSMITH_PROJECT=smartbank-ai",
    "SIMULATOR_INTERVAL=20"
) -join ","

$secrets = @("JWT_SECRET=jwt-secret:latest")
$existing = & gcloud.cmd secrets list --format="value(name)" 2>$null | ForEach-Object { ($_ -split '/')[-1] }
if ($existing -contains "langsmith-api-key") { $secrets += "LANGSMITH_API_KEY=langsmith-api-key:latest" }

# max-instances=1: SQLite and the in-process WebSocket hub live inside one instance.
# min-instances=1: no cold start for evaluators; data re-seeds only on redeploy.
# timeout=3600: lets WebSocket connections stay open up to an hour.
& gcloud.cmd run deploy $SERVICE `
    --source . `
    --region $REGION `
    --service-account $SA `
    --build-service-account $BUILD_SA `
    --allow-unauthenticated `
    --min-instances 1 --max-instances 1 `
    --cpu 1 --memory 1Gi `
    --timeout 3600 `
    --set-env-vars $envVars `
    --set-secrets ($secrets -join ",") `
    --quiet

if ($LASTEXITCODE -eq 0) {
    $url = & gcloud.cmd run services describe $SERVICE --region $REGION --format="value(status.url)" 2>$null
    Write-Host "`nDeployed: $url"
}
