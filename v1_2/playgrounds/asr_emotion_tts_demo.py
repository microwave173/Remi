import argparse
import base64
import binascii
import json
import os
import subprocess
import threading
import wave
from datetime import datetime
from pathlib import Path

import numpy as np
import requests
import sounddevice as sd
from openai import OpenAI
from pynput import keyboard


PROJECT_ROOT = Path("/Users/mabokai/Desktop/proj/Remi")
OUT_DIR = PROJECT_ROOT / "v1_1" / "playgrounds" / "audio_outputs"

QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_ASR_MODEL = os.getenv("QWEN_ASR_MODEL", "qwen3-asr-flash")
QWEN_API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")

MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")

TTS_EMOTIONS = [
    "happy",
    "sad",
    "angry",
    "fearful",
    "disgusted",
    "surprised",
    "calm",
    "fluent",
    "whisper",
]


def build_qwen_client() -> OpenAI:
    if not QWEN_API_KEY:
        raise ValueError("Missing Qwen key. Set DASHSCOPE_API_KEY (or OPENAI_API_KEY).")
    return OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)


def save_wav(path: Path, data: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16
        wf.setframerate(sample_rate)
        wf.writeframes(data.tobytes())


def record_while_holding_space(sample_rate: int = 16000) -> Path:
    print("\n[Step1] Hold SPACE to record. Release SPACE to stop.")
    print("If first run on macOS, grant microphone + accessibility permissions.")

    chunks: list[np.ndarray] = []
    is_recording = False
    lock = threading.Lock()
    finished = threading.Event()

    def audio_callback(indata, frames, time_info, status):  # noqa: ARG001
        if status:
            print(f"[audio status] {status}")
        with lock:
            if is_recording:
                chunks.append(indata.copy())

    def on_press(key):
        nonlocal is_recording
        if key == keyboard.Key.space:
            with lock:
                if not is_recording:
                    is_recording = True
                    print("Recording...")

    def on_release(key):
        nonlocal is_recording
        if key == keyboard.Key.space:
            with lock:
                if is_recording:
                    is_recording = False
                    print("Stopped.")
                    finished.set()
                    return False
        return None

    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        callback=audio_callback,
        blocksize=0,
    ):
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    if not chunks:
        raise RuntimeError("No audio captured. Please hold SPACE while speaking, then release.")

    audio = np.concatenate(chunks, axis=0).reshape(-1)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    wav_path = OUT_DIR / f"record_{ts}.wav"
    save_wav(wav_path, audio, sample_rate=sample_rate)
    print(f"Saved audio: {wav_path}")
    return wav_path


def qwen_asr_with_emotion(client: OpenAI, wav_path: Path) -> tuple[str, str | None, dict]:
    audio_b64 = base64.b64encode(wav_path.read_bytes()).decode("utf-8")
    data_url = f"data:audio/wav;base64,{audio_b64}"

    resp = client.chat.completions.create(
        model=QWEN_ASR_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": data_url},
                    }
                ],
            }
        ],
        stream=False,
        extra_body={"enable_thinking": False},
    )

    msg = resp.choices[0].message
    transcript = (msg.content or "").strip()
    msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else {}

    emotion = None
    for ann in msg_dict.get("annotations", []) or []:
        if ann.get("type") == "audio_info" and ann.get("emotion"):
            emotion = ann["emotion"]
            break

    return transcript, emotion, msg_dict


def minimax_tts(api_key: str, text: str, emotion: str, out_mp3: Path) -> dict:
    if not api_key:
        raise ValueError("Missing MiniMax key. Set MINIMAX_API_KEY.")

    url = f"{MINIMAX_BASE_URL}/t2a_v2"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "speech-2.8-hd",
        "text": text,
        "stream": False,
        "output_format": "hex",
        "voice_setting": {
            "voice_id": "qiaopi_mengmei",
            "speed": 1.3,
            "vol": 1,
            "pitch": 0,
            "emotion": emotion,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()

    audio_hex = ((data.get("data") or {}).get("audio") or "").strip()
    if not audio_hex:
        raise RuntimeError(f"MiniMax t2a_v2 response invalid: {json.dumps(data, ensure_ascii=False)[:600]}")

    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    out_mp3.write_bytes(binascii.unhexlify(audio_hex))
    return data


def play_audio(path: Path) -> None:
    # macOS
    subprocess.run(["afplay", str(path)], check=True)


def normalize_emotion_for_tts(emotion: str | None) -> str:
    if not emotion:
        return "fluent"
    if emotion in TTS_EMOTIONS:
        return emotion
    # Qwen emotion sometimes can be "neutral"; map to closest supported TTS style.
    if emotion == "neutral":
        return "calm"
    return "fluent"


def main() -> None:
    parser = argparse.ArgumentParser(description="SPACE-to-record ASR(emotion) + MiniMax emotional TTS demo")
    parser.add_argument("--sample-rate", type=int, default=16000)
    args = parser.parse_args()

    client = build_qwen_client()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    wav_path = record_while_holding_space(sample_rate=args.sample_rate)
    transcript, asr_emotion, raw_msg = qwen_asr_with_emotion(client, wav_path)

    print("\nQwen-ASR result:")
    print(f"- transcript: {transcript or '<empty>'}")
    print(f"- emotion: {asr_emotion or '<none>'}")
    if not asr_emotion:
        print(f"- raw annotations: {raw_msg.get('annotations')}")

    print("\n[Step2] Input text for MiniMax TTS.")
    text = input("text> ").strip()
    if not text:
        print("Empty text. Exit.")
        return

    default_emotion = normalize_emotion_for_tts(asr_emotion)
    user_emotion = input(
        f"emotion ({', '.join(TTS_EMOTIONS)}), default={default_emotion}> "
    ).strip()
    tts_emotion = user_emotion if user_emotion in TTS_EMOTIONS else default_emotion

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_mp3 = OUT_DIR / f"tts_{tts_emotion}_{ts}.mp3"
    minimax_tts(api_key=MINIMAX_API_KEY or "", text=text, emotion=tts_emotion, out_mp3=out_mp3)

    print(f"\nGenerated: {out_mp3}")
    print("Playing on speaker...")
    play_audio(out_mp3)
    print("Done.")


if __name__ == "__main__":
    main()
