# -*- coding: utf-8 -*-
"""
PULSE · P1 链路升级验证

A 区（PC 服务端，独立 PairServer，短 hold/心跳加速）：
    token 持久化（落盘/600 权限/重启复用/损坏重生成）
    /api/poll 长轮询（rev 变化立即返回 / hold 唤醒 / 超时 204 / 鉴权 / 坏 rev）
    /api/stream SSE（初始快照 / 变化推送 / 心跳 / 鉴权 / 断开清理）
    /api/tasks 契约不变（响应不含 rev）
    health 端点清单
B 区（移动端，Chromium + fetch 拦截桥，加载 APK 内真实页面）：
    首轮 /api/tasks 全量 → /api/poll?rev=N 长轮询切换
    rev 递增与数据同步、204 空轮询节奏
    失败指数退避（1s/2s 递增）与成功重置
    断开（disconnect）后不再发出请求；断线回退语义不回归

用法：QT_QPA_PLATFORM=offscreen python3.12 verify_p1.py
退出码 0 = 全部通过。
"""
import http.client
import json
import os
import re
import shutil
import stat
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pulse_core import seed_tasks
import pulse_pair_server as PPS
from pulse_pair_server import PairServer, build_payload

# ---- 可移植性：APK 与截图输出目录支持参数/自动探测（沙箱 /workspace 与 GitHub 仓库结构均可）----
_HERE = os.path.dirname(os.path.abspath(__file__))
_ap = __import__("argparse").ArgumentParser(description="PULSE P1 链路验证")
_ap.add_argument("--apk", default=None, help="签名 APK 路径（默认自动探测）")
_ap.add_argument("--out", default=None, help="截图输出目录（默认自动探测）")
_ap.add_argument("--port", type=int, default=9341, help="Chromium CDP 端口")
ARGS, _ = _ap.parse_known_args()


def _detect_apk():
    if ARGS.apk:
        return ARGS.apk
    for c in (os.path.join(_HERE, "..", "releases", "PULSE_v1.5.0.apk"),
              "/workspace/PULSE_v1.5.0.apk"):
        if os.path.exists(c):
            return os.path.abspath(c)
    raise RuntimeError("未找到 PULSE_v1.5.0.apk，用 --apk 指定")


def _detect_out():
    if ARGS.out:
        return ARGS.out
    for c in (os.path.join(_HERE, "..", "..", "PulseApp"),  # 沙箱
              _HERE):                                        # 仓库 desktop/
        if os.path.isdir(c) and os.access(c, os.W_OK):
            return os.path.abspath(c)
    return _HERE


APK_PATH = _detect_apk()
OUT_DIR = _detect_out()

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + str(detail)[:100]) if detail else ""))


def get(port, path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=12) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode()
            return e.code, (json.loads(raw) if raw else {})
        except Exception:
            return e.code, {}


# token 文件重定向到临时 HOME，避免污染真实环境
TMP_HOME = "/tmp/p1_home"
shutil.rmtree(TMP_HOME, ignore_errors=True)
os.makedirs(TMP_HOME, exist_ok=True)
PPS.TOKEN_PATH = os.path.join(TMP_HOME, ".pulse", "pair_token")

print("== A 区：PC 服务端 ==")

# A1/A2 首次生成：落盘 + 600 权限 + hex8 格式
srv = PairServer(poll_hold=1.0, heartbeat_cycles=4)
assert srv.start(), srv.error
srv.publish(seed_tasks())
tok = srv.state.token
exists = os.path.exists(PPS.TOKEN_PATH)
mode = stat.S_IMODE(os.stat(PPS.TOKEN_PATH).st_mode) if exists else 0
check("A1 token 落盘且权限 600", exists and mode == 0o600, "mode=%o" % mode)
check("A2 token 格式 hex8", bool(re.fullmatch(r"[0-9a-f]{8}", tok)), tok)

# A3 重启复用
srv.stop()
srv2 = PairServer(poll_hold=1.0, heartbeat_cycles=4)
srv2.start()
check("A3 重启后复用同一 token", srv2.state.token == tok and srv2.state.token_reused is True)

# A4 损坏文件 → 重新生成
with open(PPS.TOKEN_PATH, "w", encoding="utf-8") as f:
    f.write("not-a-token!!")
