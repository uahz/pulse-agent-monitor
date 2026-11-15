# -*- coding: utf-8 -*-
"""
PULSE · Agent Console  —  Agent 任务进度表（PC 原生桌面版）

技术栈：Python 3 + PySide6 / Qt Widgets
纯原生控件绘制，无 HTML / WebView / 浏览器内核，离线可用。

运行：
    python pulse_agent_console.py
参数（用于自动化验证）：
    --screenshot <path>     启动后保存窗口截图并退出
    --page <0|1|2|3>       初始页面
    --size <W> <H>         窗口尺寸

设计系统：design-system/PC-MASTER.md（ui-ux-pro-max-skill 驱动）
"""
import csv
import glob
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime

from pulse_pair_server import PairServer, open_pair_dialog, save_qr_png

from PySide6.QtCore import (
    Qt, QRect, QSize, QTimer, QSortFilterProxyModel, QAbstractTableModel,
    QModelIndex, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QPainter, QPen, QBrush, QPalette,
    QTextCharFormat, QTextCursor, QShortcut, QKeySequence, QAction,
    QLinearGradient, QCursor,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QLineEdit, QComboBox, QTableView, QHeaderView, QAbstractItemView,
    QStyledItemDelegate, QStyle, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSplitter, QStackedWidget, QPlainTextEdit, QProgressBar, QStatusBar,
    QCheckBox, QScrollArea, QFileDialog, QMessageBox, QDialog, QSizePolicy,
    QMenuBar, QMenu, QToolTip,
)

APP_NAME = "PULSE · Agent Console"
APP_VER = "1.3.0"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RES_DIR = os.path.join(BASE_DIR, "resources")

# ---------------------------------------------------------------- 设计令牌
C = {
    "bg": "#0F172A", "sidebar": "#0B1322", "surface": "#16223A",
    "surface2": "#1E293B", "surface3": "#243349", "row_alt": "#142137",
    "row": "#111C30", "hover": "#1B2C48", "selected": "#223B55",
    "border": "#22304A", "border_soft": "#1E293B",
    "text": "#F8FAFC", "muted": "#94A3B8", "dim": "#64748B",
    "green": "#22C55E", "green_hi": "#4ADE80", "green_soft": "#6EE7A0",
    "amber": "#F59E0B", "red": "#EF4444", "blue": "#3B82F6",
    "violet": "#A78BFA",
}

STATUS = {
    "running": ("运行中", C["green"]),
    "queued": ("排队中", C["dim"]),
    "review": ("待人工确认", C["amber"]),
    "done": ("已完成", C["green_hi"]),
    "failed": ("失败", C["red"]),
    "paused": ("已暂停", C["blue"]),
}

AGENTS = [
    ("Orchestrator", "调度编排", "GPT-4o"),
    ("DataCollector", "数据采集", "本地 Qwen2.5"),
    ("Planner", "任务规划", "Claude-3.5"),
    ("Coder", "代码生成", "Claude-3.5"),
    ("Reviewer", "结果复核", "GPT-4o"),
    ("Deployer", "发布部署", "本地 Qwen2.5"),
]

PRIORITIES = ["高", "中", "低"]

QSS = """
QWidget { color:#F8FAFC; font-family:'Fira Sans'; font-size:12px; }
QMainWindow { background:#0F172A; }
QToolTip { background:#243349; color:#F8FAFC; border:1px solid #3B4A63; padding:6px 8px; border-radius:6px; }

QLineEdit, QComboBox {
    background:#1E293B; border:1px solid #2C3C55; border-radius:8px;
    padding:0 12px; min-height:34px; color:#F8FAFC; selection-background-color:#22C55E;
}
QLineEdit:focus, QComboBox:focus { border-color:#22C55E; }
QLineEdit::placeholder { color:#64748B; }
QComboBox::drop-down { border:0; width:24px; }
QComboBox::down-arrow { image:none; border-left:4px solid transparent; border-right:4px solid transparent; border-top:5px solid #94A3B8; margin-right:10px; }
QComboBox QAbstractItemView { background:#1E293B; border:1px solid #2C3C55; selection-background-color:#243349; color:#F8FAFC; outline:0; }

QPushButton {
    background:#1E293B; border:1px solid #2C3C55; border-radius:8px;
    padding:0 14px; min-height:34px; color:#E2E8F0; font-size:12px;
}
QPushButton:hover { background:#243349; border-color:#3B4A63; }
QPushButton:pressed { background:#2C3C55; }
QPushButton:disabled { color:#64748B; background:#16223A; border-color:#22304A; }
QPushButton#primary { background:#22C55E; color:#0F172A; font-weight:700; border:0; }
QPushButton#primary:hover { background:#4ADE80; }
QPushButton#ghost { background:transparent; border-color:transparent; color:#94A3B8; }
QPushButton#ghost:hover { background:#1E293B; color:#F8FAFC; }
QPushButton#nav { text-align:left; padding:0 14px; min-height:42px; border:0; background:transparent; border-radius:8px; color:#94A3B8; font-size:13px; }
QPushButton#nav:hover { background:#16223A; color:#F8FAFC; }
QPushButton#nav:checked { background:#1B3A2C; color:#6EE7A0; font-weight:600; }

QTableView {
    background:#111C30; border:1px solid #22304A; border-radius:10px;
    gridline-color:#1E293B; outline:0; selection-color:#F8FAFC;
}
QHeaderView::section {
    background:#16223A; color:#94A3B8; font-family:'Fira Code'; font-size:11px;
    border:0; border-bottom:1px solid #22304A; border-right:1px solid #1E293B;
    padding:0 12px; height:40px; text-align:left;
}
QHeaderView::section:hover { background:#1E293B; color:#F8FAFC; }
QTableView::item { border:0; }
QTableView QTableCornerButton::section { background:#16223A; border:0; }

QScrollBar:vertical { background:transparent; width:10px; margin:0; border:0; }
QScrollBar:horizontal { background:transparent; height:10px; margin:0; border:0; }
QScrollBar::handle:vertical { background:#2C3C55; border-radius:5px; min-height:32px; }
QScrollBar::handle:horizontal { background:#2C3C55; border-radius:5px; min-width:32px; }
QScrollBar::handle:hover { background:#3B4A63; }
QScrollBar::add-line, QScrollBar::sub-line { height:0; width:0; }
QScrollBar::add-page, QScrollBar::sub-page { background:transparent; }

QStatusBar { background:#0B1322; color:#64748B; border-top:1px solid #1E293B; font-family:'Fira Code'; font-size:11px; }
QStatusBar::item { border:0; }
QMenuBar { background:#0B1322; color:#94A3B8; border-bottom:1px solid #1E293B; padding:2px 6px; }
QMenuBar::item:selected { background:#1E293B; color:#F8FAFC; border-radius:4px; }
QMenu { background:#16223A; border:1px solid #2C3C55; color:#F8FAFC; padding:4px; }
QMenu::item { padding:7px 22px; border-radius:5px; }
QMenu::item:selected { background:#243349; }

QPlainTextEdit { background:#0B1322; border:1px solid #22304A; border-radius:8px; font-family:'Fira Code'; font-size:11px; color:#94A3B8; padding:8px; }
QProgressBar { background:#243349; border:0; border-radius:5px; height:9px; text-align:right; }
QProgressBar::chunk { background:#22C55E; border-radius:5px; }
QSplitter::handle { background:#1E293B; width:3px; }
QSplitter::handle:hover { background:#22C55E; }
QCheckBox { color:#94A3B8; spacing:8px; }
QCheckBox::indicator { width:32px; height:18px; border-radius:9px; background:#2C3C55; border:1px solid #3B4A63; }
QCheckBox::indicator:checked { background:#22C55E; border-color:#22C55E; }
QDialog { background:#0F172A; }
"""

CARD_QSS = "QFrame{background:#16223A;border:1px solid #22304A;border-radius:12px;}"


def font_mono(size=11, bold=False):
    f = QFont("Fira Code", size)
    f.setStyleHint(QFont.Monospace)
    f.setBold(bold)
    return f


def font_body(size=12, bold=False):
    f = QFont("Fira Sans", size)
    f.setBold(bold)
    return f


def now_str():
    return datetime.now().strftime("%H:%M:%S")


