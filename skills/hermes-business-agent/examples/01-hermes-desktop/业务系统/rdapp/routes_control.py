"""routes_control.py — 内控治理中心

对应 rd-governor 工作流 A/B：
  ① 内控成熟度自评（九章节逐项评分 0-5 → 评级 + 差距项，存 ControlAssessment）
  ② 实时合规红线扫描（scan_compliance_risks：其他费用限额 / 委托境外 2/3 / 预算超支 / 负面清单 / 特殊收入冲减）
  ③ 审批权限矩阵可视化
  ④ 数据质量凭证清单（加计扣除 8 项 / 高企 6 项 / IPO 8 项）
"""
import json
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import date

from .db import assessment_tb, evidence_tb, scan_compliance_risks, log_audit
from .components import (
    page_layout, stat_card, data_table, empty_state, alert_box, progress_bar, level_badge
)

ar = APIRouter()

# 内控九章节（对应 internal-control-system.md）
CHAPTERS = [
    ("总则", "明确研发活动定义、适用范围与管理原则"),
    ("组织架构与职责", "研发/财务/决策层职责分离与授权体系"),
    ("立项管理", "立项审批、目标与预算编制、文档留存"),
    ("预算管理", "预算编制、执行监控、超支调整审批"),
    ("归集与核算", "费用归集口径、辅助账、凭证链完整性"),
    ("资本化", "研究/开发阶段划分、资本化条件判定"),
    ("资产与合同", "研发设备、委外/受托合同管理"),
    ("监督与检查", "内部监督、合规自查、整改闭环"),
    ("附则", "制度解释、修订与生效机制"),
]

# 三套证据清单（对应 evidence-checklist.md）
EVIDENCE_SETS = {
    "研发费用加计扣除": [
        "研发项目立项文件", "研发人员名册与工时", "研发费用辅助账",
        "材料领用单与出库记录", "设备折旧/租赁凭证", "委外研发合同与付款凭证",
        "科技成果转化证明", "研发费用归集口径说明",
    ],
    "高新技术企业认定": [
        "知识产权证书", "研发项目立项与验收报告", "研发费用专项审计",
        "科技人员占比证明", "高新收入专项审计", "研发组织管理材料",
    ],
    "IPO 申报": [
        "研发内控制度文件", "研发费用归集政策", "研发工时系统导出",
        "委外研发明细", "资本化判定依据", "关联方研发交易说明",
        "研发费用勾稽底稿", "申报会计师访谈回复",
    ],
}

# 审批权限矩阵（对应 expense-reimbursement-workflow.md）
APPROVAL_MATRIX = [
    ["≤ 1 万", "常规费用（材料/试制/差旅/会议/其他）", "部门负责人"],
    ["≤ 1 万", "委外研发 / 设备购置", "部门负责人"],
    ["> 1 万", "常规费用", "财务总监"],
    ["> 1 万", "委外研发 / 设备购置", "财务总监 + 总经理"],
    ["> 10 万", "常规费用", "总经理 / 总办"],
    ["> 10 万", "委外研发 / 设备购置", "董事会"],
]


def _assess_bars(scores: dict):
    """九章节评分进度条"""
    items = []
    for k, _desc in CHAPTERS:
        v = scores.get(k, 0)
        pct = (v / 5 * 100) if v else 0
        color = "red" if v < 3 else ("orange" if v < 4 else "green")
        items.append(Div(
            Div(f"{k}：{v}/5", style="font-size:12px;margin-bottom:4px;"),
            progress_bar(pct, color),
            style="margin-bottom:10px;",
        ))
    return Div(*items)


