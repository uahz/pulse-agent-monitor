# -*- coding: utf-8 -*-
"""
PULSE · Agent Studio  —  全新 PC 主界面（v2.0.0）

设计目标：彻底摆脱「后台管理界面」观感。
  - 无边框圆角窗口 + 自定义标题栏（品牌 / 胶囊分段 / 悬浮窗开关 / 窗口按钮）
  - Aurora 氛围光晕背景 + 统一的液态玻璃卡片材质（与悬浮窗同源）
  - Hero 大环形进度 + 一句话状态，取代 4 个并排 KPI 方块
  - Bento 任务卡片流，取代 8 列密集表格
  - chips 筛选取代下拉框，取消左侧竖栏 / 双行工具栏 / 底部状态栏

保留的能力（不回归上一轮验证过的链路）：
  - 局域网只读配对服务 PairServer + 扫码面板
  - 每 2 秒实时推进、新建任务、导出 CSV、搜索
  - 自动化参数 --screenshot / --page / --size / --pair-* / --serve-seconds
  - 新增 --overlay-shot / --overlay-collapsed-shot 用于悬浮窗验证

技术：Python 3 + PySide6 / Qt Widgets，纯原生绘制，无 HTML / WebView。
"""
import csv
import os
import random
import sys
from datetime import datetime

from pulse_core import (
    T, C, STATUS, AGENTS, PRIORITIES, APP_NAME, APP_SUB, APP_VER,
    load_fonts, now_str, fmt_elapsed, fmt_tokens, summarise,
    f_cn, f_bold, f_display, f_mono, seed_tasks,
)
from pulse_glass import (
    GlassCard, GlassOverlay, rounded_path, paint_aurora, paint_glass_surface,
    paint_soft_shadow, draw_ring, draw_bar, _c, _global_pos,
)
from pulse_pair_server import PairServer, open_pair_dialog, save_qr_png

from PySide6.QtCore import (
    Qt, QRectF, QPointF, QSize, QTimer, Signal, QPropertyAnimation, QEasingCurve,
)
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush, QLinearGradient, QRadialGradient,
    QFont, QAction, QShortcut, QKeySequence, QCursor, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QLineEdit,
    QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget, QScrollArea,
    QSizePolicy, QButtonGroup, QFileDialog, QMessageBox, QDialog, QComboBox,
    QGraphicsOpacityEffect,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
W, H = 1460, 940
MARGIN = 14          # 窗口阴影留白
RADIUS = 26

# ---------------------------------------------------------------- 全局样式
QSS = """
QWidget { font-family:'Noto Sans CJK SC'; color:#EAF2FF; }
QLabel { background:transparent; border:0; }
QLineEdit {
    background:rgba(255,255,255,16); border:1px solid rgba(255,255,255,30);
    border-radius:18px; padding:0 16px; min-height:36px; color:#EAF2FF;
    selection-background-color:#22C55E; font-size:12px;
}
QLineEdit:focus { border-color:rgba(74,222,128,150); background:rgba(255,255,255,24); }
QLineEdit::placeholder { color:#7C8FB0; }
QComboBox {
    background:rgba(255,255,255,16); border:1px solid rgba(255,255,255,30);
    border-radius:12px; padding:0 12px; min-height:34px; color:#EAF2FF; font-size:12px;
}
QComboBox::drop-down { border:0; width:22px; }
QComboBox::down-arrow { image:none; border-left:4px solid transparent;
    border-right:4px solid transparent; border-top:5px solid #9AAAC4; margin-right:10px; }
QComboBox QAbstractItemView { background:#16223A; border:1px solid #2C3C55;
    selection-background-color:#243A55; color:#EAF2FF; outline:0; }
QScrollArea { background:transparent; border:0; }
QScrollArea > QWidget > QWidget { background:transparent; }
QScrollBar:vertical { background:transparent; width:8px; margin:0; border:0; }
QScrollBar::handle:vertical { background:rgba(255,255,255,42); border-radius:4px; min-height:36px; }
QScrollBar::handle:vertical:hover { background:rgba(255,255,255,80); }
QScrollBar::add-line, QScrollBar::sub-line { height:0; width:0; }
QScrollBar::add-page, QScrollBar::sub-page { background:transparent; }
QDialog { background:#0C1424; }
QToolTip { background:#16223A; color:#EAF2FF; border:1px solid rgba(255,255,255,60);
    padding:7px 10px; border-radius:8px; }
QPushButton:focus { outline:0; }
"""


# ---------------------------------------------------------------- 小部件
class Segmented(QWidget):
    """胶囊分段导航：玻璃底 + 滑动高亮块，点击切换。"""
    changed = Signal(int)
    LABELS = ["工作台", "概览", "日志", "预警"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(376, 42)
        self.setCursor(Qt.PointingHandCursor)
        self._index = 0
        self._hover = -1
        self.setMouseTracking(True)

    def index(self):
        return self._index

    def set_index(self, i):
        self._index = max(0, min(3, i))
        self.update()

    def _slot(self, i):
        return QRectF(4 + i * 92, 4, 92, 34)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = rounded_path(r, 21)
        p.save()
        p.setClipPath(path)
        p.fillPath(path, _c("#0A1222", 150))
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, _c("#FFFFFF", 26))
        g.setColorAt(1, _c(T["cyan"], 14))
        p.fillPath(path, QBrush(g))
        p.restore()
        p.save()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_c("#FFFFFF", 40), 1.2))
        p.drawPath(path)
        p.restore()

        # 高亮滑块
        s = self._slot(self._index)
        sp = rounded_path(s, 17)
        p.save()
        p.setClipPath(sp)
        hg = QLinearGradient(s.topLeft(), s.bottomRight())
        hg.setColorAt(0, _c(T["green_hi"], 245))
        hg.setColorAt(1, _c(T["cyan"], 225))
        p.fillPath(sp, QBrush(hg))
        p.restore()
        p.save()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_c("#FFFFFF", 120), 1.0))
        p.drawPath(sp)
        p.restore()

        for i, label in enumerate(self.LABELS):
            rc = self._slot(i)
            active = (i == self._index)
            p.setFont(f_bold(12) if active else f_cn(12))
            p.setPen(_c("#07131E", 250) if active else
                     (_c("#DCE8FF", 235) if i == self._hover else _c("#9FB2D0", 205)))
            p.drawText(rc, Qt.AlignCenter, label)
        p.end()

    def mouseMoveEvent(self, e):
        pos = e.position()
        h = -1
        for i in range(4):
            if self._slot(i).contains(QPointF(pos)):
                h = i
                break
        if h != self._hover:
            self._hover = h
            self.update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self._hover = -1
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        for i in range(4):
            if self._slot(i).contains(QPointF(e.position())):
                if i != self._index:
                    self._index = i
                    self.changed.emit(i)
                    self.update()
                return
        super().mousePressEvent(e)


