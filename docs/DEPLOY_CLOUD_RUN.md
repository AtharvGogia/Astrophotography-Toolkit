# Deploying to Google Cloud Run

Cloud Run runs the app's container only while someone is using it and scales to zero
otherwise, so a hobby site normally stays inside the monthly free tier. The repo already has
everything the container needs (`Dockerfile`, `.dockerignore`); these are the one-time steps
on your side.

## What it costs

- **Cloud Run:** the free tier covers a fixed number of vCPU-seconds and GiB-seconds of memory
  each month (see the [pricing page](https://cloud.google.com/run/pricing) for the current
  figures). A photo analysis uses a few seconds of one vCPU; the planner and previews use less
  than a second. With the settings below, the bill stays at or near $0 at personal/hobby traffic.
- **Image storage (Artifact Registry):** the image is about 1 GB. Storage beyond the free 0.5 GB
  costs a few cents a month; delete old images now and then.
- **Builds (Cloud Build):** `--source` deploys build the image in Google's cloud, within its free
  daily build minutes for occasional deploys.
- **Billing account:** Google requires one (with a card) even for free-tier use. Set a budget
  alert (step 2). Alerts notify you; they don't stop charges, which is why the deploy command
  below also caps the service at one instance.

## 1. Install the Google Cloud CLI

Install it from <https://cloud.google.com/sdk/docs/install>, then sign in:

```bash
gcloud init
```

## 2. Create a project, link billing, set a budget alert

In the [Cloud Console](https://console.cloud.google.com/):

1. Create a project, for example `astro-toolkit`.
2. **Billing** → link a billing account to the project.
3. **Billing → Budgets & alerts** → create a budget of, say, $2 with alerts at 50%, 90% and 100%.

Then point the CLI at the project and turn on the services the deploy uses:

```bash
gcloud config set project YOUR_PROJECT_ID
```

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

## 3. Deploy

From the repository folder:

```bash
gcloud run deploy astro-toolkit --source . --region asia-south1 --allow-unauthenticated --memory 2Gi --cpu 1 --concurrency 4 --min-instances 0 --max-instances 1 --timeout 120 --cpu-boost
```

What the options do:

- `--region asia-south1`: Mumbai, close to India. Any region works; check the pricing page,
  because prices differ slightly between region tiers.
- `--memory 2Gi --cpu 1`: enough for large photos; one CPU uses the free allowance slowly.
- `--min-instances 0`: scale to zero when idle (no cost), at the price of a cold start.
- `--max-instances 1`: never more than one copy, which caps cost and keeps the app's in-memory
  rate limiter accurate.
- `--concurrency 4`: up to four requests at once; at most two photo solves run at the same time.
- `--cpu-boost`: extra CPU while the container starts, for a quicker cold start.

The first deploy takes several minutes (it builds the image, including the solver index and
sky map). At the end it prints the address, like `https://astro-toolkit-xxxxxxxx.a.run.app`.

## 4. Updating

Run the same deploy command again after pulling or changing code. Each deploy makes a new
revision; Cloud Run switches traffic to it once it starts successfully.

## What changes when hosted

The image sets these (see `app/settings.py`):

| Setting | Value | Why |
|---|---|---|
| `HOSTED` | `1` | Privacy wording says photos are solved on the server (and not kept). |
| `SYNC_JOBS` | `1` | Photos are solved inside the upload request: Cloud Run only gives CPU during requests. |
| `WARMUP_SYNC` | `1` | Catalogs, sky map and solver index load before the first request is served. |
| `MAX_UPLOAD_MB` | `30` | Cloud Run accepts requests up to 32 MiB. The page shrinks big JPG/PNG files before upload. |
| `ANALYZE_PER_10_MIN` | `20` | Photo analyses per visitor per 10 minutes. |

Uploaded photos are processed in memory and dropped as soon as the answer is sent.

## Checking on it

```bash
gcloud run services logs read astro-toolkit --region asia-south1 --limit 50
```

`/healthz` on the site returns `{"ok": true, ...}` when the app is up.

## Running the same image elsewhere

```bash
docker build -t astro-toolkit .
```

```bash
docker run --rm -p 8080:8080 astro-toolkit
```

Then open <http://localhost:8080>.
