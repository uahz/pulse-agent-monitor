# -*- coding: utf-8 -*-
"""
PULSE · 事件引擎（P0 数据真实化）

把 v2.0.0 之前「seed_tasks() + random 推进」的本地模拟，升级为可接入真实
Agent 事件源的驱动模型：

    AgentEventSource  事件源协议（三种内置适配器）
      ├─ FileEventSource    tail 跟随 JSONL 事件文件（真实 agent 边跑边写）
      ├─ ReplayEventSource  按时间轴回放录制的事件流（可倍速，用于演示/回归）
      └─ HttpEventSource    接收 POST /api/events 推送（线程安全队列）

    EventEngine       事件 → 任务状态机（6 态 + 步骤四态 + 进度/日志/Tokens）

设计原则：
  - 纯 Python + 标准库，不依赖 Qt，可被任意入口安全 import；
  - 就地修改外部传入的 tasks 列表（与 UI / 悬浮窗 / 配对服务共享引用），
    refresh_all() 等下游逻辑零改动；
  - /api/tasks 数据契约不变，移动端自动吃到真实数据；
  - 引擎自身不写 UI 日志，通过回调 on_log / on_event 通知宿主。
"""
import json
import os
import queue
import random
import threading
import time

from pulse_core import Task, AGENTS, now_str, fmt_tokens

# ---------------------------------------------------------------- 事件类型
EV_TASK_STARTED = "task_started"      # 新建或重启任务
EV_STEP_COMPLETED = "step_completed"  # 完成某一步骤
EV_TASK_PROGRESS = "task_progress"    # 直接汇报进度百分比
EV_TASK_PAUSED = "task_paused"
EV_TASK_RESUMED = "task_resumed"
EV_TASK_REVIEW = "task_review"        # 转入待人工确认
EV_TASK_FAILED = "task_failed"        # 失败（可带 reason）
EV_TASK_COMPLETED = "task_completed"
EV_LOG = "log"                        # 追加任务日志（info/run/ok/warn/error）
EV_TOKENS = "tokens"                  # Token 用量增量

KNOWN_TYPES = {
    EV_TASK_STARTED, EV_STEP_COMPLETED, EV_TASK_PROGRESS,
    EV_TASK_PAUSED, EV_TASK_RESUMED, EV_TASK_REVIEW,
    EV_TASK_FAILED, EV_TASK_COMPLETED, EV_LOG, EV_TOKENS,
}

LOG_LEVELS = ("info", "run", "ok", "warn", "error")


def parse_event(obj):
    """把 dict 解析为规范事件；非法事件返回 (None, 原因)。"""
    if not isinstance(obj, dict):
        return None, "not a dict"
    etype = obj.get("type")
    if etype not in KNOWN_TYPES:
        return None, "unknown type %r" % (etype,)
    task_id = obj.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        return None, "missing task_id"
    ev = {"type": etype, "task_id": task_id.strip()}
    for k in ("name", "agent", "model", "priority", "reason", "text", "level"):
        if k in obj and isinstance(obj[k], str):
            ev[k] = obj[k]
    for k in ("step_index", "delta", "progress"):
        if k in obj and isinstance(obj[k], (int, float)):
            ev[k] = obj[k]
    if "steps" in obj and isinstance(obj["steps"], list):
        ev["steps"] = [str(s) for s in obj["steps"]][:24]
    if "t" in obj and isinstance(obj["t"], (int, float)):
        ev["t"] = float(obj["t"])
    return ev, None


# ---------------------------------------------------------------- 事件源
class AgentEventSource:
    """事件源协议：poll() 返回待处理事件列表，close() 释放资源。"""
    def poll(self):
        raise NotImplementedError

    def close(self):
        pass

    def describe(self):
        return "abstract"


