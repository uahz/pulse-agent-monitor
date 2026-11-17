# PULSE · Agent Studio — PC 端设计系统

> 生成方式：ui-ux-pro-max-skill `search.py --design-system` + `--domain style` / `--domain ux`
> 平台约束：**Qt Widgets 原生控件**，不使用 HTML / WebView / 浏览器内核。
> 基础令牌沿用移动端 `PulseApp/design-system/pulse/MASTER.md`（Code dark + run green）。
>
> **版本历史**：第 1–8 节为 v1.0–v1.3.0「Data-Dense Dashboard」旧版记录（保留作回退基线，
> 对应 `pulse_agent_console.py`）。**v2.0.0 起主程序改为 `pulse_studio.py`，见文末第 9 节**——
> 用户判定旧版「像后台管理界面」，已整体重写为品牌化玻璃工作台 + 液态玻璃悬浮窗。

---

## 1. 定位

**用途**：在 PC 桌面查看多个 AI Agent 的任务执行进度、状态、步骤与日志。
**形态**：桌面三栏 —— 固定侧边导航 / 主工作区（KPI + 任务进度表）/ 右侧详情面板。
**风格判定（skill）**：`Data-Dense Dashboard` —— 多 widget、数据表格、KPI 卡片、最小 padding、网格布局、空间高效、最大数据可见性。

## 2. 色板

沿用 MASTER 主色，并按 `Real-Time Monitoring`（skill styles.csv）扩展状态色：

| 角色 | Hex | 用途 |
|---|---|---|
| Background | `#0F172A` | 窗口底色 |
| Surface | `#16223A` / `#1E293B` | 卡片、表格行、面板 |
| Surface-2 | `#243349` | 输入框、进度条轨道、hover |
| Border | `rgba(148,163,184,.14)` | 分隔线 |
| Text | `#F8FAFC` | 主文字 |
| Text-muted | `#94A3B8` | 次要文字 |
| Text-dim | `#64748B` | 弱提示 |
| CTA / Normal | `#22C55E` | 运行、完成、主按钮、进度条 |
| Warning | `#F59E0B` | 待人工确认 |
| Critical | `#EF4444` | 失败 |
| Updating | `#3B82F6` | 暂停 / 信息 |
| Normal-dim | `#4ADE80` | 已完成高亮 |

状态指示为「圆点 + 文字」双通道，不单靠颜色传达（WCAG AA）。

## 3. 排版

- 标题 / 数字 / ID / 日志：`Fira Code`（等宽，`font-variant-numeric: tabular-nums` 等价于等宽字体）
- 正文 / 标签：`Fira Sans`
- 字号：窗口标题 20px、KPI 数值 28px、表头 11px、单元格 12–13px、日志 11px
- 字体文件随程序打包（`resources/fonts/*.ttf`），无运行时网络依赖

## 4. 密度与间距

| 项 | 值 |
|---|---|
| 侧边栏宽 | 232px |
| 详情面板宽 | 340px（可拖动 QSplitter） |
| 表格行高 | 52px |
| 卡片内边距 | 16px |
| 栅格间距 | 12px |
| 默认窗口 | 1440 × 900，最小 1100 × 700 |

## 5. 组件规范

- **侧边栏**：品牌标识 + 主导航（任务进度表 / 运行概览 / 执行日志 / 预警）+ Agent 在线分组 + 版本信息
- **工具栏**：搜索框、状态筛选、Agent 筛选、实时开关、立即刷新、新建任务、导出 CSV
- **KPI 卡片**：4 张等宽，大数值 + 标签 + 同比/占比脚注
- **任务进度表**（核心）：`QTableView` + `QSortFilterProxyModel`
  - 列：任务 ID / 任务名称 / Agent / 状态 / 进度 / 步骤 / 耗时 / Tokens / 更新时间
  - 进度列与状态列用 `QStyledItemDelegate` + `QPainter` 原生绘制（进度条 / 圆点徽章）
  - 表头可点击排序；行 hover 高亮；多选（`ExtendedSelection`）支持批量操作
  - 宽表在窄窗口下由 `QScrollArea` 横向滚动（skill: Table Handling）
