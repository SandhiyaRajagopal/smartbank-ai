# Deploying SmartBank AI to Google Cloud

**Target:** Cloud Run (asia-south1, Mumbai) · **LLM:** Gemini on Vertex AI · **Build:** Cloud Build from the repo's `Dockerfile`

```
 gcloud run deploy --source .
        │  uploads the source (minus .gcloudignore)
        ▼
 Cloud Build ── builds Dockerfile ──► Artifact Registry (container image)
                                           │
                                           ▼
                Cloud Run service "smartbank-ai"  (runs as smartbank-run@ service account)
                   ├── Vertex AI  Gemini chat + embeddings   (IAM: roles/aiplatform.user, no API key)
                   ├── Secret Manager  JWT_SECRET, LANGSMITH_API_KEY  (IAM: secretAccessor on those secrets only)
                   └── Cloud Logging   (IAM: roles/logging.logWriter)
```

## Why these choices
- **Cloud Run:** serverless containers with HTTPS and WebSocket support out of the box, scaling and pay-per-use. No servers to manage.
- **Vertex AI instead of an API key:** in Google Cloud the service authenticates as its **service account**, so no long-lived key exists that could leak. Usage is billed to the project's credits and governed by IAM.
- **Dedicated least-privilege service account:** the service can call Gemini, read its own two secrets and write logs, and nothing else.
- **Secret Manager:** secrets are mounted as environment variables at runtime. They are never baked into the image or shown in the Cloud Run configuration.
- **Single instance (`--max-instances 1`):** SQLite and the in-process WebSocket hub must live in one instance. The data re-seeds when a new revision starts. The upgrade path is Cloud SQL Postgres (`DATABASE_URL` is already configurable) plus Redis pub/sub for the hub.
- **`--min-instances 1`:** no cold start when an evaluator opens the link.
- **Budget alert:** ₹2,000 with email alerts at 50/90/100%.

## One-time setup (already done for this project)
```bash
gcloud auth login
gcloud auth application-default login          # lets the app on your PC call Vertex AI as you
gcloud config set project <PROJECT_ID>
gcloud services enable aiplatform.googleapis.com run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
gcloud iam service-accounts create smartbank-run --display-name="SmartBank AI (Cloud Run)"
gcloud projects add-iam-policy-binding <PROJECT_ID> --member=serviceAccount:smartbank-run@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/aiplatform.user
gcloud projects add-iam-policy-binding <PROJECT_ID> --member=serviceAccount:smartbank-run@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/logging.logWriter
```
Store secrets (reads `LANGSMITH_API_KEY` from `.env`, generates a JWT secret, prints no values):
```powershell
.\deploy\create_secrets.ps1
gcloud secrets add-iam-policy-binding jwt-secret --member=serviceAccount:smartbank-run@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding langsmith-api-key --member=serviceAccount:smartbank-run@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
```

## Deploy / redeploy
```powershell
.\deploy\deploy.ps1
```

## Run locally against Vertex AI
In `.env` set `USE_VERTEXAI=true`, `GCP_PROJECT=<PROJECT_ID>`, `GCP_LOCATION=global`, then:
```bash
uvicorn backend.app.main:app --reload
```

## Operate
```bash
gcloud run services logs read smartbank-ai --region asia-south1 --limit 50
gcloud run services describe smartbank-ai --region asia-south1 --format="value(status.url)"
```
To stop spending credits after the evaluation: `gcloud run services update smartbank-ai --region asia-south1 --min-instances 0`, or delete the service.
