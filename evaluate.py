import os
import glob
import subprocess
import pretty_midi

from basic_pitch.evaluation import score_prediction
from basic_pitch.constants import ANNOTATION_FPS

# -------------------
# 1) CONFIG
# -------------------
AUDIO_FILE_PATH = r"C:\path\to\maestro_audio.wav"
GROUND_TRUTH_MIDI_PATH = r"C:\path\to\maestro_truth.mid"

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(WORK_DIR, "eval_outputs")
os.makedirs(OUT_DIR, exist_ok=True)

# Your Basic Pitch settings (match FastAPI)
ONSET_THRESHOLD = 0.60
MIN_NOTE_DURATION_SEC = 0.22

# Your cleanup settings (match FastAPI)
CLEAN_MIN_DUR = 0.16
CLEAN_MIN_VELOCITY = 28
CLEAN_MERGE_GAP = 0.05
CLEAN_LEGATO_GAP = 0.08
CLEAN_MIN_PITCH = 43   # try 40/43/45
CLEAN_MAX_PITCH = 108


# -------------------
# 2) MIDI CLEANUP (same as your backend)
# -------------------
def clean_midi(
    in_midi_path: str,
    out_midi_path: str,
    min_dur: float = 0.16,
    min_velocity: int = 30,
    merge_gap: float = 0.05,
    min_pitch: int = 40,
    max_pitch: int = 108,
    legato_gap: float = 0.08,
):
    pm = pretty_midi.PrettyMIDI(in_midi_path)

    for inst in pm.instruments:
        notes = [
            n for n in inst.notes
            if (
                min_pitch <= n.pitch <= max_pitch
                and (n.end - n.start) >= min_dur
                and n.velocity >= min_velocity
            )
        ]

        # merge same pitch notes that nearly touch
        notes.sort(key=lambda n: (n.pitch, n.start))
        merged = []
        for n in notes:
            if not merged:
                merged.append(n)
                continue
            prev = merged[-1]
            if n.pitch == prev.pitch and n.start <= prev.end + merge_gap:
                prev.end = max(prev.end, n.end)
                prev.velocity = max(prev.velocity, n.velocity)
            else:
                merged.append(n)

        # legato-gap fill to reduce rests in notation
        merged.sort(key=lambda n: n.start)
        for i in range(len(merged) - 1):
            a = merged[i]
            b = merged[i + 1]
            gap = b.start - a.end
            if 0 < gap <= legato_gap:
                a.end = max(a.end, b.start - 0.005)

        inst.notes = merged

    pm.write(out_midi_path)


# -------------------
# 3) RUN BASIC PITCH (CLI) -> RAW MIDI
# -------------------
print("Running Basic Pitch CLI...")

# Use a stable stem so we can find the output
stem = os.path.splitext(os.path.basename(AUDIO_FILE_PATH))[0]
raw_out_pattern = os.path.join(OUT_DIR, stem + "*.mid")

# Clean up old matches
for old in glob.glob(raw_out_pattern):
    try:
        os.remove(old)
    except:
        pass

command = [
    "basic-pitch",
    OUT_DIR,
    "--onset-threshold", str(ONSET_THRESHOLD),
    "--minimum-note-length", str(MIN_NOTE_DURATION_SEC),
    "--save-midi",
    AUDIO_FILE_PATH,
]

# Windows UTF-8 fix (sparkles print)
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"

subprocess.run(
    command,
    check=True,
    capture_output=True,
    text=True,
    encoding="utf-8",
    env=env,
)

matches = glob.glob(raw_out_pattern)
if not matches:
    raise RuntimeError(f"No MIDI produced. Looked for: {raw_out_pattern}")

raw_midi_path = max(matches, key=os.path.getmtime)
print("Raw MIDI:", raw_midi_path)

# -------------------
# 4) CLEAN MIDI (your pipeline)
# -------------------
cleaned_midi_path = os.path.join(OUT_DIR, stem + "_clean.mid")

clean_midi(
    raw_midi_path,
    cleaned_midi_path,
    min_dur=CLEAN_MIN_DUR,
    min_velocity=CLEAN_MIN_VELOCITY,
    merge_gap=CLEAN_MERGE_GAP,
    min_pitch=CLEAN_MIN_PITCH,
    max_pitch=CLEAN_MAX_PITCH,
    legato_gap=CLEAN_LEGATO_GAP,
)

print("Cleaned MIDI:", cleaned_midi_path)

# -------------------
# 5) EVALUATE (F1)
# -------------------
print("Running evaluation...")

MIN_NOTE_LEN_FRAMES = int(MIN_NOTE_DURATION_SEC * ANNOTATION_FPS)

results = score_prediction(
    GROUND_TRUTH_MIDI_PATH,
    cleaned_midi_path,      # evaluate your cleaned output
    min_length=MIN_NOTE_LEN_FRAMES,
    onset_threshold=ONSET_THRESHOLD,
)

metric = results["metric_notes"]
print("\n--- F1-SCORE RESULTS (Note-level) ---")
print(f"Precision: {metric['precision']:.4f}")
print(f"Recall:    {metric['recall']:.4f}")
print(f"F1:        {metric['f1']:.4f}")
print("-------------------------------------")
