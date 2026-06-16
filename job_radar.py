"""
JobRadar AI — Automated Job Hunt for Vedika Sumbli
====================================================
Searches Google Jobs via SerpAPI every hour for 7 target roles,
scores matches against your resume skills, deduplicates, and sends
a Gmail digest with AI-generated cover letter snippets.

SETUP (one-time, ~10 minutes):
  1. pip install google-api-python-client google-auth-oauthlib serpapi schedule requests
  2. Get free SerpAPI key at https://serpapi.com  (100 searches/month free)
  3. Gmail API:
       a. Go to https://console.cloud.google.com
       b. Create project → Enable "Gmail API"
       c. OAuth 2.0 → Desktop App → Download credentials.json
       d. Place credentials.json in the same folder as this script
  4. Set your SERPAPI_KEY below
  5. python job_radar.py
     (First run opens browser for Gmail auth — one time only, saves token.json)

DEPLOY 24/7 FREE:
  - Render.com (free tier) or Google Cloud Run (free tier)
  - Or: nohup python job_radar.py &  on any always-on Linux machine
"""

import os, json, time, datetime, logging, re
import schedule
import requests
from serpapi import GoogleSearch
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import base64

# Google Auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ─── CONFIG ────────────────────────────────────────────────────────────────────
SERPAPI_KEY      = "YOUR_SERPAPI_KEY_HERE"          # https://serpapi.com
GMAIL_TO         = "vedika.sumbli@gmail.com"
GMAIL_FROM       = "vedika.sumbli@gmail.com"        # must match OAuth account
SEEN_FILE        = "seen_jobs.json"
TOKEN_FILE       = "token.json"
CREDENTIALS_FILE = "credentials.json"
CHECK_INTERVAL   = 60                               # minutes between searches
INSTANT_THRESHOLD = 80                             # match % for instant alert
SCOPES           = ["https://www.googleapis.com/auth/gmail.send"]
ANTHROPIC_KEY    = "YOUR_ANTHROPIC_KEY_HERE"       # optional: for cover letters

# ─── YOUR PROFILE ──────────────────────────────────────────────────────────────
CANDIDATE = {
    "name": "Vedika Sumbli",
    "email": GMAIL_TO,
    "phone": "(657) 750-6525",
    "location": "San Jose, CA",
    "degree": "MS Applied Data Intelligence, SJSU (In Progress)",
    "linkedin": "linkedin.com/in/vedikasumbli",
    "github": "github.com/vedikasumbli",
}

SKILLS = {
    "languages":  ["Python", "SQL", "Java", "Scala", "C", "C++", "MATLAB"],
    "ml_ai":      ["PyTorch", "TensorFlow", "Scikit-Learn", "Transformers", "LangChain",
                   "Ollama", "Neo4j", "ElasticSearch", "NumPy", "Pandas", "XGBoost",
                   "GNN", "RAG", "Few-Shot Learning", "SHAP", "ARIMA", "SMOTE",
                   "Grad-CAM", "ALS", "KMeans", "TF-IDF", "NLP", "LLM"],
    "cloud":      ["AWS", "S3", "EC2", "SageMaker", "Lambda", "Athena", "EMR", "RDS",
                   "Snowflake", "Redis", "Kafka", "Spark", "Hadoop"],
    "tools":      ["Airflow", "Docker", "Tableau", "Power BI", "Streamlit", "Git",
                   "Jira", "Parquet", "AWS QuickSight", "Agentic pipeline"],
    "soft":       ["Team leadership", "Stakeholder management", "Agile", "Project management"],
}

ALL_SKILLS = [s.lower() for group in SKILLS.values() for s in group]

# ─── TARGET ROLES ──────────────────────────────────────────────────────────────
ROLE_QUERIES = [
    ("ML Engineer",              ["machine learning engineer", "ML engineer"]),
    ("Data Scientist",           ["data scientist"]),
    ("Data Analyst",             ["data analyst"]),
    ("AI Engineer",              ["AI engineer", "artificial intelligence engineer", "GenAI engineer"]),
    ("Data Engineer",            ["data engineer"]),
    ("Forward Deployed Engineer",["forward deployed engineer", "field engineer software"]),
    ("SWE",                      ["software engineer machine learning", "software engineer data"]),
]

LOCATIONS = ["San Francisco Bay Area", "United States", "Remote"]

# ─── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("jobradar.log")],
)
log = logging.getLogger("jobradar")

# ─── SEEN JOBS ─────────────────────────────────────────────────────────────────
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

