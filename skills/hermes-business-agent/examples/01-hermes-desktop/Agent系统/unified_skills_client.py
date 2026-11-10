"""unified_skills_client.py — 统一技能市场（聚合 SkillHub + Hermes 各源，来源标注）

背景：此前技能市场割裂为两个按钮 ——「社区市场(SkillHub)」走 api.skillhub.cn，
「Hermes官方」走 HermesIndexSource（整包下载 35MB skills-index.json 并本地缓存 40MB）。

本模块将它们统一为一个市场，拉取逻辑一致（全部按服务端 API / 各源适配器按需查询）：
  - SkillHub    → api.skillhub.cn（服务端分页搜索，不下载全量）
  - official    → tools.skills_hub.OptionalSkillSource（GitHub optional-skills，按需）
  - skills.sh   → tools.skills_hub.SkillsShSource（skills.sh/api/search，服务端搜索）
  - clawhub     → tools.skills_hub.ClawHubSource（clawhub.ai/api/v1）
  - lobehub     → tools.skills_hub.LobeHubSource（lobehub.com）
  - browse-sh   → tools.skills_hub.BrowseShSource（browse.sh/api/skills）
  - github      → tools.skills_hub.GitHubSource
  - claude-marketplace → tools.skills_hub.ClaudeMarketplaceSource

显式排除 HermesIndexSource（35MB 全量索引）→ 根治 40MB 缓存缺陷。
卡片通过 source / type 字段标注技能来源（官方 / skills.sh / clawhub / ... / 社区）。
"""
from __future__ import annotations

import re
import math
import json
from pathlib import Path
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import skillhub_client as shub

# 官方站 & 各源 URL 常量
OFFICIAL_REPO = "NousResearch/hermes-agent"
OFFICIAL_RAW = "https://raw.githubusercontent.com/NousResearch/hermes-agent/main"
OFFICIAL_SITE = "https://hermes-agent.nousresearch.com"
OFFICIAL_SITEMAP = OFFICIAL_SITE + "/docs/sitemap.xml"
_OFFICIAL_TREE_URL = "https://api.github.com/repos/NousResearch/hermes-agent/git/trees/main?recursive=1"
LOBEHUB_INDEX_URL = "https://chat-agents.lobehub.com/index.json"
MODELSCOPE_SKILLS_URL = "https://modelscope.cn/api/v1/dolphin/skills"

# 上游 API 的 Cloudflare 防护会把「Mozilla/5.0」这种简写 UA 判成机器人并返回 403
# （页面是 "Just a moment..." 的 HTML，不是 JSON）。实测带完整浏览器请求头后返回 200。
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
_BROWSER_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


# 来源显示名（前端徽标用）
SOURCE_LABEL = {
    "trusttools": "TrustTools",
    "skills.sh": "skills.sh",
    "clawhub": "clawhub",
    "lobehub": "lobehub",
    "browse-sh": "browse.sh",
    "skillsmp": "skillsmp",
    "modelscope": "ModelScope",
    "github": "GitHub",
    "claude-marketplace": "claude",
    "community": "SkillHub",
    "well-known": "内置",
    "url": "URL",
    "other": "其他",
}

# 可独立筛选的市场标识（= 卡片 source 字段，与 SOURCE_LABEL key 一致）
MARKET_SOURCES = [
    "community", "skills.sh", "clawhub",
    "lobehub", "browse-sh", "skillsmp", "trusttools", "modelscope",
]

# Hermes 源 source_id() → 卡片 source 字段（source_id 与卡片 source 偶有不同，如 skills-sh→skills.sh）
_SRCID_TO_LABEL = {
    "skills-sh": "skills.sh",
    "clawhub": "clawhub",
    "lobehub": "lobehub",
    "browse-sh": "browse-sh",
    "github": "github",
    "claude-marketplace": "claude-marketplace",
}


def _normalize_sources(sources):
    """归一化市场过滤参数 → None(全部) 或去重的市场标识列表。"""
    if sources is None:
        return None
    if isinstance(sources, str):
        sources = [s.strip() for s in sources.split(",") if s.strip()]
    elif not isinstance(sources, (list, tuple, set)):
        sources = [sources]
    out = []
    for s in sources:
        if s in MARKET_SOURCES and s not in out:
            out.append(s)
    if not out:
        return None
    return out


def _sources_key(sources) -> str:
    return ",".join(sorted(sources)) if sources else "*"


# ── 源适配器单例（排除 HermesIndexSource 全量索引）─────────────────────
_sources_lock = threading.Lock()
_sources: list = None

def _get_sources():
    """create_source_router 的源列表，排除 HermesIndexSource（35MB 全量索引）。"""
    global _sources
    with _sources_lock:
        if _sources is None:
            from tools.skills_hub import (HermesIndexSource, GitHubSource,
                                          ClaudeMarketplaceSource, OptionalSkillSource, LobeHubSource,
                                          create_source_router, GitHubAuth)
            _sources = [
                s for s in create_source_router(auth=GitHubAuth())
                if not isinstance(s, (HermesIndexSource, GitHubSource, ClaudeMarketplaceSource, OptionalSkillSource, LobeHubSource))
            ]
        return _sources

# ── 内存短缓存（进程内，不落盘磁盘）───────────────────────────────────
_MEM_LOCK = threading.Lock()
_MEM: dict = {}
_TTL = 60 * 10  # 10 分钟

def _cache_get(key):
    with _MEM_LOCK:
        hit = _MEM.get(key)
        if hit and time.time() - hit[0] < _TTL:
            return hit[1]
    return None

def _cache_put(key, val):
    with _MEM_LOCK:
        _MEM[key] = (time.time(), val)

def _clear_cache():
    with _MEM_LOCK:
        _MEM.clear()

# ── 归一化 ────────────────────────────────────────────────────────────
def _source_of(meta) -> str:
    """归一化 SkillMeta → source 标识。"""
    return getattr(meta, "source", "") or "community"

def _type_of(source: str, trust_level: str = "") -> str:
    """前端类型徽标：official / trusted / github / community。"""
    if source == "official" or trust_level == "builtin":
        return "official"
    if trust_level == "trusted":
        return "trusted"
    if source == "github":
        return "github"
    return "community"

