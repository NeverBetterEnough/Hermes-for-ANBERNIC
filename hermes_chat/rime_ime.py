# Rime 中文输入法引擎封装 (librime 1.7.3)
# 通过 ctypes 直接调用 librime 导出函数,零第三方 Python 依赖。
# 软键盘输入拼音 → Rime 返回候选 → 上屏汉字。

import ctypes
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DIR = os.path.join(APP_DIR, "rime")     # 用户目录(可写):方案状态、日志
SHARED_DIR = "/usr/share/rime-data"          # 系统目录(只读):方案 + 预编译词库
PREBUILT_DIR = os.path.join(SHARED_DIR, "build")

# X11 keysym(Rime 键码)
K_BACKSPACE = 0xFF08
K_TAB = 0xFF09
K_RETURN = 0xFF0D
K_ESCAPE = 0xFF1B
K_LEFT = 0xFF51
K_UP = 0xFF52
K_RIGHT = 0xFF53
K_DOWN = 0xFF54
K_HOME = 0xFF50
K_END = 0xFF57
K_PAGEUP = 0xFF55
K_PAGEDOWN = 0xFF56
K_SPACE = 0x20


class RimeComposition(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_int),
        ("cursor_pos", ctypes.c_int),
        ("sel_start", ctypes.c_int),
        ("sel_end", ctypes.c_int),
        ("preedit", ctypes.c_char_p),
    ]


class RimeCandidate(ctypes.Structure):
    _fields_ = [
        ("text", ctypes.c_char_p),
        ("comment", ctypes.c_char_p),
        ("reserved", ctypes.c_void_p),
    ]


class RimeMenu(ctypes.Structure):
    _fields_ = [
        ("page_size", ctypes.c_int),
        ("page_no", ctypes.c_int),
        ("is_last_page", ctypes.c_int),
        ("highlighted_candidate_index", ctypes.c_int),
        ("num_candidates", ctypes.c_int),
        ("candidates", ctypes.POINTER(RimeCandidate)),
        ("select_keys", ctypes.c_char_p),
    ]


class RimeContext(ctypes.Structure):
    _fields_ = [
        ("data_size", ctypes.c_int),
        ("composition", RimeComposition),
        ("menu", RimeMenu),
        ("commit_text_preview", ctypes.c_char_p),
        ("select_labels", ctypes.POINTER(ctypes.c_char_p)),
    ]


class RimeCommit(ctypes.Structure):
    _fields_ = [
        ("data_size", ctypes.c_int),
        ("text", ctypes.c_char_p),
    ]


class RimeStatus(ctypes.Structure):
    _fields_ = [
        ("data_size", ctypes.c_int),
        ("schema_id", ctypes.c_char_p),
        ("schema_name", ctypes.c_char_p),
        ("is_disabled", ctypes.c_int),
        ("is_composing", ctypes.c_int),
        ("is_ascii_mode", ctypes.c_int),
        ("is_full_shape", ctypes.c_int),
        ("is_simplified", ctypes.c_int),
        ("is_traditional", ctypes.c_int),
        ("is_ascii_punct", ctypes.c_int),
    ]


class RimeTraits(ctypes.Structure):
    _fields_ = [
        ("data_size", ctypes.c_int),
        ("shared_data_dir", ctypes.c_char_p),
        ("user_data_dir", ctypes.c_char_p),
        ("distribution_name", ctypes.c_char_p),
        ("distribution_code_name", ctypes.c_char_p),
        ("distribution_version", ctypes.c_char_p),
        ("app_name", ctypes.c_char_p),
        ("modules", ctypes.POINTER(ctypes.c_char_p)),
        ("min_log_level", ctypes.c_int),
        ("log_dir", ctypes.c_char_p),
        ("prebuilt_data_dir", ctypes.c_char_p),
        ("staging_dir", ctypes.c_char_p),
    ]


_lib = None
_session = 0
_ready = False
_init_error = ""


def _load():
    global _lib
    if _lib is not None:
        return True
    for name in ("librime.so.1", "librime.so"):
        try:
            _lib = ctypes.CDLL(name)
            return True
        except OSError:
            continue
    return False


