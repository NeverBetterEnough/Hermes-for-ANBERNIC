# Hermes 对话 App 主逻辑
# 软键盘系统复刻自 SimpleTerminal (st-sdl Anbernic fork) 的设计:
#   X=显示/隐藏键盘  Y=移动键盘位置  L1=Shift  R1=修饰键循环
#   START=回车(发送)  SELECT=Tab  B=退格  方向键选择  A=确认
#   A→hermes chat -q 子进程 → 多轮会话 → 历史回看

import os
import sys
import time
import threading
import atexit

from main import system_lang, hw_info
from graphic import UserInterface
import input
import agent_client
import rime_ime

gr = UserInterface()

# ---------------- 文案 ----------------
T = {
    "zh_CN": {
        "title": "Hermes 对话",
        "input_hint": "输入问题...",
        "sending": "思考中",
        "error": "错误",
        "new_session": "新对话",
        "keyboard": "键盘",
        "help": "方向键:选择  A:确认  B:退格  L1:Shift  R1:修饰  X:键盘  Y:位置  START:发送  SELECT:Tab",
        "help_no_kb": "X:显示键盘  L2/R2:滚动  B:退出",
        "mod_none": "普通",
        "mod_shift": "Shift",
        "mod_ctrl": "Ctrl",
        "mod_alt": "Alt",
        "kb_bottom": "底部",
        "kb_top": "顶部",
    },
    "en_US": {
        "title": "Hermes Chat",
        "input_hint": "Type a question...",
        "sending": "Thinking",
        "error": "Error",
        "new_session": "New Session",
        "keyboard": "Keyboard",
        "help": "D-pad:move  A:press  B:backspace  L1:Shift  R1:Mod  X:KB  Y:Pos  START:send  SELECT:Tab",
        "help_no_kb": "X:show KB  L2/R2:scroll  B:quit",
        "mod_none": "Normal",
        "mod_shift": "Shift",
        "mod_ctrl": "Ctrl",
        "mod_alt": "Alt",
        "kb_bottom": "Bottom",
        "kb_top": "Top",
    },
}


def get_text(key):
    """安全取文案:缺键不崩溃,记录日志并返回 key 本身。"""
    v = T.get(system_lang, T["zh_CN"]).get(key)
    if v is None:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.txt"), "a") as f:
                f.write(f"[WARN] missing text key: {key}\n")
        except Exception:
            pass
        v = T["zh_CN"].get(key, key)
    return v


class SafeTextDict(dict):
    """文案字典:访问缺失键时记录日志并回退中文/键名,绝不抛 KeyError。"""

    def __missing__(self, key):
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.txt"), "a") as f:
                f.write(f"[WARN] missing text key: {key}\n")
        except Exception:
            pass
        val = T["zh_CN"].get(key, key)
        self[key] = val
        return val


L = SafeTextDict(T.get(system_lang, T["zh_CN"]))

# ---------------- 软键盘布局(10 列,复刻 st-sdl 风格) ----------------
# 键值: 单字符=输入该字符; 特殊键用标签
PAGE_MAIN = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
    ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
    ["A", "S", "D", "F", "G", "H", "J", "K", "L", "BK"],
    ["Z", "X", "C", "V", "B", "N", "M", ",", ".", "/"],
    ["?1", "SP", "SP", "SP", "IM", "CLR", "-", "_", "CAPS", "SEND"],
]
PAGE_SYM = [
    ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"],
    ["[", "]", "{", "}", "|", "\\", ":", ";", "'", '"'],
    ["+", "=", "-", "_", "<", ">", "?", "/", "~", "`"],
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
    ["abc", "SP", "SP", "SP", "IM", "CLR", "-", "_", "CAPS", "SEND"],
]
PAGE_SPEC = [
    ["↑", "↓", "←", "→", "↔", "①", "②", "③", "④", "⑤"],
    ["─", "┌", "┐", "└", "┘", "├", "┤", "┬", "┴", "│"],
    ["°", "±", "≤", "≥", "≠", "π", "√", "∞", "≈", "×"],
    ["♥", "★", "☆", "●", "○", "■", "□", "◆", "◇", "·"],
    ["abc", "SP", "SP", "SP", "IM", "CLR", "-", "_", "CAPS", "SEND"],
]
PAGES = [PAGE_MAIN, PAGE_SYM, PAGE_SPEC]
PAGE_NAMES = ["ABC", "SYM", "SPC"]

