"""routes_roles.py — 项目级角色权限管理（缺口⑨，P2/M6）

依据 rd-governor：
- 模块权限控制：项目经理 / 研发人员 / 观察员三级角色
- 角色用于控制项目数据访问粒度：项目经理可编辑项目与费用；
  研发人员仅可查看本人参与项目；观察员只读

功能：
- /project-roles            项目角色权限总览
- /project-roles/{pid}      单项目角色分配
- /project-roles/{pid}/save 保存角色分配
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import date
from .db import projects_tb, personnel_tb, project_roles_tb, log_audit
from .components import (
    page_layout, data_table, empty_state, alert_box, stat_card, person_options
)

ar = APIRouter()

ROLE_TYPES = ["项目经理", "研发人员", "观察员"]

ROLE_BADGE = {
    "项目经理": "badge-red",
    "研发人员": "badge-green",
    "观察员": "badge-gray",
}


def _project_name(pid):
    try:
        return projects_tb[pid].name if pid else "—"
    except Exception:
        return "—"


def _person_name(pid):
    try:
        return personnel_tb[pid].name if pid else "—"
    except Exception:
        return "—"


@ar("/project-roles")
def project_roles_index():
    """项目角色权限总览"""
    projects = list(projects_tb())
    rows = []
    for p in projects:
        roles = project_roles_tb(where=f"project_id={p.id}")
        pm = [r for r in roles if r.role == "项目经理"]
        rd = [r for r in roles if r.role == "研发人员"]
        obs = [r for r in roles if r.role == "观察员"]
        rows.append([
            p.name,
            Span(f"{len(roles)} 人", cls="badge badge-blue"),
            ", ".join(_person_name(r.person_id) for r in pm) or "—",
            str(len(rd)),
            str(len(obs)),
            A("分配角色", href=f"/project-roles/{p.id}", cls="btn btn-primary btn-sm"),
        ])

    total_roles = len(project_roles_tb())
    return page_layout(
        "项目角色权限", "首页 / 内控与治理 / 项目权限", "/project-roles",
        Div(
            stat_card("项目总数", str(len(projects)), "个", "blue"),
            stat_card("角色分配", str(total_roles), "条记录", "green"),
            stat_card("角色类型", str(len(ROLE_TYPES)), "三级权限", "orange"),
            cls="stat-grid"
        ),
        alert_box(
            "项目级角色权限控制数据访问粒度：项目经理可编辑项目与费用、审批资本化；"
            "研发人员仅可查看本人参与的项目数据；观察员只读。角色分配全程写入审计日志。",
            "info"
        ),
        Div(
            Div("项目角色分配总览", cls="card-title"),
            data_table(["项目", "已分配", "项目经理", "研发人员数", "观察员数", ""], rows)
            if rows else empty_state("🔒", "暂无项目，请先创建研发项目"),
            cls="card"
        )
    )


@ar("/project-roles/{pid}")
def project_roles_detail(pid: int):
    """单项目角色分配"""
    p = projects_tb[pid]
    roles = project_roles_tb(where=f"project_id={pid}")

    # 已分配人员
    assigned_ids = {r.person_id for r in roles}
    avail = [pp for pp in personnel_tb() if pp.id not in assigned_ids]

    rows = [[
        _person_name(r.person_id),
        Span(r.role, cls=f"badge {ROLE_BADGE.get(r.role, 'badge-gray')}"),
        r.created_at or "—",
        A("移除", href=f"/project-roles/{pid}/remove/{r.id}", cls="btn btn-outline btn-sm",
          onclick="return confirm('确认移除该角色？')"),
    ] for r in roles]

    return page_layout(
        f"项目角色权限 · {p.name}", "首页 / 内控与治理 / 项目权限 / 详情", "/project-roles",
        Div(
            Div(
                Span(f"当前角色分配（{len(roles)} 人）"),
                A("← 返回总览", href="/project-roles", cls="btn btn-outline btn-sm"),
                cls="card-title"
            ),
            data_table(["人员", "角色", "分配时间", ""], rows)
            if rows else empty_state("🔒", "该项目尚未分配角色"),
            cls="card"
        ),
        Div(
            Div("新增角色分配", cls="card-title"),
            Form(
                Input(type="hidden", name="pid", value=pid),
                Div(
                    Div(Label("人员", cls="form-label"),
                        Select(*person_options("", "— 选择人员 —"), name="person_id",
                               cls="form-select", required=True), cls="form-group"),
                    Div(Label("角色", cls="form-label"),
                        Select(*[Option(r, value=r, selected=(r == "研发人员")) for r in ROLE_TYPES],
                               name="role", cls="form-select"), cls="form-group"),
                    Div(Button("添加", type="submit", cls="btn btn-primary"),
                        style="align-self:end;"),
                    cls="form-row"
                ),
                method="post", action=f"/project-roles/{pid}/save"
            ),
            cls="card"
        )
    )


@ar("/project-roles/{pid}/save", methods=["POST"])
def project_roles_save(pid: int, person_id: str = "", role: str = "研发人员"):
    if not person_id:
        return RedirectResponse(url=f"/project-roles/{pid}", status_code=303)
    pid_i = int(person_id)
    # 防重复
    dup = [r for r in project_roles_tb(where=f"project_id={pid}") if r.person_id == pid_i]
    if dup:
        dup[0].role = role
        project_roles_tb.update(dup[0])
        log_audit("UPDATE", "project_roles", dup[0].id,
                  f"更新角色：{_person_name(pid_i)} 在《{_project_name(pid)}》 → {role}")
    else:
        rec = project_roles_tb.insert(
            project_id=pid, person_id=pid_i, role=role,
            created_at=date.today().strftime("%Y-%m-%d %H:%M")
        )
        log_audit("CREATE", "project_roles", rec.id,
                  f"分配角色：{_person_name(pid_i)} 在《{_project_name(pid)}》 {role}")
    return RedirectResponse(url=f"/project-roles/{pid}", status_code=303)


@ar("/project-roles/{pid}/remove/{rid}")
def project_roles_remove(pid: int, rid: int):
    r = project_roles_tb[rid]
    log_audit("DELETE", "project_roles", rid,
              f"移除角色：{_person_name(r.person_id)} 从《{_project_name(pid)}》")
    project_roles_tb.delete(rid)
    return RedirectResponse(url=f"/project-roles/{pid}", status_code=303)
