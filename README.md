# PULSE · 双端 Agent 任务进度监测

![CI](https://github.com/uahz/pulse-agent-monitor/actions/workflows/ci.yml/badge.svg)

PC 端一个窗口搞定：启动即内嵌显示配对二维码，实时列出 Agent 任务进度；Android 端扫码连接后可远程查看进度，并**暂停 / 恢复 / 重试**任务。纯局域网直连，无云端、无账号。

[English](README.en.md)

## 界面

| PC 端（轻量单窗） | Android 端 |
|---|---|
| ![PC](docs/screenshots/desktop-workbench.png) | ![Mobile](docs/screenshots/mobile-projects-connected.png) |

## 快速开始

1. **PC**：从 [Releases](../../releases) 下载单文件程序运行——二维码直接显示在窗口里
2. **Android**：下载 APK 安装
3. 手机端「连接 PC」扫码（或手动输入地址 + token），即连即看

## 从源码运行 / 构建

```bash
# PC（Python 3.10+，pip install PySide6 segno）
python desktop/pulse_desktop.py

# 打包 PC 单文件
bash desktop/build_linux.sh          # 产物 dist/PULSE_Desktop（Windows 用 build_exe.bat）

# Android APK（需 Android SDK 35）
bash mobile/android/build.sh         # 产物 releases/PULSE_v1.6.0.apk
```

## 验证与发版

六套脚本共 **174 项断言**（`desktop/verify_*.py`、`mobile/verify_link.py`），CI 每次 push 自动跑全量；推 `v*` 标签时自动构建并发布 Release（exe + APK）。

```bash
cd desktop && QT_QPA_PLATFORM=offscreen python3.12 verify_desktop.py   # 轻量单窗 11 项
```

## 说明

- 数据默认本地演示推进；`--source http` 可接入真实 Agent 事件（`POST /api/events`，协议见代码注释）
- 配对 token 持久化在 `~/.pulse/pair_token`（600 权限），PC 重启后手机免重新扫码
- 已知限制：扫码依赖机型 WebView 相机权限（失败自动退化为手动输入地址）；APK 为演示自签名
