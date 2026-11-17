# -*- coding: utf-8 -*-
"""
PULSE · PC 端轻量单窗版（v3.0.0）

一个窗口搞定全部：启动即内嵌显示配对二维码，左侧实时列出 Agent 任务进度。
数据层完整复用 pulse_core / pulse_events（事件引擎 + 手机命令通道）/ pulse_pair_server
（局域网配对服务 + token 持久化），与 Android 端 v1.6.0 完全兼容。

自动化参数（测试/CI 用）：
  --source none|http|file:路径|replay:路径   数据驱动模式（缺省本地模拟 + 手机命令）
  --source-speed N                          回放倍速
  --screenshot 路径 [--size W H]            截图后退出
  --pair-info 路径 / --pair-qr 路径         导出配对信息 / 二维码 PNG
  --serve-seconds N                         N 秒后自动退出
"""
import os
import sys

from pulse_core import (
    T, STATUS, APP_VER, load_fonts, now_str, fmt_elapsed, fmt_tokens, summarise, seed_tasks,
)
from pulse_events import (
    EventEngine, FileEventSource, ReplayEventSource, HttpEventSource,
    EV_TASK_STARTED, EV_TASK_COMPLETED, EV_TASK_FAILED,
)
from pulse_pair_server import PairServer, make_qr_pixmap

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QPainter, QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QFrame, QGraphicsOpacityEffect,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def f_cn(size=12, bold=False):
    fam = "Noto Sans CJK SC"
    try:
        from PySide6.QtGui import QFontDatabase
        if fam not in QFontDatabase.families():
            fam = "Sans Serif"
    except Exception:
        pass
    f = QFont(fam, size)
    f.setBold(bold)
    return f


def f_mono(size=11, bold=False):
    f = QFont("Fira Code", size)
    f.setBold(bold)
    f.setStyleHint(QFont.Monospace)
    return f


QSS = """
QMainWindow, QWidget { background:#0B1120; color:#EAF2FF; font-family:'Noto Sans CJK SC'; }
QLabel { background:transparent; border:0; }
QListWidget { background:transparent; border:0; outline:0; }
QScrollBar:vertical { background:transparent; width:8px; margin:2px; }
QScrollBar::handle:vertical { background:#26334C; border-radius:4px; min-height:40px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
"""

STATUS_DOT = {k: v[1] for k, v in STATUS.items()}
STATUS_TXT = {k: v[0] for k, v in STATUS.items()}


class TaskRow(QWidget):
    """单行任务：状态点 + 名称 + Agent/模型 + 进度条 + 耗时/Tokens。"""

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task
        self.setMinimumHeight(84)

    def set_task(self, task):
        self.task = task
        self.update()

    def paintEvent(self, _):
        t = self.task
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # 底卡
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#111A2C"))
        p.drawRoundedRect(QRectF(0, 2, w - 8, h - 10), 10, 10)
        # 状态点 + 名称
        dot = QColor(STATUS_DOT.get(t.status, "#94A3B8"))
        p.setBrush(dot)
        p.drawEllipse(14, 16, 8, 8)
        p.setPen(QColor("#F1F5FB"))
        p.setFont(f_cn(13, True))
        p.drawText(30, 8, w - 330, 22, Qt.AlignLeft, t.name)
        # 状态徽章（右上）
        p.setPen(dot)
        p.setFont(f_cn(10, True))
        p.drawText(w - 296, 10, 80, 18, Qt.AlignRight, STATUS_TXT.get(t.status, t.status))
        # 进度条 + 百分比（右上第二行）
        bar_w = 130
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1E293B"))
        p.drawRoundedRect(QRectF(w - 214, 34, bar_w, 8), 4, 4)
        p.setBrush(dot)
        p.drawRoundedRect(QRectF(w - 214, 34, bar_w * t.progress / 100, 8), 4, 4)
        p.setPen(QColor("#EAF2FF"))
        p.setFont(f_mono(11, True))
        p.drawText(w - 76, 30, 60, 18, Qt.AlignRight, "%d%%" % t.progress)
        # 第二行：Agent · 模型 · 步骤
        p.setPen(QColor("#7C91B2"))
        p.setFont(f_cn(10))
        p.drawText(30, 36, w - 330, 16, Qt.AlignLeft,
                   "%s · %s · %d/%d 步骤" % (t.agent, t.model, t.steps_done, len(t.steps)))
        # 第三行：耗时 / Tokens / 更新（限制宽度避免压进度条区）
        p.setPen(QColor("#5D7290"))
        p.setFont(f_mono(9))
        p.drawText(30, 56, w - 330, 16, Qt.AlignLeft,
                   "耗时 %s   ·   Tokens %s   ·   更新 %s" %
                   (fmt_elapsed(t.elapsed), fmt_tokens(t.tokens), t.updated))
        p.end()


