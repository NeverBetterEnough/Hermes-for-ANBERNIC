import os
import select
import struct

code = 0
codeName = ""
value = 0

# Anbernic RG35xxH 按键映射 (/dev/input/event1)
mapping = {
    304: "A",
    305: "B",
    306: "Y",
    307: "X",
    308: "L1",
    309: "R1",
    314: "L2",
    315: "R2",
    17: "DY",      # 十字键上下 (value: +1=下, -1=上)
    16: "DX",      # 十字键左右 (value: +1=右, -1=左)
    310: "SELECT",
    311: "START",
    312: "MENUF",
    114: "V+",
    115: "V-",
    103: "UP",
    108: "DOWN",
    106: "RIGHT",
    105: "LEFT",
}

_fd = None


def _ensure_open():
    """一次性打开 /dev/input/event1,保持 fd 常开。

    evdev 语义: 事件只投递给"当前 fd 打开着"的客户端;
    fd 关闭期间到达的事件不会补发。之前每次 check 开/关 fd,
    在 100ms 固定节拍下打开窗口只有几微秒,按键事件几乎全部
    丢失(表现为方向键和其他按键无反应)。必须常开。
    """
    global _fd
    if _fd is None:
        _fd = os.open("/dev/input/event1", os.O_RDONLY | os.O_NONBLOCK)


def check(timeout=0.0):
    """非阻塞读一个按键事件(fd 常开,事件排队不丢)。

    有事件: 更新 code/codeName/value,返回 True。
    无事件(超时/队列空): 清空 codeName/value,返回 False。

    timeout 秒(默认 0,立即返回)内等待事件;主循环用
    固定节拍驱动渲染,check 只负责读按键不阻塞画面。
    事件方向语义(与原厂 img_browser 一致):
      DY: value=+1 表示"下", value=-1 表示"上"
      DX: value=+1 表示"右", value=-1 表示"左"
    """
    global code, codeName, value
    try:
        _ensure_open()
    except OSError:
        codeName = ""
        value = 0
        return False
    r, _, _ = select.select([_fd], [], [], timeout)
    if not r:
        codeName = ""
        value = 0
        return False

    # 跳过释放(0)/同步等零值事件,读到第一个有效按键即返回;
    # 其余事件留在 fd 队列(常开),下次 check 再读 —— 不丢快速连按。
    while True:
        try:
            data = os.read(_fd, 24)
        except (BlockingIOError, OSError):
            codeName = ""
            value = 0
            return False
        if len(data) < 24:
            codeName = ""
            value = 0
            return False
        (tv_sec, tv_usec, type, kcode, kvalue) = struct.unpack('llHHI', data)
        if kvalue != 0:
            if kvalue != 1:
                kvalue = -1
            code = kcode
            codeName = mapping.get(code, str(code))
            value = kvalue
            return True


def key(keyCodeName, keyValue=99):
    global codeName, value
    if codeName == keyCodeName:
        if keyValue != 99:
            return value == keyValue
        return True
    return False


def reset_input():
    global codeName, value
    codeName = ""
    value = 0
