#!/usr/bin/env python3.12
# -*- coding: utf-8 -*-
"""PULSE v1.4.0 移动端端到端验证：Chromium 加载 APK 内真实 index.html，
注入与 MainActivity.NativeBridge 行为一致的模拟桥，请求 PC v2.0.0 真实服务。"""
import base64
import json
import os
import shutil
import subprocess
import time
import urllib.request

import websocket

# 用法：
#   1) 构建 APK 后解出页面：unzip -o PULSE_v1.4.0.apk 'assets/*' -d /tmp/pulse_e2e
#      cp /tmp/pulse_e2e/assets/index.html /tmp/pulse_e2e/index.html
#      cp -r /tmp/pulse_e2e/assets/fonts /tmp/pulse_e2e/fonts
#   2) 启动 PC 服务并导出配对信息：
#      python3.12 pulse_studio.py --pair-info /tmp/pulse_live_info.json \
#        --pair-qr /tmp/pulse_pair_qr.png --serve-seconds 240
#   3) python3.12 verify_link.py --info /tmp/pulse_live_info.json --qr /tmp/pulse_pair_qr.png
import argparse

_ap = argparse.ArgumentParser(description="PULSE v1.4.0 扫码连接 PC 端到端验证")
_ap.add_argument("--page-dir", default="/tmp/pulse_e2e", help="含 index.html + fonts/ 的页面目录")
_ap.add_argument("--info", default="/tmp/pulse_live_info.json", help="PC 服务导出的配对 JSON")
_ap.add_argument("--qr", default="", help="PC 服务导出的二维码 PNG（可选，用于解码验证）")
_ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)),
                 help="截图/报告输出目录（默认脚本所在目录，便于任意路径 clone 后直接运行）")
_ap.add_argument("--cdp-port", type=int, default=9333)
_a = _ap.parse_args()
ROOT = _a.page_dir
OUT = _a.out
INFO = _a.info
QR = _a.qr
PORT = _a.cdp_port

info = json.load(open(INFO, encoding="utf-8"))
HOST = info["host"]
PORT_PC = str(info["port"])
TOKEN = info["token"]
PAIR_URL = info["url"]

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + ("  | " + str(detail)[:180] if detail else ""))


def chromium():
    for n in ("chromium", "chromium-browser", "google-chrome"):
        p = shutil.which(n)
        if p:
            return p
    raise RuntimeError("未找到 Chromium")


proc = subprocess.Popen([
    chromium(), "--headless=new", "--no-sandbox", "--disable-gpu",
    "--disable-dev-shm-usage", "--disable-web-security",
    "--allow-file-access-from-files", "--remote-allow-origins=*",
    "--remote-debugging-port=%d" % PORT,
    "--user-data-dir=" + os.path.join(ROOT, ".chrome-profile"),
    "--window-size=440,940", "about:blank",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

for _ in range(60):
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % PORT, timeout=1).read()
        break
    except Exception:
        time.sleep(0.25)
else:
    raise RuntimeError("Chromium CDP 未就绪")

req = urllib.request.Request(
    "http://127.0.0.1:%d/json/new?about:blank" % PORT, method="PUT")
tab = json.loads(urllib.request.urlopen(req, timeout=5).read())
ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=30)
_seq = [0]


def cmd(method, params=None, timeout=30):
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


def ev(js, await_promise=False):
    r = cmd("Runtime.evaluate", {
        "expression": js, "returnByValue": True, "awaitPromise": await_promise})
    if "exceptionDetails" in r:
        raise RuntimeError("JS 异常: " + json.dumps(r["exceptionDetails"], ensure_ascii=False)[:500])
    return r.get("result", {}).get("value")


def shot(name):
    r = cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    path = os.path.join(OUT, name)
    open(path, "wb").write(base64.b64decode(r["data"]))
    print("SHOT " + path)


def wait_for(js, expect, secs=12):
    t0 = time.time()
    while time.time() - t0 < secs:
        try:
            if ev(js) == expect:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


cmd("Page.enable")
cmd("Runtime.enable")
cmd("Emulation.setDeviceMetricsOverride", {
    "width": 412, "height": 915, "deviceScaleFactor": 2, "mobile": True})

