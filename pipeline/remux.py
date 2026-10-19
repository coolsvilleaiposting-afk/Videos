"""Rebuild an old narrated video over new footage: keeps its audio, re-times captions from whisper."""
import sys, os, json, subprocess
sys.path.insert(0, "/home/claude/videos/pipeline")
import make_video as mv
src, job_path, out = sys.argv[1:4]
job = json.load(open(job_path))
work = f"/tmp/claude-0/remux/{job['slug']}"; os.makedirs(work, exist_ok=True)
wav = os.path.join(work, "narration.wav")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "24000",
                "-af", "loudnorm=I=-14:TP=-1.5", wav], check=True)
text, words = mv.transcribe(wav)
fixes = job.get("fixes", {})          # "heard" -> "correct"; "a+b" merges two heard tokens into one
out_w = []; i = 0
while i < len(words):
    a, b, w = words[i]
    if i + 1 < len(words) and (w.strip() + "+" + words[i + 1][2].strip()) in fixes:
        key = w.strip() + "+" + words[i + 1][2].strip()
        out_w.append((a, words[i + 1][1], fixes[key])); i += 2; continue
    out_w.append((a, b, fixes.get(w.strip(), w.strip()))); i += 1
words = out_w
sents, timings, cur = [], [], []
for t in words:
    cur.append(t)
    if t[2].endswith((".", "?", "!")) or t is words[-1]:
        sents.append(" ".join(w for _, _, w in cur))
        timings.append({"start": cur[0][0], "end": cur[-1][1], "words": cur}); cur = []
print("transcript:", " | ".join(sents))
D = mv.build_video(job, sents, timings, wav, work, out)
print("built", out, D)