- **详情面板**：任务名、状态徽章、Agent/模型、进度大数、步骤清单、日志流、操作按钮
- **状态栏**：总数 / 运行中 / 最后同步 / LIVE 指示 / 数据源说明

## 6. 交互与无障碍（skill UX 域）

- 必须提供筛选（skill 反模式：`No filtering`）
- 键盘可达：`Ctrl+F` 搜索、`F5` 刷新、`Ctrl+E` 导出、`Esc` 清除选择、`Ctrl+Q` 退出；Tab 顺序与视觉顺序一致
- 提供跳转主内容（Skip Link 等价：侧边栏导航可达主表格）
- 批量操作：多选后可批量暂停 / 恢复 / 重试
- 标题层级：h1 页面标题 → h2 分区标题（Qt 中以字号与字重表达）
- 实时更新用 `QTimer` 渐进推进，**不闪烁**；可一键暂停；`prefers-reduced-motion` 等价为「关闭动效」开关
- 焦点环：`2px solid #22C55E`

## 7. 规避的反模式

- Ornate design（花哨装饰）
- No filtering（无筛选）
- Slow updates / No automation → 2s 定时推进 + 状态自动流转
- 仅靠颜色区分状态 → 圆点 + 文字 + 图标三重编码
- 宽表撑破布局 → 横向滚动容器

---

## 8. 实现与验证记录

- **工程**：`pulse_agent_console.py` 单文件（PySide6 / Qt Widgets），`resources/fonts/*.ttf` 由移动版 woff2 转换而来，无运行时网络依赖
- **表格**：`QTableView` + `QAbstractTableModel` + `QSortFilterProxyModel`；进度条 / 状态徽章 / 优先级标记由 `QStyledItemDelegate.paint()` 的 `QPainter` 原生绘制，未使用任何富文本或浏览器渲染
- **实时**：`QTimer` 每 2 秒推进运行中任务（进度 / 耗时 / Tokens / 步骤 / 日志），到达 100% 自动转「已完成」，排队任务按概率出队；LIVE 开关可暂停
- **交互**：搜索、状态筛选、Agent 筛选、表头排序、多选、行选中联动详情、暂停/恢复/重试/标记完成、新建任务、导出 CSV（尊重当前筛选）、预警卡片跳转、Ctrl+F / F5 / Ctrl+E / Ctrl+P / Esc / Ctrl+Q
- **修复记录**：详情面板刷新曾因在 `layoutChanged` 栈内重入 `show_task()` 导致段错误 → 改为 `dataChanged` 刷新 + `QTimer.singleShot(0)` 合并详情刷新；行容器默认 11px margins 曾把步骤文字压成碎片 → 统一 `setContentsMargins(0,0,0,0)`；预警卡片由 `QPushButton` 改为 `QFrame` + `mousePressEvent` 避免文字重叠
- **验证**：offscreen 平台实跑截图 4 个页面；16 项交互自动化检查全部通过；PyInstaller 单文件可执行程序脱离 Python 独立启动并成功渲染
- **桌面交付**：`start.bat` / `start.sh` 一键启动（自动补依赖），`build_exe.bat` / `build_linux.sh` 打包为免 Python 环境的单文件程序

---

## 9. v1.3.0 · 局域网配对（扫码连接手机，第一阶段：可验证最小闭环）

> 目标：安卓端通过扫码连接 PC，查看 PC 端的 Agent 任务进度。
> 本阶段只打通「PC 起服务 → 二维码 → 手机能拉到真实任务 JSON」，**不改任何可见界面**（移动端 tab bar / 顶栏材质 / 卡片样式 / 布局全部保持 v1.2.5 原样），扫码 UI 与数据映射留到下一阶段。

### 架构决策

