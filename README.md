# Hermes-for-ANBERNIC

把 Hermès 装进你的 Anbernic 掌机(RG35xxH / RG34xx / RG40xx 等,运行 dmenu.bin 前端的魔改系统)。

## 项目内容

| 目录 | 说明 |
|------|------|
| `hermes_chat/` | 「Hermes 对话」应用:掌机上的 Hermes AI 聊天客户端(软键盘 + 历史记录 + 多轮会话) |
| `hermes_chat/Hermes对话.sh` | dmenu 应用启动脚本(文件名即菜单显示名) |

---

## 部署到掌机(核心)

应用必须放在掌机的 **APPS 应用目录**下,dmenu 前端会扫描该目录下所有 `.sh` 文件并显示在"应用中心"里。文件结构:

```
/mnt/mmc/Roms/APPS/              ← dmenu 扫描的应用目录(TF1 主卡)
├── Hermes对话.sh                ← 启动脚本(dmenu 菜单入口,文件名即显示名)
├── hermes_chat/                 ← 应用代码目录(与 .sh 同级的任意名字)
│   ├── main.py
│   ├── app.py
│   ├── graphic.py
│   ├── input.py
│   ├── agent_client.py
│   └── start.sh
└── Imgs/                        ← (可选)应用图标
    └── Hermes对话.png           ← 250×250 PNG,文件名与 .sh 同名
```

### 方式一:掌机直接拉取(推荐,有 SSH 认证时)

在掌机终端执行:

```bash
git clone git@github.com:NeverBetterEnough/Hermes-for-ANBERNIC.git /root/Hermes-for-ANBERNIC
```

> 注意:国内网络 HTTPS 直连 GitHub 常不通;SSH(22 端口)通常可用。
> 若未配置 SSH key,可改用 `https://github.com/NeverBetterEnough/Hermes-for-ANBERNIC.git` 并多试几次。

### 方式二:电脑下载后拷入 TF 卡

1. 电脑上 `git clone` 或下载 ZIP 解压
2. 将 `hermes_chat/` 整个目录 和 `Hermes对话.sh` 拷入 TF 卡
   - Windows/macOS 直插 TF1 卡:放入 `Roms/APPS/` 目录
   - 或掌机插卡后从文件管理器移动
3. 建议同时放入图标:`Roms/APPS/Imgs/Hermes对话.png`(250×250,可选)

### 两种方式通用步骤

**第 1 步:放置文件**(确保权限可执行)

```bash
# 方式一 clone 后:
cp -r /root/Hermes-for-ANBERNIC/hermes_chat /mnt/mmc/Roms/APPS/
cp "/root/Hermes-for-ANBERNIC/hermes_chat/Hermes对话.sh" /mnt/mmc/Roms/APPS/
chmod +x /mnt/mmc/Roms/APPS/Hermes对话.sh /mnt/mmc/Roms/APPS/hermes_chat/*.py /mnt/mmc/Roms/APPS/hermes_chat/start.sh

# 可选:外卡 TF2 若固件支持,也可放 /mnt/sdcard/Roms/APPS/(目录需自行创建)
```

**第 2 步:检查依赖**(系统自带,通常无需安装)

| 依赖 | 说明 | 检查命令 |
|------|------|----------|
| Python 3 | 系统自带 3.10 | `python3 --version` |
| pysdl2 + SDL2 | 渲染 | `python3 -c "import sdl2"` |
| Pillow | 绘图 | `python3 -c "import PIL"` |
| 系统字体 | 中文渲染 | `/mnt/vendor/bin/default.ttf` 存在即可 |
| **hermes 本体** | **核心依赖,对话全靠它** | `hermes chat -q 'ping'` 能返回即 OK |

> 若 `import sdl2` 失败:把 `sdl2.zip`(从 mod_tools 等应用里复制)放进 `hermes_chat/` 目录,程序启动时会自动解压安装。

**第 3 步:让 dmenu 识别**

- 返回 dmenu 主界面切一下目录,或直接重启设备
- 在"应用中心"里应能看到 **Hermes 对话**

**第 4 步:启动**

- 从 dmenu 选中 **Hermes 对话** 进入
- 界面:方向键选择软键盘字母,A 确认输入,输入完按 **START** 发送

---

## 按键说明

| 按键 | 功能 |
|------|------|
| 方向键 | 键盘选字 / 隐藏键盘时滚动历史 |
| A | 确认输入 / 按下所选键 |
| B | 退格 / 隐藏键盘时退出应用 |
| X | 显示 / 隐藏键盘 |
| Y | 键盘位置切换(底部 / 顶部) |
| L1 | Shift |
| R1 | 修饰键循环(无 → Shift → Ctrl → Alt) |
| START | 发送问题 |
| SELECT | 输入 Tab |
| L2 / R2 | 隐藏键盘时滚动历史 |
| MENU | 退出应用 |

---

## 数据文件(运行后自动生成,在 `hermes_chat/` 目录内)

| 文件 | 用途 |
|------|------|
| `history.json` | 对话历史(自动持久化,重启可回看) |
| `session.id` | Hermes 会话 ID(自动续接多轮对话) |
| `log.txt` | 运行日志(启动失败时排查用) |

---

## 常见问题

**启动黑屏 / 闪退**
看 `hermes_chat/log.txt` 末尾的报错,常见原因是 pysdl2 或字体缺失。

**进了应用但按键没反应**
确认 `/dev/input/event1` 存在(`ls /dev/input/`);本应用已按"fd 常开 + 非阻塞 select"模式读取,若个别键码不同,改 `hermes_chat/input.py` 的 `mapping` 表。

**发送后一直"思考中"或没有回复**
先确认 hermes 本体可用:`hermes chat -q 'ping'`。若输出超时,检查网络(对话走 hermes 后端 API)。

**中文显示为方块**
确认 `/mnt/vendor/bin/default.ttf` 存在(系统字体,含简体/繁体中文)。

---

## 许可证

Apache License 2.0
