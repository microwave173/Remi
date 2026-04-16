import argparse
import base64
import mimetypes
import os
import subprocess
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from PIL import Image

# ===== 基础配置 =====
API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
MODEL_NAME = os.getenv("QWEN_MODEL", "qwen3.6-plus")
PROJECT_ROOT = Path("/Users/mabokai/Desktop/proj/Remi")
SCREENSHOT_DIR = PROJECT_ROOT / "v1_1" / "playgrounds" / "screenshots"

# 4档分辨率：最高到最低
# full: 原始屏幕分辨率
# high: 短边 1024
# medium: 短边 512
# low: 短边 256
QUALITY_SHORT_SIDE = {
    "full": None,
    "high": 1024,
    "medium": 512,
    "low": 256,
}


def build_client() -> OpenAI:
    if not API_KEY:
        raise ValueError("未找到 API Key。请设置 DASHSCOPE_API_KEY 或 OPENAI_API_KEY。")
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


def _resize_keep_ratio(image_path: Path, short_side: int | None) -> Path:
    if short_side is None:
        return image_path

    with Image.open(image_path) as im:
        w, h = im.size
        cur_short = min(w, h)
        if cur_short <= short_side:
            return image_path

        scale = short_side / float(cur_short)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        resized = im.resize((nw, nh), Image.Resampling.LANCZOS)

        out_path = image_path.with_name(f"{image_path.stem}_{short_side}.png")
        resized.save(out_path, format="PNG")
        return out_path


def take_screenshot(quality: str = "full") -> Path:
    """最简单截屏：macOS 用 screencapture，全屏截图，支持 4 档分辨率。"""
    if quality not in QUALITY_SHORT_SIDE:
        raise ValueError(f"quality 必须是 {list(QUALITY_SHORT_SIDE.keys())}")

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = SCREENSHOT_DIR / f"screen_{ts}.png"

    cmd = ["screencapture", "-x", str(raw_path)]
    completed = subprocess.run(cmd, capture_output=True, text=False)
    if completed.returncode != 0:
        stderr = (completed.stderr or b"").decode("utf-8", errors="replace")
        raise RuntimeError(f"截图失败: {stderr}")

    short_side = QUALITY_SHORT_SIDE[quality]
    return _resize_keep_ratio(raw_path, short_side)


def ask_with_image(client: OpenAI, image_path: Path, question: str) -> str:
    image_bytes = image_path.read_bytes()
    mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime};base64,{b64}"

    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": question},
                ],
            }
        ],
        temperature=0.2,
        extra_body={"enable_thinking": False},
    )

    text = resp.choices[0].message.content or ""
    return text.strip()


def main():
    parser = argparse.ArgumentParser(description="Qwen 单次图片问答最小示例")
    parser.add_argument("--quality", choices=["full", "high", "medium", "low"], default="low")
    parser.add_argument("--question", default="这是用户现在的屏幕截图，用户大概在做什么，一句话简要描述就行，不需要细节")
    args = parser.parse_args()

    client = build_client()
    image_path = take_screenshot(args.quality)
    answer = ask_with_image(client, image_path, args.question)

    print(f"截图路径: {image_path}")
    print(f"模型回答: {answer}")


if __name__ == "__main__":
    main()