| 项 | 选择 | 理由 |
|---|---|---|
| 服务形态 | `ThreadingHTTPServer` 绑 `0.0.0.0:8765`（占用自动顺延 +5） | 标准库零新增运行时依赖，Qt 主线程不阻塞 |
| 线程安全 | 主线程 `publish()` 把 tasks 序列化为**不可变 JSON 字符串**后在锁内替换，HTTP 线程只读字符串 | 不与 `QTimer.tick()` 共享可变 `Task` 对象，杜绝竞态 |
| 网络通道 | `NativeBridge.httpGet()`（Java 子线程 `HttpURLConnection` → `evaluateJavascript` 回传） | 绕开 `file://` 页面的跨域 / 明文流量 / 混合内容三重限制；复用已有桥，不引入 WebView 网络白名单 |
| 鉴权 | 每次启动生成一次性 `token`，`/api/tasks?token=` 校验，错误/缺失返回 401 | 避免同网段任意设备读取；`/api/health` 无需 token 便于探测 |
| 二维码 | `segno`（纯 Python 无 C 依赖）→ `QPainter` 画模块矩阵 | 不影响 PyInstaller 单文件打包；同时可导出 PNG |

### 新增文件

- `pulse_pair_server.py`：`PairState` / `PairServer` / `_Handler`、`build_payload()`、`task_to_dict()`、`make_qr_pixmap()`、`save_qr_png()`、`PairDialog`
- `verify_pair.py`：22 项契约验证（服务 / 健康检查 / 字段 / 鉴权 / CORS / 实时更新 / 二维码解码）
- `pulse_agent_console.py`：接入服务、菜单栏「连接手机(M)」+ `Ctrl+M`、`refresh_all()` 同步快照、`closeEvent` 关闭服务、验证参数 `--pair-info / --pair-qr / --pair-shot / --serve-seconds`

### 跨端数据契约（`/api/tasks`）

`{v, generated, server{host,port,token,version}, summary{total,running,done,need_attention,completion_rate}, tasks[]}`
每个 task：`id / name / agent / model / status / status_label / progress / steps[{label,state}] / steps_done / steps_total / elapsed / elapsed_text / tokens / priority / started / updated / logs[]`。
`steps` 保留 `done / active / blocked / todo` 四态，避免压成布尔丢信息；`status_label` 提供中文状态，为下一阶段移动端「项目」页映射预留。

### 验证结果（全部通过）

- 契约脚本 **22/22**；真实 HTTP：12 个任务、字段完整、状态随 tick 实时变化；错误/缺失 token → 401，health → 200，CORS `*`、no-store
- 二维码 PNG（328×328）经 `zxingcpp` **真实解码**，内容与本次服务地址逐字一致
- `verify_pair.py` 与 Chromium E2E：加载 APK 内真实 `index.html` + 模拟 `Android.httpGet`，`PulseLink` 结果 `OK|tasks=12|...|hasBridge=true`
- APK：v2/v3 验签、`zipalign -c`、`unzip -t`、`versionCode=9/1.3.0`、`INTERNET`/`CAMERA` 权限、`usesCleartextTraffic=true`、dex 内含 `httpGet`、内联 JS `node --check` 通过
- 主界面 offscreen 截图比对：仅菜单栏多一项，其余布局无变化

### 下一阶段（未做）

扫码 UI（ZXing core + Camera2）、移动端「项目」页数据映射与状态徽章、断线回退、手动输入地址兜底、真机与 Windows 打包验收。

---

## 9. v2.0.0 重写：品牌化玻璃工作台 + 液态玻璃悬浮窗

> 触发：用户判定 v1.3.0「像后台管理界面，不好看」，要求整体重写，并新增「可开关的悬浮窗显示 Agent 进度，悬浮窗用液态玻璃效果」。
> 依据：Apple WWDC Liquid Glass / 流体界面原则（半透明、透射模糊、镜面高光边缘、光源跟随、弹簧动效、减弱动效）。

### 9.1 设计转向

