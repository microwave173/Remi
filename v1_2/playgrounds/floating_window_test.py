import argparse
import tkinter as tk
from datetime import datetime


def run_window(borderless: bool = False, topmost: bool = True) -> None:
    root = tk.Tk()
    root.title("Floating Window Test")
    root.geometry("420x220+120+120")
    root.configure(bg="#1f1f1f")

    if topmost:
        root.attributes("-topmost", True)
    if borderless:
        root.overrideredirect(True)

    def keep_topmost():
        if topmost and root.winfo_exists():
            root.attributes("-topmost", True)
            root.after(1500, keep_topmost)

    def start_drag(event):
        root._drag_x = event.x_root
        root._drag_y = event.y_root
        root._win_x = root.winfo_x()
        root._win_y = root.winfo_y()

    def do_drag(event):
        dx = event.x_root - root._drag_x
        dy = event.y_root - root._drag_y
        root.geometry(f"+{root._win_x + dx}+{root._win_y + dy}")

    title_bar = tk.Frame(root, bg="#2b2b2b", height=30)
    title_bar.pack(fill="x", side="top")
    title_label = tk.Label(
        title_bar,
        text="Remi Floating Test",
        bg="#2b2b2b",
        fg="#f0f0f0",
        anchor="w",
        padx=10,
    )
    title_label.pack(side="left", fill="x", expand=True)

    def on_close():
        root.destroy()

    close_btn = tk.Button(
        title_bar,
        text="×",
        bg="#2b2b2b",
        fg="#f0f0f0",
        relief="flat",
        bd=0,
        width=3,
        command=on_close,
    )
    close_btn.pack(side="right", padx=6, pady=2)

    for w in (title_bar, title_label):
        w.bind("<ButtonPress-1>", start_drag)
        w.bind("<B1-Motion>", do_drag)

    body = tk.Frame(root, bg="#1f1f1f")
    body.pack(fill="both", expand=True, padx=10, pady=10)

    output_var = tk.StringVar(value="窗口已启动")
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
        height=5,
    )
    output_box.pack(fill="x", pady=(0, 10))

    input_var = tk.StringVar()

    def on_send(event=None):
        text = input_var.get().strip()
        if not text:
            return
        now = datetime.now().strftime("%H:%M:%S")
        output_var.set(f"[{now}] 你输入了: {text}")
        input_var.set("")

    input_row = tk.Frame(body, bg="#1f1f1f")
    input_row.pack(fill="x")

    input_entry = tk.Entry(
        input_row,
        textvariable=input_var,
        bg="#2a2a2a",
        fg="#ffffff",
        insertbackground="#ffffff",
        relief="flat",
    )
    input_entry.pack(side="left", fill="x", expand=True, ipady=7)
    input_entry.bind("<Return>", on_send)

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

    hint = tk.Label(
        body,
        text=(
            "置顶: {} | 无边框: {} | 可拖拽: 标题栏\n"
            "若看不到窗口，请先试不加 --borderless"
        ).format(topmost, borderless),
        bg="#1f1f1f",
        fg="#9aa0a6",
        justify="left",
        anchor="w",
    )
    hint.pack(fill="x", pady=(10, 0))

    root.after(500, keep_topmost)
    input_entry.focus_set()

    print("Floating window test started")
    print(f"- topmost={topmost}")
    print(f"- borderless={borderless}")
    print("Close the window to exit.")

    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Floating window smoke test")
    parser.add_argument("--borderless", action="store_true", help="启用无边框模式")
    parser.add_argument("--no-topmost", action="store_true", help="关闭置顶")
    args = parser.parse_args()

    run_window(borderless=args.borderless, topmost=not args.no_topmost)


if __name__ == "__main__":
    main()