def _set_argtypes():
    P = ctypes.POINTER
    _lib.RimeSetup.argtypes = [P(RimeTraits)]
    _lib.RimeSetup.restype = None
    _lib.RimeInitialize.argtypes = [P(RimeTraits)]
    _lib.RimeInitialize.restype = None
    _lib.RimeFinalize.argtypes = []
    _lib.RimeFinalize.restype = None
    _lib.RimeCreateSession.restype = ctypes.c_ulong
    _lib.RimeDestroySession.argtypes = [ctypes.c_ulong]
    _lib.RimeDestroySession.restype = None
    _lib.RimeProcessKey.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_int]
    _lib.RimeProcessKey.restype = ctypes.c_int
    _lib.RimeGetContext.argtypes = [ctypes.c_ulong, P(RimeContext)]
    _lib.RimeGetContext.restype = ctypes.c_int
    _lib.RimeFreeContext.argtypes = [P(RimeContext)]
    _lib.RimeFreeContext.restype = None
    _lib.RimeGetCommit.argtypes = [ctypes.c_ulong, P(RimeCommit)]
    _lib.RimeGetCommit.restype = ctypes.c_int
    _lib.RimeFreeCommit.argtypes = [P(RimeCommit)]
    _lib.RimeFreeCommit.restype = None
    _lib.RimeCommitComposition.argtypes = [ctypes.c_ulong]
    _lib.RimeCommitComposition.restype = ctypes.c_int
    _lib.RimeGetStatus.argtypes = [ctypes.c_ulong, P(RimeStatus)]
    _lib.RimeGetStatus.restype = ctypes.c_int
    _lib.RimeFreeStatus.argtypes = [P(RimeStatus)]
    _lib.RimeFreeStatus.restype = None
    _lib.RimeSetOption.argtypes = [ctypes.c_ulong, ctypes.c_char_p, ctypes.c_int]
    _lib.RimeSetOption.restype = ctypes.c_int
    _lib.RimeSelectSchema.argtypes = [ctypes.c_ulong, ctypes.c_char_p]
    _lib.RimeSelectSchema.restype = ctypes.c_int
    # C++ 导出符号 (RimeSelectCandidate(RimeSessionId, size_t))
    _lib.RimeSelectCandidate = getattr(
        _lib, "_Z19RimeSelectCandidatemm"
    )
    _lib.RimeSelectCandidate.argtypes = [ctypes.c_ulong, ctypes.c_size_t]
    _lib.RimeSelectCandidate.restype = ctypes.c_int


def init(schema="luna_pinyin_simp"):
    """初始化 Rime。失败返回 False,错误原因见 init_error()。"""
    global _session, _ready, _init_error
    if _ready:
        return True
    if not _load():
        _init_error = "找不到 librime.so,请先 apt install librime1"
        return False
    try:
        _set_argtypes()
    except (AttributeError, OSError) as e:
        _init_error = f"librime 符号加载失败: {e}"
        return False

    try:
        os.makedirs(USER_DIR, exist_ok=True)
    except OSError as e:
        _init_error = f"无法创建 rime 用户目录: {e}"
        return False

    traits = RimeTraits()
    traits.data_size = ctypes.sizeof(RimeTraits)
    traits.shared_data_dir = SHARED_DIR.encode()
    traits.user_data_dir = USER_DIR.encode()
    traits.distribution_name = b"Rime"
    traits.distribution_code_name = b"Hermes Chat"
    traits.distribution_version = b"1.7.3"
    traits.app_name = b"rime.hermes_chat"
    traits.min_log_level = 3  # 只留 FATAL
    traits.log_dir = b"/tmp"
    traits.prebuilt_data_dir = PREBUILT_DIR.encode()
    traits.staging_dir = (os.path.join(USER_DIR, "build")).encode()

    try:
        _lib.RimeSetup(ctypes.byref(traits))
        _lib.RimeInitialize(ctypes.byref(traits))
    except Exception as e:
        _init_error = f"RimeInitialize 失败: {e}"
        return False

    _session = _lib.RimeCreateSession()
    if not _session:
        _init_error = "RimeCreateSession 失败"
        return False
    _lib.RimeSelectSchema(_session, schema.encode())
    # 简体中文 + 中文标点
    _lib.RimeSetOption(_session, b"ascii_mode", 0)
    _lib.RimeSetOption(_session, b"ascii_punct", 0)
    _lib.RimeSetOption(_session, b"simplification", 1)
    _ready = True
    return True