def fmt_elapsed(sec):
    if sec < 60:
        return "%ds" % sec
    if sec < 3600:
        return "%dm%02ds" % (sec // 60, sec % 60)
    return "%dh%02dm" % (sec // 3600, (sec % 3600) // 60)


def load_fonts():
    loaded = []
    for path in sorted(glob.glob(os.path.join(RES_DIR, "fonts", "*.ttf"))):
        if QFontDatabase.addApplicationFont(path) >= 0:
            loaded.append(os.path.basename(path))
    return loaded


# ---------------------------------------------------------------- 数据模型
@dataclass
class Task:
    id: str
    name: str
    agent: str
    model: str
    status: str
    progress: int
    steps: list
    elapsed: int
    tokens: int
    started: str
    updated: str
    priority: str
    logs: list = field(default_factory=list)

    @property
    def steps_done(self):
        return sum(1 for s in self.steps if s[1] == "done")

    def add_log(self, level, text):
        self.logs.append((now_str(), level, text))
        if len(self.logs) > 60:
            self.logs = self.logs[-60:]


def seed_tasks():
    raw = [
        ("AGT-1042", "实时进度看板 · 指标聚合与钻取", "DataCollector", "本地 Qwen2.5", "running", 72, "高",
         ["接入数据源", "字段映射校验", "增量聚合计算", "异常值过滤", "写入时序库", "生成指标快照", "一致性校验", "发布到看板"]),
        ("AGT-1041", "多源采集网关 · 断点续传改造", "Coder", "Claude-3.5", "running", 48, "高",
         ["读取需求文档", "设计幂等写入", "实现断点续传", "补充单元测试", "压测延迟", "代码复核"]),
        ("AGT-1040", "预警规则引擎 DSL 草案", "Planner", "Claude-3.5", "review", 88, "中",
         ["梳理规则场景", "定义语法", "编写示例", "评审反馈", "修订定稿"]),
        ("AGT-1039", "移动端推送通道联调", "Deployer", "本地 Qwen2.5", "failed", 34, "高",
         ["准备测试环境", "建立长连接", "发送测试消息", "校验触达", "排查失败原因"]),
        ("AGT-1038", "团队协作模块回归测试", "Reviewer", "GPT-4o", "done", 100, "中",
         ["生成用例", "执行回归", "比对快照", "输出报告"]),
        ("AGT-1037", "图表主题令牌化重构", "Coder", "Claude-3.5", "running", 61, "中",
         ["抽取颜色令牌", "替换硬编码", "深色对比度校验", "回归截图比对"]),
        ("AGT-1036", "周报自动汇总与分发", "Orchestrator", "GPT-4o", "queued", 0, "低",
         ["收集各 Agent 结果", "生成摘要", "排版", "发送"]),
        ("AGT-1035", "日志脱敏与合规扫描", "Reviewer", "GPT-4o", "done", 100, "高",
         ["定义敏感字段", "扫描全量日志", "生成合规报告"]),
        ("AGT-1034", "采集延迟压测报告", "DataCollector", "本地 Qwen2.5", "paused", 27, "中",
         ["搭建压测环境", "构造负载", "采集指标", "输出结论"]),
        ("AGT-1033", "灰度发布方案评审", "Deployer", "本地 Qwen2.5", "running", 55, "高",
         ["拟定灰度批次", "配置回滚策略", "演练", "评审"]),
        ("AGT-1032", "空状态与骨架屏实现", "Coder", "Claude-3.5", "done", 100, "低",
         ["设计空状态", "实现骨架屏", "无障碍校验"]),
        ("AGT-1031", "知识库索引增量更新", "DataCollector", "本地 Qwen2.5", "queued", 0, "中",
         ["扫描变更文档", "重建向量索引", "校验召回率"]),
    ]
    tasks = []
    for i, (tid, name, agent, model, st, prog, pri, steps) in enumerate(raw):
        states = []
        total = len(steps)
        done_n = round(total * prog / 100)
        for j, s in enumerate(steps):
            if j < done_n:
                states.append((s, "done"))
            elif j == done_n and st in ("running", "paused", "review", "failed"):
                states.append((s, "active" if st == "running" else "blocked"))
            else:
                states.append((s, "todo"))
        t = Task(
            id=tid, name=name, agent=agent, model=model, status=st, progress=prog,
            steps=states, elapsed=random.randint(95, 2400), tokens=random.randint(3200, 48000),
            started="%02d:%02d:%02d" % (9 + i % 8, (i * 7) % 60, (i * 13) % 60),
            updated=now_str(), priority=pri,
        )
        t.add_log("info", "任务创建，分配至 %s / %s" % (agent, model))
        t.add_log("info", "已加载 %d 个执行步骤" % total)
        if st == "running":
            t.add_log("run", "开始执行步骤 %d：%s" % (done_n + 1, steps[min(done_n, total - 1)]))
        elif st == "failed":
            t.add_log("error", "执行中断：下游服务返回 503，等待重试")
        elif st == "review":
            t.add_log("warn", "产出待人工确认，已暂停自动推进")
        elif st == "done":
            t.add_log("ok", "全部步骤完成，结果已归档")
        tasks.append(t)
    return tasks


HEADERS = ["任务", "Agent", "状态", "进度", "步骤", "耗时", "Tokens", "更新时间"]
COL_WIDTH = [255, 124, 106, 165, 70, 82, 88, 92]
COL_KEY = ["task", "agent", "status", "progress", "steps", "elapsed", "tokens", "updated"]


class TaskModel(QAbstractTableModel):
    def __init__(self, tasks, parent=None):
        super().__init__(parent)
        self.tasks = tasks

    def rowCount(self, parent=QModelIndex()):
        return len(self.tasks)

    def columnCount(self, parent=QModelIndex()):
        return len(HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return HEADERS[section]
        if role == Qt.FontRole and orientation == Qt.Horizontal:
            return font_mono(11, True)
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        t = self.tasks[index.row()]
        col = index.column()
        if role == Qt.UserRole:
            return t
        if role == Qt.UserRole + 1:
            return t.progress
        if role == Qt.UserRole + 2:  # 排序键
            if col == 0:
                return t.name
            if col == 1:
                return t.agent
            if col == 2:
                return {"failed": 0, "review": 1, "running": 2, "paused": 3, "queued": 4, "done": 5}[t.status]
            if col == 3:
                return t.progress
            if col == 4:
                return t.steps_done
            if col == 5:
                return t.elapsed
            if col == 6:
                return t.tokens
            return t.updated
        if role != Qt.DisplayRole:
            return None
        if col == 0:
            return t.name
        if col == 1:
            return t.agent
        if col == 2:
            return STATUS[t.status][0]
        if col == 3:
            return t.progress
        if col == 4:
            return "%d/%d" % (t.steps_done, len(t.steps))
        if col == 5:
            return fmt_elapsed(t.elapsed)
        if col == 6:
            return "{:,}".format(t.tokens)
        return t.updated

    def refresh(self):
        if self.rowCount() == 0:
            return
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, self.columnCount() - 1))


class TaskProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.search = ""
        self.status_filter = "all"
        self.agent_filter = "all"
        self.setDynamicSortFilter(True)
        self.setSortRole(Qt.UserRole + 2)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def filterAcceptsRow(self, row, parent):
        m = self.sourceModel()
        if not m:
            return True
        t = m.tasks[row]
        if self.status_filter != "all" and t.status != self.status_filter:
            return False
        if self.agent_filter != "all" and t.agent != self.agent_filter:
            return False
        if self.search:
            hay = (t.id + " " + t.name + " " + t.agent + " " + t.model).lower()
            if self.search.lower() not in hay:
                return False
        return True


# ---------------------------------------------------------------- 表格绘制
class CellDelegate(QStyledItemDelegate):
    """全部单元格由 QPainter 原生绘制：进度条、状态徽章、等宽数字。"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        t = index.data(Qt.UserRole)
        if t is None:
            return
        col = index.column()
        r = QRect(option.rect)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 行背景
        if option.state & QStyle.State_Selected:
            bg = QColor(C["selected"])
        elif option.state & QStyle.State_MouseOver:
            bg = QColor(C["hover"])
        else:
            bg = QColor(C["row"] if index.row() % 2 == 0 else C["row_alt"])
        painter.fillRect(r, bg)
        painter.setPen(QPen(QColor("#1C2A42")))
        painter.drawLine(r.left(), r.bottom(), r.right(), r.bottom())

        pad = 12
        if col == 3:
            self._paint_progress(painter, r, t, pad)
        elif col == 2:
            self._paint_status(painter, r, t, pad)
        else:
            self._paint_text(painter, r, t, col, pad)
        painter.restore()

    def _paint_progress(self, p, r, t, pad):
        color = QColor(STATUS[t.status][1])
        if t.status == "queued":
            color = QColor(C["dim"])
        bar_w = max(50, r.width() - pad * 2 - 44)
        h = 8
        x = r.left() + pad
        y = r.center().y() - h // 2
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(C["surface3"])))
        p.drawRoundedRect(QRect(x, y, bar_w, h), 4, 4)
        fw = int(bar_w * t.progress / 100)
        if fw > 0:
            grad = QLinearGradient(x, y, x + max(fw, 1), y)
            grad.setColorAt(0, color.darker(115))
            grad.setColorAt(1, color)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRect(x, y, max(fw, 8), h), 4, 4)
        p.setFont(font_mono(10, True))
        p.setPen(QColor("#CBD5E1"))
        tr = QRect(r.right() - pad - 42, r.top(), 42, r.height())
        p.drawText(tr, Qt.AlignRight | Qt.AlignVCenter, "%d%%" % t.progress)

    def _paint_status(self, p, r, t, pad):
        label, color = STATUS[t.status]
        cx = r.left() + pad + 5
        cy = r.center().y()
        # 运行中：外圈脉冲
        if t.status == "running":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(34, 197, 94, 40))
            p.drawEllipse(cx - 7, cy - 7, 14, 14)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawEllipse(cx - 4, cy - 4, 8, 8)
        p.setFont(font_body(11, True))
        p.setPen(QColor(color))
        tr = QRect(r.left() + pad + 18, r.top(), r.width() - pad - 20, r.height())
        p.drawText(tr, Qt.AlignLeft | Qt.AlignVCenter, label)

    def _paint_text(self, p, r, t, col, pad):
        if col == 0:
            # 任务名 + 下方小字 ID / 优先级
            p.setFont(font_body(12, True))
            p.setPen(QColor(C["text"]))
            name_rect = QRect(r.left() + pad, r.top() + 6, r.width() - pad * 2 - 46, 22)
            name = p.fontMetrics().elidedText(t.name, Qt.ElideRight, name_rect.width())
            p.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter, name)
            p.setFont(font_mono(9))
            p.setPen(QColor(C["dim"]))
            sub = QRect(r.left() + pad, r.top() + 27, r.width() - pad * 2, 16)
            sub_text = t.id + "  ·  " + t.model
            p.drawText(sub, Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(sub_text, Qt.ElideRight, sub.width()))
            pri_color = {"高": C["red"], "中": C["amber"], "低": C["dim"]}[t.priority]
            p.setFont(font_mono(9, True))
            p.setPen(QColor(pri_color))
            badge = QRect(r.right() - pad - 30, r.center().y() - 9, 30, 18)
            p.setBrush(QColor(pri_color).darker(500))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(badge, 5, 5)
            p.setPen(QColor(pri_color))
            p.drawText(badge, Qt.AlignCenter, t.priority)
            return

        val = index_text(t, col)
        mono = col in (4, 5, 6, 7, 1)
        p.setFont(font_mono(11) if mono else font_body(12))
        if col == 1:
            p.setPen(QColor("#B6C2D4"))
        elif col == 4:
            p.setPen(QColor(C["green_soft"] if t.steps_done == len(t.steps) else C["muted"]))
        elif col == 7:
            p.setPen(QColor(C["dim"]))
        else:
            p.setPen(QColor("#CBD5E1"))
        tr = QRect(r.left() + pad, r.top(), r.width() - pad * 2, r.height())
        align = Qt.AlignLeft | Qt.AlignVCenter
        if col in (5, 6, 7):
            align = Qt.AlignRight | Qt.AlignVCenter
        p.drawText(tr, align, p.fontMetrics().elidedText(val, Qt.ElideRight, tr.width()))

    def sizeHint(self, option, index):
        return QSize(COL_WIDTH[index.column()], 52)


def index_text(t, col):
    if col == 1:
        return t.agent
    if col == 4:
        return "%d/%d" % (t.steps_done, len(t.steps))
    if col == 5:
        return fmt_elapsed(t.elapsed)
    if col == 6:
        return "{:,}".format(t.tokens)
    if col == 7:
        return t.updated
    return ""


# ---------------------------------------------------------------- 组件
class KpiCard(QFrame):
    def __init__(self, title, value, foot, accent, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(CARD_QSS + "QFrame{border-left:3px solid %s;}" % accent)
        self.setFixedHeight(96)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(2)
        t = QLabel(title); t.setFont(font_body(11)); t.setStyleSheet("color:#94A3B8;background:transparent;border:0;")
        self.v = QLabel(value); self.v.setFont(font_mono(26, True)); self.v.setStyleSheet("color:%s;background:transparent;border:0;" % accent)
        f = QLabel(foot); f.setFont(font_body(10)); f.setStyleSheet("color:#64748B;background:transparent;border:0;")
        self.foot_label = f
        lay.addWidget(t); lay.addWidget(self.v); lay.addWidget(f)

    def set_value(self, value, foot=None):
        self.v.setText(value)
        if foot is not None:
            self.foot_label.setText(foot)


class Sidebar(QFrame):
    nav_changed = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("QFrame{background:#0B1322;border-right:1px solid #1E293B;border:0;border-right:1px solid #1E293B;}")
        self.setFixedWidth(232)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 20, 16, 16)
        lay.setSpacing(6)

        # 品牌
        brand = QHBoxLayout(); brand.setSpacing(10)
        mark = QLabel("◉"); mark.setFont(font_mono(22, True))
        mark.setStyleSheet("color:#22C55E;background:transparent;border:0;")
        box = QVBoxLayout(); box.setSpacing(0)
        b1 = QLabel("PULSE"); b1.setFont(font_mono(16, True)); b1.setStyleSheet("color:#F8FAFC;background:transparent;border:0;letter-spacing:2px;")
        b2 = QLabel("AGENT CONSOLE"); b2.setFont(font_mono(9)); b2.setStyleSheet("color:#64748B;background:transparent;border:0;")
        box.addWidget(b1); box.addWidget(b2)
        brand.addWidget(mark); brand.addLayout(box); brand.addStretch()
        lay.addLayout(brand)
        lay.addSpacing(22)

        cap = QLabel("工作区"); cap.setFont(font_mono(9, True))
        cap.setStyleSheet("color:#64748B;background:transparent;border:0;letter-spacing:1px;")
        lay.addWidget(cap)
        lay.addSpacing(4)

        self.nav_buttons = []
        items = [("任务进度表", 0), ("运行概览", 1), ("执行日志", 2), ("预警中心", 3)]
        for text, idx in items:
            b = QPushButton("  " + text)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setChecked(idx == 0)
            b.setProperty("page", idx)
            lay.addWidget(b)
            self.nav_buttons.append(b)
        lay.addSpacing(20)

        cap2 = QLabel("AGENT 在线"); cap2.setFont(font_mono(9, True))
        cap2.setStyleSheet("color:#64748B;background:transparent;border:0;letter-spacing:1px;")
        lay.addWidget(cap2)
        lay.addSpacing(4)
        self.agent_rows = []
        for name, role, model in AGENTS:
            row = QHBoxLayout(); row.setSpacing(8); row.setContentsMargins(0, 0, 0, 0)
            dot = QLabel("●"); dot.setFont(font_mono(10)); dot.setStyleSheet("color:#22C55E;background:transparent;border:0;")
            n = QLabel(name); n.setFont(font_body(11)); n.setStyleSheet("color:#B6C2D4;background:transparent;border:0;")
            cnt = QLabel("0"); cnt.setFont(font_mono(10)); cnt.setStyleSheet("color:#64748B;background:transparent;border:0;")
            row.addWidget(dot); row.addWidget(n); row.addStretch(); row.addWidget(cnt)
            wrap = QWidget(); wrap.setLayout(row)
            wrap.setStyleSheet("background:transparent;")
            lay.addWidget(wrap)
            self.agent_rows.append((name, dot, cnt))

        lay.addStretch()
        line = QFrame(); line.setFixedHeight(1); line.setStyleSheet("background:#1E293B;border:0;")
        lay.addWidget(line)
        lay.addSpacing(8)
        ver = QLabel("v%s  ·  本地离线模式" % APP_VER)
        ver.setFont(font_mono(9)); ver.setStyleSheet("color:#64748B;background:transparent;border:0;")
        lay.addWidget(ver)

    def update_counts(self, tasks):
        for name, dot, cnt in self.agent_rows:
            own = [t for t in tasks if t.agent == name]
            running = [t for t in own if t.status == "running"]
            cnt.setText(str(len(own)))
            color = "#22C55E" if running else ("#64748B" if not own else "#3B82F6")
            dot.setStyleSheet("color:%s;background:transparent;border:0;" % color)


class DetailPanel(QFrame):
    def __init__(self, on_action, parent=None):
        super().__init__(parent)
        self.on_action = on_action
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("QFrame{background:#111C30;border:1px solid #22304A;border-radius:12px;}")
        self.setMinimumWidth(310)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)

        head = QHBoxLayout()
        cap = QLabel("任务详情"); cap.setFont(font_mono(10, True))
        cap.setStyleSheet("color:#94A3B8;background:transparent;border:0;letter-spacing:1px;")
        head.addWidget(cap); head.addStretch()
        self.id_label = QLabel("—"); self.id_label.setFont(font_mono(10))
        self.id_label.setStyleSheet("color:#64748B;background:transparent;border:0;")
        head.addWidget(self.id_label)
        lay.addLayout(head)

        self.title = QLabel("选择一条任务查看详情")
        self.title.setFont(font_body(15, True))
        self.title.setWordWrap(True)
        self.title.setStyleSheet("color:#F8FAFC;background:transparent;border:0;")
        self.title.setMinimumHeight(46)
        lay.addWidget(self.title)

        self.badge = QLabel("—"); self.badge.setFont(font_body(11, True))
        self.badge.setStyleSheet("background:#1E293B;color:#94A3B8;border-radius:6px;padding:4px 10px;")
        self.badge.setFixedHeight(26)
        lay.addWidget(self.badge)

        grid = QGridLayout(); grid.setSpacing(8)
        self.fields = {}
        for i, (k, label) in enumerate([("agent", "Agent"), ("model", "模型"), ("started", "开始"), ("elapsed", "耗时"), ("tokens", "Tokens"), ("priority", "优先级")]):
            lb = QLabel(label); lb.setFont(font_body(10)); lb.setStyleSheet("color:#64748B;background:transparent;border:0;")
            v = QLabel("—"); v.setFont(font_mono(11)); v.setStyleSheet("color:#CBD5E1;background:transparent;border:0;")
            grid.addWidget(lb, i // 2, (i % 2) * 2)
            grid.addWidget(v, i // 2, (i % 2) * 2 + 1)
            self.fields[k] = v
        lay.addLayout(grid)

        lay.addSpacing(4)
        prow = QHBoxLayout()
        pl = QLabel("整体进度"); pl.setFont(font_body(11)); pl.setStyleSheet("color:#94A3B8;background:transparent;border:0;")
        self.pct = QLabel("0%"); self.pct.setFont(font_mono(20, True)); self.pct.setStyleSheet("color:#22C55E;background:transparent;border:0;")
        prow.addWidget(pl); prow.addStretch(); prow.addWidget(self.pct)
        lay.addLayout(prow)
        self.bar = QProgressBar(); self.bar.setValue(0); self.bar.setFixedHeight(9); self.bar.setTextVisible(False)
        lay.addWidget(self.bar)

        lay.addSpacing(6)
        sc = QLabel("执行步骤"); sc.setFont(font_mono(10, True))
        sc.setStyleSheet("color:#94A3B8;background:transparent;border:0;letter-spacing:1px;")
        lay.addWidget(sc)
        self.steps_box = QVBoxLayout(); self.steps_box.setSpacing(3)
        self.steps_box.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self.steps_box)

        lc = QLabel("执行日志"); lc.setFont(font_mono(10, True))
        lc.setStyleSheet("color:#94A3B8;background:transparent;border:0;letter-spacing:1px;")
        lay.addWidget(lc)
        self.log_edit = QPlainTextEdit(); self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(120)
        lay.addWidget(self.log_edit, 1)

        btns = QHBoxLayout(); btns.setSpacing(8)
        self.btn_pause = QPushButton("暂停")
        self.btn_retry = QPushButton("重试")
        self.btn_done = QPushButton("标记完成")
        for b in (self.btn_pause, self.btn_retry, self.btn_done):
            b.setFixedHeight(32)
            b.setStyleSheet("QPushButton{font-size:11px;padding:0 8px;}")
        btns.addWidget(self.btn_pause); btns.addWidget(self.btn_retry); btns.addWidget(self.btn_done)
        lay.addLayout(btns)
        self.btn_pause.clicked.connect(lambda: self.on_action("pause"))
        self.btn_retry.clicked.connect(lambda: self.on_action("retry"))
        self.btn_done.clicked.connect(lambda: self.on_action("done"))

        self.current = None

    def clear_steps(self):
        while self.steps_box.count():
            item = self.steps_box.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def show_task(self, t):
        self.current = t
        if t is None:
            return
        self.id_label.setText(t.id)
        self.title.setText(t.name)
        label, color = STATUS[t.status]
        self.badge.setText("●  " + label)
        rgb = QColor(color)
        self.badge.setStyleSheet(
            "background:rgba(%d,%d,%d,34);color:%s;border:1px solid rgba(%d,%d,%d,90);"
            "border-radius:6px;padding:3px 10px;font-weight:600;" %
            (rgb.red(), rgb.green(), rgb.blue(), color, rgb.red(), rgb.green(), rgb.blue()))
        self.fields["agent"].setText(t.agent)
        self.fields["model"].setText(t.model)
        self.fields["started"].setText(t.started)
        self.fields["elapsed"].setText(fmt_elapsed(t.elapsed))
        self.fields["tokens"].setText("{:,}".format(t.tokens))
        self.fields["priority"].setText(t.priority)
        self.pct.setText("%d%%" % t.progress)
        self.pct.setStyleSheet("color:%s;background:transparent;border:0;" % color)
        self.bar.setValue(t.progress)
        self.bar.setStyleSheet("QProgressBar{background:#243349;border:0;border-radius:5px;}QProgressBar::chunk{background:%s;border-radius:5px;}" % color)

        self.clear_steps()
        marks = {"done": ("✓", "#4ADE80"), "active": ("▶", "#22C55E"), "blocked": ("!", "#F59E0B"), "todo": ("○", "#64748B")}
        for name, st in t.steps:
            mark, mc = marks[st]
            row = QHBoxLayout(); row.setSpacing(8); row.setContentsMargins(0, 0, 0, 0)
            m = QLabel(mark); m.setFont(font_mono(11, True)); m.setFixedWidth(16)
            m.setStyleSheet("color:%s;background:transparent;border:0;" % mc)
            n = QLabel(name); n.setFont(font_body(11))
            n.setStyleSheet("color:%s;background:transparent;border:0;" % ("#64748B" if st == "done" else "#CBD5E1"))
            row.addWidget(m); row.addWidget(n); row.addStretch()
            w = QWidget(); w.setLayout(row); w.setFixedHeight(24)
            w.setStyleSheet("background:transparent;")
            self.steps_box.addWidget(w)

        self.render_logs()

    def render_logs(self):
        self.log_edit.clear()
        if not self.current:
            return
        colors = {"info": "#94A3B8", "run": "#22C55E", "ok": "#4ADE80", "warn": "#F59E0B", "error": "#EF4444"}
        cur = self.log_edit.textCursor()
        for tm, level, text in self.current.logs[-40:]:
            cur.movePosition(QTextCursor.End)
            fmt = QTextCharFormat()
            fmt.setFont(font_mono(10))
            fmt.setForeground(QColor(colors.get(level, "#94A3B8")))
            cur.setCharFormat(fmt)
            cur.insertText("[%s] %s\n" % (tm, text))
        self.log_edit.setTextCursor(cur)
        self.log_edit.ensureCursorVisible()

    def refresh(self, t):
        if self.current and t and self.current.id == t.id:
            self.show_task(t)


class NewTaskDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建 Agent 任务")
        self.setFixedWidth(420)
        self.setStyleSheet("QDialog{background:#0F172A;}")
        lay = QVBoxLayout(self); lay.setContentsMargins(22, 22, 22, 22); lay.setSpacing(12)
        cap = QLabel("新建 Agent 任务"); cap.setFont(font_mono(15, True))
        cap.setStyleSheet("color:#F8FAFC;background:transparent;border:0;")
        lay.addWidget(cap)
        sub = QLabel("创建后立即进入队列并开始推进进度")
        sub.setFont(font_body(11)); sub.setStyleSheet("color:#64748B;background:transparent;border:0;")
        lay.addWidget(sub)
        lay.addSpacing(6)
        self.name = QLineEdit(); self.name.setPlaceholderText("任务名称，例如：生成周报摘要")
        lay.addWidget(QLabel("任务名称")); lay.addWidget(self.name)
        self.agent = QComboBox(); self.agent.addItems([a[0] for a in AGENTS])
        lay.addWidget(QLabel("执行 Agent")); lay.addWidget(self.agent)
        self.pri = QComboBox(); self.pri.addItems(PRIORITIES); self.pri.setCurrentIndex(1)
        lay.addWidget(QLabel("优先级")); lay.addWidget(self.pri)
        lay.addSpacing(8)
        row = QHBoxLayout()
        cancel = QPushButton("取消"); ok = QPushButton("创建任务"); ok.setObjectName("primary")
        cancel.clicked.connect(self.reject); ok.clicked.connect(self.accept)
        row.addStretch(); row.addWidget(cancel); row.addWidget(ok)
        lay.addLayout(row)

    def values(self):
        return self.name.text().strip(), self.agent.currentText(), self.pri.currentText()


# ---------------------------------------------------------------- 页面
class OverviewPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background:#0F172A;")
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(14)
        self.grid = QGridLayout(); self.grid.setSpacing(12)
        lay.addLayout(self.grid)
        self.dist = QLabel("")
        self.dist.setFont(font_body(12))
        self.dist.setStyleSheet("color:#94A3B8;background:transparent;border:0;")
        lay.addWidget(self.dist)

        self.recent_card = QFrame()
        self.recent_card.setAttribute(Qt.WA_StyledBackground, True)
        self.recent_card.setStyleSheet(CARD_QSS)
        rv = QVBoxLayout(self.recent_card); rv.setContentsMargins(18, 14, 18, 14); rv.setSpacing(6)
        rc = QLabel("运行摘要")
        rc.setFont(font_mono(11, True)); rc.setStyleSheet("color:#E2E8F0;background:transparent;border:0;")
        rv.addWidget(rc); rv.addSpacing(4)
        body = QHBoxLayout(); body.setSpacing(24); body.setContentsMargins(0, 0, 0, 0)
        left = QVBoxLayout(); left.setSpacing(4); left.setContentsMargins(0, 0, 0, 0)
        lc = QLabel("最近任务动态"); lc.setFont(font_body(10, True))
        lc.setStyleSheet("color:#64748B;background:transparent;border:0;")
        left.addWidget(lc); left.addSpacing(4)
        self.recent_box = QVBoxLayout(); self.recent_box.setSpacing(4)
        left.addLayout(self.recent_box); left.addStretch()
        right = QVBoxLayout(); right.setSpacing(8); right.setContentsMargins(0, 0, 0, 0)
        mc = QLabel("系统指标"); mc.setFont(font_body(10, True))
        mc.setStyleSheet("color:#64748B;background:transparent;border:0;")
        right.addWidget(mc); right.addSpacing(4)
        self.metrics_box = QGridLayout(); self.metrics_box.setSpacing(10)
        right.addLayout(self.metrics_box); right.addStretch()
        body.addLayout(left, 3); body.addLayout(right, 2)
        rv.addLayout(body, 1)
        lay.addWidget(self.recent_card)
        lay.addStretch()

    def refresh(self, tasks):
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        for i, (name, role, model) in enumerate(AGENTS):
            own = [t for t in tasks if t.agent == name]
            running = [t for t in own if t.status == "running"]
            avg = round(sum(t.progress for t in own) / len(own)) if own else 0
            card = QFrame(); card.setAttribute(Qt.WA_StyledBackground, True)
            card.setStyleSheet(CARD_QSS)
            card.setFixedHeight(165)
            v = QVBoxLayout(card); v.setContentsMargins(16, 14, 16, 14); v.setSpacing(5)
            h = QHBoxLayout()
            n = QLabel(name); n.setFont(font_mono(13, True)); n.setStyleSheet("color:#F8FAFC;background:transparent;border:0;")
            dot = QLabel("● 在线" if running else "○ 空闲")
            dot.setFont(font_body(10))
            dot.setStyleSheet("color:%s;background:transparent;border:0;" % (C["green"] if running else C["dim"]))
            h.addWidget(n); h.addStretch(); h.addWidget(dot)
            v.addLayout(h)
            r = QLabel(role + "  ·  " + model); r.setFont(font_body(10))
            r.setStyleSheet("color:#64748B;background:transparent;border:0;")
            v.addWidget(r)
            v.addSpacing(4)
            p = QProgressBar(); p.setValue(avg); p.setTextVisible(False); p.setFixedHeight(7)
            v.addWidget(p)
            f = QLabel("%d 个任务   ·   平均进度 %d%%   ·   %d 运行中" % (len(own), avg, len(running)))
            f.setFont(font_mono(10)); f.setStyleSheet("color:#94A3B8;background:transparent;border:0;")
            v.addWidget(f)
            self.grid.addWidget(card, i // 3, i % 3)
        counts = {}
        for t in tasks:
            counts[t.status] = counts.get(t.status, 0) + 1
        parts = ["%s %d" % (STATUS[k][0], counts.get(k, 0)) for k in ("running", "queued", "review", "paused", "done", "failed")]
        self.dist.setText("状态分布   " + "   ·   ".join(parts))

        while self.recent_box.count():
            it = self.recent_box.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        for t in sorted(tasks, key=lambda x: x.id, reverse=True)[:6]:
            label, color = STATUS[t.status]
            row = QHBoxLayout(); row.setSpacing(12); row.setContentsMargins(0, 0, 0, 0)
            tm = QLabel(t.updated); tm.setFont(font_mono(10)); tm.setFixedWidth(74)
            tm.setStyleSheet("color:#64748B;background:transparent;border:0;")
            nm = QLabel(t.name); nm.setFont(font_body(11))
            nm.setStyleSheet("color:#CBD5E1;background:transparent;border:0;")
            st = QLabel("● " + label); st.setFont(font_body(10))
            st.setStyleSheet("color:%s;background:transparent;border:0;" % color)
            row.addWidget(tm); row.addWidget(nm, 1); row.addWidget(st)
            w = QWidget(); w.setLayout(row); w.setFixedHeight(24)
            w.setStyleSheet("background:transparent;")
            self.recent_box.addWidget(w)

        while self.metrics_box.count():
            it = self.metrics_box.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        total_tokens = sum(t.tokens for t in tasks)
        avg_elapsed = round(sum(t.elapsed for t in tasks) / len(tasks)) if tasks else 0
        done_n = sum(1 for t in tasks if t.status == "done")
        active_agents = len(set(t.agent for t in tasks if t.status == "running"))
        metrics = [
            ("累计 Tokens", "{:,}".format(total_tokens), C["green"]),
            ("平均耗时", fmt_elapsed(avg_elapsed), C["blue"]),
            ("完成率", "%d%%" % (round(done_n / len(tasks) * 100) if tasks else 0), C["violet"]),
            ("活跃 Agent", "%d / %d" % (active_agents, len(AGENTS)), C["amber"]),
        ]
        for i, (label, value, accent) in enumerate(metrics):
            cell = QFrame(); cell.setAttribute(Qt.WA_StyledBackground, True)
            cell.setStyleSheet("QFrame{background:#0E1A2E;border:1px solid #2C3C55;border-radius:9px;}")
            cell.setFixedHeight(62)
            cv = QVBoxLayout(cell); cv.setContentsMargins(12, 8, 12, 8); cv.setSpacing(2)
            lb = QLabel(label); lb.setFont(font_body(10))
            lb.setStyleSheet("color:#64748B;background:transparent;border:0;")
            vb = QLabel(value); vb.setFont(font_mono(15, True))
            vb.setStyleSheet("color:%s;background:transparent;border:0;" % accent)
            cv.addWidget(lb); cv.addWidget(vb)
            self.metrics_box.addWidget(cell, i // 2, i % 2)


class LogsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background:#0F172A;")
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        cap = QLabel("全局执行日志 · 所有 Agent 实时输出")
        cap.setFont(font_mono(10, True)); cap.setStyleSheet("color:#94A3B8;background:transparent;border:0;")
        lay.addWidget(cap)
        self.logs = QPlainTextEdit(); self.logs.setReadOnly(True)
        lay.addWidget(self.logs, 1)
        self.lines = []

    def append(self, tm, level, agent, text):
        self.lines.append((tm, level, agent, text))
        colors = {"info": "#94A3B8", "run": "#22C55E", "ok": "#4ADE80", "warn": "#F59E0B", "error": "#EF4444"}
        cur = self.logs.textCursor(); cur.movePosition(QTextCursor.End)
        fmt = QTextCharFormat(); fmt.setFont(font_mono(11))
        fmt.setForeground(QColor(colors.get(level, "#94A3B8")))
        cur.setCharFormat(fmt)
        cur.insertText("[%s] %-14s %s\n" % (tm, agent, text))
        self.logs.setTextCursor(cur); self.logs.ensureCursorVisible()

    def seed(self, tasks):
        for t in tasks:
            for tm, level, text in t.logs[-3:]:
                self.append(tm, level, t.agent, text)


class AlertCard(QFrame):
    """可点击预警卡片：QFrame + 鼠标事件，避免 QPushButton 内嵌布局压扁文字。"""
    clicked = Signal(str)

    def __init__(self, tid, accent, parent=None):
        super().__init__(parent)
        self.tid = tid
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(78)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QFrame{background:#16223A;border:1px solid #22304A;border-left:3px solid %s;border-radius:10px;}" % accent)
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 11, 16, 11); lay.setSpacing(7)
        top = QHBoxLayout(); top.setSpacing(10); top.setContentsMargins(0, 0, 0, 0)
        self.name = QLabel(""); self.name.setFont(font_body(12, True))
        self.name.setStyleSheet("color:#F8FAFC;background:transparent;border:0;")
        self.badge = QLabel(""); self.badge.setFont(font_body(10, True))
        top.addWidget(self.name, 1); top.addWidget(self.badge)
        lay.addLayout(top)
        self.info = QLabel(""); self.info.setFont(font_mono(10))
        self.info.setStyleSheet("color:#94A3B8;background:transparent;border:0;")
        lay.addWidget(self.info)
        for w in (self.name, self.badge, self.info):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_name(self, v):
        self.name.setText(v)

    def set_badge(self, text, color):
        self.badge.setText("● " + text)
        self.badge.setStyleSheet("color:%s;background:transparent;border:0;" % color)

    def set_info(self, v):
        self.info.setText(v)

    def mousePressEvent(self, e):
        self.clicked.emit(self.tid)
        super().mousePressEvent(e)


class AlertsPage(QWidget):
    def __init__(self, on_jump, parent=None):
        super().__init__(parent)
        self.on_jump = on_jump
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background:#0F172A;")
        self.lay = QVBoxLayout(self); self.lay.setContentsMargins(0, 0, 0, 0); self.lay.setSpacing(10)
        cap = QLabel("需要关注 · 失败 / 待人工确认 / 已暂停")
        cap.setFont(font_mono(10, True)); cap.setStyleSheet("color:#94A3B8;background:transparent;border:0;")
        self.lay.addWidget(cap)
        self.box = QVBoxLayout(); self.box.setSpacing(10)
        wrap = QWidget(); wrap.setLayout(self.box); wrap.setStyleSheet("background:transparent;")
        self.lay.addWidget(wrap, 1)
        self.lay.addStretch()

    def refresh(self, tasks):
        while self.box.count():
            it = self.box.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        need = [t for t in tasks if t.status in ("failed", "review", "paused")]
        if not need:
            empty = QLabel("当前没有需要关注的异常任务")
            empty.setFont(font_body(12)); empty.setStyleSheet("color:#64748B;background:transparent;border:0;padding:30px;")
            self.box.addWidget(empty)
            return
        for t in need:
            label, color = STATUS[t.status]
            card = AlertCard(t.id, color)
            card.set_name(t.name)
            card.set_badge(label, color)
            card.set_info("%s  ·  %s  ·  %s  ·  进度 %d%%  ·  点击查看" % (t.id, t.agent, t.model, t.progress))
            card.clicked.connect(self.on_jump)
            self.box.addWidget(card)
        self.box.addStretch()


# ---------------------------------------------------------------- 主窗口
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1600, 950)
        self.setMinimumSize(1180, 720)
        self.tasks = seed_tasks()
        self.live = True
        self.global_logs = []
        self.active_page = 0
        self._detail_pending = False
        self._pending_task = None

        # 局域网只读配对服务：后台线程，主线程只 publish 不可变 JSON 字符串
        self.pair = PairServer()
        self.pair.start()
        self.pair.publish(self.tasks)

        self._build_menu()
        central = QWidget()
        central.setStyleSheet("background:#0F172A;")
        root = QHBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        self.sidebar = Sidebar()
        root.addWidget(self.sidebar)

        right = QWidget(); right.setStyleSheet("background:#0F172A;")
        rv = QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(0)
        rv.addWidget(self._build_topbar())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_table_page())
        self.overview = OverviewPage(); self.stack.addWidget(self.overview)
        self.logs_page = LogsPage(); self.stack.addWidget(self.logs_page)
        self.alerts = AlertsPage(self.jump_to_task); self.stack.addWidget(self.alerts)
        rv.addWidget(self.stack, 1)
        root.addWidget(right, 1)
        self.setCentralWidget(central)

        self.status = QStatusBar(); self.setStatusBar(self.status)
        self._build_shortcuts()
        for b in self.sidebar.nav_buttons:
            b.clicked.connect(self.on_nav)

        # 表格模型
        self.model = TaskModel(self.tasks)
        self.proxy = TaskProxy()
        self.proxy.setSourceModel(self.model)
        self.table.setModel(self.proxy)
        self.delegate = CellDelegate(self.table)
        for c in range(len(HEADERS)):
            self.table.setItemDelegateForColumn(c, self.delegate)
        for c, w in enumerate(COL_WIDTH):
            self.table.setColumnWidth(c, w)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.sortByColumn(2, Qt.AscendingOrder)
        self.table.selectionModel().selectionChanged.connect(self.on_selection)

        self.logs_page.seed(self.tasks)
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(2000)
        self.refresh_all()
        self.select_first()

    # ---------- 构建 ----------
    def _build_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("文件(&F)")
        a = QAction("导出当前视图 CSV", self); a.setShortcut("Ctrl+E"); a.triggered.connect(self.export_csv); fm.addAction(a)
        fm.addSeparator()
        q = QAction("退出", self); q.setShortcut("Ctrl+Q"); q.triggered.connect(self.close); fm.addAction(q)
        pm = mb.addMenu("连接手机(&M)")
        pair_action = QAction("扫码连接手机…", self)
        pair_action.setShortcut("Ctrl+M")
        pair_action.triggered.connect(self.show_pair)
        pm.addAction(pair_action)
        vm = mb.addMenu("视图(&V)")
        r = QAction("立即刷新", self); r.setShortcut("F5"); r.triggered.connect(self.manual_sync); vm.addAction(r)
        self.act_live = QAction("暂停实时推进", self); self.act_live.setShortcut("Ctrl+P"); self.act_live.triggered.connect(self.toggle_live); vm.addAction(self.act_live)
        hm = mb.addMenu("帮助(&H)")
        ab = QAction("关于", self); ab.triggered.connect(self.about); hm.addAction(ab)

    def _build_topbar(self):
        bar = QFrame(); bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setStyleSheet("QFrame{background:#0F172A;border-bottom:1px solid #1E293B;}")
        bar.setFixedHeight(62)
        h = QHBoxLayout(bar); h.setContentsMargins(20, 0, 20, 0); h.setSpacing(10)
        crumb = QLabel("工作区  /  Agent 任务进度表")
        crumb.setFont(font_mono(11)); crumb.setStyleSheet("color:#64748B;background:transparent;border:0;")
        h.addWidget(crumb)
        h.addStretch()

        self.search = QLineEdit(); self.search.setPlaceholderText("搜索任务 / ID / Agent  (Ctrl+F)")
        self.search.setFixedWidth(260); self.search.textChanged.connect(self.apply_filters)
        h.addWidget(self.search)

        self.f_status = QComboBox(); self.f_status.setFixedWidth(130)
        self.f_status.addItem("全部状态", "all")
        for k, (label, _) in STATUS.items():
            self.f_status.addItem(label, k)
        self.f_status.currentIndexChanged.connect(self.apply_filters)
        h.addWidget(self.f_status)

        self.f_agent = QComboBox(); self.f_agent.setFixedWidth(150)
        self.f_agent.addItem("全部 Agent", "all")
        for name, _, _ in AGENTS:
            self.f_agent.addItem(name, name)
        self.f_agent.currentIndexChanged.connect(self.apply_filters)
        h.addWidget(self.f_agent)

        self.chk_live = QCheckBox(); self.chk_live.setChecked(True)
        self.chk_live.setToolTip("实时推进（每 2 秒）")
        self.chk_live.stateChanged.connect(lambda s: self.set_live(self.chk_live.isChecked()))
        self.live_dot = QLabel("● LIVE"); self.live_dot.setFont(font_mono(10, True))
        self.live_dot.setStyleSheet("color:#22C55E;background:transparent;border:0;")
        h.addWidget(self.chk_live); h.addWidget(self.live_dot)

        btn_sync = QPushButton("刷新"); btn_sync.setFixedWidth(70); btn_sync.clicked.connect(self.manual_sync)
        btn_add = QPushButton("+ 新建任务"); btn_add.setObjectName("primary"); btn_add.clicked.connect(self.new_task)
        btn_csv = QPushButton("导出 CSV"); btn_csv.setFixedWidth(96); btn_csv.clicked.connect(self.export_csv)
        h.addWidget(btn_sync); h.addWidget(btn_csv); h.addWidget(btn_add)
        return bar

    def _build_table_page(self):
        page = QWidget(); page.setAttribute(Qt.WA_StyledBackground, True)
        page.setStyleSheet("background:#0F172A;")
        lay = QVBoxLayout(page); lay.setContentsMargins(20, 18, 20, 16); lay.setSpacing(14)

        head = QHBoxLayout()
        hv = QVBoxLayout(); hv.setSpacing(3)
        h1 = QLabel("Agent 任务进度表"); h1.setFont(font_mono(21, True))
        h1.setStyleSheet("color:#F8FAFC;background:transparent;border:0;")
        sub = QLabel("集中查看所有 Agent 的执行状态、步骤推进与实时日志")
        sub.setFont(font_body(11)); sub.setStyleSheet("color:#94A3B8;background:transparent;border:0;")
        hv.addWidget(h1); hv.addWidget(sub)
        head.addLayout(hv); head.addStretch()
        self.head_meta = QLabel(""); self.head_meta.setFont(font_mono(10))
        self.head_meta.setStyleSheet("color:#64748B;background:transparent;border:0;")
        head.addWidget(self.head_meta)
        lay.addLayout(head)

        self.kpis = QHBoxLayout(); self.kpis.setSpacing(12)
        self.k_total = KpiCard("任务总数", "0", "", C["blue"])
        self.k_run = KpiCard("运行中", "0", "", C["green"])
        self.k_rate = KpiCard("整体完成率", "0%", "", C["violet"])
        self.k_alert = KpiCard("需要关注", "0", "", C["amber"])
        for k in (self.k_total, self.k_run, self.k_rate, self.k_alert):
            self.kpis.addWidget(k, 1)
        lay.addLayout(self.kpis)

        split = QSplitter(Qt.Horizontal)
        left = QFrame(); left.setAttribute(Qt.WA_StyledBackground, True)
        left.setStyleSheet("QFrame{background:#111C30;border:1px solid #22304A;border-radius:12px;}")
        lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(0)
        th = QHBoxLayout(); th.setContentsMargins(16, 12, 16, 12)
        tc = QLabel("任务列表"); tc.setFont(font_mono(11, True))
        tc.setStyleSheet("color:#E2E8F0;background:transparent;border:0;")
        self.count_label = QLabel(""); self.count_label.setFont(font_mono(10))
        self.count_label.setStyleSheet("color:#64748B;background:transparent;border:0;")
        th.addWidget(tc); th.addStretch(); th.addWidget(self.count_label)
        lv.addLayout(th)
        self.table = QTableView()
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        self.table.setMouseTracking(True)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setMinimumSectionSize(70)
        self.table.setStyleSheet("QTableView{border:0;border-top:1px solid #22304A;border-radius:0 0 12px 12px;}")
        lv.addWidget(self.table, 1)
        split.addWidget(left)

        self.detail = DetailPanel(self.on_detail_action)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([1000, 320])
        lay.addWidget(split, 1)
        return page

    # ---------- 交互 ----------
    def _build_shortcuts(self):
        s1 = QShortcut(QKeySequence("Ctrl+F"), self); s1.activated.connect(self.focus_search)
        s2 = QShortcut(QKeySequence("Esc"), self); s2.activated.connect(self.clear_selection)

    def focus_search(self):
        self.search.setFocus(); self.search.selectAll()

    def clear_selection(self):
        self.table.clearSelection()
        self.detail.show_task(None)
        self.detail.title.setText("选择一条任务查看详情")

    def on_nav(self):
        btn = self.sender()
        idx = btn.property("page")
        for b in self.sidebar.nav_buttons:
            b.setChecked(b is btn)
        self.stack.setCurrentIndex(idx)
        self.active_page = idx
        if idx == 1:
            self.overview.refresh(self.tasks)
        elif idx == 3:
            self.alerts.refresh(self.tasks)

    def apply_filters(self):
        self.proxy.search = self.search.text()
        self.proxy.status_filter = self.f_status.currentData() or "all"
        self.proxy.agent_filter = self.f_agent.currentData() or "all"
        self.proxy.invalidateFilter()
        self.update_counts()

    def on_selection(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        src = self.proxy.mapToSource(rows[0])
        self.detail.show_task(self.tasks[src.row()])

    def select_first(self):
        if self.proxy.rowCount() > 0:
            self.table.selectRow(0)

    def jump_to_task(self, tid):
        self.search.setText("")
        self.f_status.setCurrentIndex(0)
        self.f_agent.setCurrentIndex(0)
        self.proxy.invalidateFilter()
        for r in range(self.proxy.rowCount()):
            src = self.proxy.mapToSource(self.proxy.index(r, 0))
            if self.tasks[src.row()].id == tid:
                for b in self.sidebar.nav_buttons:
                    b.setChecked(b.property("page") == 0)
                self.stack.setCurrentIndex(0)
                self.active_page = 0
                self.table.selectRow(r)
                self.table.scrollTo(self.proxy.index(r, 0))
                return

    def on_detail_action(self, act):
        t = self.detail.current
        if not t:
            return
        if act == "pause":
            if t.status == "running":
                t.status = "paused"; t.add_log("warn", "用户暂停了任务")
            elif t.status == "paused":
                t.status = "running"; t.add_log("run", "用户恢复了任务")
            else:
                QMessageBox.information(self, "提示", "仅运行中的任务可暂停 / 恢复")
                return
        elif act == "retry":
            t.status = "running"; t.progress = min(t.progress, 20)
            t.add_log("run", "用户触发重试，从断点继续执行")
        elif act == "done":
            t.status = "done"; t.progress = 100
            t.steps = [(s, "done") for s, _ in t.steps]
            t.add_log("ok", "用户标记为已完成")
        self.refresh_all()

    def new_task(self):
        dlg = NewTaskDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        name, agent, pri = dlg.values()
        if not name:
            QMessageBox.warning(self, "提示", "请填写任务名称")
            return
        model = next((m for n, _, m in AGENTS if n == agent), "GPT-4o")
        tid = "AGT-%d" % (1043 + len([t for t in self.tasks if t.id.startswith("AGT-")]))
        t = Task(
            id=tid, name=name, agent=agent, model=model, status="queued", progress=0,
            steps=[(s, "todo") for s in ["初始化", "加载上下文", "执行主逻辑", "结果校验", "归档"]],
            elapsed=0, tokens=0, started=now_str(), updated=now_str(), priority=pri,
        )
        t.add_log("info", "任务创建，分配至 %s / %s" % (agent, model))
        self.model.beginInsertRows(QModelIndex(), 0, 0)
        self.tasks.insert(0, t)
        self.model.endInsertRows()
        self.logs_page.append(now_str(), "info", agent, "新任务 %s 已创建" % tid)
        self.refresh_all()
        self.jump_to_task(tid)
        QMessageBox.information(self, "已创建", "任务 %s 已加入队列，将自动开始推进" % tid)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", "pulse_agent_tasks.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["任务ID", "任务名称", "Agent", "模型", "状态", "进度(%)", "步骤", "耗时(s)", "Tokens", "优先级", "更新时间"])
                for r in range(self.proxy.rowCount()):
                    src = self.proxy.mapToSource(self.proxy.index(r, 0))
                    t = self.tasks[src.row()]
                    w.writerow([t.id, t.name, t.agent, t.model, STATUS[t.status][0], t.progress,
                                "%d/%d" % (t.steps_done, len(t.steps)), t.elapsed, t.tokens, t.priority, t.updated])
            QMessageBox.information(self, "导出完成", "已导出 %d 条任务到：\n%s" % (self.proxy.rowCount(), path))
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def set_live(self, on):
        self.live = on
        self.chk_live.setChecked(on)
        self.live_dot.setText("● LIVE" if on else "○ PAUSED")
        self.live_dot.setStyleSheet("color:%s;background:transparent;border:0;" % (C["green"] if on else C["dim"]))
        self.act_live.setText("暂停实时推进" if on else "恢复实时推进")

    def toggle_live(self):
        self.set_live(not self.live)

    def manual_sync(self):
        self.tick(force=True)
        self.status.showMessage("已手动同步 · %s" % now_str(), 2500)

    def about(self):
        QMessageBox.about(self, "关于", "%s\nv%s\n\nQt Widgets 原生桌面应用\n设计系统：UI/UX Pro Max (Data-Dense Dashboard)\n数据：本地离线演示\n局域网只读配对：文件 › 连接手机 › 扫码连接手机" % (APP_NAME, APP_VER))

    # ---------- 局域网配对 ----------
    def show_pair(self):
        """打开二维码面板，让手机扫码连接到本机服务。"""
        if self.pair.error:
            # 服务未起来时尝试重启一次，避免端口被临时占用导致的永久失败
            self.pair.start()
            self.pair.publish(self.tasks)
        open_pair_dialog(self, self.pair)

    def closeEvent(self, event):
        try:
            self.pair.stop()
        except Exception:
            pass
        super().closeEvent(event)

    # ---------- 实时推进 ----------
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
                # 步骤推进
                done_n = round(len(t.steps) * t.progress / 100)
                t.steps = [(s, "done" if j < done_n else ("active" if j == done_n else "todo")) for j, (s, _) in enumerate(t.steps)]
                if t.progress >= 100:
                    t.status = "done"
                    t.add_log("ok", "全部步骤完成，结果已归档")
                    self.logs_page.append(now_str(), "ok", t.agent, "%s 完成" % t.id)
                elif random.random() < 0.28:
                    t.add_log("run", "步骤推进至 %d%%，已处理 %s tokens" % (t.progress, "{:,}".format(t.tokens)))
                    self.logs_page.append(now_str(), "run", t.agent, "%s 进度 %d%%" % (t.id, t.progress))
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
            self.model.refresh()
            self.refresh_all()

    def _flush_detail(self):
        self._detail_pending = False
        t = self._pending_task
        if t and self.detail.current and self.detail.current.id == t.id:
            self.detail.refresh(t)

    def refresh_all(self):
        tasks = self.tasks
        total = len(tasks)
        running = sum(1 for t in tasks if t.status == "running")
        done = sum(1 for t in tasks if t.status == "done")
        need = sum(1 for t in tasks if t.status in ("failed", "review", "paused"))
        rate = round(sum(t.progress for t in tasks) / total) if total else 0
        self.k_total.set_value(str(total), "%d 个 Agent 在线" % len(AGENTS))
        self.k_run.set_value(str(running), "占全部任务 %d%%" % (round(running / total * 100) if total else 0))
        self.k_rate.set_value("%d%%" % rate, "%d/%d 已完成" % (done, total))
        self.k_alert.set_value(str(need), "失败 / 待确认 / 暂停")
        self.head_meta.setText("最后同步 %s   ·   数据源 本地演示" % now_str())
        self.status.showMessage("共 %d 个任务  ·  %d 运行中  ·  %d 已完成  ·  最后同步 %s  ·  %s" %
                               (total, running, done, now_str(), "LIVE" if self.live else "PAUSED"))
        self.sidebar.update_counts(tasks)
        self.update_counts()
        if self.detail.current:
            cur = next((t for t in tasks if t.id == self.detail.current.id), None)
            if cur is not None and not self._detail_pending:
                self._detail_pending = True
                self._pending_task = cur
                QTimer.singleShot(0, self._flush_detail)
        if self.active_page == 1:
            self.overview.refresh(tasks)
        if self.active_page == 3:
            self.alerts.refresh(tasks)
        # 每次界面刷新同步一次只读快照（主线程序列化，不与 HTTP 线程共享对象）
        self.pair.publish(tasks)

    def update_counts(self):
        self.count_label.setText("%d / %d 条" % (self.proxy.rowCount(), len(self.tasks)))


# ---------------------------------------------------------------- 入口
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(C["bg"]))
    pal.setColor(QPalette.WindowText, QColor(C["text"]))
    pal.setColor(QPalette.Base, QColor(C["surface"]))
    pal.setColor(QPalette.AlternateBase, QColor(C["surface2"]))
    pal.setColor(QPalette.Text, QColor(C["text"]))
    pal.setColor(QPalette.Button, QColor(C["surface2"]))
    pal.setColor(QPalette.ButtonText, QColor(C["text"]))
    pal.setColor(QPalette.Highlight, QColor(C["green"]))
    pal.setColor(QPalette.HighlightedText, QColor(C["bg"]))
    app.setPalette(pal)
    loaded = load_fonts()
    app.setFont(font_body(12))
    app.setStyleSheet(QSS)

    win = MainWindow()
    win.show()

    argv = sys.argv
    # 自动化验证用：导出配对信息与二维码，不改变界面
    if "--pair-info" in argv:
        i = argv.index("--pair-info")
        info_path = argv[i + 1] if i + 1 < len(argv) else "/tmp/pulse_pair_info.json"
        import json as _json
        info = {
            "version": APP_VER, "host": win.pair.host, "port": win.pair.port,
            "token": win.pair.state.token, "url": win.pair.url(),
            "health_url": win.pair.health_url(), "error": win.pair.error,
        }
        try:
            with open(info_path, "w", encoding="utf-8") as f:
                _json.dump(info, f, ensure_ascii=False, indent=2)
            print("PAIR_INFO %s" % info_path)
        except Exception as e:
            print("PAIR_INFO_FAILED %s" % e)
    if "--pair-qr" in argv:
        i = argv.index("--pair-qr")
        qr_path = argv[i + 1] if i + 1 < len(argv) else "/tmp/pulse_pair_qr.png"
        try:
            save_qr_png(win.pair.url(), qr_path)
            print("PAIR_QR %s" % qr_path)
        except Exception as e:
            print("PAIR_QR_FAILED %s" % e)
    if "--pair-shot" in argv:
        i = argv.index("--pair-shot")
        shot_path = argv[i + 1] if i + 1 < len(argv) else "/tmp/pulse_pair_shot.png"
        from pulse_pair_server import PairDialog

        def capture_pair():
            app.processEvents()
            dlg = PairDialog(win.pair, win)
            dlg.show()
            app.processEvents()
            ok = dlg.grab().save(shot_path)
            print("PAIR_SHOT %s %s" % (shot_path, "OK" if ok else "FAILED"))
            dlg.close()  # 不退出进程，服务继续由 --serve-seconds 控制

        QTimer.singleShot(1200, capture_pair)
    if "--serve-seconds" in argv:
        i = argv.index("--serve-seconds")
        try:
            secs = float(argv[i + 1])
            QTimer.singleShot(int(secs * 1000), app.quit)
        except (ValueError, IndexError):
            pass
    if "--page" in argv:
        i = argv.index("--page")
        try:
            p = int(argv[i + 1])
            if 0 <= p <= 3:
                for b in win.sidebar.nav_buttons:
                    b.setChecked(b.property("page") == p)
                win.stack.setCurrentIndex(p)
                win.active_page = p
                win.refresh_all()
        except (ValueError, IndexError):
            pass
    if "--size" in argv:
        i = argv.index("--size")
        try:
            win.resize(int(argv[i + 1]), int(argv[i + 2]))
        except (ValueError, IndexError):
            pass
    if "--screenshot" in argv:
        i = argv.index("--screenshot")
        path = argv[i + 1] if i + 1 < len(argv) else "/tmp/pulse_pc.png"
        def capture():
            app.processEvents()
            ok = win.grab().save(path)
            print("SCREENSHOT %s %s" % (path, "OK" if ok else "FAILED"))
            app.quit()
        QTimer.singleShot(1600, capture)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
