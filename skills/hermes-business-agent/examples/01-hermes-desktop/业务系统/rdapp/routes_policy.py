# -*- coding: utf-8 -*-
"""政策智能校验规则库模块（缺口4.8：可配置规则库，替代10%限额/负面清单硬编码校验）

设计要点：
- PolicyRule 表已存在（db.py），本模块补齐规则库管理 UI + 参数读取服务。
- 版本化：同名规则保留多行（version_no 递增），更新=新版本行，支持回滚。
- get_policy_params()：供 routes_compliance 等读取可配置参数，未配置时回退默认值，
  保证接入后行为与硬编码完全一致（万无一失）。
"""

from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime
import json

from .db import policies_tb, log_audit
from .components import (
    page_layout, data_table, empty_state, stat_block,
)

ar = APIRouter()

now = lambda: datetime.now().strftime("%Y-%m-%d %H:%M")


# ═══════════════════════ 参数读取服务（供其它模块消费） ═══════════════════════

def get_policy_params(caliber: str, key: str, default=None):
    """读取指定口径下启用规则中 key 的参数值；未配置/解析失败时返回 default。

    用法示例：get_policy_params("加计扣除", "other_ratio_max", 0.10)
    """
    try:
        for r in policies_tb(order_by="-version_no"):
            if r.caliber == caliber and r.enabled:
                params = json.loads(r.params) if r.params else {}
                if key in params:
                    return params[key]
    except Exception:
        pass
    return default


def ensure_policy_seed():
    """幂等补齐默认政策规则（负面清单等），供存量库初始化调用，不动已有规则。"""
    try:
        existing = [r for r in policies_tb() if r.caliber == "加计扣除"]
        for r in existing:
            try:
                p = json.loads(r.params) if r.params else {}
            except Exception:
                p = {}
            if "negative_industries" in p:
                return
        policies_tb.insert(
            name="负面清单行业口径",
            caliber="加计扣除",
            params=json.dumps({
                "negative_industries": ["烟草", "住宿和餐饮", "批发和零售", "房地产", "租赁和商务服务", "娱乐"],
            }, ensure_ascii=False),
            description="研发费用加计扣除负面清单行业（财税〔2015〕119号），不得享受加计扣除",
            version_no=1, enabled=True, updated_at=now(),
        )
        log_audit("政策规则", "补齐", detail="初始化负面清单行业规则")
    except Exception:
        pass


# ═══════════════════════ 规则库管理 UI ═══════════════════════