def _skillhub_to_card(it: dict) -> dict:
    """SkillHub(api.skillhub.cn) item → 前端卡片（来源=community）。"""
    return {
        "slug": it.get("slug") or "",
        "name": it.get("name") or "",
        "description": it.get("description") or "",
        "category": it.get("category") or "",
        "iconUrl": it.get("iconUrl") or "",
        "downloads": it.get("downloads") or 0,
        "owner": it.get("owner") or "",
        "namespace": it.get("namespace") or "",
        "upstream_url": it.get("upstream_url") or "",
        "homepage": it.get("homepage") or "",
        "verified": bool(it.get("verified")),
        "source": "community",
        "source_label": SOURCE_LABEL["community"],
        "type": "community",
        "identifier": it.get("slug") or "",
        "tags": [],
        "market": "skillhub",
    }

def _meta_to_card(meta) -> dict:
    """Hermes 各源 SkillMeta → 前端卡片。"""
    src = _source_of(meta)
    tl = getattr(meta, "trust_level", "") or ""
    extra = dict(getattr(meta, "extra", None) or {})
    cat = ""
    ident = getattr(meta, "identifier", "") or ""
    if ident.startswith("official/"):
        parts = ident.split("/")
        if len(parts) >= 3:
            cat = "/".join(parts[1:-1])
    return {
        "slug": ident or getattr(meta, "name", "") or "",
        "name": getattr(meta, "name", "") or "",
        "description": getattr(meta, "description", "") or "",
        "category": cat or extra.get("category", ""),
        "iconUrl": "",
        "downloads": (
            extra.get("downloads") or extra.get("installCount") or
            extra.get("installs") or extra.get("install_count") or
            (extra.get("stats") or {}).get("downloads") or 0
        ),
        "owner": _owner_of(meta, src, ident, extra),
        "namespace": src,
        "upstream_url": getattr(meta, "repo", "") or "",
        "homepage": "",
        "verified": tl == "builtin",
        "source": src,
        "source_label": SOURCE_LABEL.get(src, src),
        "type": _type_of(src, tl),
        "identifier": ident,
        "tags": list(getattr(meta, "tags", None) or []),
        "market": src,
    }

# ── 各源搜索（排除 HermesIndexSource）─────────────────────────────────
def _interleave(a: list, b: list) -> list:
    """交错合并两类来源卡片，保证首页能看到多种来源（避免单一来源淹没）。"""
    out: list = []
    i = j = 0
    while i < len(a) and j < len(b):
        out.append(a[i]); i += 1
        out.append(b[j]); j += 1
    out.extend(a[i:])
    out.extend(b[j:])
    return out


def _interleave_multi(groups: list) -> list:
    """按来源轮询交错多个卡片列表，保证每个来源的结果都出现在首页。

    例如 groups=[[A1,A2],[B1,B2],[C1]] → [A1,B1,C1,A2,B2]。
    """
    out: list = []
    i = 0
    while True:
        progressed = False
        for g in groups:
            if i < len(g):
                out.append(g[i])
                progressed = True
        if not progressed:
            break
        i += 1
    return out


def _owner_of(meta, src: str, ident: str, extra: dict) -> str:
    """从 SkillMeta 尽量提取真实发布者；无法确定则返回空（前端不显示 owner）。

    优先级：extra.provider/owner/author → repo（owner/repo 或 github URL）→ repo_url
    → identifier（skills-sh/owner/...）→ official 固定 Nous Research → 空。
    """
    for k in ("provider", "owner", "author"):
        v = extra.get(k)
        if v:
            return str(v)
    repo = (getattr(meta, "repo", "") or "").strip().rstrip("/")
    if repo:
        if "github.com/" in repo:
            parts = repo.split("github.com/")[-1].split("/")
            if parts and parts[0]:
                return parts[0]
        if "/" in repo:
            return repo.split("/")[0]
    ru = (extra.get("repo_url") or "").strip()
    if "github.com/" in ru:
        parts = ru.split("github.com/")[-1].split("/")
        if parts and parts[0]:
            return parts[0]
    if src == "skills.sh" and ident.startswith("skills-sh/"):
        parts = ident.split("/")
        if len(parts) >= 2 and parts[1]:
            return parts[1]
    if src == "official":
        return "Nous Research"
    return ""



def _search_hermes_sources(q: str, limit: int = 40, timeout: float = 8.0,
                          sources: list = None) -> list:
    """并发查询 Hermes 各源适配器，整体超时快速返回（不等待慢源）。

    注意：不能用 `with ThreadPoolExecutor` —— 其退出时 shutdown(wait=True)
    会等待所有源线程跑完（GitHubSource 限流最长 10s+），导致聚合卡死。
    这里用整体 timeout + shutdown(wait=False, cancel_futures=True)，
    超时的慢源结果被丢弃，主线程立即返回，慢线程在后台自然结束。

    sources: 市场过滤标识（None=全部）；只查询命中市场的源，提升速度。
    """
    cards: list = []
    q = (q or "").strip()
    srcs = _get_sources()
    # browse-sh 改由 _browse_sh_page 独立抓取：它的目录大、冷启动常超过本函数
    # 的整体 timeout，留在这里会既拖慢并发窗口、又拿到被丢弃的空结果。
    srcs = [s for s in srcs if s.source_id() != "browse-sh"]
    if not srcs:
        return cards
    # 按市场过滤 Hermes 源（source_id → 卡片 source label）
    if sources:
        sel = []
        for s in srcs:
            label = _SRCID_TO_LABEL.get(s.source_id(), s.source_id())
            if label in sources:
                sel.append(s)
        srcs = sel
    if not srcs:
        return cards
    ex = ThreadPoolExecutor(max_workers=min(8, len(srcs)))
    futs = {ex.submit(s.search, q, max(limit, 5)): s for s in srcs}
    # 按源分组收集（避免单源占满首页）
    groups: dict = {}
    try:
        for fut in as_completed(futs, timeout=timeout):
            try:
                metas = fut.result()
                s = futs[fut]
                label = _SRCID_TO_LABEL.get(s.source_id(), s.source_id())
                g = groups.setdefault(label, [])
                for m in metas:
                    if getattr(m, "name", None) or getattr(m, "identifier", None):
                        g.append(_meta_to_card(m))
            except Exception:
                continue
    except TimeoutError:
        pass  # 剩余慢源丢弃，不阻塞主线程
    finally:
        # 关键：不等待未完成线程，取消未启动任务
        ex.shutdown(wait=False, cancel_futures=True)
    # 按来源轮询交错，使多源结果都出现在首页
    cards = _interleave_multi(list(groups.values()))
    return cards

