# Hermes 子进程会话管理
# 通过 hermes chat -q --continue <session_id> 实现多轮对话

import os
import re
import subprocess
import json
import time
import threading

APP_PATH = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(APP_PATH, "history.json")
SESSION_FILE = os.path.join(APP_PATH, "session.id")

_session_id = None
_session_lock = threading.Lock()
_history = []          # [{"role": "user"/"hermes", "text": "..."}]
_history_loaded = False


def load_history():
    """加载历史记录(App 重启后可回看)。"""
    global _history, _history_loaded
    if _history_loaded:
        return _history
    _history_loaded = True
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                _history = json.load(f)
    except Exception as e:
        print(f"[history] load failed: {e}")
        _history = []
    return _history


def save_history():
    """保存历史记录。"""
    try:
        # 只保留最近 200 条,避免文件无限膨胀
        trimmed = _history[-200:]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"[history] save failed: {e}")


def get_session_id():
    global _session_id
    with _session_lock:
        if _session_id:
            return _session_id
        try:
            if os.path.exists(SESSION_FILE):
                with open(SESSION_FILE, "r") as f:
                    _session_id = f.read().strip()
        except Exception:
            pass
        return _session_id


def set_session_id(sid):
    global _session_id
    with _session_lock:
        _session_id = sid
        try:
            with open(SESSION_FILE, "w") as f:
                f.write(sid)
        except Exception as e:
            print(f"[session] save failed: {e}")


def extract_reply(output):
    """从 hermes chat 输出中提取助手回复正文。

    输出格式:
      ╭─ ⚕ Hermes ───────╮
      回复内容
      ╰───────────────────╯
    兼容多种边框/无边框格式。
    """
    if not output:
        return ""
    # 去掉 ANSI 转义序列
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", output)
    lines = [ln.rstrip("\r") for ln in text.split("\n")]

    # 找边框线: ╭ 开头 或 ╰ 开头 或 纯横线 ──
    start_idx = None
    end_idx = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("╭") or s.startswith("╔"):
            start_idx = i
        if s.startswith("╰") or s.startswith("╚"):
            end_idx = i
    if start_idx is not None and end_idx is not None and end_idx > start_idx:
        body = lines[start_idx + 1:end_idx]
    else:
        # 无边框:去掉已知的噪声行
        body = []
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if s.startswith("Initializing agent"):
                continue
            if s.startswith("↻ Resumed session") or s.startswith("Resume this session"):
                continue
            if s.startswith("Query:"):
                continue
            if s.startswith("Session:") or s.startswith("Duration:") or s.startswith("Messages:"):
                continue
            if s.startswith("─"):
                continue
            if re.match(r"^\d+ \([^)]*\)$", s):  # 会话统计
                continue
            body.append(s)

    reply = "\n".join(ln for ln in body if ln.strip()).strip()
    return reply


def ask(question, timeout=300):
    """向 Hermes 提问,返回 (回复文本, 错误信息)。多轮: 自动续接上次会话。"""
    sid = get_session_id()
    cmd = ["hermes", "chat", "-q", question, "--source", "cli"]
    if sid:
        cmd += ["--continue", sid]
    cmd += ["--max-turns", "4"]

    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    # 避免输出分页/交互干扰
    env["PAGER"] = "cat"
    env["TERM"] = "dumb"

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=APP_PATH,
        )
        output = proc.stdout or ""
        err = proc.stderr or ""
        reply = extract_reply(output)

        # 解析会话 ID(第一次提问时会生成)
        m = re.search(r"hermes --resume (\S+)", output) or \
            re.search(r"Session:\s+(\S+)", output)
        if m and not sid:
            set_session_id(m.group(1))

        if not reply and proc.returncode != 0:
            return "", f"hermes 返回错误({proc.returncode}): {err.strip()[:200]}"
        if not reply:
            return "", "未收到回复(可能是空输出)"

        return reply, None
    except subprocess.TimeoutExpired:
        return "", "请求超时(300s),请稍后重试"
    except FileNotFoundError:
        return "", "找不到 hermes 命令,请确认已安装"
    except Exception as e:
        return "", f"调用失败: {e}"


def add_message(role, text):
    _history.append({"role": role, "text": text})
    save_history()


def new_session():
    """清空会话,开启全新对话。"""
    global _session_id
    with _session_lock:
        _session_id = None
        try:
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
        except Exception:
            pass
