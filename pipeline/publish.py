"""Publish a built video: commit to the Videos repo, append queue.json (YouTube via Apps Script),
and schedule on TikTok + Instagram through Zernio.

  ZERNIO_API_KEY=sk_... python3 publish.py <job.json> <video.mp4> <publish_at ISO -05:00/-06:00>

Caption format: hook + question, blank line, linktree line, blank line, hashtags.
"""
import json, os, subprocess, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RAW = "https://raw.githubusercontent.com/coolsvilleaiposting-afk/Videos/main/"
LINK = "More gaming history: linktr.ee/coolsvillecrossings"
ZBASE = "https://zernio.com/api/v1"

def caption(job):
    return f"{job['hook']}\n\n{LINK}\n\n{job['hashtags']}"

def zernio(method, path, body=None):
    key = os.environ["ZERNIO_API_KEY"]
    args = ["curl", "-sS", "-m", "90", "--retry", "3", "--retry-all-errors", "-X", method, ZBASE + path,
            "-H", f"Authorization: Bearer {key}", "-H", "Content-Type: application/json"]
    if body is not None:
        args += ["--data", json.dumps(body)]
    out = subprocess.run(args, capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise SystemExit(f"Zernio bad response {path}: {out[:400]}")

def zernio_accounts():
    ids = {}
    for a in zernio("GET", "/accounts").get("accounts", []):
        if a.get("isActive") and a["platform"] in ("tiktok", "instagram") and a["platform"] not in ids:
            ids[a["platform"]] = a["_id"]
    return ids

def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], check=True, capture_output=True, text=True).stdout

def commit_video(video, job, publish_at):
    name = os.path.basename(video)
    dest = os.path.join(REPO, name)
    # analytics.py writes pipeline/analytics.json before publishing; carry it across the reset
    keep = {}
    for f in ("pipeline/analytics.json", "pipeline/youtube_stats.json"):
        fp = os.path.join(REPO, f)
        if os.path.exists(fp): keep[f] = open(fp, "rb").read()
    git("fetch", "origin", "main")
    git("reset", "--hard", "origin/main")   # keep queue.json current before editing
    for f, b in keep.items():
        open(os.path.join(REPO, f), "wb").write(b)
    if os.path.abspath(video) != dest:
        subprocess.run(["cp", video, dest], check=True)
    q = json.load(open(os.path.join(REPO, "queue.json")))
    ids = [int(x["id"]) for x in q if str(x.get("id", "")).isdigit()]
    entry = {"id": str(max(ids + [0]) + 1), "publish_at": publish_at, "video_url": RAW + name,
             "title": job["title"], "caption": caption(job)}
    q.append(entry)
    json.dump(q, open(os.path.join(REPO, "queue.json"), "w"), indent=1)
    used = os.path.join(REPO, "pipeline", "topics_used.json")
    u = json.load(open(used)) if os.path.exists(used) else []
    u.append({"slug": job["slug"], "series": job["series"], "title": job["title"], "publish_at": publish_at})
    json.dump(u, open(used, "w"), indent=1)
    git("add", name, "queue.json", "pipeline/topics_used.json")
    for f in keep:
        git("add", f)
    git("-c", "user.email=coolsvilleaiposting@gmail.com", "-c", "user.name=Coolsville Crossings",
        "commit", "-q", "-m", f"Add {job['slug']} for {publish_at}")
    for attempt in range(4):
        try:
            git("push", "origin", "HEAD:main"); break
        except subprocess.CalledProcessError as e:
            if attempt == 3: raise
            time.sleep(10); git("fetch", "origin", "main"); git("rebase", "origin/main")
    # wait for the raw URL to serve
    url = RAW + name
    for _ in range(20):
        code = subprocess.run(["curl", "-sI", "-o", "/dev/null", "-w", "%{http_code}", url], capture_output=True, text=True).stdout
        if code == "200": break
        time.sleep(6)
    return url, entry

def schedule_zernio(job, url, publish_at):
    ids = zernio_accounts()
    body = {
        "content": caption(job), "title": job["title"],
        "mediaItems": [{"type": "video", "url": url, "mimeType": "video/mp4"}],
        "platforms": [dict({"platform": p, "accountId": ids[p]},
                           # TikTok: no link line (not clickable there, and links feed its spam filter)
                           **({"customContent": f"{job['hook']}\n\n{job['hashtags']}"} if p == "tiktok" else {}))
                      for p in ("tiktok", "instagram") if p in ids],
        # TIKTOK_DRAFT=1 (default): TikTok gets the video in the Creator Inbox and Justin taps Post in the app.
        # Set TIKTOK_DRAFT=0 to go back to direct posting once the account is clear of spam_risk rejections.
        "tiktokSettings": {"draft": os.environ.get("TIKTOK_DRAFT", "1") != "0",
                           "privacy_level": "PUBLIC_TO_EVERYONE", "allow_comment": True, "allow_duet": True,
                           "allow_stitch": True, "content_preview_confirmed": True, "express_consent_given": True,
                           "media_type": "video", "video_made_with_ai": True},
        "scheduledFor": publish_at, "timezone": "America/Chicago",
    }
    r = zernio("POST", "/posts", body)
    p = r.get("post", r)
    if not p.get("_id"):
        raise SystemExit(f"Zernio post failed: {json.dumps(r)[:500]}")
    return p["_id"], p.get("status")

def main(job_path, video, publish_at):
    job = json.load(open(job_path))
    url, entry = commit_video(video, job, publish_at)
    print("pushed", url, "queue id", entry["id"], flush=True)
    pid, status = schedule_zernio(job, url, publish_at)
    print("zernio", pid, status, "for", publish_at, flush=True)

if __name__ == "__main__":
    main(*sys.argv[1:4])
