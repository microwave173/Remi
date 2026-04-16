import os
from pathlib import Path
from openai import OpenAI
import tools

# ===== 基础配置 =====
API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
MODEL_NAME = os.getenv("QWEN_MODEL", "qwen3.6-plus")

# 是否开启思考模式
ENABLE_THINKING = False

# 控制历史长度，避免上下文无限膨胀
MAX_TURNS = 12  # 指最近多少轮 user+assistant

def build_client() -> OpenAI:
    if not API_KEY:
        raise ValueError(
            "未找到 API Key。请先设置环境变量 DASHSCOPE_API_KEY 或 OPENAI_API_KEY。"
        )
    return OpenAI(
        api_key=API_KEY,
        base_url=BASE_URL,
    )


def trim_history(messages: list, max_turns: int) -> list:
    """
    保留 system 消息 + 最近 max_turns 轮 user/assistant 对话
    """
    if not messages:
        return messages

    system_msg = messages[0]
    rest = messages[1:]

    # 一轮通常是 user + assistant，两条消息
    keep_n = max_turns * 2
    if len(rest) > keep_n:
        rest = rest[-keep_n:]

    return [system_msg] + rest


def chat():
    client = build_client()

    messages = [
        {
            "role": "system",
            "content": (
                "你是一个优秀的ai助手"
                ""
            ),
        }
    ]

    print("Remi 已启动。输入 /exit 退出，输入 /clear 清空历史。\n")

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            break

        if not user_input:
            continue

        if user_input == "/exit":
            print("已退出。")
            break

        if user_input == "/clear":
            messages = [messages[0]]
            print("历史已清空。\n")
            continue

        messages.append({"role": "user", "content": user_input})
        messages = trim_history(messages, MAX_TURNS)

        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.85,
                extra_body={
                    "enable_thinking": ENABLE_THINKING
                }
            )

            assistant_text = response.choices[0].message.content or ""
            assistant_text = assistant_text.strip()

            print(f"Remi: {assistant_text}\n")

            messages.append({
                "role": "assistant",
                "content": assistant_text
            })

        except Exception as e:
            print(f"[请求失败] {e}\n")


if __name__ == "__main__":
    chat()