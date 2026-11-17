# -*- coding: utf-8 -*-
"""
PULSE · 局域网配对服务（PC 端）

职责：把 MainWindow 里的 Agent 任务以只读快照的形式开放给同一局域网的手机。
- 后台 ThreadingHTTPServer（daemon 线程），端口 8765（占用时自动顺延）
- GET /api/health          健康检查，不需要 token
- GET /api/tasks?token=... 返回任务快照 JSON，带 CORS 与 no-store
- 二维码：segno 生成，QPainter 渲染为 QPixmap，或导出 PNG

线程安全约定：主线程 publish() 时把 tasks 完整序列化成「不可变 JSON 字符串」再在锁内替换；
HTTP 线程只读该字符串，不接触任何 Task 对象，避免与 QTimer 的 tick() 产生竞态。
"""
import json
import os
import re
import secrets
import socket
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

API_PATH = "/api/tasks"
HEALTH_PATH = "/api/health"
EVENTS_PATH = "/api/events"   # P0：POST 推送 Agent 事件（仅 http 事件模式启用）
POLL_PATH = "/api/poll"       # P1：长轮询（rev 变化即返回，未变化挂起至 hold 超时）
STREAM_PATH = "/api/stream"   # P1：SSE 实时推送
COMMAND_PATH = "/api/command"  # P3：POST 手机端写命令（pause/resume/retry，始终可用）
DEFAULT_PORT = 8765
# 配对协议版本（HTTP 接口契约），与 PC 应用 UI 版本 APP_VER 解耦：
# 自 v1.3.0 引入后 /api/tasks 响应字段未变；P1 新增 /api/poll 与 /api/stream
# 为向后兼容扩展，故维持 1.3.0，保证移动端 v1.4.0 与旧版继续可用。
PAIR_VERSION = "1.3.0"

# token 持久化路径：PC 重启后复用同一 token，手机端已保存的地址无需重新扫码。
TOKEN_PATH = os.path.join(os.path.expanduser("~"), ".pulse", "pair_token")


def load_or_create_token():
    """读取持久化 token；不存在或损坏时生成新 token 并落盘（600 权限）。"""
    try:
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        if os.path.exists(TOKEN_PATH):
            with open(TOKEN_PATH, encoding="utf-8") as f:
                t = f.read().strip()
            if re.fullmatch(r"[0-9a-f]{8}", t):
                return t, True  # 复用
        t = secrets.token_hex(4)
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(t)
        os.chmod(TOKEN_PATH, 0o600)
        return t, False  # 新生成
    except OSError:
        return secrets.token_hex(4), False  # 无法落盘时退化为一次性 token

STATUS_LABEL = {
    "running": "运行中", "queued": "排队中", "review": "待人工确认",
    "done": "已完成", "failed": "失败", "paused": "已暂停",
}


def fmt_elapsed(sec):
    if sec < 60:
        return "%ds" % sec
    if sec < 3600:
        return "%dm%02ds" % (sec // 60, sec % 60)
    return "%dh%02dm" % (sec // 3600, (sec % 3600) // 60)


def get_lan_ip():
    """取本机局域网出口 IP（UDP connect 不实际发包），失败时逐级降级。"""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.4)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def task_to_dict(t):
    """PC Task -> 跨端契约字段（下一步移动端「项目」页映射直接消费）。"""
    return {
        "id": t.id,
        "name": t.name,
        "agent": t.agent,
        "model": t.model,
        "status": t.status,
        "status_label": STATUS_LABEL.get(t.status, t.status),
        "progress": t.progress,
        "steps": [{"label": s, "state": st} for s, st in t.steps],
        "steps_done": t.steps_done,
        "steps_total": len(t.steps),
        "elapsed": t.elapsed,
        "elapsed_text": fmt_elapsed(t.elapsed),
        "tokens": t.tokens,
        "priority": t.priority,
        "started": t.started,
        "updated": t.updated,
        "logs": [{"time": tm, "level": lv, "text": tx} for tm, lv, tx in t.logs[-8:]],
    }


def build_payload(tasks, state, host, port):
    total = len(tasks)
    running = sum(1 for t in tasks if t.status == "running")
    done = sum(1 for t in tasks if t.status == "done")
    need = sum(1 for t in tasks if t.status in ("failed", "review", "paused"))
    return {
        "v": 1,
        "generated": datetime.now().strftime("%H:%M:%S"),
        "server": {"host": host, "port": port, "token": state.token, "version": PAIR_VERSION},
        "summary": {
            "total": total, "running": running, "done": done, "need_attention": need,
            "completion_rate": round(sum(t.progress for t in tasks) / total) if total else 0,
        },
        "tasks": [task_to_dict(t) for t in tasks],
    }


class PairState:
    """HTTP 线程与 Qt 主线程之间唯一的共享状态。"""

    def __init__(self):
        self.token, self.token_reused = load_or_create_token()
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)  # 长轮询唤醒
        self._snapshot = json.dumps({"v": 1, "tasks": [], "summary": {}}, ensure_ascii=False)
        self.requests = 0
        self.rev = 0  # 快照修订号：publish 一次 +1，长轮询按此判断变化

    def publish(self, payload):
        s = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._cond:
            self._snapshot = s
            self.rev += 1
            self._cond.notify_all()  # 唤醒所有挂起的 /api/poll

    def snapshot(self):
        with self._lock:
            return self._snapshot

    def wait_for_change(self, known_rev, timeout):
        """长轮询等待：rev 变化返回新快照，超时返回 None。"""
        with self._cond:
            if self.rev != known_rev:
                return self._snapshot
            self._cond.wait(timeout)
            if self.rev != known_rev:
                return self._snapshot
        return None

    def hit(self):
        with self._lock:
            self.requests += 1
            return self.requests