| 维度 | v1.3.0（旧） | v2.0.0（新） |
|---|---|---|
| 风格判定 | Data-Dense Dashboard | 品牌化工作台 / Consumer-grade Glass |
| 窗口 | 系统边框 + 菜单栏 + 状态栏 | 无边框圆角 + 自定义标题栏 + 自绘阴影 |
| 导航 | 左侧竖栏 + 顶部菜单 | 顶部胶囊分段（工作台/概览/日志/预警） |
| 焦点 | 4 个并排 KPI 数字方块 | 单个 Hero 玻璃卡：大环形完成率 + 一句话状态 + 3 枚统计胶囊 |
| 任务呈现 | 8 列密集表格 + 右侧属性面板 | Bento 卡片流（自适应 1–3 列网格），状态徽章/进度条/步骤/耗时/Tokens |
| 筛选 | 两个下拉框 + 工具栏按钮 | chips 胶囊组 + 圆角搜索框 |
| 背景 | 纯色 `#0F172A` | Aurora 低强度流动光晕（绿/青/紫/粉） |
| 日志 | 等宽黑框终端 | 彩色时间线（圆点 + 玻璃行 + 级别色） |
| 中文字体 | Fira 回退（偏细） | `Noto Sans CJK SC` 优先，Fira 仅用于数字/等宽 |

已移除：左侧竖导航、双行工具栏、KPI 方块阵、8 列表格、右侧详情面板、底部状态栏、面包屑、下拉筛选框。

### 9.2 液态玻璃材质引擎（`pulse_glass.py`）

Qt Widgets 无原生 `backdrop-filter`，用 `QPainter` 分层合成：

1. **透射底层**：悬浮窗显示前 `QScreen.grabWindow(0)` 抓桌面 → 缩放近似高斯模糊（降采样 ×3 + `SmoothTransformation` 放大）→ 低透明度叠底；`desktop_variance()` 判定为纯色/离屏时自动降级。
2. **程序化 Aurora**：4 团径向渐变彩色光斑，按 `phase` 正弦漂移（60ms 刷新），保证任何环境都有流动彩色底光——这是「液态」观感的主要来源。
3. **玻璃表面** `paint_glass_surface()`：深色半透明基底（`base_alpha` 可调）→ 左上偏白/右下偏冷的主体光泽渐变 → 光源跟随径向内高光 → 顶部弧形镜面反射带 → 边缘内侧低饱和彩色折射圈 → **镜面高光边缘**（上缘亮白 224α、中段收敛、下缘冷光，1.6px 渐变描边）。
4. **柔和阴影** `paint_soft_shadow()`：多层低 α 圆角矩形外扩叠加，替代透明窗口拿不到的系统阴影。

`GlassCard`（主界面卡片）与 `GlassOverlay`（悬浮窗）**共用同一套玻璃表面函数**，材质语言统一；前者靠 Qt 子控件天然叠加在父级 Aurora 上透射，后者靠抓屏 + Aurora。

### 9.3 悬浮窗交互

- 主界面标题栏「◈ 悬浮窗」发光开关 / `Ctrl+O`；关闭悬浮窗会回写开关状态
- 拖拽移动、鼠标 hover 时高光跟随（光源跟随 sheen）
- 展开（352×452）/ 折叠胶囊（352×96）切换，`QEasingCurve.OutBack` 弹簧（420ms）；淡入 `OutCubic` 220ms、淡出 `InCubic` 180ms
- 右键菜单：收起/展开、始终置顶、减弱动效、回到主界面、关闭
- 双击回主界面；减弱动效时禁用弹性与 Aurora 漂移（无障碍）
- 内容：大环形完成率 + 运行中/已完成/需关注 + 进行中 Top3 任务细进度条 + 更新时间
- 数据由主窗口 `refresh_all()` 每 2 秒 `set_tasks()` 实时同步，与配对服务同源

### 9.4 文件结构

| 文件 | 职责 |
|---|---|
| `pulse_core.py` | 共享数据核心：`Task` / `seed_tasks()` / 状态枚举 / 设计令牌 / 字体 / `summarise()` |
| `pulse_glass.py` | 液态玻璃引擎 + `GlassCard` + `GlassOverlay` |
| `pulse_studio.py` | 全新主界面（四页 + 标题栏 + 悬浮窗接入）+ 入口 |
| `pulse_pair_server.py` | **未改动**，v1.3.0 局域网只读配对服务 |
| `pulse_agent_console.py` | **未改动**，v1.3.0 旧界面，保留作回退基线 |
| `verify_studio.py` | v2.0.0 端到端验证（30 项） |
| `verify_pair.py` | **未改动**，v1.3.0 契约验证（22 项） |