SPECIAL_KEYS = {
    "SP": " ",
    "BK": "\b",
    "SEND": "\n",
    "CLR": None,
    "CAPS": None,
    "IM": None,        # 中/英 输入法切换
    "?1": None,
    "abc": None,
}

MOD_LABELS = ["mod_none", "mod_shift", "mod_ctrl", "mod_alt"]
MOD_MAP = {"CAPS": 1, "CTRL": 2, "ALT": 3}  # R1 循环: 无→Shift→Ctrl→Alt→无

# ---------------- 状态 ----------------
kb_page = 0          # 0=主 1=符号 2=特殊
kb_row = 0
kb_col = 0
kb_visible = True    # X 切换
kb_top = False       # Y 切换位置
shift_on = False     # L1 / CAPS
modifier = 0         # 0=无 1=Shift 2=Ctrl 3=Alt (R1 循环)
input_text = ""
reply_text = ""
reply_error = None
busy = False
status_msg = ""
status_timer = 0
history_scroll = 0
exit_flag = False
kb_lock = False      # 防止一次按键重复触发

# ---------------- Rime 中文输入法 ----------------
im_mode = False      # False=英文直输 True=中文拼音
im_ready = rime_ime.init()   # 启动即初始化,失败则降级英文输入
if not im_ready:
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.txt"), "a") as f:
            f.write(f"[RIME] init failed: {rime_ime.init_error()}\n")
    except Exception:
        pass

# 退出兜底:不调 RimeFinalize 的话,进程退出时 librime 静态析构会段错误
atexit.register(rime_ime.finalize)

HISTORY = agent_client.load_history()

FONT_CACHE = {}

def get_font(size):
    if size not in FONT_CACHE:
        from PIL import ImageFont
        FONT_CACHE[size] = ImageFont.truetype("/mnt/vendor/bin/default.ttf", size)
    return FONT_CACHE[size]


# ---------------- 软键盘操作 ----------------
def current_kb():
    return PAGES[kb_page]


def kb_key(row, col):
    grid = current_kb()
    if 0 <= row < len(grid) and 0 <= col < len(grid[row]):
        return grid[row][col]
    return None


def kb_move(dr, dc):
    global kb_row, kb_col
    grid = current_kb()
    rows, cols = len(grid), len(grid[0])
    nr, nc = kb_row, kb_col
    for _ in range(rows * cols):
        nr = (nr + dr) % rows
        nc = (nc + dc) % cols
        if kb_key(nr, nc) is not None:
            kb_row, kb_col = nr, nc
            return


def shift_char(c):
    """Shift 作用于字母和常用符号。"""
    if c.isalpha():
        return c.upper() if shift_on else c.lower()
    return c


def apply_modifier(c):
    """修饰键影响输入字符(主要作用于字母)。"""
    global modifier
    if modifier == 2 and c.isalpha():   # Ctrl
        return chr(ord(c.upper()) - ord('A') + 1) if c.upper() in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' else c
    if modifier == 3:                    # Alt 对文本输入无实际效果,直接返回
        return c
    return c


def commit_ime_text():
    """把 Rime 上屏的文本追加到输入框。"""
    global input_text
    t = rime_ime.commit_text()
    if t:
        input_text += t