class _Handler(BaseHTTPRequestHandler):
    server_version = "PULSE/%s" % PAIR_VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass  # 静默，避免刷屏

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        # P3：POST（/api/command、/api/events）需允许跨域，浏览器页面的命令按钮依赖它
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        state = self.server.state
        if u.path == HEALTH_PATH:
            self._send_json(200, {
                "ok": True, "service": "PULSE Pair", "version": PAIR_VERSION,
                "port": self.server.server_address[1],
                "token_required": True, "requests": state.requests,
                "endpoints": [HEALTH_PATH, API_PATH, POLL_PATH, STREAM_PATH]
                              + ([EVENTS_PATH] if self.server.event_source else [])
                              + ([COMMAND_PATH] if self.server.command_source else []),
            })
            return
        if u.path == API_PATH:
            token = parse_qs(u.query).get("token", [""])[0]
            if not token or not secrets.compare_digest(token, state.token):
                self._send_json(401, {
                    "ok": False, "error": "invalid_token",
                    "hint": "请使用 PC 端二维码中的完整地址（含 token）",
                })
                return
            state.hit()
            body = state.snapshot().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if u.path == POLL_PATH:
            self._do_poll(state, parse_qs(u.query))
            return
        if u.path == STREAM_PATH:
            self._do_stream(state, parse_qs(u.query))
            return
        self._send_json(404, {"ok": False, "error": "not_found",
                              "endpoints": [HEALTH_PATH, API_PATH, POLL_PATH, STREAM_PATH]})

    # ---------------- P1：长轮询（rev 变化即返回，未变化挂起） ----------------
    def _do_poll(self, state, q):
        token = q.get("token", [""])[0]
        if not token or not secrets.compare_digest(token, state.token):
            self._send_json(401, {"ok": False, "error": "invalid_token"})
            return
        try:
            known = int(q.get("rev", ["0"])[0])
        except ValueError:
            self._send_json(400, {"ok": False, "error": "bad_rev"})
            return
        state.hit()
        hold = float(getattr(self.server, "poll_hold", 8.0))
        snap = state.wait_for_change(known, hold)
        if snap is None:
            # 无变化：204 空响应（Java 层 2xx 走 _onData，Web 层空 body 视为无变化）
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        payload = json.loads(snap)
        payload["rev"] = state.rev
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ---------------- P1：SSE 实时推送 ----------------
    def _do_stream(self, state, q):
        token = q.get("token", [""])[0]
        if not token or not secrets.compare_digest(token, state.token):
            self._send_json(401, {"ok": False, "error": "invalid_token"})
            return
        state.hit()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self._cors()
        self.end_headers()
        try:
            # 立即推送当前快照，之后每次变化推送一次，空闲期发心跳注释行
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            last = None
            idle = 0
            while not self.server.stop_event.is_set():
                snap = state.snapshot()
                if snap != last:
                    self.wfile.write(b"event: tasks\ndata: " + snap.encode("utf-8") + b"\n\n")
                    self.wfile.flush()
                    last = snap
                    idle = 0
                else:
                    idle += 1
                    hb = int(getattr(self.server, "heartbeat_cycles", 20))
                    if hb > 0 and idle >= hb:  # 0.5s × 20 = 10s 心跳（可参数化）
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        idle = 0
                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # 客户端断开：静默清理，服务不受影响

    # ---------------- P0：接收外部 Agent 事件推送 ----------------
    # ---------------- P3：手机端写命令（pause/resume/retry） ----------------
    COMMAND_ACTIONS = {
        # action -> (事件类型, 允许的来源状态, 拒绝原因)
        "pause":  ("task_paused", ("running", "review", "paused"),
                   "仅运行中 / 待人工确认 / 已暂停的任务可以暂停"),
        "resume": ("task_resumed", ("paused", "review"),
                   "仅已暂停 / 待人工确认的任务可以恢复"),
        "retry":  ("task_started", ("failed", "paused", "review", "done"),
                   "失败 / 已暂停 / 待人工确认 / 已完成的任务可以重试（从头开始）"),
    }

    def _handle_command(self, state, q):
        src = self.server.command_source
        if src is None:
            self._send_json(404, {"ok": False, "error": "not_available",
                                  "hint": "命令通道由主窗口注入后开放"})
            return
        token = q.get("token", [""])[0]
        if not token:
            token = self.headers.get("X-Pulse-Token", "")
        if not token or not secrets.compare_digest(token, state.token):
            self._send_json(401, {"ok": False, "error": "invalid_token"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"ok": False, "error": "bad_length"})
            return
        if n <= 0 or n > 65536:
            self._send_json(400, {"ok": False, "error": "bad_length", "max": 65536})
            return
        try:
            raw = json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"ok": False, "error": "bad_json"})
            return
        items = raw.get("commands") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            items = [raw]
        # 任务存在性检查基于最新快照
        snapshot_ids = {t["id"]: t["status"] for t in
                        json.loads(state.snapshot()).get("tasks", [])}
        accepted, details = 0, []
        for obj in items[:32]:
            if not isinstance(obj, dict):
                details.append({"ok": False, "why": "bad_item"})
                continue
            tid = str(obj.get("task_id", ""))
            action = str(obj.get("action", ""))
            if action not in self.COMMAND_ACTIONS:
                details.append({"task_id": tid, "action": action, "ok": False,
                                "why": "unknown_action"})
                continue
            if tid not in snapshot_ids:
                details.append({"task_id": tid, "action": action, "ok": False,
                                "why": "task_not_found"})
                continue
            etype, allowed, why = self.COMMAND_ACTIONS[action]
            if snapshot_ids[tid] not in allowed:
                details.append({"task_id": tid, "action": action, "ok": False,
                                "why": why})
                continue
            ev = {"type": etype, "task_id": tid}
            if action == "pause":
                ev["reason"] = str(obj.get("reason") or "手机端暂停")
            ok, _ = src.push(ev)
            details.append({"task_id": tid, "action": action, "ok": bool(ok),
                            "why": "" if ok else "queue full"})
            accepted += 1 if ok else 0
        self._send_json(200, {"ok": True, "accepted": accepted,
                              "rejected": len(details) - accepted, "details": details})

    def do_POST(self):
        u = urlparse(self.path)
        state = self.server.state
        if u.path == COMMAND_PATH:
            self._handle_command(state, parse_qs(u.query))
            return
        src = self.server.event_source
        if u.path != EVENTS_PATH or src is None:
            self._send_json(404, {"ok": False, "error": "not_found",
                                  "hint": "POST 事件通道仅在 --source http 模式开放"})
            return
        token = parse_qs(u.query).get("token", [""])[0]
        if not token:
            token = self.headers.get("X-Pulse-Token", "")
        if not token or not secrets.compare_digest(token, state.token):
            self._send_json(401, {"ok": False, "error": "invalid_token"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"ok": False, "error": "bad_length"})
            return
        if n <= 0 or n > 262144:  # 256KB 上限
            self._send_json(400, {"ok": False, "error": "bad_length", "max": 262144})
            return
        try:
            raw = json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"ok": False, "error": "bad_json"})
            return
        items = raw.get("events") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            items = [raw]
        accepted, rejected = 0, 0
        for obj in items[:256]:
            ok, _why = src.push(obj)
            accepted += 1 if ok else 0
            rejected += 0 if ok else 1
        self._send_json(200, {"ok": True, "accepted": accepted, "rejected": rejected})


