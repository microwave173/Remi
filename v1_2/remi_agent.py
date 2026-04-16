import os
import copy
import time
import json
import threading
from queue import Queue, Empty
from datetime import datetime
from pathlib import Path
import tkinter as tk

from openai import OpenAI

import tools
import memory

# ===== 基础配置 =====
BASE_DIR = Path(__file__).resolve().parent
API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
MODEL_NAME = os.getenv("QWEN_MODEL", "qwen3.6-plus")

ENABLE_THINKING = False
MAX_HISTORY = 15
USER_NAME = "火球鼠"
PROMPT_MODE = os.getenv("PROMPT_MODE", "cat").strip().lower()  # cat | test

MESSAGES_PATH = BASE_DIR / "messages.json"
MID_MEM_PATH = BASE_DIR / "mid_mem.txt"

state_lock = threading.Lock()
mid_mem_queue = Queue(maxsize=3)


def _load_main_prompt() -> str:
    prompt_path = (
        BASE_DIR / "sys_prompt_main_test_assistant.txt"
        if PROMPT_MODE == "test"
        else BASE_DIR / "sys_prompt_main.txt"
    )
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


SYS_PROMPT = _load_main_prompt()

messages = [{"role": "system", "content": SYS_PROMPT}]
if MESSAGES_PATH.exists():
    with open(MESSAGES_PATH, "r", encoding="utf-8") as f:
        temp_messages = f.read()
        if len(temp_messages) > 5:
            messages = json.loads(temp_messages)


def build_client() -> OpenAI:
    if not API_KEY:
        raise ValueError("未找到 API Key。请先设置环境变量 DASHSCOPE_API_KEY 或 OPENAI_API_KEY。")
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


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
    think = str(payload.get("think", "")).strip()
    action = str(payload.get("action", "")).strip()
    return {
        "speak": speak,
        "think": think,
        "action": action,
        "raw": raw_text or "",
    }


def _enqueue_mid_mem_update(msg_slice):
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


def trim_history(msgs: list) -> list:
    if not msgs:
        return msgs

    system_msg = msgs[0]
    rest = msgs[1:]
    if len(rest) > MAX_HISTORY:
        keep_len = max(1, len(rest) // 3)
        _enqueue_mid_mem_update(rest[:-keep_len])
        rest = rest[-keep_len:]
    return [system_msg] + rest


def summarize_image_for_history(image_data_url: str) -> str:
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
                        {"type": "text", "text": "快速描述这个图片，不要在意细节"},
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


def _single_chat_on_messages(base_messages: list, in_text: str, full_img: bool = False):
    local_messages = copy.deepcopy(base_messages)

    if MID_MEM_PATH.exists():
        with open(MID_MEM_PATH, "r", encoding="utf-8") as f:
            mid_mem = "[海马体中]\n\n" + f.read()
    else:
        mid_mem = "[海马体中]\n\n"

    img_codes = tools.take_screenshot_base64("full" if full_img else "low")
    content = []
    if isinstance(img_codes, str) and img_codes.startswith("data:image/"):
        content.append({"type": "image_url", "image_url": {"url": img_codes}})
    else:
        content.append({"type": "text", "text": f"[截图状态] {img_codes}"})

    content.extend([
        {"type": "text", "text": mid_mem},
        {"type": "text", "text": in_text},
    ])

    user_msg = {"role": "user", "content": content}
    local_messages.append(user_msg)
    user_idx = len(local_messages) - 1

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=local_messages,
        temperature=0.85,
        extra_body={"enable_thinking": ENABLE_THINKING},
    )
    res_text = (response.choices[0].message.content or "").strip()

    img_summary = summarize_image_for_history(img_codes)
    if 0 <= user_idx < len(local_messages):
        local_messages[user_idx]["content"] = [
            {"type": "text", "text": f"[画面摘要] {img_summary}"},
            {"type": "text", "text": in_text},
        ]

    local_messages.append({"role": "assistant", "content": res_text})
    return res_text, local_messages