启动/打包脚本（`start.sh` / `start.bat` / `build_linux.sh` / `build_exe.bat`）已切到 `pulse_studio.py`，产物更名 `PULSE_Agent_Studio`，并加 `--hidden-import pulse_core / pulse_glass`。

### 9.5 验证结果（全部通过）

- `verify_studio.py` **30/30**：四页切换、3 列网格、筛选/搜索、新建任务、tick 推进、悬浮窗开关/折叠/拖拽/减弱动效/实时同步/关闭回写
- `verify_pair.py` **22/22** 独立复跑：扫码配对链路零回归；配对服务仍产出任务快照
- offscreen 截图：工作台 / 概览 / 日志 / 预警 4 页 + 悬浮窗展开/折叠 2 态 + 2 张「悬浮窗叠在主界面上」合成图
- `py_compile` 全通过；修复记录：卡片首次布局只排 1 列 → viewport 宽度 + `showEvent` 重排；卡片底部标签被裁 → 卡高 196→214、改相对顶部定位；玻璃文字裁切 → `elidedText` + 按钮预留宽度；日志 Agent 名粘连 → 加宽截断 + 竖向分隔
- PyInstaller 单文件 `dist/PULSE_Agent_Studio`（58MB ELF）：**脱离源码、在临时目录独立启动成功**，主界面截图与悬浮窗截图均正常，产物内含 `pulse_glass`

### 9.6 已知限制 / 下一步

- 悬浮窗透射模糊依赖 `QScreen.grabWindow(0)`；部分 Linux 合成器 / 远程桌面可能抓不到有效画面，此时自动降级为程序化 Aurora（视觉仍完整，但看不到真实桌面透射）
- 悬浮窗为 `Qt.Tool` 顶层窗口，Windows 上需真机确认任务栏行为与多显示器落点
- 数据仍为本地 `seed_tasks()` + `random` 推进（两端独立、未接真实后端）——延续上一轮 P0 数据契约结论
- 移动端 v1.4.0 已完成扫码（内联 jsQR，非 ZXing）、「项目」页数据映射、断线回退与手动输入兜底；PC 端本文件描述的配对服务作为其数据源，`PAIR_VERSION` 保持 1.3.0 以维持接口契约稳定
- 仍需真机验收：CAMERA 运行时授权 / 后置摄像头取帧 / 多机型 WebView 对 `file://` 下 `getUserMedia` 的兼容性；Windows exe 打包与任务栏/多显示器行为确认

---

## 10. v2.1.0（P0 数据真实化）：random 模拟 → 事件驱动引擎

> 目标：消除「数据全靠 `seed_tasks()` + `random` 推进」这一最大缺口，让 PC 端可接入真实 Agent 事件源；`/api/tasks` 契约不变，移动端 v1.4.0 无需改动即自动吃到真实数据。

### 10.1 架构

```
真实 Agent ──┬── JSONL 文件 ────→ FileEventSource（tail 跟随）
             ├── HTTP POST ─────→ HttpEventSource（POST /api/events，token 鉴权）
             └── 录制/回放 ─────→ ReplayEventSource（时间轴 × 倍速，可复现）
                        ↓ poll()
                  EventEngine（事件 → 任务状态机，就地修改共享 tasks 列表）
                        ↓ 每 2s tick
                  StudioWindow.refresh_all()（UI / 悬浮窗 / 配对快照零改动）
```

### 10.2 事件模型（10 类）

