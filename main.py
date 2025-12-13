from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import uuid
import subprocess
import glob

import librosa
import numpy as np
import soundfile as sf
import pretty_midi


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- BASIC PITCH PARAMS (clean piano defaults) ---
ONSET_THRESHOLD = 0.60
MIN_NOTE_DURATION = 0.22

# --- AUDIO GATE (removes quiet noise) ---
RMS_THRESHOLD = 0.02  # try 0.01–0.04

# --- MIDI CLEANUP (removes jitter + junk) ---
CLEAN_MIN_DUR = 0.16       # seconds
CLEAN_MIN_VELOCITY = 28    # 0–127
CLEAN_MERGE_GAP = 0.05     # seconds
CLEAN_LEGATO_GAP = 0.08    # seconds (reduces rests in notation)

# 🔥 KEY SETTING: remove low-octave ghost notes
# try 40 (E2), 43 (G2), 45 (A2)
CLEAN_MIN_PITCH = 43       # <--- bumping this up usually kills the rumble notes
CLEAN_MAX_PITCH = 80    # Default - 108




def apply_loudness_gate(input_wav: str, output_wav: str, rms_threshold: float):
    y, sr = librosa.load(input_wav, sr=None, mono=True)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    rms_expanded = np.repeat(rms, 512)[: len(y)]
    y_gated = np.where(rms_expanded >= rms_threshold, y, 0.0)
    sf.write(output_wav, y_gated, sr)


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
        # 1) hard filter: pitch range + duration + velocity
        notes = [
            n for n in inst.notes
            if (
                min_pitch <= n.pitch <= max_pitch
                and (n.end - n.start) >= min_dur
                and n.velocity >= min_velocity
            )
        ]

        # 2) merge same pitch notes that nearly touch
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

        # 3) legato-gap fill to reduce rests in notation (no overlaps)
        merged.sort(key=lambda n: n.start)
        for i in range(len(merged) - 1):
            a = merged[i]
            b = merged[i + 1]
            gap = b.start - a.end
            if 0 < gap <= legato_gap:
                a.end = max(a.end, b.start - 0.005)

        inst.notes = merged

    pm.write(out_midi_path)


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    input_filename = f"{uuid.uuid4()}_{audio.filename}"
    input_path = os.path.join(UPLOAD_DIR, input_filename)

    gated_path = os.path.splitext(input_path)[0] + "_gated.wav"

    midi_path = None
    cleaned_path = None

    try:
        with open(input_path, "wb") as f:
            f.write(await audio.read())

        apply_loudness_gate(input_path, gated_path, RMS_THRESHOLD)

        command = [
            "basic-pitch",
            OUTPUT_DIR,
            "--onset-threshold", str(ONSET_THRESHOLD),
            "--minimum-note-length", str(MIN_NOTE_DURATION),
            "--save-midi",
            gated_path,
        ]

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )

        stem = os.path.splitext(os.path.basename(gated_path))[0]
        matches = glob.glob(os.path.join(OUTPUT_DIR, stem + "*.mid"))

        if not matches:
            return {
                "error": "No MIDI file produced by Basic Pitch.",
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        midi_path = max(matches, key=os.path.getmtime)

        cleaned_path = os.path.splitext(midi_path)[0] + "_clean.mid"
        clean_midi(
            midi_path,
            cleaned_path,
            min_dur=CLEAN_MIN_DUR,
            min_velocity=CLEAN_MIN_VELOCITY,
            merge_gap=CLEAN_MERGE_GAP,
            min_pitch=CLEAN_MIN_PITCH,       # ✅ important change
            max_pitch=CLEAN_MAX_PITCH,
            legato_gap=CLEAN_LEGATO_GAP,
        )

        return FileResponse(
            cleaned_path,
            media_type="audio/midi",
            filename="transcribed_clean.mid",
        )

    except subprocess.CalledProcessError as e:
        return {
            "error": "Basic Pitch failed (CLI error).",
            "stdout": e.stdout,
            "stderr": e.stderr,
        }

    except Exception as e:
        return {"error": str(e)}

    finally:
        for p in [input_path, gated_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass
