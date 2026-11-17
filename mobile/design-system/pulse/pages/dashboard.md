# Dashboard Page Overrides

> **PROJECT:** PULSE
> **Generated:** 2026-11-14 16:42:12
> **Page Type:** Dashboard / Data View

> ⚠️ **IMPORTANT:** Rules in this file **override** the Master file (`design-system/MASTER.md`).
> Only deviations from the Master are documented here. For all other rules, refer to the Master.

---

## Page-Specific Rules

### Layout Overrides

- **Max Width:** 1400px or full-width
- **Grid:** 12-column grid for data flexibility
- **Sections:** 1. Hero (Name/Role), 2. Project Grid (Masonry), 3. About/Philosophy, 4. Contact

### Spacing Overrides

- **Content Density:** High — optimize for information display

### Typography Overrides

- No overrides — use Master typography

### Color Overrides

- **Strategy:** Neutral background (let work shine). Text: Black/White. Accent: Minimal.

### Component Overrides

- Avoid: No feedback after submit
- Avoid: No feedback during loading

---

## Page-Specific Components

- No unique components for this page

---

## Recommendations

- Effects: Real-time chart animations, alert pulse/glow, status indicator blink animation, smooth data stream updates, loading effect
- Forms: Show loading then success/error state
- Feedback: Show spinner/skeleton for operations > 300ms
- CTA Placement: Project Card Hover + Footer Contact

## Tab Bar Override（用户指定规格）

- **形态**：悬浮式圆角托盘，非贴底通栏；左右留白 12px，距底部 14px
- **结构**：左侧胶囊分组（4 个 tab，完全圆角）+ 右侧独立圆形「+」按钮，间距 10px
- **层级明度**：托盘 `#141C2E` → 胶囊 `#1E293B`（MASTER primary）→ 激活项 `#3B4A63`（MASTER secondary 家族），三级递进
- **激活态**：独立高亮胶囊，**不使用**顶部指示线或品牌绿；图标与文字 `#F8FAFC`
- **排版**：图标在上、标签在下，标签 11px；最小触控高度 62px（≥44px 规范）
- **FAB**：62px 圆形，中性 `#2B3A52` + 白色加号；绑定「快速新建任务」，提交后即时联动进度
- **无障碍**：保留 `role="tab"` / `aria-selected`；待处理预警用 7px 圆点提示，且概览页与预警页均有文字计数，不依赖颜色单独传达
- **遵从 MASTER**：200ms 过渡、`prefers-reduced-motion`、全 SVG 图标无 emoji、可见焦点

## v1.2.0 UI Refinement（层次与质感精修）

- **背景**：`body` 叠加两道极淡径向氛围光（绿 `#22C55E` @10% / 蓝 `#3B82F6` @5.5%），`background-attachment:fixed`；消除 OLED 纯色平板感，不改变 MASTER 的 `#0F172A` 基色
- **卡片**：统一 20px 圆角（列表卡片 18px），新增 `inset 0 1px 0` 内高光 + 双层柔和投影；不引入半透明伪元素覆盖层，避免文字对比度下降
- **Hero**：渐变底 `linear-gradient(150deg,#1C2B46,#16223A)` + 绿色径向光晕；进度环改用 SVG `linearGradient`（`#4ADE80 → #22C55E → #16A34A`）描边，数字提至 36px，右侧统计区加竖向分隔线
- **Bento**：每张 KPI 卡片按语义色注入 `--glow` 径向氛围光（蓝 / 琥珀 / 绿 / 紫），末根迷你柱高亮；信息层级由字号与字重区分，不新增颜色
- **图表**：新增 80 目标虚线、末点放大高亮、脚注统计条（7 日均值 / 峰值 / 较计划差值）。仍为纯 SVG + HTML，无图表库
- **动效**：卡片错峰淡入 420ms（10→270ms 递进），`prefers-reduced-motion` 与「界面动效」开关均可全局禁用
- **Tab Bar**：新增独立 `.tab-indicator` 滑动高亮块，JS 按激活项 `offsetLeft / offsetWidth` 定位，260ms 过渡；托盘加 20px 毛玻璃与柔和投影。保持 v1.1 的悬浮胶囊 + 独立圆形「+」规格不变
- **版本可辨识**：界面同步行右侧常驻 `v1.2.0` 标记；资源改名为 `app.css` / `main.js` 以破坏缓存；WebView 启动 `clearCache(true)` + `LOAD_NO_CACHE`

## v1.2.1 Bug Fix

- **进度环 `%`**：原 `.ring-unit` 用 `position:absolute;top/right` 定位，数字放大到 36px 后飘到数字右上并压在环描边上。改为 `.ring-num-row{display:inline-flex;align-items:baseline}` 把数字与 `%` 作为同一行整体居中，`%` 15px/600 与 36px 数字基线对齐
- **Tab Bar 外围描边**：`.tabbar` 与 `.tab-group` 的 `border` 全部移除，仅保留 `border-radius:30px / 999px`、背景明度三级递进与投影，视觉更干净且贴合参考图

## v1.2.2 Outer Tray Removal（用户指定：只保留内 tab bar）

- **需求澄清**：v1.2.1 只去掉了 `border`，但外层 `.tabbar` 仍带 `background:rgba(20,28,46,.96)`、`padding:10px`、`border-radius:30px`、大投影与毛玻璃，视觉上仍是一个包裹胶囊的「外框」。用户要的是**整个外层托盘消失**。
- **实现**：`.tabbar` 用 `!important` 清空 `background / border / border-radius / box-shadow / backdrop-filter / padding`，降级为纯定位容器；保留 `position:fixed`、`width:calc(100% - 24px)`、`max-width:416px`、`bottom:calc(14px + env(safe-area-inset-bottom))`、`display:flex`、`gap:10px`、`z-index:40`。
- **保留主体**：`.tab-group` 胶囊（4 tab + 滑动高亮块）与 `.fab-add` 独立圆形「+」不变；给胶囊补一层柔和外投影，使其在透明背景上仍有层次。
- **底部过渡**：原全局 `.app-shell::after` 淡出层会压暗图表脚注，改为 `.tabbar::before` 局部渐隐（`top:-28px` → 屏幕底，`z-index:-1` + `isolation:isolate`），只覆盖导航区域，不触碰上方内容。
- **缓存**：CSS 改名 `app.css` → `ui.css`，与 v1.2.0 的 `main.js` 一起确保在线预览与 WebView 不命中旧样式；版本升 `versionCode=5 / versionName=1.2.2`。

## v1.2.3 Navigation Final（只保留白圈标注的两个浮块）

- **根因复盘**：v1.2.0→v1.2.2 一直在文件末尾「追加覆盖」，累计 43 行互相覆盖的导航规则；且 APK 始终同名 `PULSE.apk` + 外部 CSS，用户端极易装回旧包或命中旧样式缓存，导致「改了但看不到」。
- **结构根治**：删除全部历史导航规则块，只保留**一份**干净定义；`.tabbar` 为透明定位容器（无背景 / 边框 / 圆角 / 投影 / 毛玻璃 / 内边距 / 伪元素），`.tabbar::before`、`.tabbar::after`、`.app-shell::after` 全部 `content:none`。**画面上只剩 `.tab-group` 胶囊与 `.fab-add` 圆形「+」两个浮块**，两者之间是页面背景。
- **交付根治**：CSS 与 JS 全部**内联进单个 `index.html`**（字体相对路径由 `../fonts/` 修正为 `fonts/`），APK assets 只含 `index.html + fonts/`，彻底消除外部资源缓存与引用不一致；产物改名 `PULSE_v1.2.3.apk`，旧 `PULSE.apk` 删除。
- **版本**：`versionCode=6 / versionName=1.2.3`，界面右上角与「我的」页可见，便于用户自检是否为新包。
- **运行时**：已删除 `web/css/ui.css` / `web/js/main.js` 副本，`web/` 下只有 `index.html`（内联全部样式与逻辑）+ `fonts/`，**单一真相源**，杜绝副本与运行时不一致。
- **保护底**：`.tabbar::before` 使用与页面背景完全同色的不透明 `#0F172A`（顶部 24px 渐变过渡），仅用于盖住滚动时从两个浮块后方透出的内容；因颜色与背景一致，不产生可见色块、边界或外框。

## v1.2.4 iOS Material（需求最终澄清）

- **误读复盘**：前几轮把「外框」理解为整个托盘并删除，v1.2.3 又加了纯色保护底，导致内容完全不透出 —— 用户明确指出「怎么不是透明的了」。真实需求是**保留托盘的半透明毛玻璃质感，只去掉四周可见的边界线**。
- **实现**：`.tabbar::before` 改为 iOS 材质层 —— `background:rgba(38,52,77,.40)` + `backdrop-filter:blur(22px) saturate(165%)`，用 `mask-image:radial-gradient(ellipse closest-side ...)` 把四周羽化到完全透明，**无 border / 无 inset 亮线 / 无硬投影边界**；后面的图表与脚注可透视并被柔化模糊。
- **高亮**：`.tab-group` 胶囊与 `.fab-add` 圆钮改为半透明浅色材质（`rgba(148,163,184,.16~.32)`）+ 各自 `backdrop-filter` 与 `inset 0 1px 0` 顶部高光；激活块 `rgba(203,213,225,.24)` 更亮，形成 iOS 式层级。
- **删除**：v1.2.3 的纯色 `#0F172A` 保护底（遮挡透视的元凶）与历史所有不透明背景。
- **交付**：`PULSE_v1.2.4.apk`（新文件名，旧包删除），`versionCode=7 / versionName=1.2.4`；仍为单文件内联、零外部 css/js。

- **实测修正**：伪元素 + `env()` + `z-index:-1` 会让雾面层位置偏移且覆盖不到胶囊，改为真实 DOM 双层 `.nav-glass`（径向雾面渐变，必定渲染）+ `.nav-blur`（独立 backdrop-filter + mask 羽化），四边相对 `.tabbar` 各扩展 26px/18px，跟随父元素实际位置。像素采样：`y=880` 中心 `(40~56,65~84,105~131)` 亮雾面，两端 `(15,23,42)` 纯背景，垂直方向 `y>=920` 回归背景色 —— 中心亮、四周全透明、无硬边界。

## v1.2.5 App Bar Gradient Blur（顶部大横条 → 渐变模糊）

- **问题**：`.appbar` 累计两处叠加定义，实色底 `rgba(15,23,42,.80/.86)` + `border-bottom:1px solid`，形成一整条与内容区有明显色差和硬水平分界线的「大横条」。
- **实现**：合并为**一份**干净定义 —— `.appbar` 降级为透明 sticky 容器（无背景 / 无边框 / 无投影），沿用底部导航已验证的**真实 DOM 双层**材质：`.top-glass` 线性雾面渐变（顶部 `rgba(38,54,80,.58)` → 底部 `rgba(15,23,42,0)`，必定渲染）+ `.top-blur` 独立 `backdrop-filter:blur(20px) saturate(150%)` + 线性 mask 下缘羽化。
- **方向差异**：底部导航用 radial 四周羽化；顶栏贴屏幕顶/左/右三边，故用 **180deg 线性向下羽化**，仅下边缘渐隐，保证状态栏与品牌区可读。
- **层级**：`.brand` / `.appbar-actions` 设 `position:relative;z-index:1`，材质层 `z-index:0` + `pointer-events:none`，不影响点击。
- **删除**：两处历史实色覆盖与 `border-bottom` 硬线；未新增覆盖层，保持单一真相源。
- **交付**：`PULSE_v1.2.5.apk`（新文件名，v1.2.4 旧包删除），`versionCode=8 / versionName=1.2.5`；仍为单文件内联、零外部 css/js。

- **稳健性**：移除顶栏冗余的 `isolation:isolate`（`position:sticky;z-index:30` 本身已是层叠上下文），避免部分真机 WebView 上限制 `backdrop-filter` 的采样范围；底部导航的 isolation 保持不变（已实测生效）。

## v1.3.0 LAN Pairing（扫码连接 PC · 第一阶段最小闭环）

