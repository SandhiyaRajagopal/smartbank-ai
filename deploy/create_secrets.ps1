# Stores the app's secrets in Google Secret Manager so they never live in the
# container image or in Cloud Run's plain environment variables.
#
#   langsmith-api-key  <- LANGSMITH_API_KEY from your local .env
#   jwt-secret         <- a newly generated random value (signs login tokens)
#
# Run from the project root after `gcloud config set project <id>`:
#   .\deploy\create_secrets.ps1

$ErrorActionPreference = "Stop"

function Set-Secret([string]$name, [string]$value) {
    $tmp = New-TemporaryFile
    try {
        # write without a trailing newline or BOM so the secret is exactly the value
        [System.IO.File]::WriteAllText($tmp.FullName, $value)
        gcloud secrets describe $name *> $null
        if ($LASTEXITCODE -eq 0) {
            gcloud secrets versions add $name --data-file="$($tmp.FullName)" | Out-Null
            Write-Host "updated secret $name"
        } else {
            gcloud secrets create $name --replication-policy=automatic --data-file="$($tmp.FullName)" | Out-Null
            Write-Host "created secret $name"
        }
    } finally {
        Remove-Item $tmp.FullName -Force
    }
}

$envFile = Join-Path $PSScriptRoot "..\.env"
if (-not (Test-Path $envFile)) { throw ".env not found - copy .env.example to .env and add your keys first." }

$langsmith = (Get-Content $envFile | Where-Object { $_ -match '^LANGSMITH_API_KEY=(.+)$' } | ForEach-Object { $Matches[1].Trim() }) | Select-Object -First 1
if ($langsmith) { Set-Secret "langsmith-api-key" $langsmith } else { Write-Warning "LANGSMITH_API_KEY is empty in .env - LangSmith tracing will be off in the cloud." }

$bytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
Set-Secret "jwt-secret" ([Convert]::ToBase64String($bytes))

Write-Host "Done. Secrets are stored in Secret Manager (values not printed)."
