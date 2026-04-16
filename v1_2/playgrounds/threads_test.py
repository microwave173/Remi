import threading
import time

input_cache = ""


def read_input():
    global input_cache
    while True:
        input_cache = input("请输入：")


def print_cache():
    global input_cache
    while True:
        if input_cache != "":
            print(f"input_cache = {input_cache}")
            input_cache = ""
        time.sleep(0.5)


if __name__ == "__main__":
    t1 = threading.Thread(target=read_input, daemon=True)
    t2 = threading.Thread(target=print_cache, daemon=True)

    t1.start()
    t2.start()

    while True:
        time.sleep(1)