@ar("/policy-rules")
def policy_rules(caliber: str = ""):
    """政策规则库列表（按口径分组，同名规则只显示最新版本）"""
    all_rules = policies_tb(order_by="-version_no")
    # 每个 name 取最新版本
    latest = {}
    for r in all_rules:
        if r.name not in latest:
            latest[r.name] = r
    rules = list(latest.values())
    if caliber:
        rules = [r for r in rules if r.caliber == caliber]
    total = len(latest)
    enabled = len([r for r in latest.values() if r.enabled])
    calibers = sorted(set(r.caliber for r in latest.values()))

    rows = []
    for r in rules:
        status_cls = "badge-green" if r.enabled else "badge-gray"
        status_txt = "启用" if r.enabled else "禁用"
        toggle_url = f"/policy-rules/{r.id}/toggle"
        params_preview = ""
        try:
            p = json.loads(r.params) if r.params else {}
            params_preview = ", ".join(f"{k}={v}" for k, v in list(p.items())[:3])
        except Exception:
            params_preview = ""
        rows.append(
            Tr(
                Td(r.name),
                Td(Span(r.caliber, cls="chip")),
                Td(Span(f"v{r.version_no}", cls="chip")),
                Td(params_preview),
                Td(r.description[:40] + ("..." if len(r.description) > 40 else "")),
                Td(Span(status_txt, cls=status_cls)),
                Td(
                    A("切换", href=toggle_url, cls="btn btn-sm btn-outline"),
                    " ",
                    A("编辑", href=f"/policy-rules/{r.id}/edit", cls="btn btn-sm"),
                    " ",
                    A("版本", href=f"/policy-rules/{r.id}/versions", cls="btn btn-sm btn-outline"),
                ),
            )
        )
    rule_table = Table(
        Thead(Tr(Th("规则名称"), Th("口径"), Th("版本"), Th("参数"), Th("描述"), Th("状态"), Th("操作"))),
        Tbody(*rows), cls="table",
    ) if rows else empty_state("", "暂无规则，请先添加")

    # 新增规则表单
    add_form = Form(
        Div(
            Div(
                Label("规则名称", _for="name"),
                Input(id="name", name="name", required=True, cls="form-input",
                      placeholder="如：加计扣除其他费用限额"),
            ),
            Div(
                Label("口径", _for="caliber"),
                Select(
                    Option("高企认定", value="高企认定"),
                    Option("加计扣除", value="加计扣除"),
                    Option("统计报表", value="统计报表"),
                    id="caliber", name="caliber", cls="form-input",
                ),
            ),
            Div(
                Label("参数(JSON)", _for="params"),
                Textarea(id="params", name="params", rows=2, cls="form-input",
                         placeholder='{"other_ratio_max": 0.1}'),
            ),
            Div(
                Label("描述", _for="description"),
                Textarea(id="description", name="description", rows=2, cls="form-input"),
            ),
            Button("添加规则", type="submit", cls="btn btn-primary"),
            cls="form-grid",
        ),
        action="/policy-rules/add", method="POST",
    )

    # 口径过滤 tabs
    caliber_tabs = Div(
        A("全部", href="/policy-rules", cls=f"tab {'active' if not caliber else ''}"),
        *[A(f"{c}", href=f"/policy-rules?caliber={c}", cls=f"tab {'active' if caliber == c else ''}") for c in calibers],
        cls="tab-row",
    )

    content = Div(
        Div(
            Div(stat_block("规则总数", str(total), "blue"), cls="card"),
            Div(stat_block("已启用", str(enabled), "green"), cls="card"),
            Div(stat_block("已禁用", str(total - enabled), "gray"), cls="card"),
            cls="stats-grid-3",
        ),
        Div(
            H3("新增规则", cls="card-title"),
            add_form, cls="card",
        ),
        Div(
            H3("规则列表", cls="card-title"),
            caliber_tabs,
            rule_table, cls="card",
        ),
        cls="page",
    )
    return page_layout("政策规则库", "首页 / 合规管理 / 政策规则库", "/policy-rules", content)


@ar("/policy-rules/add", methods=["POST"])
def policy_rule_add(name: str, caliber: str, params: str = "{}", description: str = ""):
    """新增规则（首个版本）"""
    try:
        json.loads(params)
    except (json.JSONDecodeError, TypeError):
        params = "{}"
    policies_tb.insert(
        name=name, caliber=caliber, params=params, description=description,
        version_no=1, enabled=True, updated_at=now(),
    )
    log_audit("政策规则", "新增", detail=f"{name}（{caliber}）")
    return RedirectResponse(url="/policy-rules", status_code=303)


@ar("/policy-rules/{rid}/toggle")
def policy_rule_toggle(rid: int):
    """启用/禁用规则（仅最新版本行）"""
    r = policies_tb[rid]
    if r:
        policies_tb.update({"enabled": not r.enabled, "updated_at": now()}, r.id)
        log_audit("政策规则", "切换", detail=f"{r.name}->{'启用' if not r.enabled else '禁用'}")
    return RedirectResponse(url="/policy-rules", status_code=303)


@ar("/policy-rules/{rid}/edit")
def policy_rule_edit(rid: int):
    """编辑规则表单"""
    r = policies_tb[rid]
    if not r:
        return RedirectResponse(url="/policy-rules", status_code=303)
    form = Form(
        Div(
            Div(
                Label("规则名称", _for="name"),
                Input(id="name", name="name", value=r.name, required=True, cls="form-input"),
            ),
            Div(
                Label("口径", _for="caliber"),
                Select(
                    Option("高企认定", value="高企认定", selected=r.caliber == "高企认定"),
                    Option("加计扣除", value="加计扣除", selected=r.caliber == "加计扣除"),
                    Option("统计报表", value="统计报表", selected=r.caliber == "统计报表"),
                    id="caliber", name="caliber", cls="form-input",
                ),
            ),
            Div(
                Label("参数(JSON)", _for="params"),
                Textarea(id="params", name="params", rows=2, cls="form-input"),
            ),
            Div(
                Label("描述", _for="description"),
                Textarea(id="description", name="description", rows=2, cls="form-input"),
            ),
            Input(type="hidden", name="id", value=str(rid)),
            Div(
                P("保存将生成新版本（当前 v{0} → v{1}），历史版本可在「版本」中回滚。".format(r.version_no, r.version_no + 1),
                  cls="text-muted"),
            ),
            Button("保存并升级版本", type="submit", cls="btn btn-primary"),
            A("取消", href="/policy-rules", cls="btn btn-outline"),
            cls="form-grid",
        ),
        action="/policy-rules/update", method="POST",
    )
    content = Div(
        H2("编辑规则", cls="page-title"),
        Div(form, cls="card"),
        cls="page",
    )
    return page_layout("编辑规则", "首页 / 合规管理 / 政策规则库 / 编辑", "/policy-rules", content)