class DesktopWindow(QMainWindow):
    def __init__(self, source=None, source_speed=1.0):
        super().__init__()
        self.setWindowTitle("PULSE · Agent 进度（v%s）" % APP_VER)
        self.resize(1020, 640)
        self.tasks = seed_tasks()
        self.live = True

        # 引擎 + 命令通道（与 Studio 版完全同构，数据层零差异）
        self.pair = PairServer()
        self.cmd_source = HttpEventSource()
        self.pair.set_command_source(self.cmd_source)
        self.engine = EventEngine(
            self.tasks, source=None, simulate=True,
            on_event=self._on_engine_event, extra_sources=[self.cmd_source])
        self._build_engine(source, source_speed)
        self.pair.start()
        self.pair.publish(self.tasks)

        self._build_ui()
        self._refresh_qr()
        self.refresh_all()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(2000)
        self.refresh_all()

    # ------------------------------------------------------------ UI
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(14)

        # 左：标题 + 任务列表
        left = QVBoxLayout()
        head = QHBoxLayout()
        title = QLabel("Agent 任务进度")
        title.setFont(f_cn(20, True))
        title.setStyleSheet("color:#F4F8FF;")
        head.addWidget(title)
        head.addStretch()
        self.stat = QLabel("")
        self.stat.setFont(f_cn(11))
        self.stat.setStyleSheet("color:#7C91B2;")
        head.addWidget(self.stat)
        left.addLayout(head)

        self.list = QListWidget()
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setSpacing(6)
        for t in self.tasks:
            item = QListWidgetItem()
            item.setSizeHint(TaskRow(t).sizeHint().expandedTo(
                __import__("PySide6.QtCore", fromlist=["QSize"]).QSize(0, 84)))
            self.list.addItem(item)
            row = TaskRow(t)
            self.rows = getattr(self, "rows", {})
            self.rows[t.id] = (item, row)
            self.list.setItemWidget(item, row)
        left.addWidget(self.list, 1)
        lay.addLayout(left, 1)

        # 右：配对面板（二维码内嵌）
        panel = QFrame()
        panel.setFixedWidth(288)
        panel.setStyleSheet(
            "QFrame{background:#111A2C;border:1px solid #26334C;border-radius:14px;}")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(18, 18, 18, 18)
        pv.setSpacing(10)
        cap = QLabel("手机扫码连接")
        cap.setFont(f_cn(14, True))
        cap.setStyleSheet("color:#22C55E;border:0;")
        pv.addWidget(cap)
        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignCenter)
        self.qr.setStyleSheet("border:0;")
        pv.addWidget(self.qr, 1)
        self.addr = QLabel("")
        self.addr.setFont(f_mono(9))
        self.addr.setWordWrap(True)
        self.addr.setStyleSheet("color:#9AAAC4;border:0;")
        pv.addWidget(self.addr)
        self.token_lb = QLabel("")
        self.token_lb.setFont(f_mono(9))
        self.token_lb.setStyleSheet("color:#5D7290;border:0;")
        pv.addWidget(self.token_lb)
        tip = QLabel("扫码后即可在手机上查看任务进度，\n并可远程暂停 / 恢复 / 重试任务。\n数据每 2 秒自动刷新。")
        tip.setFont(f_cn(10))
        tip.setStyleSheet("color:#5D7290;border:0;")
        pv.addWidget(tip)
        lay.addWidget(panel)

    def _refresh_qr(self):
        pm = make_qr_pixmap(self.pair.url(), size=220)
        self.qr.setPixmap(pm)
        self.addr.setText(self.pair.url())
        self.token_lb.setText("配对 token：%s（本机持久化）" % self.pair.state.token)

    # ------------------------------------------------------------ 引擎
    def _build_engine(self, source, speed):
        self.engine_desc = "本地模拟 + 手机命令通道"
        if not source:
            return
        if source == "none":
            self.engine.simulate = False
            self.engine_desc = "冻结模式（--source none，不推进；命令可用）"
            return
        if source == "http":
            src = HttpEventSource()
            self.engine.source = src
            self.pair.set_event_source(src)
            self.engine_desc = "HTTP 事件推送（POST /api/events，token 鉴权）"
            return
        if source.startswith("file:"):
            self.engine.source = FileEventSource(source[5:])
            self.engine_desc = "事件文件跟随（%s）" % os.path.basename(source[5:])
            return
        if source.startswith("replay:"):
            self.engine.source = ReplayEventSource(source[7:], speed=speed)
            self.engine_desc = "事件回放（%s · %.1fx）" % (os.path.basename(source[7:]), speed)
            return
        raise ValueError("--source 仅支持 none / http / file:路径 / replay:路径")

    def _on_engine_event(self, etype, task):
        line = now_str()
        if etype in ("sim_done", EV_TASK_COMPLETED):
            self._log = getattr(self, "_log", [])
            self._log.append((line, "ok", task.agent, "%s 完成" % task.id))
        elif etype == EV_TASK_FAILED:
            self._log = getattr(self, "_log", [])
            self._log.append((line, "error", task.agent, "%s 失败" % task.id))

    def tick(self, force=False):
        if not self.live and not force:
            return
        if self.engine.step():
            self.refresh_all()

    def refresh_all(self):
        s = summarise(self.tasks)
        self.stat.setText("共 %d · 运行 %d · 完成 %d · 需关注 %d · 整体 %d%%" % (
            s["total"], s["running"], s["done"], s["need_attention"], s["completion_rate"]))
        self.pair.publish(self.tasks)
        # 列表：新增任务追加行，已有行原地刷新
        seen = set()
        for t in self.tasks:
            seen.add(t.id)
            if t.id in self.rows:
                self.rows[t.id][1].set_task(t)
            else:
                item = QListWidgetItem()
                item.setSizeHint(TaskRow(t).sizeHint().expandedTo(
                    __import__("PySide6.QtCore", fromlist=["QSize"]).QSize(0, 84)))
                self.list.addItem(item)
                row = TaskRow(t)
                self.rows[t.id] = (item, row)
                self.list.setItemWidget(item, row)
                self._refresh_qr()
        for tid in list(self.rows):
            if tid not in seen:
                item, _row = self.rows.pop(tid)
                self.list.takeItem(self.list.row(item))


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    load_fonts()
    argv = sys.argv

    def arg(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default

    try:
        speed = float(arg("--source-speed", "1.0"))
    except ValueError:
        speed = 1.0
    win = DesktopWindow(source=arg("--source"), source_speed=speed)
    win.show()
    win._refresh_qr()

    if "--pair-info" in argv:
        import json
        info = {
            "version": APP_VER, "host": win.pair.host, "port": win.pair.port,
            "token": win.pair.state.token, "url": win.pair.url(),
            "health_url": win.pair.health_url(), "error": win.pair.error,
            "engine": "轻量单窗（数据引擎与命令通道同构）",
        }
        try:
            with open(arg("--pair-info", "/tmp/pulse_pair_info.json"), "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
            print("PAIR_INFO_OK")
        except Exception as e:
            print("PAIR_INFO_FAILED %s" % e)

    if "--pair-qr" in argv:
        try:
            from pulse_pair_server import save_qr_png
            save_qr_png(win.pair.url(), arg("--pair-qr", "/tmp/pulse_pair_qr.png"))
            print("PAIR_QR_OK")
        except Exception as e:
            print("PAIR_QR_FAILED %s" % e)

    if "--screenshot" in argv:
        def capture():
            app.processEvents()
            print("SCREENSHOT", win.grab().save(arg("--screenshot", "/tmp/pulse_desktop.png")))
            app.quit()
        QTimer.singleShot(1400, capture)

    if "--serve-seconds" in argv:
        try:
            QTimer.singleShot(int(float(arg("--serve-seconds", "30")) * 1000), app.quit)
        except ValueError:
            pass
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