- **目标**：安卓端扫码连接 PC，查看 PC 端的 Agent 任务进度。本阶段只打通数据通道，**不改任何可见 UI** —— tab bar 的 iOS 羽化毛玻璃、顶栏渐变模糊、卡片、布局、动效全部保持 v1.2.5 原样。
- **Web 层**：新增 `window.PulseLink` 纯数据接口（`get / connect / disconnect / on / status / _onData / _onError`），默认不自动连接、不写入界面；优先走 `NativeBridge.httpGet`，浏览器预览降级为 `fetch`。仅新增接口，未调用、未渲染。
- **原生层**：`AndroidManifest.xml` 增 `INTERNET` / `CAMERA` 权限与 `usesCleartextTraffic="true"`；`MainActivity.java` 的 `NativeBridge` 增 `httpGet(url)`（子线程请求 + `evaluateJavascript` 回传，含 `jsQuote` 转义与超时/错误回调）；`shouldOverrideUrlLoading` 的 `file://` 白名单不变，因为请求不走 WebView 导航。
- **版本**：`versionCode=9 / versionName=1.3.0`，产物 `PULSE_v1.3.0.apk`；界面 `ver-tag` 与页脚同步为 `v1.3.0`（沿用防旧包缓存机制），`getVersion()` 返回 `1.3.0`。
- **单一真相源不变**：仍是 `web/index.html` 单文件内联 + `fonts/`，无外部 css/js，未引入 ZXing 或任何 jar，构建链仍是纯 `aapt2 → javac → d8 → zipalign → apksigner`。
- **验证**：APK v2/v3 验签、`zipalign -c`、`unzip -t`、权限与明文标志、dex 内含 `httpGet`、内联 JS `node --check` 通过；Chromium 加载 APK 内真实 `index.html` + 模拟原生桥，`PulseLink` 成功拉到 12 条 PC 任务。
- **未做（下一阶段）**：扫码 UI、项目页数据映射与状态徽章、断线回退、手动输入地址兜底、真机验收。

## v1.4.0 LAN Pairing（扫码连接 PC · 完整闭环）

- **目标**：接上 v1.3.0 的数据通道，安卓端真正能扫码 / 输入地址连接 PC，并把 PC 的 Agent 任务进度渲染到界面。按用户既定方向「复用「项目」页、不动 tab bar」执行。
- **UI 红线**：tab bar 的 iOS 羽化毛玻璃、顶栏渐变模糊、卡片圆角与既有布局规则一行未改；本轮新增样式全部为独立类，未覆盖任何既有选择器。
- **连接入口**：「我的」页新增「连接 PC」卡片 + 「项目」页顶部连接状态条（未连接 / 连接中 / 已连接 / 失败四态，带「连接 PC」「断开」动作）。连接面板复用 `.sheet` 机制：相机扫码区 + 手动输入 `IP:端口` 与 `token` 两栏 + 连接 / 断开按钮。
- **扫码实现**：内联 jsQR 1.4.0（terser 压缩，UMD 挂 `window.jsQR`，全离线、无 jar、不引 ZXing），`getUserMedia` 取帧 → canvas → `jsQR` 解码 → 自动回填并连接。原生层补 CAMERA 运行时权限申请、`WebChromeClient.onPermissionRequest` 仅放行 `RESOURCE_VIDEO_CAPTURE`、`setMediaPlaybackRequiresUserGesture(false)`。
- **必备兜底**：相机不可用 / `file://` 安全上下文受限时，`scanFallback` 明确提示并聚焦手动输入框；手动输入路径零权限依赖，任何机型都能连。绝不静默失败、绝不白屏。
- **数据映射**：`applyRemoteData()` 把 PC `/api/tasks` 快照映射为与 `DATA.projects` 兼容的结构；6 态 → 3 态筛选（running/queued→active，review/paused/failed→risk，done→done），并保留 `status_label` 中文徽章；`steps` 四态、`agent/model`、`elapsed/tokens/priority/logs` 全部保留。渲染层统一走 `activeProjects()`，概览完成率取 PC `summary.completion_rate`。
- **只读与回退**：连接后远端任务只读（`toggleTask` / `submitQuick` 拦截并提示），「+」改为立即刷新远端快照；连续 2 次请求失败或 PC 离线自动回退本地演示数据；`REMOTE.suppressed` 抑制断开后的在途响应，避免「断开又自动连回来」；启动时静默重连上次地址，失效则保持本地数据、不打扰。
- **sheet 互斥**：`openSheet()` / `openQuick()` 均先 `closeLinkSheet()`，杜绝抽屉与连接面板叠加。
- **视觉修正**：① `.progress-fill` 原为 inline span，`width/height` 百分比不生效，进度条长期只显示灰底槽 → 改 `display:block`；② 远端指标卡改两列 + `word-break`，解决长 Agent / 模型名撑破卡片重叠。
- **版本**：`versionCode=10 / versionName=1.4.0`，产物 `PULSE_v1.4.0.apk`（旧 v1.3.0 保留作回退）；界面 `ver-tag` / 页脚 / `appVersion` / `PulseLink.version` 同步 v1.4.0。仍为单文件内联 + 6 字体，构建链零外部依赖。
- **验证**：新增 `verify_link.py`（Chromium CDP 加载 APK 内真实 `index.html` + 模拟 `NativeBridge.httpGet` + 请求 PC v2.0.0 真实服务）**32/32 通过**：初始 5 个本地项目、连接后 12 个 PC 任务、中文状态徽章、进度与 PC 一致、概览完成率、筛选数量、抽屉步骤 / 日志 / 只读、sheet 互斥、断开即时回退、6 秒后迟到响应仍被抑制、内联 jsQR 解出真实二维码地址、进度条填充实测 `302/302`、指标卡零溢出。`verify_pair.py` 22/22 独立复跑（PC 端本轮未改，零回归）。APK v2/v3 验签、`zipalign -c`、`unzip -t`、权限与明文标志、dex 内含 `WebChromeClient / onPermissionRequest / requestPermissions / httpGet`、内联 JS `node --check` 全通过。
- **已知限制 / 下一步**：相机扫码依赖 Android WebView 对 `file://` 授予 `getUserMedia`，部分机型或较旧系统 WebView 可能失败，此时自动退化到手动输入（能力不丢失）；需真机验证 CAMERA 运行时授权与后置摄像头取帧。PC 端 token 每次启动重新生成，过期后需重新扫码或在面板点「连接」。两端数据仍为本地 `seed_tasks()` + `random` 推进，未接真实 agent 事件源。

## v1.5.0 LAN Link（长轮询 + 指数退避 + 断线自动恢复）

- **目标**：落实 P1 链路升级——PC 重启免重新扫码（token 持久化）、准实时推送（长轮询）、断线退避与自动恢复。方向仍为「复用项目页、不动 tab bar / 顶栏 / 卡片布局」，本轮 Web 层改动全部集中在 `PulseLink` 通道层。
- **长轮询**：首轮 `GET /api/tasks` 全量（契约与 v1.4.0 一致），之后 `GET /api/poll?rev=N`：服务端快照修订号变化立即返回（含 `rev`），未变化挂起至 hold（默认 8s）超时 204。PC 端每 2s tick `publish` 时 rev +1 并唤醒挂起连接——进度变化 1s 内推达手机，且远低于固定轮询的空开销。
- **原生桥**：`MainActivity` 新增 `httpGetT(url, timeoutMs)`（读超时参数化，默认 15000 覆盖长轮询挂起），旧 `httpGet` 保留兼容；Web 层优先 `httpGetT`，回退 `httpGet`，浏览器预览走 fetch（204 空体 → 视为无变化立即下一轮）。
- **指数退避**：失败按 1/2/4/8/15/30s 退避，成功重置；连续失败仍由上层 `linkFailCount>=2` 语义断线回退（瞬时失败不断线）。
- **断线自动恢复（本轮修掉的真 Bug）**：`dropRemote` 断线回退时原实现不清长轮询 rev——服务端此后无变化则永远 204，远端视图**无法自动恢复**，界面卡在「连接失败」且「断开」按钮禁用、后台空转轮询。修复：回退时清零 `PulseLink.rev`，下一轮强制全量同步自动恢复。实测：连续 2 次失败回退本地 → 下一轮 poll 全量返回 → 自动重连 12 个任务、「断开」按钮恢复可用。
- **token 持久化（PC 端配合）**：PC 端 token 持久化到 `~/.pulse/pair_token`（600 权限，损坏自动重生成），重启后 token 不变 → 手机端已保存地址 + 启动静默重连真实生效（回归时曾用旧 profile 直接复现「加载即已连接」）。App 端零改动即受益。
- **版本**：`versionCode=11 / versionName=1.5.0`，产物 `PULSE_v1.5.0.apk`（v1.4.0 保留回退）；`ver-tag` / 页脚 / `appVersion` / `PulseLink.version` 同步 v1.5.0。
- **验证**：PC 端新增 `verify_p1.py` **28/28**（A 区 18 项服务端：token 持久化/复用/损坏重生成、poll 立即返回/hold 唤醒 <0.8s/超时 204/鉴权/坏 rev、SSE 初始推送/变化推送/心跳/断开清理/鉴权/stop 不挂死；B 区 10 项 Chromium + fetch 拦截桥：首轮全量、poll 切换、rev 递增、204 节奏 ≈ hold、退避 1s→2s 递增、成功重置、断开零新请求、回退语义）。`verify_link.py` **32/32** 更新到 v1.5.0 页面（模拟桥 `getVersion` 同步）；`verify_events` 42/42、`verify_studio` 30/30、`verify_pair` 22/22 零回归。APK v2/v3 验签、`zipalign -c`、内联 JS `node --check` 全通过。
- **已知限制 / 下一步**：长轮询 hold 默认 8s，弱网高延迟下极端情况延迟上限 8s+退避；SSE `/api/stream` 已在 PC 端就绪但 Android WebView 的 `EventSource` 在 `file://` 下兼容性不确定，暂不启用（长轮询已达准实时）；真机验收项延续 v1.4.0 清单。

