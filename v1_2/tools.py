import os
import subprocess
import base64
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = os.getenv("PROJECT_ROOT", "/Users/mabokai/Desktop/proj/Remi")
SCREENSHOT_DIR = Path(PROJECT_ROOT) / "v1_1" / "screenshots"

QUALITY_SHORT_SIDE = {
    "full": None,
    "high": 1024,
    "medium": 512,
    "low": 256,
}


def run_cli(command: str, timeout: int = 20) -> str:
    """执行一条本地 shell 命令（非持久会话，每次独立进程）。"""
    if not command.strip():
        return "命令为空。"

    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"命令执行超时（>{timeout}s）。"
    except Exception as e:
        return f"执行命令出错: {e}"

    result = [f"exit_code: {completed.returncode}"]
    stdout_text = (completed.stdout or "").strip()
    stderr_text = (completed.stderr or "").strip()

    if stdout_text:
        result.append(f"stdout:\n{stdout_text[:8000]}")
    if stderr_text:
        result.append(f"stderr:\n{stderr_text[:8000]}")
    return "\n\n".join(result)


def close_cli_session() -> None:
    """兼容旧接口：非持久实现下无需处理。"""
    return None


def _to_int(v, default: int | None = None) -> int | None:
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def web_search(query: str, max_results: int = 5) -> str:
    """
    联网搜索工具（DuckDuckGo）。
    返回标题、链接和摘要，供模型二次整理。
    """
    q = (query or "").strip()
    if not q:
        return "参数错误：query 不能为空。"

    n = max(1, min(10, _to_int(max_results, 5) or 5))

    try:
        try:
            from ddgs import DDGS  # type: ignore
        except Exception:
            return (
                "web_search 不可用：缺少 ddgs 依赖。\n"
                "请先安装：python3 -m pip install ddgs"
            )

        lines = [f"query: {q}", f"max_results: {n}"]
        with DDGS() as ddgs:
            results = list(ddgs.text(q, max_results=n))

        if not results:
            return f"query: {q}\nno_results: true"

        for i, item in enumerate(results, start=1):
            title = str(item.get("title") or "").strip()
            link = str(item.get("href") or item.get("url") or "").strip()
            snippet = str(item.get("body") or "").strip()
            lines.append(f"\n[{i}] {title}\nurl: {link}\nsnippet: {snippet}")

        return "\n".join(lines)[:12000]
    except Exception as e:
        return f"web_search 执行失败: {e}"


def _resize_png_short_side(src: Path, dst: Path, short_side: int = 256) -> None:
    from PIL import Image  # 延迟导入，避免无关调用受依赖影响

    with Image.open(src) as im:
        w, h = im.size
        cur_short = min(w, h)
        if cur_short <= short_side:
            im.save(dst, format="PNG")
            return

        scale = short_side / float(cur_short)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        resized = im.resize((nw, nh), Image.Resampling.LANCZOS)
        resized.save(dst, format="PNG")


def take_screenshot_base64(quality: str = "full") -> str:
    """
    最简单截图函数，返回可直接放入 message 的 data URL。
    quality:
      - full: 原始分辨率
      - low:  短边 256
    返回:
      data:image/png;base64,xxxx
    """
    if quality not in {"full", "low"}:
        return "参数错误：quality 只能是 'full' 或 'low'。"

    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        full_path = SCREENSHOT_DIR / f"screen_full.png"
        out_path = full_path

        cmd = ["screencapture", "-x", str(full_path)]
        completed = subprocess.run(cmd, capture_output=True, text=False, cwd=PROJECT_ROOT)
        if completed.returncode != 0:
            stderr = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
            return f"截图失败: {stderr}"

        if quality == "low":
            out_path = SCREENSHOT_DIR / f"screen_low.png"
            _resize_png_short_side(full_path, out_path, short_side=256)

        b64 = base64.b64encode(out_path.read_bytes()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        return f"take_screenshot_base64 执行失败: {e}"


tools_desc = [
    {
        "type": "function",
        "function": {
            "name": "run_cli",
            "description": "执行一条本地shell命令并返回结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的shell命令，例如: ls -la v1_0",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "执行一次互联网搜索并返回搜索结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜索的内容 关键词",
                    },
                    "max_results": {
                        "type": "int",
                        "description": "最多返回的搜索结果条数，一般设为5，根据实际情况可以改变"
                    }
                }
            },
            "required": ["query", "max_results"],
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot_base64",
            "description": "截屏并返回可直接放在message里的 data:image/png;base64,... 字符串",
            "parameters": {
                "type": "object",
                "properties": {
                    "quality": {
                        "type": "string",
                        "description": "截图清晰度：full（原分辨率）或 low（短边256）",
                    }
                },
                "required": [],
            },
        },
    },
]


if __name__ == "__main__":
    print("=== tools.py 使用案例 ===")

    print("\n[1] CLI 工具示例：")
    print(run_cli("pwd"))
    print(run_cli("ls -la v1_0 | head"))

    print("\n[2] 联网搜索工具示例：")
    result = web_search("wayward 大黄", max_results=5)
    print(result)

    print("\n[3] 截屏 base64 工具示例（仅展示前100字符）：")
    img_data_url = take_screenshot_base64("low")
    print(img_data_url[:100] + "...")

    close_cli_session()