| 事件 | 语义 | 状态机效果 |
|---|---|---|
| `task_started` | 新建或重启 | 新任务 append（首步 active）；终态任务清零重跑 |
| `step_completed` | 完成某步 | 按索引（或首个 active/todo）置 done，下一个置 active，进度按完成数重算 |
| `task_progress` | 直报进度 | progress 设置 + 步骤四态按百分比同步 |
| `task_paused / resumed / review` | 状态流转 | paused/running/review；done/failed 终态拒绝流转 |
| `task_failed` | 失败 | failed + reason 写 error 日志 + active→blocked |
| `task_completed` | 完成 | done + 100% + 全步骤 done |
| `log` | 追加日志 | level 归一化（非法→info），任务日志 60 条截断 |
| `tokens` | 用量增量 | 只累计正 delta |

容错：未知 `task_id` 记录到 `unknown_ids` 不崩溃；坏 JSON/未知 type 计数跳过；HTTP 队列上限 512 满时丢最旧。

### 10.3 接入方式（CLI）

```bash
python3.12 pulse_studio.py                          # 默认：本地模拟（行为与 2.0.0 一致）
python3.12 pulse_studio.py --source none            # 冻结模式（不推进）
python3.12 pulse_studio.py --source replay:events/demo_events.jsonl --source-speed 30
python3.12 pulse_studio.py --source file:/path/agent_events.jsonl
python3.12 pulse_studio.py --source http            # 开放 POST /api/events
```

`POST /api/events?token=...`（或 `X-Pulse-Token` 头）接受单事件或 `{"events": [...]}` 批量（≤256 条、body ≤256KB）；仅 `--source http` 模式开放，其余模式返回 404，/api/tasks 与 /api/health 契约不变。

### 10.4 文件与验证

| 项 | 内容 |
|---|---|
| `pulse_events.py` | 事件模型 + 三事件源 + `EventEngine` 状态机（纯 Python 无 Qt 依赖） |
| `events/demo_events.jsonl` | 18 条录制事件流，覆盖全部 10 类事件、多任务交错 |
| `verify_events.py` | **42 项**：A 区 26 项引擎单元（状态机/容错/三源行为）+ B 区 16 项集成（replay/file/http 接入主程序、卡片重建、全局日志、快照、POST 通道鉴权/坏包/批量、默认模拟回归） |
| 回归 | `verify_studio` 30/30、`verify_pair` 22/22、`verify_link` 32/32 全部通过，零回归 |
| 打包 | v2.1.0 单文件 `dist/PULSE_Agent_Studio` 脱离源码独立启动成功，`--source replay` 模式在打包产物内验证通过，产物含 `pulse_events` |

### 10.5 已知限制 / 下一步（P1）

- 引擎仍保留模拟分支（`simulate=True` 默认）作为无事件源时的兜底；接入真实 agent 后建议显式 `--source` 启动
- 同步仍是手机 2s 轮询拉取，未做 SSE/WebSocket 推送（P1）
- token 每次启动重新生成，PC 重启后手机需重新配对（P1：token 持久化）
- `task_progress` 与 `step_completed` 双通道写同一进度，外部 agent 应二选一使用，避免抖动

---

## 11. v2.1.0（P1 链路升级）：token 持久化 + 长轮询 + SSE

> 目标：PC 重启免重新扫码；进度变化准实时推达手机；断线退避与自动恢复。`/api/tasks` 契约与 `PAIR_VERSION=1.3.0` 不变（向后兼容扩展），移动端 v1.4.0 继续可用。

### 11.1 服务端新增

| 端点/机制 | 说明 |
|---|---|
| token 持久化 | `~/.pulse/pair_token`（600 权限）；启动复用，损坏自动重生成；无法落盘时退化一次性 token |
| `GET /api/poll?token&rev=N` | 长轮询：rev 过期立即 200（含新 rev）；未变化挂起 `poll_hold`（默认 8s，可参数化）超时 204；`publish()` 时 Condition 唤醒全部挂起连接 |
| `GET /api/stream?token` | SSE：连接即推当前快照，之后每次变化推 `event: tasks`；空闲 10s 心跳注释行（周期可参数化）；客户端断开静默清理；`stop_event` 保证停机不挂死 |
| health | endpoints 增列 `/api/poll` `/api/stream`（`/api/events` 仍仅 http 事件模式） |

