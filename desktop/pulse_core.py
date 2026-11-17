# -*- coding: utf-8 -*-
"""
PULSE · 共享数据核心（v2.0.0）

把数据模型、状态枚举、字体与设计令牌抽成单一真相源，供
  - pulse_studio.py   全新主界面（品牌化工作台）
  - pulse_glass.py    液态玻璃悬浮窗
  - pulse_pair_server.py 局域网只读配对（跨端契约字段）
共同复用。

设计原则：本模块只依赖 PySide6 的字体/颜色基础类与标准库，
不包含任何 UI 组件、不启动 QApplication，可被任意入口安全 import。
旧版 pulse_agent_console.py 保持不动，作为 v1.3.0 可回退基线。
"""
import glob
import os
import random
from dataclasses import dataclass, field
from datetime import datetime

from PySide6.QtGui import QFont, QFontDatabase, QColor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RES_DIR = os.path.join(BASE_DIR, "resources")

APP_NAME = "PULSE"
APP_SUB = "AGENT STUDIO"
APP_VER = "3.0.0"

# ---------------------------------------------------------------- 设计令牌
# 与移动端 PULSE 同源的深空底 + 荧光绿主色；额外加入青/紫/琥珀用于氛围光晕。
T = {
    "bg": "#070B14",          # 最深背景
    "bg2": "#0B1120",         # 次级背景
    "panel": "#111A2C",       # 玻璃底衬
    "stroke": "#26334C",
    "text": "#F1F5FB",
    "muted": "#9AAAC4",
    "dim": "#64748B",
    "green": "#22C55E",
    "green_hi": "#4ADE80",
    "green_soft": "#86EFAC",
    "cyan": "#38BDF8",
    "violet": "#A78BFA",
    "amber": "#FBBF24",
    "red": "#FB7185",
    "blue": "#60A5FA",
}

# 状态 -> (中文, 主色, 用于玻璃发光的柔和色)
STATUS = {
    "running": ("运行中", T["green"], "#34D399"),
    "queued":  ("排队中", T["dim"],   "#94A3B8"),
    "review":  ("待人工确认", T["amber"], "#FCD34D"),
    "done":    ("已完成", T["green_hi"], "#6EE7B7"),
    "failed":  ("失败", T["red"],   "#FDA4AF"),
    "paused":  ("已暂停", T["blue"], "#93C5FD"),
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

# 中文字体：优先系统 Noto Sans CJK SC（解决旧版中文偏细），回退到打包字体。
CN_FAMILY = "Noto Sans CJK SC"
LATIN_FAMILY = "Fira Sans"
MONO_FAMILY = "Fira Code"


def C(hex_or_key, alpha=255):
    """颜色助手：可传 '#RRGGBB' 或令牌 key，附带 alpha。"""
    s = T.get(hex_or_key, hex_or_key)
    c = QColor(s)
    c.setAlpha(alpha)
    return c


def now_str():
    return datetime.now().strftime("%H:%M:%S")


def fmt_elapsed(sec):
    if sec < 60:
        return "%ds" % sec
    if sec < 3600:
        return "%dm%02ds" % (sec // 60, sec % 60)
    return "%dh%02dm" % (sec // 3600, (sec % 3600) // 60)


def fmt_tokens(n):
    return "{:,}".format(n)


# ---------------------------------------------------------------- 字体
def load_fonts():
    """加载 resources/fonts 下的 Fira 字体，返回成功列表。"""
    loaded = []
    for path in sorted(glob.glob(os.path.join(RES_DIR, "fonts", "*.ttf"))):
        if QFontDatabase.addApplicationFont(path) >= 0:
            loaded.append(os.path.basename(path))
    return loaded


def _family_available(name):
    try:
        return name in QFontDatabase.families()
    except Exception:
        return False


def f_cn(size=13, weight=QFont.Normal):
    """中文界面字体。"""
    fam = CN_FAMILY if _family_available(CN_FAMILY) else LATIN_FAMILY
    f = QFont(fam, size)
    f.setWeight(weight)
    f.setStyleHint(QFont.SansSerif)
    return f


def f_bold(size=13):
    return f_cn(size, QFont.DemiBold)


def f_display(size=30):
    """大号数字/标题（拉丁，字重更实）。"""
    f = QFont(LATIN_FAMILY, size)
    f.setWeight(QFont.Bold)
    f.setStyleHint(QFont.SansSerif)
    return f


def f_mono(size=11, bold=False):
    f = QFont(MONO_FAMILY, size)
    f.setStyleHint(QFont.Monospace)
    f.setBold(bold)
    return f


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
    """12 个演示任务。与 v1.3.0 完全一致，保证配对服务跨端契约稳定。"""
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


def summarise(tasks):
    """统一摘要，主界面 / 悬浮窗 / 配对服务共用口径。"""
    total = len(tasks)
    running = sum(1 for t in tasks if t.status == "running")
    done = sum(1 for t in tasks if t.status == "done")
    need = sum(1 for t in tasks if t.status in ("failed", "review", "paused"))
    rate = round(sum(t.progress for t in tasks) / total) if total else 0
    return {
        "total": total, "running": running, "done": done,
        "need_attention": need, "completion_rate": rate,
    }
