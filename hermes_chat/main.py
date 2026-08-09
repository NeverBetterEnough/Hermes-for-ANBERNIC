#!/usr/bin/env python3
# Hermes 对话 - 掌机客户端
# 通过子进程调用 hermes chat -q 与 Hermes 对话

import zipfile
import os
import sys
import traceback
from pathlib import Path

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.txt")

board_mapping = {
    'RGcubexx': 1,
    'RG34xx': 2,
    'RG34xxSP': 2,
    'RG28xx': 3,
    'RG35xx+_P': 4,
    'RG35xxH': 5,
    'RG35xxSP': 6,
    'RG40xxH': 7,
    'RG40xxV': 8,
    'RG35xxPRO': 9
}
system_list = ['zh_CN', 'zh_TW', 'en_US', 'ja_JP', 'ko_KR', 'es_LA', 'ru_RU', 'de_DE', 'fr_FR', 'pt_BR']

try:
    board_info = Path("/mnt/vendor/oem/board.ini").read_text().splitlines()[0]
except (FileNotFoundError, IndexError):
    board_info = 'RG35xxH'

try:
    lang_info = Path("/mnt/vendor/oem/language.ini").read_text().splitlines()[0]
except (FileNotFoundError, IndexError):
    lang_info = 2
try:
    hdmi_info = Path("/sys/class/extcon/hdmi/state").read_text().splitlines()[0]
except (FileNotFoundError, IndexError):
    hdmi_info = 'HDMI=0'

hw_info = board_mapping.get(board_info, 5)
system_lang = system_list[int(lang_info)]


def log(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def ensure_sdl2():
    try:
        import sdl2
        return True
    except ImportError:
        try:
            program = os.path.dirname(os.path.abspath(__file__))
            module_file = os.path.join(program, "sdl2.zip")
            with zipfile.ZipFile(module_file, 'r') as zip_ref:
                zip_ref.extractall("/")
            print("Successfully installed sdl2")
            return True
        except Exception as e:
            print(f"Failed to install sdl2: {e}")
            return False


def main():
    if ensure_sdl2():
        import app
    else:
        log("[FATAL] sdl2 unavailable")
        return

    # 全局异常捕获: 崩溃前写 traceback 到 log.txt,并在屏幕上显示
    try:
        app.start()
        import time as _time
        frame_interval = 0.1   # 100ms 节拍 = 10fps 定时刷新
        while True:
            t0 = _time.time()
            app.update()
            if app.exit_flag:
                break
            # 固定节拍: 补偿渲染耗时,保证稳定 ~10fps
            elapsed = _time.time() - t0
            if elapsed < frame_interval:
                _time.sleep(frame_interval - elapsed)
        app.cleanup()
    except SystemExit:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        log(f"[CRASH] {tb}")
        try:
            # 屏幕上显示错误,停留几秒再退出
            app.gr.draw_start()
            app.gr.draw_clear()
            app.gr.draw_log(f"Error: {e}", fill=app.gr.colorRed, outline="black", width=540)
            lines = tb.strip().split("\n")
            err_lines = [ln for ln in lines if "line" in ln or "Error" in ln]
            y = app.gr.screen_height // 2 + 60
            for ln in err_lines[-4:]:
                app.gr.draw_text((app.gr.screen_width // 2 - 270, y), ln.strip()[:80], font=14)
                y += 20
            app.gr.draw_paint()
            import time
            time.sleep(6)
            app.gr.draw_end()
        except Exception as e2:
            log(f"[CRASH-RENDER] {e2}")
        raise


if __name__ == "__main__":
    main()
