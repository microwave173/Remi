import json
import os
import subprocess
import base64
import mimetypes
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from v1_0.tools import close_cli_session, run_cli, web_search

# ===== 基础配置 =====
API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
MODEL_NAME = os.getenv("QWEN_MODEL", "qwen3.5-flash")
# MODEL_NAME = os.getenv("QWEN_MODEL", "qwen3.6-plus")

# 是否开启思考模式
ENABLE_THINKING = False

# 控制历史长度，避免上下文无限膨胀
MAX_TURNS = 12  # 指最近多少轮 user+assistant
MAX_TOOL_STEPS = 20
PROJECT_ROOT = "/Users/mabokai/Desktop/proj/Remi"
AUTO_SCREENSHOT_AFTER_CLICK = True


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
    保留 system 消息 + 最近 max_turns 轮 user/assistant/tool 对话
    """
    if not messages:
        return messages

    system_msg = messages[0]
    rest = messages[1:]

    # 一轮通常至少是 user + assistant，两条消息
    keep_n = max_turns * 2
    if len(rest) > keep_n:
        rest = rest[-keep_n:]

    return [system_msg] + rest


def _to_int(v, default: int | None = None) -> int | None:
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _to_float(v, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_bool(v, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "y", "on"}
    return default


def control_input(
    action: str,
    x: int | None = None,
    y: int | None = None,
    x_norm: float | None = None,
    y_norm: float | None = None,
    text: str | None = None,
    key: str | None = None,
    keys: list[str] | None = None,
    amount: int | None = None,
    button: str = "left",
    clicks: int = 1,
    interval: float = 0.05,
    duration: float = 0.0,
    post_check: bool | None = None,
    vision_prompt: str | None = None,
) -> str:
    """
    控制鼠标和键盘。依赖 pyautogui:
    pip install pyautogui
    """
    try:
        import pyautogui  # type: ignore
    except Exception:
        return (
            "control_input 不可用：缺少 pyautogui。\n"
            "请先安装：python3 -m pip install pyautogui"
        )

    try:
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.03

        screen_w, screen_h = pyautogui.size()
        resolved_x = x
        resolved_y = y
        if x_norm is not None and y_norm is not None:
            # 归一化坐标映射到屏幕像素，范围自动夹紧到 [0, 1]
            xn = max(0.0, min(1.0, float(x_norm)))
            yn = max(0.0, min(1.0, float(y_norm)))
            resolved_x = int(round(xn * (screen_w - 1)))
            resolved_y = int(round(yn * (screen_h - 1)))

        if action == "position":
            pos = pyautogui.position()
            x_n = pos.x / max(1, screen_w - 1)
            y_n = pos.y / max(1, screen_h - 1)
            return (
                f"ok: x={pos.x}, y={pos.y}, "
                f"x_norm={x_n:.4f}, y_norm={y_n:.4f}, "
                f"screen={screen_w}x{screen_h}"
            )

        if action == "move":
            if resolved_x is None or resolved_y is None:
                return "参数错误：move 需要 (x,y) 或 (x_norm,y_norm)。"
            pyautogui.moveTo(
                resolved_x, resolved_y, duration=max(0.0, float(duration))
            )
            return (
                f"ok: moved to ({resolved_x}, {resolved_y}), "
                f"screen={screen_w}x{screen_h}"
            )

        if action == "click":
            if resolved_x is not None and resolved_y is not None:
                pyautogui.click(
                    x=resolved_x,
                    y=resolved_y,
                    clicks=max(1, clicks),
                    interval=max(0.0, interval),
                    button=button,
                )
            else:
                pyautogui.click(
                    clicks=max(1, clicks),
                    interval=max(0.0, interval),
                    button=button,
                )

            do_post_check = _to_bool(post_check, AUTO_SCREENSHOT_AFTER_CLICK)
            if not do_post_check:
                return (
                    f"ok: click button={button}, clicks={max(1, clicks)}, "
                    f"xy=({resolved_x}, {resolved_y})"
                )

            shot_result = take_screenshot()
            # take_screenshot 成功时格式: ok: screenshot saved to <path>, ...
            shot_path = None
            if shot_result.startswith("ok: screenshot saved to "):
                raw = shot_result[len("ok: screenshot saved to "):]
                shot_path = raw.split(", size=", 1)[0].strip()

            analysis = ""
            if shot_path:
                prompt = (
                    vision_prompt
                    or "请判断刚才点击操作是否成功，描述当前界面状态，并给下一步可执行建议。"
                )
                analysis = analyze_image(image_path=shot_path, prompt=prompt)

            result_lines = [
                "ok: click completed",
                f"button={button}, clicks={max(1, clicks)}",
                f"xy=({resolved_x}, {resolved_y}), screen={screen_w}x{screen_h}",
                f"screenshot={shot_path or 'N/A'}",
            ]
            if analysis:
                result_lines.append("post_check:")
                result_lines.append(analysis[:6000])
            else:
                result_lines.append(f"post_check: 截图或图像分析未成功。detail: {shot_result}")
            return "\n".join(result_lines)

        if action == "type":
            if text is None:
                return "参数错误：type 需要 text。"
            pyautogui.write(text, interval=max(0.0, interval))
            return f"ok: typed {len(text)} chars"

        if action == "press":
            if not key:
                return "参数错误：press 需要 key。"
            pyautogui.press(key, presses=max(1, clicks), interval=max(0.0, interval))
            return f"ok: pressed key={key}, times={max(1, clicks)}"

        if action == "hotkey":
            if not keys:
                return "参数错误：hotkey 需要 keys（例如 ['command', 'c']）。"
            pyautogui.hotkey(*keys)
            return f"ok: hotkey {'+'.join(keys)}"

        if action == "scroll":
            if amount is None:
                return "参数错误：scroll 需要 amount。"
            pyautogui.scroll(amount)
            return f"ok: scrolled {amount}"

        return (
            "未知 action。可用值：position, move, click, type, press, hotkey, scroll"
        )
    except Exception as e:
        return f"control_input 执行失败: {e}"


def take_screenshot(
    save_path: str | None = None,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> str:
    """
    截屏工具。macOS 下使用 screencapture。
    支持全屏和区域截图（x,y,width,height）。
    """
    try:
        shot_dir = Path(PROJECT_ROOT) / "v1_0" / "screenshots"
        shot_dir.mkdir(parents=True, exist_ok=True)

        if save_path:
            target = Path(save_path)
            if not target.is_absolute():
                target = (Path(PROJECT_ROOT) / target).resolve()
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = shot_dir / f"screenshot_{stamp}.png"

        target.parent.mkdir(parents=True, exist_ok=True)

        cmd = ["screencapture", "-x"]
        if None not in (x, y, width, height):
            cmd.extend(["-R", f"{x},{y},{width},{height}"])
        cmd.append(str(target))

        completed = subprocess.run(
            cmd, capture_output=True, text=False, timeout=15, cwd=PROJECT_ROOT
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
            return f"截图失败: exit_code={completed.returncode}, stderr={stderr}"

        size_bytes = target.stat().st_size if target.exists() else 0
        extra = f", size={size_bytes} bytes"
        try:
            from PIL import Image  # type: ignore

            with Image.open(target) as im:
                extra += f", resolution={im.width}x{im.height}"
        except Exception:
            pass

        return f"ok: screenshot saved to {target}{extra}"
    except Exception as e:
        return f"take_screenshot 执行失败: {e}"


def _latest_screenshot() -> Path | None:
    shot_dir = Path(PROJECT_ROOT) / "v1_0" / "screenshots"
    if not shot_dir.exists():
        return None
    files = sorted(
        [p for p in shot_dir.glob("*.png") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def analyze_image(
    image_path: str | None = None,
    prompt: str = "请详细描述这张图里你看到了什么。",
) -> str:
    """
    用当前 Qwen 模型做图像分析。
    OpenAI 兼容方式下，本地文件用 Base64 Data URL 传入。
    """
    path_text = (image_path or "").strip()

    # 支持直接分析公网 URL
    if path_text.startswith("http://") or path_text.startswith("https://"):
        image_url = path_text
    else:
        if not path_text:
            latest = _latest_screenshot()
            if not latest:
                return "没有可分析的截图。请先调用 take_screenshot。"
            img = latest
        else:
            img = Path(path_text)
            if not img.is_absolute():
                img = (Path(PROJECT_ROOT) / img).resolve()

        if not img.exists() or not img.is_file():
            return f"图片不存在: {img}"

        size_bytes = img.stat().st_size
        # 阿里云文档建议：OpenAI 兼容 + Base64 时，原始文件应小于 7MB
        if size_bytes >= 7 * 1024 * 1024:
            return (
                f"图片过大（{size_bytes} bytes）。"
                "Base64 方式建议原始文件小于 7MB。请裁剪或压缩后重试。"
            )

        mime = mimetypes.guess_type(str(img))[0] or "image/png"
        b64 = base64.b64encode(img.read_bytes()).decode("utf-8")
        image_url = f"data:{mime};base64,{b64}"

    try:
        vision_client = build_client()
        completion = vision_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            temperature=0.2,
            extra_body={"enable_thinking": ENABLE_THINKING},
        )
        content = completion.choices[0].message.content
        if isinstance(content, str):
            return content.strip() or "图像分析完成，但没有返回文本。"
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    txt = part.get("text")
                    if txt:
                        parts.append(str(txt))
            text = "\n".join(parts).strip()
            return text or "图像分析完成，但没有返回文本。"
        return "图像分析完成，但返回内容格式异常。"
    except Exception as e:
        return f"analyze_image 执行失败: {e}"


def chat():
    client = build_client()

    system_prompt = (
        "你是一个可以调用本地工具的助手。"
        "当用户问题需要真实系统信息、文件内容或命令执行结果时，优先调用 run_cli。"
        "当用户要求操作鼠标键盘时，调用 control_input。"
        "做屏幕定位时优先输出归一化坐标 x_norm/y_norm（范围 0 到 1），不要优先用像素坐标。"
        "点击动作后应进行状态确认（截图并分析），判断是否成功再继续下一步。"
        "如果实在没办法就如实反馈。"
        "当用户要求截图时，调用 take_screenshot。"
        "当用户要求你看图、读图、描述截图内容时，调用 analyze_image。"
        "如果用户说“截图看一下/截图后说说看到什么”，应先 take_screenshot，再 analyze_image。"
        "当用户需要联网查询、最新信息或外部资料时，调用 web_search。"
        "run_cli 复用同一个 shell 会话，命令之间的状态会保留。"
        "命令执行后，基于工具输出给出简洁、准确的中文回答。"
    )

    messages = [{"role": "system", "content": system_prompt}]

    tools = [
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
                "name": "control_input",
                "description": (
                    "控制鼠标和键盘。"
                    "action 可用: position, move, click, type, press, hotkey, scroll。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "x_norm": {
                            "type": "number",
                            "description": "归一化横坐标，范围 0 到 1（推荐）",
                        },
                        "y_norm": {
                            "type": "number",
                            "description": "归一化纵坐标，范围 0 到 1（推荐）",
                        },
                        "text": {"type": "string"},
                        "key": {"type": "string"},
                        "keys": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "amount": {"type": "integer"},
                        "button": {"type": "string"},
                        "clicks": {"type": "integer"},
                        "interval": {"type": "number"},
                        "duration": {"type": "number"},
                        "post_check": {
                            "type": "boolean",
                            "description": "点击后是否自动截图并分析，默认 true",
                        },
                        "vision_prompt": {
                            "type": "string",
                            "description": "点击后分析截图时使用的提示词",
                        },
                    },
                    "required": ["action"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "take_screenshot",
                "description": (
                    "截屏并保存图片。默认全屏；若提供 x,y,width,height 则区域截图。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "save_path": {"type": "string"},
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_image",
                "description": (
                    "分析图片内容。image_path 可传本地路径或 http/https URL；"
                    "不传时默认分析最近一次截图。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_path": {"type": "string"},
                        "prompt": {"type": "string"},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "联网搜索并返回结果列表（标题、链接、摘要）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
        },
    ]

    print("Body Agent 已启动。输入 /exit 退出，输入 /clear 清空历史。\n")

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
            for _ in range(MAX_TOOL_STEPS):
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.4,
                    extra_body={"enable_thinking": ENABLE_THINKING},
                )

                msg = response.choices[0].message
                tool_calls = msg.tool_calls or []

                if not tool_calls:
                    assistant_text = (msg.content or "").strip()
                    print(f"Agent: {assistant_text}\n")
                    messages.append({"role": "assistant", "content": assistant_text})
                    break

                # 先把 assistant 的 tool_call 消息记入上下文
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [tc.model_dump() for tc in tool_calls],
                    }
                )

                for tc in tool_calls:
                    print(tc)
                    name = tc.function.name
                    raw_args = tc.function.arguments or "{}"

                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {"command": raw_args}

                    if name == "run_cli":
                        tool_result = run_cli(args.get("command", ""))
                    elif name == "control_input":
                        tool_result = control_input(
                            action=str(args.get("action", "")),
                            x=_to_int(args.get("x")),
                            y=_to_int(args.get("y")),
                            x_norm=_to_float(args.get("x_norm"), None),
                            y_norm=_to_float(args.get("y_norm"), None),
                            text=args.get("text"),
                            key=args.get("key"),
                            keys=args.get("keys") if isinstance(args.get("keys"), list) else None,
                            amount=_to_int(args.get("amount")),
                            button=str(args.get("button", "left")),
                            clicks=max(1, _to_int(args.get("clicks"), 1) or 1),
                            interval=_to_float(args.get("interval"), 0.05),
                            duration=_to_float(args.get("duration"), 0.0),
                            post_check=_to_bool(args.get("post_check"), AUTO_SCREENSHOT_AFTER_CLICK),
                            vision_prompt=args.get("vision_prompt"),
                        )
                    elif name == "take_screenshot":
                        tool_result = take_screenshot(
                            save_path=args.get("save_path"),
                            x=_to_int(args.get("x")),
                            y=_to_int(args.get("y")),
                            width=_to_int(args.get("width")),
                            height=_to_int(args.get("height")),
                        )
                    elif name == "analyze_image":
                        tool_result = analyze_image(
                            image_path=args.get("image_path"),
                            prompt=str(
                                args.get("prompt", "请详细描述这张图里你看到了什么。")
                            ),
                        )
                    elif name == "web_search":
                        tool_result = web_search(
                            query=str(args.get("query", "")),
                            max_results=_to_int(args.get("max_results"), 5) or 5,
                        )
                    else:
                        tool_result = f"未知工具: {name}"

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": name,
                            "content": tool_result,
                        }
                    )
            else:
                print("Agent: 工具调用轮次超过上限，请重试或缩小问题范围。\n")

        except Exception as e:
            print(f"[请求失败] {e}\n")

    close_cli_session()


if __name__ == "__main__":
    chat()