def kb_press():
    global input_text, kb_page, kb_row, kb_col, shift_on, modifier
    global reply_text, reply_error, busy, status_msg, status_timer, history_scroll
    global im_mode
    k = kb_key(kb_row, kb_col)
    if k is None:
        return

    # 中/英切换键
    if k == "IM":
        im_mode = not im_mode
        if not im_mode and rime_ime.is_ready():
            rime_ime.clear()
        set_status("中" if im_mode else "EN")
        return

    # 中文拼音模式:字母/数字/标点/功能键交给 Rime
    if im_mode and rime_ime.is_ready():
        composing = rime_ime.is_composing()
        if k == "BK":
            if composing:
                rime_ime.process_key(rime_ime.K_BACKSPACE, 0)
            else:
                input_text = input_text[:-1]
            return
        if k == "SP":
            if composing:
                rime_ime.process_key(rime_ime.K_SPACE, 0)
                commit_ime_text()
            else:
                input_text += " "
            return
        if k == "SEND":
            if composing:
                rime_ime.commit_composition()
                commit_ime_text()
            send_question()
            return
        if k == "CLR":
            if composing:
                rime_ime.clear()
            input_text = ""
            return
        if k in "1234567890" and composing:
            n = int(k) - 1
            if n < len(rime_ime.candidates()):
                rime_ime.select(n)
                commit_ime_text()
            return
        if k in ".,/?!;:'\"-()[]{}<>@#$%^&*_+=|\\~`" and composing:
            # 拼音态输入标点:直通 Rime(自动转中文标点,如 , → ，)
            rime_ime.process_char(k)
            commit_ime_text()
            return
        if k.isalpha():
            rime_ime.process_char(k.lower())
            return

    if k == "BK":
        input_text = input_text[:-1]
    elif k == "SEND":
        send_question()
    elif k == "CLR":
        input_text = ""
    elif k == "CAPS":
        shift_on = not shift_on
        modifier = 1 if shift_on else 0
    elif k == "?1":
        kb_page = (kb_page + 1) % len(PAGES)
        kb_row, kb_col = 0, 0
    elif k == "abc":
        kb_page = 0
        kb_row, kb_col = 0, 0
    elif k == "SP":
        input_text += " "
    else:
        c = shift_char(k)
        c = apply_modifier(c)
        if c == "\b":
            input_text = input_text[:-1]
        elif c == "\n":
            send_question()
        else:
            input_text += c
        # 单字符输入后自动退出 Shift
        if shift_on and k.isalpha():
            shift_on = False
            modifier = 0


def set_status(msg):
    global status_msg, status_timer
    status_msg = msg
    status_timer = time.time()


# ---------------- Hermes 调用 ----------------
def send_question():
    global busy, reply_text, reply_error, status_msg, status_timer, history_scroll, input_text
    q = input_text.strip()
    if not q or busy:
        return
    input_text = ""
    # 发送后自动滚动到最新消息(render 会把超大值钳制到底部)。
    # 之前 history_scroll=0 固定置顶,历史一多新消息就画在屏幕外,
    # 表现为"思考完但没有新增回答"。
    history_scroll = 1 << 30
    busy = True
    set_status(L["sending"])
    agent_client.add_message("user", q)

    def worker():
        global busy, reply_text, reply_error, status_msg, status_timer, history_scroll
        try:
            reply, err = agent_client.ask(q)
            if err:
                reply_error = err
                reply_text = ""
                agent_client.add_message("hermes", f"[{L['error']}] {err}")
            else:
                reply_error = None
                reply_text = reply
                agent_client.add_message("hermes", reply)
                # 回答写入后滚动到最新,保证回复可见
                history_scroll = 1 << 30
        finally:
            busy = False
            set_status("")

    threading.Thread(target=worker, daemon=True).start()


def start():
    gr.draw_log(f"{L['title']}...", fill=gr.colorBlue, outline=gr.colorBlueD1)
    gr.draw_paint()
    time.sleep(1.2)
    if HISTORY:
        last = HISTORY[-1]
        if last["role"] == "hermes":
            reply_text = last["text"]
        elif last["role"] == "user":
            reply_text = ""


