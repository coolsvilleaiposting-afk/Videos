"""Performance loop: pull every published post's numbers from Zernio (TikTok + Instagram),
group them by game series, and turn that into topic weights for the next day's videos.

  ZERNIO_API_KEY=sk_... python3 pipeline/analytics.py

Writes pipeline/analytics.json (per-post stats, per-series summary, weights, picked-up lessons)
and prints a short report. The daily task reads the weights when choosing topics:
roughly 2 of the 3 daily slots go to the strongest series, 1 slot keeps testing the rest
so a series that is down on a small sample still gets another look.
"""
import json, os, re, subprocess, sys, statistics as st
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ZBASE = "https://zernio.com/api/v1"
OUT = os.path.join(HERE, "analytics.json")

SERIES = {
    "WoW":            ["#wow", "#worldofwarcraft", "warcraft", "blizzard", "azeroth"],
    "OSRS":           ["#osrs", "#runescape", "#oldschoolrunescape", "runescape", "jagex"],
    "Final Fantasy":  ["#finalfantasy", "#ff7", "#ffxiv", "final fantasy", "ffxiv"],
    "Kingdom Hearts": ["#kingdomhearts", "#keyblade", "#sora", "kingdom hearts", "keyblade"],
    "Zelda":          ["#zelda", "#legendofzelda", "#ocarinaoftime", "zelda", "hyrule"],
    "Fire Emblem":    ["#fireemblem", "fire emblem"],
    "Resident Evil":  ["#residentevil", "#biohazard", "resident evil", "biohazard"],
}
MIN_POSTS_TO_TRUST = 2   # below this a series keeps a neutral weight

def zernio(path):
    key = os.environ["ZERNIO_API_KEY"]
    out = subprocess.run(["curl", "-sS", "-m", "90", "--retry", "3", "--retry-all-errors", ZBASE + path,
                          "-H", f"Authorization: Bearer {key}"], capture_output=True, text=True).stdout
    return json.loads(out)

def series_of(text):
    t = text.lower()
    hits = {s: sum(k in t for k in keys) for s, keys in SERIES.items()}
    best = max(hits, key=hits.get)
    return best if hits[best] else "Other"

def collect():
    posts, page = [], 1
    while True:
        d = zernio(f"/analytics?page={page}&limit=50")
        posts += d.get("posts", [])
        pg = d.get("pagination", {})
        if page >= pg.get("pages", 1): break
        page += 1
    rows = []
    for p in posts:
        if p.get("status") != "published": continue
        s = series_of(p.get("content", ""))
        for pl in p.get("platforms", []):
            a = pl.get("analytics") or {}
            if not a or pl.get("status") != "published": continue
            rows.append({
                "post_id": p["_id"], "platform": pl["platform"], "series": s,
                "published": (p.get("publishedAt") or "")[:10],
                "hook": p.get("content", "").split("\n")[0][:90],
                "views": a.get("views") or 0, "likes": a.get("likes") or 0,
                "comments": a.get("comments") or 0, "shares": a.get("shares") or 0,
                "saves": a.get("saves") or 0, "follows": a.get("follows") or 0,
                "completion": a.get("completionRate") or 0,
                "avg_watch_ms": a.get("igReelsAvgWatchTime") or 0,
                "engagement_rate": a.get("engagementRate") or 0,
            })
    accounts = {a["platform"]: a.get("followersCount") for a in d.get("accounts", [])}
    return rows, accounts

def summarize(rows):
    # TikTok is the platform with real reach so far; Instagram is tracked but weighted lightly.
    weight_platform = {"tiktok": 1.0, "instagram": 0.4}
    per = {}
    for r in rows:
        per.setdefault(r["series"], []).append(r)
    summary = {}
    for s, rs in per.items():
        tt = [r for r in rs if r["platform"] == "tiktok"]
        base = tt or rs
        views = [r["views"] for r in base]
        eng = [(r["likes"] + 2 * r["comments"] + 3 * r["shares"] + 2 * r["saves"] + 5 * r["follows"]) / max(r["views"], 1) for r in base]
        summary[s] = {
            "posts": len(base), "median_views": int(st.median(views)), "mean_views": int(st.mean(views)),
            "engagement_per_view": round(st.mean(eng), 4),
            "avg_watch_s": round(st.mean([r["avg_watch_ms"] for r in base]) / 1000, 1),
            "follows": sum(r["follows"] for r in base),
            "ig_median_views": int(st.median([r["views"] for r in rs if r["platform"] == "instagram"] or [0])),
        }
    # score = views relative to channel median, nudged by engagement and watch time
    all_views = [r["views"] for r in rows if r["platform"] == "tiktok"] or [1]
    chan_med = max(st.median(all_views), 1)
    weights = {}
    for s in SERIES:
        if s not in summary or summary[s]["posts"] < MIN_POSTS_TO_TRUST:
            weights[s] = 1.0; continue
        m = summary[s]
        score = (m["median_views"] / chan_med) * (1 + 4 * m["engagement_per_view"]) * (1 + m["avg_watch_s"] / 20)
        weights[s] = round(min(max(score, 0.4), 3.0), 2)
    total = sum(weights.values())
    share = {s: round(w / total, 3) for s, w in weights.items()}
    return summary, weights, share, chan_med

def lessons(rows, summary, share):
    out = []
    ranked = sorted(share.items(), key=lambda kv: -kv[1])
    out.append("Series ranked by weight: " + ", ".join(f"{s} {w:.0%}" for s, w in ranked))
    top = [r for r in rows if r["platform"] == "tiktok"]
    top.sort(key=lambda r: -r["views"])
    if top:
        out.append("Top hooks: " + " | ".join(f"{r['views']}v {r['hook']}" for r in top[:3]))
        out.append("Weakest hooks: " + " | ".join(f"{r['views']}v {r['hook']}" for r in top[-3:]))
    hi = [r for r in top if r["completion"] >= 0.07]
    if hi: out.append("Best completion: " + " | ".join(f"{r['completion']:.0%} {r['hook'][:50]}" for r in hi[:3]))
    return out

def main():
    rows, accounts = collect()
    summary, weights, share, chan_med = summarize(rows)
    notes = lessons(rows, summary, share)
    json.dump({"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "followers": accounts,
               "channel_median_tiktok_views": chan_med, "series": summary, "weights": weights, "share": share,
               "lessons": notes, "posts": rows}, open(OUT, "w"), indent=1)
    print(f"{len(rows)} platform-posts, followers {accounts}, TikTok median views {chan_med:.0f}")
    for s in sorted(summary, key=lambda s: -weights.get(s, 1)):
        m = summary[s]
        print(f"  {s:15} n={m['posts']} med={m['median_views']:5} eng={m['engagement_per_view']:.3f} watch={m['avg_watch_s']:4}s  weight={weights.get(s,1)}  share={share.get(s,0):.0%}")
    for n in notes: print("-", n)

if __name__ == "__main__":
    main()
