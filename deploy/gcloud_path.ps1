# Shared by the deploy scripts: sets $gcloud to the gcloud.cmd executable.
# Works even in a terminal opened before the Cloud SDK was installed (stale PATH).
# Uses gcloud.cmd, not the gcloud.ps1 wrapper, so gcloud's informational stderr
# output isn't turned into PowerShell errors.

$gcloud = (Get-Command gcloud.cmd -ErrorAction SilentlyContinue).Source
if (-not $gcloud) {
    $candidate = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    if (Test-Path $candidate) { $gcloud = $candidate }
}
if (-not $gcloud) { throw "gcloud not found - install the Google Cloud SDK, then open a new terminal." }
