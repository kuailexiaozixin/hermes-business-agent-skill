// @ts-check
/* =====================================================================
 * views.js — 主区视图路由 + 各独立屏渲染（chat 之外的屏）
 *   showView / VIEW_RENDERERS / renderCurrentView / refreshPanels
 *   + render*View 包装器（委托给 panels.js 的 render*Panel）
 *   + Soul / 记忆 / 系统提示词 / Wiki / Kanban 视图
 * 依赖：dom / state / api（叶子）+ Panels（render*Panel/wikiModal）+ Channels（renderChannelsView）
 * ===================================================================== */
import { $, el, toast } from "./dom.js";
import { State } from "./state.js";
import { getJSON, postJSON, delJSON } from "./api.js";
import * as Panels from "./panels.js";
import * as Channels from "./channels.js";

// ------------------------------------------------------------------ 主区视图切换
// 已渲染视图缓存：模块视图首次进入才全量渲染，之后仅显隐，避免每次切换都清空重建 + 重复请求导致卡顿。
// 各面板内部的「刷新」按钮仍直接调用 render*View，不受缓存影响。
const _renderedViews = new Set();
function showView(name) {
  State.currentView = name;
  document.querySelectorAll("#sideNav .nav").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  const act = document.querySelector('#sideNav .nav[data-view="' + name + '"]');
  if (act && act.scrollIntoView) { try { act.scrollIntoView({ block: "nearest" }); } catch (_) {} }
  const isChat = name === "chat";
  const chat = $("#chat"), comp = $("#composerWrap");
  if (chat) chat.style.display = isChat ? "" : "none";
  if (comp) comp.style.display = isChat ? "" : "none";
  // 对话区标题栏（新对话/会话操作/搜索/皮肤/主题/用量/导出/配置等）仅在对话视图显示，
  // 避免覆盖功能面板自己的标题与内容。
  const topbar = $(".topbar");
  if (topbar) topbar.classList.toggle("hidden", !isChat);
  document.querySelectorAll(".app-view").forEach((v) => v.classList.add("hidden"));
  if (!isChat) {
    const v = $("#view-" + name);
    if (v) v.classList.remove("hidden");
    if (!_renderedViews.has(name)) {
      _renderedViews.add(name);
      renderCurrentView();
    }
  }
}

// 主区独立视图路由表：视图名 -> 渲染函数（单一注册表，替代原 if/else 级联）
const VIEW_RENDERERS = {
  skills: renderSkillsView, models: renderModelsView, plugins: renderPluginsView,
  cron: renderCronView,   tools: renderToolsView, mcp: renderMcpView, loops: renderLoopsView,
  delegation: renderDelegationView, memory: renderMemoryView, context: renderContextView, soul: renderSoulView,
  wiki: renderWikiView, channels: Channels.renderChannelsView, kanban: renderKanbanView,
  sysprompt: renderSyspromptView,
  goals: renderGoalsView, checkpoints: renderCheckpointsView, moa: renderMoaView,
  projects: renderProjectsView, bundles: renderBundlesView, security: renderSecurityView,
  blueprints: renderBlueprintsView, batch: renderBatchView, journey: renderJourneyView,
  backup: renderBackupView,   profiles: renderProfilesView, curator: renderCuratorView,
  routing: renderRoutingView, workspace: renderWorkspaceView, snapshots: renderSnapshotsView,
  logs: renderLogsView, structured: renderStructuredView,
};
function renderCurrentView() {
  const fn = VIEW_RENDERERS[State.currentView];
  if (fn) fn();
}