srv2.stop()
srv3 = PairServer(poll_hold=1.0, heartbeat_cycles=4)
srv3.start()
srv3.publish(seed_tasks())
check("A4 损坏 token 自动重新生成",
      srv3.state.token != tok and re.fullmatch(r"[0-9a-f]{8}", srv3.state.token))
srv3.publish(seed_tasks())
TOK = srv3.state.token
PORT = srv3.port

# A5 /api/tasks 契约不变（不含 rev）
code, body = get(PORT, "/api/tasks?token=" + TOK)
check("A5 /api/tasks 契约不变（12 任务、无 rev 字段）",
      code == 200 and len(body.get("tasks", [])) == 12 and "rev" not in body)

# A6 health 端点清单
code, h = get(PORT, "/api/health")
check("A6 health 列出 poll/stream 端点",
      set(h.get("endpoints", [])) >= {"/api/poll", "/api/stream"}, h.get("endpoints"))

# A7 poll：rev 过期立即返回新数据（含 rev）
code, body = get(PORT, "/api/poll?token=%s&rev=0" % TOK)
check("A7 rev 过期立即返回 200 + rev", code == 200 and body.get("rev") == srv3.state.rev
      and len(body.get("tasks", [])) == 12,
      "code=%s rev=%s state.rev=%s" % (code, body.get("rev"), srv3.state.rev))

# A8 poll：rev 相同 → 挂起，publish 后快速唤醒
box = {}
def poll_bg():
    t0 = time.monotonic()
    c, b = get(PORT, "/api/poll?token=%s&rev=1" % TOK)
    box["dt"] = time.monotonic() - t0
    box["code"] = c
    box["body"] = b
th = threading.Thread(target=poll_bg, daemon=True)
th.start()
time.sleep(0.5)
srv3.publish(seed_tasks())  # rev=2
th.join(timeout=10)
check("A8 hold 中 publish 立即唤醒（<0.8s）",
      box.get("code") == 200 and box.get("dt", 99) < 0.8 and box["body"].get("rev") == 2,
      "dt=%.2fs" % box.get("dt", -1))

# A9 poll：hold 超时 204
t0 = time.monotonic()
code, body = get(PORT, "/api/poll?token=%s&rev=%d" % (TOK, srv3.state.rev))
dt = time.monotonic() - t0
check("A9 无变化挂起至 hold 超时 204",
      code == 204 and 0.9 <= dt < 2.5, "dt=%.2fs code=%s state.rev=%s" % (dt, code, srv3.state.rev))

# A10/A11 poll 鉴权与坏 rev
code, _ = get(PORT, "/api/poll?token=wrong&rev=0")
check("A10 错 token → 401", code == 401)
code, _ = get(PORT, "/api/poll?token=%s&rev=abc" % TOK)
check("A11 坏 rev → 400", code == 400)

# A12-A16 SSE
conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=15)
conn.request("GET", "/api/stream?token=" + TOK)
resp = conn.getresponse()
check("A12 SSE 返回 200 + event-stream",
      resp.status == 200 and "event-stream" in resp.getheader("Content-Type", ""))
lines = []
def read_lines(n):
    out = []
    for _ in range(n):
        out.append(resp.readline().decode("utf-8").rstrip("\n"))
    return out
head = read_lines(5)
check("A13 SSE 立即推送 connected 注释 + event: tasks + data JSON",
      head[0] == ": connected" and head[2] == "event: tasks"
      and head[3].startswith("data: {") and '"tasks"' in head[3],
      " | ".join(x[:26] for x in head))
# 变化推送
srv3.publish(seed_tasks())  # rev=3
pushed = read_lines(3)
snap = json.loads(pushed[1][6:]) if pushed[1].startswith("data: ") else {}
check("A14 快照变化时推送新数据", pushed[0] == "event: tasks" and len(snap.get("tasks", [])) == 12,
      " | ".join(x[:20] for x in pushed))
# 心跳（heartbeat_cycles=4 → ~2s）
t0 = time.monotonic()
hb = read_lines(2)
dt = time.monotonic() - t0
check("A15 空闲心跳注释行", hb[0] == ": ping" and 1.0 < dt < 5.0,
      "dt=%.2f lines=%s" % (dt, hb))
# 客户端断开 → 服务存活
conn.close()
time.sleep(0.3)
code, _ = get(PORT, "/api/tasks?token=" + TOK)
check("A16 SSE 客户端断开后服务存活", code == 200)

