"""Build one Coolsville Crossings video from a job JSON.

Job file fields:
  slug, series, accent, deep, script, footage (file in ../footage), footage_offset (seconds)

Output: <out_dir>/<slug>.mp4 and <out_dir>/<slug>.timing.json
Narration: Chatterbox TTS cloned from voice_ref.wav, one sentence at a time, each take
transcribed with faster-whisper and kept only if it matches the script (best of up to 3).
"""
import json, os, re, subprocess, sys, textwrap, difflib, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FONT = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"
FONT_MED = "/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf"
W, H, FPS = 1080, 1920, 30
GAP = 0.28            # silence between sentences
MIN_MATCH = 0.80      # whisper vs script similarity to accept a take
MAX_TAKES = 3
MUSIC_GAIN = 0.16     # music bed level under the voice (voice is -14 LUFS; this sits roughly 20 dB under)

def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)

def sentences(text):
    text = re.sub(r'\b([A-Z]|Bros|Mr|Mrs|Dr|vs|St)\.\s', lambda m: m.group(1) + '․ ', text.strip())
    parts = [p.replace('․', '.') for p in re.split(r'(?<=[.?!])\s+', text)]
    return [p for p in parts if p.strip()]

def norm(s):
    s = s.lower().replace("'", "")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(s.split())

def similarity(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()

def load_audio_16k(path):
    b = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                       capture_output=True, check=True).stdout
    return np.frombuffer(b, dtype=np.float32)

def duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", path]).decode().strip().splitlines()[-1]
    return float(out)

_tts = None
_asr = None
def tts_model():
    global _tts
    if _tts is None:
        from chatterbox.tts import ChatterboxTTS
        log("loading Chatterbox")
        _tts = ChatterboxTTS.from_pretrained(device="cpu")
    return _tts

def asr_model():
    global _asr
    if _asr is None:
        from faster_whisper import WhisperModel
        _asr = WhisperModel("small", device="cpu", compute_type="int8")
    return _asr

def transcribe(path):
    """Return (text, [(start, end, word), ...]) with word timestamps."""
    segs, _ = asr_model().transcribe(load_audio_16k(path), beam_size=3, word_timestamps=True)
    words, text = [], []
    for sg in segs:
        text.append(sg.text)
        for w in (sg.words or []):
            words.append((w.start, w.end, w.word.strip()))
    return " ".join(text).strip(), words

def narrate(sents, work, ref):
    """Generate each sentence; return list of (wav_path, dur, transcript, score)."""
    import torchaudio
    m = tts_model()
    out = []
    for i, s in enumerate(sents):
        best = None
        for take in range(MAX_TAKES):
            p = f"{work}/s{i:02d}_t{take}.wav"
            wav = m.generate(s, audio_prompt_path=ref, exaggeration=0.5, cfg_weight=0.5)
            torchaudio.save(p, wav, m.sr)
            tr, words = transcribe(p)
            sc = similarity(s, tr)
            log(f"  s{i:02d} take{take} score={sc:.2f} | {tr[:70]}")
            if best is None or sc > best[3]:
                best = (p, duration(p), tr, sc, words)
            if sc >= MIN_MATCH:
                break
        if best[3] < MIN_MATCH:
            log(f"  WARNING sentence {i} best score {best[3]:.2f} below {MIN_MATCH}; keeping best take")
        out.append(best)
    return out

def lead_silence(path):
    out = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-af", "silencedetect=noise=-45dB:d=0.05", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"silence_start: (-?[0-9.]+)\s*\n.*?silence_end: ([0-9.]+)", out, re.S)
    if m and float(m.group(1)) <= 0.01:
        return float(m.group(2)) - 0.05
    return 0.0

def assemble_narration(takes, work):
    """Trim silence from each take, join with gaps, loudness normalise. Returns (wav, timings)."""
    parts, timings, t = [], [], 0.0
    for i, (p, d, tr, sc, words) in enumerate(takes):
        q = f"{work}/c{i:02d}.wav"
        lead = lead_silence(p)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", p, "-af",
                        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
                        "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse",
                        q], check=True)
        d = duration(q)
        parts.append(q)
        wl = [(round(max(0, a - lead) + t, 3), round(min(d, b - lead) + t, 3), w) for a, b, w in words]
        timings.append({"start": round(t, 3), "end": round(t + d, 3), "words": wl})
        t += d + GAP
    lst = f"{work}/concat.txt"
    with open(lst, "w") as f:
        for i, q in enumerate(parts):
            f.write(f"file '{q}'\n")
            if i < len(parts) - 1:
                f.write(f"file '{work}/gap.wav'\n")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono", "-t", str(GAP), f"{work}/gap.wav"], check=True)
    raw = f"{work}/narration_raw.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, raw], check=True)
    wav = f"{work}/narration.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", "highpass=f=80,loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-ar", "48000", "-ac", "2", wav], check=True)
    return wav, timings