class PairServer:
    def __init__(self, port=DEFAULT_PORT, poll_hold=8.0, heartbeat_cycles=20):
        self.state = PairState()
        self.host = get_lan_ip()
        self.port = port
        self.error = ""
        self.poll_hold = max(1.0, float(poll_hold))  # 长轮询挂起时长（秒）
        self.heartbeat_cycles = int(heartbeat_cycles)  # SSE 心跳间隔（0.5s 周期数）
        self.stop_event = threading.Event()
        self._httpd = None
        self._thread = None
        self.event_source = None  # HttpEventSource，仅 http 事件模式下由宿主注入
        self.command_source = None  # P3：手机命令队列，由主窗口始终注入

    def set_event_source(self, source):
        """宿主在 start() 前调用；注入后 health 会列出 /api/events。"""
        self.event_source = source

    def set_command_source(self, source):
        """宿主在 start() 前调用；注入后手机端可 POST /api/command。"""
        self.command_source = source

    def start(self):
        last = ""
        for p in range(self.port, self.port + 6):
            try:
                httpd = ThreadingHTTPServer(("0.0.0.0", p), _Handler)
                httpd.daemon_threads = True
                httpd.state = self.state
                httpd.event_source = self.event_source
                httpd.command_source = self.command_source
                httpd.poll_hold = self.poll_hold
                httpd.stop_event = self.stop_event
                httpd.heartbeat_cycles = self.heartbeat_cycles
                self._httpd = httpd
                self.port = p
                break
            except OSError as e:
                last = str(e)
        if self._httpd is None:
            self.error = "端口 %d-%d 均不可用：%s" % (self.port, self.port + 5, last)
            return False
        self.error = ""
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            kwargs={"poll_interval": 0.3},
            name="pulse-pair-http", daemon=True,
        )
        self._thread.start()
        return True

    def publish(self, tasks):
        """主线程调用：把当前任务列表序列化成快照。"""
        self.state.publish(build_payload(tasks, self.state, self.host, self.port))

    def url(self):
        return "http://%s:%d%s?token=%s" % (self.host, self.port, API_PATH, self.state.token)

    def health_url(self):
        return "http://127.0.0.1:%d%s" % (self.port, HEALTH_PATH)

    def stop(self):
        if self._httpd is None:
            return
        self.stop_event.set()  # 通知 SSE 循环退出
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        except Exception:
            pass
        self._httpd = None