## v1.6.0 Task Commands（手机端暂停 / 恢复 / 重试）

- **目标**：P3 把连接后「只读」升级为可操作——远端任务抽屉按状态显示命令按钮，提交到 PC 端执行。UI 红线不变：tab bar / 顶栏 / 卡片布局一行未改，新增 `.cmd-row/.cmd-btn` 独立样式类。
- **命令按钮**：running→「暂停任务」（琥珀）；paused→「恢复执行」（绿）；review→「确认通过，继续执行」（绿）；failed→「重试（从头开始）」（绿）；done→「重新执行」（灰）；queued→无按钮。按钮仅出现在已连接的远端任务抽屉，本地任务不受影响。
- **提交链路**：`PulseLink.command(taskId, action)` → 原生 `httpPostT`（新增桥，子线程 POST，回调与轮询数据流隔离）→ PC `POST /api/command` → 命令映射为规范事件（复用 P0 状态机）→ 引擎应用 → 下次轮询同步回手机。浏览器预览环境走 fetch 降级。回执 toast + 2.5s 后延时全量刷新。
- **修掉的 3 个真 Bug**：① PC 端 CORS `Allow-Methods` 缺 POST → 浏览器命令按钮全部静默失败；② `PulseLink` 的 `listeners` 缺 `cmd` 键 → `on('cmd')` 注册被静默忽略、回执无人接收；③ 按钮误传 `pc-` 前缀映射 id → 服务端 `task_not_found` 拒绝且前端误报成功 → 改传原始 id（`p.code`）且回执按 `rejected` 区分失败原因（toast 显示 PC 端拒绝原因，如「任务在 PC 端已不存在」）。
- **版本**：`versionCode=12 / versionName=1.6.0`，产物 `PULSE_v1.6.0.apk`；ver-tag / 页脚 / appVersion / PulseLink.version 同步。
- **验证**：PC 端新增 `verify_p3.py` **20/20**（A 区命令契约 12 项 + B 区 Chromium 抽屉按钮与命令应用 8 项，含「点击暂停 → PC 应用 → 手机卡片同步显示已暂停」全链路）；`verify_link.py` **32/32** 更新到 v1.6.0；五套既有回归（30+42+22+28）全部通过，共 **174 项断言**全绿并纳入 CI。
- **已知限制 / 下一步**：命令生效 ≤2s（PC tick 节奏）+ 刷新 ≤2.5s；「重试」为从头重跑不支持断点续跑；P3 余项（历史趋势、多 PC 配对）未开始。