# A17 SSE 错 token
conn2 = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
conn2.request("GET", "/api/stream?token=wrong")
r2 = conn2.getresponse()
check("A17 SSE 错 token → 401", r2.status == 401)
conn2.close()

# A18 stop 后 SSE 退出（stop_event 生效，stop 不挂死）
t0 = time.monotonic()
srv3.stop()
dt = time.monotonic() - t0
check("A18 stop 时 SSE 循环退出（stop 不挂死）", dt < 3.0, "dt=%.2fs" % dt)

# ================================================================ B 区
print("== B 区：移动端长轮询（Chromium + fetch 拦截桥）==")
# 起一个干净的 PC 服务供页面连接
srvB = PairServer(poll_hold=1.0, heartbeat_cycles=4)
srvB.start()
srvB.publish(seed_tasks())
INFO = "/tmp/p1_info.json"
with open(INFO, "w", encoding="utf-8") as f:
    json.dump({"url": srvB.url(), "token": srvB.state.token}, f)

# APK 内真实页面
E2E = "/tmp/p1_e2e"
shutil.rmtree(E2E, ignore_errors=True)
os.makedirs(E2E)
os.system('cd %s && unzip -oq "%s" "assets/*"' % (E2E, APK_PATH))
shutil.move(os.path.join(E2E, "assets", "index.html"), os.path.join(E2E, "index.html"))
os.system("cp -r %s/assets/fonts %s/fonts" % (E2E, E2E))

import subprocess
import websocket

def chromium():
    import shutil as sh
    for n in ("chromium", "chromium-browser", "google-chrome"):
        p = sh.which(n)
        if p:
            return p
    raise RuntimeError("未找到 Chromium")

proc = subprocess.Popen([
    chromium(), "--headless=new", "--no-sandbox", "--disable-gpu",
    "--disable-dev-shm-usage", "--disable-web-security",
    "--allow-file-access-from-files", "--remote-allow-origins=*",
    "--remote-debugging-port=%d" % ARGS.port,
    "--user-data-dir=" + os.path.join(E2E, ".chrome-profile"),
    "--window-size=440,940", "about:blank",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

for _ in range(60):
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % ARGS.port, timeout=1).read()
        break
    except Exception:
        time.sleep(0.25)
else:
    raise RuntimeError("Chromium CDP 未就绪")

_req = urllib.request.Request("http://127.0.0.1:%d/json/new?about:blank" % ARGS.port, method="PUT")
tab = json.loads(urllib.request.urlopen(_req, timeout=5).read())
ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=60)
_seq = [0]


def cmd(method, params=None, timeout=45):
    _seq[0] += 1
    mid = _seq[0]
    ws.send(json.dumps({"id": mid, "method": "method" and method, "params": params or {}}))
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = json.loads(ws.recv())
        if msg.get("id") == mid:
            if "error" in msg:
                raise RuntimeError("%s -> %s" % (method, msg["error"]))
            return msg.get("result", {})
    raise TimeoutError(method)


def ev(js, timeout=45):
    r = cmd("Runtime.evaluate", {"expression": js, "returnByValue": True,
                                 "awaitPromise": True}, timeout=timeout)
    if "exceptionDetails" in r:
        raise RuntimeError("JS 异常: " + json.dumps(r["exceptionDetails"], ensure_ascii=False)[:400])
    return r.get("result", {}).get("value")


def shot(name):
    r = cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    import base64
    open(os.path.join(OUT_DIR, name), "wb").write(base64.b64decode(r["data"]))


cmd("Page.enable")
cmd("Runtime.enable")
cmd("Page.navigate", {"url": "file://" + os.path.join(E2E, "index.html")})
time.sleep(2.2)

# 注入 fetch 拦截桥（记录请求时间戳，可控失败）
INJECT = r"""
(() => {
  const orig = window.fetch.bind(window);
  window.__reqTimes = [];
  window.__failNext = 0;
  window.fetch = function(url, opts) {
    window.__reqTimes.push({url: String(url), at: Date.now()});
    if (window.__failNext > 0) {
      window.__failNext--;
      return Promise.reject(new TypeError('simulated network failure'));
    }
    return orig(url, opts);
  };
  return 'bridge-ok';
})()
"""
check("B0 fetch 拦截桥注入", ev(INJECT) == "bridge-ok")

