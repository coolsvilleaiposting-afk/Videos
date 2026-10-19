"""Synthesize the royalty-free background bed used under the narration (no external assets).
Writes footage/music_bed.m4a: 21 s loopable lo-fi synth pad with a soft kick and hat at 92 BPM."""
import numpy as np, subprocess, os, sys

SR = 44100
BPM = 92
BEAT = 60 / BPM
BAR = 4 * BEAT
# Am  F  C  G  (two bars each) -> 8 bars, loops cleanly
CHORDS = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]
PROG = [c for c in CHORDS for _ in range(2)]

def f(m): return 440 * 2 ** ((m - 69) / 12)

def pad(midi, dur):
    t = np.arange(int(dur * SR)) / SR
    out = np.zeros_like(t)
    for m in midi:
        for k, a in ((1, 1.0), (2, 0.35), (3, 0.12)):
            det = 1 + 0.0012 * np.sin(2 * np.pi * 0.13 * t + m)
            out += a * np.sin(2 * np.pi * f(m) * k * det * t)
        out += 0.5 * np.sin(2 * np.pi * f(m - 12) * t)  # sub octave
    env = np.minimum(1, t / 0.6) * np.minimum(1, (dur - t) / 0.8)
    return out * env / (len(midi) * 2.2)

def kick(dur):
    t = np.arange(int(dur * SR)) / SR
    return np.sin(2 * np.pi * (55 + 80 * np.exp(-t * 30)) * t) * np.exp(-t * 9)

def hat(dur):
    n = np.random.default_rng(1).standard_normal(int(dur * SR))
    t = np.arange(len(n)) / SR
    return n * np.exp(-t * 60) * 0.25

def main(out):
    total = len(PROG) * BAR
    y = np.zeros(int(total * SR))
    pos = 0
    for ch in PROG:
        seg = pad(ch, BAR); y[pos:pos + len(seg)] += seg; pos += len(seg)
    nb = int(total / BEAT)
    for b in range(nb):
        s = int(b * BEAT * SR)
        if b % 2 == 0:
            k = kick(0.4); y[s:s + len(k)] += 0.9 * k
        for half in (0, 0.5):
            hs = int((b + half) * BEAT * SR)
            h = hat(0.08); y[hs:hs + len(h)] += 0.5 * h
    y = y / np.max(np.abs(y)) * 0.8
    raw = "/tmp/claude-0/music_raw.wav"
    import wave
    with wave.open(raw, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((y * 32767).astype(np.int16).tobytes())
    # low-pass for a mellow lo-fi tone, light reverb-ish echo, stereo widen
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af",
                    "lowpass=f=2400,aecho=0.7:0.5:60:0.18,stereotools=slev=1:mlev=1,loudnorm=I=-20:TP=-3",
                    "-ac", "2", out], check=True)
    print("wrote", out, f"{total:.1f}s")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "footage", "music_bed.m4a"))
