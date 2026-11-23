// 근무표 화면(결정 기록 2026-11-23). 서버는 기간·근무표의 전체 명단을 그리고, 아래는 서버에 묻지 않고 바로 바꾼다:
// 부서·유형·스케줄 필터, 변경 내역 표시, 이름 강조, 다른 사람 흐리게, 관제 펼치기. 필터 값은 주소창에 남기고 /prefs/ 로 저장한다.
// ◀ ▶ 앞뒤 기간은 화면이 열리자마자 미리 받아 두었다가 누르면 바로 바꿔 끼운다(브라우저 캐시는 쓰지 않는다: 고친 뒤 옛 화면 방지).
(() => {
  if (window.DutyRoster) { window.DutyRoster.init(); return; }
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const store = {
    get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} },
  };
  const FILTER = ["f", "dept", "type", "shift", "hist"], NAMES = ["q1", "q2", "q3"];
  const cache = new Map();  // 미리 받은 화면 {주소(이름 강조 뺌): Promise<HTML|null>}
  let carry = null, saveTimer = 0;

  function state(f) {
    const pick = n => {  // 일부만 골랐을 때만 거른다(모두·하나도 안 고름 = 전체, prefs.clean 과 같다)
      const all = $$(`input[type=checkbox][name=${n}]`, f), on = all.filter(c => c.checked).map(c => c.value);
      return on.length && on.length < all.length ? new Set(on) : null;
    };
    const hist = $("input[type=checkbox][name=hist]", f);
    return {dept: pick("dept"), type: pick("type"), shift: pick("shift"), hist: hist ? hist.checked : true,
            names: NAMES.map(n => (($(`[name=${n}]`, f) || {}).value || "").trim())};
  }

  function apply(f) {
    const s = state(f), root = $("#roster-root");
    if (!root) return s;
    root.classList.toggle("nohist", !s.hist);
    $$(".lb[data-t]", root).forEach(e => e.classList.toggle("x",
      !!(s.dept && !s.dept.has(e.dataset.d)) || !!(s.type && !s.type.has(e.dataset.t))));
    $$(".sec[data-k]", root).forEach(e => e.classList.toggle("x", !!(s.shift && !s.shift.has(e.dataset.k))));
    $$(".tk", root).forEach(e => {
      e.classList.remove("hl1", "hl2", "hl3");
      const i = s.names.indexOf(e.textContent.trim());
      if (i >= 0 && s.names[i]) e.classList.add("hl" + (i + 1));
    });
    const n = [s.dept, s.type, s.shift].filter(Boolean).length + s.names.filter(Boolean).length + (s.hist ? 0 : 1);
    const cnt = $("#flt-cnt");
    if (cnt) cnt.textContent = n ? `(${n}개 적용 중)` : "(적용 없음)";
    // 엑셀 받기 조건도 지금 화면을 따른다(받기 전에 바꿀 수 있다)
    $$("#xl-panel input[type=checkbox]").forEach(c => {
      const g = $(`input[type=checkbox][name="${c.name}"][value="${CSS.escape(c.value)}"]`, f);
      if (g && c.name !== "board") c.checked = g.checked;
    });
    return s;
  }

  function syncUrl(f, s) {
    const u = new URL(location.href);
    [...FILTER, ...NAMES, "q"].forEach(k => u.searchParams.delete(k));
    for (const [k, v] of new FormData(f)) {
      if ((FILTER.includes(k) && (k !== "f" || f.dataset.mine === "1")) || (NAMES.includes(k) && v.trim())) u.searchParams.append(k, v.trim());
    }
    history.replaceState(history.state, "", u);
    $$("a[data-nav]").forEach(a => {  // ◀ ▶ 는 이름 강조만 싣는다(필터는 저장값을 따른다)
      const v = new URL(a.href);
      NAMES.forEach((k, i) => { v.searchParams.delete(k); if (s.names[i]) v.searchParams.set(k, s.names[i]); });
      a.href = v.pathname + v.search;
    });
  }

  function save(f) {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      const body = new FormData();
      for (const [k, v] of new FormData(f)) {
        if (k === "hist" || (f.dataset.mine === "1" && FILTER.includes(k))) body.append(k, v);
      }
      fetch(f.dataset.prefs, {method: "POST", body, keepalive: true, credentials: "same-origin",
                              headers: {"X-CSRFToken": ($("input[name=csrfmiddlewaretoken]") || {}).value || ""}}).catch(() => {});
    }, 300);
  }

  const snapshot = f => $$("input", f).filter(i => i.name && i.type !== "hidden").map(i => [i.name, i.value, i.type === "checkbox" ? i.checked : null]);
  function restore(f, snap) {
    snap.forEach(([name, value, checked]) => {
      if (checked === null) { const i = $(`input[name="${name}"]`, f); if (i) i.value = value; }
      else { const i = $(`input[type=checkbox][name="${name}"][value="${CSS.escape(value)}"]`, f); if (i) i.checked = checked; }
    });
  }

  const key = h => { const u = new URL(h, location.href); NAMES.forEach(k => u.searchParams.delete(k)); u.hash = ""; return u.href; };
  function prefetch(h) {
    const k = key(h);
    if (!cache.has(k)) cache.set(k, fetch(h, {credentials: "same-origin"})
      .then(r => (r.ok && !r.redirected ? r.text() : null)).catch(() => null));
  }
  function swap(html, href) {
    const doc = new DOMParser().parseFromString(html, "text/html"), next = $("main", doc);
    if (!next || !$("#flt", next)) { location.href = href; return; }
    carry = snapshot($("#flt"));
    $("main").replaceWith(document.adoptNode(next));
    document.title = doc.title;
    history.pushState({duty: 1}, "", href);
    htmx.process(next);
    init();
  }

  function monthPanel() {
    const t = $("#roster.cal"), panel = $("#mday");
    if (!t || !panel) return;
    const show = td => {
      if (!td) return;
      $$("td.sel", t).forEach(x => x.classList.remove("sel"));
      td.classList.add("sel");
      const h = document.createElement("h4"), a = document.createElement("a");
      a.href = td.dataset.day; a.textContent = td.dataset.label; h.append(a);
      panel.replaceChildren(h, ...[...td.children].filter(c => !c.classList.contains("dh")).map(c => c.cloneNode(true)));
      if (panel.children.length === 1) { const p = document.createElement("p"); p.className = "none"; p.textContent = "근무 없음"; panel.append(p); }
      htmx.process(panel);
    };
    t.addEventListener("click", e => {
      const td = e.target.closest("td[data-label]");
      if (!td || !matchMedia("(max-width: 600px)").matches) return;
      e.preventDefault();
      show(td);
    }, true);
    show($("td.today-col", t) || $("td[data-label]:not(.we)", t));
  }

  function init() {
    const f = $("#flt");
    if (!f) return;
    if (carry) { restore(f, carry); carry = null; }
    const changed = () => { const s = apply(f); syncUrl(f, s); return s; };
    f.addEventListener("change", e => { changed(); if (!NAMES.includes(e.target.name)) save(f); });
    f.addEventListener("input", e => { if (NAMES.includes(e.target.name)) changed(); });
    f.addEventListener("submit", e => { e.preventDefault(); changed(); });
    $$("[data-toggle]").forEach(b => b.addEventListener("click", () => {
      const p = document.getElementById(b.getAttribute("aria-controls"));
      p.hidden = !p.hidden;
      b.setAttribute("aria-expanded", String(!p.hidden));
    }));
    const dim = $("#dim"), root = $("#roster-root"), saved = store.get("duty-dim");
    if (dim && root) {
      dim.checked = saved === null ? dim.dataset.default === "1" : saved === "1";
      const draw = () => root.classList.toggle("dim", dim.checked);
      dim.addEventListener("change", () => { store.set("duty-dim", dim.checked ? "1" : "0"); draw(); });
      draw();
    }
    const open = store.get("duty-slots") === "1";  // 관제: 하나를 펴거나 접으면 모두 같이, 기기마다 기억
    $$("details.slot").forEach(x => {
      x.open = open;
      x.addEventListener("toggle", () => {
        store.set("duty-slots", x.open ? "1" : "0");
        $$("details.slot").forEach(y => { if (y.open !== x.open) y.open = x.open; });
      });
    });
    apply(f);
    monthPanel();
    const today = $("#today");
    if (today && !location.hash.startsWith("#d-")) {  // 겹친 화면: 팝업에서 돌아온 날짜 칸을 그대로 둔다
      today.scrollIntoView({block: "nearest", inline: "center"});
      if (location.hash === "#today") $$(".today-col").forEach(e => e.classList.add("blink"));
    }
    $$("a[data-nav]").forEach(a => prefetch(a.href));
  }

  document.addEventListener("click", e => {
    const a = e.target.closest("a[data-nav]");
    if (!a || e.button || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    const p = cache.get(key(a.href));
    if (!p) return;
    e.preventDefault();
    p.then(html => (html ? swap(html, a.href) : (location.href = a.href)));
  });
  addEventListener("popstate", () => location.reload());  // 바꿔 끼운 화면에서 뒤로 가기 = 그 주소를 새로 연다
  // 칸·메모 팝업: 돌아올 주소는 지금 주소(필터가 주소창에만 바뀌어 있다), 근무 변경 To 후보는 지금 부서·유형 필터로
  document.addEventListener("htmx:configRequest", e => {
    const el = e.detail.elt, f = $("#flt");
    if (!f || !el.closest || !el.closest("#roster-root")) return;
    const n = new URL(el.getAttribute("hx-get") || "", location.href).searchParams.get("next");
    if (n === null) return;
    e.detail.parameters.next = location.pathname + location.search + (n.includes("#") ? n.slice(n.indexOf("#")) : "");
    if (el.matches("a.cell") && el.closest("[data-k]")) {
      const s = state(f);
      if (s.dept) e.detail.parameters.dept = [...s.dept];
      if (s.type) e.detail.parameters.type = [...s.type];
    }
  });
  window.DutyRoster = {init};
  init();
})();
