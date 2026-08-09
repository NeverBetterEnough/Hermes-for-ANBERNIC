# Hermes-for-ANBERNIC

Bring your Anbernic handheld console to life with Hermès — a collection of apps for Anbernic handhelds (RG35xxH / RG34xx / RG40xx 等) running the dmenu.bin frontend.

## 应用列表

### hermes_chat — Hermes 对话

掌机上的 Hermes AI 聊天客户端。通过子进程调用 `hermes chat -q --continue <session_id>` 与 Hermes 多轮对话。

- 屏幕软键盘(方向键选择 / A 确认 / B 退格 / L1 Shift / R1 修饰键 / X 显隐 / Y 换位置 / START 发送 / SELECT Tab)
- 历史记录持久化(`history.json`),启动回看
- 固定节拍 10fps 定时刷新,思考动画平滑
- 自动续接会话,`session.id` 记录会话

**安装**:将 `hermes_chat/` 目录与 `Hermes对话.sh` 放到 `/mnt/mmc/Roms/APPS/` 下,dmenu 会自动发现。

**依赖**:Python3 + SDL2 (pysdl2) + Pillow,系统字体 `/mnt/vendor/bin/default.ttf`。

**注意**:设备在中国网络环境下 GitHub 直连可能不稳定,push 需要代理或可直连的网络。

## 许可证

Apache License 2.0