# ─── MATCH SCORING ─────────────────────────────────────────────────────────────
def score_job(title: str, description: str) -> tuple[int, list[str]]:
    """Return (match_percent, matched_skill_list)."""
    text = (title + " " + description).lower()
    matched = [s for s in ALL_SKILLS if s in text]
    # Bonus for role keywords
    role_bonus = 0
    role_map = {
        "machine learning": 10, "deep learning": 8, "pytorch": 6, "tensorflow": 6,
        "spark": 6, "kafka": 5, "langchain": 7, "llm": 7, "data pipeline": 5,
        "aws": 5, "python": 4, "sql": 4,
    }
    for kw, pts in role_map.items():
        if kw in text:
            role_bonus += pts
    raw = len(matched) * 5 + role_bonus
    pct = min(99, raw)
    display_matched = [s.title() for s in matched[:6]]
    return pct, display_matched

# ─── SERPAPI SEARCH ────────────────────────────────────────────────────────────
def search_jobs(query: str, location: str) -> list[dict]:
    """Search Google Jobs via SerpAPI. Returns list of job dicts."""
    try:
        params = {
            "engine": "google_jobs",
            "q": query,
            "location": location,
            "hl": "en",
            "chips": "date_posted:today",   # last 24h (tightest Google allows)
            "api_key": SERPAPI_KEY,
        }
        results = GoogleSearch(params).get_dict()
        return results.get("jobs_results", [])
    except Exception as e:
        log.warning(f"SerpAPI error for '{query}' in '{location}': {e}")
        return []

def collect_new_jobs(seen: set) -> list[dict]:
    """Run all role × location queries and return deduplicated new jobs."""
    new_jobs = []
    for role_label, queries in ROLE_QUERIES:
        for query in queries:
            for location in LOCATIONS:
                raw = search_jobs(query, location)
                for j in raw:
                    job_id = j.get("job_id") or (j.get("title","") + j.get("company_name",""))
                    if job_id in seen:
                        continue
                    description = j.get("description", "")
                    match_pct, matched_skills = score_job(j.get("title",""), description)
                    new_jobs.append({
                        "id":            job_id,
                        "role_label":    role_label,
                        "title":         j.get("title", ""),
                        "company":       j.get("company_name", ""),
                        "location":      j.get("location", location),
                        "posted":        j.get("detected_extensions", {}).get("posted_at", "Recently"),
                        "apply_link":    j.get("related_links", [{}])[0].get("link", j.get("share_link","")),
                        "description":   description[:800],
                        "match_pct":     match_pct,
                        "matched_skills":matched_skills,
                    })
                    seen.add(job_id)
    # Sort by match score descending
    new_jobs.sort(key=lambda x: x["match_pct"], reverse=True)
    # Deduplicate by (title, company)
    seen_tc = set()
    deduped = []
    for j in new_jobs:
        tc = (j["title"].lower(), j["company"].lower())
        if tc not in seen_tc:
            seen_tc.add(tc)
            deduped.append(j)
    return deduped

# ─── COVER LETTER SNIPPET (optional Anthropic API) ─────────────────────────────
def generate_cover_snippet(job: dict) -> str:
    """Generate a 3-sentence cover letter opener via Claude API."""
    if ANTHROPIC_KEY == "YOUR_ANTHROPIC_KEY_HERE":
        return ""
    try:
        headers = {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 200,
            "messages": [{
                "role": "user",
                "content": (
                    f"Write a 3-sentence cover letter opener for Vedika Sumbli applying to "
                    f"{job['title']} at {job['company']}. "
                    f"Her skills: Python, PyTorch, LangChain, Spark, AWS, Airflow, RAG, GNNs. "
                    f"She's completing MS Applied Data Intelligence at SJSU. "
                    f"Matched skills for this role: {', '.join(job['matched_skills'])}. "
                    f"Be specific, confident, no fluff. Return only the 3 sentences."
                )
            }]
        }
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers=headers, json=body, timeout=15)
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        log.warning(f"Cover letter gen failed: {e}")
        return ""

# ─── EMAIL BUILDER ─────────────────────────────────────────────────────────────
MATCH_COLOR = lambda pct: ("#16a34a" if pct>=85 else "#d97706" if pct>=70 else "#6b7280")

