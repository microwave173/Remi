import argparse
import binascii
import json
from datetime import datetime
from pathlib import Path

import requests

# 你给的测试 key（仅用于本地测试）
DEFAULT_API_KEY = "sk-api-A9nr-xuYaJDuXluNFGQQMpOPCxLqT_PJM0gfPoEk60w6B9dpRwqIP_UUraZ-bF9suZN8zoTRIJ5OCD4vJ_2QwUWKA_zWRTzjGVLJsGYCGLIG5Mb7BN3FKvs"
BASE_URL = "https://api.minimaxi.com/v1"
OUT_DIR = Path("/Users/mabokai/Desktop/proj/Remi/v1_1/playgrounds/minimax_outputs")


def minimax_chat(api_key: str, user_text: str) -> str:
    """调用 M2-her 做角色扮演对话（文本）。"""
    url = f"{BASE_URL}/text/chatcompletion_v2"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "M2-her",  # MiniMax 角色扮演表现较强的模型
        "messages": [
            {
                "role": "system",
                "content": (
                    "你现在是一个擅长角色扮演的角色：温柔、机智、略带俏皮，"
                    "会自然接梗，回复简洁有画面感。"
                ),
            },
            {"role": "user", "content": user_text},
        ],
        # 让人格更明显一点
        "temperature": 0.85,
        "top_p": 0.95,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=40)
    resp.raise_for_status()
    data = resp.json()

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"chat 返回异常: {json.dumps(data, ensure_ascii=False)[:500]}")

    message = choices[0].get("message", {})
    text = (message.get("content") or "").strip()
    if not text:
        raise RuntimeError(f"chat 没有返回文本: {json.dumps(data, ensure_ascii=False)[:500]}")

    return text


def minimax_tts(api_key: str, text: str, out_mp3: Path) -> None:
    """调用 t2a_v2 合成语音，保存 mp3。"""
    url = f"{BASE_URL}/t2a_v2"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "speech-2.8-turbo",
        "text": text,
        "stream": False,
        "output_format": "hex",
        "voice_setting": {
            "voice_id": "Chinese (Mandarin)_Warm_Bestie",
            "speed": 1.3,
            "vol": 1,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    audio_hex = ((data.get("data") or {}).get("audio") or "").strip()
    if not audio_hex:
        raise RuntimeError(f"t2a 返回异常: {json.dumps(data, ensure_ascii=False)[:500]}")

    audio_bytes = binascii.unhexlify(audio_hex)
    out_mp3.write_bytes(audio_bytes)


def run_once(user_text: str, api_key: str = DEFAULT_API_KEY) -> tuple[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_mp3 = OUT_DIR / f"minimax_reply_{ts}.mp3"

    reply = minimax_chat(api_key=api_key, user_text=user_text)
    minimax_tts(api_key=api_key, text=reply, out_mp3=out_mp3)
    return reply, out_mp3


def main() -> None:
    parser = argparse.ArgumentParser(description="MiniMax 最小端到端音频对话 demo")
    parser.add_argument("--text", default="你现在扮演一个有点傲娇但很关心我的伙伴，先跟我打个招呼")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    args = parser.parse_args()

    reply, out_mp3 = run_once(user_text=args.text, api_key=args.api_key)
    print("模型回复:")
    print(reply)
    print("\n音频文件:")
    print(out_mp3)


if __name__ == "__main__":
    main()