info = json.load(open(INFO))
host_port = "127.0.0.1:%d" % srvB.port
# 连接（面板手动路径）
ev("document.getElementById('linkHost').value = %s;" % json.dumps(host_port))
ev("document.getElementById('linkHost').dispatchEvent(new Event('input'))")
ev("document.getElementById('linkToken').value = %s;" % json.dumps(info["token"]))
ev("document.getElementById('linkToken').dispatchEvent(new Event('input'))")
ev("document.getElementById('btnConnect').click()")
time.sleep(1.6)

reqs = ev("JSON.stringify(window.__reqTimes.map(x => x.url))")
urls = json.loads(reqs)
check("B1 首轮请求为 /api/tasks 全量", bool(urls) and "/api/tasks?" in urls[0], urls[0] if urls else "")
n_cards = ev("document.querySelectorAll('#projectList .project-card').length")
check("B2 连接成功渲染 12 个远端任务", n_cards == 12, "cards=%s" % n_cards)
poll_urls = [u for u in urls[1:] if "/api/poll" in u]
check("B3 后续请求切换为 /api/poll 且带 rev",
      len(poll_urls) >= 1 and "rev=" in poll_urls[0], poll_urls[0] if poll_urls else "")

# rev 递增：PC publish 新快照（等在途 hold 结束）
time.sleep(2.6)  # hold 1s 超时 → 204 → 立即下一轮（rev 已带）
srvB.publish(seed_tasks())  # rev+1
time.sleep(2.2)
reqs2 = json.loads(ev("JSON.stringify(window.__reqTimes.map(x => x.url))"))
polls = [u for u in reqs2 if "/api/poll" in u]
revs = [int(u.split("rev=")[-1]) for u in polls]
check("B4 长轮询 rev 递增推进", len(revs) >= 3 and revs[-1] >= 2
      and any(b > a for a, b in zip(revs, revs[1:])), "revs=%s" % revs[-6:])

# 204 空轮询节奏：两次 poll 间隔 ≈ hold(1s) 而非固定轮询间隔
gaps = []
times = json.loads(ev("JSON.stringify(window.__reqTimes.map(x => x.at))"))
if len(times) >= 3:
    gaps = [b - a for a, b in zip(times, times[1:])]
check("B5 204 空轮询间隔约等于 hold（1s 上下）",
      bool(gaps) and 700 <= sum(gaps[-3:]) / len(gaps[-3:]) <= 4000,
      "gaps=%s" % gaps[-4:])

# 指数退避：连续 2 次失败 → 间隔递增
ev("window.__failNext = 2;")
ev("window.__reqTimes.length = 0;")
n_before = ev("window.__reqTimes.length")
# 等在途请求结束再制造失败
time.sleep(1.6)
t_fail_start = time.time()
time.sleep(5.2)
times = json.loads(ev("JSON.stringify(window.__reqTimes.map(x => x.at))"))
dts = [b / 1000 - a / 1000 for a, b in zip(times, times[1:])]
check("B6 失败后指数退避（间隔 ≥1s 且递增）",
      len(dts) >= 2 and dts[0] >= 0.9 and dts[1] >= dts[0] + 0.5,
      "dts=%s" % [round(x, 2) for x in dts[:4]])

# 成功重置：恢复后下一轮立即发出（间隔回到 ~1s hold 节奏）
time.sleep(3.0)
times = json.loads(ev("JSON.stringify(window.__reqTimes.map(x => x.at))"))
if len(times) >= 2:
    d2 = [b / 1000 - a / 1000 for a, b in zip(times, times[1:])]
    check("B7 成功后退避重置（间隔回落）", d2[-1] < 4.0, "last=%.2f" % d2[-1])
else:
    check("B7 成功后退避重置（间隔回落）", False, "无后续请求")

# 断开后不再发出请求
ev("document.getElementById('btnDisconnect').click()")
time.sleep(0.6)
n1 = len(json.loads(ev("JSON.stringify(window.__reqTimes.map(x => x.at))")))
time.sleep(2.6)
n2 = len(json.loads(ev("JSON.stringify(window.__reqTimes.map(x => x.at))")))
check("B8 disconnect 后无新请求", n2 == n1, "n=%d → %d" % (n1, n2))
cards = ev("document.querySelectorAll('#projectList .project-card').length")
check("B9 断线回退本地项目（语义不回归）", cards == 5, "cards=%s" % cards)

# 停 Chromium 与服务
try:
    ws.close()
except Exception:
    pass
proc.terminate()
srvB.stop()

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
