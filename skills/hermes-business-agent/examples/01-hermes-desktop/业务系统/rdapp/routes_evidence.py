"""routes_evidence.py — 凭证管理与备查文件（缺口⑦⑫）

功能：
- 凭证挂接：Expense 记录关联 EvidenceDoc 凭证文件（PDF/JPG）
- 备查文件管理：按类型分类，上传/查看/删除
- 辅助账自动生成：按加计扣除辅助账模板格式，按月/科目汇总
- 留存备查资料包一键打包：ZIP 含辅助账 + 凭证文件 + 汇总清单
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime, date
from pathlib import Path
from urllib.parse import quote
import csv, io, os, zipfile

from .db import (
    expenses_tb, projects_tb, evidence_docs_tb, evidence_tb, log_audit,
    subjects_tb, work_time_tb, equipment_depreciation_tb, material_requisition_tb,
)
from .components import (
    page_layout, stat_card, data_table, empty_state, alert_box, stat_block,
)

ar = APIRouter()

EVI_DIR = Path(__file__).parent / "evidence_docs"
EVI_DIR.mkdir(exist_ok=True)

CALIBER_FILTER = "加计扣除"  # 辅助账默认口径


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _today():
    return date.today().strftime("%Y-%m-%d")


# ── 辅助账 ──────────────────────────────────────────────
def _aux_account_data(project_id: int = 0, caliber: str = CALIBER_FILTER):
    """按期间/科目汇总，生成辅助账数据。"""
    from collections import defaultdict
    monthly = defaultdict(lambda: defaultdict(float))
    total = 0.0
    for e in expenses_tb():
        if project_id and e.project_id != project_id:
            continue
        if caliber and caliber not in (e.caliber or ""):
            continue
        month = (e.expense_date or "")[:7]
        if not month:
            continue
        monthly[month][e.subject_name or "未分类"] += e.amount
        total += e.amount
    rows = []
    running = 0.0
    for m in sorted(monthly.keys()):
        for sname in sorted(monthly[m].keys()):
            amt = monthly[m][sname]
            running += amt
            rows.append([m, sname, f"¥{amt:,.2f}", f"¥{running:,.2f}", ""])
        rows.append(["", "小计", f"¥{sum(monthly[m].values()):,.2f}", f"¥{running:,.2f}", ""])
    return rows, total


# ── 首页 ──────────────────────────────────────────────────
@ar("/evidence-docs")
def evidence_index():
    """凭证管理首页"""
    docs = list(evidence_docs_tb(order_by="id DESC"))
    # 统计
    total_docs = len(docs)
    total_evidences = sum(1 for d in docs if d.ev_type == "凭证")
    total_materials = sum(1 for d in docs if d.ev_type == "备查材料")

    # 凭证列表
    rows = []
    for d in docs:
        proj = projects_tb[d.project_id] if d.project_id else None
        rows.append([
            d.doc_name, d.ev_type, proj.name if proj else "—",
            d.upload_date or "—", d.uploader or "—",
            A("查看", href=f"/evidence-docs/{d.id}", cls="btn btn-outline btn-sm"),
        ])

    doc_table = data_table(
        ["文件名", "类型", "项目", "上传日期", "上传人", ""], rows
    ) if rows else empty_state("file", "暂无凭证/备查文件")

    return page_layout(
        "凭证与备查文件", "首页 / 合规管理 / 凭证备查", "/evidence-docs",
        Div(
            Div(
                Span("凭证与备查文件管理", style="font-size:15px;font-weight:600;"),
                cls="card-title"
            ),
            Div(
                stat_block("文件总数", str(total_docs), "blue"),
                stat_block("凭证文件", str(total_evidences), "green"),
                stat_block("备查材料", str(total_materials), "orange"),
                style="display:flex;gap:12px;margin-bottom:14px;"
            ),
            Div(
                A("+ 上传凭证", href="/evidence-docs/new", cls="btn btn-primary btn-sm"),
                A("辅助账预览", href="/evidence-docs/aux-account", cls="btn btn-outline btn-sm"),
                A("打包下载", href="/evidence-docs/preserve-pack", cls="btn btn-success btn-sm"),
                style="display:flex;gap:8px;margin-bottom:14px;"
            ),
            doc_table,
            cls="card"
        ),
    )


# ── 上传新凭证 ──────────────────────────────────────────
@ar("/evidence-docs/new")
def evidence_new():
    """上传凭证页面"""
    from .components import project_options
    opts = [Option("— 请选择 —", value="")]
    for e in expenses_tb(order_by="id DESC"):
        proj = projects_tb[e.project_id] if e.project_id else None
        opts.append(Option(f"#{e.id} {proj.name if proj else '?'} ¥{e.amount:,.0f} {e.expense_date}",
                           value=e.id))
    return page_layout(
        "上传凭证", "首页 / 合规管理 / 凭证备查 / 上传", "/evidence-docs",
        Div(
            Form(
                Div(
                    Label("关联费用记录", cls="nat-label"),
                    Select(*opts, name="expense_id", cls="input", required=True),
                    cls="nat-field"
                ),
                Div(
                    Label("文件类型", cls="nat-label"),
                    Select(
                        Option("凭证", value="凭证"),
                        Option("备查材料", value="备查材料"),
                        Option("辅助账附件", value="辅助账附件"),
                        Option("其他", value="其他"),
                        name="ev_type", cls="input", required=True,
                    ),
                    cls="nat-field"
                ),
                Div(
                    Label("项目", cls="nat-label"),
                    Select(*project_options(), name="project_id", cls="input"),
                    cls="nat-field"
                ),
                Div(
                    Label("选择文件（PDF/JPG/PNG）", cls="nat-label"),
                    Input(type="file", name="file", accept=".pdf,.jpg,.jpeg,.png,.zip", required=True, cls="input"),
                    cls="nat-field"
                ),
                Div(
                    Label("备注", cls="nat-label"),
                    Input(name="remark", placeholder="可选备注", cls="input"),
                    cls="nat-field"
                ),
                Button("上传", cls="btn btn-primary", type="submit"),
                method="post", action="/evidence-docs/upload",
                enctype="multipart/form-data",
                cls="nat-form"
            ),
            cls="card"
        ),
    )


@ar("/evidence-docs/upload", methods=["POST"])
async def evidence_upload(expense_id: str = "", ev_type: str = "凭证",
                           project_id: str = "0", file: UploadFile = None,
                           remark: str = ""):
    """处理凭证文件上传"""
    if not file or not file.filename:
        return alert_box("请选择上传文件", "danger")
    raw = await file.read()
    if not raw:
        return alert_box("文件内容为空", "danger")

    # 保存文件
    safe_name = f"{int(datetime.now().timestamp())}_{file.filename}"
    save_path = EVI_DIR / safe_name
    save_path.write_bytes(raw)

    pid = int(project_id or 0)
    eid = int(expense_id or 0)
    # 如果没传 project_id，从 expense 反查
    if not pid and eid:
        exp = expenses_tb[eid]
        if exp:
            pid = exp.project_id

    record = evidence_docs_tb.insert(
        expense_id=eid,
        project_id=pid,
        ev_type=ev_type,
        doc_name=file.filename,
        file_path=str(save_path),
        upload_date=_today(),
        uploader="系统管理员",
        remark=remark,
        created_at=_now(),
    )
    log_audit("UPLOAD_EVIDENCE", "EvidenceDoc", record.id,
              detail=f"上传凭证 {file.filename} 类型={ev_type} 关联费用#{eid}")
    return RedirectResponse(url="/evidence-docs?msg=upload_ok", status_code=303)


# ── 凭证详情 ──────────────────────────────────────────────
@ar("/evidence-docs/{doc_id:int}")
def evidence_detail(doc_id: int):
    try:
        d = evidence_docs_tb[doc_id]
    except Exception:
        d = None
    if not d:
        return alert_box("凭证不存在", "danger")
    proj = projects_tb[d.project_id] if d.project_id else None
    exp = expenses_tb[d.expense_id] if d.expense_id else None
    return page_layout(
        "凭证详情", "首页 / 合规管理 / 凭证备查 / 详情", "/evidence-docs",
        Div(
            Div(
                Span(d.doc_name, style="font-size:15px;font-weight:600;"),
                cls="card-title"
            ),
            Div(
                Div(Label("类型", cls="nat-label"), Div(d.ev_type, cls="card"), cls="nat-field"),
                Div(Label("项目", cls="nat-label"), Div(proj.name if proj else "—", cls="card"), cls="nat-field"),
                Div(Label("关联费用", cls="nat-label"),
                    Div(f"#{exp.id} ¥{exp.amount:,.0f} {exp.expense_date}" if exp else "未关联", cls="card"),
                    cls="nat-field"),
                Div(Label("文件路径", cls="nat-label"), Div(d.file_path or "—", cls="card"), cls="nat-field"),
                Div(Label("上传日期", cls="nat-label"), Div(d.upload_date or "—", cls="card"), cls="nat-field"),
                Div(Label("上传人", cls="nat-label"), Div(d.uploader or "—", cls="card"), cls="nat-field"),
                Div(Label("备注", cls="nat-label"), Div(d.remark or "—", cls="card"), cls="nat-field"),
                style="display:flex;flex-direction:column;gap:10px;"
            ),
            Div(
                A("下载文件", href=f"/evidence-docs/{doc_id}/download", cls="btn btn-primary btn-sm"),
                A("← 返回", href="/evidence-docs", cls="btn btn-outline btn-sm"),
                style="margin-top:14px;display:flex;gap:8px;"
            ),
            cls="card"
        ),
    )


@ar("/evidence-docs/{doc_id:int}/download")
def evidence_download(doc_id: int):
    """下载凭证文件"""
    try:
        d = evidence_docs_tb[doc_id]
    except Exception:
        d = None
    if not d or not d.file_path:
        return alert_box("文件不存在", "danger")
    fp = Path(d.file_path)
    if not fp.exists():
        return alert_box("文件已丢失，原始路径：" + str(fp), "danger")
    return FileResponse(str(fp), filename=d.doc_name, media_type="application/octet-stream")


# ── 辅助账预览 ──────────────────────────────────────────
@ar("/evidence-docs/aux-account")
def evidence_aux_account(project_id: str = "0"):
    """研发费用辅助账（加计扣除口径）预览"""
    pid = int(project_id or 0)
    proj = projects_tb[pid] if pid else None
    rows, total = _aux_account_data(pid)
    return page_layout(
        "研发费用辅助账", "首页 / 合规管理 / 凭证备查 / 辅助账", "/evidence-docs",
        Div(
            Div(
                Span(f"研发费用辅助账（{CALIBER_FILTER}口径）", style="font-size:15px;font-weight:600;"),
                Span(f"累计：¥{total:,.2f}", style="font-size:14px;color:var(--primary);margin-left:14px;"),
                cls="card-title"
            ),
            Div(
                A("导出 CSV", href=f"/evidence-docs/aux-account/export?project_id={pid}", cls="btn btn-primary btn-sm"),
                A("← 返回", href="/evidence-docs", cls="btn btn-outline btn-sm"),
                style="display:flex;gap:8px;margin-bottom:12px;"
            ),
            data_table(["期间", "科目", "金额", "累计", "备注"], rows) if rows else empty_state("table", "暂无辅助账数据"),
            cls="card"
        ),
    )


@ar("/evidence-docs/aux-account/export")
def evidence_aux_export(project_id: str = "0"):
    """导出辅助账 CSV"""
    pid = int(project_id or 0)
    rows, total = _aux_account_data(pid)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["研发费用辅助账", f"口径：{CALIBER_FILTER}", f"累计：¥{total:,.2f}"])
    w.writerow([])
    w.writerow(["期间", "科目", "金额", "累计", "备注"])
    for r in rows:
        w.writerow(r)
    csv_bytes = buf.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('研发费用辅助账.csv')}"},
    )


# ── 一键打包 ──────────────────────────────────────────────
@ar("/evidence-docs/preserve-pack")
def evidence_preserve_pack(project_id: str = "0"):
    """留存备查资料包一键打包（ZIP）"""
    pid = int(project_id or 0)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. 辅助账 CSV
        rows, total = _aux_account_data(pid)
        csv_buf = io.StringIO()
        w = csv.writer(csv_buf)
        w.writerow(["研发费用辅助账", f"口径：{CALIBER_FILTER}"])
        w.writerow(["期间", "科目", "金额", "累计", "备注"])
        for r in rows:
            w.writerow(r)
        zf.writestr("辅助账.csv", csv_buf.getvalue().encode("utf-8-sig"))

        # 2. 费用明细 CSV
        exp_buf = io.StringIO()
        w = csv.writer(exp_buf)
        w.writerow(["日期", "项目", "科目", "阶段", "金额", "口径", "来源", "描述"])
        for e in expenses_tb():
            if pid and e.project_id != pid:
                continue
            p = projects_tb[e.project_id] if e.project_id else None
            w.writerow([e.expense_date, p.name if p else str(e.project_id),
                        e.subject_name, e.phase, e.amount, e.caliber, e.source, e.description])
        zf.writestr("费用明细.csv", exp_buf.getvalue().encode("utf-8-sig"))

        # 3. 凭证文件清单
        docs = []
        for d in evidence_docs_tb():
            if pid and d.project_id != pid:
                continue
            docs.append(d)
        doc_buf = io.StringIO()
        w = csv.writer(doc_buf)
        w.writerow(["文件名", "类型", "费用ID", "上传日期", "文件路径"])
        for d in docs:
            w.writerow([d.doc_name, d.ev_type, d.expense_id, d.upload_date, d.file_path])
        zf.writestr("凭证清单.csv", doc_buf.getvalue().encode("utf-8-sig"))

        # 4. 附加凭证文件
        for d in docs:
            if d.file_path and os.path.isfile(d.file_path):
                try:
                    zf.write(d.file_path, f"凭证文件/{d.doc_name}")
                except Exception:
                    pass  # 跳过无法读取的文件

        # 5. 工时记录 CSV（如存在）
        wt_buf = io.StringIO()
        w = csv.writer(wt_buf)
        w.writerow(["人员ID", "项目ID", "日期", "工时", "任务描述"])
        for wt in work_time_tb():
            w.writerow([wt.person_id, wt.project_id, wt.work_date, wt.hours, wt.task_desc])
        zf.writestr("工时记录.csv", wt_buf.getvalue().encode("utf-8-sig"))

        # 6. 设备折旧 CSV（如存在）
        dep_buf = io.StringIO()
        w = csv.writer(dep_buf)
        w.writerow(["设备ID", "期间", "折旧金额", "研发占比", "状态"])
        for dep in equipment_depreciation_tb():
            w.writerow([dep.equipment_id, dep.cost_month, dep.monthly_depreciation, dep.rd_usage_ratio, dep.status])
        zf.writestr("设备折旧表.csv", dep_buf.getvalue().encode("utf-8-sig"))

        # 7. 材料领用 CSV（如存在）
        mat_buf = io.StringIO()
        w = csv.writer(mat_buf)
        w.writerow(["项目ID", "材料名称", "数量", "金额", "日期", "用途"])
        for m in material_requisition_tb():
            w.writerow([m.project_id, m.material_name, m.quantity, m.amount, m.requisition_date, m.purpose])
        zf.writestr("材料领用.csv", mat_buf.getvalue().encode("utf-8-sig"))

    buf.seek(0)
    fname = f"留存备查资料包_{_today()}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )