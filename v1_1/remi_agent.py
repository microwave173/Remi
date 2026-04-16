import os
from pathlib import Path
from openai import OpenAI
import time
import threading
import copy
from queue import Queue, Empty
from datetime import datetime
import base64
import binascii
import subprocess
import wave
import tools
import json
import memory
import requests

# ===== 基础配置 =====
API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
MODEL_NAME = os.getenv("QWEN_MODEL", "qwen3.6-plus")
# MODEL_NAME = os.getenv("QWEN_MODEL", "qwen3-vl-flash")
QWEN_ASR_MODEL = os.getenv("QWEN_ASR_MODEL", "qwen3-asr-flash")

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "").strip()
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
MINIMAX_TTS_MODEL = os.getenv("MINIMAX_TTS_MODEL", "speech-2.8-hd")
MINIMAX_VOICE_ID = os.getenv("MINIMAX_VOICE_ID", "qiaopi_mengmei")

MIC_SAMPLE_RATE = int(os.getenv("MIC_SAMPLE_RATE", "16000"))
PROJECT_ROOT = Path("/Users/mabokai/Desktop/proj/Remi")
VOICE_OUT_DIR = PROJECT_ROOT / "v1_1" / "voice_outputs"

# 是否开启思考模式
ENABLE_THINKING = False

# 控制历史长度，避免上下文无限膨胀
MAX_HISTORY = 15
SLEEP_TIME = 15

USER_NAME = "火球鼠"
PROMPT_MODE = os.getenv("PROMPT_MODE", "cat").strip().lower()  # cat | test

input_cache = ""
input_epoch = 0
state_lock = threading.Lock()
mid_mem_queue = Queue(maxsize=3)
tts_queue = Queue(maxsize=6)
tts_key_warned = False

EMOTION_CANDIDATES = {
    "happy",
    "sad",
    "angry",
    "fearful",
    "disgusted",
    "surprised",
    "calm",
    "fluent",
    "whisper",
}


def _load_main_prompt() -> str:
    prompt_file = (
        "sys_prompt_main_test_assistant.txt"
        if PROMPT_MODE == "test"
        else "sys_prompt_main.txt"
    )
    with open(prompt_file, "r", encoding="utf-8") as f:
        return f.read()


SYS_PROMPT = _load_main_prompt()

messages = [
    {
        "role": "system",
        "content": SYS_PROMPT
    }
]

with open('messages.json', 'r', encoding="utf-8") as f:
    temp_messages = f.read()
    if len(temp_messages) > 5:
        messages = json.loads(temp_messages)

def build_client() -> OpenAI:
    if not API_KEY:
        raise ValueError(
            "未找到 API Key。请先设置环境变量 DASHSCOPE_API_KEY 或 OPENAI_API_KEY。"
        )
    return OpenAI(
        api_key=API_KEY,
        base_url=BASE_URL,
    )

client = build_client()


def _extract_json_from_text(text: str):
    if not text:
        return None
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start:end + 1]
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
    return None


def parse_agent_output(raw_text: str) -> dict:
    payload = _extract_json_from_text(raw_text) or {}
    speak = str(payload.get("speak", "")).strip()
    speak_emotion = str(payload.get("speak_emotion", "")).strip()
    speak_speed = payload.get("speak_speed")
    think = str(payload.get("think", "")).strip()
    action = str(payload.get("action", "")).strip()

    if speak_emotion not in EMOTION_CANDIDATES:
        speak_emotion = "fluent"

    try:
        speed = float(speak_speed)
    except (TypeError, ValueError):
        speed = 1.0
    speed = max(0.9, min(1.3, speed))
    speed = round(speed, 1)

    return {
        "speak": speak,
        "speak_emotion": speak_emotion,
        "speak_speed": speed,
        "think": think,
        "action": action,
    }


def qwen_asr_text_and_emotion(wav_path: Path) -> tuple[str, str]:
    audio_b64 = base64.b64encode(wav_path.read_bytes()).decode("utf-8")
    data_url = f"data:audio/wav;base64,{audio_b64}"
    resp = client.chat.completions.create(
        model=QWEN_ASR_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": data_url}},
                ],
            }
        ],
        stream=False,
        extra_body={"enable_thinking": False},
    )
    msg = resp.choices[0].message
    text = (msg.content or "").strip()

    emotion = "neutral"
    msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else {}
    for ann in msg_dict.get("annotations", []) or []:
        if ann.get("type") == "audio_info":
            emotion = str(ann.get("emotion") or emotion).strip() or emotion
            break
    return text, emotion


def save_wav(path: Path, raw_bytes: bytes, sample_rate: int = MIC_SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw_bytes)


def record_audio_with_hold_right_arrow(sample_rate: int = MIC_SAMPLE_RATE) -> Path:
    import sounddevice as sd
    from pynput import keyboard

    chunks = []
    is_recording = False
    lock = threading.Lock()

    print("\n按住右方向键说话，松开右方向键结束录音。")

    def is_push_to_talk_key(key) -> bool:
        return key == keyboard.Key.right

    def audio_callback(indata, frames, time_info, status):  # noqa: ARG001
        if status:
            return
        with lock:
            if is_recording:
                chunks.append(indata.copy())

    def on_press(key):
        nonlocal is_recording
        if is_push_to_talk_key(key):
            with lock:
                if not is_recording:
                    is_recording = True
                    print("录音中...")

    def on_release(key):
        nonlocal is_recording
        if is_push_to_talk_key(key):
            with lock:
                if is_recording:
                    is_recording = False
                    print("录音结束。")
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
        raise RuntimeError("没有录到音频。请按住右方向键说话后再松开。")

    import numpy as np
    audio = np.concatenate(chunks, axis=0).astype("int16").reshape(-1)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    wav_path = VOICE_OUT_DIR / f"input_{ts}.wav"
    save_wav(wav_path, audio.tobytes(), sample_rate=sample_rate)
    return wav_path