# ---------------------------------------------------------------- 二维码
def make_qr_pixmap(payload, size=264):
    import segno
    qr = segno.make(payload, error="m")
    matrix = qr.matrix
    n = len(matrix)
    quiet = 4
    total = n + quiet * 2
    scale = max(1, size // total)
    px = total * scale
    img = QImage(px, px, QImage.Format_RGB32)
    img.fill(QColor("#FFFFFF"))
    painter = QPainter(img)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor("#000000")))
    for r, row in enumerate(matrix):
        for c, v in enumerate(row):
            if v:
                painter.drawRect((c + quiet) * scale, (r + quiet) * scale, scale, scale)
    painter.end()
    return QPixmap.fromImage(img)


def save_qr_png(payload, path, scale=8):
    import segno
    qr = segno.make(payload, error="m")
    try:
        qr.save(path, scale=scale, border=4, dark="#000000", light="#FFFFFF")
    except TypeError:
        qr.save(path, scale=scale, border=4)
    return path


# ---------------------------------------------------------------- 配对对话框
class PairDialog(QDialog):
    def __init__(self, pair, parent=None):
        super().__init__(parent)
        self.pair = pair
        self.setWindowTitle("连接手机 · PULSE")
        self.setMinimumWidth(440)
        self.setStyleSheet(
            "QDialog{background:#0F172A;}"
            "QLabel{color:#F8FAFC;background:transparent;border:0;}"
            "QPushButton{background:#1E293B;border:1px solid #2C3C55;border-radius:8px;"
            "padding:0 14px;min-height:34px;color:#E2E8F0;font-size:12px;}"
            "QPushButton:hover{background:#243349;border-color:#3B4A63;}"
            "QPushButton#primary{background:#22C55E;color:#0F172A;font-weight:700;border:0;}"
            "QFrame#card{background:#16223A;border:1px solid #22304A;border-radius:12px;}"
            "QFrame#qrbg{background:#FFFFFF;border-radius:10px;}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        title = QLabel("连接手机 · 扫码查看 Agent 任务进度")
        f = QFont("Fira Sans", 15)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        sub = QLabel("手机与电脑连接同一 Wi-Fi，用相机或扫码工具扫描下方二维码")
        sub.setStyleSheet("color:#94A3B8;")
        root.addWidget(sub)

        # 二维码
        qr_card = QFrame()
        qr_card.setObjectName("card")
        qc = QVBoxLayout(qr_card)
        qc.setContentsMargins(16, 16, 16, 16)
        qr_bg = QFrame()
        qr_bg.setObjectName("qrbg")
        qb = QVBoxLayout(qr_bg)
        qb.setContentsMargins(10, 10, 10, 10)
        qr_label = QLabel()
        qr_label.setAlignment(Qt.AlignCenter)
        try:
            pm = make_qr_pixmap(pair.url())
            qr_label.setPixmap(pm)
            qr_label.setFixedSize(pm.width(), pm.height())
        except Exception as e:
            qr_label.setText("二维码生成失败：%s\n请使用下方地址" % e)
            qr_label.setStyleSheet("color:#EF4444;")
            qr_label.setWordWrap(True)
        qb.addWidget(qr_label, 0, Qt.AlignCenter)
        qc.addWidget(qr_bg, 0, Qt.AlignCenter)
        root.addWidget(qr_card)

        # 状态
        if pair.error:
            state_text = "服务未启动 · %s" % pair.error
            state_color = "#EF4444"
        else:
            state_text = "服务运行中 · 0.0.0.0:%d · 只读快照" % pair.port
            state_color = "#4ADE80"
        self.state_label = QLabel(state_text)
        self.state_label.setStyleSheet("color:%s;font-family:'Fira Code';font-size:11px;" % state_color)
        root.addWidget(self.state_label)

        # 明文地址
        addr_card = QFrame()
        addr_card.setObjectName("card")
        av = QVBoxLayout(addr_card)
        av.setContentsMargins(14, 12, 14, 12)
        av.setSpacing(6)
        cap = QLabel("配对地址（扫码失败时可手动输入）")
        cap.setStyleSheet("color:#64748B;font-size:11px;")
        av.addWidget(cap)
        self.addr = QLabel(pair.url())
        self.addr.setStyleSheet("color:#6EE7A0;font-family:'Fira Code';font-size:11px;")
        self.addr.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.addr.setWordWrap(True)
        av.addWidget(self.addr)
        self.meta = QLabel("token %s   ·   已响应 0 次请求" % pair.state.token)
        self.meta.setStyleSheet("color:#64748B;font-family:'Fira Code';font-size:10px;")
        av.addWidget(self.meta)
        root.addWidget(addr_card)

        tips = QLabel("提示：接口只读、带一次性 token；PC 关闭窗口后服务自动停止。\n"
                     "扫不出二维码时，可直接复制地址在手机浏览器打开查看任务 JSON。")
        tips.setStyleSheet("color:#64748B;font-size:11px;")
        tips.setWordWrap(True)
        root.addWidget(tips)

        row = QHBoxLayout()
        row.addStretch()
        btn_copy = QPushButton("复制地址")
        btn_copy.clicked.connect(self._copy)
        btn_close = QPushButton("关闭")
        btn_close.setObjectName("primary")
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_copy)
        row.addWidget(btn_close)
        root.addLayout(row)

        self._poll = QTimer(self)
        self._poll.timeout.connect(self._refresh_meta)
        self._poll.start(1000)

    def _refresh_meta(self):
        self.meta.setText("token %s   ·   已响应 %d 次请求" %
                          (self.pair.state.token, self.pair.state.requests))

    def _copy(self):
        QApplication.clipboard().setText(self.pair.url())
        self.state_label.setText("地址已复制到剪贴板")
        self.state_label.setStyleSheet("color:#4ADE80;font-family:'Fira Code';font-size:11px;")


def open_pair_dialog(parent, pair):
    dlg = PairDialog(pair, parent)
    dlg.exec()
    return dlg