async function renderSkillsView() {
  const v = $("#view-skills"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  try { await Panels.renderSkillsPanel(sp); } catch (e) { sp.appendChild(el("div", { class: "muted", text: "加载失败：" + e.message })); }
}
async function renderModelsView() {
  const v = $("#view-models"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  try { await Panels.renderModelsPanel(sp); } catch (e) { sp.appendChild(el("div", { class: "muted", text: "加载失败：" + e.message })); }
}
async function renderPluginsView() {
  const v = $("#view-plugins"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  try { await Panels.renderPluginsPanel(sp); } catch (e) { sp.appendChild(el("div", { class: "muted", text: "加载失败：" + e.message })); }
}
async function renderCronView() {
  const v = $("#view-cron"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  try { await Panels.renderCronPanel(sp); } catch (e) { sp.appendChild(el("div", { class: "muted", text: "加载失败：" + e.message })); }
}
async function renderToolsView() {
  const v = $("#view-tools"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  try { await Panels.renderToolsPanel(sp); } catch (e) { sp.appendChild(el("div", { class: "muted", text: "加载失败：" + e.message })); }
}
async function renderMcpView() {
  const v = $("#view-mcp"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  try { await Panels.renderMcpPanel(sp); } catch (e) { sp.appendChild(el("div", { class: "muted", text: "加载失败：" + e.message })); }
}
async function renderLoopsView() {
  const v = $("#view-loops"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  try { await Panels.renderLoopsPanel(sp); } catch (e) { sp.appendChild(el("div", { class: "muted", text: "加载失败：" + e.message })); }
}
async function renderDelegationView() {
  const v = $("#view-delegation"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  try { await Panels.renderDelegationPanel(sp); } catch (e) { sp.appendChild(el("div", { class: "muted", text: "加载失败：" + e.message })); }
}

// ------------------------------------------------------------------ Soul / 记忆 / 系统提示词 / Wiki / Kanban
async function renderSoulView() {
  const v = $("#view-soul"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  const d = await getJSON("/api/soul").catch(() => ({ ok: false }));
  if (!d || !d.ok) { sp.appendChild(el("div", { class: "muted", text: "加载失败" })); return; }
  sp.appendChild(el("div", { class: "section-title", text: "Soul 人格（SOUL.md）" }));
  sp.appendChild(el("div", { class: "muted small", text: "SOUL.md 定义智能体人格身份。启用后新会话会将其注入系统提示词。" }));
  const sw = el("label", { class: "switch" }, [
    el("input", { type: "checkbox", ...(d.enabled ? { checked: "checked" } : {}) }),
    el("span", { class: "slider" }),
  ]);
  sp.appendChild(el("div", { class: "field-inline" }, [
    el("span", { text: "启用 Soul 加载（新会话生效）" }), sw,
  ]));
  const ta = el("textarea", { class: "editor", rows: 16 });
  ta.value = d.content || "";
  sp.appendChild(ta);
  sp.appendChild(el("div", { class: "actions-row" }, [
    el("button", { class: "btn primary", text: "保存", onclick: async () => {
      const r = await postJSON("/api/soul", { content: ta.value, enabled: sw.querySelector("input").checked }).catch(e => ({ ok: false, error: e.message }));
      if (r.ok) toast("已保存，新会话生效", "ok"); else toast("保存失败：" + (r.error || ""), "err");
    } }),
  ]));
}

async function renderMemoryView() {
  const v = $("#view-memory"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  const d = await getJSON("/api/memory").catch(() => ({ ok: false }));
  if (!d || !d.ok) { sp.appendChild(el("div", { class: "muted", text: "加载失败" })); return; }
  sp.appendChild(el("div", { class: "section-title", text: "记忆管理（memories/）" }));
  sp.appendChild(el("div", { class: "muted small", text: "MEMORY.md 记录环境事实与项目约定；USER.md 记录对用户的了解。条目以 § 分隔，记忆循环开启后按会话注入。" }));
  // ── 记忆增强：Provider 切换 + 向量检索 + 分层查看（对照 13 §2.2） ──
  const provWrap = el("div", { class: "panel", style: "margin-bottom:12px;" });
  provWrap.appendChild(el("div", { class: "card-title", text: "记忆 Provider" }));
  const provRow = el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap;" });
  const provSel = el("select", { class: "form-input", style: "max-width:240px;" });
  const provBtn = el("button", { class: "btn primary", text: "切换", onclick: async () => {
    const r = await postJSON("/api/memory/provider/switch", { provider: provSel.value }).catch(e => ({ ok:false, error:e.message }));
    if (r.ok) { toast("已切换到 " + provSel.value, "ok"); loadProviders(); }
    else toast("切换失败：" + (r.error || ""), "err");
  } });
  const provStatus = el("span", { class: "muted small", style: "margin-left:4px;", text: "" });
  async function loadProviders() {
    const d = await getJSON("/api/memory/providers").catch(() => ({ ok:false }));
    provSel.innerHTML = "";
    if (!d.ok) { provStatus.textContent = "加载失败"; return; }
    for (const p of d.providers || []) {
      provSel.appendChild(el("option", { value: p.id, text: p.id + (p.active ? "（当前）" : ""), selected: !!p.active }));
    }
    provStatus.textContent = "当前：" + (d.current || "");
  }
  provRow.appendChild(provSel); provRow.appendChild(provBtn); provRow.appendChild(provStatus);
  provWrap.appendChild(provRow);
  sp.appendChild(provWrap);
  loadProviders();

  // 向量/语义检索
  const searchWrap = el("div", { class: "panel", style: "margin-bottom:12px;" });
  searchWrap.appendChild(el("div", { class: "card-title", text: "向量/语义检索（holographic）" }));
  const sRow = el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap;" });
  const sIn = el("input", { class: "form-input", style: "flex:1;min-width:200px;", placeholder: "输入查询，按语义检索记忆…", onkeydown: e => { if (e.key === "Enter") runSearch(); } });
  const sBtn = el("button", { class: "btn primary", text: "检索", onclick: runSearch });
  const sOut = el("div", { style: "margin-top:8px;" });
  async function runSearch() {
    const q = sIn.value.trim(); if (!q) { sOut.innerHTML = ""; return; }
    sOut.innerHTML = "";
    const d = await getJSON("/api/memory/search?q=" + encodeURIComponent(q)).catch(() => ({ ok:false }));
    if (!d.ok) { sOut.appendChild(el("div", { class: "muted", text: d.error || "检索失败" })); return; }
    if (!d.items || !d.items.length) { sOut.appendChild(el("div", { class: "muted", text: "未找到相关记忆" })); return; }
    for (const it of d.items) {
      sOut.appendChild(el("div", { class: "panel", style: "padding:8px;margin-bottom:6px;" }, [
        el("div", { class: "small", text: (it.content || "").slice(0, 200) }),
        el("div", { class: "muted small", text: "分类:" + (it.category || "-") + " · 评分:" + (it.score != null ? it.score : "-") + " · 信任:" + (it.trust_score != null ? it.trust_score : "-") }),
      ]));
    }
  }
  sRow.appendChild(sIn); sRow.appendChild(sBtn);
  searchWrap.appendChild(sRow); searchWrap.appendChild(sOut);
  sp.appendChild(searchWrap);

  // 分层查看
  const layerWrap = el("div", { class: "panel" });
  layerWrap.appendChild(el("div", { class: "card-title", text: "分层查看（记忆文件 / 记忆事实 / provider）" }));
  const layerBtn = el("button", { class: "btn", text: "加载分层", onclick: loadLayers });
  const layerOut = el("div", { style: "margin-top:8px;" });
  async function loadLayers() {
    layerOut.innerHTML = "";
    const d = await getJSON("/api/memory/layers").catch(() => ({ ok:false }));
    if (!d.ok) { layerOut.appendChild(el("div", { class: "muted", text: d.error || "加载失败" })); return; }
    layerOut.appendChild(el("div", { class: "small", text: "Active Provider: " + (d.active_provider || "") }));
    const fc = d.facts_by_category || {};
    if (fc.error) { layerOut.appendChild(el("div", { class: "muted small", text: fc.error })); }
    else {
      layerOut.appendChild(el("div", { class: "small", style: "margin-top:4px;", text: "记忆事实（holographic）: " + (d.fact_count != null ? d.fact_count : 0) + " 条" }));
      for (const cat of Object.keys(fc)) {
        const items = fc[cat] || [];
        layerOut.appendChild(el("div", { class: "small", style: "margin-top:6px;", text: "▸ " + cat + "（" + items.length + "）" }));
        for (const it of items.slice(0, 5)) {
          layerOut.appendChild(el("div", { class: "muted small", style: "margin-left:12px;", text: "· " + (it.content || "").slice(0, 120) }));
        }
      }
    }
  }
  layerWrap.appendChild(layerBtn); layerWrap.appendChild(layerOut);
  sp.appendChild(layerWrap);


  // 搜索框
  let _memFilter = "";
  const searchInput = el("input", { class: "form-input", style: "margin-bottom:12px;", placeholder: "搜索记忆文件名/内容…",
    oninput: () => { _memFilter = searchInput.value.trim().toLowerCase(); applyMemFilter(); } });
  const listWrap = el("div", { id: "mem-list" });
  sp.appendChild(searchInput);
  sp.appendChild(listWrap);
  function applyMemFilter() {
    const cards = listWrap.querySelectorAll(".panel");
    let visible = 0;
    for (const card of cards) {
      const txt = (card.dataset.search || "").toLowerCase();
      const match = !_memFilter || txt.includes(_memFilter);
      card.style.display = match ? "" : "none";
      if (match) visible++;
    }
    let noResult = listWrap.querySelector(".mem-no-result");
    if (!visible && _memFilter) {
      if (!noResult) {
        noResult = el("div", { class: "muted mem-no-result", style: "padding:14px;text-align:center;", text: "未找到匹配的记忆条目" });
        listWrap.appendChild(noResult);
      }
      noResult.style.display = "";
    } else if (noResult) {
      noResult.style.display = "none";
    }
  }
  for (const f of d.files || []) {
    const card = el("div", { class: "panel" });
    card.dataset.search = f.name + " " + (f.text || "");
    card.appendChild(el("div", { class: "card-title" }, [
      el("b", { text: f.name }), el("span", { class: "badge", text: f.count + " 条" }),
    ]));
    const ta = el("textarea", { class: "editor", rows: 8 });
    ta.value = f.text || "";
    card.appendChild(ta);
    card.appendChild(el("div", { class: "actions-row" }, [
      el("button", { class: "btn primary", text: "保存 " + f.name, onclick: async () => {
        const r = await postJSON("/api/memory/" + f.name, { text: ta.value }).catch(e => ({ ok: false, error: e.message }));
        if (r.ok) toast("已保存", "ok"); else toast("保存失败：" + (r.error || ""), "err");
      } }),
    ]));
    listWrap.appendChild(card);
  }
  // 导出按钮
  sp.appendChild(el("div", { class: "export-actions-row" }, [
    el("button", { class: "btn primary", text: "⭳ 导出记忆 (JSON)", onclick: async () => {
      try {
        const r = await getJSON("/api/memory/export");
        if (!r.ok) { toast("导出失败：" + (r.error || ""), "err"); return; }
        const blob = new Blob([JSON.stringify(r, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = el("a", { href: url, download: "memory-export-" + new Date().toISOString().slice(0, 10) + ".json" });
        document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
        toast("记忆已导出", "ok");
      } catch (e) { toast("导出失败：" + e.message, "err"); }
    } }),
  ]));
}

async function renderContextView() {
  const v = $("#view-context"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  sp.appendChild(el("div", { class: "section-title", text: "上下文管理" }));
  sp.appendChild(el("div", { class: "muted small", text: "选择上下文压缩引擎、查看会话上下文水位、主动压缩并跟踪压缩历史。" }));

  // ── 引擎选择 ──
  const engWrap = el("div", { class: "panel", style: "margin-bottom:12px;" });
  engWrap.appendChild(el("div", { class: "card-title", text: "上下文压缩引擎" }));
  const engRow = el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap;" });
  const engSel = el("select", { class: "form-input", style: "max-width:260px;" });
  const engBtn = el("button", { class: "btn primary", text: "切换", onclick: async () => {
    const r = await postJSON("/api/context/engine", { engine_id: engSel.value }).catch(e => ({ ok:false, error:e.message }));
    if (r.ok) { toast("已切换为 " + engSel.value + "（新会话/重启后生效）", "ok"); loadEngines(); refreshStatus(); }
    else toast("切换失败：" + (r.error || ""), "err");
  } });
  const engStatus = el("span", { class: "muted small", style: "margin-left:4px;", text: "" });
  async function loadEngines() {
    const d = await getJSON("/api/context/engines").catch(() => ({ ok:false }));
    engSel.innerHTML = "";
    if (!d.ok) { engStatus.textContent = "加载失败"; return; }
    for (const e of d.engines || []) {
      engSel.appendChild(el("option", { value: e.id, text: e.id + (e.active ? "（当前）" : "") + (e.builtin ? " [内置]" : ""), selected: !!e.active }));
    }
    engStatus.textContent = "当前：" + (d.current || "") + "（写入配置，新会话生效）";
  }
  engRow.appendChild(engSel); engRow.appendChild(engBtn); engRow.appendChild(engStatus);
  engWrap.appendChild(engRow);
  sp.appendChild(engWrap);
  loadEngines();

  // ── 压缩状态 + token 跟踪 ──
  const stWrap = el("div", { class: "panel", style: "margin-bottom:12px;" });
  stWrap.appendChild(el("div", { class: "card-title", text: "压缩状态 / token 跟踪" }));
  const stRow = el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px;" });
  const hasConv = !!State.conv_id;
  stRow.appendChild(el("span", { class: "muted small", text: hasConv ? ("当前会话：" + State.conv_id) : "未选择会话——先在左侧选择或新建会话" }));
  const compressBtn = el("button", { class: "btn" + (hasConv ? " primary" : ""), text: "立即压缩", disabled: !hasConv, onclick: doCompress });
  stRow.appendChild(compressBtn);
  stRow.appendChild(el("button", { class: "btn", text: "刷新", onclick: refreshStatus }));
  stWrap.appendChild(stRow);
  const stOut = el("div", {});
  stWrap.appendChild(stOut);
  sp.appendChild(stWrap);

  // ── 压缩历史 ──
  const histWrap = el("div", { class: "panel" });
  histWrap.appendChild(el("div", { class: "card-title", text: "压缩历史" }));
  const histOut = el("div", {});
  histWrap.appendChild(histOut);
  sp.appendChild(histWrap);

  async function doCompress() {
    if (!State.conv_id) { toast("请先选择会话", "err"); return; }
    compressBtn.disabled = true; compressBtn.textContent = "压缩中…";
    const r = await postJSON("/api/context/compress", { conv_id: State.conv_id }).catch(e => ({ ok:false, error:e.message }));
    compressBtn.disabled = false; compressBtn.textContent = "立即压缩";
    if (!r.ok) { toast("压缩失败：" + (r.error || ""), "err"); return; }
    if (r.compressed) toast("已压缩：" + r.original_count + " → " + r.compressed_count + " 条", "ok");
    else toast("未压缩：" + (r.reason || ""), "info");
    refreshStatus(); loadHistory();
  }

  function fmtN(v) { return (v === null || v === undefined) ? "未知" : v; }

  async function refreshStatus() {
    stOut.innerHTML = "";
    if (!State.conv_id) {
      stOut.appendChild(el("div", { class: "muted small", text: "请先选择或新建一个会话以查看上下文水位。" }));
      histOut.innerHTML = "";
      return;
    }
    const d = await getJSON("/api/context/status?cid=" + encodeURIComponent(State.conv_id)).catch(() => ({ ok:false }));
    if (!d.ok) { stOut.appendChild(el("div", { class: "muted", text: d.error || "加载失败" })); return; }
    const cw = d.context_window;
    const cwTxt = cw ? (cw >= 1000 ? (cw/1000).toFixed(1) + "K" : String(cw)) : "未知";
    const up = d.usage_percent;
    const sc = d.should_compress === true ? "需要压缩 ⚠️" : (d.should_compress === false ? "未触发" : "未知");
    stOut.appendChild(el("div", { class: "small", style: "margin-top:4px;", text: "活动引擎：" + (d.active_engine || "-") + (d.engine_live ? "（实时）" : "（推算）") }));
    stOut.appendChild(el("div", { class: "small", text: "上下文窗口：" + cwTxt + " · 压缩阈值：" + (d.threshold_tokens ?? "未知") }));
    stOut.appendChild(el("div", { class: "small", text: "压缩次数：" + fmtN(d.compression_count) + " · 判定：" + sc }));
    const diag = d.diagnostics || {};
    if (diag.reason) stOut.appendChild(el("div", { class: "small muted", style: "margin-top:2px;", text: "提示：" + diag.reason }));
    stOut.appendChild(el("div", { class: "small", style: "margin-top:4px;", text: "会话 token：" + (d.session_tokens ? ("输入 " + (d.session_tokens.input||0) + " / 输出 " + (d.session_tokens.output||0)) : "无数据") + (up != null ? " · 已用 " + up + "%" : "") }));
    if (up != null) {
      const bar = el("div", { style: "height:10px;background:#eee;border-radius:5px;margin-top:8px;overflow:hidden;" });
      const fill = el("div", { style: "height:100%;width:" + Math.min(100, up) + "%;background:" + (up > 80 ? "#e53935" : up > 60 ? "#fb8c00" : "#43a047") + ";" });
      bar.appendChild(fill);
      stOut.appendChild(bar);
    }
  }

  async function loadHistory() {
    histOut.innerHTML = "";
    if (!State.conv_id) { histOut.appendChild(el("div", { class: "muted small", text: "选择会话后显示压缩历史。" })); return; }
    const d = await getJSON("/api/context/history?conv_id=" + encodeURIComponent(State.conv_id)).catch(() => ({ ok:false }));
    if (!d.ok) { histOut.appendChild(el("div", { class: "muted small", text: "加载历史失败" })); return; }
    const hs = d.history || [];
    if (!hs.length) { histOut.appendChild(el("div", { class: "muted small", text: "暂无压缩记录。" })); return; }
    for (const h of hs) {
      histOut.appendChild(el("div", { class: "small", style: "margin-top:2px;",
        text: "[" + h.at + "] " + h.original_count + " → " + h.compressed_count + " 条（节省 " + h.saved + "）" + (h.reason ? " · " + h.reason : "") }));
    }
  }

  refreshStatus(); loadHistory();
}


async function renderSyspromptView() {
  const v = $("#view-sysprompt"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  const d = await getJSON("/api/system-prompt").catch(() => ({ ok: false }));
  if (!d || !d.ok) { sp.appendChild(el("div", { class: "muted", text: "加载失败" })); return; }
  sp.appendChild(el("div", { class: "section-title", text: "系统提示词" }));
  sp.appendChild(el("div", { class: "muted small", text: "自定义系统提示词以 ephemeral 方式注入并覆盖默认提示词（新会话生效）；留空则使用默认。" }));
  const ta = el("textarea", { class: "editor", rows: 14 });
  ta.value = d.custom || "";
  sp.appendChild(el("div", { class: "field" }, [el("label", { text: "自定义提示词（留空 = 使用默认）" }), ta]));
  sp.appendChild(el("div", { class: "actions-row" }, [
    el("button", { class: "btn primary", text: "保存", onclick: async () => {
      const r = await postJSON("/api/system-prompt", { custom: ta.value }).catch(e => ({ ok: false, error: e.message }));
      if (r.ok) toast("已保存，新会话生效", "ok"); else toast("保存失败：" + (r.error || ""), "err");
    } }),
    el("button", { class: "btn ghost", text: "清空（还原默认）", onclick: async () => {
      ta.value = "";
      const r = await postJSON("/api/system-prompt", { custom: "" }).catch(e => ({ ok: false, error: e.message }));
      if (r.ok) toast("已还原默认", "ok"); else toast("失败：" + (r.error || ""), "err");
    } }),
  ]));
  sp.appendChild(el("div", { class: "section-title", text: "默认提示词（只读）" }));
  const pre = el("pre", { class: "code-block" });
  pre.textContent = d.default || "";
  sp.appendChild(pre);
}

// ── LLM Wiki 视图（对齐 Hermes llm-wiki：三层互联知识库 + 图/摄入/询问/健康） ──
let _wikiMode = "list";          // list | graph
const _wikiFilter = { q: "", type: "", tag: "" };
const WIKI_TYPE_LABEL = { entity: "实体", concept: "概念", comparison: "对比", query: "问答", summary: "综述" };

async function renderWikiView() {
  const v = $("#view-wiki"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  sp.appendChild(renderWikiToolbar());
  if (_wikiMode === "graph") {
    sp.appendChild(await renderWikiGraph());
  } else {
    sp.appendChild(await renderWikiList());
  }
}

function renderWikiToolbar() {
  const search = el("input", { class: "form-input wiki-search", placeholder: "搜索标题/标签…", value: _wikiFilter.q });
  search.addEventListener("input", () => { _wikiFilter.q = search.value.trim(); renderWikiView(); });
  const typeSel = el("select", { class: "form-input wiki-type" }, [
    el("option", { value: "", text: "全部类型" }),
    ...Object.entries(WIKI_TYPE_LABEL).map(([k, lbl]) => el("option", { value: k, text: lbl, selected: _wikiFilter.type === k ? "selected" : null })),
  ]);
  typeSel.addEventListener("change", () => { _wikiFilter.type = typeSel.value; renderWikiView(); });
  return el("div", { class: "wiki-toolbar" }, [
    search, typeSel,
    el("button", { class: "btn primary", text: "＋ 新建", onclick: () => Panels.wikiModal("create", null) }),
    el("button", { class: "btn ghost", text: "📥 摄入", onclick: () => wikiIngestPanel() }),
    el("button", { class: "btn ghost", text: "🔍 询问", onclick: () => wikiQueryPanel() }),
    el("button", { class: "btn ghost", text: "🩺 健康", onclick: () => wikiLintPanel() }),
    el("button", { class: "btn ghost", text: "🔗 修复链接", onclick: () => wikiFixLinks() }),
    el("button", { class: "btn ghost", text: "⭳ 导出", onclick: () => wikiExport() }),
    el("button", { class: "btn ghost", text: _wikiMode === "graph" ? "▤ 列表" : "🕸 图视图",
      onclick: () => { _wikiMode = _wikiMode === "graph" ? "list" : "graph"; renderWikiView(); } }),
    el("button", { class: "btn ghost", text: "🧠 生成结构", onclick: () => wikiSchemaPanel() }),
  ]);
}

async function renderWikiList() {
  const d = await getJSON("/api/wiki").catch(() => ({ ok: false }));
  const wrap = el("div", {});
  if (!d || !d.ok) { wrap.appendChild(el("div", { class: "muted", text: "加载失败" })); return wrap; }
  const items = (d.items || []).filter((it) => {
    if (_wikiFilter.type && it.type !== _wikiFilter.type) return false;
    if (_wikiFilter.q) {
      const hay = (it.title + " " + (it.tags || []).join(" ") + " " + it.slug).toLowerCase();
      if (!hay.includes(_wikiFilter.q.toLowerCase())) return false;
    }
    return true;
  });
  if (!items.length) { wrap.appendChild(el("div", { class: "muted", text: "暂无条目，点「＋ 新建」或「📥 摄入」" })); return wrap; }
  const groups = {};
  for (const it of items) (groups[it.type] = groups[it.type] || []).push(it);
  for (const type of Object.keys(WIKI_TYPE_LABEL)) {
    const arr = groups[type]; if (!arr || !arr.length) continue;
    wrap.appendChild(el("div", { class: "wiki-group-title", text: WIKI_TYPE_LABEL[type] + ` (${arr.length})` }));
    const list = el("div", { class: "wiki-list" });
    for (const it of arr) {
      list.appendChild(el("div", { class: "wiki-card" }, [
        el("div", { class: "wiki-card-head" }, [
          el("span", { class: "wiki-type-badge t-" + it.type, text: WIKI_TYPE_LABEL[it.type] || it.type }),
          el("span", { class: "wiki-title", text: it.title }),
        ]),
        el("div", { class: "wiki-card-meta muted small", text:
          (it.tags || []).join(" · ") + (it.tags && it.tags.length ? "  ·  " : "") +
          "反链 " + it.backlinks + "  ·  " + (it.updated || "") }),
        el("div", { class: "wiki-actions" }, [
          el("button", { class: "btn ghost", text: "查看", onclick: () => wikiReader(it.slug) }),
          el("button", { class: "btn ghost", text: "改名", onclick: () => renameWikiPage(it.slug) }),
          el("button", { class: "btn ghost", text: "编辑", onclick: async () => {
            const rd = await getJSON("/api/wiki/" + encodeURIComponent(it.slug)).catch(() => null);
            if (!rd || !rd.ok) { toast("读取失败", "err"); return; }
            Panels.wikiModal("edit", rd);
          } }),
          el("button", { class: "btn ghost danger", text: "删除", onclick: async () => {
            if (!confirm("删除该页面？")) return;
            const r = await delJSON("/api/wiki/" + encodeURIComponent(it.slug)).catch(e => ({ ok: false, error: e.message }));
            if (r.ok) { toast("已删除", "ok"); renderWikiView(); } else toast("删除失败：" + (r.error || ""), "err");
          } }),
        ]),
      ]));
    }
    wrap.appendChild(list);
  }
  return wrap;
}

// 改名：调用后端已有的 link-safe 改名（rename_page 会级联更新全库 [[链接]] 并重置反链）
async function renameWikiPage(slug) {
  const nu = prompt("改名：输入新的页面标识（将自动更新所有指向它的链接）\n当前：" + slug, slug);
  if (nu == null) return;
  const newSlug = nu.trim().toLowerCase();
  if (!newSlug || newSlug === slug) return;
  const r = await postJSON("/api/wiki/rename", { old: slug, new: newSlug })
    .catch((e) => ({ ok: false, error: e.message }));
  if (r.ok) {
    const n = (r.updated || []).length;
    toast(n ? ("已改名，已同步更新 " + n + " 处链接") : "已改名", "ok");
    renderWikiView();
  } else {
    toast("改名失败：" + (r.error || ""), "err");
  }
}

async function renderWikiGraph() {
  const g = await getJSON("/api/wiki/graph").catch(() => ({ ok: false }));
  const wrap = el("div", {});
  if (!g || !g.ok) { wrap.appendChild(el("div", { class: "muted", text: "加载失败" })); return wrap; }
  const nodes = g.nodes || [], edges = g.edges || [];
  if (!nodes.length) { wrap.appendChild(el("div", { class: "muted", text: "暂无页面，无法绘制图" })); return wrap; }
  const W = 900, H = 560, cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 60;
  const pos = {};
  if (nodes.length <= 14) {
    nodes.forEach((n, i) => { const a = (i / nodes.length) * Math.PI * 2; pos[n.id] = [cx + R * Math.cos(a), cy + R * Math.sin(a)]; });
  } else {
    const cols = Math.ceil(Math.sqrt(nodes.length));
    nodes.forEach((n, i) => { pos[n.id] = [60 + (i % cols) * ((W - 120) / cols), 60 + Math.floor(i / cols) * 70]; });
  }
  const svg = [`<svg viewBox="0 0 ${W} ${H}" class="wiki-graph" xmlns="http://www.w3.org/2000/svg">`];
  for (const e of edges) {
    const a = pos[e.source], b = pos[e.target];
    if (!a || !b) continue;
    svg.push(`<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" class="wl-edge" />`);
  }
  for (const n of nodes) {
    const p = pos[n.id]; if (!p) continue;
    const col = { entity: "#e06c75", concept: "#61afef", comparison: "#e5c07b", query: "#98c379", summary: "#c678dd" }[n.type] || "#888";
    svg.push(`<g class="wl-node" data-slug="${n.id}" style="cursor:pointer">` +
      `<circle cx="${p[0]}" cy="${p[1]}" r="7" fill="${col}" />` +
      `<text x="${p[0] + 11}" y="${p[1] + 4}" class="wl-label">${n.title}</text></g>`);
  }
  svg.push("</svg>");
  const box = el("div", { class: "wiki-graph-box", html: svg.join("") });
  box.addEventListener("click", (ev) => {
    const g2 = ev.target.closest(".wl-node"); if (g2) wikiReader(g2.dataset.slug);
  });
  wrap.appendChild(box);
  wrap.appendChild(el("div", { class: "muted small", text: `${nodes.length} 页 · ${edges.length} 条互联链接 · 点击节点查看` }));
  return wrap;
}

// 把 [[slug|label]] 转为可点击链接（在已净化的安全 HTML 上做后处理）
function linkifyWikilinks(html) {
  return (html || "").replace(/\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]/g,
    (_, s) => { const slug = s.trim(); return `<a class="wl" data-slug="${slug}">${slug.split("/").pop()}</a>`; });
}

// 阅读器：渲染正文 + 入站/出站反链
async function wikiReader(slug) {
  const [pg, htm] = await Promise.all([
    getJSON("/api/wiki/" + encodeURIComponent(slug)).catch(() => null),
    getJSON("/api/wiki/" + encodeURIComponent(slug) + "/html").catch(() => null),
  ]);
  if (!pg || !pg.ok) { toast("读取失败", "err"); return; }
  const ov = el("div", { class: "ov" });
  const box = el("div", { class: "ov-box wiki-reader" });
  box.appendChild(el("div", { class: "section-title" }, [
    el("span", { class: "wiki-type-badge t-" + pg.type, text: WIKI_TYPE_LABEL[pg.type] || pg.type }),
    el("span", { text: pg.title }),
    el("button", { class: "btn ghost", text: "编辑", onclick: () => { ov.remove(); Panels.wikiModal("edit", pg); } }),
  ]));
  const meta = el("div", { class: "wiki-reader-meta muted small" });
  meta.textContent = "标签：" + ((pg.tags || []).join(", ") || "无") +
    "  ·  置信度：" + (pg.confidence || "—") + "  ·  更新：" + (pg.updated || "");
  box.appendChild(meta);
  const body = el("div", { class: "wiki-reader-body markdown-body",
    html: linkifyWikilinks((htm && htm.ok && htm.html) || "<p>（无正文）</p>") });
  body.addEventListener("click", (ev) => { const a = ev.target.closest(".wl"); if (a) wikiReader(a.dataset.slug); });
  box.appendChild(body);
  // 反链栏
  const bl = el("div", { class: "wiki-backlinks" });
  bl.appendChild(el("div", { class: "wiki-bl-title", text: "反向链接（" + (pg.inbound || []).length + "）" }));
  for (const s of pg.inbound || []) bl.appendChild(el("div", { class: "wiki-bl-item", text: s, onclick: () => wikiReader(s) }));
  if (!(pg.inbound || []).length) bl.appendChild(el("div", { class: "muted small", text: "（暂无页面链接到此）" }));
  box.appendChild(bl);
  ov.appendChild(box);
  ov.addEventListener("click", (e) => { if (e.target === ov) ov.remove(); });
  document.body.appendChild(ov);
}

// 摄入面板（P2）：添加源材料 + 触发编译
async function wikiExport() {
  try {
    const r = await getJSON("/api/wiki/export");
    if (!r.ok) { toast("导出失败：" + (r.error || ""), "err"); return; }
    const blob = new Blob([JSON.stringify({ pages: r.pages, raw: r.raw, schema: r.schema }, null, 2)],
      { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: "wiki-export-" + (r.exported_at || new Date().toISOString().slice(0, 10)) + ".json" });
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    toast("Wiki 已导出：" + (r.pages || []).length + " 页", "ok");
  } catch (e) { toast("导出失败：" + e.message, "err"); }
}

function wikiIngestPanel() {
  const ov = el("div", { class: "ov" });
  const box = el("div", { class: "ov-box wiki-panel" });
  box.appendChild(el("div", { class: "section-title", text: "📥 摄入源材料（Ingest）" }));
  box.appendChild(el("div", { class: "muted small", text: "粘贴文本或 URL → 保存为 raw/ →「全部编译」调用进程内 LLM 编译成互联知识页。需配置 API Key，是有成本的 LLM 往返。" }));
  const ta = el("textarea", { class: "editor", rows: 6, placeholder: "粘贴要摄入的资料文本…" });
  const url = el("input", { class: "form-input", placeholder: "或填入 URL（自动抓取）" });
  const nameI = el("input", { class: "form-input", placeholder: "源名称（可选）" });
  box.appendChild(el("div", { class: "field" }, [el("label", { text: "文本" }), ta]));
  box.appendChild(el("div", { class: "field" }, [el("label", { text: "URL" }), url]));
  box.appendChild(el("div", { class: "field" }, [el("label", { text: "名称" }), nameI]));
  const rawList = el("div", { class: "wiki-raw-list" });
  const status = el("div", { class: "muted small" });
  async function refreshRaw() {
    const r = await getJSON("/api/wiki/raw").catch(() => ({ ok: false }));
    rawList.innerHTML = "";
    for (const x of (r.ok && r.items) || []) {
      rawList.appendChild(el("div", { class: "wiki-raw-item" }, [
        el("span", { text: x.name }),
        el("span", { class: x.absorbed ? "tag ok" : "tag warn", text: x.absorbed ? "已吸收" : "未吸收" }),
        el("button", { class: "btn ghost danger", text: "删", onclick: async () => {
          if (!confirm("删除该源？")) return;
          const dr = await delJSON("/api/wiki/raw/" + encodeURIComponent(x.name)).catch(() => ({ ok: false }));
          if (dr.ok) refreshRaw();
        } }),
      ]));
    }
  }
  box.appendChild(el("div", { class: "actions-row" }, [
    el("button", { class: "btn primary", text: "添加源", onclick: async () => {
      const payload = { text: ta.value, url: url.value, name: nameI.value };
      if (!payload.text && !payload.url) { toast("请填写文本或 URL", "err"); return; }
      const r = await postJSON("/api/wiki/raw", payload).catch(e => ({ ok: false, error: e.message }));
      if (r.ok) { toast("已添加源", "ok"); ta.value = ""; url.value = ""; nameI.value = ""; refreshRaw(); }
      else toast("添加失败：" + (r.error || ""), "err");
    } }),
    el("button", { class: "btn primary", text: "全部编译", onclick: async () => {
      status.textContent = "编译中（可能耗时数十秒）…";
      const r = await postJSON("/api/wiki/ingest", {}).catch(e => ({ ok: false, error: e.message }));
      if (r.ok) { status.textContent = `完成：新建 ${r.created} · 更新 ${r.updated} · ${r.note || ""}`; toast("编译完成", "ok"); }
      else status.textContent = "失败：" + (r.error || ""), toast("编译失败", "err");
      refreshRaw();
    } }),
    el("button", { class: "btn ghost", text: "关闭", onclick: () => ov.remove() }),
  ]));
  box.appendChild(status);
  box.appendChild(el("div", { class: "wiki-bl-title", text: "已添加源" }));
  box.appendChild(rawList);
  ov.appendChild(box);
  ov.addEventListener("click", (e) => { if (e.target === ov) ov.remove(); });
  document.body.appendChild(ov);
  refreshRaw();
}

// 询问面板（P3）：索引导航 + LLM 综合 + cite
function wikiQueryPanel() {
  const ov = el("div", { class: "ov" });
  const box = el("div", { class: "ov-box wiki-panel" });
  box.appendChild(el("div", { class: "section-title", text: "🔍 询问 Wiki" }));
  box.appendChild(el("div", { class: "muted small", text: "基于 index.md 导航 + 相关页综合回答；答案中 [[slug]] 可点击跳转。需配置 API Key。" }));
  const q = el("input", { class: "form-input", placeholder: "例如：注意力机制与 Transformer 的关系？" });
  const ans = el("div", { class: "wiki-query-ans markdown-body" });
  const cited = el("div", { class: "wiki-query-cited" });
  box.appendChild(el("div", { class: "field" }, [el("label", { text: "问题" }), q]));
  box.appendChild(el("div", { class: "actions-row" }, [
    el("button", { class: "btn primary", text: "询问", onclick: async () => {
      if (!q.value.trim()) { toast("请输入问题", "err"); return; }
      ans.innerHTML = "<span class='muted'>思考中…</span>"; cited.innerHTML = "";
      const r = await postJSON("/api/wiki/query", { question: q.value }).catch(e => ({ ok: false, error: e.message }));
      if (!r.ok) { ans.innerHTML = ""; toast("查询失败：" + (r.error || ""), "err"); return; }
      ans.innerHTML = linkifyWikilinks(r.answer || "（无答案）");
      ans.addEventListener("click", (ev) => { const a = ev.target.closest(".wl"); if (a) wikiReader(a.dataset.slug); });
      cited.appendChild(el("div", { class: "wiki-bl-title", text: "引用页面" }));
      for (const s of r.cited || []) cited.appendChild(el("div", { class: "wiki-bl-item", text: s, onclick: () => wikiReader(s) }));
      if (!(r.cited || []).length) cited.appendChild(el("div", { class: "muted small", text: "（无显式引用）" }));
    } }),
    el("button", { class: "btn ghost", text: "关闭", onclick: () => ov.remove() }),
  ]));
  box.appendChild(ans);
  box.appendChild(cited);
  ov.appendChild(box);
  ov.addEventListener("click", (e) => { if (e.target === ov) ov.remove(); });
  document.body.appendChild(ov);
  q.focus();
}

// 健康面板（P4）：13 项 Lint
function wikiLintPanel() {
  const ov = el("div", { class: "ov" });
  const box = el("div", { class: "ov-box wiki-panel" });
  box.appendChild(el("div", { class: "section-title", text: "🩺 Wiki 健康（Lint）" }));
  const body = el("div", { class: "wiki-lint-body" });
  box.appendChild(body);
  ov.appendChild(box);
  ov.addEventListener("click", (e) => { if (e.target === ov) ov.remove(); });
  document.body.appendChild(ov);
  body.appendChild(el("div", { class: "muted", text: "检测中…" }));
  getJSON("/api/wiki/lint").then((r) => {
    body.innerHTML = "";
    if (!r || !r.ok) { body.appendChild(el("div", { class: "muted", text: "检测失败" })); return; }
    const c = r.counts || {};
    body.appendChild(el("div", { class: "wiki-lint-summary", text:
      `共 ${r.total_pages} 页 · 检查 ${r.checks} 项 · 错误 ${c.error || 0} · 警告 ${c.warn || 0} · 提示 ${c.info || 0}` }));
    const order = { error: 0, warn: 1, info: 2 };
    const items = (r.issues || []).slice().sort((a, b) => order[a.level] - order[b.level]);
    if (!items.length) body.appendChild(el("div", { class: "tag ok", text: "✓ 一切健康" }));
    for (const it of items) {
      body.appendChild(el("div", { class: "wiki-lint-item lv-" + it.level }, [
        el("span", { class: "wiki-lint-lv", text: it.level === "error" ? "错误" : it.level === "warn" ? "警告" : "提示" }),
        el("span", { text: it.msg }),
      ]));
    }
  }).catch(() => body.appendChild(el("div", { class: "muted", text: "检测失败" })));
}

// 结构生成面板（G5）：输入领域 → 让模型生成 SCHEMA.md 骨架
function wikiSchemaPanel() {
  const ov = el("div", { class: "ov" });
  const box = el("div", { class: "ov-box wiki-panel" });
  box.appendChild(el("div", { class: "section-title", text: "🧠 生成知识库结构（SCHEMA）" }));
  box.appendChild(el("div", { class: "muted small", text: "为指定领域生成 SCHEMA.md：定义核心概念类型、写作约定与必填 frontmatter。需配置 API Key。" }));
  const dom = el("input", { class: "form-input", placeholder: "领域，例如：机器学习 / 公司制度（可留空=通用）" });
  const out = el("div", { class: "wiki-schema-out" });
  box.appendChild(el("div", { class: "field" }, [el("label", { text: "领域" }), dom]));
  box.appendChild(el("div", { class: "actions-row" }, [
    el("button", { class: "btn primary", text: "生成", onclick: async () => {
      out.innerHTML = "<span class='muted'>生成中…</span>";
      const r = await postJSON("/api/wiki/schema", { domain: dom.value.trim() }).catch(e => ({ ok: false, error: e.message }));
      if (!r || !r.ok) { out.innerHTML = ""; toast("生成失败：" + ((r && r.error) || ""), "err"); return; }
      out.textContent = r.schema || "（无输出）";
      toast("已生成 SCHEMA.md", "ok");
    } }),
    el("button", { class: "btn ghost", text: "关闭", onclick: () => ov.remove() }),
  ]));
  box.appendChild(out);
  ov.appendChild(box);
  ov.addEventListener("click", (e) => { if (e.target === ov) ov.remove(); });
  document.body.appendChild(ov);
  dom.focus();
}

async function wikiFixLinks() {
  const ov = el("div", { class: "ov" });
  const box = el("div", { class: "ov-box wiki-panel" });
  box.appendChild(el("div", { class: "section-title", text: "🔗 修复破损链接" }));
  const body = el("div", { class: "wiki-lint-body" });
  box.appendChild(body);
  ov.appendChild(box);
  ov.addEventListener("click", (e) => { if (e.target === ov) ov.remove(); });
  document.body.appendChild(ov);
  body.appendChild(el("div", { class: "muted", text: "扫描中\u2026" }));
  try {
    const r = await postJSON("/api/wiki/fix-links");
    body.innerHTML = "";
    if (!r || !r.ok) { body.appendChild(el("div", { class: "muted", text: "修复失败" })); return; }
    const created = r.created || [];
    body.appendChild(el("div", { class: "wiki-lint-summary", text: `共生成 ${created.length} 个占位页` }));
    if (created.length) {
      for (const slug of created) {
        body.appendChild(el("div", { class: "wiki-lint-item lv-info" }, [el("span", { text: slug })]));
      }
    } else {
      body.appendChild(el("div", { class: "tag ok", text: "\u2713 无需修复" }));
    }
  } catch (e) {
    body.innerHTML = "";
    body.appendChild(el("div", { class: "muted", text: `修复失败: ${e.message}` }));
  }
}

async function renderKanbanView() {
  const v = $("#view-kanban"); if (!v) return;
  v.innerHTML = "";
  const sp = el("div", { class: "app-view-body" });
  v.appendChild(sp);
  const d = await getJSON("/api/kanban").catch(() => ({ ok: false }));
  if (!d || !d.ok) { sp.appendChild(el("div", { class: "muted", text: "加载失败" })); return; }
  sp.appendChild(el("div", { class: "section-title", text: "Kanban 看板" }));
  if (!d.exists) sp.appendChild(el("div", { class: "muted", text: "看板数据库尚未初始化：先在对话中使用看板工具创建任务，或在此新增第一条任务。" }));
  const nt = el("input", { class: "form-input", placeholder: "新任务标题" });
  sp.appendChild(el("div", { class: "field" }, [
    el("label", { text: "新增任务" }), nt,
    el("button", { class: "btn primary", text: "添加", onclick: async () => {
      if (!nt.value.trim()) { toast("请输入任务标题", "err"); return; }
      const r = await postJSON("/api/kanban", { title: nt.value.trim() }).catch(e => ({ ok: false, error: e.message }));
      if (r.ok) { toast("已添加", "ok"); renderKanbanView(); } else toast(r.error || "添加失败", "err");
    } }),
  ]));
  // 搜索框
  let _kanbanFilter = "";
  const searchInput = el("input", { class: "form-input", style: "margin-bottom:10px;", placeholder: "搜索任务标题…",
    oninput: () => { _kanbanFilter = searchInput.value.trim().toLowerCase(); applyKanbanFilter(); } });
  sp.appendChild(searchInput);
  const board = el("div", { class: "kanban-board" });
  sp.appendChild(board);
  // 真实 Hermes 看板状态多于 UI 的三列（todo/ready/running/blocked/scheduled/
  // triage/done）。用映射把全部状态归到三列，避免任务因状态不匹配而静默消失；
  // 卡片另显示真实状态徽标，用户仍能看到内核里的真实状态。
  const COLS = ["todo", "in_progress", "done"];
  const COL_LABEL = { todo: "待办", in_progress: "进行中", done: "已完成" };
  const STATUS_BUCKET = {
    todo: "todo", ready: "todo", scheduled: "todo", triage: "todo",
    running: "in_progress", blocked: "in_progress", review: "in_progress",
    done: "done", archived: "done",
  };
  const STATUS_LABEL = {
    todo: "待办", ready: "就绪", scheduled: "已排期", triage: "待分诊",
    running: "进行中", blocked: "阻塞", review: "待审核", archived: "已归档", done: "已完成",
  };
  function bucketOf(s) { return STATUS_BUCKET[s] || "todo"; }
  function applyKanbanFilter() {
    board.innerHTML = "";
    const cols = (d.columns && d.columns.length) ? d.columns : COLS;
    for (const col of cols) {
      const items = (d.items || []).filter(i => bucketOf(i.status) === col);
      const filtered = _kanbanFilter ? items.filter(i => (i.title || "").toLowerCase().includes(_kanbanFilter)) : items;
      const colEl = el("div", { class: "kanban-col" });
      colEl.appendChild(el("div", { class: "kanban-col-head", text: (COL_LABEL[col] || col) + " (" + filtered.length + "/" + items.length + ")" }));
      const body = el("div", { class: "kanban-col-body" });
      for (const it of filtered) {
        const realStatus = it.status || "todo";
        const prio = (typeof it.priority === "number") ? it.priority
          : (parseInt(it.priority, 10) || 0);
        body.appendChild(el("div", { class: "kanban-card" }, [
          el("div", { class: "kanban-card-title", text: it.title }),
          el("div", { class: "muted small", text: it.description || "" }),
          el("span", { class: "kanban-card-status", text: (STATUS_LABEL[realStatus] || realStatus) }),
          el("span", { class: "kanban-card-status", text: "优先级 " + prio }),
        ]));
      }
      colEl.appendChild(body);
      board.appendChild(colEl);
    }
  }
  applyKanbanFilter();
  // 导出按钮
  sp.appendChild(el("div", { class: "export-actions-row" }, [
    el("button", { class: "btn primary", text: "⭳ 导出看板 (JSON)", onclick: async () => {
      try {
        const r = await getJSON("/api/kanban/export?fmt=json");
        if (!r.ok) { toast("导出失败：" + (r.error || ""), "err"); return; }
        const blob = new Blob([JSON.stringify(r, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = el("a", { href: url, download: "kanban-export-" + new Date().toISOString().slice(0, 10) + ".json" });
        document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
        toast("看板已导出", "ok");
      } catch (e) { toast("导出失败：" + e.message, "err"); }
    } }),
    el("button", { class: "btn btn-outline", text: "⭳ 导出看板 (CSV)", onclick: async () => {
      try {
        const r = await getJSON("/api/kanban/export?fmt=csv");
        if (!r.ok) { toast("导出失败：" + (r.error || ""), "err"); return; }
        const blob = new Blob([r], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = el("a", { href: url, download: "kanban-export-" + new Date().toISOString().slice(0, 10) + ".csv" });
        document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
        toast("看板已导出", "ok");
      } catch (e) { toast("导出失败：" + e.message, "err"); }
    } }),
  ]));
}

// 统一刷新当前视图
function refreshPanels() { renderCurrentView(); }


// ------------------------------------------------------------------ 新功能视图（hermes_features 13 模块）
async function renderGoalsView() {
  const v = $('#view-goals'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderGoalsPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderCheckpointsView() {
  const v = $('#view-checkpoints'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderCheckpointsPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderMoaView() {
  const v = $('#view-moa'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderMoaPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderProjectsView() {
  const v = $('#view-projects'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderProjectsPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderBundlesView() {
  const v = $('#view-bundles'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderBundlesPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderSecurityView() {
  const v = $('#view-security'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderSecurityPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderBlueprintsView() {
  const v = $('#view-blueprints'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderBlueprintsPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderBatchView() {
  const v = $('#view-batch'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderBatchPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderJourneyView() {
  const v = $('#view-journey'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderJourneyPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderBackupView() {
  const v = $('#view-backup'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderBackupPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderProfilesView() {
  const v = $('#view-profiles'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderProfilesPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderSnapshotsView() {
  const v = $('#view-snapshots'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderSnapshotsPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderCuratorView() {
  const v = $('#view-curator'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderCuratorPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderRoutingView() {
  const v = $('#view-routing'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderRoutingPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}
async function renderWorkspaceView() {
  const v = $('#view-workspace'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderWorkspacePanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}

// 日志视图（只读查看 Hermes 日志，对齐 `hermes logs`）
async function renderLogsView() {
  const v = $('#view-logs'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderLogsPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}

// 结构化输出视图（触发 host-owned 结构化补全 + 离线 JSON Schema 校验，对齐 Hermes Library）
async function renderStructuredView() {
  const v = $('#view-structured'); if (!v) return;
  v.innerHTML = ''; const sp = el('div', { class: 'app-view-body' }); v.appendChild(sp);
  try { await Panels.renderStructuredPanel(sp); } catch (e) { sp.appendChild(el('div', { class: 'muted', text: '加载失败：' + e.message })); }
}

// 工具清单视图已在统一「工具」面板内作为「工具清单」子面板承载（renderToolsCatalogPanel），此处不再单独保留视图


export {
  showView, VIEW_RENDERERS, renderCurrentView, refreshPanels,
  renderSkillsView, renderModelsView, renderPluginsView, renderCronView, renderToolsView,
  renderMcpView, renderLoopsView, renderDelegationView, renderSoulView, renderMemoryView, renderContextView,
  renderSyspromptView, renderWikiView, renderKanbanView, wikiReader,
  renderGoalsView, renderCheckpointsView, renderMoaView, renderProjectsView,
  renderBundlesView, renderSecurityView, renderBlueprintsView, renderBatchView,
  renderJourneyView, renderBackupView, renderProfilesView, renderCuratorView,
  renderRoutingView, renderWorkspaceView, renderLogsView, renderStructuredView,
};

// 暴露给 panels.js 的 wikiReader（反链点击跳转）
window.__wikiReader = wikiReader;
