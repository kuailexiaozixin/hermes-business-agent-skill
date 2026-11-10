"""app.py — 研发费用管理系统主应用

FastHTML 路由与页面逻辑入口。
模块结构：
  app.py        — 主应用、布局、仪表盘
  db.py          — 数据库模型与种子数据
  components.py  — 共享 UI 组件
  routes_*.py    — 各功能模块路由
"""
from fasthtml.common import *
import sys
from pathlib import Path
from .db import (
    subjects_tb, personnel_tb, projects_tb, expenses_tb, risks_tb,
    approval_tb, audit_tb
)
from .components import (
    APP_CSS, page_layout, stat_card, status_badge, level_badge,
    data_table, empty_state, progress_bar
)
from .routes_base import ar as base_ar
from .routes_projects import ar as projects_ar
from .routes_process import ar as process_ar
from .routes_expenses import ar as expenses_ar
from .routes_compliance import ar as compliance_ar
from .routes_worktime import ar as worktime_ar
from .routes_equipment import ar as equipment_ar
from .routes_materials import ar as materials_ar
from .routes_outsourcing import ar as outsourcing_ar
from .routes_others import ar as others_ar
from .routes_segregation import ar as segregation_ar
from .routes_special_income import ar as special_income_ar
# rd 自研 Agent 相关路由（settings/kanban/market/agent）已废弃删除。
# 融合模式下由 Agent系统（底座）提供；独立模式（纯业务）不再加载任何 rd 自研 Agent 路由。

from .routes_approval import ar as approval_ar
from .routes_audit import ar as audit_ar
from .routes_control import ar as control_ar
from .routes_personnel import ar as personnel_ar
from .routes_import import ar as import_ar
from .routes_report import ar as report_ar
from .routes_sharing import ar as sharing_ar
from .routes_ai import ar as ai_ar
from .routes_evidence import ar as evidence_ar
from .routes_datacenter import ar as datacenter_ar
from .routes_risk import ar as risk_ar
from .routes_org import ar as org_ar
from .routes_reporting import ar as reporting_ar
from .routes_roles import ar as roles_ar
from .routes_patent import ar as patent_ar
from .routes_policy import ar as policy_ar, ensure_policy_seed

# ── 静态资源目录（frozen-aware 绝对路径）──────────────────
# 说明：fasthtml 的静态路由用 FileResponse(f'{static_path}/{fname}')，
# 传相对路径会按运行时 CWD 解析，onefile EXE 下必然 404。
# 故必须给绝对路径：冻结态指向 _MEIPASS/src/rdapp/static，开发态指向本包 static/。
if getattr(sys, "frozen", False):
    _STATIC_DIR = str(Path(sys._MEIPASS) / "src" / "rdapp" / "static")
else:
    _STATIC_DIR = str(Path(__file__).parent / "static")

# ── 头部：本地化 default_hdrs ──
# default_hdrs=False 关闭框架默认的 5 个 jsdelivr CDN 引用；
# 下面手动复刻 charset/viewport + 本地 htmx/fasthtml-js/surreal/css-scope-inline，
# 用本地 Script(src=...) 引用 static/vendor/ 内已 vendored 的文件（非删除、非 CDN）。
_HDRS = (
    Meta(charset="utf-8"),
    Meta(name="viewport",
         content="width=device-width, initial-scale=1, viewport-fit=cover"),
    Script(src="/vendor/htmx.min.js"),
    Script(src="/vendor/fasthtml.js"),
    Script(src="/vendor/surreal.js"),
    Script(src="/vendor/css-scope-inline.js"),
    Style(APP_CSS),
)

# ── app 构建与路由挂载（纯业务，不依赖 Agent 系统）──
# 融合模式：连接系统 bridge 把业务路由挂载到 Agent 底座 app 上（含 Agent 对话）。
# 独立模式：业务系统自建 FastHTML app，只挂纯业务路由。
# 通过环境变量 RD_BIZ_STANDALONE=1 可强制独立模式（例如打包验证时）。

