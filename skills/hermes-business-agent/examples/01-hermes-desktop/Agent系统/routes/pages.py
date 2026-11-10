from fasthtml.common import A, Body, Button, Div, Form, Head, Html, Input, Label, Link, Meta, Option, Script, Select, Span, Title

from server import app, APP_TITLE
@app.get("/")
def index():
    """单页外壳：结构在这里，交互全在 static/app.js。"""
    return Html(
        Head(
            Meta(charset="utf-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1"),
            Title(APP_TITLE),
            Link(rel="stylesheet", href="/app.css"),
        ),
        Body(
            # ── 左侧栏：会话列表 ─────────────────────────────────────
            Div(cls="sidebar", id="sidebar")(
                Div(cls="side-head")(
                    Div(cls="brand")(Span(cls="dot"), "Hermes Desktop"),
                    A(
                        Span("🏢", cls="biz-entry-icon"),
                        Div(
                            Span("研发费用管理系统", cls="biz-entry-title"),
                            Span("进入业务系统 →", cls="biz-entry-sub"),
                        ),
                        href="/dashboard", cls="biz-entry", title="一键进入研发费用管理系统",
                    ),
                    Button("＋ 新对话", cls="btn primary block", id="btnNew"),
                    Form(
                        Input(id="convSearch", cls="search-box", placeholder="搜索会话 / #标签",
                              **{"type": "text"}, aria_label="搜索会话"),
                        style="margin:0;padding:0;",
                        onsubmit="event.preventDefault(); loadConversations(); return false;",
                    ),
                    Button("⭳ 导入会话", cls="btn ghost block", id="btnImportConv"),
                    Input(id="importFile", type="file", accept=".json,application/json",
                          style="display:none", aria_label="导入会话文件"),
                ),
                Div(cls="side-nav", id="sideNav")(
                    Div(cls="side-nav-group")("对话"),
                    Button(Span(cls="nav-icon")("💬"), Span("对话"), cls="nav", id="navChat", data_view="chat", title="回到对话"),
                    Div(cls="side-nav-group")("Agent 能力"),
                    Button(Span(cls="nav-icon")("🧩"), Span("技能"), cls="nav", id="navSkills", data_view="skills", title="技能市场 / 我的技能"),
                    Button(Span(cls="nav-icon")("🤖"), Span("模型"), cls="nav", id="navModels", data_view="models", title="模型配置"),
                    Button(Span(cls="nav-icon")("🔧"), Span("工具"), cls="nav", id="navTools", data_view="tools", title="统一工具面板：工具清单（只读）+ 工具管理（可操作）"),
                    Button(Span(cls="nav-icon")("⚙"), Span("MCP"), cls="nav", id="navMcp", data_view="mcp", title="MCP 服务器市场"),
                    Button(Span(cls="nav-icon")("🧩"), Span("插件"), cls="nav", id="navPlugins", data_view="plugins", title="Hermes 原生内置插件 95 个"),
                    Button(Span(cls="nav-icon")("👥"), Span("委派"), cls="nav", id="navDelegation", data_view="delegation", title="多代理委派"),
                    Button(Span(cls="nav-icon")("🔁"), Span("循环"), cls="nav", id="navLoops", data_view="loops", title="循环 / 委派框架"),
                    Button(Span(cls="nav-icon")("🔄"), Span("MOA"), cls="nav", id="navMoa", data_view="moa", title="多智能体混合"),
                    Div(cls="side-nav-group")("知识"),
                    Button(Span(cls="nav-icon")("🧠"), Span("记忆管理"), cls="nav", id="navMemory", data_view="memory", title="MEMORY.md / USER.md"),
                    Button(Span(cls="nav-icon")("✨"), Span("Soul 人格"), cls="nav", id="navSoul", data_view="soul", title="SOUL.md 人格编辑"),
                    Button(Span(cls="nav-icon")("📚"), Span("LLM Wiki"), cls="nav", id="navWiki", data_view="wiki", title="个人知识库"),
                    Div(cls="side-nav-group")("工作台"),
                    Button(Span(cls="nav-icon")("📂"), Span("文件浏览器"), cls="nav", id="navWorkspace", data_view="workspace", title="浏览本机文件夹，挑选文件给 AI（受限授权根）"),
                    Button(Span(cls="nav-icon")("📋"), Span("项目"), cls="nav", id="navProjects", data_view="projects", title="项目管理"),
                    Button(Span(cls="nav-icon")("📋"), Span("Kanban"), cls="nav", id="navKanban", data_view="kanban", title="看板管理"),
                    Button(Span(cls="nav-icon")("📜"), Span("旅程"), cls="nav", id="navJourney", data_view="journey", title="学习旅程时间线"),
                    Button(Span(cls="nav-icon")("🔍"), Span("策展"), cls="nav", id="navCurator", data_view="curator", title="内容策展"),
                    Div(cls="side-nav-group")("自动化"),
                    Button(Span(cls="nav-icon")("⏰"), Span("定时任务"), cls="nav", id="navCron", data_view="cron", title="定时任务"),
                    Button(Span(cls="nav-icon")("🔧"), Span("蓝图"), cls="nav", id="navBlueprints", data_view="blueprints", title="Hermes 自动化蓝图（生成真实定时任务）"),
                    Button(Span(cls="nav-icon")("📊"), Span("批量处理"), cls="nav", id="navBatch", data_view="batch", title="批量处理"),
                    Div(cls="side-nav-group")("接入"),
                    Button(Span(cls="nav-icon")("📡"), Span("远程渠道"), cls="nav", id="navChannels", data_view="channels", title="微信/QQ/飞书/钉钉/企微/Telegram"),
                    Button(Span(cls="nav-icon")("📡"), Span("路由"), cls="nav", id="navRouting", data_view="routing", title="提供者路由"),
                    Div(cls="side-nav-group")("系统"),
                    Button(Span(cls="nav-icon")("🧠"), Span("上下文"), cls="nav", id="navContext", data_view="context", title="上下文引擎选择 / 压缩状态 / token 跟踪"),
                    Button(Span(cls="nav-icon")("⚙"), Span("系统提示词"), cls="nav", id="navSysprompt", data_view="sysprompt", title="自定义系统提示词"),
                    Button(Span(cls="nav-icon")("📜"), Span("日志"), cls="nav", id="navLogs", data_view="logs", title="查看 Hermes 运行日志（对齐 hermes logs）"),
                    Button(Span(cls="nav-icon")("🔣"), Span("结构化输出"), cls="nav", id="navStructured", data_view="structured", title="触发结构化输出 / 离线校验 JSON（对齐 Hermes Library structured output）"),
                    Button(Span(cls="nav-icon")("🎯"), Span("目标"), cls="nav", id="navGoals", data_view="goals", title="持久化会话目标"),
                    Button(Span(cls="nav-icon")("📸"), Span("快照"), cls="nav", id="navCheckpoints", data_view="checkpoints", title="对话快照管理"),
                    Button(Span(cls="nav-icon")("📦"), Span("捆绑包"), cls="nav", id="navBundles", data_view="bundles", title="技能捆绑包"),
                    Button(Span(cls="nav-icon")("🔐"), Span("安全审计"), cls="nav", id="navSecurity", data_view="security", title="安全审计"),
                    Button(Span(cls="nav-icon")("📁"), Span("备份"), cls="nav", id="navBackup", data_view="backup", title="完整备份/恢复（全量 ZIP 归档）"),
                    Button(Span(cls="nav-icon")("💾"), Span("状态快照"), cls="nav", id="navSnapshots", data_view="snapshots", title="Hermes 原生状态快照（轻量核心状态快速回滚）"),
                    Button(Span(cls="nav-icon")("👤"), Span("配置管理"), cls="nav", id="navProfiles", data_view="profiles", title="多配置文件管理"),
                ),
                Div(cls="conv-toolbar", id="convToolbar")(
                    Label(cls="conv-selall")(
                        Input(type="checkbox", id="convSelectAll", title="全选 / 取消全选"),
                        Span("全选"),
                    ),
                    Button("🗑 删除选中", cls="btn ghost danger hidden", id="btnBatchDelete",
                           title="批量删除所选会话"),
                    Button("⧉ 复制选中", cls="btn ghost hidden", id="btnBatchCopy",
                           title="批量复制所选会话"),
                    Button("⭳ 导出选中", cls="btn ghost hidden", id="btnBatchExport",
                           title="批量导出所选会话为 Markdown"),
                ),
                Div(cls="conv-list", id="convList"),
            ),
            # ── 侧栏宽度拖拽手柄 ────────────────────────────────────
            Div(cls="side-resize", id="sideResize",
                title="拖动调整侧栏宽度"),
            # ── 主区 ─────────────────────────────────────────────────
            Div(cls="main")(
                Div(cls="topbar")(
                    Button("☰", cls="btn icon", id="btnToggleSide",
                           title="折叠 / 展开左侧栏", aria_label="折叠 / 展开左侧栏"),
                    Div(cls="conv-title", id="convTitle")("新对话"),
                    Div(cls="conv-actions hidden", id="convActions")(
                        Button("✎", cls="btn icon", id="btnConvRename",
                               title="重命名当前对话", aria_label="重命名当前对话"),
                        Button("⭳", cls="btn icon", id="btnConvExport",
                               title="导出当前对话", aria_label="导出当前对话"),
                        Button("📥", cls="btn icon", id="btnConvArchive",
                               title="归档 / 取消归档当前对话", aria_label="归档 / 取消归档当前对话"),
                        Button("🗑", cls="btn icon", id="btnConvDelete",
                               title="删除当前对话", aria_label="删除当前对话"),
                    ),
                    Div(cls="spacer"),
                    Button("🔍", cls="btn ghost", id="btnConvSearch",
                           title="在当前对话中搜索（高亮定位）", aria_label="在当前对话中搜索"),
                    Button("🎨", cls="btn ghost", id="btnSkin", title="主题皮肤", aria_label="主题皮肤"),
                    Button(Span(cls="menu-icon", id="themeIcon")("🌗"), cls="btn ghost", id="btnTheme",
                           title="切换深浅主题", aria_label="切换深浅主题"),
                    Button(Span(cls="menu-icon")("📊"), cls="btn ghost", id="btnAnalytics",
                           title="用量分析（对标 hermes-studio Usage Analytics）", aria_label="用量分析"),
                    Button(Span(cls="menu-icon")("📦"), cls="btn ghost", id="btnFullExport",
                           title="导出所有数据（会话、Wiki、记忆、看板、配置）为 ZIP",
                           aria_label="导出所有数据为 ZIP"),
                    Button(Span(cls="menu-icon")("⚙"), cls="btn ghost", id="btnConfig",
                           title="导出/导入配置（模型、技能、MCP）", aria_label="导出/导入配置"),
                ),
                Div(cls="agent-phase hidden", id="agentPhase")(
                    Span(cls="dot"), Span("就绪", id="agentPhaseText"),
                ),
                Div(cls="conv-search hidden", id="convSearchBar")(
                    Form(
                        Input(id="convSearchInput", type="text",
                              placeholder="在对话中搜索…（Enter 跳下一条，Esc 关闭）",
                              aria_label="在对话中搜索"),
                        style="margin:0;padding:0;flex:1;",
                        onsubmit="event.preventDefault(); convSearchJump(1); return false;",
                    ),
                    Span(id="convSearchCount", cls="conv-search-count"),
                ),
                Div(cls="chat", id="chat")(
                    Div(cls="empty", id="emptyHint")(
                        Div(cls="empty-title")("开始一段对话"),
                        Div(cls="empty-sub")(
                            "输入 / 可查看原生指令；工具执行过程会实时显示在时间线上。"),
                        Div(cls="chips", id="starterChips"),
                    ),
                ),
                Div(cls="composer-wrap", id="composerWrap")(
                    Div(cls="cmd-pop hidden", id="cmdPop"),
                    Div(cls="attachments-area hidden", id="attachmentsArea")(
                        Div(cls="attachments-head")(
                            Span("📎 附件"),
                            Button("× 清空", cls="btn ghost sm", id="btnClearAttach"),
                        ),
                        Div(cls="attachments-list", id="attachmentsList"),
                    ),
                    Div(cls="ctx-folder-bar hidden", id="ctxFolderBar")(
                        Div(cls="ctx-folder-inner")(
                            Span("📌 固定上下文：", cls="ctx-folder-label"),
                            Span(cls="ctx-folder-path", id="ctxFolderPath", title=""),
                            Button("解绑", cls="btn ghost xs", id="btnUnbindCtx",
                                   title="取消此会话的固定文件夹上下文"),
                        ),
                    ),
                    Div(cls="composer")(
                        Div(cls="composer-main")(
                            Div(cls="ta-wrap", id="taWrap")(
                                Div(cls="resize-handle", id="resizeHandle",
                                    title="拖动调整输入框高度；也可拖拽文件到此处上传为附件"),
                                Div(id="prompt", cls="ta", contenteditable="true",
                                    **{"data-ph": "问点什么…（Enter 发送，Shift+Enter 换行，/ 唤起指令；拖文件到此处上传）"}),
                            ),
                            Button("🎤", cls="btn icon", id="btnMic", title="语音输入（Web Speech API）"),
                            Button("发送", cls="btn primary send", id="btnSend"),
                            Button("■ 停止", cls="btn danger send hidden", id="btnStop"),
                        ),
                        Div(cls="composer-toolbar")(
                            Label("模型", cls="tool-label"),
                            Select(id="modelSelect", cls="tool-select", title="选择对话使用的模型", aria_label="模型")(
                                Option("加载中…", value=""),
                            ),
                            Label("技能", cls="tool-label"),
                            Select(id="skillSelect", cls="tool-select", title="选择要注入的原生技能（可留空）", aria_label="技能")(
                                Option("默认（不指定技能）", value=""),
                            ),
                            Button("🧠 深度思考", cls="btn toggle", id="btnDeep",
                                   title="开启后提升模型推理强度（深度思考），并把 <thinking> 段分流到可折叠区"),
                            Button("🌐 联网", cls="btn toggle on", id="btnWeb",
                                   title="关闭后禁用 web / browser 工具集"),
                            Button("📎 上传", cls="btn ghost", id="btnUpload",
                                   title="上传文件作为附件注入上下文"),
                            Button("📁 文件夹", cls="btn ghost", id="btnUploadFolder",
                                   title="选择整个文件夹，递归上传其中全部文件（保留目录结构）"),
                            Input(type="file", id="fileInput", multiple=True,
                                  style="display:none", aria_label="上传文件附件"),
                            Input(type="file", id="folderInput", multiple=True,
                                  **{"webkitdirectory": "", "directory": ""},
                                  style="display:none", aria_label="选择整个文件夹上传"),
                            Span(id="attachChip", cls="attach-chip hidden"),
                        ),
                    ),
                    Div(cls="composer-foot", id="composerFoot")(
                        Span(id="usageChip", cls="usage-chip",
                             title="当前会话 token 用量与估算成本（进程内路线无 provider 账单，成本仅为估算）"),
                        Span(id="ctxIndicator", cls="ctx-indicator"),
                        Button("🗜 压缩", cls="btn ghost", id="btnQuickCompress",
                               title="立即压缩当前会话上下文（引擎压缩）"),
                        Span(cls="hint", id="cmdHint",
                             text="输入 / 查看命令，/help 获取帮助"),
                        Span(id="modelChip", cls="model-chip"),
                        Span(cls="spacer"),
                        Span(id="voiceState", cls="voice-state hidden"),
                        Div(cls="health", id="healthChip")("就绪"),
                    ),
                ),
                Div(cls="app-view hidden", id="view-skills")(),
                Div(cls="app-view hidden", id="view-models")(),
                Div(cls="app-view hidden", id="view-tools")(),
                Div(cls="app-view hidden", id="view-mcp")(),
                Div(cls="app-view hidden", id="view-cron")(),
                Div(cls="app-view hidden", id="view-plugins")(),
                Div(cls="app-view hidden", id="view-logs")(),
                Div(cls="app-view hidden", id="view-structured")(),
                Div(cls="app-view hidden", id="view-loops")(),
                Div(cls="app-view hidden", id="view-delegation")(),
                Div(cls="app-view hidden", id="view-memory")(),
                Div(cls="app-view hidden", id="view-context")(),
                Div(cls="app-view hidden", id="view-soul")(),
                Div(cls="app-view hidden", id="view-wiki")(),
                Div(cls="app-view hidden", id="view-channels")(),
                Div(cls="app-view hidden", id="view-kanban")(),
                Div(cls="app-view hidden", id="view-sysprompt")(),
                Div(cls="app-view hidden", id="view-goals")(),
                Div(cls="app-view hidden", id="view-checkpoints")(),
                Div(cls="app-view hidden", id="view-moa")(),
                Div(cls="app-view hidden", id="view-projects")(),
                Div(cls="app-view hidden", id="view-bundles")(),
                Div(cls="app-view hidden", id="view-security")(),
                Div(cls="app-view hidden", id="view-blueprints")(),
                Div(cls="app-view hidden", id="view-batch")(),
                Div(cls="app-view hidden", id="view-journey")(),
                Div(cls="app-view hidden", id="view-backup")(),
                Div(cls="app-view hidden", id="view-snapshots")(),
                Div(cls="app-view hidden", id="view-profiles")(),
                Div(cls="app-view hidden", id="view-curator")(),
                Div(cls="app-view hidden", id="view-routing")(),
                Div(cls="app-view hidden", id="view-workspace")(),
            ),
            Div(cls="mask hidden", id="approvalMask")(
                Div(cls="modal")(
                    Div(cls="modal-head")(
                        Div("需要你确认", cls="modal-title"),
                        Button("✕", cls="btn icon", id="btnCloseApproval"),
                    ),
                    Div(cls="approval-body", id="approvalBody"),
                    Div(cls="modal-foot")(
                        Button("取消", cls="btn ghost", id="btnRejectCmd"),
                        Button("批准执行", cls="btn danger", id="btnApproveCmd"),
                    ),
                ),
            ),
            Div(cls="drawer hidden", id="artifactDrawer")(
                Div(cls="drawer-head")(
                    Div("产物", cls="modal-title"),
                    Div(cls="spacer"),
                    Button("刷新", cls="btn ghost", id="btnRefreshArtifacts"),
                    Button("✕", cls="btn icon", id="btnCloseArtifacts"),
                ),
                Div(cls="drawer-body", id="artifactBody"),
            ),
            # ── 工具调用信息抽屉（对话区右上角「工具调用信息」按钮触发）──
            # 对话过程中的工具调用与参数配置不再内联在对话区，统一汇总到此处。
            Div(cls="drawer hidden", id="toolCallsDrawer")(
                Div(cls="drawer-head")(
                    Div("🔧 工具调用信息", cls="modal-title"),
                    Div(cls="spacer"),
                    Button("清空", cls="btn ghost sm", id="btnClearToolCalls",
                           title="清空本对话的工具调用记录"),
                    Button("✕", cls="btn icon", id="btnCloseToolCalls"),
                ),
                Div(cls="drawer-body")(
                    Div(cls="tcp-list", id="toolCallsList"),
                    Div(cls="drawer-empty hidden", id="toolCallsEmpty")("本对话暂无工具调用记录"),
                ),
            ),
            # ── 用量分析弹窗（对标 hermes-studio「Usage Analytics」）──
            Div(cls="mask hidden", id="analyticsMask")(
                Div(cls="modal wide")(
                    Div(cls="modal-head")(
                        Div("用量分析", cls="modal-title"),
                        Button("✕", cls="btn icon", id="btnCloseAnalytics"),
                    ),
                    Div(cls="analytics-body", id="analyticsBody",
                        **{"data-empty": "加载中…"}),
                ),
            ),
            Div(cls="toasts", id="toasts"),
            Div(cls="ctx-menu", id="ctxMenu"),
            # 技能商店 / MCP 商店自包含组件（对标 业务示例）
            Script(src="/skillstore.js"),
            Script(src="/mcpstore.js"),
            # 错误捕获（在 app.js 之前注入）
            Script('window.__caughtErrors=[];window.addEventListener("error",function(e){window.__caughtErrors.push({type:"error",message:e.message,filename:e.filename,lineno:e.lineno,colno:e.colno,stack:e.error&&e.error.stack?e.error.stack.substring(0,500):""});try{fetch("/api/js-errors",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(window.__caughtErrors[window.__caughtErrors.length-1])})}catch(_){}});window.addEventListener("unhandledrejection",function(e){window.__caughtErrors.push({type:"unhandledrejection",message:e.reason&&e.reason.message?e.reason.message:String(e.reason),stack:e.reason&&e.reason.stack?e.reason.stack.substring(0,500):""});try{fetch("/api/js-errors",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(window.__caughtErrors[window.__caughtErrors.length-1])})}catch(_){}});'),
            # 热重载：开发时监听文件变更自动刷新页面（调试用，生产可移除）
            Script('(function(){var es=new EventSource("/api/hot-reload");es.addEventListener("reload",function(){es.close();location.reload()});es.addEventListener("connected",function(){console.log("[hot-reload] watching static/")});})();'),
            # 入口为原生 ES 模块（零构建）；其 import 的 ./src/*.js 由 static_path 递归服务
            Script(src="/app.js", type="module"),
        ),
    )


# ---------------------------------------------------------------------------
# 健康自检
# ---------------------------------------------------------------------------