def _skillsmp_to_card(s: dict) -> dict:
    """skillsmp.com skill -> frontend card (source=skillsmp)."""
    route = s.get("route") or {}
    github = s.get("githubUrl") or ""
    return {
        "slug": s.get("id") or "",
        "name": s.get("name") or "",
        "description": s.get("description") or "",
        "category": "",
        "iconUrl": s.get("authorAvatar") or "",
        "downloads": 0,  # skillsmp API 的 stars 为占位/异常值(实测恒为386028)，非真实下载量，置0避免误导
        "updatedAt": s.get("updatedAt") or 0,  # 最近更新时间(Unix)，作排序信号
        "owner": s.get("author") or "",
        "namespace": "skillsmp",
        "upstream_url": github,
        "homepage": github,
        "verified": False,
        "source": "skillsmp",
        "source_label": SOURCE_LABEL["skillsmp"],
        "type": "community",
        "identifier": s.get("id") or "",
        "tags": [],
        "market": "skillsmp",
        "branch": s.get("branch") or "main",
        "path": s.get("path") or "SKILL.md",
        "route": route,
        "sourceSkillPath": route.get("sourceSkillPath") or "",
    }

def _skillsmp_page(q: str, page: int = 1, pageSize: int = 24, timeout: float = 8.0):
    """skillsmp.com server-side paged search. Returns (cards, total).

    上游有 Cloudflare：只带 ``User-Agent: Mozilla/5.0`` 会返回 403 的 HTML 挑战页，
    异常被吞掉后就表现为「市场空白」。实测补完整浏览器请求头 + Referer 后返回
    200 / 24 条 / total=1200（2026-11-10）。
    """
    try:
        params = urllib.parse.urlencode({"q": q, "page": max(page, 1), "limit": max(pageSize, 10)})
        headers = dict(_BROWSER_HEADERS)
        headers["Referer"] = "https://skillsmp.com/"
        req = urllib.request.Request(
            "https://skillsmp.com/api/skills?" + params, headers=headers)
        with urllib.request.urlopen(req, timeout=max(timeout, 12.0)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return [], 0
    skills = [s for s in (data.get("skills") or []) if s.get("id")]
    total = (data.get("pagination") or {}).get("total") or len(skills)
    return [_skillsmp_to_card(s) for s in skills], total


# ── browse.sh：独立抓取 + 内存缓存，不依赖 Hermes 适配器的 8 秒并发窗口 ──────
# 目录约 700KB / 479 条，冷启动时直连很慢。Hermes 自带 BrowseShSource 用
# httpx 直连 + 20s 超时，赶不上统一聚合的整体 timeout，结果会被整批丢弃，
# 表现为「browse.sh 市场空白」。这里独立抓取、给足超时、只缓存非空结果。
BROWSE_SH_CATALOG_URL = "https://browse.sh/api/skills"
_BROWSE_CACHE_KEY = "browse_sh_catalog"


def _browse_sh_catalog(timeout: float = 25.0) -> list:
    """抓取 browse.sh 全量目录并缓存 10 分钟；失败不缓存，下次请求立即重试。"""
    hit = _cache_get(_BROWSE_CACHE_KEY)
    if hit is not None:
        return hit
    try:
        req = urllib.request.Request(BROWSE_SH_CATALOG_URL, headers=_BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    skills = [s for s in (data.get("skills") or []) if s.get("slug") and s.get("name")]
    if not skills:
        return []
    _cache_put(_BROWSE_CACHE_KEY, skills)
    return skills


def _browse_sh_to_card(item: dict) -> dict:
    """browse.sh 目录条目 → 前端卡片（字段与 BrowseShSource 的 SkillMeta 对齐）。"""
    slug = item.get("slug") or ""
    desc = item.get("description") or item.get("title") or ""
    return {
        "slug": f"browse-sh/{slug}",
        "name": item.get("name") or "",
        "description": desc[:1021] + "..." if len(desc) > 1024 else desc,
        "category": item.get("category") or "",
        "iconUrl": "",
        "downloads": item.get("installCount") or 0,
        "owner": item.get("hostname") or "",
        "namespace": "browse-sh",
        "upstream_url": "",  # 安装仍走 Hermes BrowseShSource 的 identifier 解析
        "homepage": item.get("sourceUrl") or "",
        "verified": bool(item.get("verified")),
        "source": "browse-sh",
        "source_label": SOURCE_LABEL["browse-sh"],
        "type": "community",
        "identifier": f"browse-sh/{slug}",
        "tags": list(item.get("tags") or []),
        "market": "browse-sh",
    }


def _browse_sh_page(q: str = "", page: int = 1, pageSize: int = 24):
    """本地过滤 + 切片（browse.sh 无服务端分页）。Returns (cards, total)."""
    catalog = _browse_sh_catalog()
    if not catalog:
        return [], 0
    needle = (q or "").strip().lower()
    matched = []
    for item in catalog:
        parts = [str(item.get(k) or "") for k in
                 ("name", "title", "description", "hostname", "category", "task")]
        parts += [str(t) for t in (item.get("tags") or [])]
        if not needle or needle in " ".join(parts).lower():
            matched.append(_browse_sh_to_card(item))
    start = (max(page, 1) - 1) * max(pageSize, 1)
    return matched[start:start + max(pageSize, 1)], len(matched)


def _parse_frontmatter(text: str) -> dict:
    """Minimal YAML-ish frontmatter parser (name/description/tags)."""
    fm = {}
    tags = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip(); val = val.strip()
        if key == "tags" and val.startswith("["):
            tags = [t.strip() for t in val.strip("[]").split(",") if t.strip()]
        elif key in ("name", "description"):
            v = val
            if len(v) >= 2 and v[0] == v[-1] == "\"":
                v = v[1:-1]
            elif len(v) >= 2 and v[0] == v[-1] == "'\"":
                v = v[1:-1]
            fm[key] = v
    fm["tags"] = tags
    return fm

def _official_paths() -> list:
    """Get optional-skills SKILL.md paths (in-memory, from GitHub tree API)."""
    hit = _cache_get("official_paths")
    if hit is not None:
        return hit
    try:
        req = urllib.request.Request(_OFFICIAL_TREE_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        paths = [t["path"] for t in d.get("tree", [])
                 if t["path"].startswith("optional-skills/") and t["path"].endswith("/SKILL.md")]
    except Exception:
        paths = []
    _cache_put("official_paths", paths)
    return paths

def _official_scan() -> list:
    """In-memory index of official skills, fetched from the official docs site."""
    hit = _cache_get("official_index")
    if hit is not None:
        return hit
    urls = _official_sitemap()
    out = []
    if not urls:
        return out

    def _fetch(u):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return u, resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return u, ""

    ex = ThreadPoolExecutor(max_workers=16)
    futs = {ex.submit(_fetch, u): u for u in urls}
    try:
        for fut in as_completed(futs, timeout=90):
            u, html = fut.result()
            m = re.search(r"<title[^>]*>([^<]+)</title>", html)
            if not m:
                continue
            title = m.group(1).rstrip().rsplit(" | Hermes Agent", 1)[0].strip()
            parts = title.split(" — ", 1)
            name = parts[0].strip()
            desc = parts[1].strip() if len(parts) > 1 else ""
            pseg = u.rstrip("/").split("/")
            cat = pseg[-2] if len(pseg) >= 2 else ""
            seg = pseg[-1] if pseg else ""
            gh_rel = f"{cat}/{seg[len(cat) + 1:]}" if cat and seg.startswith(cat) else seg
            out.append({"name": name, "desc": desc, "tags": [], "cat": cat, "path": gh_rel})
    except Exception:
        pass
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    _cache_put("official_index", out)
    return out

def _official_sitemap() -> list:
    """Optional-skill page URLs from the official docs sitemap (in-memory)."""
    hit = _cache_get("official_sitemap")
    if hit is not None:
        return hit
    urls = []
    try:
        req = urllib.request.Request(OFFICIAL_SITEMAP, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            xml = resp.read().decode("utf-8", errors="ignore")
        for mm in re.finditer(r"<loc>([^<]+)</loc>", xml):
            u = mm.group(1).strip()
            if "/skills/optional/" in u and u.rstrip("/").count("/") > 6:
                urls.append(u)
    except Exception:
        urls = []
    _cache_put("official_sitemap", urls)
    return urls
def _official_to_card(it: dict) -> dict:
    name = it["name"]
    cat = it["cat"]
    ident = f"official/{cat}/{name}" if cat else f"official/{name}"
    return {
        "slug": ident,
        "name": name,
        "description": it["desc"],
        "category": cat,
        "iconUrl": "",
        "downloads": 0,
        "owner": "Nous Research",
        "namespace": "official",
        "upstream_url": "",
        "homepage": "",
        "verified": True,
        "source": "official",
        "source_label": SOURCE_LABEL["official"],
        "type": "official",
        "identifier": ident,
        "tags": it["tags"],
        "market": "official",
        "_official_path": it["path"],
    }

def _official_matched(q: str) -> list:
    """All official skill dicts matching q (name/desc/tags/cat)."""
    ql = (q or "").lower()
    return [it for it in _official_scan() if ql in f"{it['name']} {it['desc']} {' '.join(it['tags'])} {it['cat']}".lower()]

def _official_page(q: str, page: int = 1, pageSize: int = 24):
    """Paged slice of matching official skills. Returns (cards, total)."""
    matched = _official_matched(q)
    total = len(matched)
    start = (max(page, 1) - 1) * pageSize
    return [_official_to_card(it) for it in matched[start:start + pageSize]], total

def _lobehub_index() -> list:
    """Fetch lobehub skill index (UTF-8, in-memory cache, no disk)."""
    hit = _cache_get("lobehub_index")
    if hit is not None:
        return hit
    try:
        req = urllib.request.Request(LOBEHUB_INDEX_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    agents = data.get("agents") if isinstance(data, dict) else data
    if not isinstance(agents, list):
        agents = []
    _cache_put("lobehub_index", agents)
    return agents

def _lobehub_to_card(a: dict) -> dict:
    meta = a.get("meta") or {}
    ident = a.get("identifier") or ""
    title = meta.get("title") or ident
    from datetime import datetime as _dt
    _created = (a.get("createdAt") or "").strip()
    _upd = 0
    if _created:
        try:
            _upd = int(_dt.strptime(_created[:10], "%Y-%m-%d").timestamp())
        except Exception:
            _upd = 0
    return {
        "slug": ident,
        "name": title,
        "description": meta.get("description") or "",
        "category": meta.get("category") or "",
        "iconUrl": meta.get("avatar") or "",
        "downloads": 0,
        "updatedAt": _upd,  # 创建时间(Unix)，作"最近更新"排序信号
        "owner": a.get("author") or "",
        "namespace": "lobehub",
        "upstream_url": a.get("homepage") or "",
        "homepage": a.get("homepage") or "",
        "verified": False,
        "source": "lobehub",
        "source_label": SOURCE_LABEL["lobehub"],
        "type": "community",
        "identifier": f"lobehub/{ident}" if ident else "",
        "tags": meta.get("tags") or [],
        "market": "lobehub",
    }

def _lobehub_matched(q: str) -> list:
    """All lobehub agents matching q (title/desc/tags)."""
    ql = (q or "").lower()
    out = []
    for a in _lobehub_index():
        meta = a.get("meta") or {}
        title = meta.get("title") or a.get("identifier") or ""
        desc = meta.get("description") or ""
        tags = meta.get("tags") or []
        if ql in f"{title} {desc} {' '.join(tags)}".lower():
            out.append(a)
    return out

def _lobehub_page(q: str, page: int = 1, pageSize: int = 24):
    """Paged slice of matching lobehub skills. Returns (cards, total)."""
    matched = _lobehub_matched(q)
    total = len(matched)
    start = (max(page, 1) - 1) * pageSize
    return [_lobehub_to_card(a) for a in matched[start:start + pageSize]], total

# Hermes 各源（skills.sh/clawhub/browse-sh）可浏览总量估算（官方 skills-meta bySource，
# 这些服务端源 search 不返回 total，用其 catalog 总量支撑无限分页）。
_SOURCE_TOTAL_EST = {
    "skills.sh": 19967,
    "clawhub": 69150,
    "browse-sh": 440,
}

def _hermes_group_total(sources, q: str) -> int:
    """估算 Hermes 各源组可加载总量（选中市场对应源总量之和，至少 500）。"""
    sel = set(sources) if sources else set(_SOURCE_TOTAL_EST)
    return sum(v for k, v in _SOURCE_TOTAL_EST.items() if k in sel) or 500


# TrustTools 源（ai.trusttools.cn/api/skills/search，服务端分页，不落盘）
_TRUSTTOOLS_API = "https://ai.trusttools.cn/api/skills/search"

def _modelscope_to_card(it: dict) -> dict:
    """ModelScope SkillList item → 前端卡片（source=modelscope）。"""
    owner = it.get("Path") or it.get("Owner") or ""
    name = it.get("Name") or ""
    l1 = it.get("L1") or {}
    cat = (l1.get("ChineseName") if isinstance(l1, dict) else "") or ""
    ident = f"{owner}/{name}" if owner else name
    src_url = it.get("SourceURL") or ""
    return {
        "slug": ident,
        "name": it.get("DisplayName") or name,
        "description": it.get("Description") or "",
        "category": cat or "",
        "iconUrl": it.get("CoverImages") or "",
        "downloads": it.get("DownloadCount") or 0,
        "likes": it.get("Likes") or 0,
        "visits": it.get("Visits") or 0,
        "owner": owner,
        "namespace": "modelscope",
        "upstream_url": src_url,
        "homepage": src_url or f"https://modelscope.cn/skills/{ident}",
        "verified": False,
        "source": "modelscope",
        "source_label": SOURCE_LABEL.get("modelscope", "ModelScope"),
        "type": "community",
        "identifier": ident,
        "tags": list(it.get("Tags") or []),
        "market": "modelscope",
    }


def _modelscope_raw_url(upstream_url: str = ""):
    """ModelScope GitHub 源 → raw SKILL.md 下载地址；解析失败返回 None。"""
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/(blob|tree)/([^/]+)/(.*)",
                 upstream_url or "")
    if not m:
        return None
    owner, repo, kind, branch, path = m.groups()
    path = path.rstrip("/")
    if kind == "tree":
        path = path + "/SKILL.md"
    elif not path.lower().endswith((".md", ".markdown")):
        path = path + "/SKILL.md"
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"


def _modelscope_page(q: str = "", page: int = 1, pageSize: int = 24, timeout: float = 10.0):
    """ModelScope 服务端分页搜索。返回 (cards, total)。"""
    body = {"PageNumber": max(1, page), "PageSize": max(1, pageSize)}
    if (q or "").strip():
        body["Query"] = q.strip()
    try:
        req = urllib.request.Request(
            MODELSCOPE_SKILLS_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            method="PUT")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception:
        return [], 0
    d = data.get("Data") or {}
    sl = d.get("SkillList") or []
    total = d.get("TotalCount") or 0
    cards = [_modelscope_to_card(it) for it in sl if it.get("Name")]
    return cards, total


def _trusttools_to_card(it: dict) -> dict:
    """TrustTools skill -> frontend card (source=trusttools)."""
    owner = it.get("repo_owner") or ""
    repo = it.get("repo_name") or ""
    branch = it.get("branch") or "main"
    rpath = (it.get("repo_path") or "").strip("/")
    slug = it.get("slug") or str(it.get("id") or "")
    blob = (f"https://github.com/{owner}/{repo}/blob/{branch}/{rpath}"
            if owner and repo else (it.get("repo_url") or ""))
    return {
        "slug": slug,
        "name": it.get("name") or "",
        "description": it.get("description_zh") or it.get("description") or "",
        "category": "",
        "iconUrl": "",
        "downloads": it.get("install_count") or 0,
        "owner": owner,
        "namespace": "trusttools",
        "upstream_url": blob,
        "homepage": it.get("repo_url") or "",
        "verified": it.get("status") == "APPROVED",
        "source": "trusttools",
        "source_label": SOURCE_LABEL["trusttools"],
        "type": "community",
        "identifier": f"trusttools/{slug}",
        "tags": it.get("tags") or [],
        "market": "trusttools",
        "branch": branch,
        "path": rpath,
    }

def _trusttools_page(q: str, page: int = 1, pageSize: int = 24, timeout: float = 10.0):
    """TrustTools server-side paged search. Returns (cards, total)."""
    try:
        body = json.dumps({"search": q or "", "page": max(page, 1), "limit": max(pageSize, 10)}).encode("utf-8")
        req = urllib.request.Request(_TRUSTTOOLS_API, data=body,
            headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return [], 0
    items = data.get("data") or []
    pag = data.get("pagination") or {}
    total = pag.get("total") or len(items)
    return [_trusttools_to_card(s) for s in items if s.get("name")], total

def _install_modelscope(identifier: str, upstream_url: str = "", force: bool = False) -> dict:
    """ModelScope skill：从 GitHub SourceURL 拉 SKILL.md 安装。"""
    raw = _modelscope_raw_url(upstream_url)
    if not raw:
        return {"ok": False, "error": "ModelScope 技能缺少可用的 GitHub 源地址"}
    try:
        req = urllib.request.Request(raw, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return {"ok": False, "error": f"下载失败：{type(e).__name__}: {e}"}
    if not content.strip():
        return {"ok": False, "error": "SKILL.md 为空"}
    import hermes_skills_client as hskills
    name = identifier.split("/", 1)[-1] if "/" in identifier else identifier
    return hskills.install_bundle_files(identifier, name, {"SKILL.md": content},
                                        source="modelscope", trust_level="community",
                                        metadata={"source_url": raw}, force=force)


def _install_trusttools(identifier: str, upstream_url: str = "", force: bool = False) -> dict:
    """Install a trusttools skill by downloading SKILL.md from raw GitHub."""
    import re
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)", upstream_url or "")
    if not m:
        return {"ok": False, "error": "trusttools 技能缺少 github blob 地址"}
    owner, repo, branch, path = m.groups()
    path = path.rstrip("/")
    # trusttools 的 repo_path 已是完整文件路径（以 .md 结尾）；个别为目录则补 SKILL.md
    if not path.lower().endswith((".md", ".markdown")):
        path = path + "/SKILL.md"
    raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    try:
        req = urllib.request.Request(raw, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return {"ok": False, "error": f"下载失败：{type(e).__name__}: {e}"}
    if not content.strip():
        return {"ok": False, "error": "SKILL.md 为空"}
    import hermes_skills_client as hskills
    name = identifier.split("/", 1)[-1] if "/" in identifier else identifier
    return hskills.install_bundle_files(identifier, name, {"SKILL.md": content},
                                        source="trusttools", trust_level="community",
                                        metadata={"source_url": raw}, force=force)


def search_skills(q: str = "", category: str = "", page: int = 1,
                  pageSize: int = 24, sources=None, use_cache: bool = True,
                  sort: str = "default") -> dict:
    """统一技能市场搜索：多源聚合，支持无限分页加载。

    每源按当前页取数（服务端分页或本地切片），total 用各源真实 total 之和，
    前端以 page*pageSize < total 判断是否有更多，实现无限加载。
    """
    q = (q or "").strip()
    category = (category or "").strip()
    page = max(1, page)
    pageSize = max(1, min(pageSize, 100))
    sources = _normalize_sources(sources)

    cache_key = f"u:{q}|{category}|{page}|{pageSize}|{_sources_key(sources)}|{sort}"
    if use_cache:
        hit = _cache_get(cache_key)
        if hit is not None:
            return dict(hit, cached=True)

    # 各源返回 (cards, total)，最终 total 累加
    groups: list = []  # [(cards, total), ...]
    grand_total = 0

    # 1) SkillHub 社区（服务端分页，total 真实）
    if sources is None or "community" in sources:
        try:
            sh = shub.search_skills(q=q, category=category, page=page,
                                    pageSize=pageSize, use_cache=use_cache)
            sh_cards = [_skillhub_to_card(it) for it in sh.get("items", []) if it.get("slug")]
            if sh_cards:
                sh_total = sh.get("total") or len(sh_cards)
                groups.append((sh_cards, sh_total))
                grand_total += sh_total
        except Exception:
            pass

    # 2) Hermes 各源（累积 limit 切片实现分页）
    if sources:
        hermes_timeout = 8.0 if q else 8.0
    else:
        hermes_timeout = 8.0 if q else 3.0
    h_all = _search_hermes_sources(q, limit=pageSize * page, timeout=hermes_timeout,
                                   sources=sources)
    h_cards = h_all[(page - 1) * pageSize: page * pageSize]
    if h_cards:
        h_total = _hermes_group_total(sources, q)
        groups.append((h_cards, h_total))
        grand_total += h_total

    # 2.4) browse.sh（独立抓取 + 内存缓存，本地分页）
    if sources is None or "browse-sh" in sources:
        bs_cards, bs_total = _browse_sh_page(q, page, pageSize)
        if bs_cards:
            groups.append((bs_cards, bs_total))
            grand_total += bs_total

    # 2.5) skillsmp（服务端分页）
    if sources is None or "skillsmp" in sources:
        mp_cards, mp_total = _skillsmp_page(q, page, pageSize, timeout=hermes_timeout)
        if mp_cards:
            groups.append((mp_cards, mp_total))
            grand_total += mp_total

    # 2.6) trusttools（服务端分页）
    if sources is None or "trusttools" in sources:
        tt_cards, tt_total = _trusttools_page(q, page, pageSize, timeout=hermes_timeout)
        if tt_cards:
            groups.append((tt_cards, tt_total))
            grand_total += tt_total

    # 2.7) lobehub（本地匹配切片）
    if sources is None or "lobehub" in sources:
        lobe_cards, lobe_total = _lobehub_page(q, page, pageSize)
        if lobe_cards:
            groups.append((lobe_cards, lobe_total))
            grand_total += lobe_total

    # 2.8) modelscope（服务端分页）
    if sources is None or "modelscope" in sources:
        ms_cards, ms_total = _modelscope_page(q, page, pageSize, timeout=hermes_timeout)
        if ms_cards:
            groups.append((ms_cards, ms_total))
            grand_total += ms_total

    # 3) 交错混合多来源（本页内）
    cards = _interleave_multi([g[0] for g in groups]) if len(groups) > 1 \
        else (groups[0][0] if groups else [])

    # 4) 按 identifier 去重（保留首个）
    seen, dedup = set(), []
    for c in cards:
        k = c.get("identifier") or c.get("slug")
        if not k or k in seen:
            continue
        seen.add(k)
        dedup.append(c)

    # 4.4) 补充 skillsmp/lobehub 的 GitHub star（参与热度值；失败回退 0）
    _fetch_github_stars(dedup)

    # 4.5) 计算热度值（下载量/安装量/收藏量/星数统一指标）
    for c in dedup:
        c["heat"] = _heat_of(c)

    # 5) 应用排序（default=按热度值降序）
    _apply_sort(dedup, sort, q)

    total = max(grand_total, 1)
    # 空搜索（无关键词）却一条都没有，多半是上游超时/被拦，不是「真的没匹配」。
    # 交给前端显示可操作的提示，避免用户对着空白市场反复刷新。
    source_errors = [] if dedup or q else [
        "所选市场暂时没有取到数据，可能是上游不可达或响应超时，请稍后重试",
    ]
    result = {
        "items": dedup[:pageSize],
        "categories": get_categories(),
        "total": total,
        "page": page,
        "pageSize": pageSize,
        "pages": (total + pageSize - 1) // pageSize,
        "source_errors": source_errors,
        "cached": False,
    }
    # 空结果不写 10 分钟缓存：一次上游抖动会把市场锁死 10 分钟，
    # 用户刷新多少次都还是空白。失败时下次请求立即重试。
    if use_cache and dedup:
        _cache_put(cache_key, result)
    return result

# 权威性分级权重（official/trusted/github/community）
_AUTHORITY_SCORE = {"official": 30, "trusted": 25, "github": 15, "community": 5}


def _num(v):
    """容错转数值，失败返回 0。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _score_card(card: dict, q: str = "") -> float:
    """综合推荐评分：权威性 + 对数流行度 + 已验证 + 名称相关。

    权重设计（满分约 95）：
      - 权威性 type（official 30 / trusted 25 / github 15 / community 5）
      - 流行度 log10(1+downloads)/log10(1+1e6) * 40（对数归一，避免单源巨量淹没）
      - 已验证 +10
      - 搜索词命中名称 +15
    """
    s = _AUTHORITY_SCORE.get((card.get("type") or "community").lower(), 5)
    d = max(_num(card.get("downloads")), 0.0)
    s += min(math.log10(1.0 + d) / math.log10(1.0 + 1e6), 1.0) * 40.0
    s += 10.0 if card.get("verified") else 0.0
    if q:
        name = (card.get("name") or "")
        if q.lower() in name.lower():
            s += 15.0
    return s


def _apply_sort_score(cards: list, q: str = "") -> None:
    """score（综合推荐）排序：每市场内部按综合分降序，再按各市场最高分降序轮换交错。

    依据：多源聚合时各源数据丰富度不一致（skillsmp/lobehub 等无下载量/验证信号），
    若做单一全局数值排序会让这些"数据稀疏但可能优质"的源系统性沉底。此处采用
    推荐系统的"多样性/覆盖度保底"策略——保证每个市场都露出其最强技能，同时强者优先。
    """
    groups = {}
    for c in cards:
        key = c.get("source") or c.get("market") or "?"
        groups.setdefault(key, []).append(c)
    for g in groups.values():
        g.sort(key=lambda c: _score_card(c, q), reverse=True)
    ordered = sorted(groups.values(), key=lambda g: _score_card(g[0], q), reverse=True)
    out = []
    i = 0
    while True:
        progressed = False
        for g in ordered:
            if i < len(g):
                out.append(g[i])
                progressed = True
        if not progressed:
            break
        i += 1
    cards[:] = out


_GITHUB_STAR_CACHE: dict = {}


def _parse_abbrev(v) -> float:
    """解析 shields 缩写星数：'386k' / '1.2m' / '12345' → 数值。"""
    v = str(v).strip().lower().replace(",", "")
    mult = 1
    if v.endswith("k"):
        mult, v = 1000, v[:-1]
    elif v.endswith("m"):
        mult, v = 1000000, v[:-1]
    try:
        return int(float(v) * mult)
    except Exception:
        return 0


def _github_repo_of(url: str = ""):
    """从 github 链接解析 (owner, repo)，失败返回 (None, None)。"""
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url or "")
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _github_star(owner: str, repo: str) -> int:
    """用 shields.io 获取 GitHub star（带缓存）。失败返回 0。"""
    key = f"{owner}/{repo}"
    if key in _GITHUB_STAR_CACHE:
        return _GITHUB_STAR_CACHE[key]
    try:
        req = urllib.request.Request(
            f"https://img.shields.io/github/stars/{owner}/{repo}.json",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            d = json.loads(resp.read().decode("utf-8", "ignore"))
        n = _parse_abbrev(d.get("value") or d.get("message") or 0)
    except Exception:
        n = 0
    _GITHUB_STAR_CACHE[key] = n
    return n


def _fetch_github_stars(cards: list) -> None:
    """对 skillsmp（及有 github 源且暂无星数的）卡片并发获取 GitHub star，填充 stars 字段。"""
    targets = []
    for c in cards:
        if c.get("source") not in ("skillsmp", "lobehub"):
            continue
        if c.get("stars"):
            continue
        o, r = _github_repo_of(c.get("upstream_url") or c.get("homepage") or "")
        if o and r:
            targets.append((c, o, r))
    if not targets:
        return
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(_github_star, o, r): c for c, o, r in targets}
        for f in as_completed(futs):
            c = futs[f]
            try:
                c["stars"] = f.result()
            except Exception:
                c["stars"] = 0


def _heat_of(card: dict) -> float:
    """热度值 = 下载量/安装量/收藏量/星数 中可用的最大者（统一排序指标）。"""
    vals = [
        _num(card.get("downloads")),
        _num(card.get("installs")),
        _num(card.get("stars")),
        _num(card.get("favorites")),
        _num(card.get("likes")),
        _num(card.get("visits")),
    ]
    return max(vals)


def _apply_sort(cards: list, sort: str, q: str = "") -> None:
    """对去重后的本页卡片应用排序（原地）。

    仅两种排序：热度值(默认，按 heat 降序，无热度值排后) / 名称(升序)。
    其余 sort 值兼容保留（verified/updated/downloads/score）。
    """
    s = (sort or "default").strip().lower()
    if s in ("", "default", "heat", "downloads", "score"):
        cards.sort(key=lambda c: (1 if _num(c.get("heat")) > 0 else 0, _num(c.get("heat"))),
                   reverse=True)
    elif s == "name":
        cards.sort(key=lambda c: (c.get("name") or "").lower())
    elif s == "verified":
        cards.sort(key=lambda c: (1 if c.get("verified") else 0, _num(c.get("heat"))),
                   reverse=True)
    elif s == "updated":
        cards.sort(key=lambda c: _num(c.get("updatedAt")), reverse=True)


def get_categories() -> list:
    """统一市场分类：SkillHub 兜底分类 + 各源（官方为主）分类，聚合去重。"""
    cache_key = "u:cats"
    hit = _cache_get(cache_key)
    if hit is not None:
        return hit
    cats: set = set(shub._BASE_CATEGORIES)
    try:
        sh = shub.get_categories(use_cache=True)
        cats.update(sh)
    except Exception:
        pass
    # 官方分类已移除（official 源不再接入）
    result = sorted(cats)
    _cache_put(cache_key, result)
    return result

def _official_skill_files(rel: str) -> dict:
    """Fetch all files under optional-skills/{rel} from GitHub raw (in-memory)."""
    hit = _cache_get(f"official_files|{rel}")
    if hit is not None:
        return hit
    try:
        req = urllib.request.Request(_OFFICIAL_TREE_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        prefix = f"optional-skills/{rel}/"
        blob_paths = [t["path"] for t in d.get("tree", [])
                      if t.get("type") == "blob" and t["path"].startswith(prefix)]
    except Exception:
        blob_paths = []
    files = {}
    for bp in blob_paths:
        try:
            req = urllib.request.Request(f"{OFFICIAL_RAW}/{bp}",
                headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                files[bp[len(prefix):]] = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
    _cache_put(f"official_files|{rel}", files)
    return files

def _install_official(identifier: str, force: bool = False) -> dict:
    """Install a hermes official skill fetched on demand from GitHub (no disk)."""
    rel = identifier.split("/", 1)[-1] if identifier.startswith("official/") else identifier
    files = _official_skill_files(rel)
    if not files:
        return {"ok": False, "error": f"官方技能未找到：{identifier}"}
    name = rel.split("/")[-1]
    import hermes_skills_client as hskills
    meta = {"source_url": f"https://github.com/NousResearch/hermes-agent/tree/main/optional-skills/{rel}"}
    return hskills.install_bundle_files(identifier, name, files, source="official",
                                        trust_level="builtin", metadata=meta, force=force)
def _install_skillsmp(identifier: str, upstream_url: str = "", force: bool = False) -> dict:
    """Install a skillsmp skill by downloading SKILL.md from raw GitHub."""
    import re
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.*)", upstream_url or "")
    if not m:
        m2 = re.match(r"https?://github\.com/([^/]+)/([^/]+)", upstream_url or "")
        if not m2:
            return {"ok": False, "error": "skillsmp 技能缺少 github 地址"}
        owner, repo = m2.group(1), m2.group(2); branch, path = "main", ""
    else:
        owner, repo, branch, path = m.groups()
    raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}/SKILL.md"
    try:
        req = urllib.request.Request(raw, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return {"ok": False, "error": f"下载失败：{type(e).__name__}: {e}"}
    if not content.strip():
        return {"ok": False, "error": "SKILL.md 为空"}
    import hermes_skills_client as hskills
    name = identifier.replace("-", "_").split("_")[-1] or identifier
    return hskills.install_bundle_files(identifier, name, {"SKILL.md": content},
                                        source="skillsmp", trust_level="community",
                                        metadata={"source_url": raw}, force=force)

def _install_lobehub(identifier: str, force: bool = False) -> dict:
    """Install a lobehub skill (convert agent json to SKILL.md)."""
    agent_id = identifier.split("/", 1)[-1]
    try:
        from tools.skills_hub import LobeHubSource
        src = LobeHubSource()
        data = src._fetch_agent(agent_id)
        if not data:
            return {"ok": False, "error": "lobehub 获取 agent 失败"}
        md = src._convert_to_skill_md(data)
    except Exception as e:
        return {"ok": False, "error": f"lobehub 获取失败：{type(e).__name__}: {e}"}
    import hermes_skills_client as hskills
    return hskills.install_bundle_files(identifier, agent_id, {"SKILL.md": md},
                                        source="lobehub", trust_level="community",
                                        metadata={"source_url": f"https://chat-agents.lobehub.com/{agent_id}.json"}, force=force)


def install(identifier: str, upstream_url: str = "", force: bool = False, source: str = "") -> dict:
    """统一安装：按来源走 SkillHub 或 Hermes 各源 fetch（hermes skills add 同路径）。"""
    identifier = (identifier or "").strip()
    if not identifier:
        return {"ok": False, "error": "identifier 为空"}
    source = (source or "").strip()
    if source == "trusttools":
        return _install_trusttools(identifier, upstream_url, force)
    if source == "skillsmp":
        return _install_skillsmp(identifier, upstream_url, force)
    if source == "lobehub":
        return _install_lobehub(identifier, force)
    if source == "modelscope":
        return _install_modelscope(identifier, upstream_url, force)

    # 非 official 的社区标识 → 尝试 SkillHub 下载（slug）
    if not identifier.startswith("official/"):
        try:
            r = shub.download_and_install(upstream_url or "", identifier.split("/")[-1])
            if r.get("ok"):
                return r
        except Exception:
            pass

    # 其余走 Hermes 各源 fetch（进程内 Library 流水线）
    import hermes_skills_client as hskills
    try:
        return hskills.install_from_sources(identifier, force=force)
    except Exception as e:
        return {"ok": False, "error": f"安装失败：{type(e).__name__}: {e}"}


def warm_cache() -> None:
    """后台预热：先拉 browse.sh 大目录，再拉首页（内部顺带缓存分类）。

    服务启动时在后台线程调用，避免用户首次打开市场时撞上冷启动超时。
    """
    try:
        _browse_sh_catalog()
    except Exception:
        pass
    try:
        search_skills(q="", category="", page=1, pageSize=24, use_cache=True)
    except Exception:
        pass


def _github_to_raw(upstream_url, source=""):
    """best-effort 把 GitHub 链接解析为 raw SKILL.md 下载地址；解析失败返回 None。"""
    if not upstream_url:
        return None
    if source == "skillsmp":
        m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.*)", upstream_url)
        if not m:
            m2 = re.match(r"https?://github\.com/([^/]+)/([^/]+)", upstream_url)
            if not m2:
                return None
            owner, repo = m2.group(1), m2.group(2); branch, path = "main", ""
        else:
            owner, repo, branch, path = m.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}/SKILL.md"
    # trusttools：blob 地址（已是文件路径，缺 .md 补 SKILL.md）
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)", upstream_url or "")
    if not m:
        return None
    owner, repo, branch, path = m.groups()
    path = path.rstrip("/")
    if not path.lower().endswith((".md", ".markdown")):
        path = path + "/SKILL.md"
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"


def fetch_content(identifier="", source="", upstream_url=""):
    """best-effort 拉取技能正文(SKILL.md)，不落盘。失败返回 {"ok": False, "error": ...}。

    供详情弹窗使用：已安装技能走本地 read_skill，本函数只处理市场未安装技能。
    """
    identifier = (identifier or "").strip()
    source = (source or "").strip()

    def _fetch_raw(url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return None

    # 1) trusttools / skillsmp：raw GitHub 直接下载 SKILL.md
    if source in ("trusttools", "skillsmp"):
        url = _github_to_raw(upstream_url, source)
        if url:
            content = _fetch_raw(url)
            if content and content.strip():
                return {"ok": True, "body": content, "name": identifier.split("/")[-1]}
        return {"ok": False, "error": "下载 SKILL.md 失败"}

    # 2) lobehub：agent json → SKILL.md
    if source == "lobehub":
        try:
            from tools.skills_hub import LobeHubSource
            src = LobeHubSource()
            data = src._fetch_agent(identifier.split("/")[-1])
            if data:
                md = src._convert_to_skill_md(data)
                if md:
                    return {"ok": True, "body": md, "name": identifier.split("/")[-1]}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        return {"ok": False, "error": "lobehub 获取失败"}

    # 2.5) modelscope：从 GitHub SourceURL 拉 SKILL.md 正文
    if source == "modelscope":
        url = _modelscope_raw_url(upstream_url)
        if url:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    content = resp.read().decode("utf-8", "ignore")
                if content and content.strip():
                    return {"ok": True, "body": content, "name": identifier.split("/")[-1]}
            except Exception as e:
                return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        return {"ok": False, "error": "ModelScope 技能缺少 GitHub 源地址"}

    # 3) 其余（community/official/github 等）：Hermes 各源 bundle 提取 SKILL.md
    try:
        import hermes_skills_client as hskills
        meta, bundle = hskills._resolve_meta_and_bundle(
            identifier, hskills._sources_no_index())
        if bundle:
            body = bundle.files.get("SKILL.md")
            if isinstance(body, bytes):
                body = body.decode("utf-8", "ignore")
            if body:
                return {"ok": True, "body": body, "name": bundle.name,
                        "description": (meta.description if meta else "")}
        return {"ok": False, "error": "无法获取正文（GitHub 未鉴权限流或该技能无 SKILL.md）"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