class FileEventSource(AgentEventSource):
    """跟随 JSONL 事件文件：真实 agent 进程边执行边追加事件行。

    容错：坏行跳过并计数，绝不因脏数据中断引擎。
    """

    def __init__(self, path):
        self.path = path
        self._fh = None
        self._offset = 0
        self.bad_lines = 0
        if os.path.exists(path):
            self._fh = open(path, "r", encoding="utf-8")

    def poll(self):
        if self._fh is None:  # 文件尚未出现：等待 agent 创建
            if os.path.exists(self.path):
                self._fh = open(self.path, "r", encoding="utf-8")
            else:
                return []
        events = []
        while True:
            line = self._fh.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                ev, why = parse_event(json.loads(line))
            except (ValueError, TypeError):
                ev, why = None, "bad json"
            if ev is None:
                self.bad_lines += 1
                continue
            events.append(ev)
        return events

    def close(self):
        if self._fh:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None

    def describe(self):
        return "file:%s" % self.path


class ReplayEventSource(AgentEventSource):
    """按时间轴回放录制的事件流（JSONL，每行可带 t 秒）。

    - 无 t 的事件按文件顺序、以 speed 条/秒均匀吐出；
    - 有 t 的事件按 (t - t0) / speed 的节奏到期；
    - 用于演示与回归：同一文件回放结果完全可复现。
    """

    def __init__(self, path, speed=1.0):
        self.speed = max(0.1, float(speed))
        self.timeline = []  # (due_seconds, ev) 按到期时间升序
        self.t0 = None
        self.started_at = None
        self.cursor = 0
        self.bad_lines = 0
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    ev, why = parse_event(json.loads(line))
                except (ValueError, TypeError):
                    ev, why = None, "bad json"
                if ev is None:
                    self.bad_lines += 1
                    continue
                if "t" in ev:
                    due = ev["t"]
                    if self.t0 is None:
                        self.t0 = due
                    due = (due - self.t0) / self.speed
                else:
                    due = (i + 1) / self.speed  # 无时间戳：1 条/秒（按倍速）
                self.timeline.append((due, ev))
        self.timeline.sort(key=lambda x: x[0])
        self.total = len(self.timeline)

    def start(self):
        self.started_at = time.monotonic()

    def poll(self):
        if self.started_at is None:
            self.start()
        now = time.monotonic() - self.started_at
        events = []
        while self.cursor < len(self.timeline) and self.timeline[self.cursor][0] <= now:
            events.append(self.timeline[self.cursor][1])
            self.cursor += 1
        return events

    @property
    def finished(self):
        return self.cursor >= len(self.timeline)

    def describe(self):
        return "replay:%s x%.1f" % (os.path.basename(self.path), self.speed)


class HttpEventSource(AgentEventSource):
    """接收 POST /api/events 推送：配对服务线程 put，主线程 poll。

    队列有上限（防恶意灌入），超出时丢弃最旧事件并计数。
    """

    MAX_QUEUE = 512

    def __init__(self):
        self._q = queue.Queue(maxsize=self.MAX_QUEUE)
        self.dropped = 0
        self.received = 0
        self.rejected = 0
        self._lock = threading.Lock()

    def push(self, obj):
        """由 HTTP 线程调用；返回 (是否接受, 原因)。"""
        ev, why = parse_event(obj)
        if ev is None:
            with self._lock:
                self.rejected += 1
            return False, why or "invalid"
        try:
            self._q.put_nowait(ev)
        except queue.Full:
            with self._lock:
                self.dropped += 1
            return False, "queue full"
        with self._lock:
            self.received += 1
        return True, ""

    def poll(self):
        events = []
        while True:
            try:
                events.append(self._q.get_nowait())
            except queue.Empty:
                break
        return events

    def describe(self):
        return "http(POST /api/events)"


