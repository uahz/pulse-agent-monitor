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
import secrets
import socket
import threading
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
DEFAULT_PORT = 8765
# 配对协议版本（HTTP 接口契约），与 PC 应用 UI 版本 APP_VER 解耦：
# 自 v1.3.0 引入后接口字段未变，故保持 1.3.0 以保证移动端 v1.4.0 与旧版兼容。
# 若修改 /api/tasks 响应结构，必须同步提升此值与两端解析逻辑。
PAIR_VERSION = "1.3.0"

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
        self.token = secrets.token_hex(4)
        self._lock = threading.Lock()
        self._snapshot = json.dumps({"v": 1, "tasks": [], "summary": {}}, ensure_ascii=False)
        self.requests = 0

    def publish(self, payload):
        s = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._snapshot = s

    def snapshot(self):
        with self._lock:
            return self._snapshot

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
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
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
                "endpoints": [HEALTH_PATH, API_PATH],
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
        self._send_json(404, {"ok": False, "error": "not_found", "endpoints": [HEALTH_PATH, API_PATH]})


class PairServer:
    def __init__(self, port=DEFAULT_PORT):
        self.state = PairState()
        self.host = get_lan_ip()
        self.port = port
        self.error = ""
        self._httpd = None
        self._thread = None

    def start(self):
        last = ""
        for p in range(self.port, self.port + 6):
            try:
                httpd = ThreadingHTTPServer(("0.0.0.0", p), _Handler)
                httpd.daemon_threads = True
                httpd.state = self.state
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