# 与 MainActivity.java 的 NativeBridge 契约一致：httpGet 在子线程取数后回调 _onData / _onError
BRIDGE = """
window.Android = {
  getVersion: function(){ return '1.4.0'; },
  vibrate: function(){}, toast: function(){},
  httpGet: function(url){
    fetch(url, {cache:'no-store'})
      .then(function(r){
        if(!r.ok){ window.PulseLink._onError('HTTP ' + r.status); return null; }
        return r.text();
      })
      .then(function(t){ if(t) window.PulseLink._onData(t); })
      .catch(function(e){ window.PulseLink._onError(String(e)); });
  }
};
"""
cmd("Page.addScriptToEvaluateOnNewDocument", {"source": BRIDGE})
cmd("Page.navigate", {"url": "file://" + ROOT + "/index.html"})
wait_for("(window.PulseLink && document.readyState==='complete') ? 1 : 0", 1)
time.sleep(0.4)

# ---------- T1 初始态（本地演示数据） ----------
init = ev("JSON.stringify({"
          "cards:document.querySelectorAll('#projectList .project-card').length,"
          "remote:document.querySelectorAll('#projectList .is-remote').length,"
          "status:document.getElementById('projectLinkText').textContent,"
          "subtitle:document.getElementById('projectsSubtitle').textContent,"
          "ver:document.querySelector('.ver-tag').textContent,"
          "appver:document.getElementById('appVersion').textContent,"
          "jsqr:typeof window.jsQR,"
          "linkSheet:!!document.getElementById('linkSheet'),"
          "tabbar:!!document.querySelector('.tabbar .nav-glass'),"
          "topbar:!!document.querySelector('.appbar .top-glass')})")
d = json.loads(init)
print("T1", json.dumps(d, ensure_ascii=False))
check("T1 初始为 5 个本地项目", d["cards"] == 5 and d["remote"] == 0, d["cards"])
check("T1 状态显示未连接", "未连接 PC" in d["status"], d["status"])
check("T1 版本 v1.4.0", d["ver"] == "v1.4.0" and d["appver"] == "1.4.0", d["ver"])
check("T1 jsQR 已内联可用", d["jsqr"] == "function", d["jsqr"])
check("T1 连接面板存在", d["linkSheet"] is True)
check("T1 tab bar / 顶栏材质 DOM 未改", d["tabbar"] and d["topbar"])

ev("document.querySelectorAll('.tab')[1].click()")
time.sleep(0.5)
shot("preview-mobile-v140-projects-local.png")

# ---------- T2 连接面板 ----------
ev("document.getElementById('btnOpenLink').click()")
time.sleep(0.3)
check("T2 连接面板可打开", ev("document.getElementById('linkSheet').hidden === false"))
check("T2 手动输入兜底始终可用", ev(
    "!!document.getElementById('linkHost') && !!document.getElementById('linkToken')"))
shot("preview-mobile-v140-link-panel.png")

# ---------- T3 连接真实 PC 服务 ----------
ev("document.getElementById('linkHost').value = %s;"
   "document.getElementById('linkToken').value = %s;"
   "document.getElementById('btnConnect').click();" %
   (json.dumps(HOST + ":" + PORT_PC), json.dumps(TOKEN)))
ok = wait_for("document.querySelectorAll('#projectList .is-remote').length", 12, 15)
check("T3 连接后渲染 PC 的 12 个任务", ok,
      "remote=" + str(ev("document.querySelectorAll('#projectList .is-remote').length")))
time.sleep(0.5)
shot("preview-mobile-v140-link-panel-connected.png")
ev("document.getElementById('btnCloseLink').click()")   # 关面板后再拍项目页
time.sleep(0.3)

conn = ev("JSON.stringify({"
          "cards:document.querySelectorAll('#projectList .project-card').length,"
          "remote:document.querySelectorAll('#projectList .is-remote').length,"
          "status:document.getElementById('projectLinkText').textContent,"
          "subtitle:document.getElementById('projectsSubtitle').textContent,"
          "badges:Array.prototype.map.call(document.querySelectorAll('#projectList .chip-status'),function(x){return x.textContent}),"
          "first:document.querySelector('#projectList .project-card').innerText.replace(/\\s+/g,' ').slice(0,240),"
          "pct:document.querySelector('#projectList .progress-pct').textContent,"
          "overviewPct:document.getElementById('overallPct').textContent,"
          "footnote:document.getElementById('overviewFootnote').textContent,"
          "summary:window.PulseLink.lastData?window.PulseLink.lastData.summary:null,"
          "pcFirst:window.PulseLink.lastData?window.PulseLink.lastData.tasks[0]:null,"
          "err:window.PulseLink.lastError})")