def _build_fastapp():
    """构建纯业务 FastHTML app（独立模式 / 业务独立 EXE 用）。"""
    from fasthtml.common import fast_app
    _a, _rt = fast_app(
        pico=False, htmx=False, live=False,
        title="研发费用管理系统",
        static_path=_STATIC_DIR,
        default_hdrs=False,
    )
    _a.hdrs = tuple(getattr(_a, "hdrs", ()) or ()) + _HDRS
    return _a, _rt

def mount_rd_routes(_a, _rt):
    """把 rd 纯业务路由挂载到指定 app/rt。
    独立模式：挂到自建 app；融合模式：由连接系统 bridge 传入 Agent 底座 app/rt。"""
    base_ar.to_app(_a)
    # org_ar 必须在 projects_ar 之前挂载：其 /projects/cross-org、
    # /projects/duplicate-check 路由会被 projects_ar 的 /projects/{pid}
    # （pid 为 str 类型）抢先 FULL 匹配，导致 404。前置可避免被拦截。
    org_ar.to_app(_a)
    projects_ar.to_app(_a)
    process_ar.to_app(_a)
    expenses_ar.to_app(_a)
    compliance_ar.to_app(_a)
    worktime_ar.to_app(_a)
    equipment_ar.to_app(_a)
    materials_ar.to_app(_a)
    outsourcing_ar.to_app(_a)
    others_ar.to_app(_a)
    segregation_ar.to_app(_a)
    special_income_ar.to_app(_a)
    approval_ar.to_app(_a)
    audit_ar.to_app(_a)
    control_ar.to_app(_a)
    personnel_ar.to_app(_a)
    import_ar.to_app(_a)
    report_ar.to_app(_a)
    sharing_ar.to_app(_a)
    ai_ar.to_app(_a)
    evidence_ar.to_app(_a)
    datacenter_ar.to_app(_a)
    risk_ar.to_app(_a)
    reporting_ar.to_app(_a)
    roles_ar.to_app(_a)
    patent_ar.to_app(_a)
    policy_ar.to_app(_a)
    ensure_policy_seed()
    _rt("/close/{modal_id}")(_modal_close)
    _rt("/dashboard")(_dashboard)
    _rt("/")(lambda: RedirectResponse(url="/dashboard", status_code=302))

def get_business_snapshot() -> str:
    """生成业务数据快照（融合模式下由连接系统注入 Agent 对话上下文）。"""
    try:
        projects = projects_tb(); expenses = expenses_tb()
        risks = risks_tb(); personnel = personnel_tb(); subjects = subjects_tb()
        total_expense = sum(e.amount for e in expenses)
        proj_summary = []
        for p in projects:
            pe = [e for e in expenses if e.project_id == p.id]
            proj_summary.append(
                f"- {p.name}（{p.code}）：状态 {p.status}，预算 ¥{p.budget:,.0f}，"
                f"已归集费用 ¥{sum(e.amount for e in pe):,.0f}，负责人 {p.manager}"
            )
        subj_summary = []
        for s in subjects:
            se = [e for e in expenses if e.subject_id == s.id]
            if se:
                subj_summary.append(
                    f"- {s.code} {s.name}：合计 ¥{sum(e.amount for e in se):,.0f}，"
                    f"{'可资本化' if getattr(s,'capitalizable',False) else '费用化'}"
                )
        risk_summary = [f"- [{r.level}] {r.risk_type}：{r.description}" for r in risks]
        lines = [
            "## 当前系统数据快照",
            f"- 项目总数：{len(projects)}",
            f"- 费用记录数：{len(expenses)}，总金额：¥{total_expense:,.0f}",
            f"- 人员档案数：{len(personnel)}",
            f"- 未处理风险数：{len([r for r in risks if r.status == '待处理'])}",
            "", "### 项目概览",
            *(proj_summary or ["暂无项目数据"]), "",
            "### 费用科目分布",
            *(subj_summary or ["暂无费用数据"]), "",
            "### 风险预警",
            *(risk_summary or ["暂无风险记录"]),
        ]
        data = "\n".join(lines)
    except Exception as _e:
        data = f"（业务数据快照不可用：{_e}）"
    guidance = (
        "\n\n## 智能制度生成能力（内化）\n"
        "本系统具备两项 AI 自改造能力，用户提出「梳理研发流程管理制度 / 编制研发费用内控制度 / "
        "帮我做一套研发管理制度 / 完善研发制度 / 生成制度」时，必须调用 `generate_rd_policy` 工具"
        "（policy_type=process 生成研发流程管理制度；internal_control 生成研发费用内部控制制度），"
        "工具会返回企业资料 + 制度模板骨架 + 生成指引，据此用 write_file 写 output/ 正式制度文件。\n"
        "原则：不改变企业现有研发管理，只嵌入财税合规要求；明确区分 研究/开发阶段、资本化/费用化、"
        "研发/生产 三对边界；内控制度体现完整证据链（立项→预算→归集→资本化→验收→归档每节点留痕）。"
    )
    return data + guidance