# ---------------------------------------------------------------- 引擎
class EventEngine:
    """事件 → 任务状态机。

    - tasks 列表由宿主传入并就地修改（与 UI / 悬浮窗 / 配对服务共享引用）；
    - simulate=True 且无事件源时保留 v2.0.0 原 random 模拟（向后兼容）；
    - on_log(task, level, text) / on_event(etype, task) 为宿主回调（可空）。
    """

    def __init__(self, tasks, source=None, simulate=True,
                 on_log=None, on_event=None, on_task_added=None):
        self.tasks = tasks          # 外部列表引用，就地修改
        self.source = source
        self.simulate = simulate
        self.on_log = on_log
        self.on_event = on_event
        self.on_task_added = on_task_added
        self.applied = 0            # 已应用事件计数
        self.unknown_ids = []       # 未匹配任务的容错记录
        self._unknown_seen = set()

    # ---------------- 主入口 ----------------
    def step(self, dt=2):
        """消费一轮事件并推进；返回是否有任何数据变化。"""
        changed = False
        if self.source is not None:
            for ev in self.source.poll():
                if self._apply(ev):
                    changed = True
        if self.simulate and self.source is None:
            changed = self._simulate_step(dt) or changed
        elif self.simulate and self.source is not None:
            # 事件模式下：running 任务按真实时间流逝累计 elapsed
            for t in self.tasks:
                if t.status == "running":
                    t.elapsed += dt
                    changed = True
        return changed

    # ---------------- 事件应用 ----------------
    def _task(self, ev):
        tid = ev["task_id"]
        for t in self.tasks:
            if t.id == tid:
                return t
        with_no = "task_id=%s" % tid
        if with_no not in self._unknown_seen:
            self._unknown_seen.add(with_no)
            self.unknown_ids.append(with_no)
        return None

    def _apply(self, ev):
        etype = ev["type"]
        if etype == EV_TASK_STARTED:
            return self._apply_started(ev)
        t = self._task(ev)
        if t is None:
            return False
        handler = {
            EV_STEP_COMPLETED: self._apply_step,
            EV_TASK_PROGRESS: self._apply_progress,
            EV_TASK_PAUSED: self._apply_status,
            EV_TASK_RESUMED: self._apply_status,
            EV_TASK_REVIEW: self._apply_status,
            EV_TASK_FAILED: self._apply_failed,
            EV_TASK_COMPLETED: self._apply_completed,
            EV_LOG: self._apply_log,
            EV_TOKENS: self._apply_tokens,
        }[etype]
        ok = handler(ev, t)
        if ok:
            t.updated = now_str()
            self.applied += 1
            if self.on_event:
                self.on_event(etype, t)
        return ok

    def _apply_started(self, ev):
        tid = ev["task_id"]
        existing = None
        for t in self.tasks:
            if t.id == tid:
                existing = t
                break
        if existing is not None:
            # 重启：清零后重跑
            existing.status = "running"
            existing.progress = 0
            existing.elapsed = 0
            existing.tokens = 0
            existing.steps = [(s, "todo") for s, _ in existing.steps]
            existing.add_log("run", "任务重启，重新开始执行")
            self._after(existing, ev)
            return True
        # 新建：payload 提供名称/Agent/模型/步骤，缺省给安全默认值
        name = ev.get("name") or tid
        agent = ev.get("agent") or AGENTS[0][0]
        model = ev.get("model") or AGENTS[0][2]
        steps = ev.get("steps") or ["执行中"]
        t = Task(
            id=tid, name=name, agent=agent, model=model,
            status="running", progress=0,
            steps=[(s, "todo") for s in steps],
            elapsed=0, tokens=0, started=now_str(), updated=now_str(),
            priority=ev.get("priority") or "中",
        )
        if steps:
            t.steps[0] = (steps[0], "active")
        t.add_log("run", "任务由事件源创建并开始执行")
        self.tasks.append(t)
        self._after(t, ev)
        if self.on_task_added:
            self.on_task_added(t)
        return True

    def _apply_step(self, ev, t):
        idx = int(ev.get("step_index", -1))
        if 0 <= idx < len(t.steps):
            s, _ = t.steps[idx]
            t.steps[idx] = (s, "done")
        else:
            # 无索引：完成第一个进行中/待办步骤
            for j, (s, st) in enumerate(t.steps):
                if st in ("active", "todo"):
                    t.steps[j] = (s, "done")
                    idx = j
                    break
        if idx < 0:
            return False
        self._resync_steps(t)
        self._sync_progress(t)
        t.add_log("run", "步骤完成：%s" % t.steps[idx][0])
        return True

    def _apply_progress(self, ev, t):
        p = int(ev.get("progress", -1))
        if not 0 <= p <= 100:
            return False
        t.progress = p
        # 步骤四态按百分比同步（与模拟模式观感一致）
        done_n = round(len(t.steps) * p / 100)
        active_state = "active" if t.status == "running" else "blocked"
        t.steps = [(s, "done" if j < done_n else ("active" if j == done_n else "todo"))
                   for j, (s, _) in enumerate(t.steps)]
        return True

    def _apply_status(self, ev, t):
        etype = ev["type"]
        if etype == EV_TASK_PAUSED:
            if t.status == "done":
                return False
            t.status = "paused"
            self._resync_steps(t)
            t.add_log("warn", "任务已暂停" + ("：%s" % ev["reason"] if ev.get("reason") else ""))
        elif etype == EV_TASK_RESUMED:
            if t.status not in ("paused", "review"):
                return False
            t.status = "running"
            self._resync_steps(t)
            t.add_log("run", "任务恢复执行")
        elif etype == EV_TASK_REVIEW:
            if t.status in ("done", "failed"):
                return False
            t.status = "review"
            self._resync_steps(t)
            t.add_log("warn", "产出待人工确认，已暂停自动推进")
        return True

    def _apply_failed(self, ev, t):
        if t.status == "done":
            return False
        t.status = "failed"
        self._resync_steps(t)
        reason = ev.get("reason") or "未提供原因"
        t.add_log("error", "执行失败：%s" % reason)
        return True

    def _apply_completed(self, ev, t):
        t.status = "done"
        t.progress = 100
        t.steps = [(s, "done") for s, _ in t.steps]
        t.add_log("ok", "全部步骤完成，结果已归档")
        return True

    def _apply_log(self, ev, t):
        level = ev.get("level") or "info"
        if level not in LOG_LEVELS:
            level = "info"
        t.add_log(level, ev.get("text") or "")
        return True

    def _apply_tokens(self, ev, t):
        delta = int(ev.get("delta", 0))
        if delta <= 0:
            return False
        t.tokens += delta
        return True

    # ---------------- 状态同步 ----------------
    def _resync_steps(self, t):
        """让步骤四态与任务状态保持一致（done 之外的第一个非完成步为 active/blocked）。"""
        if t.status == "done":
            t.steps = [(s, "done") for s, _ in t.steps]
            return
        active_state = "active" if t.status == "running" else "blocked"
        for j, (s, st) in enumerate(t.steps):
            if st == "done":
                continue
            t.steps[j] = (s, active_state)
            break

    def _sync_progress(self, t):
        total = len(t.steps) or 1
        done_n = sum(1 for _, st in t.steps if st == "done")
        t.progress = min(100, round(done_n / total * 100))

    def _after(self, t, ev):
        t.updated = now_str()
        self.applied += 1
        if self.on_log:
            pass  # 事件内部已直接 add_log；回调留给宿主写全局日志
        if self.on_event:
            self.on_event(ev["type"], t)

    # ---------------- 兼容模拟（无事件源时）----------------
    def _simulate_step(self, dt=2):
        """原 v2.0.0 random 模拟，逐字迁自 pulse_studio.tick() 的任务循环。"""
        changed = False
        for t in self.tasks:
            if t.status == "running":
                step = random.randint(1, 4)
                t.progress = min(100, t.progress + step)
                t.elapsed += dt
                t.tokens += random.randint(120, 640)
                t.updated = now_str()
                done_n = round(len(t.steps) * t.progress / 100)
                t.steps = [(s, "done" if j < done_n else ("active" if j == done_n else "todo"))
                           for j, (s, _) in enumerate(t.steps)]
                if t.progress >= 100:
                    t.status = "done"
                    t.add_log("ok", "全部步骤完成，结果已归档")
                    if self.on_event:
                        self.on_event("sim_done", t)
                elif random.random() < 0.28:
                    t.add_log("run", "步骤推进至 %d%%，已处理 %s tokens" %
                              (t.progress, fmt_tokens(t.tokens)))
                    if self.on_event:
                        self.on_event("sim_progress", t)
                changed = True
            elif t.status == "queued" and random.random() < 0.12:
                t.status = "running"
                t.add_log("run", "任务出队，开始执行")
                if self.on_event:
                    self.on_event("sim_start", t)
                changed = True
            elif t.status == "review" and random.random() < 0.05:
                t.status = "running"
                t.add_log("run", "人工确认通过，继续执行")
                changed = True
        return changed