class Chip(QPushButton):
    """筛选胶囊。"""
    def __init__(self, text, key, parent=None):
        super().__init__(text, parent)
        self.key = key
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)
        self.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,14);border:1px solid rgba(255,255,255,28);"
            "border-radius:16px;padding:0 16px;color:#A9BCD8;font-size:12px;}"
            "QPushButton:hover{background:rgba(255,255,255,26);color:#EAF2FF;}"
            "QPushButton:checked{background:rgba(74,222,128,42);border-color:rgba(74,222,128,150);"
            "color:#C6F6D9;font-weight:bold;}")


class GlowButton(QPushButton):
    """标题栏按钮：可切换的发光态（用于悬浮窗开关）。"""
    def __init__(self, text, parent=None, accent=None):
        super().__init__(text, parent)
        self.accent = accent or T["green"]
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setFixedHeight(36)
        self._apply(False)

    def _apply(self, on):
        a = self.accent
        if on:
            self.setStyleSheet(
                "QPushButton{background:rgba(74,222,128,46);border:1px solid rgba(74,222,128,170);"
                "border-radius:18px;padding:0 16px;color:#DCFCE7;font-size:12px;font-weight:bold;}"
                "QPushButton:hover{background:rgba(74,222,128,66);}")
        else:
            self.setStyleSheet(
                "QPushButton{background:rgba(255,255,255,16);border:1px solid rgba(255,255,255,34);"
                "border-radius:18px;padding:0 16px;color:#C3D3EC;font-size:12px;}"
                "QPushButton:hover{background:rgba(255,255,255,30);color:#FFFFFF;}")

    def setChecked(self, on):
        super().setChecked(on)
        self._apply(on)


class PlainButton(QPushButton):
    def __init__(self, text, parent=None, primary=False, fixed=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        if fixed:
            self.setFixedWidth(fixed)
        if primary:
            self.setStyleSheet(
                "QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                "stop:0 #4ADE80,stop:1 #22C55E);border:0;border-radius:18px;padding:0 18px;"
                "color:#07131E;font-size:12px;font-weight:bold;}"
                "QPushButton:hover{background:#6EE7A0;}")
        else:
            self.setStyleSheet(
                "QPushButton{background:rgba(255,255,255,16);border:1px solid rgba(255,255,255,34);"
                "border-radius:18px;padding:0 16px;color:#C3D3EC;font-size:12px;}"
                "QPushButton:hover{background:rgba(255,255,255,30);color:#FFFFFF;}")


class WinButton(QPushButton):
    """无边框窗口的最小化 / 最大化 / 关闭圆按钮。"""
    def __init__(self, glyph, kind, parent=None):
        super().__init__(glyph, parent)
        self.kind = kind
        self.setFixedSize(30, 30)
        self.setCursor(Qt.PointingHandCursor)
        hover = "rgba(251,113,133,150)" if kind == "close" else "rgba(255,255,255,60)"
        self.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,14);border:1px solid rgba(255,255,255,26);"
            "border-radius:15px;color:#B9C9E2;font-size:13px;}"
            "QPushButton:hover{background:%s;color:#FFFFFF;border-color:%s;}" % (hover, hover))


