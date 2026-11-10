"""biz_config.py — 业务系统独立配置层

用途：让业务系统可以脱离 Agent系统 / 连接系统独立运行，同时保留融合模式下
与 hermes_launcher 的数据一致性。

双模式策略
==========
- 融合模式（默认）：项目根存在 .hermes_data 且 hermes_launcher 可用时，
  复用 hermes_launcher 的 get_hermes_home / get_rd_settings / save_rd_settings，
  业务配置读写到 <项目根>/.hermes_data/rd_settings.json（与旧行为一致）。
- 独立模式：hermes_launcher 不可用（业务系统被单独部署/单独打包）时，
  使用本模块自带的独立实现，业务配置读写到 <业务系统>/data/rd_settings.json。

对外接口（与 hermes_launcher 对齐，便于平滑替换）
==================================================
    get_hermes_home() -> Path
    get_rd_settings(home=None) -> dict
    save_rd_settings(patch, home=None) -> dict
    rd_settings_default() -> dict
"""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path

_RD_LOCK = threading.RLock()  # 可重入锁

# ── 独立模式数据目录：<业务系统>/data ─────────────────────────
# biz_config.py 位于 <业务系统>/rdapp/，故 parents[1] = <业务系统>。
_BIZ_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_BIZ_RD_FILE = _BIZ_DATA_DIR / "rd_settings.json"


# ------------------------------------------------------------------
# 独立模式实现（hermes_launcher 不可用时）
# ------------------------------------------------------------------
def _deep_merge(base: dict, override: dict) -> dict:
    """把 override 深合并进 base 的拷贝（dict 递归，其它类型整体替换）。"""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def rd_settings_default() -> dict:
    """研发费用管理默认配置（依据财政部/税务总局加计扣除口径与企业会计准则）。"""
    return {
        "enterprise": {
            "name": "",                       # 企业名称
            "credit_code": "",                # 统一社会信用代码
            "industry": "",                   # 所属行业
            "is_high_tech": False,            # 是否高新技术企业
            "is_sci_sme": False,              # 是否科技型中小企业
            "accounting_standard": "企业会计准则",
        },
        "tax": {
            "super_deduction_rate": 100,
            "policy_basis": "财政部 税务总局公告2023年第7号",
            "collection_method": "auxiliary_account",
            "categories": {
                "personnel": True,
                "direct": True,
                "depreciation": True,
                "amortization": True,
                "design": True,
                "other": True,
            },
            "other_cap_rate": 10,
        },
        "capitalization": {
            "research_expense": True,
            "dev_capitalize": True,
            "criteria": [
                "技术上具有完成该无形资产以使其能够使用或出售的可行性",
                "具有完成该无形资产并使用或出售的意图",
                "无形资产产生经济利益的方式（含存在市场或自用有用性）",
                "有足够的技术、财务资源支持开发并有能力使用或出售",
                "归属于该无形资产开发阶段的支出能够可靠计量",
            ],
            "amortization_years": 10,
        },
        "projects": [],
        "risk": {
            "personnel_ratio_max": 0.70,
            "other_ratio_max": 0.10,
            "single_project_max": 0,
            "checks": {
                "cross_project": True,
                "non_rd_personnel": True,
                "capitalization_misuse": True,
                "invoice_compliance": True,
            },
        },
        "reports": {
            "default_period": "monthly",
            "formats": ["xlsx", "pdf"],
            "include": {
                "summary": True,
                "by_project": True,
                "by_category": True,
                "super_deduction": True,
                "capitalization": True,
            },
        },
    }


def _standalone_hermes_home() -> Path:
    """独立模式：业务配置目录（<业务系统>/data）。"""
    _BIZ_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _BIZ_DATA_DIR


def _standalone_rd_file(home: Path | None = None) -> Path:
    home = home or _standalone_hermes_home()
    home.mkdir(parents=True, exist_ok=True)
    return home / "rd_settings.json"


def _standalone_get_rd_settings(home: Path | None = None) -> dict:
    with _RD_LOCK:
        p = _standalone_rd_file(home)
        if not p.exists():
            return rd_settings_default()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return rd_settings_default()
            return _deep_merge(rd_settings_default(), data)
        except Exception:
            return rd_settings_default()


def _standalone_save_rd_settings(patch: dict, home: Path | None = None) -> dict:
    with _RD_LOCK:
        current = _standalone_get_rd_settings(home)
        merged = _deep_merge(current, patch or {})
        _standalone_rd_file(home).write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return merged


# ------------------------------------------------------------------
# 模式探测与对外接口
# ------------------------------------------------------------------
def _try_import_hermes_launcher():
    """尝试导入融合模式的 hermes_launcher。失败返回 None（独立模式）。"""
    try:
        from .hermes_launcher import (  # type: ignore
            get_hermes_home as _hl_home,
            get_rd_settings as _hl_get_rd,
            save_rd_settings as _hl_save_rd,
            rd_settings_default as _hl_default,
        )
        return _hl_home, _hl_get_rd, _hl_save_rd, _hl_default
    except Exception:
        return None


if os.environ.get("RD_BIZ_STANDALONE") == "1":
    # 独立模式：强制使用业务系统自带实现（业务配置归 <业务系统>/data），
    # 不依赖 hermes_launcher / Agent系统。
    _HL = None
else:
    _HL = _try_import_hermes_launcher()


def get_hermes_home() -> Path:
    """返回配置数据目录（融合模式 = Agent系统 Hermes home；独立模式 = 业务系统/data）。"""
    if _HL is not None:
        return _HL[0]()
    return _standalone_hermes_home()


def get_rd_settings(home: Path | None = None) -> dict:
    """读取研发费用管理配置；缺失字段用默认补全。"""
    if _HL is not None:
        return _HL[1](home)
    return _standalone_get_rd_settings(home)


def save_rd_settings(patch: dict, home: Path | None = None) -> dict:
    """合并保存研发费用管理配置。"""
    if _HL is not None:
        return _HL[2](patch, home)
    return _standalone_save_rd_settings(patch, home)