# 业务系统独立运行（biz_main / 独立 EXE）时自建纯业务 app；融合模式由连接系统 bridge 装配。
app, rt = _build_fastapp()


# （rd 自研 Agent 路由 settings/kanban/market 已废弃删除，独立模式不再挂载）



# ── 模态框关闭路由 ───────────────────────────────────────
# modal_dialog 的 × 按钮向 /close/{modal_id} 发起 HTMX 请求，
# hx_target=#{modal_id} + hx_swap=outerHTML，故返回空内容即可把整个 overlay 从 DOM 移除。
def _modal_close(modal_id: str):
    return ""


# ── 健康检查 ── 01 底座已提供 /healthz（详见 routes/chat.py），此处移除 rd 重复定义以避免路由冲突。


# ── 仪表盘 ──────────────────────────────────────────────

def _dashboard():
    """仪表盘 — 研发全景概览（功能模块，首页见 Agent 对话 /）"""
    all_projects = projects_tb()
    active_projects = [p for p in all_projects if p.status == "进行中"]
    all_expenses = expenses_tb()
    all_risks = risks_tb()
    pending_risks = [r for r in all_risks if r.status == "待处理"]
    pending_approval = len(list(approval_tb(where="status='待复核' OR status='已复核'")))
    audit_count = len(list(audit_tb()))

    # 费用统计
    total_expense = sum(e.amount for e in all_expenses)
    research_expense = sum(e.amount for e in all_expenses if e.phase == "研究")
    develop_expense = sum(e.amount for e in all_expenses if e.phase == "开发")
    capitalized = sum(e.amount for e in all_expenses if e.capitalize_status == "待资本化")

    # 预算统计
    total_budget = sum(p.budget for p in all_projects)
    budget_used = sum(e.amount for e in all_expenses)

    # 各项目费用概览
    project_rows = []
    for p in all_projects:
        proj_expenses = [e for e in all_expenses if e.project_id == p.id]
        used = sum(e.amount for e in proj_expenses)
        pct = (used / p.budget * 100) if p.budget > 0 else 0
        bar_color = "red" if pct > 90 else ("orange" if pct > 70 else "green")
        project_rows.append([
            p.code,
            A(p.name, href=f"/projects/{p.id}", style="color:var(--primary);text-decoration:none;font-weight:500;"),
            p.manager,
            f"¥{p.budget:,.0f}",
            f"¥{used:,.0f}",
            progress_bar(pct, bar_color),
            f"{pct:.1f}%",
            status_badge(p.status),
        ])

    # 近期风险
    risk_rows = []
    for r in pending_risks[:5]:
        proj = projects_tb[r.project_id] if r.project_id else None
        risk_rows.append([
            level_badge(r.level),
            r.risk_type,
            proj.name if proj else "—",
            r.description[:40] + "..." if len(r.description) > 40 else r.description,
            status_badge(r.status),
        ])

    return page_layout(
        "仪表盘", "首页 / 仪表盘", "/dashboard",
        # 统计卡片
        Div(
            stat_card("研发项目总数", str(len(all_projects)), f"进行中 {len(active_projects)} 个", "blue"),
            stat_card("研发费用总额", f"¥{total_expense:,.0f}", f"预算 ¥{total_budget:,.0f}", "green"),
            stat_card("待资本化金额", f"¥{capitalized:,.0f}", f"开发阶段 ¥{develop_expense:,.0f}", "orange"),
            stat_card("待处理风险", str(len(pending_risks)), f"高风险 {sum(1 for r in pending_risks if r.level=='高')} 个", "red"),
            stat_card("待审批事项", str(pending_approval), "待复核/已复核", "orange"),
            stat_card("操作日志", str(audit_count), "全系统留痕", "blue"),
            cls="stat-grid"
        ),
        # 费用结构
        Div(
            Div("研发费用结构分析", cls="card-title"),
            Div(
                Div(
                    Div("研究阶段（费用化）", style="font-size:12px;color:var(--text-muted);margin-bottom:4px;"),
                    Div(f"¥{research_expense:,.0f}", style="font-size:22px;font-weight:700;color:var(--phase-research);"),
                    progress_bar(research_expense / total_expense * 100 if total_expense > 0 else 0, ""),
                    style="flex:1;"
                ),
                Div(
                    Div("开发阶段（待资本化）", style="font-size:12px;color:var(--text-muted);margin-bottom:4px;"),
                    Div(f"¥{develop_expense:,.0f}", style="font-size:22px;font-weight:700;color:var(--phase-develop);"),
                    progress_bar(develop_expense / total_expense * 100 if total_expense > 0 else 0, "green"),
                    style="flex:1;"
                ),
                style="display:flex;gap:24px;"
            ),
            cls="card"
        ),
        # 项目概览表格
        Div(
            Div(
                Span("项目费用概览"),
                A("查看全部 →", href="/projects", style="font-size:12px;color:var(--primary);text-decoration:none;"),
                cls="card-title"
            ),
            data_table(
                ["项目编号", "项目名称", "负责人", "总预算", "已使用", "预算执行率", "执行率", "状态"],
                project_rows
            ) if project_rows else empty_state("📋", "暂无项目数据"),
            cls="card"
        ),
        # 近期风险
        Div(
            Div(
                Span("近期风险预警"),
                A("查看全部 →", href="/risks", style="font-size:12px;color:var(--primary);text-decoration:none;"),
                cls="card-title"
            ),
            data_table(
                ["等级", "风险类型", "关联项目", "风险描述", "状态"],
                risk_rows
            ) if risk_rows else empty_state("✓", "暂无风险预警"),
            cls="card"
        ),
    )

# 融合/独立均已定义 app，此处执行挂载（必须在上述函数定义之后）
mount_rd_routes(app, rt)


# ── 风控规则自动扫描（缺口⑩-a 自动预警增强）────────────────────
# 独立/融合模式共用：应用启动 30 秒后执行首次扫描，此后每 6 小时自动扫描一次。
# 复用 routes_risk.risk_scan()，仅做定时调度，不重复实现规则逻辑；
# 全程 try/except 兜底，扫描异常不影响业务主进程。
def start_risk_auto_scan():
    """启动风控自动扫描后台线程（幂等，可被融合模式 bridge 复用）。"""
    import threading

    def _loop():
        try:
            from .routes_risk import risk_scan
            risk_scan()
        except Exception:
            pass
        threading.Timer(6 * 3600, _loop).start()

    threading.Timer(30, _loop).start()


app.on_event("startup")(start_risk_auto_scan)