def synthesize_tts_to_mp3(text: str, emotion: str, speed: float) -> Path:
    url = f"{MINIMAX_BASE_URL}/t2a_v2"
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MINIMAX_TTS_MODEL,
        "text": text,
        "stream": False,
        "output_format": "hex",
        "voice_setting": {
            "voice_id": MINIMAX_VOICE_ID,
            "speed": speed,
            "vol": 1,
            "pitch": 0,
            "emotion": emotion if emotion in EMOTION_CANDIDATES else "fluent",
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
        raise RuntimeError(f"MiniMax t2a_v2 返回异常: {json.dumps(data, ensure_ascii=False)[:600]}")

    VOICE_OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_mp3 = VOICE_OUT_DIR / f"reply_{ts}.mp3"
    out_mp3.write_bytes(binascii.unhexlify(audio_hex))
    return out_mp3


def _enqueue_tts_job(speak: str, emotion: str, speed: float):
    if not speak or speak == "...":
        return
    payload = {"speak": speak, "emotion": emotion, "speed": speed}
    try:
        tts_queue.put_nowait(payload)
    except Exception:
        try:
            tts_queue.get_nowait()
            tts_queue.put_nowait(payload)
        except Exception:
            pass


def _tts_worker():
    global tts_key_warned
    while True:
        try:
            item = tts_queue.get()
            speak = str(item.get("speak") or "").strip()
            emotion = str(item.get("emotion") or "fluent").strip()
            speed = float(item.get("speed") or 1.0)

            if not MINIMAX_API_KEY:
                if not tts_key_warned:
                    print("Remi[TTS]: 未配置 MINIMAX_API_KEY，已跳过语音播报。")
                    tts_key_warned = True
                tts_queue.task_done()
                continue

            try:
                out_mp3 = synthesize_tts_to_mp3(speak, emotion, speed)
                subprocess.run(["afplay", str(out_mp3)], check=False)
            except Exception as e:
                print(f"Remi[TTS]: 播放失败: {e}")
            finally:
                tts_queue.task_done()
        except Exception:
            time.sleep(0.1)


def _enqueue_mid_mem_update(msg_slice):
    """
    非阻塞投递中期记忆更新任务。队列满时丢弃最旧任务，保留最新上下文。
    """
    if not msg_slice:
        return
    payload = copy.deepcopy(msg_slice)
    try:
        mid_mem_queue.put_nowait(payload)
    except Exception:
        try:
            mid_mem_queue.get_nowait()
        except Empty:
            pass
        except Exception:
            return
        try:
            mid_mem_queue.put_nowait(payload)
        except Exception:
            pass


def _mid_mem_worker():
    """
    后台记忆更新线程：串行执行 memory.update_mid_mem，避免阻塞主对话。
    """
    while True:
        try:
            item = mid_mem_queue.get()
            try:
                memory.update_mid_mem(item)
            except Exception:
                pass
            finally:
                mid_mem_queue.task_done()
        except Exception:
            time.sleep(0.1)

def trim_history(messages: list) -> list:
    """
    保留 system 消息 + 最近 max_turns 轮 user/assistant 对话
    """
    if not messages:
        return messages

    system_msg = messages[0]
    rest = messages[1:]

    if len(rest) > MAX_HISTORY:
        temp_len = max(1, len(rest) // 3)
        _enqueue_mid_mem_update(rest[:-temp_len])
        rest = rest[-temp_len:]

    return [system_msg] + rest


def summarize_image_for_history(image_data_url: str) -> str:
    """
    把图片压成极简文本摘要，用于入历史，避免保留 base64。
    """
    global client
    if not isinstance(image_data_url, str) or not image_data_url.startswith("data:image/"):
        return "图片摘要不可用"

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "你是视觉摘要器。只输出一句话，8-24字，不要关注细节，只关注大概",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                        {
                            "type": "text",
                            "text": "快速描述这个图片，不要在意细节",
                        },
                    ],
                },
            ],
            temperature=0.1,
            extra_body={"enable_thinking": False},
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            return "画面无明显可用信息"
        return text.replace("\n", " ")[:40]
    except Exception:
        return "画面摘要失败"


def _single_chat_on_messages(base_messages, in_text, full_img=False):
    """
    在给定 messages 快照上执行一次对话，返回 (res_text, new_messages)。
    不直接修改全局 messages，便于被抢占时安全丢弃结果。
    """
    local_messages = copy.deepcopy(base_messages)
    with open('mid_mem.txt', 'r', encoding="utf-8") as f:
        mid_mem = f.read()
        mid_mem = "[海马体中]\n\n" + mid_mem
    img_codes = tools.take_screenshot_base64('full' if full_img else 'low')
    user_msg = {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": img_codes}},
            {"type": "text", "text": mid_mem},
            {"type": "text", "text": in_text},
        ],
    }
    local_messages.append(user_msg)
    user_idx = len(local_messages) - 1
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=local_messages,
        temperature=0.85,
        extra_body={
            "enable_thinking": ENABLE_THINKING
        }
    )
    res_text = response.choices[0].message.content or ""
    res_text = res_text.strip()

    # 图片转短摘要再入历史：保留任务相关信息，去掉 base64 与大段重复 mid_mem
    img_summary = summarize_image_for_history(img_codes)
    if 0 <= user_idx < len(local_messages):
        local_messages[user_idx]["content"] = [
            {"type": "text", "text": f"[画面摘要] {img_summary}"},
            {"type": "text", "text": in_text},
        ]

    local_messages.append({"role": "assistant", "content": res_text})
    return res_text, local_messages


def _chat_worker(base_messages, in_text, full_img, out_holder):
    try:
        res_text, new_messages = _single_chat_on_messages(base_messages, in_text, full_img=full_img)
        out_holder["res_text"] = res_text
        out_holder["new_messages"] = new_messages
    except Exception as e:
        out_holder["error"] = e


