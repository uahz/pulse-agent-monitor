# -*- coding: utf-8 -*-
"""
PULSE · P3 手机端写命令端到端验证

A 区（PC，StudioWindow 模拟模式 + 命令通道）：
    /api/command 鉴权、暂停/恢复/重试→引擎应用→快照变化、
    终态/未知任务/白名单外拒绝、批量命令、health 端点
B 区（移动端，Chromium + fetch 拦截桥，加载 APK 内真实页面）：
    抽屉按钮按状态显隐、点击发出 POST /api/command、
    命令回执 toast、未连接态无按钮

用法：QT_QPA_PLATFORM=offscreen python3.12 verify_p3.py
退出码 0 = 全部通过。
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication

# ---- 可移植性：APK 与输出目录支持参数/自动探测（沙箱与 GitHub 仓库结构均可）----
_HERE = os.path.dirname(os.path.abspath(__file__))
_ap = __import__("argparse").ArgumentParser(description="PULSE P3 写命令验证")
_ap.add_argument("--apk", default=None, help="签名 APK 路径（默认自动探测）")
_ap.add_argument("--out", default=None, help="截图输出目录（默认当前目录）")
_ap.add_argument("--port", type=int, default=9344, help="Chromium CDP 端口")
ARGS, _r = _ap.parse_known_args()


def _detect_apk():
    if ARGS.apk:
        return ARGS.apk
    for c in (os.path.join(_HERE, "..", "releases", "PULSE_v1.6.0.apk"),
              "/workspace/PULSE_v1.6.0.apk"):
        if os.path.exists(c):
            return os.path.abspath(c)
    raise RuntimeError("未找到 PULSE_v1.6.0.apk，用 --apk 指定")


APK_PATH = _detect_apk()
OUT_DIR = ARGS.out or _HERE

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + str(detail)[:110]) if detail else ""))


def post(port, path, payload, token):
    req = urllib.request.Request(
        "http://127.0.0.1:%d%s?token=%s" % (port, path, token),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def get(port, path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


print("== A 区：PC 命令通道（模拟模式 + 命令）==")
app = QApplication(sys.argv)
from pulse_desktop import DesktopWindow

win = DesktopWindow()
win.live = False
win.engine.simulate = False  # 冻结模拟推进（random），断言基于确定状态；tick(force=True) 仍消费命令
app.processEvents()
PORT = win.pair.port
TOKEN = win.pair.token if hasattr(win.pair, "token") else win.pair.state.token
check("A0 health 列出 /api/command", "/api/command" in get(PORT, "/api/health")[1].get("endpoints", []))


def snap_status(tid):
    code, body = get(PORT, "/api/tasks?token=" + TOKEN)
    for t in body.get("tasks", []):
        if t["id"] == tid:
            return t["status"], t.get("progress")
    return None, None


tid_running = next(t.id for t in win.tasks if t.status == "running")
tid_done = next(t.id for t in win.tasks if t.status == "done")
tid_failed = next(t.id for t in win.tasks if t.status == "failed")
tid_queued = next(t.id for t in win.tasks if t.status == "queued")

# A1 暂停 running → tick → 快照 paused
code, body = post(PORT, "/api/command", {"task_id": tid_running, "action": "pause"}, TOKEN)
win.tick(force=True)
app.processEvents()
st, _ = snap_status(tid_running)
check("A1 暂停运行中任务（回执 accepted=1 → 快照 paused）",
      code == 200 and body.get("accepted") == 1 and st == "paused", "%s %s" % (code, st))

# A2 恢复
code, body = post(PORT, "/api/command", {"task_id": tid_running, "action": "resume"}, TOKEN)
win.tick(force=True)
app.processEvents()
st, _ = snap_status(tid_running)
check("A2 恢复已暂停任务 → running", body.get("accepted") == 1 and st == "running", st)

# A3 重试 failed → running + progress 0
code, body = post(PORT, "/api/command", {"task_id": tid_failed, "action": "retry"}, TOKEN)
win.tick(force=True)
app.processEvents()
st, prog = snap_status(tid_failed)
# 同一 tick 内模拟推进最多 +4%，重试后立即开始推进属预期行为
check("A3 重试失败任务（从头开始 → running / ≤4%）",
      body.get("accepted") == 1 and st == "running" and prog is not None and prog <= 4,
      "%s %s%%" % (st, prog))

# A4 重试 done → 重新执行
code, body = post(PORT, "/api/command", {"task_id": tid_done, "action": "retry"}, TOKEN)
win.tick(force=True)
app.processEvents()
st, prog = snap_status(tid_done)
check("A4 已完成任务可重新执行",
      body.get("accepted") == 1 and st == "running" and prog is not None and prog <= 4)

# A5 终态拒绝暂停（A4 已重试 tid_done，换一个仍处于 done 的任务）
tid_done2 = next(t.id for t in win.tasks if t.status == "done" and t.id != tid_done)
code, body = post(PORT, "/api/command", {"task_id": tid_done2, "action": "pause"}, TOKEN)
d0 = body.get("details", [{}])[0]
check("A5 已完成任务拒绝暂停（给出原因）", body.get("rejected") == 1
      and d0.get("why") == "仅运行中 / 待人工确认 / 已暂停的任务可以暂停", d0.get("why"))

# A6 queued 拒绝恢复
code, body = post(PORT, "/api/command", {"task_id": tid_queued, "action": "resume"}, TOKEN)
check("A6 排队中任务拒绝恢复", body.get("rejected") == 1)

# A7 未知任务
code, body = post(PORT, "/api/command", {"task_id": "AGT-GHOST", "action": "pause"}, TOKEN)
check("A7 未知任务拒绝（task_not_found）", body.get("rejected") == 1
      and body["details"][0].get("why") == "task_not_found")

# A8 白名单外 action
code, body = post(PORT, "/api/command", {"task_id": tid_running, "action": "delete"}, TOKEN)
check("A8 白名单外 action 拒绝", body.get("rejected") == 1
      and body["details"][0].get("why") == "unknown_action")

# A9 批量：对两个不同任务暂停（批量基于同一快照校验，顺序依赖命令属预期拒绝语义）
tid_r2 = next(t.id for t in win.tasks if t.status == "running" and t.id != tid_running)
code, body = post(PORT, "/api/command", {"commands": [
    {"task_id": tid_running, "action": "pause"},
    {"task_id": tid_r2, "action": "pause"},
]}, TOKEN)
win.tick(force=True); app.processEvents()
st1, _ = snap_status(tid_running)
st2, _ = snap_status(tid_r2)
check("A9 批量命令（两任务同时暂停）",
      body.get("accepted") == 2 and st1 == "paused" and st2 == "paused",
      "%s %s/%s" % (body.get("accepted"), st1, st2))

# A10 错 token
code, body = post(PORT, "/api/command", {"task_id": tid_running, "action": "pause"}, "wrong")
check("A10 错 token → 401", code == 401)

# A11 未连接（无 token）
req = urllib.request.Request("http://127.0.0.1:%d/api/command" % PORT,
                             data=json.dumps({"task_id": tid_running, "action": "pause"}).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
try:
    urllib.request.urlopen(req, timeout=10)
    code = 200
except urllib.error.HTTPError as e:
    code = e.code
check("A11 缺失 token → 401", code == 401)

win.close()

# ================================================================ B 区
print("== B 区：移动端抽屉命令按钮（Chromium）==")
win2 = DesktopWindow()
win2.live = False
win2.engine.simulate = False  # 同上：冻结模拟，queued/running 状态不再随机变化
app.processEvents()
PORT2 = win2.pair.port
TOKEN2 = win2.pair.state.token

# 从 v1.6.0 APK 解出真实页面
E2E = "/tmp/p3_e2e"
shutil.rmtree(E2E, ignore_errors=True)
os.makedirs(E2E)
os.system('cd %s && unzip -oq "%s" "assets/*"' % (E2E, APK_PATH))
os.rename(os.path.join(E2E, "assets", "index.html"), os.path.join(E2E, "index.html"))
os.system("cp -r %s/assets/fonts %s/fonts" % (E2E, E2E))

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
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = json.loads(ws.recv())
        if msg.get("id") == mid:
            if "error" in msg:
                raise RuntimeError("%s -> %s" % (method, msg["error"]))
            return msg.get("result", {})
    raise TimeoutError(method)


def ev(js):
    r = cmd("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True})
    if "exceptionDetails" in r:
        raise RuntimeError("JS 异常: " + json.dumps(r["exceptionDetails"], ensure_ascii=False)[:400])
    return r.get("result", {}).get("value")


cmd("Page.enable")
cmd("Page.navigate", {"url": "file://" + os.path.join(E2E, "index.html")})
time.sleep(2.2)

INJECT = """
(() => {
  const orig = window.fetch.bind(window);
  window.__reqTimes = [];
  window.fetch = function(url, opts) {
    window.__reqTimes.push({url: String(url), method: (opts && opts.method) || 'GET', at: Date.now()});
    return orig(url, opts);
  };
  return 'bridge-ok';
})()
"""
check("B0 fetch 拦截桥注入", ev(INJECT) == "bridge-ok")

# 连接 PC（手动路径）
ev("document.getElementById('linkHost').value = '127.0.0.1:%d';" % PORT2)
ev("document.getElementById('linkToken').value = '%s';" % TOKEN2)
ev("document.getElementById('btnConnect').click()")
time.sleep(1.8)

# 远端任务在页面内的 id 带 pc- 前缀（mapRemoteTask 防本地冲突）
_dbg = ev("JSON.stringify({cards: document.querySelectorAll('#projectList .project-card').length,"
          " first: (document.querySelector('#projectList .project-card')||{getAttribute:()=>null}).getAttribute('data-project'),"
          " st: window.PulseLink.status().connected})")
print("B 诊断:", _dbg)
tid_run2 = "pc-" + next(t.id for t in win2.tasks if t.status == "running")
tid_done2 = "pc-" + next(t.id for t in win2.tasks if t.status == "done")
tid_queued2 = "pc-" + next(t.id for t in win2.tasks if t.status == "queued")

# B1 running 任务抽屉有「暂停」按钮
ev("document.querySelector('#projectList [data-project=%s]').click()" % json.dumps(tid_run2))
time.sleep(0.3)
btns = ev("JSON.stringify(Array.from(document.querySelectorAll('#sheetBody [data-cmd-action]')).map(b => ({a: b.getAttribute('data-cmd-action'), t: b.textContent})))")
bl = json.loads(btns)
check("B1 running 任务抽屉显示「暂停任务」",
      len(bl) == 1 and bl[0]["a"] == "pause" and "暂停" in bl[0]["t"], btns)

# B2 点击 → POST /api/command 发出
ev("window.__reqTimes.length = 0")
ev("document.querySelector('#sheetBody [data-cmd-action]').click()")
time.sleep(0.8)
reqs = json.loads(ev("JSON.stringify(window.__reqTimes.map(x => x.method + ' ' + x.url.split('?')[0]))"))
check("B2 点击按钮发出 POST /api/command",
      any(r.startswith("POST http://127.0.0.1:%d/api/command" % PORT2) for r in reqs), reqs[-2:])

# B3 命令回执 toast
toast_txt = ev("var t=document.getElementById('toast'); t ? t.textContent : ''")
check("B3 命令成功回执 toast", "已提交暂停" in toast_txt, toast_txt)

# B4 PC 端真正应用（tick 后快照 paused）→ 手机刷新后抽屉状态更新
win2.tick(force=True)
app.processEvents()
time.sleep(3.0)  # _onCmdResult 调度的 2.5s 后全量刷新
_d = ev("JSON.stringify({rev: window.PulseLink.rev, sync: window.PulseLink.lastSync, err: window.PulseLink.lastError})")
print("B4 诊断:", _d)
print("队列 qsize:", win2.cmd_source._q.qsize(), "| engine.extra:", len(win2.engine.extra_sources))
_pc_status = next((t.status for t in win2.tasks if t.id == tid_run2[3:]), "?")
print("B4 PC端状态:", _pc_status)
card_txt = ev("var c=document.querySelector('#projectList [data-project=%s]'); c ? c.innerText.replace(/\\s+/g,' ') : 'GONE'" % json.dumps(tid_run2))
check("B4 命令应用后手机端状态同步为 paused", "已暂停" in card_txt, card_txt[:80])

# B5 done 任务 → 「重新执行」
ev("document.querySelector('#projectList [data-project=%s]').click()" % json.dumps(tid_done2))
time.sleep(0.3)
btns = json.loads(ev("JSON.stringify(Array.from(document.querySelectorAll('#sheetBody [data-cmd-action]')).map(b => b.getAttribute('data-cmd-action')))"))
check("B5 done 任务抽屉显示「重新执行」", btns == ["retry"], btns)

# B6 queued 任务 → 无命令按钮
ev("document.querySelector('#projectList [data-project=%s]').click()" % json.dumps(tid_queued2))
time.sleep(0.3)
btns = ev("document.querySelectorAll('#sheetBody [data-cmd-action]').length")
check("B6 queued 任务抽屉无命令按钮", btns == 0, btns)
# closeSheet 为 IIFE 内部函数，不暴露：抽屉切换由 openSheet 覆盖，无需显式关闭

# B7 未连接态：断开后抽屉无命令按钮（本地任务走本地渲染）
ev("document.getElementById('btnDisconnect').click()")
time.sleep(0.6)
ev("document.querySelector('#projectList .project-card').click()")
time.sleep(0.3)
btns = ev("document.querySelectorAll('#sheetBody [data-cmd-action]').length")
check("B7 本地任务抽屉无命令按钮", btns == 0, btns)

try:
    ws.close()
except Exception:
    pass
proc.terminate()
win2.close()

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