@ar("/control")
def control():
    """内控治理中心首页"""
    # ① 最新内控成熟度自评
    all_assess = list(assessment_tb())
    latest = all_assess[-1] if all_assess else None
    if latest:
        try:
            sc = json.loads(latest.scores)
        except Exception:
            sc = {}
        latest_card = Div(
            Div(f"最新评级：{latest.maturity}（{latest.total_score:.0f}/45）", cls="card-title"),
            Div(f"评估人：{latest.assessor} ｜ 时间：{latest.ts}",
                style="font-size:12px;color:var(--text-muted);margin-bottom:10px;"),
            _assess_bars(sc),
            cls="card"
        )
    else:
        latest_card = Div(
            Div("内控成熟度自评", cls="card-title"),
            empty_state("📊", "尚未进行自评，请在下方提交一次自评快照"),
            cls="card"
        )

    # 自评表单
    score_inputs = []
    for i, (k, desc) in enumerate(CHAPTERS):
        score_inputs.append(Div(
            Label(f"{i+1}. {k}", cls="form-label", title=desc),
            Div(desc, style="font-size:11px;color:var(--text-muted);margin-bottom:4px;"),
            Input(name=f"s{i}", type="number", min="0", max="5", step="1",
                  value="0", cls="form-input", style="max-width:120px;"),
            cls="form-group"
        ))
    assess_form = Form(
        Div(Label("评估人", cls="form-label"), Input(name="assessor", cls="form-input"), cls="form-group"),
        Div(*score_inputs, style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;"),
        Div(Label("整体说明", cls="form-label"),
            Textarea(name="note", cls="form-textarea", placeholder="自评结论与改进方向..."), cls="form-group"),
        Div(Button("保存自评快照", type="submit", cls="btn btn-primary"), style="display:flex;gap:10px;"),
        method="post", action="/control/assess"
    )

    # ② 实时合规红线扫描
    risks = scan_compliance_risks()
    risk_rows = [[
        level_badge(r["level"]), r["type"], r["project"],
        r["description"], r["citation"], r["suggestion"],
    ] for r in risks]
    risk_card = Div(
        Div("实时合规红线扫描", cls="card-title"),
        data_table(
            ["等级", "风险类型", "关联对象", "说明", "政策依据", "整改建议"],
            risk_rows
        ) if risk_rows else alert_box("当前未发现可计算的合规红线风险，系统将持续监控。", "success"),
        cls="card"
    )

    # ③ 审批权限矩阵可视化
    matrix_rows = [[a, b, c] for a, b, c in APPROVAL_MATRIX]
    matrix_card = Div(
        Div("审批权限矩阵（金额分级 + 费用类型）", cls="card-title"),
        data_table(["金额区间", "费用类型", "所需批准层级"], matrix_rows),
        cls="card"
    )

    # ④ 数据质量凭证清单
    ev_by_type = {}
    for e in evidence_tb():
        ev_by_type[e.ev_type] = ev_by_type.get(e.ev_type, 0) + 1
    ev_cards = []
    for set_name, items in EVIDENCE_SETS.items():
        li = []
        for it in items:
            cnt = ev_by_type.get(it, 0)
            mark = "✅" if cnt > 0 else "⬜"
            li.append(Li(f"{mark} {it}（系统已有 {cnt} 份）", style="font-size:13px;margin:3px 0;"))
        ev_cards.append(Div(
            Div(set_name, cls="card-title"),
            Ul(*li, style="list-style:none;padding-left:0;margin:0;"),
            cls="card"
        ))
    ev_grid = Div(*ev_cards, style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;")

    # 统计
    ev_total = len(evidence_tb())
    assess_cnt = len(all_assess)
    high_risk = sum(1 for r in risks if r["level"] == "高")

    return page_layout(
        "内控治理中心", "首页 / 内控治理中心", "/control",
        Div(
            stat_card("合规红线风险", str(len(risks)), f"高危 {high_risk} 项", "red"),
            stat_card("系统内凭证", str(ev_total), "证据材料总数", "blue"),
            stat_card("自评快照", str(assess_cnt), "历史评估次数", "green"),
            stat_card("内控章节", "9", "成熟度评分维度", "orange"),
            cls="stat-grid",
        ),
        Div(Div("一、内控成熟度自评", cls="section-title"), latest_card,
            Div(Div("提交新的自评快照", cls="card-title"), assess_form, cls="card")),
        Div(Div("二、实时合规红线扫描", cls="section-title"), risk_card),
        Div(Div("三、审批权限矩阵", cls="section-title"), matrix_card),
        Div(Div("四、数据质量凭证清单", cls="section-title"), ev_grid),
    )


@ar("/control/assess", methods=["POST"])
def control_assess(assessor: str = "", note: str = "",
                   s0: str = "0", s1: str = "0", s2: str = "0", s3: str = "0",
                   s4: str = "0", s5: str = "0", s6: str = "0", s7: str = "0", s8: str = "0"):
    """保存一次内控成熟度自评快照"""
    raw = [s0, s1, s2, s3, s4, s5, s6, s7, s8]
    scores = {}
    total = 0
    for i, (k, _desc) in enumerate(CHAPTERS):
        try:
            v = int(float(raw[i] or 0))
        except (ValueError, TypeError):
            v = 0
        v = max(0, min(5, v))
        scores[k] = v
        total += v

    if total >= 40:
        maturity = "成熟"
    elif total >= 30:
        maturity = "规范"
    elif total >= 18:
        maturity = "基础"
    else:
        maturity = "初创"

    gaps = [k for k, v in scores.items() if v < 3]

    assessment_tb.insert(
        ts=date.today().strftime("%Y-%m-%d %H:%M"),
        assessor=assessor, scores=json.dumps(scores, ensure_ascii=False),
        total_score=total, maturity=maturity,
        gaps=json.dumps(gaps, ensure_ascii=False), note=note,
    )
    log_audit("CREATE", "assessment", 0,
              detail=f"内控成熟度自评：{maturity}（{total}/45），差距 {len(gaps)} 项",
              actor=assessor or "系统")
    return RedirectResponse(url="/control", status_code=303)
