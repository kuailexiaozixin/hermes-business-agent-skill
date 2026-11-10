/* skillstore.js — 技能商店前端（SkillHub 接入）
 * 自包含 vanilla JS，无 CDN 依赖。支持多实例：window.initSkillStore(rootId)
 * 在 /skills 页面自动挂载 #skillStoreRoot；设置中心可挂载 #skillStoreRootSettings。
 * 接入后端：/api/skill-store/sources | /skills | /categories | /installed(+enable/detail/save) | install(POST) | installed/{id}(DELETE)
 */
(function () {
  "use strict";

  var CSS = [
    // 对标 业务示例 设置界面视觉：主色蓝 #2563eb
    ".skill-store{--primary:#2563eb;--primary-hover:#1d4ed8;--primary-soft:rgba(37,99,235,.12);}",
    ".skill-store .ss-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:18px;}",
    ".skill-store .ss-tabs{display:inline-flex;gap:6px;background:var(--bg-muted,#f1f5f9);padding:4px;border-radius:10px;}",
    ".skill-store .ss-tab{border:none;background:transparent;padding:7px 16px;border-radius:8px;font-size:13px;font-weight:600;color:var(--text-muted);cursor:pointer;transition:color .15s;}",
    ".skill-store .ss-tab.active{background:var(--surface);color:var(--primary);box-shadow:0 1px 3px rgba(0,0,0,.08);}",
    ".skill-store .ss-search{display:flex;gap:8px;align-items:center;flex:1;min-width:240px;justify-content:flex-end;}",
    ".skill-store .ss-search input{max-width:280px;}",
    ".skill-store .ss-chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px;}",
    ".skill-store .ss-chip{white-space:nowrap;border:1px solid var(--border);background:var(--surface);color:var(--text-muted);padding:6px 15px;border-radius:999px;font-size:12.5px;cursor:pointer;transition:all .15s;}",
    ".skill-store .ss-chip:hover{border-color:var(--primary);color:var(--primary);}",
    ".skill-store .ss-chip.active{background:var(--primary);border-color:var(--primary);color:#fff;box-shadow:0 2px 6px rgba(37,99,235,.28);}",
    ".skill-store .ss-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:20px;}",
    ".skill-store .ss-card{background:var(--bg-card,#fff);border:1px solid var(--border-strong,#cbd5e1);border-radius:14px;padding:18px;display:flex;flex-direction:column;gap:12px;box-shadow:0 1px 3px rgba(15,23,42,.07);transition:box-shadow .18s,transform .18s;cursor:pointer;}",
    ".skill-store .ss-detail-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:12px;}",
    ".skill-store .ss-detail-name{font-size:17px;font-weight:700;color:var(--text);display:flex;align-items:center;flex-wrap:wrap;gap:8px;}",
    ".skill-store .ss-detail-row{display:flex;gap:12px;align-items:baseline;padding:7px 0;border-bottom:1px dashed var(--border,#e2e8f0);font-size:13px;}",
    ".skill-store .ss-detail-label{flex:0 0 84px;color:var(--text-muted);font-size:12px;}",
    ".skill-store .ss-detail-val{color:var(--text);word-break:break-all;}",
    ".skill-store .ss-detail-val a{color:var(--primary);text-decoration:none;}",
    ".skill-store .ss-detail-val a:hover{text-decoration:underline;}",
    ".skill-store .ss-detail-desc{margin-top:12px;font-size:13px;line-height:1.7;color:var(--text);white-space:pre-wrap;word-break:break-word;}",
    ".skill-store .ss-detail-body{margin-top:12px;border-top:1px solid var(--border,#e2e8f0);padding-top:10px;}",
    ".skill-store .ss-detail-loading{font-size:12.5px;color:var(--text-muted);}",
    ".skill-store .ss-detail-fname{font-size:13px;font-weight:600;color:var(--text);margin-bottom:8px;}",
    ".skill-store .ss-detail-pre{margin:0;background:var(--bg-muted,#f1f5f9);border:1px solid var(--border,#e2e8f0);border-radius:8px;padding:12px;max-height:46vh;overflow:auto;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word;color:var(--text);}",
    ".skill-store .ss-card:hover{box-shadow:0 8px 24px rgba(15,23,42,.10);transform:translateY(-2px);}",
    ".skill-store .ss-card-head{display:flex;gap:12px;align-items:flex-start;}",
    ".skill-store .ss-icon{width:46px;height:46px;border-radius:12px;flex-shrink:0;object-fit:contain;background:var(--bg-muted,#f1f5f9);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;color:var(--primary);padding:6px;}",
    ".skill-store .ss-name{font-size:15px;font-weight:700;color:var(--text);line-height:1.35;word-break:break-word;}",
    ".skill-store .ss-owner{font-size:11px;margin-top:2px;color:var(--text-muted);}",
    ".skill-store .ss-desc{font-size:12.5px;line-height:1.65;color:var(--text-muted);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;min-height:56px;}",
    ".skill-store .ss-foot{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:auto;padding-top:12px;border-top:1px solid var(--border);}",
    ".skill-store .ss-meta{font-size:11px;color:var(--text-muted);}",
    ".skill-store .ss-status{text-align:center;color:var(--text-muted);padding:24px;font-size:13px;}",
    ".skill-store .ss-badge{font-size:10.5px;padding:2px 9px;border-radius:999px;background:var(--primary-soft);color:var(--primary);font-weight:600;}",
    ".skill-store .ss-installed{font-size:12px;color:#15803d;font-weight:600;display:inline-flex;align-items:center;gap:4px;}",
    ".skill-store .ss-empty{text-align:center;padding:60px 20px;color:var(--text-muted);}",
    ".skill-store .ss-loadmore-wrap{text-align:center;margin:18px 0 8px;}",
    ".skill-store .ss-market-switch{display:flex;gap:8px;align-items:center;margin-bottom:14px;padding:0 2px;}",
    ".skill-store .ss-market-switch.hidden{display:none;}",
    ".skill-store .ss-market-btn{border:1px solid var(--border);background:var(--surface);color:var(--text-muted);padding:5px 14px;border-radius:999px;font-size:12px;cursor:pointer;transition:all .15s;}",
    ".skill-store .ss-market-btn:hover{border-color:var(--primary);color:var(--primary);}",
    ".skill-store .ss-market-btn.active{background:var(--primary);border-color:var(--primary);color:#fff;}",
    ".skill-store .ss-hermes-filter{display:flex;gap:8px;align-items:center;margin-bottom:14px;padding:0 2px;}",
    ".skill-store .ss-hermes-filter.hidden{display:none;}",
    ".skill-store .ss-hermes-filter .ss-hf-label{font-size:12px;color:var(--text-muted);margin-right:2px;}",
    ".skill-store .ss-type{font-size:10.5px;padding:2px 8px;border-radius:999px;font-weight:600;margin-left:6px;vertical-align:middle;}",
    ".skill-store .ss-type-official{background:rgba(21,128,61,.12);color:#15803d;}",
    ".skill-store .ss-type-trusted{background:rgba(37,99,235,.12);color:#2563eb;}",
    ".skill-store .ss-type-github{background:rgba(30,41,59,.10);color:#334155;}",
    ".skill-store .ss-type-community{background:rgba(100,116,139,.14);color:#475569;}",
    ".skill-store .ss-loadmore{display:inline-block;padding:7px 22px;border-radius:999px;}",
    ".skill-store .ss-market-wrap{position:relative;display:inline-block;}",
    ".skill-store .ss-market-panel{position:absolute;top:calc(100% + 6px);right:0;background:var(--surface,#fff);border:1px solid var(--border,#cbd5e1);border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.14);padding:10px;min-width:220px;z-index:300;display:none;}",
    ".skill-store .ss-market-panel.open{display:block;}",
    ".skill-store .ss-market-opt{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:8px;cursor:pointer;font-size:13px;}",
    ".skill-store .ss-market-opt:hover{background:var(--bg-muted,#f1f5f9);}",
    ".skill-store .ss-market-opt input{margin:0;}",
    ".skill-store .ss-market-foot{display:flex;gap:8px;justify-content:flex-end;margin-top:8px;padding-top:8px;border-top:1px solid var(--border,#e2e8f0);}",
    ".skill-store .ss-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:auto;padding-top:12px;border-top:1px solid var(--border);}",
    ".skill-store .ss-card .btn-danger{background:#dc2626;border-color:#dc2626;}",
    ".skill-store .ss-switch{position:relative;display:inline-block;width:38px;height:20px;}",
    ".skill-store .ss-switch input{opacity:0;width:0;height:0;}",
    ".skill-store .ss-switch .slider{position:absolute;cursor:pointer;inset:0;background:#cbd5e1;border-radius:999px;transition:.2s;}",
    ".skill-store .ss-switch input:checked + .slider{background:var(--primary);}",
    ".skill-store .ss-switch .slider:before{content:'';position:absolute;height:14px;width:14px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.2s;}",
    ".skill-store .ss-switch input:checked + .slider:before{transform:translateX(18px);}",
    ".skill-store .ss-toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1e293b;color:#fff;padding:10px 18px;border-radius:10px;font-size:13px;z-index:4000;opacity:0;transition:opacity .25s;pointer-events:none;}",
    ".skill-store .ss-toast.show{opacity:1;}",
    ".ss-edit-overlay{position:fixed;inset:0;background:rgba(15,23,42,.55);display:flex;align-items:center;justify-content:center;z-index:5000;}",
    ".ss-edit-modal{background:var(--surface);color:var(--text);width:min(680px,92vw);max-height:90vh;overflow:auto;padding:22px;border-radius:14px;box-shadow:0 20px 60px rgba(0,0,0,.35);}",
    ".ss-edit-modal h3{margin:0 0 14px;font-size:15px;}",
    ".ss-edit-field{display:flex;flex-direction:column;gap:4px;margin-bottom:12px;font-size:13px;color:var(--text-muted);}",
    ".ss-edit-body{width:100%;min-height:220px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;line-height:1.5;}",
    ".ss-edit-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:6px;}",
    "@media (max-width:768px){.skill-store .ss-search{justify-content:flex-start;}.skill-store .ss-grid{grid-template-columns:1fr;}}"
  ].join("\n");

  function fmtNum(n) {
    n = Number(n) || 0;
    if (n >= 100000000) return (n / 100000000).toFixed(1).replace(/\.0$/, "") + "亿";
    if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, "") + "万";
    return String(n);
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function ensureStyle() {
    if (document.getElementById("ssStyle")) return;
    var st = document.createElement("style");
    st.id = "ssStyle";
    st.textContent = CSS;
    document.head.appendChild(st);
  }

  function createStore(rootId) {
    var root = document.getElementById(rootId);
    if (!root) return null;

    // 市场下拉选项（id = 后端市场标识 / 卡片 source 字段）
    var MARKETS = [
      { id: "community", label: "SkillHub" },
      { id: "skills.sh", label: "skills.sh" },
      { id: "clawhub", label: "clawhub" },
      { id: "lobehub", label: "lobehub" },
      { id: "browse-sh", label: "browse.sh" },
      { id: "skillsmp", label: "skillsmp" },
      { id: "trusttools", label: "TrustTools" },
    ];

    function marketBtnLabel() {
      if (!state.markets.length) return "市场：全部";
      var names = MARKETS.filter(function (m) { return state.markets.indexOf(m.id) >= 0; })
        .map(function (m) { return m.label; });
      return "市场：" + names.join("/");
    }

    function marketPanelHtml() {
      var html = '<div class="ss-market-panel" id="ssMarketPanel">';
      MARKETS.forEach(function (m) {
        var checked = state.markets.indexOf(m.id) >= 0 ? " checked" : "";
        html += '<label class="ss-market-opt"><input type="checkbox" value="' + m.id + '"' + checked + '> ' +
          escapeHtml(m.label) + '</label>';
      });
      html += '<div class="ss-market-foot">' +
        '<button class="btn btn-outline btn-sm" id="ssMktClear">全部</button>' +
        '<button class="btn btn-primary btn-sm" id="ssMktOk">确定</button>' +
        '</div></div>';
      return html;
    }

    function toggleMarketPanel() {
      var btn = document.getElementById("ssMarketBtn");
      var existing = document.getElementById("ssMarketPanel");
      if (existing && existing.classList.contains("open")) { closeMarketPanel(); return; }
      closeMarketPanel();
      if (!btn) return;
      var holder = document.createElement("div");
      holder.innerHTML = marketPanelHtml();
      var panel = holder.firstChild;
      btn.parentNode.appendChild(panel);
      panel.classList.add("open");
    }

    function closeMarketPanel() {
      var p = document.getElementById("ssMarketPanel");
      if (p && p.parentNode) p.parentNode.removeChild(p);
    }

    function applyMarketPanel() {
      var panel = document.getElementById("ssMarketPanel");
      if (!panel) return;
      var sel = [];
      panel.querySelectorAll('input[type="checkbox"]:checked').forEach(function (c) { sel.push(c.value); });
      state.markets = sel;
      var btn = document.getElementById("ssMarketBtn");
      if (btn) btn.textContent = marketBtnLabel();
      closeMarketPanel();
      renderMarket(true);
    }

    var state = {
      tab: "market",
      q: "",
      category: "",
      markets: [], // 选中的市场标识（空 = 全部）
      sort: "heat",
      // 排序方式：heat(热度值=下载量/安装量/收藏量/星数，默认) / name(名称)
      sortModes: [
        ["heat", "热度值（默认）"],
        ["name", "排序：名称"],
      ],
      page: 1,
      pageSize: 24,
      loading: false,
      installedIds: {},
      hasMore: false,
    };

    function toast(msg, ok) {
      var t = document.getElementById("ssToast");
      if (!t) {
        t = document.createElement("div");
        t.id = "ssToast";
        t.className = "ss-toast";
        document.body.appendChild(t);
      }
      t.textContent = msg;
      t.style.background = ok === false ? "#b91c1c" : "#1e293b";
      t.classList.add("show");
      setTimeout(function () { t.classList.remove("show"); }, 2600);
    }

    function iconHtml(item) {
      var letter = (item.name || "?").trim().charAt(0).toUpperCase();
      var url = item.iconUrl || "";
      // iconUrl 可能是 http(s) 图片链接，也可能是 emoji 字符（上游技能源直接把 emoji 当图标）。
      // 只有合法 http(s) 链接才用 <img>；emoji / 空 / 相对路径 一律按文本或字母展示，
      // 避免把 emoji 当成 URL 请求导致 404（如 http://host/🐍）。
      if (/^https?:\/\//i.test(url)) {
        return '<img class="ss-icon" src="' + escapeHtml(url) + '" alt="" onerror="this.style.display=\'none\'">';
      }
      if (/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2190}-\u{21FF}\u{2B00}-\u{2BFF}\u{2300}-\u{23FF}\u{FE0F}\u{20E3}\u{2139}\u{2122}\u{00A9}\u{00AE}]/u.test(url)) {
        return '<span class="ss-icon">' + escapeHtml(url) + '</span>';
      }
      return '<span class="ss-icon">' + escapeHtml(letter) + "</span>";
    }

    function typeInfo(item) {
      // 仅 Hermes 条目带 item.type（official/trusted/github/community）；SkillHub 条目无此字段。
      var t = item.type || "community";
      if (t === "official") return { text: "官方", cls: "ss-type-official" };
      if (t === "trusted") return { text: "受信任", cls: "ss-type-trusted" };
      if (t === "github") return { text: "GitHub", cls: "ss-type-github" };
      return { text: "社区", cls: "ss-type-community" };
    }

    function cardHtml(item) {
      // 官方技能落盘后 id=name（扁平），而卡片 slug=identifier；重载后 installedIds 以 name 为键，
      // 故官方条目额外按 name 命中，保证「已安装」徽标在刷新后仍正确。
      var isInstalled = !!state.installedIds[item.slug] ||
        (item.source === "official" && !!state.installedIds[item.name]);
      // 统一市场显示来源徽标（官方/skills.sh/clawhub/.../社区）
      var typeBadge = "";
      if (item.source_label || item.type) {
        var ti = typeInfo(item);
        typeBadge = '<span class="ss-type ' + ti.cls + '">' + (item.source_label || ti.text) + "</span>";
      }
      var action;
      if (isInstalled) {
        action = '<span class="ss-installed">✓ 已安装</span>';
      } else {
        action = '<button class="btn btn-primary btn-sm" data-install="' + escapeHtml(item.slug) +
          '" data-upstream="' + escapeHtml(item.upstream_url || "") +
          '" data-type="' + escapeHtml(item.type || "") +
          '" data-source="' + escapeHtml(item.source || "") + '">安装</button>';
      }
      var meta = [];
      if (item.stars) meta.push("★ " + fmtNum(item.stars));
      if (item.downloads) meta.push("⬇ " + fmtNum(item.downloads));
      if (item.verified) meta.push("✓ 已验");
      var _dd = {
        name: item.name, type: (item.source_label || typeInfo(item).text),
        typeCls: typeInfo(item).cls, owner: item.owner || "",
        description: item.description || "", category: item.category || "",
        downloads: item.downloads || 0, stars: item.stars || 0, likes: item.likes || 0,
        source: item.source || "",
        upstream_url: item.upstream_url || "",
        homepage: item.homepage || item.upstream_url || ""
      };
      return '' +
        '<div class="ss-card" data-slug="' + escapeHtml(item.slug) +
        '" data-detail="' + escapeHtml(JSON.stringify(_dd)) + '">' +
          '<div class="ss-card-head">' +
            iconHtml(item) +
            '<div style="min-width:0;">' +
              '<div class="ss-name">' + escapeHtml(item.name) + typeBadge + '</div>' +
              (item.owner ? '<div class="ss-owner">@' + escapeHtml(item.owner) + '</div>' : '') +
            '</div>' +
          '</div>' +
          '<div class="ss-desc">' + escapeHtml(item.description) + '</div>' +
          '<div class="ss-foot">' +
            (item.category ? '<span class="ss-badge">' + escapeHtml(item.category) + '</span>' : '<span></span>') +
            action +
          '</div>' +
          (meta.length ? '<div class="ss-meta">' + escapeHtml(meta.join(" · ")) + '</div>' : '') +
        '</div>';
    }

    function mineCardHtml(s) {
      var dir = s.dir || "";
      var on = s.enabled !== false;
      var _md = { name: s.name || "", category: s.category || "",
        description: s.description || "", dir: dir, source: "本机已安装" };
      return '' +
        '<div class="ss-card" data-id="' + escapeHtml(s.id) + '" data-dir="' + escapeHtml(dir) +
        '" data-detail="' + escapeHtml(JSON.stringify(_md)) + '">' +
          '<div class="ss-card-head">' +
            '<span class="ss-icon">' + escapeHtml((s.name || "?").charAt(0).toUpperCase()) + '</span>' +
            '<div style="min-width:0;">' +
              '<div class="ss-name">' + escapeHtml(s.name) + '</div>' +
              (s.category ? '<div class="ss-owner">' + escapeHtml(s.category) + '</div>' : '') +
            '</div>' +
          '</div>' +
          '<div class="ss-desc">' + escapeHtml(s.description) + '</div>' +
          '<div class="ss-foot">' +
            '<span class="ss-installed">✓ 本机</span>' +
            '<button class="btn btn-danger btn-sm" data-uninstall="' + escapeHtml(s.id) + '">卸载</button>' +
          '</div>' +
          '<div class="ss-actions">' +
            '<label class="ss-switch" title="启用/关闭"><input type="checkbox" ' + (on ? "checked" : "") +
              ' data-enable="' + escapeHtml(s.id) + '"><span class="slider"></span></label>' +
            '<button class="btn btn-outline btn-sm" data-folder="' + escapeHtml(dir) + '">打开文件夹</button>' +
            '<button class="btn btn-outline btn-sm" data-edit="' + escapeHtml(s.id) + '">修改</button>' +
          '</div>' +
        '</div>';
    }

    function getInstalledIds(cb) {
      fetch("/api/skill-store/installed").then(function (r) { return r.json(); }).then(function (d) {
        var m = {};
        (d.items || []).forEach(function (s) { m[s.id] = true; });
        state.installedIds = m;
        cb && cb();
      }).catch(function () { cb && cb(); });
    }

    function renderMarket(reset) {
      var grid = root.querySelector("#ssGrid");
      var status = root.querySelector("#ssStatus");
      var loadMore = root.querySelector("#ssLoadMore");
      if (state.loading) return;
      state.loading = true;
      if (reset) { state.page = 1; grid.innerHTML = ""; }
      if (loadMore) loadMore.innerHTML = "";
      status.textContent = "加载中…";
      var params = "q=" + encodeURIComponent(state.q) +
        "&category=" + encodeURIComponent(state.category) +
        "&page=" + state.page + "&pageSize=" + state.pageSize +
        "&sort=" + encodeURIComponent(state.sort) +
        (state.markets.length ? "&sources=" + encodeURIComponent(state.markets.join(",")) : "");
      var url = "/api/skill-store/skills?" + params;
      fetch(url).then(function (r) { return r.json(); }).then(function (d) {
        state.loading = false;
        if (!d.ok) { status.textContent = "加载失败：" + (d.error || "未知错误"); return; }
        var items = d.items || [];
        state.hasMore = (items.length > 0) && ((state.page * state.pageSize) < (d.total || 0));
        if (reset && !items.length) {
          var srcErrs = d.source_errors || [];
          status.textContent = srcErrs.length
            ? srcErrs.join("；")
            : "没有找到匹配的技能。";
          grid.innerHTML = "";
          return;
        }
        grid.insertAdjacentHTML("beforeend", items.map(cardHtml).join(""));
        if (state.hasMore && loadMore) {
          loadMore.innerHTML = '<button class="btn btn-outline ss-loadmore">加载更多…</button>';
        }
        status.textContent = "";
      }).catch(function (e) {
        state.loading = false;
        status.textContent = "网络错误：" + e;
      });
    }

    function renderMine() {
      var grid = root.querySelector("#ssGrid");
      var status = root.querySelector("#ssStatus");
      grid.innerHTML = "";
      status.textContent = "加载中…";
      fetch("/api/skill-store/installed").then(function (r) { return r.json(); }).then(function (d) {
        var items = d.items || [];
        state.installedIds = {};
        items.forEach(function (s) { state.installedIds[s.id] = true; });
        if (!items.length) {
          status.textContent = "";
          grid.innerHTML = '<div class="ss-empty">本机还没有安装技能。<br>去「技能市场」挑一个安装，或点右上角「上传本地技能」。</div>';
          return;
        }
        status.textContent = "";
        grid.innerHTML = items.map(mineCardHtml).join("");
      }).catch(function (e) { status.textContent = "加载失败：" + e; });
    }

    function renderChips(categories) {
      var box = root.querySelector("#ssChips");
      if (!box) return;
      // 如果未传入分类列表且 DOM 里已有 chips，仅刷新 active 状态，避免清空
      if (!categories || !categories.length) {
        var existing = box.querySelectorAll(".ss-chip[data-cat]");
        if (existing.length) {
          box.querySelectorAll(".ss-chip").forEach(function (btn) {
            btn.classList.toggle("active", btn.getAttribute("data-cat") === state.category);
          });
          return;
        }
      }
      var cats = categories || [];
      var html = '<button class="ss-chip' + (state.category === "" ? " active" : "") + '" data-cat="">全部</button>';
      cats.forEach(function (c) {
        html += '<button class="ss-chip' + (state.category === c ? " active" : "") + '" data-cat="' +
          escapeHtml(c) + '">' + escapeHtml(c) + "</button>";
      });
      box.innerHTML = html;
    }

    function switchTab(tab) {
      state.tab = tab;
      root.querySelectorAll(".ss-tab").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-tab") === tab);
      });
      root.querySelector("#ssChips").style.display = tab === "market" ? "flex" : "none";
      root.querySelector("#ssSearch").style.visibility = tab === "market" ? "visible" : "hidden";
      if (tab === "market") {
        // 首次渲染市场时拉一次全部分类
        getInstalledIds(function () { renderMarket(true); });
        loadMarketCategories();
      } else {
        renderMine();
      }
    }

    function loadMarketCategories() {
      var url = "/api/skill-store/categories";
      fetch(url).then(function (r) { return r.json(); }).then(function (d) {
        if (d.ok) renderChips(d.categories);
      }).catch(function () {});
    }


    function doInstall(slug, btn) {
      var card = btn.closest(".ss-card");
      var name = card ? card.querySelector(".ss-name").textContent : slug;
      var upstream = btn.getAttribute("data-upstream") || (card && card.getAttribute("data-upstream")) || "";
      var itype = btn.getAttribute("data-type") || "";
      var sourceHint = itype === "official"
        ? "（来源：Hermes 官方）"
        : (upstream ? "（来源：" + upstream + "）" : "（来源：市场远程仓库）");
      var riskLine = itype === "official"
        ? "官方可选技能由 Nous Research 维护，安装后复制到本机 skills 目录。"
        : "第三方/社区技能可能包含脚本，且多为远程拉取（未鉴权有 60 次/小时限流），确认继续？";
      if (!confirm('将下载并安装技能「' + name + '」到本机' + sourceHint + '\n' + riskLine)) return;
      btn.disabled = true; btn.textContent = "安装中…";
      var url = "/api/skill-store/install";
      var payload = { identifier: slug, upstream_url: upstream, name: name, source: btn.getAttribute("data-source") || "" };
      var ctrl = (typeof AbortController !== "undefined") ? new AbortController() : null;
      var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, 90000);
      fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: ctrl ? ctrl.signal : undefined,
      }).then(function (r) { return r.json(); }).then(function (d) {
        clearTimeout(timer);
        if (d.ok) {
          toast("已安装：" + (d.name || slug));
          state.installedIds[slug] = true;
          if (card) {
            var foot = card.querySelector(".ss-foot");
            if (foot) foot.innerHTML = '<span></span><span class="ss-installed">✓ 已安装</span>';
          }
        } else {
          toast("安装失败：" + (d.error || "未知错误"), false);
          btn.disabled = false; btn.textContent = "安装";
        }
      }).catch(function (e) {
        clearTimeout(timer);
        var aborted = ctrl && e && e.name === "AbortError";
        toast(aborted ? "安装超时（90秒）：技能来自海外仓库，下载可能较慢，请检查网络后重试" : ("安装请求失败：" + e), false);
        btn.disabled = false; btn.textContent = "安装";
      });
    }

    function doUninstall(id, btn) {
      if (!confirm("确定卸载本机技能「" + id + "」？")) return;
      btn.disabled = true; btn.textContent = "卸载中…";
      fetch("/api/skill-store/installed/" + encodeURIComponent(id), { method: "DELETE" }).then(function (r) {
        return r.json();
      }).then(function (d) {
        if (d.ok) { toast("已卸载：" + id); renderMine(); }
        else { toast("卸载失败：" + (d.error || ""), false); btn.disabled = false; btn.textContent = "卸载"; }
      }).catch(function (e) { toast("卸载请求失败：" + e, false); btn.disabled = false; btn.textContent = "卸载"; });
    }

    function enableSkill(id, on, el) {
      fetch("/api/skill-store/installed/" + encodeURIComponent(id) + "/enable", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: on }),
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (!d.ok) {
          toast("启用状态更新失败：" + (d.error || ""), false);
          el.checked = !on;
        } else {
          toast((on ? "已启用" : "已关闭") + "：" + id);
        }
      }).catch(function (e) {
        toast("请求失败：" + e, false);
        el.checked = !on;
      });
    }

    function openFolder(dir) {
      if (!dir) { toast("无文件夹路径", false); return; }
      // 桌面壳优先走 pywebview；浏览器模式回退 HTTP 接口
      var api = window.pywebview && window.pywebview.api;
      if (api && api.open_in_explorer) {
        try { api.open_in_explorer(dir); return; } catch (e) { /* 回退 HTTP */ }
      }
      fetch("/api/open-in-explorer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dir: dir })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d && d.ok) toast("已打开文件夹");
        else toast("打开失败：" + (d && d.error ? d.error : ""), false);
      }).catch(function (e) { toast("打开失败：" + e, false); });
    }

    function uploadLocal() {
      // 桌面壳优先走 pywebview；浏览器模式用 file input 选 .zip 上传
      var api = window.pywebview && window.pywebview.api;
      if (api && api.pick_and_install_skill) {
        try {
          Promise.resolve(api.pick_and_install_skill("")).then(function (res) {
            if (res && res.ok) { toast("已安装技能：" + (res.name || "")); switchTab("mine"); }
            else if (res) { toast("安装失败：" + (res.error || ""), false); }
          }).catch(function (e) { toast("上传失败：" + e, false); });
          return;
        } catch (e) { /* 回退 HTTP */ }
      }
      var input = document.createElement("input");
      input.type = "file"; input.accept = ".zip,application/zip";
      input.style.display = "none";
      input.onchange = function () {
        var f = input.files && input.files[0];
        if (!f) return;
        var fd = new FormData();
        fd.append("file", f);
        fetch("/api/skill-store/upload-local", { method: "POST", body: fd })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d && d.ok) { toast("已安装技能：" + (d.name || "")); switchTab("mine"); }
            else toast("安装失败：" + (d && d.error ? d.error : ""), false);
          }).catch(function (e) { toast("上传失败：" + e, false); });
      };
      document.body.appendChild(input);
      input.click();
    }

    function openEdit(id) {
      fetch("/api/skill-store/installed/" + encodeURIComponent(id) + "/detail").then(function (r) {
        return r.json();
      }).then(function (d) {
        if (!d.ok) { toast("读取失败：" + (d.error || ""), false); return; }
        showEditor(id, d);
      }).catch(function (e) { toast("读取失败：" + e, false); });
    }

    function showEditor(id, data) {
      var ov = document.createElement("div");
      ov.className = "ss-edit-overlay";
      ov.innerHTML =
        '<div class="ss-edit-modal">' +
          '<h3>修改技能：' + escapeHtml(data.name || id) + '</h3>' +
          '<label class="ss-edit-field">名称<input id="ssEditName" class="form-input" value="' + escapeHtml(data.name || "") + '"></label>' +
          '<label class="ss-edit-field">分类<input id="ssEditCat" class="form-input" value="' + escapeHtml(data.category || "") + '" placeholder="如 ai-agent / office-efficiency"></label>' +
          '<label class="ss-edit-field">描述<textarea id="ssEditDesc" class="form-input" rows="2">' + escapeHtml(data.description || "") + '</textarea></label>' +
          '<label class="ss-edit-field">正文（SKILL.md 内容）<textarea id="ssEditBody" class="ss-edit-body">' + escapeHtml(data.body || "") + '</textarea></label>' +
          '<div class="ss-edit-actions">' +
            '<button class="btn btn-primary btn-sm" id="ssEditSave">保存</button>' +
            '<button class="btn btn-outline btn-sm" id="ssEditCancel">取消</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(ov);
      ov.addEventListener("click", function (e) { if (e.target === ov) document.body.removeChild(ov); });
      var cancelBtn = ov.querySelector("#ssEditCancel");
      var saveBtn = ov.querySelector("#ssEditSave");
      cancelBtn.addEventListener("click", function () { document.body.removeChild(ov); });
      saveBtn.addEventListener("click", function () {
        var payload = {
          name: ov.querySelector("#ssEditName").value,
          category: ov.querySelector("#ssEditCat").value,
          description: ov.querySelector("#ssEditDesc").value,
          body: ov.querySelector("#ssEditBody").value,
        };
        saveBtn.disabled = true; saveBtn.textContent = "保存中…";
        fetch("/api/skill-store/installed/" + encodeURIComponent(id) + "/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }).then(function (r) { return r.json(); }).then(function (d) {
          if (d.ok) { toast("已保存：" + id); document.body.removeChild(ov); renderMine(); }
          else { toast("保存失败：" + (d.error || ""), false); saveBtn.disabled = false; saveBtn.textContent = "保存"; }
        }).catch(function (e) {
          toast("保存失败：" + e, false); saveBtn.disabled = false; saveBtn.textContent = "保存";
        });
      });
    }

    function showSkillDetail(d, card) {
      var ov = document.createElement("div");
      ov.className = "ss-edit-overlay";
      function row(label, val, link) {
        if (val === undefined || val === null || val === "") return "";
        var v = link
          ? '<a href="' + escapeHtml(val) + '" target="_blank" rel="noopener">' + escapeHtml(val) + '</a>'
          : escapeHtml(String(val));
        return '<div class="ss-detail-row"><span class="ss-detail-label">' + escapeHtml(label) +
          '</span><span class="ss-detail-val">' + v + '</span></div>';
      }
      var head = '<div class="ss-detail-name">' + escapeHtml(d.name || "未知") +
        (d.type ? '<span class="ss-type ' + escapeHtml(d.typeCls || "ss-type-community") + '">' + escapeHtml(d.type) + '</span>' : "") +
        '</div>';
      var fieldBody =
        row("类型", d.type) +
        row("作者", d.owner) +
        row("分类", d.category) +
        row("来源", d.source) +
        (d.downloads ? row("下载量", d.downloads) : "") +
        (d.stars ? row("星数", d.stars) : "") +
        (d.likes ? row("收藏", d.likes) : "") +
        row("目录", d.dir) +
        row("主页/仓库", d.homepage, true);
      ov.innerHTML =
        '<div class="ss-edit-modal">' +
          '<div class="ss-detail-head">' + head +
            '<button class="btn ghost sm" id="ssDetailClose">✕</button></div>' +
          fieldBody +
          (d.description ? '<div class="ss-detail-desc">' + escapeHtml(d.description) + '</div>' : "") +
          '<div class="ss-detail-body" id="ssDetailBody"><div class="ss-detail-loading">加载正文…</div></div>' +
        '</div>';
      document.body.appendChild(ov);
      ov.addEventListener("click", function (e) { if (e.target === ov) document.body.removeChild(ov); });
      ov.querySelector("#ssDetailClose").addEventListener("click", function () { document.body.removeChild(ov); });
      // 异步拉取正文：我的技能走本地 detail，市场技能走 /api/skill-store/detail（best-effort）
      var bodyEl = ov.querySelector("#ssDetailBody");
      var id = card && card.getAttribute("data-id");
      var slug = card && card.getAttribute("data-slug");
      var fetchUrl = null, fetchOpts = null;
      if (id) {
        fetchUrl = "/api/skill-store/installed/" + encodeURIComponent(id) + "/detail";
      } else if (slug) {
        fetchUrl = "/api/skill-store/detail";
        fetchOpts = {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ identifier: slug, source: d.source || "", upstream_url: d.upstream_url || "" })
        };
      }
      if (!fetchUrl) { bodyEl.innerHTML = ""; return; }
      fetch(fetchUrl, fetchOpts || {}).then(function (r) { return r.json(); }).then(function (dd) {
        if (dd && dd.ok && dd.body) {
          bodyEl.innerHTML = dd.name ? '<div class="ss-detail-fname">' + escapeHtml(dd.name) + '</div>' : "";
          bodyEl.insertAdjacentHTML('beforeend', '<pre class="ss-detail-pre">' + escapeHtml(dd.body) + '</pre>');
        } else {
          bodyEl.innerHTML = '<div class="ss-detail-loading">详情正文拉取失败：' +
            escapeHtml((dd && dd.error) || "未知") + '</div>';
        }
      }).catch(function () {
        bodyEl.innerHTML = '<div class="ss-detail-loading">详情正文加载失败</div>';
      });
    }

    function bindEvents() {
      root.addEventListener("click", function (e) {
        var t = e.target;
        var tab = t.closest && t.closest(".ss-tab");
        if (tab) { switchTab(tab.getAttribute("data-tab")); return; }
        var mkt = t.closest && t.closest(".ss-market-btn");
        var chip = t.closest && t.closest(".ss-chip");
        if (chip) {
          var sb0 = root.querySelector("#ssSearch");
          if (sb0) state.q = sb0.value.trim();
          state.category = chip.getAttribute("data-cat"); renderChips(); renderMarket(true); return;
        }
        var mktBtn = t.closest && t.closest("#ssMarketBtn");
        if (mktBtn) { toggleMarketPanel(); return; }
        var mktClear = t.closest && t.closest("#ssMktClear");
        if (mktClear) { state.markets = []; closeMarketPanel(); renderMarket(true); return; }
        var mktOk = t.closest && t.closest("#ssMktOk");
        if (mktOk) { applyMarketPanel(); return; }
        var inst = t.closest && t.closest("[data-install]");
        if (inst) { doInstall(inst.getAttribute("data-install"), inst); return; }
        var uninst = t.closest && t.closest("[data-uninstall]");
        if (uninst) { doUninstall(uninst.getAttribute("data-uninstall"), uninst); return; }
        var folder = t.closest && t.closest("[data-folder]");
        if (folder) { openFolder(folder.getAttribute("data-folder")); return; }
        var edit = t.closest && t.closest("[data-edit]");
        if (edit) { openEdit(edit.getAttribute("data-edit")); return; }
        var more = t.closest && t.closest(".ss-loadmore");
        if (more) { state.page++; renderMarket(false); return; }
        var upload = t.closest && t.closest("[data-upload]");
        if (upload) { uploadLocal(); return; }
        var card = t.closest && t.closest(".ss-card");
        if (card && card.getAttribute("data-detail")) {
          try { showSkillDetail(JSON.parse(card.getAttribute("data-detail")), card); } catch (_e) {}
          return;
        }
      });
      root.addEventListener("change", function (e) {
        var en = e.target.closest && e.target.closest("[data-enable]");
        if (en) { enableSkill(en.getAttribute("data-enable"), en.checked, en); }
      });
      var search = root.querySelector("#ssSearch");
      if (search) {
        var debounce;
        search.addEventListener("input", function () {
          state.q = search.value.trim(); // 立即同步，避免 debounce 期间仍用旧 q 搜索
          clearTimeout(debounce);
          debounce = setTimeout(function () { renderMarket(true); }, 200);
        });
      }
      var sortSel = root.querySelector("#ssSort");
      if (sortSel) sortSel.addEventListener("change", function () {
        var sb1 = root.querySelector("#ssSearch");
        if (sb1) state.q = sb1.value.trim();
        state.sort = sortSel.value || "default";
        renderMarket(true);
      });
      // 点击面板外任意处关闭市场下拉
      document.addEventListener("click", function (e) {
        var pnl = document.getElementById("ssMarketPanel");
        if (!pnl || !pnl.classList.contains("open")) return;
        if (pnl.contains(e.target)) return;
        if (e.target.closest && e.target.closest("#ssMarketBtn")) return;
        closeMarketPanel();
      });
    }

    function init() {
      var initTab = (rootId && rootId.indexOf("Settings") >= 0) ? "mine" : "market";
      state.tab = initTab;
      root.innerHTML =
        '<div class="ss-toolbar">' +
          '<div class="ss-tabs">' +
            '<button class="ss-tab' + (initTab === "market" ? " active" : "") + '" data-tab="market">技能市场</button>' +
            '<button class="ss-tab' + (initTab === "mine" ? " active" : "") + '" data-tab="mine">我的技能</button>' +
          '</div>' +
          '<div class="ss-search">' +
            '<input class="form-input" id="ssSearch" placeholder="搜索技能…">' +
            '<div class="ss-market-wrap"><button class="btn btn-outline btn-sm" id="ssMarketBtn">市场：全部 ▼</button></div>' +
            '<button class="btn btn-outline btn-sm" data-upload>📁 上传本地技能</button>' +
            '<select class="form-input ss-sort" id="ssSort" title="排序方式" style="width:auto;">' +
              state.sortModes.map(function (m) {
                return '<option value="' + m[0] + '">' + m[1] + '</option>';
              }).join("") +
            '</select>' +
          '</div>' +
        '</div>' +
        '<div class="ss-chips" id="ssChips"></div>' +
        '<div class="ss-grid" id="ssGrid"></div>' +
        '<div class="ss-status" id="ssStatus"></div>' +
        '<div class="ss-loadmore-wrap" id="ssLoadMore"></div>';
      bindEvents();
      switchTab(initTab);
    }

    init();
    return { root: root, refresh: function () { switchTab(state.tab); } };
  }

  window.initSkillStore = function (rootId) {
    ensureStyle();
    return createStore(rootId || "skillStoreRoot");
  };

  // 自动初始化默认根（/skills 页面）
  if (document.readyState !== "loading") {
    window.initSkillStore("skillStoreRoot");
  } else {
    document.addEventListener("DOMContentLoaded", function () { window.initSkillStore("skillStoreRoot"); });
  }
})();
