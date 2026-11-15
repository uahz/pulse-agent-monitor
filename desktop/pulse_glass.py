# -*- coding: utf-8 -*-
"""
PULSE · 液态玻璃材质引擎与悬浮窗（v2.0.0）

材质依据 Apple WWDC「Liquid Glass」+ 流体界面原则：
  - 半透明玻璃（translucency）+ 背后内容的模糊透射（backdrop blur）
  - 镜面高光边缘（specular rim）：上缘亮、下缘次亮、中段收敛
  - 内高光 / 光源跟随（vibrancy、light-following sheen）
  - 折射感：边缘内侧一圈低饱和彩色微光
  - 大圆角连续曲面、柔和外阴影
  - 弹簧物理动效：展开 QEasingCurve.OutBack（响应约 420ms），
    淡入 OutCubic 220ms；reduced-motion 时禁用弹性与漂移

Qt Widgets 无原生 backdrop-filter，因此透射层用两种手段合成：
  1) 顶层悬浮窗：显示前抓取桌面内容 → 缩放近似高斯模糊 → 低透明度叠底；
     抓不到有效画面（纯色/离屏）时降级为程序化 Aurora 彩色光晕。
  2) 主界面玻璃卡片：Qt 子控件天然叠加在父级 Aurora 背景之上，
     直接绘制半透明玻璃表面即可透出底光，无需抓屏。

对外:
  paint_glass_surface()  通用玻璃表面（渐变/镜面边/内高光/折射）
  paint_aurora()         程序化氛围光晕底
  GlassCard             主界面可复用玻璃卡片容器
  GlassOverlay          可拖拽 / 折叠 / 置顶的液态玻璃悬浮窗
"""
import math

from PySide6.QtCore import (
    Qt, QPointF, QRectF, QTimer, QVariantAnimation, QEasingCurve,
    QPropertyAnimation, Signal, QSize,
)
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush, QLinearGradient,
    QRadialGradient, QPixmap, QImage, QFont, QGuiApplication, QPolygonF,
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QMenu, QApplication,
)

from pulse_core import (
    T, C, STATUS, summarise, now_str, fmt_elapsed,
    f_cn, f_bold, f_display, f_mono,
)


def _c(h, a=255):
    col = QColor(h)
    col.setAlpha(int(a))
    return col


def _global_pos(e):
    """兼容 PySide6 6.x（globalPosition）与旧版（globalPos）。"""
    try:
        return e.globalPosition().toPoint()
    except Exception:
        return e.globalPos()


def _local_pos(e):
    try:
        return e.position()
    except Exception:
        return e.posF()


def rounded_path(rect, radius):
    p = QPainterPath()
    p.addRoundedRect(QRectF(rect), float(radius), float(radius))
    return p


# ---------------------------------------------------------------- 氛围光晕
_AURORA_BLOBS = [
    # (相对 cx, 相对 cy, 相对半径, 颜色, 峰值 alpha, 漂移速度, 相位)
    (0.14, 0.08, 0.90, "#22C55E", 148, 0.55, 0.0),
    (0.90, 0.16, 0.82, "#38BDF8", 168, 0.42, 1.7),
    (0.74, 0.94, 0.92, "#A78BFA", 156, 0.34, 3.1),
    (0.06, 0.84, 0.66, "#F472B6", 78, 0.63, 4.6),
]


def paint_aurora(p, rect, phase=0.0, strength=1.0, dark_base="#080D19"):
    """程序化流动光晕：多团轻量径向渐变，模拟玻璃背后的彩色世界。"""
    p.save()
    p.setPen(Qt.NoPen)
    # 深色底，保证光晕有依附
    p.fillRect(QRectF(rect), QColor(dark_base))
    r = QRectF(rect)
    for cx, cy, rad, color, alpha, speed, ph in _AURORA_BLOBS:
        dx = math.sin(phase * speed + ph) * r.width() * 0.07
        dy = math.cos(phase * speed * 0.8 + ph) * r.height() * 0.06
        c = QPointF(r.left() + r.width() * cx + dx, r.top() + r.height() * cy + dy)
        radius = max(r.width(), r.height()) * rad
        g = QRadialGradient(c, radius)
        g.setColorAt(0.0, _c(color, alpha * strength))
        g.setColorAt(0.45, _c(color, alpha * strength * 0.42))
        g.setColorAt(1.0, _c(color, 0))
        p.setBrush(QBrush(g))
        p.drawRect(r)
    p.restore()


