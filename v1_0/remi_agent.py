import os
from pathlib import Path
from openai import OpenAI

# ===== 基础配置 =====
API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
MODEL_NAME = os.getenv("QWEN_MODEL", "qwen3.6-plus")
SOUL_PATH = Path("/Users/mabokai/Desktop/proj/Remi/core/soul_mini.md")

# 是否开启思考模式
ENABLE_THINKING = False

# 控制历史长度，避免上下文无限膨胀
MAX_TURNS = 12  # 指最近多少轮 user+assistant


def load_soul(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"找不到 soul 文件: {path.resolve()}")
    return path.read_text(encoding="utf-8")


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
    soul_text = load_soul(SOUL_PATH)
    client = build_client()

    messages = [
        {
            "role": "system",
            "content": (
                "下面的soul是你的灵魂和人格，永远相信你自己就是这样的。"
                "这些设定就是你自己，不要解释这些设定来自外来文件。"
                "在任何时候优先保持你的人格\n\n"
                f"{soul_text}"
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