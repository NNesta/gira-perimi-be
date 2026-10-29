"""Generates the "Umva" audio: every active question (with its answers) and every default explanation, read aloud in
Kinyarwanda by Meta's MMS voice (facebook/mms-tts-kin), as small MP3 files in media/audio/ plus the list the API
serves (app/data/audio.json).

    uv run --with "torch>=2.5" --with "transformers>=4.45" python scripts/audio/generate.py [--limit N]

Needs ffmpeg (MP3 encoding). Clips whose text has not changed are kept, so a rerun only redoes what changed.

LICENCE: the MMS voice is CC BY-NC 4.0 (non-commercial). The manifest records it, and the API stops serving these
clips once PAYWALL_ENABLED is on; replace them with a commercially licensed voice (or real recordings) before charging.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
import torch
from speech_text import phrases, question_script
from transformers import AutoTokenizer, VitsModel

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "app" / "data"
OUT = ROOT / "media" / "audio"
MANIFEST = DATA / "audio.json"
MODEL = "facebook/mms-tts-kin"
BITRATE = "24k"  # mono speech: about 3 KB a second


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class Voice:
    def __init__(self) -> None:
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL)
        self.model = VitsModel.from_pretrained(MODEL).eval()
        self.rate = self.model.config.sampling_rate

    def say(self, text: str, seed: int) -> np.ndarray:
        torch.manual_seed(seed)  # the voice has some randomness: the same text always gives the same clip
        pieces = []
        for words, pause in phrases(text):
            inputs = self.tokenizer(words, return_tensors="pt")
            if inputs["input_ids"].shape[1] == 0:
                continue
            with torch.no_grad():
                wave_out = self.model(**inputs).waveform[0].numpy()
            pieces += [wave_out, np.zeros(int(self.rate * pause), dtype=np.float32)]
        return np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)


def save_mp3(samples: np.ndarray, rate: int, path: Path) -> None:
    peak = float(np.max(np.abs(samples))) or 1.0
    pcm = (samples / peak * 0.9 * 32767).astype(np.int16)
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        with wave.open(tmp.name, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes(pcm.tobytes())
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name, "-ac", "1", "-b:a", BITRATE, str(path)],
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only the first N questions (to listen before a full run)")
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is needed to write MP3 files.")

    bank = json.loads((DATA / "questions.json").read_text())
    questions = [q for q in bank if q["active"] and q["answer"] is not None]
    explanations = json.loads((DATA / "explanations.json").read_text())
    if args.limit:
        questions = questions[: args.limit]
    old = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    manifest = {
        "voice": MODEL,
        "license": "CC-BY-NC-4.0",
        "credit": "Amajwi: Meta MMS (CC BY-NC 4.0)",
        "questions": {},
        "explanations": {},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    voice = Voice()

    jobs = []
    for q in questions:
        jobs.append(("questions", q["id"], f"q{q['id']}.mp3", question_script(q)))
        if text := (explanations.get(str(q["id"]), {}).get("text") or "").strip():
            jobs.append(("explanations", q["id"], f"e{q['id']}.mp3", text))

    if args.limit:  # a trial run keeps the rest of an earlier full run
        manifest["questions"] = dict(old.get("questions", {}))
        manifest["explanations"] = dict(old.get("explanations", {}))

    made = kept = 0
    for i, (kind, qid, name, text) in enumerate(jobs, 1):
        digest = text_hash(text)
        previous = old.get(kind, {}).get(str(qid))
        if previous and previous["file"] == name and previous["hash"] == digest and (OUT / name).exists():
            manifest[kind][str(qid)] = previous
            kept += 1
        else:
            samples = voice.say(text, seed=qid)
            save_mp3(samples, voice.rate, OUT / name)
            manifest[kind][str(qid)] = {"file": name, "hash": digest, "seconds": round(len(samples) / voice.rate, 1)}
            made += 1
        if i % 25 == 0 or i == len(jobs):
            print(f"{i}/{len(jobs)} clips ({made} made, {kept} unchanged)", flush=True)
            MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