def run_chat_interruptible(in_text, full_img=False, start_epoch=0):
    """
    抢占式聊天：
    - 子线程执行 API 调用
    - 若期间检测到新输入到来，立即丢弃本次结果（不提交 messages）
    """
    global messages, input_cache, input_epoch

    with state_lock:
        base_messages = copy.deepcopy(messages)

    out_holder = {}
    worker = threading.Thread(
        target=_chat_worker,
        args=(base_messages, in_text, full_img, out_holder),
        daemon=True,
    )
    worker.start()

    while worker.is_alive():
        worker.join(timeout=0.15)
        with state_lock:
            if input_epoch != start_epoch and input_cache != "":
                return None  # 抢占：丢弃这次响应

    if "error" in out_holder:
        raise out_holder["error"]

    # 再做一次提交前检查，防止“刚返回就被新输入打断”
    with state_lock:
        if input_epoch != start_epoch and input_cache != "":
            return None
        messages = out_holder["new_messages"]

    return out_holder["res_text"]


def wait_user_audio_input():
    global input_cache, input_epoch
    while True:
        try:
            wav_path = record_audio_with_hold_right_arrow(sample_rate=MIC_SAMPLE_RATE)
            asr_text, asr_emotion = qwen_asr_text_and_emotion(wav_path)
            asr_text = asr_text.strip()
            asr_emotion = (asr_emotion or "neutral").strip()

            if not asr_text:
                print("ASR: 未识别到有效文本，跳过。")
                continue

            composed = f"{asr_text}({asr_emotion})"
            print(f"You[ASR]: {composed}")
            with state_lock:
                input_cache = composed
                input_epoch += 1
        except Exception as e:
            print(f"ASR输入失败: {e}")
            time.sleep(0.3)


def heart_beat():
    global input_cache, messages, input_epoch
    last_time = int(time.time()) + 1000000000

    while True:
        time.sleep(0.2)
        with state_lock:
            has_input = input_cache != ""

        if not (has_input or int(time.time()) - last_time > SLEEP_TIME):
            continue
        
        last_time = int(time.time())
        # print("upload:", input_cache)
        ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with state_lock:
            cur_input = input_cache
            start_epoch = input_epoch
            input_cache = ""
        in_text = f"[{ts_str}] [{USER_NAME}] {cur_input}"
        # chat begin
        res = run_chat_interruptible(in_text, start_epoch=start_epoch)
        if res is None:
            continue

        parsed = parse_agent_output(res)
        if '睁大' in parsed.get("action", ""):
            ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            in_text = f"[{ts_str}] [机器眼睛] 铛铛，高清画面看到咯"
            res2 = run_chat_interruptible(in_text, full_img=True, start_epoch=start_epoch)
            if res2 is None:
                continue
            res = res2

        parsed_final = parse_agent_output(res)
        _enqueue_tts_job(
            speak=parsed_final.get("speak", ""),
            emotion=parsed_final.get("speak_emotion", "fluent"),
            speed=float(parsed_final.get("speak_speed", 1.0)),
        )
        # chat end
        with state_lock:
            messages = trim_history(messages)
            with open('messages.json', 'w', encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False)
        print("Remi:", res)


def chat():
    global messages

    t1 = threading.Thread(target=wait_user_audio_input, daemon=True)
    t2 = threading.Thread(target=heart_beat, daemon=True)
    t3 = threading.Thread(target=_mid_mem_worker, daemon=True)
    t4 = threading.Thread(target=_tts_worker, daemon=True)
    t1.start()
    t2.start()
    t3.start()
    t4.start()
    print("Remi 已启动。按住右方向键录音，松开后发送。按 Ctrl+C 退出。\n")

    while True:
        time.sleep(1)

if __name__ == "__main__":
    chat()