def est_lines(t):
    n = 0
    for para in t.split("\n"):
        n += max(1, (len(para) + 28) // 29)
    return n


# ---------------- 主循环 ----------------
def update():
    global exit_flag, input_text, reply_text, reply_error, status_msg
    global kb_row, kb_col, kb_page, kb_visible, kb_top, shift_on, modifier
    global history_scroll, kb_lock

    # 每 tick 处理完队列里所有排队的按键
    # (input.check 的 fd 常开,事件排队不丢;连按快速输入也能全部生效)
    while input.check() and not exit_flag:
        k = input.codeName
        v = input.value

        if k == "MENUF":
            exit_flag = True
        elif k == "B":
            # 中文拼音态:B 先删拼音,再退输入框
            if im_mode and rime_ime.is_ready() and rime_ime.is_composing():
                rime_ime.process_key(rime_ime.K_BACKSPACE, 0)
            elif input_text:
                input_text = input_text[:-1]
            elif not kb_visible:
                exit_flag = True
        elif k == "A":
            if kb_visible:
                if im_mode and rime_ime.is_ready() and rime_ime.is_composing():
                    # 拼音态:A 上屏高亮候选
                    idx = rime_ime.highlighted_index()
                    rime_ime.select(idx if idx >= 0 else 0)
                    commit_ime_text()
                else:
                    kb_press()
        elif k == "L1":
            if im_mode and rime_ime.is_ready() and rime_ime.is_composing():
                rime_ime.process_key(rime_ime.K_PAGEUP, 0)   # 候选上一页
            else:
                shift_on = not shift_on
                modifier = 1 if shift_on else 0
                set_status(L["mod_shift"] if shift_on else L["mod_none"])
        elif k == "R1":
            if im_mode and rime_ime.is_ready() and rime_ime.is_composing():
                rime_ime.process_key(rime_ime.K_PAGEDOWN, 0) # 候选下一页
            else:
                modifier = (modifier + 1) % 4
                shift_on = (modifier == 1)
                set_status(MOD_LABELS[modifier])
        elif k == "START":
            if im_mode and rime_ime.is_ready() and rime_ime.is_composing():
                rime_ime.commit_composition()
                commit_ime_text()
            send_question()
        elif k == "SELECT":
            input_text += "\t"
        elif k == "X":
            if im_mode and rime_ime.is_ready() and rime_ime.is_composing():
                rime_ime.clear()   # 先取消拼音再收键盘
            kb_visible = not kb_visible
            set_status(L["keyboard"] if kb_visible else L["help_no_kb"])
        elif k == "Y":
            kb_top = not kb_top
            set_status(L["kb_top"] if kb_top else L["kb_bottom"])
        elif k == "L2" and not kb_visible:
            history_scroll = max(0, history_scroll - 3)
        elif k == "R2" and not kb_visible:
            history_scroll += 3
        elif k == "DY":
            # value: +1=下, -1=上
            if kb_visible:
                kb_move(v, 0)
            else:
                history_scroll = max(0, history_scroll + v)
        elif k == "DX":
            # value: +1=右, -1=左
            if kb_visible:
                if im_mode and rime_ime.is_ready() and rime_ime.is_composing():
                    # 拼音态:左右移动候选高亮
                    rime_ime.process_key(
                        rime_ime.K_LEFT if v < 0 else rime_ime.K_RIGHT, 0
                    )
                else:
                    kb_move(0, v)
        elif k == "UP":
            if kb_visible:
                kb_move(-1, 0)
            else:
                history_scroll = max(0, history_scroll - 1)
        elif k == "DOWN":
            if kb_visible:
                kb_move(1, 0)
            else:
                history_scroll += 1
        elif k == "LEFT":
            if kb_visible:
                if im_mode and rime_ime.is_ready() and rime_ime.is_composing():
                    rime_ime.process_key(rime_ime.K_LEFT, 0)
                else:
                    kb_move(0, -1)
        elif k == "RIGHT":
            if kb_visible:
                if im_mode and rime_ime.is_ready() and rime_ime.is_composing():
                    rime_ime.process_key(rime_ime.K_RIGHT, 0)
                else:
                    kb_move(0, 1)

    render()


# ---------------- 渲染 ----------------
def render():
    global history_scroll
    gr.draw_start()
    gr.draw_clear()

    W = gr.screen_width
    H = gr.screen_height

    # 顶部标题栏
    gr.draw_rectangle([0, 0, W, 30], fill=gr.colorBlueD1)
    gr.draw_text((8, 3), L["title"], font=21, color="#ffff00")
    right_info = ""
    if kb_visible:
        right_info = f"{PAGE_NAMES[kb_page]} {MOD_LABELS[modifier]}"
    if im_mode:
        right_info = f"中 {right_info}".strip()
    sid = agent_client.get_session_id()
    if sid:
        right_info = f"{right_info} #{sid[-6:]}".strip()
    if right_info:
        gr.draw_text((W - 10, 5), right_info, font=13, anchor="ra")

    # 中文拼音态(候选条占用输入框上方 28px)
    composing = im_mode and rime_ime.is_ready() and rime_ime.is_composing()

    # 键盘占据的空间
    kb_h = 5 * 36 + 8   # 5 行 × 36px + 边距
    if kb_visible:
        if kb_top:
            kb_y0 = 34
            conv_top = 34 + kb_h + 4
            conv_bottom = H - 4
        else:
            kb_y0 = H - kb_h - 4
            conv_top = 34
            conv_bottom = kb_y0 - 38   # 输入框占 34px
        if composing:
            conv_bottom -= 28          # 给候选条让位
    else:
        kb_y0 = None
        conv_top = 34
        conv_bottom = H - 4

    # 对话区
    gr.draw_rectangle_r([4, conv_top, W - 4, conv_bottom], 8,
                        fill="#141414", outline=gr.colorBlueD1)

    items = list(HISTORY)
    line_h = 20
    max_h = conv_bottom - conv_top - 12
    total_est = sum(est_lines(m["text"]) + 1 for m in items)
    visible = max(1, max_h // line_h)
    history_scroll = max(0, min(history_scroll, max(0, total_est - visible)))

    y = conv_top + 6
    skip = history_scroll
    for m in items:
        label = "你: " if m["role"] == "user" else "Hermes: "
        color = "#00d7ff" if m["role"] == "user" else "#ffffff"
        m_lines = est_lines(m["text"])
        if skip > 0:
            skip -= (m_lines + 1)
            continue
        if y > conv_bottom - line_h:
            break
        gr.draw_text((10, y), label + m["text"][:300], font=15, color=color)
        y += line_h * (m_lines + 1)

    # 输入框
    if kb_visible:
        ib_y = conv_bottom + (30 if composing else 4)
        gr.draw_rectangle_r([4, ib_y, W - 4, ib_y + 30], 6,
                            fill="#1a1a2e", outline=gr.colorBlue)
        if composing:
            # 拼音态:已上屏文本 + 绿色拼音串
            py = rime_ime.composition()
            gr.draw_text((12, ib_y + 5), input_text, font=16, color="#ffffff")
            if py:
                w = get_font(16).getlength(input_text)
                gr.draw_text((14 + w, ib_y + 5), py, font=16, color="#00ff00")
                w2 = get_font(16).getlength(py)
                gr.draw_rectangle([14 + w + w2, ib_y + 6, 16 + w + w2, ib_y + 24],
                                  fill="#00ff00")
        else:
            hint = L["input_hint"] if not input_text else input_text
            gr.draw_text((12, ib_y + 5), hint, font=16,
                         color="#888888" if not input_text else "#ffffff")
            # 光标
            if input_text:
                w = get_font(16).getlength(input_text)
                gr.draw_rectangle([14 + w, ib_y + 6, 16 + w, ib_y + 24], fill="#00ff00")

        # 状态
        if busy:
            dots = "." * (int(time.time() * 2) % 4)
            gr.draw_text((W - 12, ib_y + 5), L["sending"] + dots, font=14,
                         color=gr.colorYellow, anchor="ra")
        elif status_msg and time.time() - status_timer < 3:
            gr.draw_text((W - 12, ib_y + 5), status_msg, font=14,
                         color=gr.colorGreen, anchor="ra")
    else:
        # 无键盘时底部提示
        gr.draw_text((10, H - 26), L["help_no_kb"], font=14, color=gr.colorGrayL2)

    # 中文候选条(输入框与键盘之间)
    if composing:
        cands = rime_ime.candidates()
        hl = rime_ime.highlighted_index()
        if hl < 0:
            hl = 0
        py = rime_ime.composition()
        cy0 = conv_bottom + 2
        gr.draw_rectangle_r([4, cy0, W - 4, cy0 + 26], 6,
                            fill="#0d1b2a", outline="#00d7ff")
        gr.draw_text((10, cy0 + 5), "中", font=15, color="#ffd700")
        x = 36
        if py:
            gr.draw_text((x, cy0 + 5), py, font=15, color="#00ff00")
            x += int(get_font(15).getlength(py)) + 16
        for i, (text, _cm) in enumerate(cands[:7]):
            label = f"{i + 1}.{text}"
            lw = int(get_font(15).getlength(label))
            if i == hl:
                gr.draw_rectangle([x - 2, cy0 + 2, x + lw + 4, cy0 + 24],
                                  fill="#3d3d00")
                gr.draw_text((x, cy0 + 5), label, font=15, color="#ffff00")
            else:
                gr.draw_text((x, cy0 + 5), label, font=15, color="#bbbbbb")
            x += lw + 14
            if x > W - 40:
                break

    # 软键盘
    if kb_visible:
        draw_keyboard(kb_y0)

    gr.draw_paint()


def draw_keyboard(y0):
    grid = current_kb()
    rows = len(grid)
    cols = len(grid[0])
    key_w = (gr.screen_width - 12) // cols
    key_h = 34

    # 键盘背景
    gr.draw_rectangle_r([2, y0 - 4, gr.screen_width - 2, y0 + rows * key_h + 2], 8,
                        fill="#0a0a14", outline=gr.colorBlueD1)

    for r in range(rows):
        for c in range(cols):
            k = grid[r][c]
            if k is None:
                continue
            x = 6 + c * key_w
            y = y0 + r * key_h
            selected = (r == kb_row and c == kb_col)

            if selected:
                gr.draw_rectangle_r([x + 1, y + 1, x + key_w - 2, y + key_h - 2],
                                    6, fill=gr.colorBlue, outline="#00d7ff")
            else:
                gr.draw_rectangle_r([x + 1, y + 1, x + key_w - 2, y + key_h - 2],
                                    6, fill=gr.colorGrayL1, outline=gr.colorGrayD2)

            label = k
            color = "#ffffff"
            if k == "SP":
                label = "SPACE"
                color = "#bbbbbb"
            elif k == "BK":
                label = "⌫"
            elif k == "SEND":
                label = "⏎"
                color = "#ffff00"
            elif k == "CLR":
                label = "C"
                color = "#ffff00"
            elif k == "CAPS":
                label = "⇧"
                color = gr.colorGreen if shift_on else "#ffff00"
            elif k == "?1":
                label = "ABC" if kb_page == 0 else ("SYM" if kb_page == 1 else "SPC")
                color = "#ffd700"
            elif k == "abc":
                label = "ABC"
                color = "#ffd700"
            elif k == "IM":
                label = "中" if im_mode else "EN"
                color = gr.colorGreen if im_mode else "#bbbbbb"

            gr.active_draw.text((x + key_w // 2, y + key_h // 2), label,
                                font=get_font(15), fill=color, anchor="mm")


def cleanup():
    agent_client.save_history()