线程模型：HTTP 线程只读不可变快照字符串与 `Condition`，不接触 Task 对象——沿用既有「主线程 publish 序列化、HTTP 线程只读」的竞态防线。

### 11.2 移动端配合（v1.5.0）

- `MainActivity.httpGetT(url, timeoutMs)`：读超时参数化（默认 15s 覆盖长轮询挂起），旧 `httpGet` 兼容保留
- Web 层 `PulseLink`：首轮 `/api/tasks` 全量 → `/api/poll?rev=N` 长轮询（204 空体立即下一轮）；失败 1/2/4/8/15/30s 指数退避，成功重置；连续失败仍由上层 `linkFailCount>=2` 语义断线回退
- **修复真 Bug**：`dropRemote` 断线回退后 rev 未清零 → 服务端无变化时永远 204 → 远端视图无法自动恢复、界面卡「连接失败」、「断开」按钮禁用、后台空转。修复：回退时 `PulseLink.rev=0`，下一轮全量同步自动恢复

### 11.3 验证（五套全绿）

- `verify_p1.py` **28/28**（新）：A 区 18 项服务端（token 持久化/复用/损坏重生成；poll 立即返回 / hold 唤醒 <0.8s / 超时 204 / 鉴权 / 坏 rev；SSE 初始推送 / 变化推送 / 心跳 / 断开清理 / 鉴权 / stop 不挂死）+ B 区 10 项移动端（Chromium + fetch 拦截桥：首轮全量、poll 切换与 rev 递增、204 节奏 ≈ hold、退避 1s→2s 递增、成功重置、断开零新请求、回退语义不回归）
- 回归：`verify_link` 32/32（更新到 v1.5.0 页面）、`verify_events` 42/42、`verify_studio` 30/30、`verify_pair` 22/22
- 打包：`dist/PULSE_Agent_Studio` 脱离源码独立启动，**两次启动 token 复用**（持久化在产物内生效）；APK `PULSE_v1.5.0.apk`（versionCode=11）v2/v3 验签通过

### 11.4 已知限制 / 下一步（P2）

- 长轮询延迟上限 = `poll_hold`(8s) + 退避；SSE 已就绪但 Android WebView `EventSource` 在 `file://` 下兼容性不确定，暂不启用
- token 持久化后取消「一次性 token」的会话隔离——安全性依赖局域网边界与 600 权限文件；如需撤销配对，删除 token 文件并重启
- P2 待办：Android 真机清单（CAMERA / WebView 兼容）、Windows exe、悬浮窗多显示器、GitHub Actions CI 自动发版

---

## 12. v2.2.0（P3）：手机端写命令——暂停 / 恢复 / 重试

> 目标：连接后从「只读」升级为可操作。设计上完全复用 P0 事件状态机——**命令即事件**：服务端把用户命令翻译为规范事件推入命令队列，引擎用同一套状态机应用，零新增状态逻辑。

### 12.1 命令协议（POST /api/command，token 鉴权，任何 --source 模式可用）

| action | 映射事件 | 允许来源状态 | 语义 |
|---|---|---|---|
| `pause` | `task_paused`（reason=手机端暂停） | running / review / paused | 请求体可带自定义 reason |
| `resume` | `task_resumed` | paused / review | review 任务「确认通过」同此 |
| `retry` | `task_started` | failed / paused / review / done | 从头开始（清零重跑，引擎既有语义） |

拒绝语义（响应 200 但 `rejected>0` 并给出原因）：终态不可暂停/恢复、`queued` 不可恢复、任务不存在（`task_not_found`）、白名单外 action（`unknown_action`）。批量基于**同一快照**校验——顺序依赖的命令（如 pause+resume 同任务）属预期拒绝，分两次提交即可。

### 12.2 实现