c = json.loads(conn)
print("T4", json.dumps({k: v for k, v in c.items() if k != "first"}, ensure_ascii=False)[:900])
print("T4 first card:", c["first"])
check("T4 项目页 12 张远端卡片", c["cards"] == 12 and c["remote"] == 12)
check("T4 状态显示已连接 PC", "已连接 PC" in c["status"] and "已连接 PC" in c["subtitle"])
check("T4 12 个中文状态徽章", len(c["badges"]) == 12 and all(
    b in ("运行中", "排队中", "待人工确认", "已暂停", "失败", "已完成") for b in c["badges"]),
    sorted(set(c["badges"])))
if c["pcFirst"]:
    check("T4 进度与 PC 数据一致", c["pct"] == str(c["pcFirst"]["progress"]) + "%",
          "%s vs %s" % (c["pct"], c["pcFirst"]["progress"]))
    check("T4 卡片含 Agent / 模型 / Tokens 信息",
          any(k in c["first"] for k in ("步骤", "tokens")) and len(c["first"]) > 40)
if c["summary"]:
    check("T4 概览完成率取 PC 快照", str(c["summary"]["completion_rate"]) == c["overviewPct"],
          "%s vs %s" % (c["overviewPct"], c["summary"]["completion_rate"]))
check("T4 概览脚注标注数据来源", "PC 实时快照" in c["footnote"], c["footnote"])
bar = ev("JSON.stringify({"
         "track:document.querySelector('#projectList .progress-track').getBoundingClientRect().width,"
         "fill:document.querySelector('#projectList .progress-fill').getBoundingClientRect().width,"
         "display:getComputedStyle(document.querySelector('#projectList .progress-fill')).display})")
bd2 = json.loads(bar)
check("T4 进度条填充可见（inline 失效修复）",
      bd2["display"] == "block" and bd2["fill"] > bd2["track"] * 0.5, bd2)
shot("preview-mobile-v140-projects-pc.png")

# ---------- T5 筛选 ----------
f = ev("(function(){"
       "document.querySelector('[data-filter=\\'risk\\']').click();"
       "var n=document.querySelectorAll('#projectList .project-card').length;"
       "document.querySelector('[data-filter=\\'all\\']').click();"
       "return JSON.stringify({risk:n,all:document.querySelectorAll('#projectList .project-card').length,"
       "pcRisk:window.PulseLink.lastData.tasks.filter(function(t){return ['review','paused','failed'].indexOf(t.status)>=0}).length,"
       "pcTotal:window.PulseLink.lastData.tasks.length});})()")
fd = json.loads(f)
print("T5", fd)
check("T5 筛选「有风险」数量与 PC 一致", fd["risk"] == fd["pcRisk"], fd)
check("T5 筛选「全部」恢复 12 张", fd["all"] == 12)

# ---------- T6 远端抽屉 ----------
# 故意先打开连接面板再点项目卡片，验证三个 sheet 互斥
ev("document.getElementById('btnOpenLink').click();"
   "document.querySelector('#projectList .project-card').click()")
time.sleep(0.3)
check("T6 抽屉与连接面板互斥（面板自动关闭）", ev(
    "document.getElementById('linkSheet').hidden===true && "
    "document.getElementById('projectSheet').hidden===false"))
s = ev("JSON.stringify({"
       "open:document.getElementById('projectSheet').hidden===false,"
       "sub:document.getElementById('sheetSub').textContent,"
       "steps:document.querySelectorAll('#sheetBody .step-item').length,"
       "facts:document.querySelectorAll('#sheetBody .remote-fact').length,"
       "logs:document.querySelectorAll('#sheetBody .log-line').length,"
       "readonly:document.getElementById('sheetBody').innerText.indexOf('只读')>=0,"
       "hasStepsTitle:document.getElementById('sheetBody').innerText.indexOf('执行步骤')>=0})")
