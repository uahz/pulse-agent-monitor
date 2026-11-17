# -*- coding: utf-8 -*-
"""
PULSE · P0 事件引擎端到端验证

A 区（引擎单元，无 UI）：10 类事件 → 状态机映射、容错、三种事件源行为
B 区（StudioWindow 集成，offscreen）：replay/file/http 三种模式接入主程序、
    卡片重建、全局日志、配对服务快照与 POST /api/events 通道、默认模式回归

用法：QT_QPA_PLATFORM=offscreen python3.12 verify_events.py
退出码 0 = 全部通过。
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from pulse_core import seed_tasks, summarise
from pulse_events import (
    EventEngine, FileEventSource, ReplayEventSource, HttpEventSource,
    EV_TASK_STARTED, EV_STEP_COMPLETED, EV_TASK_PROGRESS, EV_TASK_PAUSED,
    EV_TASK_RESUMED, EV_TASK_REVIEW, EV_TASK_FAILED, EV_TASK_COMPLETED,
    EV_LOG, EV_TOKENS,
)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + str(detail)[:110]) if detail else ""))


def find(tasks, tid):
    return next((t for t in tasks if t.id == tid), None)


def fresh_engine(simulate=False):
    tasks = seed_tasks()
    log = []
    eng = EventEngine(tasks, simulate=simulate,
                      on_event=lambda e, t: log.append((e, t.id)),
                      on_task_added=lambda t: log.append(("added", t.id)))
    src = HttpEventSource()
    eng.source = src
    return tasks, eng, src, log


# ================================================================ A 区
print("== A 区：引擎单元 ==")

# A1 模拟模式兼容（回归保障）
tasks, _, _, _ = fresh_engine(simulate=True)
eng = EventEngine(tasks, source=None, simulate=True)
p0 = sum(t.progress for t in tasks)
eng.step(2)
check("A1 模拟模式推进（无事件源时保持原行为）", sum(t.progress for t in tasks) > p0)

# A2 冻结模式
tasks, eng, src, _ = fresh_engine(simulate=False)
eng.source = None
p0 = sum(t.progress for t in tasks)
eng.step(2)
check("A2 冻结模式（simulate=False）数据不变", sum(t.progress for t in tasks) == p0)

# A3 task_started 新建
tasks, eng, src, log = fresh_engine()
src.push({"type": EV_TASK_STARTED, "task_id": "AGT-9001", "name": "真实事件任务",
          "agent": "Coder", "model": "Claude-3.5", "priority": "高",
          "steps": ["拉代码", "写实现", "跑测试"]})
eng.step()
t = find(tasks, "AGT-9001")
ok = (t is not None and t.status == "running" and t.progress == 0
      and [s[1] for s in t.steps] == ["active", "todo", "todo"]
      and t.priority == "高" and ("added", "AGT-9001") in log)
check("A3 task_started 新建任务（首步 active + 回调）", ok,
      "%s %s %s" % (t.status, [s[1] for s in t.steps], t.priority))

# A4 task_started 重启已完成任务
src.push({"type": EV_TASK_COMPLETED, "task_id": "AGT-9001"})
eng.step()
src.push({"type": EV_TASK_STARTED, "task_id": "AGT-9001"})
eng.step()
check("A4 task_started 重启终态任务（清零重跑）",
      t.status == "running" and t.progress == 0 and t.tokens == 0
      and all(st == "todo" for _, st in t.steps))

# A5 step_completed 按索引 + 进度重算
src.push({"type": EV_TASK_STARTED, "task_id": "AGT-9002", "name": "步骤推进测试",
          "steps": ["甲", "乙", "丙", "丁"]})
src.push({"type": EV_STEP_COMPLETED, "task_id": "AGT-9002", "step_index": 0})
src.push({"type": EV_STEP_COMPLETED, "task_id": "AGT-9002", "step_index": 1})
eng.step()
t2 = find(tasks, "AGT-9002")
check("A5 step_completed 推进步骤并重算进度",
      [s[1] for s in t2.steps] == ["done", "done", "active", "todo"]
      and t2.progress == 50, "progress=%d" % t2.progress)

# A6 无索引 step_completed 完成第一个进行中步骤
src.push({"type": EV_STEP_COMPLETED, "task_id": "AGT-9002"})
eng.step()
check("A6 无索引 step_completed 容错（推进 active 步）",
      [s[1] for s in t2.steps] == ["done", "done", "done", "active"])

# A7 越界索引容错
src.push({"type": EV_STEP_COMPLETED, "task_id": "AGT-9002", "step_index": 99})
eng.step()
check("A7 越界 step_index 不崩溃（回退到无索引语义）",
      [s[1] for s in t2.steps] == ["done", "done", "done", "done"]
      and t2.progress == 100)

# A8 task_progress 直接设置 + steps 同步
src.push({"type": EV_TASK_STARTED, "task_id": "AGT-9003", "name": "进度直报", "steps": ["一", "二", "三", "四"]})
src.push({"type": EV_TASK_PROGRESS, "task_id": "AGT-9003", "progress": 50})
eng.step()
t3 = find(tasks, "AGT-9003")
check("A8 task_progress 直报并同步步骤四态",
      t3.progress == 50 and [s[1] for s in t3.steps] == ["done", "done", "active", "todo"])

# A9 progress 越界拒绝
src.push({"type": EV_TASK_PROGRESS, "task_id": "AGT-9003", "progress": 150})
src.push({"type": EV_TASK_PROGRESS, "task_id": "AGT-9003", "progress": -5})
eng.step()
check("A9 越界 progress 被拒绝", t3.progress == 50)

# A10 task_paused
src.push({"type": EV_TASK_PAUSED, "task_id": "AGT-9003", "reason": "等待审批"})
eng.step()
check("A10 task_paused → paused + active→blocked",
      t3.status == "paused" and t3.steps[2][1] == "blocked"
      and any("等待审批" in x[2] for x in t3.logs))

# A10b done 任务拒绝暂停
src.push({"type": EV_TASK_COMPLETED, "task_id": "AGT-9002"})
eng.step()
src.push({"type": EV_TASK_PAUSED, "task_id": "AGT-9002"})
eng.step()
check("A10b 终态任务拒绝暂停", t2.status == "done")

# A11 task_resumed
src.push({"type": EV_TASK_RESUMED, "task_id": "AGT-9003"})
eng.step()
check("A11 task_resumed → running + blocked→active",
      t3.status == "running" and t3.steps[2][1] == "active")

# A11b 非暂停状态拒绝恢复
applied_before = eng.applied
src.push({"type": EV_TASK_RESUMED, "task_id": "AGT-9003"})
eng.step()
check("A11b running 状态重复恢复被拒绝（幂等）", t3.status == "running"
      and eng.applied == applied_before)

# A12 task_review
src.push({"type": EV_TASK_REVIEW, "task_id": "AGT-9003"})
eng.step()
check("A12 task_review → review", t3.status == "review")

# A13 task_failed
src.push({"type": EV_TASK_STARTED, "task_id": "AGT-9004", "name": "失败路径", "steps": ["安装", "执行"]})
src.push({"type": EV_STEP_COMPLETED, "task_id": "AGT-9004", "step_index": 0})
src.push({"type": EV_TASK_FAILED, "task_id": "AGT-9004", "reason": "下游 503"})
eng.step()
t4 = find(tasks, "AGT-9004")
check("A13 task_failed → failed + reason 日志 + active→blocked",
      t4.status == "failed" and t4.steps[1][1] == "blocked"
      and any("下游 503" in x[2] for x in t4.logs))

# A14 task_completed
src.push({"type": EV_TASK_COMPLETED, "task_id": "AGT-9004"})
eng.step()
check("A14 task_completed → done + 100% + 全步骤 done",
      t4.status == "done" and t4.progress == 100
      and all(st == "done" for _, st in t4.steps))

# A15 log 事件（level 归一化 + 截断）
src.push({"type": EV_TASK_STARTED, "task_id": "AGT-9005", "name": "日志测试", "steps": ["步"]})
for i in range(70):
    src.push({"type": EV_LOG, "task_id": "AGT-9005", "level": "verbose" if i == 0 else "info",
              "text": "日志行 %d" % i})
eng.step()
t5 = find(tasks, "AGT-9005")
check("A15 log 事件追加 + level 归一化 + 60 条截断",
      len(t5.logs) == 60 and t5.logs[0][1] == "info"
      and t5.logs[-1][2] == "日志行 69",
      "n=%d head=%s tail=%s" % (len(t5.logs), t5.logs[0][2], t5.logs[-1][2]))

# A16 tokens 累计 + 非法拒绝
src.push({"type": EV_TOKENS, "task_id": "AGT-9005", "delta": 1000})
src.push({"type": EV_TOKENS, "task_id": "AGT-9005", "delta": 0})
src.push({"type": EV_TOKENS, "task_id": "AGT-9005", "delta": -50})
eng.step()
check("A16 tokens 只累计合法正增量", t5.tokens == 1000)

# A17 未知 task_id 容错
src.push({"type": EV_STEP_COMPLETED, "task_id": "AGT-GHOST"})
src.push({"type": EV_STEP_COMPLETED, "task_id": "AGT-GHOST"})
eng.step()
check("A17 未知 task_id 记录且不崩溃", eng.unknown_ids == ["task_id=AGT-GHOST"]
      and find(tasks, "AGT-GHOST") is None)

# A18 FileEventSource tail + 坏行
tmp = "/tmp/pulse_verify_tail.jsonl"
open(tmp, "w", encoding="utf-8").close()
fes = FileEventSource(tmp)
check("A18a 文件尚未写入时 poll 为空", fes.poll() == [])
with open(tmp, "a", encoding="utf-8") as f:
    f.write(json.dumps({"type": EV_LOG, "task_id": "AGT-1042", "text": "tail 事件"}, ensure_ascii=False) + "\n")
    f.write("这不是JSON\n")
    f.write(json.dumps({"type": "bogus"}, ensure_ascii=False) + "\n")
evs = fes.poll()
check("A18b 追加行可读 + 坏行计数",
      len(evs) == 1 and evs[0]["text"] == "tail 事件" and fes.bad_lines == 2,
      "events=%d bad=%d" % (len(evs), fes.bad_lines))
fes.close()

# A19 ReplayEventSource 时间轴与倍速
res = ReplayEventSource("events/demo_events.jsonl", speed=100)
check("A19a 回放源加载 18 个有效事件", res.total == 18, "total=%d" % res.total)
res.start()
first = res.poll()
check("A19b t=0 事件立即到期", any(e["type"] == EV_TASK_STARTED and e["task_id"] == "AGT-2001" for e in first))
time.sleep(0.3)
res.poll()
check("A19c 倍速 100x 下 0.3s 内放完", res.finished, "cursor=%d/%d" % (res.cursor, res.total))

# A20 HttpEventSource 队列上限与拒绝计数
hs = HttpEventSource()
for i in range(600):
    hs.push({"type": EV_LOG, "task_id": "AGT-1042", "text": "s%d" % i})
check("A20 队列上限 512 + 丢弃计数", hs.received == 512 and hs.dropped == 88,
      "recv=%d drop=%d" % (hs.received, hs.dropped))
ok, why = hs.push({"type": "nope"})
check("A20b 非法事件拒绝计数", ok is False and hs.rejected == 1)

# ================================================================ B 区
print("== B 区：主程序与配对服务集成 ==")
app = QApplication(sys.argv)
from pulse_desktop import DesktopWindow

EVENTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events", "demo_events.jsonl")

# B1 replay 模式接入主程序
win = DesktopWindow(source="replay:" + EVENTS, source_speed=100.0)
win.show()
app.processEvents()
check("B1a replay 模式描述正确", "demo_events.jsonl" in win.engine_desc and "100.0x" in win.engine_desc,
      win.engine_desc)
n_tasks_0 = len(win.tasks)
# 回放速度 100x，17s 时间线 → 0.17s 放完；连打 4 个 tick 保证消费
for _ in range(6):
    win.tick()
    app.processEvents()
    time.sleep(0.08)
check("B1b 事件驱动新建任务进入列表", len(win.tasks) == n_tasks_0 + 1
      and find(win.tasks, "AGT-2001") is not None)
t2001 = find(win.tasks, "AGT-2001")
t1039 = find(win.tasks, "AGT-1039")
t1034 = find(win.tasks, "AGT-1034")
t1033 = find(win.tasks, "AGT-1033")
check("B1c 回放终态正确（新建完成/原任务失败/暂停恢复/评审）",
      t2001.status == "done" and t2001.progress == 100
      and t1039.status == "failed" and t1034.status == "running"
      and t1033.status == "review",
      "%s/%s/%s/%s" % (t2001.status, t1039.status, t1034.status, t1033.status))
check("B1d 引擎消费计数与事件数一致",
      win.engine.applied == 18, "applied=%d" % win.engine.applied)

# B2 新任务追加列表行
check("B2 新任务触发列表行追加", "AGT-2001" in win.rows and win.list.count() == n_tasks_0 + 1)

# B3 全局日志页收到事件日志
logs = [x for x in getattr(win, "_log", []) if "AGT-2001" in str(x) or "AGT-1039" in str(x)]
check("B3 事件日志被记录", len(logs) >= 1, "lines=%d" % len(logs))

# B4 配对服务快照反映事件驱动状态
win.pair.publish(win.tasks)
snap = json.loads(win.pair.state.snapshot())
ids = [x["id"] for x in snap["tasks"]]
r2001 = next(x for x in snap["tasks"] if x["id"] == "AGT-2001")
check("B4 /api/tasks 快照包含事件新建任务且状态正确",
      "AGT-2001" in ids and r2001["status"] == "done" and r2001["progress"] == 100)

# B5 http 模式：POST /api/events
win.close()
win2 = DesktopWindow(source="http")
win2.show()
app.processEvents()
check("B5a http 模式描述正确", "POST /api/events" in win2.engine_desc, win2.engine_desc)
base = "http://127.0.0.1:%d" % win2.pair.port
token = win2.pair.state.token


def post(payload, tok=token):
    req = urllib.request.Request(
        base + "/api/events?token=" + tok if tok else base + "/api/events",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Pulse-Token": tok},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


code, body = post({"type": EV_TASK_STARTED, "task_id": "AGT-8001",
                   "name": "HTTP 推送任务", "agent": "Deployer", "model": "本地 Qwen2.5",
                   "steps": ["构建", "部署"]})
check("B5b POST /api/events 接受事件", code == 200 and body.get("accepted") == 1,
      "%s %s" % (code, body))
for _ in range(3):
    win2.tick()
    app.processEvents()
t8001 = find(win2.tasks, "AGT-8001")
check("B5c 推送事件应用到任务列表", t8001 is not None and t8001.status == "running")

# B6 错误 token
code, body = post({"type": EV_LOG, "task_id": "AGT-8001", "text": "x"}, tok="wrong")
check("B6 错误 token → 401", code == 401)

# B7 坏 JSON
req = urllib.request.Request(base + "/api/events?token=" + token,
                             data=b"{bad json", method="POST")
try:
    urllib.request.urlopen(req, timeout=5)
    code = 200
except urllib.error.HTTPError as e:
    code = e.code
check("B7 坏 JSON → 400", code == 400)

# B8 health 列出 /api/events
with urllib.request.urlopen(base + "/api/health", timeout=5) as r:
    h = json.loads(r.read().decode())
check("B8 http 模式 health 列出事件端点", "/api/events" in h.get("endpoints", []),
      h.get("endpoints"))

# B9 批量推送（events 数组）
code, body = post({"events": [
    {"type": EV_STEP_COMPLETED, "task_id": "AGT-8001", "step_index": 0},
    {"type": EV_TOKENS, "task_id": "AGT-8001", "delta": 2048},
    {"type": EV_TASK_COMPLETED, "task_id": "AGT-8001"},
]})
for _ in range(3):
    win2.tick()
    app.processEvents()
check("B9 批量事件推送并全部应用",
      code == 200 and body.get("accepted") == 3
      and t8001.status == "done" and t8001.tokens >= 2048,
      "%s %s | %s" % (code, body, t8001.status))

# B10 默认模式回归：无 --source 时模拟推进仍工作
win2.close()
win3 = DesktopWindow()
app.processEvents()
p0 = sum(t.progress for t in win3.tasks)
win3.tick(force=True)
p1 = sum(t.progress for t in win3.tasks)
check("B10 默认模拟模式仍推进（回归保障）", p1 > p0, "%d -> %d" % (p0, p1))
check("B10b 默认模式描述", "模拟" in win3.engine_desc, win3.engine_desc)

win3.close()
win.close()

# ---------------------------------------------------------------- 汇总
passed = sum(1 for _, ok, _ in RESULTS if ok)
total = len(RESULTS)
print("")
print("总计 %d 项 | 通过 %d | 失败 %d" % (total, passed, total - passed))
for name, ok, det in RESULTS:
    if not ok:
        print("  FAILED:", name, "|", det)
print("E2E_DONE" if passed == total else "E2E_FAILED")
sys.exit(0 if passed == total else 1)
