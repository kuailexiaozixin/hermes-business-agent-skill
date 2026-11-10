"""test_import_routes.py — 批量导入路由集成测试（TestClient）。

覆盖：导入页 / 模板下载 / 未知实体 / 上传预检 / 确认落库。
依赖 conftest.py 的临时隔离数据库；seed 幂等。
"""
import json

import pytest
from starlette.testclient import TestClient

from rdapp import db, importer
from rdapp.app import app


@pytest.fixture(scope="module", autouse=True)
def seeded():
    db.seed_data()
    db.seed_new_modules()
    yield


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_import_page(client):
    r = client.get("/import/worktime")
    assert r.status_code == 200
    assert "批量导入" in r.text


def test_template_download(client):
    r = client.get("/import/worktime/template")
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # xlsx 为 zip 容器


def test_unknown_entity(client):
    r = client.get("/import/nope")
    assert r.status_code == 200
    assert "未知导入实体" in r.text


def test_preview_via_csv(client):
    csv_bytes = "人员姓名,项目编号,日期,工时,工作内容\n张明远,RD-2026-001,2026-02-25,7,冒烟\n".encode("utf-8")
    r = client.post("/import/worktime/preview",
                    files={"file": ("t.csv", csv_bytes, "text/csv")})
    assert r.status_code == 200
    # 预检通过 → 出现「确认导入」按钮
    assert "确认导入" in r.text


def test_commit_inserts(client):
    payload = json.dumps([{
        "person_name": "张明远", "project_code": "RD-2026-001",
        "work_date": "2026-02-26", "hours": "7", "task_desc": "commit",
    }], ensure_ascii=False)
    r = client.post("/import/worktime/commit", data={"payload": payload})
    assert r.status_code == 200
    assert "已入库" in r.text
    assert len(db.work_time_tb(where="work_date='2026-02-26'")) == 1


def test_preview_missing_header(client):
    # 空文件（无表头）→ 提示未解析到有效数据行
    r = client.post("/import/worktime/preview",
                    files={"file": ("empty.csv", b"", "text/csv")})
    assert r.status_code == 200
    assert "未解析到有效数据行" in r.text


def test_roundtrip_xlsx_template_parse():
    """模板（_build_xlsx 生成）→ parse_upload 可读回（纯标准库对称）。"""
    spec = importer.IMPORT_MAP["worktime"]
    header = spec["template"]
    sample = spec["sample"] or [""] * len(header)
    from rdapp.routes_compliance import _build_xlsx
    data = _build_xlsx([("工时登记", [header, sample])])
    sheet = importer.parse_upload(data, "t.xlsx")
    assert sheet[0] == header
    assert sheet[1][0] == "张明远"  # 示例行人员姓名可读回