def ass_time(x):
    h = int(x // 3600); m = int(x % 3600 // 60); sec = x % 60
    return f"{h}:{m:02d}:{sec:05.2f}"

def script_words_timed(sent, tm):
    """Pair the script's own words with whisper's timings (so captions show the script, not the transcript)."""
    sw = sent.split()
    ww = tm["words"]
    if not ww:
        return []
    if len(ww) == len(sw):
        return [(a, b, w) for (a, b, _), w in zip(ww, sw)]
    t0, t1 = ww[0][0], ww[-1][1]
    n = len(sw); span = max(t1 - t0, 0.5)
    out = []
    for i, w in enumerate(sw):
        a = t0 + span * i / n; b = t0 + span * (i + 1) / n
        out.append((round(a, 3), round(b, 3), w))
    return out

def write_captions(sents, timings, path, accent):
    """Karaoke-style captions: 3 to 4 words per line, spoken word highlighted in the accent color."""
    acc = accent.lstrip("#"); acc_bgr = acc[4:6] + acc[2:4] + acc[0:2]
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
             f"Style: Cap,Poppins,80,&H00FFFFFF,&H00{acc_bgr},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,3,5,60,60,0,1",
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    events = []
    for sent, tm in zip(sents, timings):
        words = script_words_timed(sent, tm)
        if not words:
            events.append([tm['start'], tm['end'], sent])
            continue
        chunk = []
        for i, w in enumerate(words):
            chunk.append(w)
            if len(chunk) == 4 or i == len(words) - 1 or w[2].endswith((",", ".", "?", "!")) and len(chunk) >= 2:
                start, end = chunk[0][0], chunk[-1][1]
                parts = []
                for j, (a, b, txt) in enumerate(chunk):
                    nxt = chunk[j + 1][0] if j + 1 < len(chunk) else end
                    cs = max(1, int(round((nxt - a) * 100)))
                    parts.append(f"{{\\k{cs}}}{txt}")
                events.append([start, end + 0.05, ' '.join(parts)])
                chunk = []
    # never let one caption line overlap the next (ASS would stack them)
    for k in range(len(events) - 1):
        events[k][1] = min(events[k][1], events[k + 1][0] - 0.01)
    for a, b, txt in events:
        lines.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Cap,,0,0,0,,{txt}")
    open(path, "w").write("\n".join(lines))

def esc(s):
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")

def build_video(job, sents, timings, wav, work, out):
    accent, deep, header = job["accent"], job.get("deep", "#07080f"), job["series"]
    D = duration(wav)
    total = D + 0.6
    clip = os.path.join(REPO, "footage", job["footage"])
    off = job.get("footage_offset", 0)
    cd = duration(clip)
    loop = ["-stream_loop", "-1"] if cd - off < total + 1 else []
    steps = [
        f"drawtext=fontfile={FONT}:text='COOLSVILLE CROSSINGS':fontsize=34:fontcolor={accent}:x=(w-text_w)/2:y=170",
        f"drawtext=fontfile={FONT_MED}:text='{esc(header)}':fontsize=44:fontcolor=white@0.85:x=(w-text_w)/2:y=222",
        f"drawbox=x=(iw-160)/2:y=292:w=160:h=4:color={accent}:t=fill",
    ]
    ass = f"{work}/captions.ass"
    write_captions(sents, timings, ass, accent)
    steps.append(f"drawbox=x=0:y=ih-14:w=iw*min(t/{D:.3f}\\,1):h=14:color={accent}:t=fill")
    steps.append(f"drawtext=fontfile={FONT_MED}:text='follow for more gaming history':fontsize=30:fontcolor=white@0.55:x=(w-text_w)/2:y=h-130")
    music = os.path.join(REPO, "footage", "music_bed.m4a")
    fc = (f"[0:v]fps={FPS},eq=brightness=-0.05:saturation=1.1,vignette=PI/4.5,"
          f"drawbox=x=0:y=ih/2-330:w=iw:h=600:color=black@0.38:t=fill," + ",".join(steps) +
          f",subtitles={ass}:fontsdir=/usr/share/fonts/truetype/google-fonts[v];"
          f"[2:a]volume={MUSIC_GAIN},afade=t=out:st={total - 1.2:.2f}:d=1.2[m];"
          f"[1:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
    cmd = ["ffmpeg", "-y", "-v", "error", *loop, "-ss", str(off), "-t", f"{total + 1:.2f}", "-i", clip, "-i", wav,
           "-stream_loop", "-1", "-i", music,
           "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
           "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", f"{total:.2f}",
           "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    return D

def main(job_path, out_dir):
    job = json.load(open(job_path))
    slug = job["slug"]
    work = f"/tmp/claude-0/cc_{slug}"
    os.makedirs(work, exist_ok=True); os.makedirs(out_dir, exist_ok=True)
    sents = sentences(job["script"])
    # job "voice": "justin" (default) or "leigh"; an explicit "voice_ref" file wins
    VOICES = {"justin": "voice_ref.wav", "leigh": "voice_ref_leigh.wav"}
    ref = os.path.join(HERE, job.get("voice_ref") or VOICES[job.get("voice", "justin").lower()])
    log(f"{slug}: {len(sents)} sentences, {len(job['script'].split())} words")
    takes = narrate(sents, work, ref)
    wav, timings = assemble_narration(takes, work)
    out = os.path.join(out_dir, f"{slug}.mp4")
    D = build_video(job, sents, timings, wav, work, out)
    report = {"slug": slug, "duration": round(D, 1), "sentences": [
        {"text": s, "transcript": t[2], "score": round(t[3], 2), "start": tm["start"], "end": tm["end"]} for s, t, tm in zip(sents, takes, timings)]}
    json.dump(report, open(os.path.join(out_dir, f"{slug}.timing.json"), "w"), indent=1)
    worst = min(x["score"] for x in report["sentences"])
    log(f"done {out} {D:.1f}s worst sentence score {worst:.2f}")
    if D < 60:
        log(f"WARNING narration is {D:.1f}s, under the 60s target")
    return out, D, worst

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "/tmp/claude-0/cc_out")
