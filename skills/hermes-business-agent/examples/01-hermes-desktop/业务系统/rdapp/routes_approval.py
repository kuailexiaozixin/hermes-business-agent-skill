"""routes_approval.py — 审批工作流（审批权限矩阵 + 职责分离 + 审计留痕）

对应 rd-governor 工作流 A《研发费用报销审批流程》：
  - 审批权限矩阵：按金额分级 + 费用类型，确定所需批准层级（部门/总办/董事会）
  - 强制职责分离：复核人 ≠ 提交人；批准人 ≠ 提交人 且 ≠ 复核人
  - 所有状态流转写入审计日志，满足"有据可查、可审计"红线
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import date

from .db import (
    projects_tb, approval_tb, log_audit, approval_level_for_amount
)
from .components import (
    page_layout, stat_card, data_table, empty_state, alert_box, status_badge
)

ar = APIRouter()

_SUBJECT_OPTIONS = (
    "材料费", "试制费", "差旅费", "会议费", "其他费用",
    "委托外部研究费用", "设备购置费", "研发设备", "委外研发费",
)


def _level_badge(level: str):
    """审批层级徽章（部门/总办/董事会）"""
    color_map = {"部门": "badge-blue", "总办": "badge-purple", "董事会": "badge-red"}
    cls = color_map.get(level, "badge-gray")
    return Span(level or "—", cls=f"badge {cls}")


@ar("/approval")
def approval(msg: str = ""):
    """审批工作流首页 — 审批单列表 + 新建审批事项"""
    reqs = list(approval_tb())[::-1]
    rows = []
    for r in reqs:
        pname = projects_tb[r.project_id].name if r.project_id else "—"
        rows.append([
            f"#{r.id}",
            r.submitter or "—",
            pname,
            f"¥{r.amount:,.0f}",
            r.subject or "—",
            _level_badge(r.approval_level),
            status_badge(r.status),
            A("查看", href=f"/approval/{r.id}", cls="btn btn-sm btn-outline"),
        ])

    pending = sum(1 for r in reqs if r.status in ("待复核", "已复核"))
    approved = sum(1 for r in reqs if r.status == "已批准")
    closed = sum(1 for r in reqs if r.status in ("已驳回", "已撤回"))

    proj_options = [Option("— 不关联项目 —", value="0")] + \
        [Option(f"{p.code} {p.name}", value=p.id) for p in projects_tb()]
    subj_options = [Option(s, value=s) for s in _SUBJECT_OPTIONS]

    new_form = Form(
        Div(Label("经办人（提交人）", cls="form-label"),
            Input(name="submitter", cls="form-input", required=True), cls="form-group"),
        Div(Label("关联项目", cls="form-label"),
            Select(*proj_options, name="project_id", cls="form-select"), cls="form-group"),
        Div(Label("费用类别", cls="form-label"),
            Select(*subj_options, name="subject", cls="form-select"), cls="form-group"),
        Div(Label("金额（元）", cls="form-label"),
            Input(name="amount", type="number", step="0.01", cls="form-input", required=True), cls="form-group"),
        Div(Label("事项说明", cls="form-label"),
            Textarea(name="description", cls="form-textarea", placeholder="如：采购研发测试设备一台"), cls="form-group"),
        Div(Button("提交审批", type="submit", cls="btn btn-primary"),
            style="display:flex;gap:10px;"),
        method="post", action="/approval/submit"
    )

    msgs = {
        "segregation_review": ("职责分离校验未通过：复核人不能与提交人为同一人。", "danger"),
        "segregation_approve": ("职责分离校验未通过：批准人不能与提交人或复核人为同一人。", "danger"),
    }
    alert = ""
    if msg in msgs:
        alert = alert_box(msgs[msg][0], msgs[msg][1])

    return page_layout(
        "审批工作流", "首页 / 审批工作流", "/approval",
        alert,
        Div(
            stat_card("审批单总数", str(len(reqs)), f"待处理 {pending} 单", "blue"),
            stat_card("待复核", str(sum(1 for r in reqs if r.status == "待复核")), "待部门复核", "orange"),
            stat_card("已批准", str(approved), "流程完成", "green"),
            stat_card("已驳回/撤回", str(closed), "未通过", "red"),
            cls="stat-grid",
        ),
        Div(Div("新建审批事项", cls="card-title"), new_form, cls="card"),
        Div(
            Div("审批事项列表", cls="card-title"),
            data_table(
                ["编号", "经办人", "项目", "金额", "费用类别", "所需层级", "状态", "操作"],
                rows
            ) if rows else empty_state("📝", "暂无审批事项"),
            cls="card",
        ),
    )


@ar("/approval/submit", methods=["POST"])
def approval_submit(submitter: str, project_id: str = "0", subject: str = "",
                    amount: str = "0", description: str = ""):
    """提交新的审批事项：自动计算所需批准层级"""
    pid = int(project_id) if str(project_id).isdigit() and project_id not in ("", "0") else 0
    try:
        amt = float(amount or 0)
    except ValueError:
        amt = 0.0
    level, _note = approval_level_for_amount(amt, subject)
    row = approval_tb.insert(
        submitter=submitter, project_id=pid, amount=amt, subject=subject,
        description=description, status="待复核", approval_level=level,
        submitted_at=date.today().strftime("%Y-%m-%d"),
    )
    log_audit("CREATE", "approval", row.id,
              detail=f"提交审批事项 ¥{amt:,.0f}（{subject}），所需层级：{level}",
              actor=submitter or "系统")
    return RedirectResponse(url=f"/approval/{row.id}", status_code=303)


def _get_approval(rid: int):
    """安全取审批记录：不存在返回 None，避免空表/无效 ID 触发 500。"""
    try:
        return approval_tb[rid]
    except Exception:
        return None

@ar("/approval/{rid}")
def approval_detail(rid: int, msg: str = ""):
    """审批事项详情 — 信息展示 + 按状态推进的操作表单"""
    r = _get_approval(rid)
    if r is None:
        return page_layout(
            f"审批详情 #{rid}", "首页 / 审批工作流 / 详情", "/approval",
            alert_box(f"审批事项 #{rid} 不存在或已被删除。", "danger"),
        )
    pname = projects_tb[r.project_id].name if r.project_id else "（不关联项目）"

    info = Div(
        _kv("经办人", r.submitter or "—"),
        _kv("关联项目", pname),
        _kv("费用类别", r.subject or "—"),
        _kv("金额", f"¥{r.amount:,.0f}"),
        _kv("所需层级", _level_badge(r.approval_level)),
        _kv("当前状态", status_badge(r.status)),
        _kv("事项说明", r.description or "—"),
        style="display:grid;grid-template-columns:1fr 1fr;gap:10px 24px;",
    )

    actions = []
    if r.status == "待复核":
        actions.append(Form(
            Div(Label("复核人（部门负责人）", cls="form-label"),
                Input(name="reviewer", cls="form-input", required=True), cls="form-group"),
            Div(Label("复核意见", cls="form-label"),
                Textarea(name="note", cls="form-textarea"), cls="form-group"),
            Div(Button("复核通过", type="submit", cls="btn btn-primary"),
                style="display:flex;gap:10px;"),
            method="post", action=f"/approval/{rid}/review"
        ))
        actions.append(A("打回（复核不通过）", href=f"/approval/{rid}/reject",
                         cls="btn btn-danger btn-sm"))
    elif r.status == "已复核":
        actions.append(Form(
            Div(Label("批准人", cls="form-label"),
                Input(name="approver", cls="form-input", required=True), cls="form-group"),
            Div(Label("批准意见", cls="form-label"),
                Textarea(name="note", cls="form-textarea"), cls="form-group"),
            Div(Button("批准", type="submit", cls="btn btn-success"),
                A("驳回", href=f"/approval/{rid}/reject", cls="btn btn-danger btn-sm"),
                style="display:flex;gap:10px;"),
            method="post", action=f"/approval/{rid}/approve"
        ))
    else:
        actions.append(alert_box("该审批事项已结案（已批准 / 已驳回 / 已撤回）。", "info"))

    if r.status in ("待复核", "已复核"):
        actions.append(A("撤回本单", href=f"/approval/{rid}/withdraw", cls="btn btn-outline btn-sm"))

    msgs = {
        "segregation_review": ("职责分离校验未通过：复核人不能与提交人为同一人。", "danger"),
        "segregation_approve": ("职责分离校验未通过：批准人不能与提交人或复核人为同一人。", "danger"),
    }
    alert = alert_box(msgs[msg][0], msgs[msg][1]) if msg in msgs else ""

    return page_layout(
        f"审批详情 #{rid}", "首页 / 审批工作流 / 详情", "/approval",
        alert,
        Div(Div("审批事项信息", cls="card-title"), info, cls="card"),
        Div(Div("审批操作", cls="card-title"), *actions, cls="card") if actions else Div(),
        Div(Div("职责分离说明", cls="card-title"),
            alert_box("根据《研发费用报销审批流程》：复核人不得为提交人本人；批准人不得为提交人或复核人本人。"
                      "系统在执行复核/批准时自动校验，违反则拒绝操作并记录，确保关键岗位相互制约。", "warning"),
            cls="card"),
    )


@ar("/approval/{rid}/review", methods=["POST"])
def approval_review(rid: int, reviewer: str, note: str = ""):
    """部门复核：校验复核人 ≠ 提交人"""
    r = _get_approval(rid)
    if r is None:
        return RedirectResponse(url="/approval", status_code=303)
    if r.status != "待复核":
        return RedirectResponse(url=f"/approval/{rid}", status_code=303)
    if (reviewer or "").strip() == (r.submitter or "").strip():
        return RedirectResponse(url=f"/approval/{rid}?msg=segregation_review", status_code=303)
    r.reviewer = reviewer
    r.note = note
    r.status = "已复核"
    r.reviewed_at = date.today().strftime("%Y-%m-%d")
    approval_tb.update(r)
    log_audit("REVIEW", "approval", r.id,
              detail=f"部门复核通过，复核人：{reviewer}", actor=reviewer or "系统")
    return RedirectResponse(url=f"/approval/{rid}", status_code=303)


@ar("/approval/{rid}/approve", methods=["POST"])
def approval_approve(rid: int, approver: str, note: str = ""):
    """分级批准：校验批准人 ≠ 提交人 且 ≠ 复核人"""
    r = _get_approval(rid)
    if r is None:
        return RedirectResponse(url="/approval", status_code=303)
    if r.status != "已复核":
        return RedirectResponse(url=f"/approval/{rid}", status_code=303)
    submitter = (r.submitter or "").strip()
    reviewer = (r.reviewer or "").strip()
    if (approver or "").strip() in (submitter, reviewer):
        return RedirectResponse(url=f"/approval/{rid}?msg=segregation_approve", status_code=303)
    r.approver = approver
    r.note = (r.note or "") + (f" | 批准意见：{note}" if note else "")
    r.status = "已批准"
    r.decided_at = date.today().strftime("%Y-%m-%d")
    approval_tb.update(r)
    log_audit("APPROVE", "approval", r.id,
              detail=f"批准（层级：{r.approval_level}），批准人：{approver}", actor=approver or "系统")
    return RedirectResponse(url=f"/approval/{rid}", status_code=303)


@ar("/approval/{rid}/reject")
def approval_reject(rid: int):
    """驳回（复核或批准阶段均可）"""
    r = _get_approval(rid)
    if r is None:
        return RedirectResponse(url="/approval", status_code=303)
    if r.status in ("已批准", "已驳回", "已撤回"):
        return RedirectResponse(url=f"/approval/{rid}", status_code=303)
    r.status = "已驳回"
    r.decided_at = date.today().strftime("%Y-%m-%d")
    approval_tb.update(r)
    log_audit("REJECT", "approval", r.id,
              detail="审批被驳回", actor=(r.reviewer or r.submitter or "系统"))
    return RedirectResponse(url=f"/approval/{rid}", status_code=303)


@ar("/approval/{rid}/withdraw")
def approval_withdraw(rid: int):
    """撤回未结案的审批单"""
    r = _get_approval(rid)
    if r is None:
        return RedirectResponse(url="/approval", status_code=303)
    if r.status in ("待复核", "已复核"):
        r.status = "已撤回"
        approval_tb.update(r)
        log_audit("WITHDRAW", "approval", r.id,
                  detail="审批单撤回", actor=r.submitter or "系统")
    return RedirectResponse(url="/approval", status_code=303)


def _kv(label: str, value):
    """键值展示单元"""
    return Div(
        Div(label, style="font-size:12px;color:var(--text-muted);margin-bottom:2px;"),
        Div(value, style="font-size:14px;font-weight:500;"),
    )