| 端 | 改动 |
|---|---|
| PC `pulse_events.py` | `EventEngine` 加 `extra_sources`（附加事件源，与主 source 并列消费）；模拟分支条件保持「无主 source 即模拟」——命令通道不抑制模拟推进 |
| PC `pulse_pair_server.py` | `PairServer.set_command_source()`；`/api/command` 路由 + `COMMAND_ACTIONS` 映射表 + 存在性/状态校验；`_cors()` 修复 **Allow-Methods 补 POST**（浏览器命令按钮的预检依赖，旧值只允许 GET 导致跨域 POST 全部失败） |
| PC `pulse_studio.py` | `_build_engine` 各模式统一注入 cmd_source；APP_VER 2.2.0 |
| Android `MainActivity` | `httpPostT(url, body)` 桥（子线程 POST，回调与数据流隔离的 `_onCmdResult/_onCmdError`）；versionCode 12 / 1.6.0 |
| Android `index.html` | `PulseLink.command(taskId, action)`（原生桥优先，fetch 降级）；远端抽屉按状态显示命令按钮（`.cmd-row` 独立样式）；**data-cmd-task 用原始 id（p.code）而非 pc- 前缀映射 id**；cmd 监听器区分 HTTP 层 ok 与命令层 rejected；回执 toast + 2.5s 后延时刷新 |

### 12.3 修掉的 3 个真 Bug（均为实测暴露）

1. **CORS 预检拒绝 POST**：`Allow-Methods` 只有 `GET, OPTIONS`，浏览器端命令按钮全部静默失败 → 补 POST
2. **cmd 监听器未注册**：`listeners` 初始化缺 `cmd` 键，`on('cmd')` 被静默忽略、回执永远无人接收 → 补键
3. **映射 id 混淆**：按钮传 `pc-AGT-1042`（本地防冲突前缀）而服务端快照是 `AGT-1042` → 拒绝 `task_not_found` 且前端误报成功 → 改传 `p.code` + 回执按 `rejected` 区分

### 12.4 验证（六套全绿，共 174 项）

- `verify_p3.py` **20/20**（新）：A 区 12 项命令契约（暂停/恢复/重试应用、终态拒绝含原因、queued 拒绝恢复、task_not_found、unknown_action、批量、401×2、health 端点）+ B 区 8 项移动端（按钮按状态显隐、点击 POST、成功回执 toast、命令应用后卡片同步「已暂停」、done→重新执行、queued/本地无按钮）
- 回归：`verify_studio` 30、`verify_events` 42、`verify_pair` 22、`verify_p1` 28、`verify_link` 32（更新到 v1.6.0 页面，只读断言改为「由 PC 端管理」）——全部通过
- 打包：`dist/PULSE_Agent_Studio`（2.2.0）、`PULSE_v1.6.0.apk`（versionCode 12）

### 12.5 已知限制 / 下一步

- 命令生效延迟 ≤ 2s（引擎 tick 节奏）+ 一次轮询刷新（≤2.5s 调度）——准实时
- 「重试」即从头重跑（清零 progress/tokens/steps），不支持断点续跑——需 PC 端任务模型支持后可扩展
- 历史趋势、多 PC 配对（P3 余项）未开始

---

## 13. v3.0.0：形态简化——移除 Studio 工作台，轻量单窗 + 内嵌二维码

> 用户要求：PC 端只要 exe 单文件版本，二维码直接内置在程序里，不要 Agent Studio 工作台。

- **新增** `pulse_desktop.py`：普通单窗口，左侧任务进度列表（状态点/名称/Agent·模型·步骤/进度条/耗时/Tokens 三行式），右侧内嵌配对二维码 + 地址 + token——**启动即显示，无需任何菜单操作**。数据层完整复用 pulse_core/pulse_events/pulse_pair_server（事件引擎、手机命令通道、token 持久化与 Studio 版零差异），Android v1.6.0 兼容。
- **移除** `pulse_studio.py`、`pulse_glass.py`（玻璃引擎与悬浮窗）、`verify_studio.py` 及相关截图；`verify_desktop.py`（11 项）替代；`verify_events/verify_p1/verify_p3` 宿主迁移到 DesktopWindow。
- **验证**：六套全绿（11+42+22+28+32+20 = 155 项，verify_studio 30 项随 Studio 移除）；打包 `dist/PULSE_Desktop`（58MB）脱离源码独立启动验证通过。
