# Coolsville Crossings pipeline

footage/            Justin's own gameplay, pre-cropped to 1080x1920, no audio
                    wow_1..3.mp4 = WoW raid footage (use for WoW topics); fortnite_1..3, league_1 = generic
pipeline/voice_ref.wav (Justin) and voice_ref_leigh.wav (Leigh): Chatterbox clone references; job "voice": "justin"|"leigh"
pipeline/voice_ref*.wav   20 s of Justin's voice used as the Chatterbox clone reference
pipeline/make_video.py    job JSON -> mp4 (Chatterbox narration per sentence, whisper-verified, ffmpeg build)
pipeline/publish.py       mp4 -> commit + queue.json (YouTube Apps Script) + Zernio (TikTok, Instagram)
pipeline/jobs/            one JSON per video; pipeline/topics_used.json is the ledger of what has posted
pipeline/make_music.py    regenerates footage/music_bed.m4a (synthesized in numpy, no licensing to worry about)
pipeline/analytics.py     pulls Zernio post stats, writes pipeline/analytics.json + prints series weights

Every build gets word-by-word highlight captions (ASS karaoke from the script words with whisper timings)
and the music bed mixed at MUSIC_GAIN (0.16, about 19 dB under the voice). Change MUSIC_GAIN in make_video.py
if the music ever competes with the narration.

Setup on a fresh machine:
  pip install chatterbox-tts faster-whisper
  (faster-whisper's bundled av is too new; make_video.py feeds it audio via ffmpeg instead)

Run:
  python3 pipeline/make_video.py pipeline/jobs/<slug>.json /tmp/out
  ZERNIO_API_KEY=... python3 pipeline/publish.py pipeline/jobs/<slug>.json /tmp/out/<slug>.mp4 2026-10-20T10:00:00-05:00

Rules: scripts run 60 s or more spoken; caption = hook + question, blank line, linktree line, blank line, hashtags;
posts at 10 AM, 2 PM and 6 PM Central; only Justin's own footage; topic wells WoW, OSRS, Final Fantasy,
Kingdom Hearts, Zelda, Fire Emblem, Resident Evil (ask Justin before adding a series).