# ---------------------------------------------------------------- 环形 Hero
class HeroRing(QWidget):
    """大环形完成率。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(196, 196)
        self.pct = 0

    def set_value(self, v):
        self.pct = v
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        c = QPointF(self.width() / 2, self.height() / 2)
        draw_ring(p, c, 78, self.pct, thickness=13, track_alpha=20)
        p.setFont(f_display(44))
        p.setPen(_c("#FFFFFF", 250))
        num = str(self.pct)
        num_w = p.fontMetrics().horizontalAdvance(num)
        p.drawText(QRectF(c.x() - num_w - 8, c.y() - 32, num_w + 10, 50),
                   Qt.AlignRight | Qt.AlignVCenter, num)
        p.setFont(f_bold(17))
        p.setPen(_c(T["green_soft"], 240))
        p.drawText(QRectF(c.x() + 4, c.y() - 6, 30, 34), Qt.AlignLeft | Qt.AlignBottom, "%")
        p.setFont(f_cn(11))
        p.setPen(_c("#B9CCEA", 220))
        p.drawText(QRectF(c.x() - 70, c.y() + 22, 140, 20),
                   Qt.AlignHCenter | Qt.AlignVCenter, "整体完成率")
        p.end()


class StatPill(QWidget):
    """Hero 右侧的一行统计（彩色圆点 + 标签 + 数值）。"""
    def __init__(self, label, color, parent=None):
        super().__init__(parent)
        self.label = label
        self.color = color
        self.value = "0"
        self.setFixedHeight(46)

    def set_value(self, v):
        self.value = str(v)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = rounded_path(r, 14)
        p.save()
        p.setClipPath(path)
        p.fillPath(path, _c("#FFFFFF", 13))
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, _c("#FFFFFF", 20))
        g.setColorAt(1, _c(self.color, 12))
        p.fillPath(path, QBrush(g))
        p.restore()
        p.save()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_c("#FFFFFF", 34), 1.0))
        p.drawPath(path)
        p.restore()
        p.setPen(Qt.NoPen)
        p.setBrush(_c(self.color, 240))
        p.drawEllipse(QPointF(r.left() + 20, r.center().y()), 5, 5)
        p.setFont(f_cn(12))
        p.setPen(_c("#C4D4EE", 225))
        p.drawText(QRectF(r.left() + 36, r.top(), 120, r.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, self.label)
        p.setFont(f_display(20))
        p.setPen(_c("#FFFFFF", 250))
        p.drawText(QRectF(r.right() - 76, r.top(), 62, r.height()),
                   Qt.AlignVCenter | Qt.AlignRight, self.value)
        p.end()


# ---------------------------------------------------------------- Bento 任务卡
class TaskBentoCard(GlassCard):
    """单张任务卡：状态 + 名称 + 元信息 + 进度条 + 底部三小项。"""
    clicked = Signal(object)

    def __init__(self, task, parent=None):
        super().__init__(parent, radius=22, base_alpha=112, gloss=0.92, padding=0)
        self.task = task
        self.setFixedHeight(214)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False
        self.setAttribute(Qt.WA_StyledBackground, False)

    def set_task(self, t):
        self.task = t
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        self.clicked.emit(self.task)
        super().mousePressEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = rounded_path(r, self.radius)
        paint_soft_shadow(p, r, self.radius, layers=5, spread=1.8,
                          alpha=11 if self._hover else 7)
        p.save()
        p.setClipPath(path)
        paint_glass_surface(p, path, r, accent=STATUS[self.task.status][1],
                            base_alpha=104 if self._hover else 112,
                            gloss=1.2 if self._hover else 0.92)
        # hover 时叠加一层极淡主色
        if self._hover:
            p.fillPath(path, _c(STATUS[self.task.status][1], 12))
        p.restore()

        t = self.task
        pad = 20
        inner = QRectF(r).adjusted(pad, 16, -pad, -14)
        label, color, soft = STATUS[t.status]

        # 状态胶囊
        p.setFont(f_bold(10))
        sw = p.fontMetrics().horizontalAdvance(label) + 30
        badge = QRectF(inner.left(), inner.top(), sw, 22)
        p.setPen(Qt.NoPen)
        p.setBrush(_c(soft, 34))
        p.drawRoundedRect(badge, 11, 11)
        p.setBrush(_c(color, 240))
        p.drawEllipse(QPointF(badge.left() + 12, badge.center().y()), 3.5, 3.5)
        p.setPen(_c(soft, 245))
        p.drawText(QRectF(badge.left() + 20, badge.top(), badge.width() - 22, badge.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, label)

        # 优先级
        pri_color = {"高": T["red"], "中": T["amber"], "低": T["dim"]}.get(t.priority, T["dim"])
        p.setFont(f_cn(10))
        p.setPen(_c(pri_color, 230))
        p.drawText(QRectF(inner.right() - 70, inner.top(), 70, 22),
                   Qt.AlignVCenter | Qt.AlignRight, "● %s优先级" % t.priority)

        # 任务名
        p.setFont(f_bold(15))
        p.setPen(_c("#FFFFFF", 248))
        name_w = inner.width()
        name = p.fontMetrics().elidedText(t.name, Qt.ElideRight, int(name_w))
        p.drawText(QRectF(inner.left(), inner.top() + 30, name_w, 26),
                   Qt.AlignVCenter | Qt.AlignLeft, name)

        # 元信息
        p.setFont(f_mono(10))
        p.setPen(_c("#8CA2C4", 210))
        meta = "%s   ·   %s / %s" % (t.id, t.agent, t.model)
        p.drawText(QRectF(inner.left(), inner.top() + 57, inner.width(), 18),
                   Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(meta, Qt.ElideRight, int(inner.width())))

        # 进度条 + 数值
        bar_y = inner.top() + 88
        p.setFont(f_display(19))
        p.setPen(_c("#FFFFFF", 250))
        pct_text = "%d%%" % t.progress
        pw = p.fontMetrics().horizontalAdvance(pct_text) + 6
        p.drawText(QRectF(inner.right() - pw, bar_y - 8, pw, 26),
                   Qt.AlignVCenter | Qt.AlignRight, pct_text)
        draw_bar(p, QRectF(inner.left(), bar_y + 2, inner.width() - pw - 12, 8),
                 t.progress, color=color)

        # 底部三小项：相对顶部定位，保证两行都完整落在卡片内
        foot_y = inner.top() + 116
        items = [
            ("步骤", "%d/%d" % (t.steps_done, len(t.steps))),
            ("耗时", fmt_elapsed(t.elapsed)),
            ("Tokens", fmt_tokens(t.tokens)),
        ]
        col_w = inner.width() / 3.0
        for i, (k, v) in enumerate(items):
            x = inner.left() + i * col_w
            p.setFont(f_cn(10))
            p.setPen(_c("#8CA2C4", 210))
            p.drawText(QRectF(x, foot_y, col_w - 8, 16), Qt.AlignVCenter | Qt.AlignLeft, k)
            p.setFont(f_mono(11, True))
            p.setPen(_c("#D6E4FA", 240))
            p.drawText(QRectF(x, foot_y + 16, col_w - 8, 18), Qt.AlignVCenter | Qt.AlignLeft, v)
        p.end()


# ---------------------------------------------------------------- 页面：工作台
class WorkbenchPage(QWidget):
    filter_changed = Signal(str, str)   # (状态key, 搜索文本)

    CHIPS = [("全部", "all"), ("运行中", "running"), ("待确认", "review"),
             ("已完成", "done"), ("需关注", "need")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(34, 8, 34, 20)
        root.setSpacing(18)

        # 标题行
        title_row = QHBoxLayout()
        tv = QVBoxLayout(); tv.setSpacing(4)
        h1 = QLabel("工作台")
        h1.setFont(f_display(30))
        h1.setStyleSheet("color:#F4F8FF;")
        sub = QLabel("所有 Agent 的实时进度，一目了然")
        sub.setFont(f_cn(12))
        sub.setStyleSheet("color:#93A7C6;")
        tv.addWidget(h1); tv.addWidget(sub)
        title_row.addLayout(tv)
        title_row.addStretch()
        self.clock = QLabel("")
        self.clock.setFont(f_mono(12, True))
        self.clock.setStyleSheet("color:#8CA2C4;")
        title_row.addWidget(self.clock, 0, Qt.AlignBottom)
        root.addLayout(title_row)

        # Hero 玻璃卡
        hero = GlassCard(self, radius=26, base_alpha=104, gloss=1.1, padding=0)
        hero.setFixedHeight(224)
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(26, 16, 26, 16)
        hl.setSpacing(24)
        self.ring = HeroRing()
        hl.addWidget(self.ring, 0, Qt.AlignVCenter)

        info = QVBoxLayout(); info.setSpacing(10)
        self.hero_title = QLabel("多 Agent 协同推进中")
        self.hero_title.setFont(f_display(22))
        self.hero_title.setStyleSheet("color:#FFFFFF;")
        self.hero_desc = QLabel("")
        self.hero_desc.setFont(f_cn(12))
        self.hero_desc.setStyleSheet("color:#A9BCD8;")
        self.hero_desc.setWordWrap(True)
        info.addWidget(self.hero_title)
        info.addWidget(self.hero_desc)
        info.addStretch()
        stats_row = QHBoxLayout(); stats_row.setSpacing(12)
        self.p_run = StatPill("运行中", T["green"])
        self.p_done = StatPill("已完成", T["green_hi"])
        self.p_need = StatPill("需关注", T["amber"])
        for s in (self.p_run, self.p_done, self.p_need):
            stats_row.addWidget(s, 1)
        info.addLayout(stats_row)
        hl.addLayout(info, 1)
        root.addWidget(hero)

        # 筛选 / 搜索 / 操作行
        tools = QHBoxLayout(); tools.setSpacing(10)
        self.chip_group = QButtonGroup(self)
        self.chip_group.setExclusive(True)
        self.cur_filter = "all"
        for i, (label, key) in enumerate(self.CHIPS):
            c = Chip(label, key)
            c.setChecked(i == 0)
            c.clicked.connect(lambda _, k=key: self._on_chip(k))
            self.chip_group.addButton(c)
            tools.addWidget(c)
        tools.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索任务 / ID / Agent")
        self.search.setFixedWidth(230)
        self.search.textChanged.connect(self._emit_filter)
        tools.addWidget(self.search)
        tools_btn = PlainButton("+ 新建任务", primary=True, fixed=112)
        tools_btn.clicked.connect(self.new_task_requested)
        tools.addWidget(tools_btn)
        root.addLayout(tools)

        # 卡片流
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.grid_host = QWidget()
        self.grid_host.setStyleSheet("background:transparent;")
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(2, 2, 10, 2)
        self.grid.setSpacing(16)
        self.grid.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.grid_host)
        root.addWidget(self.scroll, 1)

        self.cards = {}
        self._cols = 3

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.cards:
            self._relayout()

    new_task = Signal()

    def new_task_requested(self):
        self.new_task.emit()

    def _on_chip(self, key):
        self.cur_filter = key
        self._emit_filter()

    def _emit_filter(self, *a):
        self.filter_changed.emit(self.cur_filter, self.search.text().strip())

    def set_clock(self, txt):
        self.clock.setText(txt)

    def update_stats(self, s):
        self.ring.set_value(s["completion_rate"])
        self.p_run.set_value(s["running"])
        self.p_done.set_value(s["done"])
        self.p_need.set_value(s["need_attention"])
        self.hero_desc.setText(
            "共 %d 项任务 · %d 个 Agent 在线 · 每 2 秒自动同步  |  %s" %
            (s["total"], len(AGENTS), "LIVE" if self.property("live") is not False else "PAUSED"))

    def rebuild_cards(self, tasks):
        """筛选变化时重建卡片（避免每次 tick 重建导致闪烁）。"""
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.cards = {}
        for t in tasks:
            card = TaskBentoCard(t)
            card.clicked.connect(self.on_card_clicked)
            self.cards[t.id] = card
        self._relayout()

    def _relayout(self):
        visible = [c for c in self.cards.values() if not c.property("hidden_by_filter")]
        # 列数按页面自身宽度自适应：grid_host 在首次布局前宽度不可靠，
        # 用 viewport / 页面宽度，避免初始只排出 1 列全宽卡片。
        vw = self.scroll.viewport().width() if self.scroll.viewport() else 0
        w = max(vw, self.width(), 900)
        cols = 3 if w >= 1120 else (2 if w >= 760 else 1)
        for c in list(self.cards.values()):
            try:
                self.grid.removeWidget(c)
            except Exception:
                pass
            c.hide()
        for i, c in enumerate(visible):
            self.grid.addWidget(c, i // cols, i % cols)
            c.show()
        self.grid_host.setMinimumHeight(((len(visible) + cols - 1) // cols) * 230 + 8)

    card_selected = Signal(object)

    def on_card_clicked(self, t):
        self.card_selected.emit(t)

    def apply_filter(self, key, text, all_tasks):
        """返回过滤后的任务列表，并标记卡片的显隐。"""
        q = text.lower()
        result = []
        for t in all_tasks:
            ok_state = (key == "all" or
                        (key == "need" and t.status in ("failed", "review", "paused")) or
                        t.status == key)
            ok_text = (not q or q in t.name.lower() or q in t.id.lower() or
                       q in t.agent.lower() or q in t.model.lower())
            show = ok_state and ok_text
            c = self.cards.get(t.id)
            if c:
                c.setProperty("hidden_by_filter", not show)
            if show:
                result.append(t)
        self._relayout()
        return result


# ---------------------------------------------------------------- 页面：概览
class AgentMiniCard(GlassCard):
    def __init__(self, name, role, model, parent=None):
        super().__init__(parent, radius=20, base_alpha=108, padding=0)
        self.setFixedHeight(150)
        self.name, self.role, self.model = name, role, model
        self.count = 0
        self.avg = 0

    def set_data(self, count, avg):
        self.count, self.avg = count, avg
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = rounded_path(r, self.radius)
        paint_soft_shadow(p, r, self.radius, layers=5, spread=1.6, alpha=7)
        p.save(); p.setClipPath(path)
        paint_glass_surface(p, path, r, accent=T["cyan"], base_alpha=104, gloss=0.9)
        p.restore()
        c = QPointF(r.right() - 52, r.center().y())
        draw_ring(p, c, 34, self.avg, thickness=7, track_alpha=20)
        p.setFont(f_bold(12))
        p.setPen(_c("#FFFFFF", 240))
        p.drawText(QRectF(c.x() - 34, c.y() - 12, 68, 24), Qt.AlignCenter, "%d%%" % self.avg)

        x = r.left() + 20
        p.setFont(f_bold(14))
        p.setPen(_c("#FFFFFF", 248))
        p.drawText(QRectF(x, r.top() + 20, r.width() - 110, 24),
                   Qt.AlignVCenter | Qt.AlignLeft, self.name)
        p.setFont(f_cn(11))
        p.setPen(_c(T["green_soft"], 235))
        p.drawText(QRectF(x, r.top() + 46, r.width() - 110, 20),
                   Qt.AlignVCenter | Qt.AlignLeft, self.role)
        p.setFont(f_mono(10))
        p.setPen(_c("#8CA2C4", 210))
        p.drawText(QRectF(x, r.top() + 68, r.width() - 110, 18),
                   Qt.AlignVCenter | Qt.AlignLeft, self.model)
        p.setFont(f_cn(11))
        p.setPen(_c("#B9CCEA", 220))
        p.drawText(QRectF(x, r.bottom() - 40, r.width() - 110, 20),
                   Qt.AlignVCenter | Qt.AlignLeft, "负责 %d 项任务" % self.count)
        p.end()


class OverviewPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(34, 8, 34, 20)
        root.setSpacing(18)
        h1 = QLabel("运行概览")
        h1.setFont(f_display(30)); h1.setStyleSheet("color:#F4F8FF;")
        sub = QLabel("6 个 Agent 的负载与状态分布")
        sub.setFont(f_cn(12)); sub.setStyleSheet("color:#93A7C6;")
        root.addWidget(h1); root.addWidget(sub)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        host = QWidget(); host.setStyleSheet("background:transparent;")
        v = QVBoxLayout(host); v.setContentsMargins(2, 2, 10, 2); v.setSpacing(18)

        grid_host = QWidget(); grid_host.setStyleSheet("background:transparent;")
        g = QGridLayout(grid_host); g.setSpacing(16); g.setContentsMargins(0, 0, 0, 0)
        self.agent_cards = []
        for i, (name, role, model) in enumerate(AGENTS):
            c = AgentMiniCard(name, role, model)
            self.agent_cards.append((name, c))
            g.addWidget(c, i // 3, i % 3)
        v.addWidget(grid_host)

        # 状态分布条
        dist = GlassCard(self, radius=22, base_alpha=104, padding=0)
        dist.setFixedHeight(126)
        self.dist = _DistWidget()
        dl = QVBoxLayout(dist)
        dl.setContentsMargins(20, 14, 20, 14)
        dl.setSpacing(10)
        cap = QLabel("状态分布")
        cap.setFont(f_bold(13)); cap.setStyleSheet("color:#EAF2FF;")
        dl.addWidget(cap)
        dl.addWidget(self.dist)
        v.addWidget(dist)
        v.addStretch()
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

    def refresh(self, tasks):
        for name, card in self.agent_cards:
            ts = [t for t in tasks if t.agent == name]
            avg = round(sum(t.progress for t in ts) / len(ts)) if ts else 0
            card.set_data(len(ts), avg)
        self.dist.set_tasks(tasks)


class _DistWidget(QWidget):
    """堆叠分布条 + 图例。"""
    ORDER = ["running", "done", "review", "paused", "failed", "queued"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tasks = []
        self.setFixedHeight(58)

    def set_tasks(self, tasks):
        self.tasks = list(tasks)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        r = QRectF(self.rect())
        counts = {k: 0 for k in self.ORDER}
        for t in self.tasks:
            if t.status in counts:
                counts[t.status] += 1
        total = max(1, len(self.tasks))
        bar = QRectF(r.left(), r.top() + 2, r.width(), 16)
        p.setPen(Qt.NoPen)
        p.setBrush(_c("#FFFFFF", 20))
        p.drawRoundedRect(bar, 8, 8)
        x = bar.left()
        p.save()
        p.setClipPath(rounded_path(bar, 8))
        for k in self.ORDER:
            w = bar.width() * counts[k] / total
            if w <= 0:
                continue
            seg = QRectF(x, bar.top(), w, bar.height())
            g = QLinearGradient(seg.topLeft(), seg.bottomRight())
            c = STATUS[k][1]
            g.setColorAt(0, _c(c, 235)); g.setColorAt(1, _c(STATUS[k][2], 210))
            p.fillRect(seg, QBrush(g))
            x += w
        p.restore()
        # 图例
        lx = r.left()
        ly = bar.bottom() + 14
        p.setFont(f_cn(10))
        for k in self.ORDER:
            if counts[k] == 0:
                continue
            label = "%s %d" % (STATUS[k][0], counts[k])
            tw = p.fontMetrics().horizontalAdvance(label) + 26
            p.setPen(Qt.NoPen); p.setBrush(_c(STATUS[k][1], 235))
            p.drawEllipse(QPointF(lx + 4, ly + 8), 3.5, 3.5)
            p.setPen(_c("#B9CCEA", 225))
            p.drawText(QRectF(lx + 13, ly, tw, 18), Qt.AlignVCenter | Qt.AlignLeft, label)
            lx += tw + 6
        p.end()


# ---------------------------------------------------------------- 页面：日志
class LogTimeline(QWidget):
    """自绘时间线日志，避免等宽黑框的后台感。"""
    LEVEL = {
        "info": ("#8CA2C4", "信息"), "run": ("#4ADE80", "运行"),
        "ok": ("#86EFAC", "完成"), "warn": ("#FBBF24", "注意"),
        "error": ("#FB7185", "错误"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.setMinimumHeight(600)

    def set_rows(self, rows):
        self.rows = rows[-60:]
        self.setMinimumHeight(max(600, len(self.rows) * 46 + 40))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        r = QRectF(self.rect())
        x_line = 92
        p.setPen(QPen(_c("#FFFFFF", 24), 2.0))
        p.drawLine(QPointF(x_line, 20), QPointF(x_line, r.bottom() - 20))
        for i, (tm, level, agent, text) in enumerate(reversed(self.rows)):
            y = 24 + i * 46
            if y > r.bottom() - 30:
                break
            col, _ = self.LEVEL.get(level, ("#8CA2C4", ""))
            p.setFont(f_mono(10))
            p.setPen(_c("#8CA2C4", 215))
            p.drawText(QRectF(8, y, 74, 22), Qt.AlignVCenter | Qt.AlignRight, tm)
            p.setPen(Qt.NoPen)
            p.setBrush(_c(col, 235))
            p.drawEllipse(QPointF(x_line, y + 11), 5, 5)
            p.setBrush(_c("#0A1222", 220))
            p.drawEllipse(QPointF(x_line, y + 11), 2.2, 2.2)

            row = QRectF(x_line + 20, y - 3, r.width() - x_line - 40, 30)
            rp = rounded_path(row, 10)
            p.save(); p.setClipPath(rp)
            p.fillPath(rp, _c("#FFFFFF", 12))
            g = QLinearGradient(row.topLeft(), row.bottomRight())
            g.setColorAt(0, _c(col, 26)); g.setColorAt(1, _c("#FFFFFF", 4))
            p.fillPath(rp, QBrush(g))
            p.restore()
            p.setFont(f_bold(10))
            p.setPen(_c(col, 240))
            tag_w = 104
            p.drawText(QRectF(row.left() + 12, row.top(), tag_w - 8, row.height()),
                       Qt.AlignVCenter | Qt.AlignLeft,
                       p.fontMetrics().elidedText(agent, Qt.ElideRight, int(tag_w - 8)))
            # 竖向分隔，避免 Agent 名与内容粘连
            p.setPen(QPen(_c("#FFFFFF", 24), 1.0))
            p.drawLine(QPointF(row.left() + 12 + tag_w, row.top() + 6),
                       QPointF(row.left() + 12 + tag_w, row.bottom() - 6))
            p.setFont(f_cn(11))
            p.setPen(_c("#D6E4FA", 235))
            tw = max(60.0, row.width() - tag_w - 34)
            p.drawText(QRectF(row.left() + 20 + tag_w, row.top(), tw, row.height()),
                       Qt.AlignVCenter | Qt.AlignLeft,
                       p.fontMetrics().elidedText(text, Qt.ElideRight, int(tw)))
        p.end()


class LogsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        root = QVBoxLayout(self); root.setContentsMargins(34, 8, 34, 20); root.setSpacing(16)
        h1 = QLabel("执行日志"); h1.setFont(f_display(30)); h1.setStyleSheet("color:#F4F8FF;")
        sub = QLabel("Agent 执行过程的时间线，错误与完成会高亮标记")
        sub.setFont(f_cn(12)); sub.setStyleSheet("color:#93A7C6;")
        root.addWidget(h1); root.addWidget(sub)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.timeline = LogTimeline()
        scroll.setWidget(self.timeline)
        root.addWidget(scroll, 1)
        self.rows = []

    def seed(self, tasks):
        self.rows = []
        for t in tasks:
            for tm, lv, tx in t.logs:
                self.rows.append((tm, lv, t.agent, "[%s] %s" % (t.id, tx)))
        self.timeline.set_rows(self.rows)

    def append(self, tm, lv, agent, text):
        self.rows.append((tm, lv, agent, text))
        if len(self.rows) > 80:
            self.rows = self.rows[-80:]
        self.timeline.set_rows(self.rows)


# ---------------------------------------------------------------- 页面：预警
class AlertGlassCard(GlassCard):
    def __init__(self, task, on_jump, parent=None):
        super().__init__(parent, radius=20, base_alpha=108, padding=0)
        self.task = task
        self.on_jump = on_jump
        self.setFixedHeight(96)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        self.on_jump(self.task.id)
        super().mousePressEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = rounded_path(r, self.radius)
        label, color, soft = STATUS[self.task.status]
        paint_soft_shadow(p, r, self.radius, layers=5, spread=1.6, alpha=7)
        p.save(); p.setClipPath(path)
        paint_glass_surface(p, path, r, accent=color, base_alpha=104, gloss=0.9)
        p.restore()
        # 左侧色条
        p.save(); p.setClipPath(path)
        p.fillRect(QRectF(r.left(), r.top(), 5, r.height()), _c(color, 220))
        p.restore()
        x = r.left() + 24
        p.setFont(f_bold(10)); p.setPen(_c(soft, 240))
        p.drawText(QRectF(x, r.top() + 16, 120, 18), Qt.AlignVCenter | Qt.AlignLeft, label)
        p.setFont(f_bold(14)); p.setPen(_c("#FFFFFF", 248))
        nm = p.fontMetrics().elidedText(self.task.name, Qt.ElideRight, int(r.width() - 220))
        p.drawText(QRectF(x, r.top() + 36, r.width() - 220, 24),
                   Qt.AlignVCenter | Qt.AlignLeft, nm)
        p.setFont(f_mono(10)); p.setPen(_c("#8CA2C4", 210))
        p.drawText(QRectF(x, r.bottom() - 28, r.width() - 220, 18),
                   Qt.AlignVCenter | Qt.AlignLeft,
                   "%s  ·  %s / %s  ·  进度 %d%%" %
                   (self.task.id, self.task.agent, self.task.model, self.task.progress))
        p.setFont(f_cn(11)); p.setPen(_c("#9FB2D0", 220))
        p.drawText(QRectF(r.right() - 130, r.top(), 110, r.height()),
                   Qt.AlignVCenter | Qt.AlignRight, "查看任务  →")
        p.end()


class AlertsPage(QWidget):
    def __init__(self, on_jump, parent=None):
        super().__init__(parent)
        self.on_jump = on_jump
        self.setStyleSheet("background:transparent;")
        root = QVBoxLayout(self); root.setContentsMargins(34, 8, 34, 20); root.setSpacing(16)
        h1 = QLabel("预警中心"); h1.setFont(f_display(30)); h1.setStyleSheet("color:#F4F8FF;")
        self.sub = QLabel(""); self.sub.setFont(f_cn(12)); self.sub.setStyleSheet("color:#93A7C6;")
        root.addWidget(h1); root.addWidget(self.sub)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.host = QWidget(); self.host.setStyleSheet("background:transparent;")
        self.v = QVBoxLayout(self.host); self.v.setContentsMargins(2, 2, 10, 2)
        self.v.setSpacing(14); self.v.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.host)
        root.addWidget(scroll, 1)

    def refresh(self, tasks):
        while self.v.count():
            it = self.v.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None); w.deleteLater()
        alerts = [t for t in tasks if t.status in ("failed", "review", "paused")]
        order = {"failed": 0, "review": 1, "paused": 2}
        alerts.sort(key=lambda t: order.get(t.status, 9))
        self.sub.setText("共 %d 项需要关注 · 失败 / 待人工确认 / 已暂停" % len(alerts))
        if not alerts:
            empty = QLabel("全部正常，暂无需要关注的任务")
            empty.setFont(f_cn(14)); empty.setStyleSheet("color:#8CA2C4;")
            empty.setAlignment(Qt.AlignCenter)
            self.v.addWidget(empty)
        for t in alerts:
            self.v.addWidget(AlertGlassCard(t, self.on_jump))
        self.v.addStretch()


# ---------------------------------------------------------------- 主窗口
class StudioWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("%s · %s" % (APP_NAME, APP_SUB))
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(W, H)
        self.setMinimumSize(1120, 720)

        self.tasks = seed_tasks()
        self.live = True
        self.active_page = 0
        self.global_logs = []
        self._drag = None
        self._maximized = False

        # 局域网只读配对服务（保留上一轮验证过的链路）
        self.pair = PairServer()
        self.pair.start()
        self.pair.publish(self.tasks)

        # 液态玻璃悬浮窗
        self.overlay = GlassOverlay()
        self.overlay.set_tasks(self.tasks)
        self.overlay.request_show_main.connect(self._show_main_from_overlay)
        self.overlay.closed_by_user.connect(lambda: self.btn_overlay.setChecked(False))

        self._build_ui()
        self._build_shortcuts()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(2000)
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)
        self.refresh_all()
        # 布局稳定后再重排一次卡片网格，避免首次宽度为 0 时只排 1 列
        QTimer.singleShot(60, self._apply_cards)

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._apply_cards)

    # ------------------------------------------------------------ UI 构建
    def _build_ui(self):
        self.root = _StudioRoot(self)
        self.setCentralWidget(self.root)
        lay = QVBoxLayout(self.root)
        lay.setContentsMargins(MARGIN + 22, MARGIN + 12, MARGIN + 22, MARGIN + 16)
        lay.setSpacing(14)

        lay.addWidget(self._build_titlebar())
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background:transparent;")

        self.workbench = WorkbenchPage()
        self.workbench.filter_changed.connect(self._on_filter)
        self.workbench.new_task.connect(self.new_task)
        self.workbench.card_selected.connect(self._on_card_selected)
        self.stack.addWidget(self.workbench)

        self.overview = OverviewPage()
        self.stack.addWidget(self.overview)
        self.logs_page = LogsPage()
        self.stack.addWidget(self.logs_page)
        self.alerts = AlertsPage(self.jump_to_task)
        self.stack.addWidget(self.alerts)
        lay.addWidget(self.stack, 1)

        self.logs_page.seed(self.tasks)
        self.workbench.rebuild_cards(self.tasks)
        self._apply_cards()

    def _build_titlebar(self):
        bar = QWidget()
        bar.setFixedHeight(52)
        bar.setStyleSheet("background:transparent;")
        h = QHBoxLayout(bar); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(14)

        # 品牌
        brand = QWidget(); brand.setFixedWidth(210)
        bl = QHBoxLayout(brand); bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(10)
        logo = _LogoMark(); logo.setFixedSize(34, 34)
        bl.addWidget(logo)
        tv = QVBoxLayout(); tv.setSpacing(0)
        n = QLabel(APP_NAME); n.setFont(f_display(17)); n.setStyleSheet("color:#FFFFFF;")
        s = QLabel(APP_SUB); s.setFont(f_mono(8, True)); s.setStyleSheet("color:#7C91B2;")
        tv.addWidget(n); tv.addWidget(s)
        bl.addLayout(tv); bl.addStretch()
        h.addWidget(brand)

        h.addStretch()
        self.seg = Segmented()
        self.seg.changed.connect(self.on_page_changed)
        h.addWidget(self.seg)
        h.addStretch()

        # LIVE 指示
        self.live_label = QLabel("● LIVE")
        self.live_label.setFont(f_mono(10, True))
        self.live_label.setStyleSheet("color:#4ADE80;")
        h.addWidget(self.live_label)

        # 悬浮窗开关（醒目）
        self.btn_overlay = GlowButton("◈  悬浮窗")
        self.btn_overlay.setToolTip("打开液态玻璃悬浮窗，随时查看 Agent 进度")
        self.btn_overlay.clicked.connect(self.toggle_overlay)
        h.addWidget(self.btn_overlay)

        btn_pair = PlainButton("连接手机", fixed=100)
        btn_pair.clicked.connect(self.show_pair)
        h.addWidget(btn_pair)

        btn_csv = PlainButton("导出", fixed=68)
        btn_csv.clicked.connect(self.export_csv)
        h.addWidget(btn_csv)

        # 窗口按钮
        for glyph, kind, slot in (("—", "min", self.showMinimized),
                                  ("□", "max", self.toggle_maximize),
                                  ("×", "close", self.close)):
            b = WinButton(glyph, kind)
            b.clicked.connect(slot)
            h.addWidget(b)
        return bar

    def _build_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+M"), self, self.show_pair)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.workbench.search.setFocus())
        QShortcut(QKeySequence("Ctrl+E"), self, self.export_csv)
        QShortcut(QKeySequence("Ctrl+P"), self, self.toggle_live)
        QShortcut(QKeySequence("F5"), self, lambda: self.tick(force=True))
        QShortcut(QKeySequence("Ctrl+O"), self, self.toggle_overlay)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)

    # ------------------------------------------------------------ 窗口行为
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < 76:
            self._drag = _global_pos(e) - self.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(_global_pos(e) - self._drag)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.position().y() < 76:
            self.toggle_maximize()
        super().mouseDoubleClickEvent(e)

    def toggle_maximize(self):
        if self._maximized:
            self.showNormal(); self._maximized = False
        else:
            self.showMaximized(); self._maximized = True

    # ------------------------------------------------------------ 页面 / 悬浮窗
    def on_page_changed(self, i):
        self.active_page = i
        self.stack.setCurrentIndex(i)
        self.refresh_all()

    def _show_main_from_overlay(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_overlay(self, checked=None):
        on = self.btn_overlay.isChecked()
        if on:
            self.overlay.set_tasks(self.tasks)
            self.overlay.show_glass()
        else:
            self.overlay.hide_glass(notify=False)

    def open_overlay(self):
        self.btn_overlay.setChecked(True)
        self.overlay.set_tasks(self.tasks)
        self.overlay.show_glass()

    # ------------------------------------------------------------ 筛选 / 交互
    def _on_filter(self, key, text):
        self._apply_cards()

    def _apply_cards(self):
        self.workbench.apply_filter(self.workbench.cur_filter,
                                    self.workbench.search.text().strip(),
                                    self.tasks)

    def _on_card_selected(self, t):
        # 点击卡片跳到「日志」页看该任务的轨迹
        self.logs_page.timeline.set_rows(
            [(tm, lv, t.agent, tx) for tm, lv, tx in t.logs] or
            [(now_str(), "info", t.agent, "暂无日志")])
        self.seg.set_index(2)
        self.on_page_changed(2)

    def jump_to_task(self, tid):
        t = next((x for x in self.tasks if x.id == tid), None)
        if not t:
            return
        self.workbench.search.setText(t.id)
        self.seg.set_index(0)
        self.on_page_changed(0)
        self._apply_cards()

    # ------------------------------------------------------------ 数据 / 任务
    def new_task(self):
        dlg = _NewTaskDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        name, agent, model, pri = dlg.values()
        if not name:
            return
        tid = "AGT-%d" % (1043 + len(self.tasks))
        from pulse_core import Task
        t = Task(id=tid, name=name, agent=agent, model=model, status="queued",
                 progress=0, steps=[(s, "todo") for s in ["读取需求", "规划步骤", "开始执行"]],
                 elapsed=0, tokens=0, started=now_str(), updated=now_str(), priority=pri)
        t.add_log("info", "任务创建，分配至 %s / %s" % (agent, model))
        self.tasks.insert(0, t)
        self.workbench.rebuild_cards(self.tasks)
        self._apply_cards()
        self.logs_page.append(now_str(), "info", agent, "%s 已加入队列" % tid)
        self.refresh_all()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", "pulse_agent_tasks.csv",
                                             "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["任务ID", "任务名称", "Agent", "模型", "状态", "进度(%)",
                            "步骤", "耗时(s)", "Tokens", "优先级", "更新时间"])
                for t in self.tasks:
                    w.writerow([t.id, t.name, t.agent, t.model, STATUS[t.status][0],
                                t.progress, "%d/%d" % (t.steps_done, len(t.steps)),
                                t.elapsed, t.tokens, t.priority, t.updated])
            QMessageBox.information(self, "导出完成", "已导出 %d 条任务到：\n%s" %
                                   (len(self.tasks), path))
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def toggle_live(self):
        self.live = not self.live
        self.live_label.setText("● LIVE" if self.live else "○ PAUSED")
        self.live_label.setStyleSheet("color:%s;" % (T["green_hi"] if self.live else T["dim"]))
        self.workbench.setProperty("live", self.live)
        self.refresh_all()

    def show_pair(self):
        if self.pair.error:
            self.pair.start()
            self.pair.publish(self.tasks)
        open_pair_dialog(self, self.pair)

    # ------------------------------------------------------------ 实时推进
    def tick(self, force=False):
        if not self.live and not force:
            return
        changed = False
        for t in self.tasks:
            if t.status == "running":
                step = random.randint(1, 4) if not force else 1
                t.progress = min(100, t.progress + step)
                t.elapsed += 2
                t.tokens += random.randint(120, 640)
                t.updated = now_str()
                done_n = round(len(t.steps) * t.progress / 100)
                t.steps = [(s, "done" if j < done_n else ("active" if j == done_n else "todo"))
                           for j, (s, _) in enumerate(t.steps)]
                if t.progress >= 100:
                    t.status = "done"
                    t.add_log("ok", "全部步骤完成，结果已归档")
                    self.logs_page.append(now_str(), "ok", t.agent, "%s 完成" % t.id)
                elif random.random() < 0.28:
                    t.add_log("run", "步骤推进至 %d%%，已处理 %s tokens" %
                              (t.progress, fmt_tokens(t.tokens)))
                    self.logs_page.append(now_str(), "run", t.agent,
                                         "%s 进度 %d%%" % (t.id, t.progress))
                changed = True
            elif t.status == "queued" and random.random() < 0.12:
                t.status = "running"
                t.add_log("run", "任务出队，开始执行")
                self.logs_page.append(now_str(), "run", t.agent, "%s 开始执行" % t.id)
                changed = True
            elif t.status == "review" and random.random() < 0.05:
                t.status = "running"
                t.add_log("run", "人工确认通过，继续执行")
                changed = True
        if changed or force:
            self.refresh_all()

    def refresh_all(self):
        s = summarise(self.tasks)
        self.workbench.update_stats(s)
        self._update_clock()
        # 卡片数据原地刷新（不重建，避免闪烁与布局重入）
        for t in self.tasks:
            c = self.workbench.cards.get(t.id)
            if c:
                c.set_task(t)
        if self.active_page == 1:
            self.overview.refresh(self.tasks)
        if self.active_page == 3:
            self.alerts.refresh(self.tasks)
        # 悬浮窗实时同步
        if self.overlay.isVisible():
            self.overlay.set_tasks(self.tasks)
        # 只读快照（主线程序列化，不与 HTTP 线程共享对象）
        self.pair.publish(self.tasks)

    def _update_clock(self):
        d = datetime.now().strftime("%m月%d日  %H:%M:%S")
        self.workbench.set_clock("%s   ·   v%s" % (d, APP_VER))

    def closeEvent(self, event):
        try:
            self.pair.stop()
        except Exception:
            pass
        try:
            self.overlay._aurora_timer.stop()
            self.overlay.close()
        except Exception:
            pass
        super().closeEvent(event)


class _StudioRoot(QWidget):
    """中央背景：圆角 + 阴影 + 低强度 Aurora 光晕。"""
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)
        path = rounded_path(r, RADIUS)
        paint_soft_shadow(p, r, RADIUS, layers=9, spread=2.6, alpha=11)
        p.save()
        p.setClipPath(path)
        paint_aurora(p, r, phase=0.0, strength=0.34, dark_base=T["bg"])
        # 顶部压一层深蓝，让标题栏更沉稳
        vg = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + 240))
        vg.setColorAt(0, _c("#0A1120", 150))
        vg.setColorAt(1, _c("#0A1120", 0))
        p.fillRect(r, QBrush(vg))
        p.restore()
        p.save()
        p.setBrush(Qt.NoBrush)
        rim = QLinearGradient(r.topLeft(), r.bottomRight())
        rim.setColorAt(0, _c("#FFFFFF", 70))
        rim.setColorAt(0.5, _c("#FFFFFF", 14))
        rim.setColorAt(1, _c(T["cyan"], 40))
        p.setPen(QPen(QBrush(rim), 1.4))
        p.drawPath(path)
        p.restore()
        p.end()


class _LogoMark(QWidget):
    """品牌脉冲波形标记。"""
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, _c(T["green_hi"], 255))
        g.setColorAt(1, _c(T["cyan"], 255))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(g))
        p.drawRoundedRect(r, 11, 11)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_c("#07131E", 235), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = QPainterPath()
        pts = [(0.10, 0.56), (0.28, 0.56), (0.40, 0.28), (0.54, 0.76),
               (0.66, 0.42), (0.76, 0.56), (0.90, 0.56)]
        path.moveTo(r.left() + r.width() * pts[0][0], r.top() + r.height() * pts[0][1])
        for x, y in pts[1:]:
            path.lineTo(r.left() + r.width() * x, r.top() + r.height() * y)
        p.drawPath(path)
        p.end()


class _NewTaskDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建 Agent 任务")
        self.setFixedWidth(420)
        self.setStyleSheet(
            "QDialog{background:#0C1424;}"
            "QLabel{color:#C3D3EC;font-size:12px;background:transparent;border:0;}")
        v = QVBoxLayout(self); v.setContentsMargins(24, 22, 24, 20); v.setSpacing(12)
        t = QLabel("新建 Agent 任务"); t.setFont(f_display(19)); t.setStyleSheet("color:#FFFFFF;")
        v.addWidget(t)
        self.name = QLineEdit(); self.name.setPlaceholderText("任务名称，例如：数据看板指标校验")
        v.addWidget(QLabel("任务名称")); v.addWidget(self.name)
        self.agent = QComboBox()
        for name, role, model in AGENTS:
            self.agent.addItem(name, (name, model))
        v.addWidget(QLabel("执行 Agent")); v.addWidget(self.agent)
        self.pri = QComboBox()
        for x in PRIORITIES:
            self.pri.addItem(x)
        v.addWidget(QLabel("优先级")); v.addWidget(self.pri)
        row = QHBoxLayout(); row.addStretch()
        cancel = PlainButton("取消"); cancel.clicked.connect(self.reject)
        ok = PlainButton("创建任务", primary=True); ok.clicked.connect(self.accept)
        row.addWidget(cancel); row.addWidget(ok)
        v.addLayout(row)

    def values(self):
        name, model = self.agent.currentData()
        return self.name.text().strip(), name, model, self.pri.currentText()


# ---------------------------------------------------------------- 入口
def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    load_fonts()
    win = StudioWindow()
    win.show()
    argv = sys.argv

    def arg(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default

    if "--pair-info" in argv:
        import json
        info = {
            "version": APP_VER, "host": win.pair.host, "port": win.pair.port,
            "token": win.pair.state.token, "url": win.pair.url(),
            "health_url": win.pair.health_url(), "error": win.pair.error,
        }
        try:
            with open(arg("--pair-info", "/tmp/pulse_pair_info.json"), "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
            print("PAIR_INFO_OK")
        except Exception as e:
            print("PAIR_INFO_FAILED %s" % e)

    if "--pair-qr" in argv:
        try:
            save_qr_png(win.pair.url(), arg("--pair-qr", "/tmp/pulse_pair_qr.png"))
            print("PAIR_QR_OK")
        except Exception as e:
            print("PAIR_QR_FAILED %s" % e)

    if "--pair-shot" in argv:
        from pulse_pair_server import PairDialog

        def capture_pair():
            app.processEvents()
            dlg = PairDialog(win.pair, win)
            dlg.show(); app.processEvents()
            print("PAIR_SHOT", dlg.grab().save(arg("--pair-shot", "/tmp/pulse_pair_shot.png")))
            dlg.close()
        QTimer.singleShot(1200, capture_pair)

    if "--open-overlay" in argv or "--overlay-shot" in argv or "--overlay-collapsed-shot" in argv:
        QTimer.singleShot(500, win.open_overlay)

    if "--page" in argv:
        try:
            i = int(arg("--page", "0"))
            if 0 <= i <= 3:
                win.seg.set_index(i)
                win.on_page_changed(i)
        except ValueError:
            pass

    if "--size" in argv:
        try:
            i = argv.index("--size")
            win.resize(int(argv[i + 1]), int(argv[i + 2]))
        except (ValueError, IndexError):
            pass

    if "--screenshot" in argv:
        def capture():
            app.processEvents()
            print("SCREENSHOT", win.grab().save(arg("--screenshot", "/tmp/pulse_studio.png")))
            app.quit()
        QTimer.singleShot(1400, capture)

    for flag, path, collapsed in (
        ("--overlay-shot", arg("--overlay-shot", "/tmp/pulse_overlay.png"), False),
        ("--overlay-collapsed-shot", arg("--overlay-collapsed-shot", "/tmp/pulse_overlay_min.png"), True),
    ):
        if flag in argv:
            def cap(p=path, col=collapsed):
                app.processEvents()
                if col:
                    win.overlay._set_reveal(0.0)
                app.processEvents()
                print("OVERLAY_SHOT", p, win.overlay.grab().save(p))
            QTimer.singleShot(1100, cap)

    if "--serve-seconds" in argv:
        try:
            QTimer.singleShot(int(float(arg("--serve-seconds", "30")) * 1000), app.quit)
        except ValueError:
            pass
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
