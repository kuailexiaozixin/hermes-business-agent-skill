"""Agent 实例缓存池（P0：消除每轮 build_agent 重建开销；P1：首轮预热底座）

背景
----
``stream_agent_chat`` 的 worker 每轮调用 ``factory()``（默认 ``build_agent``）重建
整个 AIAgent：首轮 4.4~5.7s（模块导入 + 工具注册发现 + 上下文扫描 + AIAgent 构造），
后续每轮 0.33~0.47s（AIAgent 实例整体重建，工具集重新注册、上下文重新扫描）。

复用可行性（代码实证，hermes-agent 0.18.2）：
- AIAgent 回调（``tool_start_callback`` / ``tool_complete_callback`` /
  ``reasoning_callback`` / ``tool_progress_callback``）均为**实例属性**
  （agent_init.py:523-528），命中后可动态替换；
- ``stream_callback`` 由 ``run_conversation`` 每次传入，与实例天然解耦；
- ``run_conversation`` 每轮经 ``build_turn_context`` 独立构建上下文，并始终以
  传入的 ``conversation_history`` 为准 —— 历史不会在实例上累积串台；
- 会话级状态（session_id / token 计数器 / context engine 绑定）可用
  ``reset_session_state(old_session_id, new_session_id)`` 一键重置并重绑。

设计
----
- **池化 + 借出/归还**：同一 key 的空闲实例同一时刻只借给一个使用者，用完归还。
  并发多会话同 key 时各自 miss 构造独立实例，互不串台（安全优先于命中率）。
- **会话级重置**：命中复用前必须重置 —— 新 session_id（隔离 Hermes 持久化 /
  记忆 / turn 状态）+ ``reset_session_state``（清计数器、重置 context engine 并
  重绑 session_db）+ 替换回调属性 + 重设 TERMINAL_CWD。
- **缓存键**：覆盖 factory 全部影响构造的入参（模型配置关键字段、working_dir、
  web_search、enabled_toolsets）；``max_iterations`` 为运行时参数（实例属性，
  复用前覆盖），不入键；``ephemeral_system_prompt`` 不参与键值（运行时属性
  重置，避免不同对话的系统提示差异击穿缓存）。
- **LRU 上限**：每 key 最多 1 个空闲实例；总 key 数上限 8，超出淘汰最久未用。
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any, Callable


# ---------------------------------------------------------------------------
# 池与统计
# ---------------------------------------------------------------------------
_POOL: "dict[tuple, list[Any]]" = {}
_LOCK = threading.Lock()
_STATS = {"hits": 0, "misses": 0, "evictions": 0, "prewarmed": 0}
_LAST_USED: "dict[tuple, float]" = {}

_MAX_KEYS = 8          # 总 key 数上限（LRU 淘汰）
_MAX_IDLE_PER_KEY = 1  # 每 key 空闲实例上限（同 key 并发多会话各自 miss 构造）

_MARK_ATTR = "__marvis_cache_key__"


def _now() -> float:
    return time.monotonic()


def _cache_key(model_cfg: dict, *, working_dir, web_search,
               enabled_toolsets) -> tuple:
    """构造缓存键：只取影响 AIAgent 构造的稳定字段。

    ``max_iterations`` 是运行时参数（实例属性、复用前覆盖），不参与键值；
    否则首轮预热（None）与对话请求（如 2）key 不一致导致预热失效。
    """
    rc = model_cfg.get("reasoning_config") or {}
    ro = model_cfg.get("request_overrides") or {}
    return (
        model_cfg.get("vendor"),
        model_cfg.get("provider"),
        model_cfg.get("model"),
        model_cfg.get("base_url"),
        model_cfg.get("api_key"),
        model_cfg.get("max_tokens"),
        str(sorted(rc.items()) if isinstance(rc, dict) else rc),
        str(sorted(ro.items()) if isinstance(ro, dict) else ro),
        os.path.realpath(working_dir) if working_dir and os.path.isdir(working_dir) else None,
        bool(web_search),
        tuple(enabled_toolsets) if enabled_toolsets else None,
    )


def _mark(agent: Any, key: tuple) -> None:
    try:
        setattr(agent, _MARK_ATTR, key)
    except Exception:
        pass


def _unmark(agent: Any) -> None:
    try:
        if hasattr(agent, _MARK_ATTR):
            delattr(agent, _MARK_ATTR)
    except Exception:
        pass


def _borrow(key: tuple):
    """借出空闲实例；无则返回 None（调用方负责 miss 构造）。"""
    with _LOCK:
        lst = _POOL.get(key)
        if lst:
            agent = lst.pop()
            if not lst:
                _POOL.pop(key, None)
            _LAST_USED.pop(key, None)
            return agent
    return None


def _put(key: tuple, agent: Any) -> bool:
    """归还实例；超限（每 key 上限 / 总 key 上限）时丢弃并返回 False。"""
    with _LOCK:
        lst = _POOL.setdefault(key, [])
        if len(lst) >= _MAX_IDLE_PER_KEY:
            _POOL.pop(key, None) if not lst else None
            return False
        lst.append(agent)
        _LAST_USED[key] = _now()
        # LRU：总 key 数超限时淘汰最久未用的 key（丢弃其全部空闲实例）
        while len(_POOL) > _MAX_KEYS:
            victim = min(_LAST_USED, key=_LAST_USED.get)
            _POOL.pop(victim, None)
            _LAST_USED.pop(victim, None)
            _STATS["evictions"] += 1
        return True


def _new_session_id() -> str:
    """与 agent_init.py 同格式生成新 session_id（隔离持久化/记忆/turn 状态）。"""
    return f"{time.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _reset_for_reuse(agent: Any, *, model_cfg: dict,
                     ephemeral_system_prompt: str | None,
                     tool_start_callback: Callable | None,
                     tool_complete_callback: Callable | None,
                     reasoning_callback: Callable | None,
                     tool_progress_callback: Callable | None,
                     web_search: bool, working_dir: str | None,
                     max_iterations: int | None = None) -> None:
    """复用前的会话级重置：新 session + 清计数器 + 重绑 context engine + 换回调。

    全部 best-effort：任何一步失败都不影响复用（Hermes 每轮 build_turn_context
    会独立重建上下文，缺失的可选重置仅影响计数/记忆精度）。
    """
    # 1) 会话隔离：换新 session_id（turn_id / 持久化 / 记忆均以它键控）
    old_sid = getattr(agent, "session_id", None)
    new_sid = _new_session_id()
    try:
        agent.session_id = new_sid
        os.environ["HERMES_SESSION_ID"] = new_sid
    except Exception:
        pass
    # 2) 清 token 计数器 + 重置 context engine 并重绑 session_db（见
    #    run_agent.py reset_session_state：自动 bind_session_state）
    try:
        agent.reset_session_state(old_session_id=old_sid, new_session_id=new_sid,
                                  carry_over_context=False)
    except Exception:
        try:
            agent.reset_session_state()
        except Exception:
            pass
    # 3) 回调属性替换（AIAgent 回调均为实例属性，agent_init.py:523-528）
    try:
        agent.tool_start_callback = tool_start_callback
        agent.tool_complete_callback = tool_complete_callback
        agent.reasoning_callback = reasoning_callback
        agent.tool_progress_callback = tool_progress_callback
    except Exception:
        pass
    # 4) ephemeral_system_prompt 同步（不入缓存键；缺失则忽略）
    if ephemeral_system_prompt:
        try:
            if hasattr(agent, "ephemeral_system_prompt"):
                agent.ephemeral_system_prompt = ephemeral_system_prompt
        except Exception:
            pass
    # 5) TERMINAL_CWD 与工作目录一致（与 build_agent 行为对齐）
    if working_dir and os.path.isdir(working_dir):
        try:
            os.environ["TERMINAL_CWD"] = os.path.realpath(working_dir)
        except Exception:
            pass
    else:
        os.environ.pop("TERMINAL_CWD", None)
    # 6) 运行时参数覆盖：max_iterations 不入缓存键，复用前按本次请求覆盖
    if max_iterations is not None:
        try:
            agent.max_iterations = max_iterations
        except Exception:
            pass
    _ = web_search  # 构造期已按 web_search 装配工具集，复用沿用


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------
def cached_build_agent(model_cfg: dict, *,
                       max_iterations: int | None = None,
                       ephemeral_system_prompt: str | None = None,
                       tool_start_callback: Callable | None = None,
                       tool_complete_callback: Callable | None = None,
                       reasoning_callback: Callable | None = None,
                       tool_progress_callback: Callable | None = None,
                       enabled_toolsets: list[str] | None = None,
                       web_search: bool = True,
                       working_dir: str | None = None) -> Any:
    """``build_agent`` 的缓存包装：命中复用 + 会话级重置，miss 构造并标记。"""
    from ._chat import build_agent  # 延迟导入，避免循环依赖

    key = _cache_key(model_cfg, working_dir=working_dir, web_search=web_search,
                     enabled_toolsets=enabled_toolsets)
    agent = _borrow(key)
    if agent is not None:
        _STATS["hits"] += 1
        _mark(agent, key)  # 重新打标记：首次 release 时已清除，须补回才能归还
        _reset_for_reuse(
            agent, model_cfg=model_cfg,
            ephemeral_system_prompt=ephemeral_system_prompt,
            tool_start_callback=tool_start_callback,
            tool_complete_callback=tool_complete_callback,
            reasoning_callback=reasoning_callback,
            tool_progress_callback=tool_progress_callback,
            web_search=web_search, working_dir=working_dir,
            max_iterations=max_iterations,
        )
        return agent

    _STATS["misses"] += 1
    agent = build_agent(
        model_cfg, max_iterations=max_iterations,
        ephemeral_system_prompt=ephemeral_system_prompt,
        tool_start_callback=tool_start_callback,
        tool_complete_callback=tool_complete_callback,
        reasoning_callback=reasoning_callback,
        tool_progress_callback=tool_progress_callback,
        enabled_toolsets=enabled_toolsets,
        web_search=web_search, working_dir=working_dir,
    )
    _mark(agent, key)
    return agent


def release_agent(agent: Any) -> None:
    """归还缓存的 Agent 到池中；非缓存实例（无标记）直接忽略。"""
    if agent is None:
        return
    key = getattr(agent, _MARK_ATTR, None)
    if key is None:
        return
    _unmark(agent)
    _put(key, agent)


def prewarm_agent(model_cfg: dict, *,
                  max_iterations: int | None = None,
                  web_search: bool = True,
                  working_dir: str | None = None) -> bool:
    """P1 首轮预热：后台预构造默认模型 Agent 并放入池，使首轮对话直接命中。

    无有效 api_key 时直接返回 False（调用方也应跳过；此处双保险，
    避免无 Key 场景下预构造一个必然 401 的实例进池）；构造失败保持静默（best-effort）。
    """
    if not (model_cfg or {}).get("api_key"):
        return False
    key = _cache_key(model_cfg, working_dir=working_dir, web_search=web_search,
                     enabled_toolsets=None)
    with _LOCK:
        if _POOL.get(key):
            return False  # 已预热，跳过
    from ._chat import build_agent  # 延迟导入，避免循环依赖
    try:
        agent = build_agent(model_cfg, max_iterations=max_iterations,
                            web_search=web_search, working_dir=working_dir)
        _mark(agent, key)
        ok = _put(key, agent)
        if ok:
            _STATS["prewarmed"] += 1
        return ok
    except Exception:
        return False


def cache_stats() -> dict:
    """缓存统计（命中/未命中/淘汰/预热/当前池大小）。"""
    with _LOCK:
        return dict(_STATS, size=sum(len(v) for v in _POOL.values()),
                    keys=len(_POOL))


def clear_cache() -> None:
    """清空缓存池（改配置/重装工具后调用）。"""
    with _LOCK:
        _POOL.clear()
        _LAST_USED.clear()
        _STATS["hits"] = _STATS["misses"] = 0