@ar("/policy-rules/update", methods=["POST"])
def policy_rule_update(id: int, name: str, caliber: str,
                       params: str = "{}", description: str = ""):
    """更新规则：插入新版本行（version_no+1），保留历史版本支持回滚"""
    r = policies_tb[id]
    if not r:
        return RedirectResponse(url="/policy-rules", status_code=303)
    try:
        json.loads(params)
    except (json.JSONDecodeError, TypeError):
        params = r.params
    new_version = r.version_no + 1
    policies_tb.insert(
        name=name, caliber=caliber, params=params, description=description,
        version_no=new_version, enabled=r.enabled, updated_at=now(),
    )
    log_audit("政策规则", "更新", detail=f"{name} -> v{new_version}")
    return RedirectResponse(url="/policy-rules", status_code=303)


@ar("/policy-rules/{rid}/versions")
def policy_rule_versions(rid: int):
    """规则版本历史"""
    r = policies_tb[rid]
    if not r:
        return RedirectResponse(url="/policy-rules", status_code=303)
    versions = [x for x in policies_tb() if x.name == r.name]
    versions.sort(key=lambda x: x.version_no, reverse=True)

    rows = []
    for v in versions:
        status_cls = "badge-green" if v.enabled else "badge-gray"
        rows.append(
            Tr(
                Td(Span(f"v{v.version_no}", cls="chip")),
                Td(v.updated_at or "-"),
                Td(Span("启用" if v.enabled else "禁用", cls=status_cls)),
                Td(v.description[:50]),
                Td(
                    Form(
                        Button("回滚到此版本", type="submit", cls="btn btn-sm btn-outline"),
                        Input(type="hidden", name="rid", value=str(rid)),
                        Input(type="hidden", name="vid", value=str(v.id)),
                        action=f"/policy-rules/{rid}/rollback", method="POST",
                    ),
                ),
            )
        )
    vtable = Table(
        Thead(Tr(Th("版本"), Th("更新时间"), Th("状态"), Th("描述"), Th("操作"))),
        Tbody(*rows), cls="table",
    ) if rows else empty_state("", "暂无版本")

    content = Div(
        H2(f"规则版本历史：{r.name}", cls="page-title"),
        Div(P(f"当前生效版本 v{r.version_no}", cls="text-muted"), cls="card"),
        Div(vtable, cls="card"),
        Div(A("返回规则库", href="/policy-rules", cls="btn btn-outline"), cls="page"),
        cls="page",
    )
    return page_layout("版本历史", "首页 / 合规管理 / 政策规则库 / 版本", "/policy-rules", content)


@ar("/policy-rules/{rid}/rollback", methods=["POST"])
def policy_rule_rollback(rid: int, vid: int = 0):
    """回滚到指定版本：复制历史版本参数生成新版本行（version_no 继续递增）"""
    cur = policies_tb[rid]
    if not cur:
        return RedirectResponse(url="/policy-rules", status_code=303)
    target = policies_tb[vid] if vid else None
    if not target:
        return RedirectResponse(url=f"/policy-rules/{rid}/versions", status_code=303)
    new_version = max([x.version_no for x in policies_tb() if x.name == cur.name] or [cur.version_no]) + 1
    policies_tb.insert(
        name=cur.name, caliber=cur.caliber,
        params=target.params, description=f"回滚自 v{target.version_no}：{target.description}",
        version_no=new_version, enabled=True, updated_at=now(),
    )
    log_audit("政策规则", "回滚", detail=f"{cur.name} -> v{new_version}（源自 v{target.version_no}）")
    return RedirectResponse(url="/policy-rules", status_code=303)
