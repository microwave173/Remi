import os
import subprocess
import threading
import time
import uuid
from select import select

PROJECT_ROOT = os.getenv("PROJECT_ROOT", "/Users/mabokai/Desktop/proj/Remi")


class ShellSession:
    """持久化 shell 会话，复用同一个 subprocess。"""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()

    def _is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        if self._is_alive():
            return
        self.proc = subprocess.Popen(
            ["/bin/bash"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
            bufsize=0,
            cwd=self.cwd,
        )

    def close(self) -> None:
        if not self.proc:
            return
        try:
            if self.proc.stdin:
                self.proc.stdin.write(b"exit\n")
                self.proc.stdin.flush()
        except Exception:
            pass

        try:
            self.proc.terminate()
            self.proc.wait(timeout=1.5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        finally:
            self.proc = None

    def execute(self, command: str, timeout: int = 20, max_chars: int = 8000) -> str:
        if not command.strip():
            return "命令为空。"

        with self.lock:
            self.start()
            if not self.proc or not self.proc.stdin or not self.proc.stdout:
                return "shell 会话初始化失败。"

            marker = f"__CMD_DONE_{uuid.uuid4().hex}__"
            wrapped = (
                f"{command}\n"
                f"printf '\\n{marker}%s\\n' \"$?\"\n"
            )
            marker_bytes = marker.encode("utf-8")

            try:
                self.proc.stdin.write(wrapped.encode("utf-8"))
                self.proc.stdin.flush()
            except Exception as e:
                self.close()
                return f"写入 shell 失败: {e}"

            output_buf = bytearray()
            exit_code = None
            deadline = time.monotonic() + timeout

            while True:
                remain = deadline - time.monotonic()
                if remain <= 0:
                    partial = output_buf.decode("utf-8", errors="replace").strip()
                    self.close()
                    if partial:
                        return (
                            f"命令执行超时（>{timeout}s），会话已重置。\n"
                            f"partial_output:\n{partial[:max_chars]}"
                        )
                    return f"命令执行超时（>{timeout}s），会话已重置。"

                ready, _, _ = select([self.proc.stdout], [], [], min(0.2, remain))
                if not ready:
                    continue

                chunk = os.read(self.proc.stdout.fileno(), 4096)
                if not chunk:
                    if self.proc.poll() is not None:
                        break
                    continue
                output_buf.extend(chunk)

                pos = output_buf.find(marker_bytes)
                if pos >= 0:
                    after = output_buf[pos + len(marker_bytes):]
                    nl = after.find(b"\n")
                    if nl < 0:
                        # marker 已出现但退出码未完整到达，继续读
                        continue
                    rc_text = after[:nl].decode("utf-8", errors="replace").strip()
                    try:
                        exit_code = int(rc_text)
                    except ValueError:
                        exit_code = -1
                    output_bytes = bytes(output_buf[:pos])
                    stdout_text = output_bytes.decode("utf-8", errors="replace").strip()
                    result = [f"exit_code: {exit_code if exit_code is not None else -1}"]
                    if stdout_text:
                        result.append(f"stdout:\n{stdout_text[:max_chars]}")
                    return "\n\n".join(result)

                if len(output_buf) > max_chars * 4:
                    output_buf.extend("\n[输出过长，已截断]\n".encode("utf-8"))
                    break

            stdout_text = bytes(output_buf).decode("utf-8", errors="replace").strip()
            result = [f"exit_code: {exit_code if exit_code is not None else -1}"]
            if stdout_text:
                result.append(f"stdout:\n{stdout_text[:max_chars]}")
            return "\n\n".join(result)


SHELL = ShellSession(cwd=PROJECT_ROOT)


def run_cli(command: str, timeout: int = 20) -> str:
    """执行本地命令行并返回输出（复用同一个 shell 会话）。"""
    return SHELL.execute(command=command, timeout=timeout, max_chars=8000)


def close_cli_session() -> None:
    """关闭持久 shell 会话。"""
    SHELL.close()


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


if __name__ == "__main__":
    print("=== tools.py 使用案例 ===")

    print("\n[1] CLI 工具示例：")
    print(run_cli("pwd"))
    print(run_cli("ls -la v1_0 | head"))

    print("\n[2] 联网搜索工具示例：")
    result = web_search("wayward 大黄", max_results=3)
    print(result)

    close_cli_session()
