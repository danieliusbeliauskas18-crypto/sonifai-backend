from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import uuid
from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH

app = FastAPI()

# Allow frontend (and for now, everything) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later you can restrict to your Vercel domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base directory of this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Folders for uploads and outputs
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

# Make sure folders exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    # Unique filenames
    input_filename = f"{uuid.uuid4()}.wav"
    output_filename = f"{uuid.uuid4()}.mid"

    input_path = os.path.join(UPLOAD_DIR, input_filename)
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    # Save uploaded file
    with open(input_path, "wb") as f:
        f.write(await audio.read())

    # Run Basic Pitch
    model_output, midi_data, note_events = predict(
        input_path,
        ICASSP_2022_MODEL_PATH
    )

    # Save MIDI
    midi_data.write(output_path)

    # Return MIDI file
    return FileResponse(
        output_path,
        media_type="audio/midi",
        filename="output.mid"
    )