def blur_pixmap(pm, passes=3, downscale=0.10):
    """缩放近似的高斯模糊：大幅降采样再平滑放大，成本低、观感柔和。"""
    if pm is None or pm.isNull():
        return None
    w, h = pm.width(), pm.height()
    if w < 2 or h < 2:
        return None
    small_w = max(2, int(w * downscale))
    small_h = max(2, int(h * downscale))
    cur = pm.scaled(QSize(small_w, small_h), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    for _ in range(max(0, passes - 1)):
        cur = cur.scaled(QSize(max(2, small_w // 2), max(2, small_h // 2)),
                         Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return cur.scaled(QSize(w, h), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def desktop_variance(pm):
    """判断抓屏是否为有效画面：把图缩到 24x24 求亮度标准差，纯色返回 ~0。"""
    if pm is None or pm.isNull():
        return 0.0
    img = pm.toImage().scaled(QSize(24, 24), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    vals = []
    for y in range(24):
        for x in range(24):
            c = img.pixelColor(x, y)
            vals.append(0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue())
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))


def grab_desktop_backdrop(size):
    """在悬浮窗尚未显示时抓取桌面，返回模糊后的 pixmap；无效则 None。"""
    try:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None
        pm = screen.grabWindow(0)
        if pm.isNull():
            return None
        pm = pm.scaled(QSize(size.width(), size.height()),
                       Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        # 居中裁剪
        x = max(0, (pm.width() - size.width()) // 2)
        y = max(0, (pm.height() - size.height()) // 2)
        pm = pm.copy(x, y, size.width(), size.height())
        if desktop_variance(pm) < 6.0:
            return None
        return blur_pixmap(pm, passes=3, downscale=0.12)
    except Exception:
        return None


# ---------------------------------------------------------------- 玻璃表面
def paint_glass_surface(p, path, rect, *, light=None, accent=None,
                        base_alpha=150, gloss=1.0, rim=True, sheen=True):
    """在已裁剪/未裁剪的 painter 上绘制液态玻璃表面。调用方须开启抗锯齿。

    base_alpha 决定玻璃「实」的程度：越小越透（透出底下 Aurora）。
    light 为局部坐标 QPointF，指定光源位置（默认顶部偏左）。
    """
    r = QRectF(rect)
    accent = accent or T["cyan"]

    # 1) 深色玻璃基底（半透明，让底光透出）
    p.fillPath(path, _c("#0A1222", base_alpha))

    # 2) 主体光泽：左上偏白、右下偏冷色，形成连续曲面反射
    gloss_g = QLinearGradient(r.topLeft(), r.bottomRight())
    gloss_g.setColorAt(0.0, _c("#FFFFFF", int(52 * gloss)))
    gloss_g.setColorAt(0.34, _c("#DCEBFF", int(20 * gloss)))
    gloss_g.setColorAt(0.72, _c("#93B4FF", int(10 * gloss)))
    gloss_g.setColorAt(1.0, _c(accent, int(30 * gloss)))
    p.fillPath(path, QBrush(gloss_g))

    # 3) 内高光：光源跟随（鼠标移动 / 默认顶部），营造 liquid 感
    if sheen:
        lp = light if light is not None else QPointF(r.left() + r.width() * 0.30,
                                                     r.top() + r.height() * 0.02)
        rad = max(r.width(), r.height()) * 0.85
        sg = QRadialGradient(QPointF(lp), rad)
        sg.setColorAt(0.0, _c("#FFFFFF", int(46 * gloss)))
        sg.setColorAt(0.35, _c("#E8F4FF", int(14 * gloss)))
        sg.setColorAt(1.0, _c("#FFFFFF", 0))
        p.fillPath(path, QBrush(sg))

    # 4) 顶部弧形镜面反射带
    if gloss > 0.1:
        band = QLinearGradient(QPointF(r.left(), r.top()),
                               QPointF(r.left(), r.top() + min(58.0, r.height() * 0.32)))
        band.setColorAt(0.0, _c("#FFFFFF", int(34 * gloss)))
        band.setColorAt(1.0, _c("#FFFFFF", 0))
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(r.left(), r.top(), r.width(), min(58.0, r.height() * 0.32)),
                   QBrush(band))
        p.restore()

    # 5) 折射：边缘内侧一圈低饱和彩色微光
    inner = rounded_path(r.adjusted(2.2, 2.2, -2.2, -2.2), max(2.0, _radius_of(r) - 2))
    p.save()
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(_c(accent, 26), 1.0))
    p.drawPath(inner)
    p.restore()

    # 6) 镜面高光边缘：上缘亮白、中段收敛、下缘次亮冷光
    if rim:
        rim_g = QLinearGradient(QPointF(r.left(), r.top()), QPointF(r.left(), r.bottom()))
        rim_g.setColorAt(0.00, _c("#FFFFFF", 224))
        rim_g.setColorAt(0.10, _c("#FFFFFF", 104))
        rim_g.setColorAt(0.48, _c("#FFFFFF", 16))
        rim_g.setColorAt(0.86, _c("#8FC4FF", 46))
        rim_g.setColorAt(1.00, _c("#C9E2FF", 168))
        p.save()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QBrush(rim_g), 1.6))
        p.drawPath(path)
        p.restore()


def _radius_of(r):
    return min(r.width(), r.height()) * 0.14


def paint_soft_shadow(p, rect, radius, layers=7, spread=2.6, alpha=9):
    """多层低透明度圆角矩形叠加，模拟透明窗口拿不到的系统柔和外阴影。"""
    p.save()
    p.setPen(Qt.NoPen)
    for i in range(layers, 0, -1):
        d = i * spread
        sh = QRectF(rect).adjusted(-d, -d + d * 0.55, d, d + d * 0.55)
        p.setBrush(_c("#000000", alpha))
        p.drawRoundedRect(sh, radius + d, radius + d)
    p.restore()


# ---------------------------------------------------------------- 玻璃卡片
class GlassCard(QFrame):
    """主界面用的玻璃卡片容器：自绘玻璃表面，内部可放常规布局与子控件。

    底层透射来自父级的 Aurora 背景，因此只画半透明玻璃表面，无需抓屏。
    """
    def __init__(self, parent=None, radius=22, accent=None, base_alpha=118,
                 gloss=1.0, padding=0):
        super().__init__(parent)
        self.radius = radius
        self.accent = accent
        self.base_alpha = base_alpha
        self.gloss = gloss
        self._light = None
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet("GlassCard{background:transparent;border:0;}")
        # 不自动建布局：部分卡片纯自绘，部分由外部 setLayout；
        # 自动布局会与外部布局冲突（Qt 会打印 "already has a layout"）。
        # padding 仅作为可选：传入时才建立内容布局。
        if padding:
            self.body = QVBoxLayout(self)
            self.body.setContentsMargins(padding, padding, padding, padding)
            self.body.setSpacing(10)

    def set_light(self, pt):
        self._light = pt
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(1, 1, -1, -1)
        path = rounded_path(r, self.radius)
        paint_soft_shadow(p, r, self.radius, layers=5, spread=1.8, alpha=7)
        p.save()
        p.setClipPath(path)
        paint_glass_surface(p, path, r, light=self._light, accent=self.accent,
                            base_alpha=self.base_alpha, gloss=self.gloss)
        p.restore()
        p.end()


# ---------------------------------------------------------------- 环形进度
def draw_ring(p, center, radius, pct, thickness=11, track_alpha=24):
    """圆环进度：自 12 点方向顺时针绘制，线性渐变绿→青。"""
    box = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
    p.save()
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(_c("#FFFFFF", track_alpha), thickness, Qt.SolidLine, Qt.RoundCap))
    p.drawEllipse(center, radius, radius)
    if pct > 0:
        g = QLinearGradient(box.topLeft(), box.bottomRight())
        g.setColorAt(0.0, _c(T["green_hi"], 255))
        g.setColorAt(0.55, _c(T["green"], 255))
        g.setColorAt(1.0, _c(T["cyan"], 255))
        p.setPen(QPen(QBrush(g), thickness, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(box, 90 * 16, -int(360 * min(100, max(0, pct)) / 100.0) * 16)
    p.restore()


def draw_bar(p, rect, pct, color=None, radius=None, track_alpha=22):
    """细进度条。"""
    r = QRectF(rect)
    rad = radius if radius is not None else r.height() / 2.0
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(_c("#FFFFFF", track_alpha))
    p.drawRoundedRect(r, rad, rad)
    if pct > 0:
        fill = QRectF(r)
        fill.setWidth(max(r.height(), r.width() * min(100, max(0, pct)) / 100.0))
        g = QLinearGradient(fill.topLeft(), fill.bottomRight())
        col = color or T["green"]
        g.setColorAt(0.0, _c(col, 210))
        g.setColorAt(1.0, _c(T["green_hi"], 255))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(fill, rad, rad)
    p.restore()


# ---------------------------------------------------------------- 悬浮窗
class GlassOverlay(QWidget):
    """液态玻璃悬浮窗：显示 Agent 整体进度与进行中任务。

    交互：拖拽移动、双击回主界面、光源跟随高光、展开/折叠弹簧动画、
    淡入淡出、右键菜单（置顶 / 减弱动效 / 回主界面 / 关闭）。
    """
    request_show_main = Signal()
    closed_by_user = Signal()

    W = 352
    H_EXPANDED = 452
    H_COLLAPSED = 96
    MARGIN = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.setFixedWidth(self.W)
        self.resize(self.W, self.H_EXPANDED)

        self._tasks = []
        self._summary = {"total": 0, "running": 0, "done": 0,
                         "need_attention": 0, "completion_rate": 0}
        self._expanded = True
        self._reveal = 1.0
        self._phase = 0.0
        self._reduced_motion = False
        self._always_on_top = True
        self._light = None
        self._dragging = False
        self._drag_offset = None
        self._backdrop = None
        self._closing = False

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.OutBack)
        self._anim.valueChanged.connect(self._set_reveal)

        self._aurora_timer = QTimer(self)
        self._aurora_timer.setInterval(60)
        self._aurora_timer.timeout.connect(self._on_aurora_tick)

        self._close_btn = QRectF(0, 0, 0, 0)
        self._fold_btn = QRectF(0, 0, 0, 0)

    # ------------------------------------------------------------ 对外 API
    def set_tasks(self, tasks):
        self._tasks = list(tasks)
        self._summary = summarise(self._tasks)
        self.update()

    def set_reduced_motion(self, on):
        self._reduced_motion = bool(on)
        if on:
            self._aurora_timer.stop()
            self._anim.setDuration(0)
        else:
            self._anim.setDuration(420)
            if self.isVisible():
                self._aurora_timer.start()

    def show_glass(self, pos=None):
        """显示悬浮窗：先在自身不可见时抓一次桌面作透射层，再淡入。"""
        if self.isVisible():
            self.raise_()
            self.activateWindow()
            return
        self._backdrop = grab_desktop_backdrop(QSize(self.W, self.H_EXPANDED))
        if pos is not None:
            self.move(pos)
        else:
            self._place_default()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        if self._reduced_motion:
            self.setWindowOpacity(1.0)
        else:
            fade = QPropertyAnimation(self, b"windowOpacity", self)
            fade.setDuration(220)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.OutCubic)
            fade.start(QPropertyAnimation.DeleteWhenStopped)
            self._fade = fade
        if not self._reduced_motion:
            self._aurora_timer.start()

    def hide_glass(self, notify=True):
        """淡出并隐藏；notify=True 时通知主界面同步开关状态。"""
        if not self.isVisible() or self._closing:
            return
        self._closing = True
        if notify:
            self.closed_by_user.emit()

        def _done():
            self._aurora_timer.stop()
            self.hide()
            self._closing = False

        if self._reduced_motion:
            _done()
        else:
            fade = QPropertyAnimation(self, b"windowOpacity", self)
            fade.setDuration(180)
            fade.setStartValue(self.windowOpacity())
            fade.setEndValue(0.0)
            fade.setEasingCurve(QEasingCurve.InCubic)
            fade.finished.connect(_done)
            fade.start(QPropertyAnimation.DeleteWhenStopped)
            self._fade = fade

    def toggle_expand(self):
        self._expanded = not self._expanded
        start = self._reveal
        end = 1.0 if self._expanded else 0.0
        self._anim.stop()
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setDuration(0 if self._reduced_motion else 420)
        self._anim.start()
        self.update()

    def _place_default(self):
        scr = QGuiApplication.primaryScreen()
        if scr is None:
            self.move(80, 80)
            return
        g = scr.availableGeometry()
        self.move(g.right() - self.W - 40, g.top() + 90)

    # ------------------------------------------------------------ 内部
    def _set_reveal(self, v):
        self._reveal = float(v)
        h = self.H_COLLAPSED + (self.H_EXPANDED - self.H_COLLAPSED) * self._reveal
        self.resize(self.W, int(max(self.H_COLLAPSED, min(self.H_EXPANDED + 14, h))))
        self.update()

    def _on_aurora_tick(self):
        if self._reduced_motion:
            return
        self._phase += 0.022
        self.update()

    def _content_rect(self):
        m = self.MARGIN
        return QRectF(m, m, self.width() - m * 2, self.height() - m * 2)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        r = self._content_rect()
        radius = 30 if self._reveal > 0.5 else 26
        path = rounded_path(r, radius)

        paint_soft_shadow(p, r, radius, layers=8, spread=2.8, alpha=9)

        p.save()
        p.setClipPath(path)
        # 透射底层：程序化 Aurora（保证任何环境都有流动彩色底光）
        paint_aurora(p, r, phase=self._phase, strength=1.0)
        # 真实桌面模糊透射（抓到有效画面时叠加）
        if self._backdrop is not None and not self._backdrop.isNull():
            p.setOpacity(0.34)
            p.drawPixmap(r, self._backdrop, QRectF(self._backdrop.rect()))
            p.setOpacity(1.0)
        # 玻璃表面：降低深色基底不透明度，让彩色光晕真正"透"出来（液态感）
        paint_glass_surface(p, path, r, light=self._light, accent=T["cyan"],
                            base_alpha=118, gloss=1.05)
        p.restore()

        # 内容（按展开/折叠交叉淡入淡出）
        if self._reveal > 0.02:
            p.setOpacity(min(1.0, self._reveal * 1.35))
            self._draw_expanded(p, r)
        if self._reveal < 0.98:
            p.setOpacity(min(1.0, (1.0 - self._reveal) * 1.35))
            self._draw_collapsed(p, r)
        p.setOpacity(1.0)
        p.end()

    # ------------------------------------------------------------ 展开态内容
    def _draw_expanded(self, p, r):
        x, y, w = r.left(), r.top(), r.width()
        pad = 22
        inner = QRectF(r).adjusted(pad, 16, -pad, -14)

        # --- 顶栏：品牌 + LIVE + 折叠/关闭（先定按钮，再按可用宽度排文字）
        p.save()
        self._fold_btn = QRectF(inner.right() - 62, inner.top() + 4, 28, 28)
        self._close_btn = QRectF(inner.right() - 30, inner.top() + 4, 28, 28)
        p.setPen(Qt.NoPen)
        p.setBrush(_c(T["green"], 235))
        p.drawEllipse(QPointF(inner.left() + 5, inner.top() + 13), 4.5, 4.5)
        txt_left = inner.left() + 18
        txt_w = max(60.0, self._fold_btn.left() - txt_left - 10)
        p.setPen(_c("#FFFFFF", 240))
        p.setFont(f_bold(12))
        p.drawText(QRectF(txt_left, inner.top() + 2, txt_w, 22),
                   Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText("PULSE  ·  AGENT 进度", Qt.ElideRight, int(txt_w)))
        p.setFont(f_mono(9, True))
        p.setPen(_c(T["green_soft"], 245))
        p.drawText(QRectF(txt_left, inner.top() + 21, txt_w, 16),
                   Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText("LIVE  每 2 秒刷新", Qt.ElideRight, int(txt_w)))

        for rect, glyph in ((self._fold_btn, "−"), (self._close_btn, "×")):
            p.setPen(Qt.NoPen)
            p.setBrush(_c("#FFFFFF", 20))
            p.drawRoundedRect(rect, 9, 9)
            p.setPen(QPen(_c("#FFFFFF", 150), 1.0))
            p.drawRoundedRect(rect, 9, 9)
            p.setPen(_c("#FFFFFF", 235))
            p.setFont(f_cn(15))
            p.drawText(rect, Qt.AlignCenter, glyph)
        p.restore()

        # --- Hero：大圆环 + 完成率
        top = inner.top() + 48
        ring_c = QPointF(inner.left() + 66, top + 66)
        pct = self._summary["completion_rate"]
        draw_ring(p, ring_c, 54, pct, thickness=11)
        p.save()
        p.setPen(_c("#FFFFFF", 250))
        num_font = f_display(31)
        p.setFont(num_font)
        num_rect = QRectF(ring_c.x() - 54, ring_c.y() - 22, 96, 36)
        p.drawText(num_rect, Qt.AlignRight | Qt.AlignVCenter, str(pct))
        p.setFont(f_bold(14))
        p.setPen(_c(T["green_soft"], 240))
        p.drawText(QRectF(ring_c.x() + 41, ring_c.y() - 22, 20, 30),
                   Qt.AlignLeft | Qt.AlignBottom, "%")
        p.setFont(f_cn(10))
        p.setPen(_c("#E2ECFF", 235))
        p.drawText(QRectF(ring_c.x() - 54, ring_c.y() + 14, 108, 20),
                   Qt.AlignHCenter | Qt.AlignVCenter, "整体完成率")
        p.restore()

        # --- 右侧统计三行
        sx = inner.left() + 138
        stats = [
            ("运行中", self._summary["running"], T["green"]),
            ("已完成", self._summary["done"], T["green_hi"]),
            ("需关注", self._summary["need_attention"], T["amber"]),
        ]
        for i, (label, val, col) in enumerate(stats):
            yy = top + 6 + i * 40
            p.setPen(Qt.NoPen)
            p.setBrush(_c(col, 230))
            p.drawEllipse(QPointF(sx + 4, yy + 11), 3.5, 3.5)
            p.setFont(f_cn(11))
            p.setPen(_c("#B9C9E2", 220))
            p.drawText(QRectF(sx + 16, yy, 80, 22), Qt.AlignVCenter | Qt.AlignLeft, label)
            p.setFont(f_display(17))
            p.setPen(_c("#FFFFFF", 250))
            p.drawText(QRectF(sx + 88, yy - 1, 60, 24), Qt.AlignVCenter | Qt.AlignRight, str(val))

        # --- 分隔
        sep_y = top + 140
        p.setPen(QPen(_c("#FFFFFF", 20), 1.0))
        p.drawLine(QPointF(inner.left(), sep_y), QPointF(inner.right(), sep_y))

        # --- 进行中任务
        p.setFont(f_bold(11))
        p.setPen(_c("#FFFFFF", 235))
        p.drawText(QRectF(inner.left(), sep_y + 10, 140, 20),
                   Qt.AlignVCenter | Qt.AlignLeft, "进行中")
        p.setFont(f_mono(9))
        p.setPen(_c("#8FA4C4", 200))
        p.drawText(QRectF(inner.right() - 90, sep_y + 10, 90, 20),
                   Qt.AlignVCenter | Qt.AlignRight, "%d 项任务" % self._summary["total"])

        running = [t for t in self._tasks if t.status == "running"][:3]
        if not running:
            running = [t for t in self._tasks if t.status not in ("done",)][:3]
        row_y = sep_y + 36
        for t in running:
            p.setFont(f_cn(11))
            p.setPen(_c("#EAF2FF", 240))
            name = t.name
            # 截断过长名称
            fm = p.fontMetrics()
            name = fm.elidedText(name, Qt.ElideRight, int(inner.width() - 40))
            p.drawText(QRectF(inner.left(), row_y, inner.width() - 44, 18),
                       Qt.AlignVCenter | Qt.AlignLeft, name)
            p.setFont(f_mono(9, True))
            p.setPen(_c(T["green_soft"], 235))
            p.drawText(QRectF(inner.right() - 42, row_y, 42, 18),
                       Qt.AlignVCenter | Qt.AlignRight, "%d%%" % t.progress)
            draw_bar(p, QRectF(inner.left(), row_y + 21, inner.width(), 5),
                     t.progress, color=STATUS[t.status][1])
            row_y += 40

        # --- 底部（文案精简到可完整放下，另用 elide 兜底）
        p.setFont(f_mono(9))
        p.setPen(_c("#94AACB", 215))
        foot = "更新 %s  ·  拖动 · 双击返回" % now_str()
        foot_w = inner.width()
        p.drawText(QRectF(inner.left(), inner.bottom() - 18, foot_w, 18),
                   Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(foot, Qt.ElideRight, int(foot_w)))

    # ------------------------------------------------------------ 折叠态内容
    def _draw_collapsed(self, p, r):
        pad = 20
        inner = QRectF(r).adjusted(pad, 10, -pad, -10)
        pct = self._summary["completion_rate"]
        c = QPointF(inner.left() + 28, inner.center().y())
        draw_ring(p, c, 21, pct, thickness=5, track_alpha=30)
        p.save()
        p.setFont(f_bold(12))
        p.setPen(_c("#FFFFFF", 245))
        p.drawText(QRectF(c.x() - 21, c.y() - 12, 42, 24), Qt.AlignCenter, "%d" % pct)
        p.restore()

        self._fold_btn = QRectF(inner.right() - 62, inner.center().y() - 14, 28, 28)
        self._close_btn = QRectF(inner.right() - 30, inner.center().y() - 14, 28, 28)
        txt_left = inner.left() + 60
        txt_w = max(60.0, self._fold_btn.left() - txt_left - 10)
        p.setFont(f_bold(12))
        p.setPen(_c("#FFFFFF", 240))
        p.drawText(QRectF(txt_left, inner.top() + 6, txt_w, 22),
                   Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText("PULSE · AGENT 进度", Qt.ElideRight, int(txt_w)))
        p.setFont(f_cn(10))
        p.setPen(_c(T["green_soft"], 230))
        p.drawText(QRectF(txt_left, inner.top() + 27, txt_w, 18),
                   Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(
                       "完成 %d%%  ·  运行中 %d" % (pct, self._summary["running"]),
                       Qt.ElideRight, int(txt_w)))

        for rect, glyph in ((self._fold_btn, "+"), (self._close_btn, "×")):
            p.setPen(Qt.NoPen)
            p.setBrush(_c("#FFFFFF", 20))
            p.drawRoundedRect(rect, 9, 9)
            p.setPen(QPen(_c("#FFFFFF", 150), 1.0))
            p.drawRoundedRect(rect, 9, 9)
            p.setPen(_c("#FFFFFF", 235))
            p.setFont(f_cn(15))
            p.drawText(rect, Qt.AlignCenter, glyph)

    # ------------------------------------------------------------ 交互
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            lp = QPointF(_local_pos(e))
            if self._close_btn.contains(lp):
                self.hide_glass(True)
                return
            if self._fold_btn.contains(lp):
                self.toggle_expand()
                return
            self._dragging = True
            self._drag_offset = _global_pos(e) - self.frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        self._light = QPointF(_local_pos(e))
        if self._dragging and self._drag_offset is not None:
            self.move(_global_pos(e) - self._drag_offset)
        self.update()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._dragging = False
        self._drag_offset = None
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e):
        self._light = None
        self.update()
        super().leaveEvent(e)

    def mouseDoubleClickEvent(self, e):
        if not self._close_btn.contains(QPointF(_local_pos(e))) and \
           not self._fold_btn.contains(QPointF(_local_pos(e))):
            self.request_show_main.emit()
        super().mouseDoubleClickEvent(e)

    def _context_menu(self, pos):
        m = QMenu(self)
        m.setStyleSheet(
            "QMenu{background:#131E33;color:#EAF2FF;border:1px solid rgba(255,255,255,40);"
            "border-radius:10px;padding:6px;font-family:'Noto Sans CJK SC';font-size:12px;}"
            "QMenu::item{padding:7px 20px;border-radius:6px;}"
            "QMenu::item:selected{background:rgba(56,189,248,55);}")
        a_fold = m.addAction("收起为胶囊" if self._expanded else "展开详情")
        a_fold.triggered.connect(self.toggle_expand)
        a_top = m.addAction("始终置顶")
        a_top.setCheckable(True)
        a_top.setChecked(self._always_on_top)
        a_top.triggered.connect(self._toggle_top)
        a_motion = m.addAction("减弱动效")
        a_motion.setCheckable(True)
        a_motion.setChecked(self._reduced_motion)
        a_motion.triggered.connect(self.set_reduced_motion)
        m.addSeparator()
        a_main = m.addAction("回到主界面")
        a_main.triggered.connect(self.request_show_main.emit)
        a_close = m.addAction("关闭悬浮窗")
        a_close.triggered.connect(lambda: self.hide_glass(True))
        m.exec(self.mapToGlobal(pos))

    def _toggle_top(self, on):
        self._always_on_top = bool(on)
        flags = Qt.FramelessWindowHint | Qt.Tool
        if on:
            flags |= Qt.WindowStaysOnTopHint
        visible = self.isVisible()
        self.setWindowFlags(flags)
        if visible:
            self.show()