def build_email_html(jobs: list[dict], run_time: str) -> str:
    count = len(jobs)
    rows = ""
    for j in jobs:
        cover = generate_cover_snippet(j)
        cover_html = (f"<div style='margin:6px 0 0;font-size:12px;color:#555;background:#f9f9f9;"
                      f"padding:8px 10px;border-left:3px solid #3b82f6;border-radius:4px'>"
                      f"<strong>Cover snippet:</strong> {cover}</div>") if cover else ""
        skills_html = " ".join(
            f"<span style='font-size:11px;padding:2px 7px;border-radius:12px;"
            f"background:#eff6ff;color:#1d4ed8;border:0.5px solid #bfdbfe'>{s}</span>"
            for s in j["matched_skills"]
        )
        rows += f"""
        <tr>
          <td style="padding:14px 16px;border-bottom:1px solid #f0f0f0;vertical-align:top">
            <div style="display:flex;justify-content:space-between;align-items:flex-start">
              <div>
                <div style="font-weight:600;font-size:14px;color:#111">{j['company']}</div>
                <div style="font-size:13px;color:#555;margin-top:2px">{j['title']} · {j['location']}</div>
                <div style="margin-top:6px;display:flex;gap:4px;flex-wrap:wrap">{skills_html}</div>
                {cover_html}
              </div>
              <div style="text-align:right;flex-shrink:0;margin-left:16px">
                <div style="font-size:20px;font-weight:700;color:{MATCH_COLOR(j['match_pct'])}">{j['match_pct']}%</div>
                <div style="font-size:11px;color:#888">{j['posted']}</div>
                <a href="{j['apply_link']}" style="display:inline-block;margin-top:6px;font-size:12px;
                   padding:5px 12px;background:#111;color:#fff;border-radius:6px;text-decoration:none">Apply →</a>
              </div>
            </div>
          </td>
        </tr>"""

    return f"""
<!DOCTYPE html><html><body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;
  background:#f5f5f5;margin:0;padding:0">
<div style="max-width:620px;margin:24px auto;background:#fff;border-radius:12px;
     overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)">
  <div style="background:#111;padding:20px 24px;color:#fff">
    <div style="font-size:18px;font-weight:600">🚨 {count} new job match{'es' if count!=1 else ''}</div>
    <div style="font-size:13px;color:#aaa;margin-top:4px">{run_time} · vedika.sumbli@gmail.com</div>
  </div>
  <table style="width:100%;border-collapse:collapse">{rows}</table>
  <div style="padding:16px 24px;background:#fafafa;font-size:12px;color:#888;
       border-top:1px solid #eee">
    Roles: ML Eng · Data Scientist · Data Analyst · AI Eng · Data Eng · Forward Deployed Eng · SWE<br>
    Locations: San Francisco Bay Area · USA Nationwide · Remote<br>
    <a href="mailto:{GMAIL_TO}">Unsubscribe</a> · JobRadar AI
  </div>
</div></body></html>"""

# ─── GMAIL SEND ────────────────────────────────────────────────────────────────
def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

def send_email(subject: str, html_body: str):
    service = get_gmail_service()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_FROM
    msg["To"]      = GMAIL_TO
    msg.attach(MIMEText(html_body, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    log.info(f"Email sent: {subject}")

# ─── MAIN JOB RUN ──────────────────────────────────────────────────────────────
def run_job_search():
    log.info("─── Job search started ───")
    seen = load_seen()
    new_jobs = collect_new_jobs(seen)
    save_seen(seen)

    if not new_jobs:
        log.info("No new jobs found this cycle.")
        return

    log.info(f"Found {len(new_jobs)} new job(s). Top match: {new_jobs[0]['company']} ({new_jobs[0]['match_pct']}%)")

    now_str = datetime.datetime.now().strftime("%a %d %b, %I:%M %p")

    # Instant alert for very high matches
    instant = [j for j in new_jobs if j["match_pct"] >= INSTANT_THRESHOLD]
    if instant:
        html = build_email_html(instant, now_str)
        send_email(f"⚡ {len(instant)} high-match job(s) just posted — {instant[0]['company']} ({instant[0]['match_pct']}%)", html)

    # Full digest (excluding already instant-alerted ones)
    rest = [j for j in new_jobs if j["match_pct"] < INSTANT_THRESHOLD]
    if rest:
        html = build_email_html(rest, now_str)
        send_email(f"📋 {len(rest)} new job match(es) — {now_str}", html)

    log.info("─── Job search complete ───")

# ─── SCHEDULER ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("JobRadar AI starting up for Vedika Sumbli...")
    log.info(f"Monitoring roles: {[r[0] for r in ROLE_QUERIES]}")
    log.info(f"Locations: {LOCATIONS}")
    log.info(f"Sending alerts to: {GMAIL_TO}")
    log.info(f"Check interval: every {CHECK_INTERVAL} minutes")

    # Run immediately on start
    run_job_search()

    # Schedule recurring
    schedule.every(CHECK_INTERVAL).minutes.do(run_job_search)
    while True:
        schedule.run_pending()
        time.sleep(30)