def init_error():
    return _init_error


def is_ready():
    return _ready


def process_key(keycode, mask=0):
    """把按键交给 Rime。返回 True 表示按键已被输入法消费。"""
    if not _ready:
        return False
    try:
        return bool(_lib.RimeProcessKey(_session, keycode, mask))
    except Exception:
        return False


def process_char(ch):
    """输入一个可见字符(字母/数字/标点)。"""
    return process_key(ord(ch), 0)


def composition():
    """当前拼音串(如 'ni hao')。无则返回空串。"""
    if not _ready:
        return ""
    ctx = RimeContext()
    ctx.data_size = ctypes.sizeof(RimeContext)
    if not _lib.RimeGetContext(_session, ctypes.byref(ctx)):
        return ""
    try:
        preedit = ctx.composition.preedit
        return preedit.decode("utf-8", "replace") if preedit else ""
    finally:
        _lib.RimeFreeContext(ctypes.byref(ctx))


def candidates():
    """当前候选列表 [(文本, 注释), ...]。"""
    if not _ready:
        return []
    ctx = RimeContext()
    ctx.data_size = ctypes.sizeof(RimeContext)
    if not _lib.RimeGetContext(_session, ctypes.byref(ctx)):
        return []
    try:
        menu = ctx.menu
        if menu.num_candidates <= 0 or not menu.candidates:
            return []
        out = []
        for i in range(menu.num_candidates):
            cand = menu.candidates[i]
            text = cand.text.decode("utf-8", "replace") if cand.text else ""
            comment = cand.comment.decode("utf-8", "replace") if cand.comment else ""
            out.append((text, comment))
        return out
    finally:
        _lib.RimeFreeContext(ctypes.byref(ctx))


def highlighted_index():
    """当前高亮候选下标(-1 无)。"""
    if not _ready:
        return -1
    ctx = RimeContext()
    ctx.data_size = ctypes.sizeof(RimeContext)
    if not _lib.RimeGetContext(_session, ctypes.byref(ctx)):
        return -1
    try:
        return ctx.menu.highlighted_candidate_index
    finally:
        _lib.RimeFreeContext(ctypes.byref(ctx))


def page_no():
    if not _ready:
        return 0
    ctx = RimeContext()
    ctx.data_size = ctypes.sizeof(RimeContext)
    if not _lib.RimeGetContext(_session, ctypes.byref(ctx)):
        return 0
    try:
        return ctx.menu.page_no
    finally:
        _lib.RimeFreeContext(ctypes.byref(ctx))


def commit_text():
    """取回上屏文本(调用后清空)。返回 str。"""
    if not _ready:
        return ""
    c = RimeCommit()
    c.data_size = ctypes.sizeof(RimeCommit)
    if not _lib.RimeGetCommit(_session, ctypes.byref(c)):
        return ""
    try:
        return c.text.decode("utf-8", "replace") if c.text else ""
    finally:
        _lib.RimeFreeCommit(ctypes.byref(c))


def commit_composition():
    """把当前拼音串直接上屏(回车确认)。上屏文本由 commit_text() 取。"""
    if not _ready:
        return
    _lib.RimeCommitComposition(_session)


def select(index):
    """选择并上屏第 index 个候选(0 起)。上屏文本由 commit_text() 取。"""
    if not _ready:
        return
    _lib.RimeSelectCandidate(_session, index)


def is_composing():
    if not _ready:
        return False
    st = RimeStatus()
    st.data_size = ctypes.sizeof(RimeStatus)
    if not _lib.RimeGetStatus(_session, ctypes.byref(st)):
        return False
    try:
        return bool(st.is_composing)
    finally:
        _lib.RimeFreeStatus(ctypes.byref(st))


def clear():
    """清空当前拼音(Esc)。"""
    if _ready:
        process_key(K_ESCAPE, 0)


def finalize():
    global _ready
    if _ready:
        try:
            _lib.RimeFinalize()
        except Exception:
            pass
        _ready = False
