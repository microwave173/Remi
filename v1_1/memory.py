import argparse
import os
import json

from openai import OpenAI

# ===== 基础配置 =====
API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
MODEL_NAME = os.getenv("QWEN_MODEL", "qwen3.6-plus")
PROMPT_MODE = os.getenv("PROMPT_MODE", "cat").strip().lower()  # cat | test

def _load_midmem_prompt() -> str:
    prompt_file = (
        "sys_prompt_midmem_test_assistant.txt"
        if PROMPT_MODE == "test"
        else "sys_prompt_midmem.txt"
    )
    with open(prompt_file, "r", encoding="utf-8") as f:
        return f.read()


SYS_PROMPT_MIDMEM = _load_midmem_prompt()


def build_client() -> OpenAI:
    if not API_KEY:
        raise ValueError("未找到 API Key。请设置 DASHSCOPE_API_KEY 或 OPENAI_API_KEY。")
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


client = build_client()


def update_mid_mem(msgs):
    global client

    msgs = json.dumps(msgs)
    with open('mid_mem.txt', 'r', encoding="utf-8") as f:
        cur_mid_mem = f.read()

    in_text = json.dumps({
        "上下文缓存": msgs,
        "海马体信息": cur_mid_mem
    })

    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": SYS_PROMPT_MIDMEM
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": in_text},
                ],
            }
        ],
        temperature=0.2,
        extra_body={"enable_thinking": False},
    )

    text = resp.choices[0].message.content or ""
    with open('mid_mem.txt', 'w', encoding="utf-8") as f:
        f.write(text)


def main():
    parser = argparse.ArgumentParser(description="Qwen 单次图片问答最小示例")
    parser.add_argument("--quality", choices=["full", "high", "medium", "low"], default="low")
    parser.add_argument("--question", default="这是用户现在的屏幕截图，用户大概在做什么，一句话简要描述就行，不需要细节")
    args = parser.parse_args()

    


if __name__ == "__main__":
    main()
