# -*- coding: utf-8 -*-
"""
PULSE · 扫码连接最小闭环验证脚本
验证：服务启动 / 健康检查 / 任务快照契约 / token 鉴权 / CORS / 实时更新 / 二维码可解码且内容正确
运行：python3.12 verify_pair.py
"""
import json
import sys
import urllib.error
import urllib.request

from pulse_agent_console import seed_tasks
from pulse_pair_server import API_PATH, HEALTH_PATH, PairServer, save_qr_png

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  [OK] " if cond else "  [!!] ") + name + (" · " + str(detail) if detail else ""))


def req(url, method="GET"):
    r = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8")


def decode_qr(path):
    try:
        import zxingcpp
        from PIL import Image
        img = Image.open(path).convert("L")
        res = zxingcpp.read_barcodes(img)
        if res:
            return True, res[0].text
        return False, "未识别到二维码"
    except Exception as e:
        return False, "解码器不可用: %s" % e


def main():
    pair = PairServer(port=8790)
    ok = pair.start()
    check("服务启动", ok and not pair.error, pair.error or "port=%d" % pair.port)
    tasks = seed_tasks()
    pair.publish(tasks)
    try:
        base = "http://127.0.0.1:%d" % pair.port
        s, h, b = req(base + HEALTH_PATH)
        j = json.loads(b)
        check("health 返回 200", s == 200)
        check("health 标记需要 token", j.get("token_required") is True)
        check("health 版本 1.3.0", j.get("version") == "1.3.0")

        url = "http://127.0.0.1:%d%s?token=%s" % (pair.port, API_PATH, pair.state.token)
        s, h, b = req(url)
        j = json.loads(b)
        check("tasks 返回 200", s == 200)
        check("Content-Type 为 JSON", "application/json" in h.get("Content-Type", ""))
        check("CORS 允许跨端读取", h.get("Access-Control-Allow-Origin") == "*")
        check("响应禁用缓存", "no-store" in h.get("Cache-Control", ""))
        check("任务数 = 12", len(j.get("tasks", [])) == 12, len(j.get("tasks", [])))
        check("summary.total = 12", j.get("summary", {}).get("total") == 12)

        need = ["id", "name", "agent", "model", "status", "status_label", "progress",
                "steps", "steps_done", "steps_total", "elapsed", "elapsed_text",
                "tokens", "priority", "started", "updated", "logs"]
        t0 = j["tasks"][0]
        check("跨端契约字段齐全", all(k in t0 for k in need), [k for k in need if k not in t0])
        check("steps 含 label/state", all("label" in x and "state" in x for x in t0["steps"]))
        check("server.token 与本机一致", j.get("server", {}).get("token") == pair.state.token)
        check("含中文状态标签", bool(t0.get("status_label")))

        s1, _, _ = req(base + API_PATH + "?token=wrongtoken")
        s2, _, _ = req(base + API_PATH)
        check("错误 token -> 401", s1 == 401)
        check("缺失 token -> 401", s2 == 401)

        s3, _, _ = req(base + "/nope")
        s4, h4, _ = req(base + API_PATH, "OPTIONS")
        check("未知路径 -> 404", s3 == 404)
        check("OPTIONS -> 204 且带 CORS", s4 == 204 and h4.get("Access-Control-Allow-Origin") == "*")

        tasks[0].progress = 99
        pair.publish(tasks)
        _, _, b2 = req(url)
        check("快照随 tick 实时更新", json.loads(b2)["tasks"][0]["progress"] == 99)
        _, _, bh = req(base + HEALTH_PATH)
        check("请求计数递增", json.loads(bh).get("requests", 0) >= 2)
    finally:
        pair.stop()

    # 二维码：用本次实例的 URL 现生成现解码，完全自洽，不依赖外部快照文件
    expected = "http://127.0.0.1:%d%s?token=%s" % (pair.port, API_PATH, pair.state.token)
    qr_path = "/tmp/pulse_verify_qr.png"
    try:
        save_qr_png(expected, qr_path)
        qr_ok, qr_text = decode_qr(qr_path)
    except Exception as e:
        qr_ok, qr_text = False, str(e)
    check("二维码可解码", qr_ok, qr_text[:72] if qr_text else "")
    check("二维码内容 == 本次配对地址", qr_ok and qr_text.strip() == expected.strip(), expected)

    print("\n结果：%d 通过 / %d 失败" % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
