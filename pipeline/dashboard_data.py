"""Turns pipeline/analytics.json into the three files the Coolsville Crossings Stats dashboard reads.

  python3 pipeline/dashboard_data.py <out_dir>

Writes posts.json (one row per platform post), series.json (one row per game series) and
followers.json (one row per platform). The daily task uploads them to the dashboard each morning.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube"}


def main(out):
    a = json.load(open(os.path.join(HERE, "analytics.json")))
    os.makedirs(out, exist_ok=True)
    posts = []
    for p in a["posts"]:
        if not p.get("published"):
            continue
        posts.append({
            "post_id": f"{p['platform']}:{p['post_id']}",
            "published": p["published"][:10],
            "platform": PLATFORM.get(p["platform"], p["platform"]),
            "series": p["series"],
            "hook": (p.get("hook") or "").strip() or "(caption not synced)",
            "views": int(p.get("views") or 0),
            "likes": int(p.get("likes") or 0),
            "comments": int(p.get("comments") or 0),
            "shares": int(p.get("shares") or 0),
            "follows": int(p.get("follows") or 0),
            "avg_watch_s": round((p.get("avg_watch_ms") or 0) / 1000, 1),
        })
    posts.sort(key=lambda r: (r["published"], r["platform"]), reverse=True)
    series = []
    for s, m in a["series"].items():
        if s == "Other":
            continue
        series.append({
            "series": s,
            "share": a["share"].get(s, 0),
            "tiktok_posts": m["posts"],
            "tiktok_median_views": m["median_views"],
            "instagram_median_views": m["ig_median_views"],
            "youtube_median_views": m.get("yt_median_views", 0),
            "avg_watch_s": m["avg_watch_s"],
        })
    series.sort(key=lambda r: -r["share"])
    followers = [{"platform": PLATFORM.get(k, k), "followers": v or 0, "as_of": a["generated"][:10]}
                 for k, v in (a.get("followers") or {}).items()]
    for name, rows in (("posts", posts), ("series", series), ("followers", followers)):
        json.dump(rows, open(os.path.join(out, f"{name}.json"), "w"), indent=1)
    print(f"posts {len(posts)}, series {len(series)}, followers {followers}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/dash")
