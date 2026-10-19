#!/bin/bash
# Renders spoiler-free Shards of Irsa gameplay and turns it into vertical channel footage.
#   pipeline/irsa_footage.sh <path to Shards-of-Irsa/godot> <godot binary>
# Needs xvfb-run and Mesa (GL Compatibility renderer). About 4 minutes of render per segment.
# Writes footage/irsa_1.mp4 .. irsa_3.mp4 (1080x1920, silent, "Gameplay: Shards of Irsa" credit baked in).
set -e
GAME=${1:?game godot folder}; GODOT=${2:?godot binary}
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(dirname "$HERE"); OUT=/tmp/claude-0/irsa
mkdir -p "$OUT"
cp "$HERE/irsa_reel.gd" "$GAME/tests/zz_social_reel.gd"
for i in 0 1 2 3 4; do
  [ -s "$OUT/seg$i.avi" ] && continue
  (cd "$GAME" && timeout 1500 xvfb-run -a -s "-screen 0 1920x1440x24" "$GODOT" --rendering-driver opengl3 \
    --audio-driver Dummy --resolution 1440x1056 --write-movie "$OUT/seg$i.avi" --fixed-fps 30 --path . \
    -- level=village stage=27 skip testnode=res://tests/zz_social_reel.gd seg=$i > "$OUT/seg$i.log" 2>&1)
  grep -E "REEL|frames at" "$OUT/seg$i.log"
done
rm -f "$GAME/tests/zz_social_reel.gd" "$GAME/tests/zz_social_reel.gd.uid"

FONT=/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf
# landscape game frame centered over a blurred, darkened fill of itself; game credit near the bottom
VF="split[a][b];[a]scale=-2:1920,crop=1080:1920,boxblur=24:2,eq=brightness=-0.18[bg];\
[b]scale=1080:-2:flags=lanczos[fg];[bg][fg]overlay=0:(H-h)/2,\
drawtext=fontfile=$FONT:text='Gameplay\: Shards of Irsa (in development)':fontsize=34:fontcolor=white@0.85:\
borderw=3:bordercolor=black@0.7:x=(w-text_w)/2:y=h-250,fps=30,format=yuv420p"
make() {  # make <name> <seg> <seg>
  # inpoint 3: skip the first seconds, before the reel hides the quest panel
  printf "file '%s'\ninpoint 3\nfile '%s'\ninpoint 3\n" "$OUT/seg$2.avi" "$OUT/seg$3.avi" > "$OUT/$1.txt"
  ffmpeg -y -v error -f concat -safe 0 -i "$OUT/$1.txt" -an -vf "$VF" -c:v libx264 -preset medium -crf 24 \
    -movflags +faststart "$REPO/footage/$1.mp4"
  echo "$1 $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$REPO/footage/$1.mp4")s"
}
make irsa_1 0 4   # woods + dungeon
make irsa_2 1 2   # frost + coast
make irsa_3 3 1   # barrens + frost