def single_text_turn(user_text: str) -> dict:
    global messages
    with state_lock:
        base_messages = copy.deepcopy(messages)

    ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    in_text = f"[{ts_str}] [{USER_NAME}] {user_text}"

    res, new_messages = _single_chat_on_messages(base_messages, in_text, full_img=False)
    parsed = parse_agent_output(res)

    if "睁大" in parsed.get("action", ""):
        ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        eye_text = f"[{ts_str}] [机器眼睛] 铛铛，高清画面看到咯"
        res2, new_messages2 = _single_chat_on_messages(new_messages, eye_text, full_img=True)
        res = res2
        new_messages = new_messages2
        parsed = parse_agent_output(res)

    with state_lock:
        messages = trim_history(new_messages)
        with open(MESSAGES_PATH, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False)

    return parsed


def run_floating_window():
    def safe_set_output(text: str):
        output_var.set(text if text else "...")

    def on_send(event=None):
        text = input_var.get().strip()
        if not text:
            return
        input_entry.configure(state="disabled")
        send_btn.configure(state="disabled")
        safe_set_output("思考中...")

        def worker():
            try:
                result = single_text_turn(text)
                speak = result.get("speak", "")
                ui_text = speak if speak else (result.get("raw", "") or "...")
            except Exception as e:
                ui_text = f"请求失败: {e}"

            def finish():
                safe_set_output(ui_text)
                input_var.set("")
                input_entry.configure(state="normal")
                send_btn.configure(state="normal")
                input_entry.focus_set()

            root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def start_drag(event):
        root._drag_x = event.x_root
        root._drag_y = event.y_root
        root._win_x = root.winfo_x()
        root._win_y = root.winfo_y()

    def do_drag(event):
        dx = event.x_root - root._drag_x
        dy = event.y_root - root._drag_y
        root.geometry(f"+{root._win_x + dx}+{root._win_y + dy}")

    root = tk.Tk()
    root.title("Remi")
    root.geometry("420x220+120+120")
    root.configure(bg="#1f1f1f")
    root.attributes("-topmost", True)
    root.overrideredirect(True)

    title_bar = tk.Frame(root, bg="#2b2b2b", height=30)
    title_bar.pack(fill="x", side="top")
    title_label = tk.Label(
        title_bar,
        text="Remi Floating Chat",
        bg="#2b2b2b",
        fg="#f0f0f0",
        anchor="w",
        padx=10,
    )
    title_label.pack(side="left", fill="x", expand=True)
    close_btn = tk.Button(
        title_bar,
        text="×",
        bg="#2b2b2b",
        fg="#f0f0f0",
        relief="flat",
        command=root.destroy,
        bd=0,
        width=3,
    )
    close_btn.pack(side="right", padx=6, pady=2)

    for w in (title_bar, title_label):
        w.bind("<ButtonPress-1>", start_drag)
        w.bind("<B1-Motion>", do_drag)

    body = tk.Frame(root, bg="#1f1f1f")
    body.pack(fill="both", expand=True, padx=10, pady=10)

    output_var = tk.StringVar(value="你好")
    output_box = tk.Label(
        body,
        textvariable=output_var,
        bg="#2a2a2a",
        fg="#f6f6f6",
        justify="left",
        anchor="nw",
        wraplength=380,
        padx=10,
        pady=10,
        height=6,
    )
    output_box.pack(fill="x", pady=(0, 10))

    input_row = tk.Frame(body, bg="#1f1f1f")
    input_row.pack(fill="x")
    input_var = tk.StringVar()
    input_entry = tk.Entry(
        input_row,
        textvariable=input_var,
        bg="#2a2a2a",
        fg="#ffffff",
        insertbackground="#ffffff",
        relief="flat",
    )
    input_entry.pack(side="left", fill="x", expand=True, ipady=7)
    send_btn = tk.Button(
        input_row,
        text="发送",
        command=on_send,
        bg="#3a3a3a",
        fg="#ffffff",
        relief="flat",
        width=8,
    )
    send_btn.pack(side="left", padx=(8, 0))

    input_entry.bind("<Return>", on_send)
    input_entry.focus_set()
    root.mainloop()


if __name__ == "__main__":
    t_mem = threading.Thread(target=_mid_mem_worker, daemon=True)
    t_mem.start()
    run_floating_window()