sd = json.loads(s)
print("T6", json.dumps(sd, ensure_ascii=False))
check("T6 抽屉打开且为远端内容", sd["open"] and sd["hasStepsTitle"], sd["sub"])
check("T6 步骤四态渲染", sd["steps"] > 0, sd["steps"])
check("T6 运行指标 5 项", sd["facts"] == 5, sd["facts"])
check("T6 最近日志渲染", sd["logs"] > 0, sd["logs"])
check("T6 明确标注只读", sd["readonly"] is True)
ov = ev("(function(){var f=document.querySelectorAll('#sheetBody .remote-fact');"
        "return Array.prototype.some.call(f,function(e){return e.scrollWidth>e.clientWidth+2;});})()")
check("T6 指标卡长文本无溢出重叠", ov is False, "overflow=" + str(ov))
shot("preview-mobile-v140-sheet.png")
ev("document.getElementById('btnCloseSheet').click()")

# ---------- T7 概览同步 ----------
ev("document.querySelectorAll('.tab')[0].click()")
time.sleep(0.3)
o = ev("JSON.stringify({remote:document.querySelectorAll('#overviewProjects .is-remote').length,"
       "pct:document.getElementById('overallPct').textContent,"
       "footnote:document.getElementById('overviewFootnote').textContent})")
od = json.loads(o)
check("T7 概览项目列表同步为 PC 卡片", od["remote"] > 0, od)
shot("preview-mobile-v140-overview.png")

# ---------- T8 断线回退 + 迟到响应竞态 ----------
ev("document.querySelectorAll('.tab')[1].click();"
   "document.querySelector('#projectLinkStatus [data-link-action]').click()")
time.sleep(0.4)
b1 = ev("JSON.stringify({cards:document.querySelectorAll('#projectList .project-card').length,"
        "remote:document.querySelectorAll('#projectList .is-remote').length,"
        "status:document.getElementById('projectLinkText').textContent,"
        "footnote:document.getElementById('overviewFootnote').textContent})")
bd = json.loads(b1)
print("T8 immediate", json.dumps(bd, ensure_ascii=False))
check("T8 断开后立即回退 5 个本地项目", bd["cards"] == 5 and bd["remote"] == 0, bd)
check("T8 状态回到未连接", "未连接 PC" in bd["status"], bd["status"])
check("T8 脚注回到本地演示", "本地离线演示" in bd["footnote"], bd["footnote"])
time.sleep(6)  # 等待任何在途响应返回，验证不会「断开又自动连回来」
still = ev("document.querySelectorAll('#projectList .is-remote').length")
check("T8 6 秒后仍为本地数据（迟到响应被抑制）", still == 0, "remote=" + str(still))

# ---------- T9 内联 jsQR 对真实二维码解码 ----------
if QR and os.path.exists(QR):
    b64 = base64.b64encode(open(QR, "rb").read()).decode()
    js = ("(async function(){var img=new Image();img.src='data:image/png;base64," + b64 + "';"
          "await new Promise(function(res,rej){img.onload=res;img.onerror=rej;});"
          "var c=document.createElement('canvas');c.width=img.width;c.height=img.height;"
          "var x=c.getContext('2d');x.drawImage(img,0,0);"
          "var d=x.getImageData(0,0,c.width,c.height);"
          "var r=window.jsQR(d.data,c.width,c.height);return r?r.data:null;})()")
    decoded = ev(js, await_promise=True)
    print("T9 decoded:", decoded)
    check("T9 内联 jsQR 解出配对地址", bool(decoded) and decoded.strip() == PAIR_URL.strip(),
          decoded)
else:
    print("SKIP T9（未提供二维码，jsQR 可用性已在 T1 验证）")

# ---------- 汇总 ----------
passed = sum(1 for _, ok, _ in results if ok)
print("\nRESULT %d/%d" % (passed, len(results)))
for n, ok, det in results:
    if not ok:
        print("  FAILED:", n, "|", det)
os.makedirs(OUT, exist_ok=True)
json.dump({"passed": passed, "total": len(results),
           "items": [{"name": n, "ok": ok, "detail": str(det)} for n, ok, det in results]},
          open(os.path.join(OUT, "verify_link_result.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
ws.close()
proc.terminate()
print("E2E_DONE")
