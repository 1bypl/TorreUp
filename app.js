/* ============================================================
   TorreUp — application logic
   ============================================================ */
(function () {
  "use strict";

  // Main author's GitHub profile.
  const ABOUT = {github: "https://github.com/1bypl"};

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const t = I18N.t;

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const state = {
    view: "search",
    query: "",
    category: "all",
    sort: "seeds",
    period: "week",
    remote: true,
    thumbnails: true,
    results: [],
    page: 1,
    perPage: 50,
    favorites: loadFavorites(),
    providers: [],
    categories: [],
    scanTimer: null,
  };

  // ---------- persistence (favorites only; no query history) ----------
  function loadFavorites() {
    try { return new Map(JSON.parse(localStorage.getItem("torreup.fav") || "[]")); }
    catch (e) { return new Map(); }
  }
  function saveFavorites() {
    localStorage.setItem("torreup.fav", JSON.stringify(Array.from(state.favorites.entries())));
    updateFavCount();
  }
  function updateFavCount() {
    const n = state.favorites.size;
    const el = $("#favCount");
    el.textContent = n;
    el.classList.toggle("has", n > 0);
  }

  // ---------- icons ----------
  const MAGNET_SVG = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M5 4v8a7 7 0 0 0 14 0V4" stroke="#fff" stroke-width="3.4" stroke-linecap="round"/>
    <path d="M5 4h4v3H5zM15 4h4v3h-4z" fill="#ff5d6c"/>
    <path d="M5 4v8a7 7 0 0 0 14 0V4" stroke="#ff5d6c" stroke-width="3.4" stroke-linecap="round" stroke-dasharray="0 0" opacity=".0"/>
    <path d="M9 4v8a3 3 0 0 0 6 0V4" stroke="#ff5d6c" stroke-width="3.4" stroke-dasharray="7 30" opacity=".9"/>
    <path d="M5 4v3M19 4v3" stroke="#fff" stroke-width="2" opacity=".6"/>
  </svg>`;
  const DOWNLOAD_SVG = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="12" cy="12" r="10" fill="rgba(61,220,132,.15)" stroke="#3ddc84" stroke-width="1.6"/>
    <path d="M12 6v9m0 0-4-4m4 4 4-4M7 18h10" stroke="#3ddc84" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;

  function fileIcon(r) {
    const map = {movies:"🎬",tv:"📺",games:"🎮",software:"💿",music:"🎵",
      ebooks:"📚",audiobooks:"🎧",comics:"📖",anime:"🌸",education:"🎓",other:"📦"};
    return map[r.category] || "📦";
  }

  function catLabel(r) {
    const tr = t("c." + r.category);
    return tr.startsWith("c.") ? (r.category_label || r.category) : tr;
  }

  // ---------- toast ----------
  let toastTimer;
  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
  }

  // ---------- boot ----------
  async function boot() {
    I18N.apply();
    const version = (await api("/api/health")).version;
    $("#versionTag").textContent = "v" + version;
    $("#aboutVersion").textContent = "v" + version;
    $("#aboutVersionRow").textContent = version;
    $("#githubLink").href = ABOUT.github;
    $("#authorLink").href = ABOUT.github;
    $("#aboutMascot").innerHTML = `<img src="/static/img/ghost.svg" alt="TorreUp mascot">`;
    state.providers = await api("/api/providers");
    state.categories = await api("/api/categories");
    initStatic();
    renderCatNav();
    renderCatChips();
    renderCatGrid();
    renderCustomCat();
    renderProviders();
    renderThemes();
    renderLangSelect();
    loadSettings();
    updateFavCount();
    setView("search");
    doSearch("", false);
  }

  async function api(url, opts) {
    const r = await fetch(url, opts);
    return r.json();
  }

  function initStatic() {
    const host = $("#mascotHost");
    host.innerHTML = `<img src="/static/img/ghost.svg" alt="TorreUp mascot">`;

    $("#searchForm").addEventListener("submit", e => {
      e.preventDefault();
      state.query = $("#searchInput").value.trim();
      setView("search");
      doSearch(state.query, true);
    });
    $("#searchInput").addEventListener("input", e => {
      $("#clearBtn").classList.toggle("show", !!e.target.value);
    });
    $("#clearBtn").addEventListener("click", () => {
      $("#searchInput").value = "";
      $("#clearBtn").classList.remove("show");
      state.query = "";
      doSearch("", false);
    });
    $("#menuBtn").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
    $("#brandHome").addEventListener("click", () => {
      $("#searchInput").value = "";
      state.query = ""; state.category = "all";
      setView("search"); doSearch("", false);
    });

    $$(".nav-item").forEach(b => b.addEventListener("click", () => {
      setView(b.dataset.view);
      if (b.dataset.view === "trending") {
        state.period = "week";
        $$("#periodSwitch button").forEach(x => x.classList.toggle("active", x.dataset.period === "week"));
        doSearch("", false);
      }
      if (b.dataset.view === "favorites") renderFavorites();
    }));

    $$("#periodSwitch button").forEach(b => b.addEventListener("click", () => {
      $$("#periodSwitch button").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
      state.period = b.dataset.period;
      doSearch("", false);
    }));

    $("#sortSelect").addEventListener("change", e => {
      state.sort = e.target.value;
      state.page = 1;
      state.results = sortLocal(state.results);
      renderResults();
    });

    $("#refreshBtn").addEventListener("click", () => {
      $("#refreshBtn").classList.add("spinning");
      doSearch(state.query, true, true).finally(() => {
        $("#refreshBtn").classList.remove("spinning");
        toast(t("toast.refreshed"));
      });
    });

    $("#viewToggle").addEventListener("click", () => {
      $("#results").classList.toggle("grid");
      $("#viewToggle").textContent = $("#results").classList.contains("grid") ? "☰" : "☷";
    });

    $("#themeBtn").addEventListener("click", cycleTheme);
    $("#langBtn").addEventListener("click", () => setView("settings"));

    $("#modalClose").addEventListener("click", closeModal);
    $("#modal").addEventListener("click", e => { if (e.target === $("#modal")) closeModal(); });
    document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });

    // settings toggles
    $("#remoteToggle").addEventListener("change", e => {
      state.remote = e.target.checked; saveSettings();
    });
    $("#thumbToggle").addEventListener("change", e => {
      state.thumbnails = e.target.checked; saveSettings(); renderResults();
    });
    $("#proxyToggle").addEventListener("change", e => {
      toast(t(e.target.checked ? "toast.proxyOn" : "toast.proxyOff"));
    });
    $("#mascotToggle").addEventListener("change", e => {
      $("#mascotHost").classList.toggle("hidden", !e.target.checked);
      saveSettings();
    });
    $("#langSelect").addEventListener("change", e => {
      I18N.set(e.target.value);
      refreshI18n();
      renderCatNav(); renderCatChips(); renderCatGrid(); renderCustomCat();
      renderResults(); renderProviders();
      toast(I18N.langs[e.target.value]);
    });

    $("#customSourceForm").addEventListener("submit", addSource);
  }

  function refreshI18n() {
    // re-apply data-i18n and dynamic headings
    $$("[data-i18n]").forEach(el => el.textContent = t(el.dataset.i18n));
    $$("[data-i18n-ph]").forEach(el => el.placeholder = t(el.dataset.i18nPh));
    $("#sortSelect").innerHTML = `
      <option value="seeds">${t("sort.seeds")}</option>
      <option value="peers">${t("sort.peers")}</option>
      <option value="size">${t("sort.size")}</option>
      <option value="date">${t("sort.date")}</option>
      <option value="relevance">${t("sort.relevance")}</option>`;
    $("#sortSelect").value = state.sort;
    updatePageHead();
    updateResultCount();
  }

  // ---------- views ----------
  function setView(view) {
    state.view = view;
    $$(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.view === view));
    $$(".view").forEach(v => v.classList.remove("active"));
    const sectionMap = {
      search: "view-results", trending: "view-results", favorites: "view-results",
      categories: "view-categories", settings: "view-settings", about: "view-about",
    };
    $("#" + (sectionMap[view] || "view-results")).classList.add("active");
    $("#periodSwitch").classList.toggle("hidden", view !== "trending");
    updatePageHead();
    $("#sidebar").classList.remove("open");
    if (view === "settings") {
      api("/api/providers").then(d => { state.providers = d; renderProviders(); });
    }
  }

  function updatePageHead() {
    const map = {
      search: ["page.searchTitle", "page.searchSub"],
      trending: ["page.trendingTitle", "page.trendingSub"],
      favorites: ["page.favoritesTitle", "page.favoritesSub"],
      categories: ["cat.title", "cat.sub"],
      about: ["about.title", "about.sub"],
    };
    const keys = map[state.view] || map.search;
    let title = t(keys[0]), sub = t(keys[1]);
    if (state.view === "search" && state.category !== "all") {
      title = state.category === "all" ? title : (t("page.catPrefix") + ": " + catLabel({category: state.category}));
    }
    $("#pageTitle").textContent = title;
    $("#pageSubtitle").textContent = sub;
  }

  // ---------- search ----------
  function startScanAnimation() {
    stopScanAnimation();
    const fill = $("#activityFill");
    fill.style.background = "linear-gradient(90deg,var(--accent),var(--green))";
    let p = 0;
    const total = state.providers.length + 1;
    state.scanTimer = setInterval(() => {
      p = Math.min(total - 1, p + Math.random() * 2.2);
      fill.style.width = (p / total * 100) + "%";
      $("#activityLabel").textContent = t("activity.sources", {a: Math.floor(p), b: total});
    }, 90);
    $("#statusText").textContent = t("status.searching");
  }
  function stopScanAnimation() {
    if (state.scanTimer) clearInterval(state.scanTimer);
    state.scanTimer = null;
  }

  async function doSearch(query, animate, refresh) {
    state.query = query;
    state.page = 1;
    const params = new URLSearchParams({
      q: query, category: state.category, sort: "seeds",
      period: state.view === "trending" ? state.period : "all",
      remote: state.remote ? "1" : "0",
      refresh: refresh ? "1" : "0",
    });
    if (animate) startScanAnimation();
    else $("#statusText").textContent = t("status.searching");

    let data;
    try {
      data = await api("/api/search?" + params.toString());
    } catch (e) {
      stopScanAnimation();
      $("#statusText").textContent = "Błąd połączenia z silnikiem";
      return;
    }
    stopScanAnimation();

    state.results = sortLocal(data.results || []);
    const total = state.providers.length + 1;
    const n = Math.max(1, (data.sources || []).length);
    const fill = $("#activityFill");
    fill.style.width = (n / total * 100) + "%";
    fill.style.background = n > 1 ? "linear-gradient(90deg,var(--accent),var(--green))"
      : "linear-gradient(90deg,var(--yellow),var(--red))";
    $("#activityLabel").textContent = t("activity.sources", {a: n, b: total});

    $("#sourceChips").innerHTML = (data.sources || []).map(s =>
      `<span class="source-chip on">✓ ${esc(s)}</span>`).join("");

    renderResults();
    const active = (data.sources || []).filter(s => s !== "Lokalny indeks").length;
    $("#statusText").textContent = t("status.done") + " · " +
      (query ? `„${esc(query)}” · ` : "") + (data.elapsed || 0) + "s" +
      (active ? "" : " · " + t("status.found"));
  }

  function sortLocal(items) {
    const arr = items.slice();
    const key = {
      seeds: x => x.seeds, peers: x => x.peers, size: x => x.size_bytes,
      date: x => -x.days_ago,
      relevance: x => (x.seeds + 1) / (x.days_ago + 2),
    }[state.sort] || (x => x.seeds);
    return arr.sort((a, b) => key(b) - key(a));
  }

  // ---------- rendering ----------
  function renderCatNav() {
    $("#catNav").innerHTML = state.categories.map(c => `
      <button class="cat-link ${state.category === c.id ? "active" : ""}" data-cat="${c.id}">
        <span class="ci">${c.icon}</span>${esc(t("c." + c.id).startsWith("c.") ? c.label : t("c." + c.id))}
      </button>`).join("");
    $$("#catNav .cat-link").forEach(b => b.addEventListener("click", () => selectCategory(b.dataset.cat)));
  }

  function renderCatChips() {
    const all = `<button class="chip ${state.category === "all" ? "active" : ""}" data-cat="all">★ ${t("c.all") || "Wszystkie"}</button>`;
    $("#categoryChips").innerHTML = all + state.categories.map(c => `
      <button class="chip ${state.category === c.id ? "active" : ""}" data-cat="${c.id}">
        ${c.icon} ${esc(t("c." + c.id).startsWith("c.") ? c.label : t("c." + c.id))}
      </button>`).join("");
    $$("#categoryChips .chip").forEach(b => b.addEventListener("click", () => selectCategory(b.dataset.cat)));
  }

  function renderCatGrid() {
    $("#catGrid").innerHTML = state.categories.map(c => `
      <div class="cat-card" data-cat="${c.id}">
        <div class="big">${c.icon}</div>
        <h4>${esc(t("cat." + c.id).startsWith("cat.") ? c.label : t("cat." + c.id))}</h4>
        <p>${esc(c.label)}</p>
      </div>`).join("");
    $$("#catGrid .cat-card").forEach(b => b.addEventListener("click", () => {
      selectCategory(b.dataset.cat);
      setView("search");
      doSearch("", false);
    }));
  }

  function selectCategory(cat) {
    state.category = cat;
    renderCatNav(); renderCatChips();
    updatePageHead();
    if (state.view === "search" || state.view === "trending" || state.view === "favorites") {
      doSearch(state.query, false);
    }
  }

  function renderCustomCat() {
    $("#customCat").innerHTML = `<option value="all">★ ${t("c.all")}</option>` +
      state.categories.map(c => {
        const label = t("c." + c.id);
        return `<option value="${c.id}">${esc(label.startsWith("c.") ? c.label : label)}</option>`;
      }).join("");
  }

  function renderProviders() {
    const box = $("#providersList");
    box.innerHTML = state.providers.map(p => {
      const dot = p.status === "ok" ? "on" : (p.status === "tried" ? "tried" : "off");
      const count = p.stats && p.stats.last_count ? `<span class="pcount">+${p.stats.last_count}</span>` : "";
      const canOpen = p.status === "tried" && p.search_url;
      const browserBtn = canOpen
        ? `<button class="open-browser" data-url="${esc(p.search_url)}" data-q="${esc((p.stats && p.stats.last_query) || "")}"
             title="${t("settings.openInBrowser")}">🌐</button>` : "";
      return `
      <div class="provider">
        <span class="pdot ${dot}" title="${esc(t("status." + p.status))}"></span>
        <div class="pinfo">
          <div class="pname">${p.custom ? "⭐ " : ""}${esc(p.name)}${count}</div>
          <div class="pnote">${esc(p.note)}</div>
        </div>
        ${browserBtn}
        ${p.custom ? `<button class="del-source" data-id="${esc(p.id)}" title="${t("settings.remove")}">✕</button>` : ""}
      </div>`;
    }).join("");
    $$(".del-source", box).forEach(b => b.addEventListener("click", () => removeSource(b.dataset.id)));
    $$(".open-browser", box).forEach(b => b.addEventListener("click", () => {
      const url = b.dataset.url.replace("{q}", encodeURIComponent(b.dataset.q || "torrent"));
      fetch("/api/client/open", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({magnet: url}),
      }).then(() => toast(t("toast.browserOpened"))).catch(() => toast(t("toast.sourceError")));
    }));
  }

  async function addSource(e) {
    e.preventDefault();
    const name = $("#customName").value.trim();
    const search_url = $("#customUrl").value.trim();
    const category = $("#customCat").value;
    if (!name || !search_url) { toast(t("toast.sourceError")); return; }
    try {
      const r = await fetch("/api/providers/custom", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name, search_url, category}),
      });
      const d = await r.json();
      if (!r.ok) { toast(d.error || t("toast.sourceError")); return; }
      state.providers = await api("/api/providers");
      renderProviders();
      $("#customName").value = "";
      $("#customUrl").value = "";
      toast(t("toast.sourceAdded"));
    } catch (err) { toast(t("toast.sourceError")); }
  }

  async function removeSource(id) {
    try {
      await fetch("/api/providers/custom?id=" + encodeURIComponent(id), {method: "DELETE"});
      state.providers = await api("/api/providers");
      renderProviders();
      toast(t("toast.sourceRemoved"));
    } catch (err) { toast(t("toast.sourceError")); }
  }

  function updateResultCount() {
    $("#resultCount").innerHTML = t("results.found", {n: state.results.length});
  }

  function renderPagination(totalPages, start, shown) {
    const pager = $("#pagination");
    if (totalPages <= 1) { pager.hidden = true; pager.innerHTML = ""; return; }
    pager.hidden = false;
    const pages = [1];
    const from = Math.max(2, state.page - 3);
    const to = Math.min(totalPages - 1, state.page + 3);
    if (from > 2) pages.push("…");
    for (let p = from; p <= to; p++) pages.push(p);
    if (to < totalPages - 1) pages.push("…");
    if (totalPages > 1) pages.push(totalPages);

    pager.innerHTML = `
      <div class="page-info">${start + 1}–${start + shown} / ${state.results.length}</div>
      <div class="page-buttons">
        <button class="page-btn" data-page="1" title="${t("page.first")}">«</button>
        <button class="page-btn" data-page="${state.page - 1}" ${state.page === 1 ? "disabled" : ""} title="${t("page.prev")}">‹</button>
        ${pages.map(p => p === "…" ? `<span class="page-dots">…</span>` :
          `<button class="page-btn ${p === state.page ? "active" : ""}" data-page="${p}">${p}</button>`).join("")}
        <button class="page-btn" data-page="${state.page + 1}" ${state.page === totalPages ? "disabled" : ""} title="${t("page.next")}">›</button>
        <button class="page-btn" data-page="${totalPages}" title="${t("page.last")}">»</button>
      </div>`;
    $$(".page-btn", pager).forEach(b => b.addEventListener("click", () => {
      state.page = parseInt(b.dataset.page, 10);
      renderResults();
      $(".content").scrollTop = 0;
    }));
  }

  function renderResults() {
    const box = $("#results");
    const pager = $("#pagination");
    if (!state.results.length) {
      box.innerHTML = "";
      pager.hidden = true; pager.innerHTML = "";
      $("#empty").hidden = false;
      updateResultCount();
      return;
    }
    $("#empty").hidden = true;
    const totalPages = Math.ceil(state.results.length / state.perPage);
    if (state.page > totalPages) state.page = totalPages;
    if (state.page < 1) state.page = 1;
    const start = (state.page - 1) * state.perPage;
    const pageItems = state.results.slice(start, start + state.perPage);
    box.innerHTML = pageItems.map(torrentCard).join("");
    renderPagination(totalPages, start, pageItems.length);
    updateResultCount();
    $$(".fav-btn", box).forEach(b => b.addEventListener("click", e => {
      e.stopPropagation(); toggleFavorite(b.dataset.id);
    }));
    $$(".btn-info", box).forEach(b => b.addEventListener("click", e => {
      e.stopPropagation(); openDetail(b.dataset.id);
    }));
    $$(".btn-magnet", box).forEach(b => b.addEventListener("click", e => {
      e.stopPropagation(); copyMagnet(b.dataset.id);
    }));
    $$(".btn-torrent", box).forEach(b => b.addEventListener("click", e => {
      e.stopPropagation(); openClient(b.dataset.id);
    }));
  }

  function torrentCard(r) {
    const fav = state.favorites.has(r.id);
    const actLabel = t("activity." + r.activity) || r.activity;
    const thumb = (state.thumbnails && r.thumbnail)
      ? `<img src="/api/image?url=${encodeURIComponent(r.thumbnail)}" alt="" onerror="this.style.display='none'">`
      : fileIcon(r);
    return `
    <article class="torrent ${r.activity}" data-id="${esc(r.id)}">
      <div class="t-icon">${thumb}</div>
      <div class="t-body">
        <div class="t-title">
          ${r.verified ? `<span class="verified" title="${t("detail.verified")}">✔</span>` : ""}
          <span>${esc(r.title)}</span>
        </div>
        <div class="t-meta">
          <span class="tag">${esc(catLabel(r))}</span>
          <span class="stat seed">▲ ${r.seeds}</span>
          <span class="stat peer">▼ ${r.peers}</span>
          <span class="sep">•</span><span>${esc(r.size)}</span>
          <span class="sep">•</span><span>${esc(r.added_human)}</span>
          <span class="sep">•</span><span>${esc(r.language)}</span>
          <span class="activity-mini ${r.activity}"><span class="dot"></span>${esc(actLabel)}</span>
          <span class="t-source">${esc(r.source)}</span>
        </div>
      </div>
      <div class="t-actions">
        <button class="fav-btn ${fav ? "on" : ""}" data-id="${esc(r.id)}" title="${t("nav.favorites")}">★</button>
        <button class="btn btn-torrent" data-id="${esc(r.id)}" title="${t("btn.download")}">${DOWNLOAD_SVG}${t("btn.download")}</button>
        <button class="btn btn-magnet" data-id="${esc(r.id)}" title="${t("btn.magnet")}">${MAGNET_SVG}${t("btn.magnet")}</button>
        <button class="btn btn-info" data-id="${esc(r.id)}">${t("btn.details")}</button>
      </div>
    </article>`;
  }

  function findTorrent(id) {
    return state.results.find(r => r.id === id) || state.favorites.get(id);
  }

  // ---------- favorites ----------
  function toggleFavorite(id) {
    const r = findTorrent(id);
    if (!r) return;
    if (state.favorites.has(id)) {
      state.favorites.delete(id);
      toast(t("toast.favRemoved"));
    } else {
      state.favorites.set(id, r);
      toast(t("toast.favAdded"));
    }
    saveFavorites();
    if (state.view === "favorites") renderFavorites();
    else renderResults();
  }

  function renderFavorites() {
    state.results = Array.from(state.favorites.values());
    if (!state.results.length) toast(t("toast.noFavorites"));
    renderResults();
    updatePageHead();
  }

  // ---------- actions ----------
  function copyMagnet(id) {
    const r = findTorrent(id);
    if (!r) return;
    const text = r.magnet || r.torrent_url || "";
    if (!text) return;
    if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => fallbackCopy(text));
    else fallbackCopy(text);
    toast(r.magnet ? t("toast.copied") : t("toast.torrentCopied"));
  }
  function fallbackCopy(text) {
    const ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    ta.remove();
  }
  function openClient(id) {
    const r = findTorrent(id);
    if (!r) return;
    // Some RSS feeds expose only a .torrent file, no magnet link.
    if (!r.magnet && r.torrent_url) {
      const a = document.createElement("a");
      a.href = "/api/torrent?url=" + encodeURIComponent(r.torrent_url);
      document.body.appendChild(a);
      a.click();
      a.remove();
      toast(t("toast.torrentDownload"));
      return;
    }
    if (!r.magnet) { toast(t("toast.noLink")); return; }
    fetch("/api/client/open", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({magnet: r.magnet, client: "system"}),
    }).then(() => toast(t("toast.opened"))).catch(() => toast("Błąd"));
  }

  // ---------- detail modal ----------
  function detailData(r) {
    const d = Object.assign({}, r);
    if (!d.added_human || d.added_human === "—") {
      d.added_human = d.added_at ? String(d.added_at).slice(0, 10) : "—";
    }
    if (!d.description || d.description.length < 70) {
      d.description =
        `${d.title}. ${catLabel(d)} • ${t("detail.source")}: ${d.source}. ` +
        `${t("detail.size")}: ${d.size || "—"}. ${t("detail.seeds")}: ${d.seeds}, ` +
        `${t("detail.peers")}: ${d.peers}. ` +
        (d.added_human !== "—" ? `${t("detail.added")}: ${d.added_human}.` : "");
    }
    if (!d.files || !d.files.length) {
      const extMatch = (d.title || "").match(/\b(mkv|mp4|avi|mov|mp3|flac|m4a|wav|zip|rar|7z|iso|exe|pdf|epub|mobi|cbz|cbr)\b/i);
      const fallbacks = {movies:"mkv",tv:"mkv",anime:"mkv",games:"zip",software:"exe",
        music:"mp3",ebooks:"epub",audiobooks:"mp3",comics:"cbz",education:"mp4",other:"zip"};
      const ext = (extMatch && extMatch[1]) || fallbacks[d.category] || "bin";
      const base = (d.title || "torrent")
        .replace(/\b(mkv|mp4|avi|mov|mp3|flac|m4a|wav|zip|rar|7z|iso|exe|pdf|epub|mobi|cbz|cbr)\s*$/i, "")
        .replace(/[\\/:*?"<>|]/g, "_").trim().slice(0, 85) || "torrent";
      d.files = [{ name: base + "." + ext, size: d.size || "—" }];
    }
    return d;
  }

  function openDetail(id) {
    const r = detailData(findTorrent(id));
    if (!r || !r.id) return;
    const thumb = r.thumbnail
      ? `<img src="/api/image?url=${encodeURIComponent(r.thumbnail)}" alt="" onerror="this.style.display='none'">`
      : fileIcon(r);
    const stat = (label, val, color) => `<div class="d-stat"><div class="k">${label}</div><div class="v" ${color ? `style="color:${color}"` : ""}>${val}</div></div>`;
    $("#modalBody").innerHTML = `
      <div class="d-head">
        <div class="d-thumb">${thumb}</div>
        <div>
          <div class="d-title">${esc(r.title)}</div>
          <div class="d-badges">
            <span class="tag">${esc(catLabel(r))}</span>
            <span class="tag">${esc(r.source)}</span>
            <span class="tag activity-mini ${r.activity}"><span class="dot"></span>${esc(t("activity." + r.activity) || "")}</span>
            ${r.verified ? `<span class="tag" style="color:var(--accent)">✔ ${t("detail.verified")}</span>` : ""}
          </div>
        </div>
      </div>
      <div class="d-stats">
        ${stat(t("detail.seeds"), "▲ " + r.seeds, "var(--green)")}
        ${stat(t("detail.peers"), "▼ " + r.peers, "var(--yellow)")}
        ${stat(t("detail.size"), esc(r.size))}
        ${stat(t("detail.added"), esc(r.added_human))}
        ${stat(t("detail.language"), esc(r.language))}
      </div>
      <div class="d-section">
        <h4>${t("detail.description")}</h4>
        <div class="d-desc readmore" id="readmore">${esc(r.description)}</div>
        <span class="link-btn" id="readmoreBtn">${t("btn.readmore")} ↓</span>
      </div>
      <div class="d-section">
        <h4>${t("detail.tags")}</h4>
        <div class="d-tags">${(r.tags || []).map(x => `<span class="tag">${esc(x)}</span>`).join("")}</div>
      </div>
      <div class="d-section">
        <h4>${t("detail.files")} (${(r.files || []).length})</h4>
        <div class="d-files">${(r.files || []).map(f => `
          <div class="d-file"><span>📄 ${esc(f.name)}</span><span class="fs">${esc(f.size)}</span></div>`).join("") || `<div class="d-file"><span>${esc(t("detail.fileCount"))}: —</span></div>`}
        </div>
      </div>
      <div class="d-actions">
        <button class="btn btn-torrent" data-act="dl">${DOWNLOAD_SVG}${t("btn.download")}</button>
        <button class="btn btn-magnet" data-act="mag">${MAGNET_SVG}${t("btn.magnet")}</button>
        <button class="btn btn-info" data-act="client">${t("btn.client")}</button>
        <button class="fav-btn ${state.favorites.has(r.id) ? "on" : ""}" data-act="fav">★</button>
        ${r.source_url ? `<a class="btn" href="${esc(r.source_url)}" target="_blank" rel="noopener noreferrer" style="text-decoration:none">↗ ${esc(r.source)}</a>` : ""}
      </div>`;

    $("#readmoreBtn").addEventListener("click", () => {
      const rm = $("#readmore");
      rm.classList.toggle("open");
      $("#readmoreBtn").textContent = rm.classList.contains("open") ? t("btn.less") + " ↑" : t("btn.readmore") + " ↓";
    });
    $$("[data-act]", $("#modalBody")).forEach(b => b.addEventListener("click", () => {
      const a = b.dataset.act;
      if (a === "dl" || a === "client") openClient(r.id);
      if (a === "mag") copyMagnet(r.id);
      if (a === "fav") { toggleFavorite(r.id); b.classList.toggle("on", state.favorites.has(r.id)); }
    }));
    $("#modal").hidden = false;
  }
  function closeModal() { $("#modal").hidden = true; }

  // ---------- themes & settings ----------
  const THEMES = [
    ["midnight", "#0d1117", "#4aa3ff"], ["aurora", "#0f0b1c", "#a06bff"],
    ["ember", "#17110d", "#ff8a4c"], ["mono", "#0a0a0a", "#e6e6e6"],
    ["forest", "#0b1410", "#4fd18b"],
  ];
  function renderThemes() {
    $("#themeGrid").innerHTML = THEMES.map(([id, bg, ac]) =>
      `<div class="theme-swatch ${document.body.dataset.theme === id ? "active" : ""}"
        data-theme="${id}" style="background:linear-gradient(135deg,${bg} 60%,${ac})" title="${id}">
        <span>${id}</span></div>`).join("");
    $$(".theme-swatch").forEach(s => s.addEventListener("click", () => setTheme(s.dataset.theme)));
  }
  function setTheme(id) {
    document.body.dataset.theme = id;
    localStorage.setItem("torreup.theme", id);
    renderThemes();
  }
  function cycleTheme() {
    const i = THEMES.findIndex(x => x[0] === document.body.dataset.theme);
    setTheme(THEMES[(i + 1) % THEMES.length][0]);
  }

  function renderLangSelect() {
    $("#langSelect").innerHTML = Object.keys(I18N.langs).map(k =>
      `<option value="${k}" ${k === I18N.get() ? "selected" : ""}>${I18N.langs[k]}</option>`).join("");
  }

  function loadSettings() {
    const theme = localStorage.getItem("torreup.theme");
    if (theme) setTheme(theme);
    const remote = localStorage.getItem("torreup.remote");
    if (remote !== null) { state.remote = remote === "1"; $("#remoteToggle").checked = state.remote; }
    const thumb = localStorage.getItem("torreup.thumb");
    if (thumb !== null) { state.thumbnails = thumb === "1"; $("#thumbToggle").checked = state.thumbnails; }
    const mascot = localStorage.getItem("torreup.mascot");
    if (mascot !== null) { $("#mascotToggle").checked = mascot === "1"; $("#mascotHost").classList.toggle("hidden", mascot !== "1"); }
  }
  function saveSettings() {
    localStorage.setItem("torreup.remote", state.remote ? "1" : "0");
    localStorage.setItem("torreup.thumb", state.thumbnails ? "1" : "0");
    localStorage.setItem("torreup.mascot", $("#mascotToggle").checked ? "1" : "0");
  }

  boot();
})();
