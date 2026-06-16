# JobRadar AI — Automated Job Hunt

Intelligent job search automation that monitors job boards, scores positions against your resume skills, and sends smart alerts with AI-generated cover letter snippets.

## What it does

- 🔍 Searches Google Jobs every hour via SerpAPI for 7 target roles
- 📊 Scores each job against your resume skills (match %)
- ⚡ Sends instant Gmail alerts for high-match jobs (80%+)
- 📋 Sends hourly digest of all new matches
- ✍️ Optionally generates 3-sentence cover letter openers using Claude AI
- 🎯 Deduplicates — never emails the same job twice

## Secure Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Create your config files
```bash
# Copy and edit your profile
cp config.json.example config.json
```
Edit `config.json` with your:
- Name, email, phone, location
- Education & degree
- LinkedIn & GitHub profiles
- Technical skills (languages, ML/AI, cloud, tools, soft skills)

```bash
# Copy and edit your API keys
cp .env.example .env
```
Add your actual API keys to `.env`. **Never commit `.env` to GitHub.**

### 3. Get API Keys

**SerpAPI** (free tier: 100 searches/month)
- Sign up at https://serpapi.com
- Copy your API key to `.env` → `SERPAPI_KEY`

**Gmail API** (one-time browser setup)
- Go to https://console.cloud.google.com
- Create a project → Enable "Gmail API"
- Create OAuth 2.0 credentials (Desktop App) → Download JSON
- Rename to `credentials.json`, place in this folder
- Add your Gmail to `.env` → `GMAIL_FROM` and `GMAIL_TO`

**Anthropic API** (optional, for AI cover letters)
- Get key at https://console.anthropic.com
- Add to `.env` → `ANTHROPIC_KEY`

### 4. Run
```bash
python job_radar.py
```
First run will open a browser for Gmail OAuth (one-time setup, saves `token.json`).

## Configuration

Edit `.env` to customize:
```env
CHECK_INTERVAL=60          # minutes between job searches
INSTANT_THRESHOLD=80       # match % for instant alerts (vs digest)
```

## Monitored Roles
- ML Engineer
- Data Scientist
- Data Analyst
- AI Engineer
- Data Engineer
- Forward Deployed Engineer
- Software Engineer (ML/Data)

## Locations
- San Francisco Bay Area
- USA Nationwide
- Remote

## Deploy 24/7 Free

### Option 1: Render.com (free tier)
1. Push this repo to GitHub
2. Go to Render.com → New Web Service
3. Connect your repo
4. Add env vars: `SERPAPI_KEY`, `GMAIL_FROM`, `GMAIL_TO`, `ANTHROPIC_KEY`
5. Deploy (free tier runs continuously)

### Option 2: Google Cloud Run (always-free tier)
```bash
gcloud run deploy jobradar --source . --region us-west1 \
  --set-env-vars SERPAPI_KEY=your_key,GMAIL_FROM=your_email,GMAIL_TO=your_email
```

### Option 3: Local Linux machine
```bash
nohup python job_radar.py > jobradar.log 2>&1 &
```

## Security Notes

**Protected files** (in `.gitignore`, never committed):
- `credentials.json` — Gmail OAuth token
- `.env` — API keys
- `config.json` — Your personal details
- `token.json` — Gmail refresh token
- `seen_jobs.json` — Job history

Always use `config.json.example` and `.env.example` as templates for new installs.
