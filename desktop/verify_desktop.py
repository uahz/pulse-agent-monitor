# -*- coding: utf-8 -*-
"""
PULSE · v3.0.0 轻量单窗版验证

窗口构建与列表、内嵌二维码内容一致性、统计摘要、模拟推进、
事件驱动新增任务追加行、--source none 冻结、手机命令应用后行刷新。

用法：QT_QPA_PLATFORM=offscreen python3.12 verify_desktop.py
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + str(detail)[:110]) if detail else ""))


app = QApplication(sys.argv)
from pulse_core import APP_VER, summarise
from pulse_desktop import DesktopWindow

# D1 窗口构建 + 12 行列表
win = DesktopWindow()
win.live = False
win.engine.simulate = False  # 冻结模拟，状态确定
app.processEvents()
check("D1 窗口构建并渲染 12 行任务", win.list.count() == 12, "rows=%d" % win.list.count())

# D2 二维码内容与配对地址一致（解码）
pm = win.qr.pixmap()
check("D2 内嵌二维码非空", pm is not None and not pm.isNull())
try:
    from PIL import Image
    import zxingcpp
    img = pm.toImage()
    img.save("/tmp/p4_qr_check.png")
    res = zxingcpp.read_barcodes(Image.open("/tmp/p4_qr_check.png").convert("L"))
    check("D3 二维码可解码且内容 == 配对地址",
          bool(res) and res[0].text.strip() == win.pair.url().strip(),
          res[0].text[:70] if res else "FAILED")
except ImportError:
    check("D3 二维码可解码（跳过：缺 zxingcpp）", True, "skipped")

# D4 统计摘要与 summarise 一致
s = summarise(win.tasks)
check("D4 统计摘要正确",
      ("共 %d" % s["total"]) in win.stat.text() and ("整体 %d%%" % s["completion_rate"]) in win.stat.text(),
      win.stat.text())

# D5 地址与 token 展示
check("D5 配对地址展示含 token",
      win.pair.state.token in win.addr.text() and "本机持久化" in win.token_lb.text())

# D6 手机命令应用后行刷新（暂停 → 行状态更新）
tid = next(t.id for t in win.tasks if t.status == "running")
win.cmd_source.push({"type": "task_paused", "task_id": tid, "reason": "验证暂停"})
win.tick(force=True)
app.processEvents()
t = next(t for t in win.tasks if t.id == tid)
check("D6 命令暂停应用且列表行刷新", t.status == "paused", t.status)

# D7 事件驱动新增任务追加行
n0 = win.list.count()
win.engine.source = None
win.cmd_source.push({"type": "task_started", "task_id": "AGT-DT01", "name": "单窗版事件任务",
                     "agent": "Coder", "model": "Claude-3.5", "steps": ["甲", "乙"]})
win.tick(force=True)
app.processEvents()
check("D7 事件新建任务追加列表行", win.list.count() == n0 + 1
      and any(t.id == "AGT-DT01" for t in win.tasks), "rows=%d" % win.list.count())

# D8 配对服务快照含新任务
win.pair.publish(win.tasks)
code, body = get_ok = 0, {}
try:
    with urllib.request.urlopen("http://127.0.0.1:%d/api/tasks?token=%s" % (win.pair.port, win.pair.state.token), timeout=8) as r:
        body = json.loads(r.read().decode())
    code = 200
except Exception:
    pass
check("D8 /api/tasks 快照包含事件新任务", code == 200
      and any(x["id"] == "AGT-DT01" for x in body.get("tasks", [])))

# D9 --source none 冻结
win.close()
win2 = DesktopWindow(source="none")
win2.live = False
win2.engine.simulate = False
p0 = sum(t.progress for t in win2.tasks)
win2.tick(force=True)
p1 = sum(t.progress for t in win2.tasks)
check("D9 --source none 冻结数据", p0 == p1, "%d -> %d" % (p0, p1))

# D10 默认模式模拟推进（无冻结）
win3 = DesktopWindow()
p0 = sum(t.progress for t in win3.tasks)
win3.tick(force=True)
p1 = sum(t.progress for t in win3.tasks)
check("D10 默认模拟推进仍工作", p1 > p0, "%d -> %d" % (p0, p1))
check("D11 版本号 3.0.0", APP_VER == "3.0.0", APP_VER)
win2.close()
win3.close()

passed = sum(1 for _, ok, _ in RESULTS if ok)
total = len(RESULTS)
print("")
print("总计 %d 项 | 通过 %d | 失败 %d" % (total, passed, total - passed))
for name, ok, det in RESULTS:
    if not ok:
        print("  FAILED:", name, "|", det)
print("E2E_DONE" if passed == total else "E2E_FAILED")
sys.exit(0 if passed == total else 1)
