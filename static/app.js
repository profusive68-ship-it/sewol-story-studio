/* 세월의 사연극장 스튜디오 — 대시보드 동작 */
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const mmss = (s) => {
  s = Math.max(0, Math.round(s || 0));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

let META = null;
let CURRENT = null;      // 현재 열어둔 프로젝트
let POLL = null;
let A_LAST_JOB = null;

const STORE = "sewol.studio.settings.v1";
const DEFAULTS = {
  genre: "tear_family", preset: "short50", hook15: true, sequel: true, teaserMode: "auto_sequel",
  teaserText: "", voiceMode: "multi", rate: 0, avatar: true, avatarKind: "female",
  subSize: "senior", imageMode: "B", likeVoice: true, likeBanner: true, outroCta: true,
  endScreen: true, sleepRain: false, topic: "", likeVoiceText: "", ctaText: "",
};

function toast(msg, bad = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (bad ? " bad" : "");
  t.hidden = false;
  clearTimeout(t._t);
  t._t = setTimeout(() => (t.hidden = true), 4200);
}

function saveLocal() {
  const data = collect();
  localStorage.setItem(STORE, JSON.stringify(data));
}

function restoreLocal() {
  try {
    const d = JSON.parse(localStorage.getItem(STORE) || "{}");
    $("#topic").value = d.topic || "";
    $("#hook15").checked = d.hook15 !== false;
    $("#sequel").checked = d.sequel !== false;
    $("#teaserMode").value = d.teaserMode || "auto_sequel";
    $("#teaserText").value = d.teaserText || "";
    $("#voiceMode").value = d.voiceMode || "multi";
    $("#rate").value = d.rate ?? 0;
    $("#avatar").checked = d.avatar !== false;
    $("#avatarKind").value = d.avatarKind || "female";
    $("#likeVoice").checked = d.likeVoice !== false;
    $("#likeBanner").checked = d.likeBanner !== false;
    $("#outroCta").checked = d.outroCta !== false;
    $("#endScreen").checked = d.endScreen !== false;
    $("#sleepRain").checked = !!d.sleepRain;
    $("#likeVoiceText").value = d.likeVoiceText || "";
    $("#ctaText").value = d.ctaText || "";
    if (d.imageMode) {
      const r = document.querySelector(`input[name=imageMode][value="${d.imageMode}"]`);
      if (r) r.checked = true;
    }
    if (d.subSize) {
      const r = document.querySelector(`input[name=subSize][value="${d.subSize}"]`);
      if (r) r.checked = true;
    }
  } catch (e) {}
}

function collect() {
  return {
    preset: document.querySelector(".preset-grid label.on")?.dataset.preset || "pilot5",
    genre: document.querySelector(".genre-grid label.on")?.dataset.genre || "tear_family",
    topic: $("#topic").value.trim(),
    hook15: $("#hook15").checked,
    sequel: $("#sequel").checked,
    teaser_mode: $("#teaserMode").value,
    teaser_text: $("#teaserText").value.trim(),
    voice_mode: $("#voiceMode").value,
    rate: Number($("#rate").value || 0),
    avatar: $("#avatar").checked,
    avatar_kind: $("#avatarKind").value,
    subtitle_size: document.querySelector("input[name=subSize]:checked")?.value || "senior",
    image_mode: document.querySelector("input[name=imageMode]:checked")?.value || "B",
    like_banner: $("#likeBanner").checked,
    like_voice: $("#likeVoice").checked,
    like_voice_text: $("#likeVoiceText").value.trim(),
    outro_cta: $("#outroCta").checked,
    cta_text: $("#ctaText").value.trim(),
    end_screen: $("#endScreen").checked,
    sleep_rain: $("#sleepRain").checked,
    youtube_privacy: ($("#ytPrivacy").value === "scheduled") ? "private" : $("#ytPrivacy").value,
    youtube_publish_at: ($("#ytPrivacy").value === "scheduled") ? $("#ytPublishAt").value : "",
    youtube_title_index: Number($("#ytTitleIndex").value || 0),
    auto_upload: $("#ytAuto").checked,
  };
}

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  const text = await r.text();
  let data = {};
  try { data = JSON.parse(text); } catch (e) { data = { raw: text }; }
  if (!r.ok) throw new Error(data.detail || data.error || data.message || `HTTP ${r.status}`);
  return data;
}

// ── 초기 화면 ────────────────────────────────────────────────────────────
async function init() {
  renderGenres();
  renderPresets();
  restoreLocal();
  bind();
  await loadMeta();
  await loadHealth();
  await loadYtStatus();
  await loadGhStatus();
  await loadProjects();
  await loadStrategy();
  await loadRemote();
  await loadSchedule();
  await loadInbox();
  await loadAutoInbox();
  setInterval(() => loadAutoInbox(), 10000);
}

function renderGenres() {
  $("#genreGrid").innerHTML = Object.entries(META_GENRES).map(([k, v]) => `
    <label data-genre="${k}" class="${k === "tear_family" ? "on" : ""}">
      <b>${esc(v.label)}</b><span>${esc(v.hint)}</span>
    </label>`).join("");
  $$("#genreGrid label").forEach((el) => el.addEventListener("click", () => {
    $$("#genreGrid label").forEach((x) => x.classList.remove("on"));
    el.classList.add("on");
    saveLocal();
  }));
}

function renderPresets() {
  $("#presetGrid").innerHTML = Object.entries(META_PRESETS).map(([k, v]) => `
    <label data-preset="${k}" class="${k === "shorts50" ? "on" : ""}">
      <b>${esc(v.label)}</b><span>${esc(v.aspect)} · ${v.target ? Math.round(v.target / 60) + "분" : "합본"}</span>
      <span>${esc(v.note || "")}</span>
    </label>`).join("");
  $$("#presetGrid label").forEach((el) => el.addEventListener("click", () => {
    $$("#presetGrid label").forEach((x) => x.classList.remove("on"));
    el.classList.add("on");
    onPresetChange();
    saveLocal();
  }));
  onPresetChange();
}

function onPresetChange() {
  const preset = document.querySelector(".preset-grid label.on")?.dataset.preset;
  const isWeekend = preset === "weekend";
  $("#weekendCard").hidden = !isWeekend;
  $("#btnCreate").disabled = isWeekend;
  $("#btnCreate").textContent = isWeekend
    ? "아래 [합본 만들기]를 사용하세요"
    : (document.querySelector("input[name=imageMode]:checked")?.value === "A"
      ? "완전자동 제작 시작 (모드 A)" : "대본 + 이미지 요청서 만들기");
  if (isWeekend) loadWeekendOptions();
}

// META 는 나중에 오므로 초기 렌더용 기본값을 먼저 둔다
const META_GENRES = {
  tear_family: { label: "① 눈물·가족 감동형", hint: "부모·자식의 오래된 오해와 사랑" },
  reversal: { label: "② 고구마→사이다 대반전형", hint: "억울함이 통쾌하게 뒤집히는 사이다" },
  mystery: { label: "③ 미스터리·휴먼 반전형", hint: "단서 하나를 따라가는 사람 사연" },
  inlaw: { label: "④ 시댁·부부 갈등형", hint: "며느리·시어머니·부부의 현실 갈등" },
  free: { label: "⑤ 자유 주제 직접 입력", hint: "직접 적어 주신 주제로" },
};
const META_PRESETS = {
  shorts50: { label: "50초 쇼츠", aspect: "9:16", target: 50, note: "첫 3초 훅 · 세로" },
  pilot5: { label: "5분 파일럿", aspect: "16:9", target: 300, note: "완결 단편" },
  mid20: { label: "20분 중편", aspect: "16:9", target: 1200, note: "8개 장" },
  full40: { label: "40분 본편", aspect: "16:9", target: 2400, note: "라디오 드라마" },
  weekend: { label: "주말 2시간 몰아듣기", aspect: "16:9", target: 7200, note: "2~3편 합본" },
};

async function loadMeta() {
  const m = await api("/api/meta");
  META = m;
  Object.keys(META_GENRES).forEach((k) => { if (m.genres?.find((g) => g.key === k)) META_GENRES[k] = m.genres.find((g) => g.key === k); });
  (m.presets || []).forEach((p) => { META_PRESETS[p.key] = p; });
  renderGenres();
  renderPresets();
  const conf = m.config || {};
  $("#apiBadge").textContent = conf.has_key ? "키 저장됨" : "키 없음";
  $("#apiBadge").className = "badge " + (conf.has_key ? "on" : "");
  if (m.defaults) {
    $("#likeVoiceText").placeholder = "기본: " + m.defaults.like_voice_text;
    $("#ctaText").placeholder = "기본: " + m.defaults.cta_text;
  }
  if (conf.has_key && conf.key_masked) $("#apiMsg").textContent = `저장된 키: ${conf.key_masked} · 모델 ${conf.text_model}`;
  if (conf.youtube_privacy !== undefined) {
    const p = conf.youtube_privacy || "private";
    $("#ytPrivacy").value = p === "private" && conf.youtube_publish_at ? "scheduled" : p;
    $("#ytPublishAt").value = conf.youtube_publish_at || "";
    $("#ytTitleIndex").value = String(conf.youtube_title_index ?? 0);
    $("#ytAuto").checked = !!conf.youtube_auto_upload;
  }
}

async function loadHealth() {
  try {
    const h = await api("/api/health");
    const enc = h.encoder || "";
    $("#health").innerHTML = `
      <span class="chip ${h.ok ? "ok" : "bad"}">ffmpeg ${h.ok ? "정상" : "없음"}</span>
      <span class="chip ${enc.includes("videotoolbox") ? "ok" : ""}">${esc(enc)}</span>
      <span class="chip">사연 ${h.projects ?? 0}개</span>
      <span class="chip">v${esc(h.version || "")}</span>`;
  } catch (e) {
    $("#health").innerHTML = `<span class="chip bad">서버 연결 실패</span>`;
  }
}

// ── API 키 ───────────────────────────────────────────────────────────────
async function saveKey() {
  const key = $("#apiKey").value.trim();
  if (!key) return toast("API 키를 입력해 주세요.", true);
  try {
    const conf = await api("/api/config", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gemini_api_key: key }),
    });
    $("#apiKey").value = "";
    $("#apiBadge").textContent = "키 저장됨";
    $("#apiBadge").className = "badge on";
    $("#apiMsg").textContent = `저장 완료 (${conf.key_masked}) · 이 맥북 안에만 보관됩니다.`;
    toast("API 키를 저장했습니다.");
  } catch (e) { toast(e.message, true); }
}

async function testKey() {
  $("#apiMsg").textContent = "연결 확인 중…";
  try {
    const r = await api("/api/config/test", { method: "POST" });
    if (r.ok) {
      $("#apiMsg").textContent = `연결 성공 — ${r.message}`;
      toast("Gemini 연결 성공");
    } else {
      $("#apiMsg").textContent = "연결 실패 — " + (r.error || "");
      toast("연결 실패: " + (r.error || ""), true);
    }
  } catch (e) { toast(e.message, true); }
}

// ── 만들기 ───────────────────────────────────────────────────────────────
async function createProject() {
  const payload = collect();
  if (payload.preset === "weekend") return toast("주말 합본은 아래 [합본 만들기]를 눌러 주세요.", true);
  if (payload.image_mode === "A" && !payload.hasKey) {
    // 키 여부는 서버가 판단. 경고만.
  }
  payload.auto_assemble = payload.image_mode === "A";
  $("#btnCreate").disabled = true;
  $("#btnCreate").textContent = "준비 중…";
  try {
    const { job } = await api("/api/projects", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    watchJob(job, { onDone: async (j) => {
      const p = j.result?.project;
      if (p?.id) await openProject(p.id);
      await loadProjects();
      await loadHealth();
    }});
  } catch (e) {
    toast(e.message, true);
  } finally {
    onPresetChange();
  }
}

function setSteps(step) {
  $$("#jobSteps .step").forEach((el) => {
    const n = Number(el.dataset.step);
    el.classList.toggle("done", n < step);
    el.classList.toggle("active", n === step);
  });
}

function watchJob(jobId, opts = {}) {
  if (POLL) clearInterval(POLL);
  A_LAST_JOB = jobId;
  $("#jobPanel").hidden = false;
  $("#jobBadge").textContent = "진행 중";
  $("#jobBadge").className = "badge";
  $("#jobResult").innerHTML = "";
  $("#jobExtra").innerHTML = "";
  $("#jobTitle").textContent = "작업 진행";
  setSteps(1);
  let lastLogLen = 0;
  const tick = async () => {
    let j;
    try { j = await api(`/api/jobs/${jobId}`); }
    catch (e) {
      clearInterval(POLL); POLL = null; toast(e.message, true); return;
    }
    $("#jobBar").style.width = `${j.percent || 0}%`;
    $("#jobMsg").textContent = `${j.percent || 0}% · ${j.message || ""}`;
    if (j.step) setSteps(j.step);
    const log = (j.log || []).slice(-8).join("\n");
    if (log !== $("#jobLog").textContent) {
      $("#jobLog").textContent = log;
      $("#jobLogWrap").open = true;
      $("#jobLogWrap").scrollTop = $("#jobLogWrap").scrollHeight;
    }
    if (j.status === "done") {
      clearInterval(POLL); POLL = null;
      setSteps(7);
      $("#jobBadge").textContent = "완료";
      $("#jobBadge").className = "badge on";
      $("#jobBar").style.width = "100%";
      $("#jobMsg").textContent = "완성되었습니다.";
      if (j.kind === "youtube_connect") {
        toast(j.result?.channel?.title ? `채널 연동 완료 — ${j.result.channel.title}` : "채널 연동 완료");
        await loadYtStatus();
      } else if (j.kind === "youtube_upload") {
        const y = j.result || {};
        $("#jobResult").innerHTML = y.url
          ? `<a href="${esc(y.url)}" target="_blank">유튜브 영상 열기 <span>${esc(y.privacy || "")}</span></a>
             <a href="${esc(y.studio_url || "")}" target="_blank">유튜브 스튜디오에서 확인 <span>예약·공개 설정</span></a>`
          : "";
        toast("유튜브 업로드가 끝났습니다.");
        if (j.result?.project_id) await openProject(j.result.project_id);
      } else if (j.result?.project?.id) await openProject(j.result.project.id);
      else if (j.result?.video) showCompileResult(j.result);
      await loadProjects();
      opts.onDone && opts.onDone(j);
      if (!opts.quiet) toast("완성되었습니다.");
    } else if (j.status === "error") {
      clearInterval(POLL); POLL = null;
      $("#jobBadge").textContent = "오류";
      $("#jobBadge").className = "badge bad";
      $("#jobMsg").textContent = j.message || "오류가 발생했습니다.";
      $("#jobLog").textContent = j.error || log;
      $("#jobLogWrap").open = true;
      toast(j.message || "오류", true);
    }
  };
  tick();
  POLL = setInterval(tick, 1400);
}

// ── 프로젝트 목록/상세 ──────────────────────────────────────────────────
async function loadProjects() {
  try {
    const list = await api("/api/projects");
    if (!list.length) {
      $("#projectList").innerHTML = `<p class="hint">아직 만든 사연이 없습니다. 왼쪽에서 첫 사연을 만들어 보세요.</p>`;
      return;
    }
    $("#projectList").innerHTML = list.map((p) => {
      const done = (p.status?.stage === "done");
      const pct = p.status?.percent || 0;
      return `<div class="project">
        <b>${esc(p.title || "(제목 없음)")}</b>
        <div class="meta">${esc(p.genre_label || "")} · ${esc(p.format || "")} · ${esc(p.created_at || "")}</div>
        <div class="mini-bar"><div style="width:${done ? 100 : pct}%"></div></div>
        <div class="meta">${done ? "완성" : esc(p.status?.message || "작업 중")} ${done ? "" : `· ${pct}%`}</div>
        <div class="acts">
          <button data-open="${p.id}">열기</button>
          ${p.outputs?.video ? `<a href="/api/projects/${p.id}/file/video" target="_blank">영상</a>` : ""}
          ${p.outputs?.thumb_style1 ? `<a href="/api/projects/${p.id}/file/thumb1" target="_blank">썸네일1</a>` : ""}
          ${p.outputs?.thumb_style2 ? `<a href="/api/projects/${p.id}/file/thumb2" target="_blank">썸네일2</a>` : ""}
          ${p.outputs?.video ? `<button data-shorts="${p.id}">쇼츠 뽑기</button>` : ""}
          ${p.outputs?.shorts ? `<a href="/api/projects/${p.id}/file/shorts" target="_blank">쇼츠</a>` : ""}
          <a href="/api/projects/${p.id}/file/request" target="_blank">요청서</a>
          <a href="/api/projects/${p.id}/file/copy" target="_blank">카피</a>
        </div>
      </div>`;
    }).join("");
    $$("[data-open]").forEach((b) => b.addEventListener("click", () => openProject(b.dataset.open)));
    $$("[data-shorts]").forEach((b) => b.addEventListener("click", () => makeShorts(b.dataset.shorts)));
    loadWeekendOptions();
  } catch (e) { /* 조용히 */ }
}

async function openProject(id) {
  try {
    const p = await api(`/api/projects/${id}`);
    CURRENT = p;
    renderDetail(p);
  } catch (e) { toast(e.message, true); }
}

function fileUrl(id, kind) { return `/api/projects/${id}/file/${kind}`; }

function renderDetail(p) {
  const panel = $("#detailPanel");
  panel.hidden = false;
  const done = p.status?.stage === "done";
  const pct = p.status?.percent || 0;
  const planFiles = p.image_plan || [];
  const have = new Set(p.image_files || []);
  const images = planFiles.map((e) => {
    const ok = have.has(e.file);
    return `<figure>${ok
      ? `<img src="/api/projects/${p.id}/image/${e.file}?v=${Date.now()}" alt="${esc(e.file)}">`
      : `<div class="missing">${esc(e.file)}<br>없음</div>`}
      <figcaption>${esc(e.file)}</figcaption></figure>`;
  }).join("");

  const scenes = (p.scenes || []).slice(0, 60).map((s) => {
    const sp = { narrator: "해설", old_male: "노인", old_female: "할머니", female: "여성", young_male: "청년", child: "아이" }[s.speaker] || s.speaker;
    return `<p><span class="sp">${esc(sp)}</span>${esc(s.text)}</p>`;
  }).join("");

  const links = [];
  if (p.outputs?.video) links.push(`<a href="${fileUrl(p.id, "video")}" target="_blank">영상 보기 <span>영상 파일</span></a>`);
  if (p.outputs?.thumb_style1) links.push(`<a href="${fileUrl(p.id, "thumb1")}" target="_blank">썸네일 ① 인물 드라마형 <span>이미지 파일</span></a>`);
  if (p.outputs?.thumb_style2) links.push(`<a href="${fileUrl(p.id, "thumb2")}" target="_blank">썸네일 ② 대문짝 텍스트형 <span>이미지 파일</span></a>`);
  links.push(`<a href="${fileUrl(p.id, "copy")}" target="_blank">업로드 카피 <span>문서</span></a>`);
  links.push(`<a href="${fileUrl(p.id, "srt")}" target="_blank">자막 <span>srt</span></a>`);
  links.push(`<a href="${fileUrl(p.id, "project")}" target="_blank">project.json <span>설계도</span></a>`);

  const warnings = (p.warnings || []).slice(0, 4).map((w) => `<div class="warn">${esc(w)}</div>`).join("");
  const need = p.missing_images || [];
  const pack = p.upload_pack || {};
  const titles = pack.titles || p.titles || [p.title];
  const desc = pack.description || p.description || "";
  const pinned = pack.pinned_comment || "(조립 후 자동 생성됩니다)";
  const seo = `
    <label class="label">유튜브 제목 3안 — [억울함/갈등] + [결정적 단서] + [충격 반전]</label>
    <div class="copy-row">${titles.map((t, i) => `
      <div class="copy-item"><span class="copy-num">${i + 1}</span><span class="copy-text">${esc(t)}</span>
        <button class="btn small" data-copy="${esc(t)}">복사</button></div>`).join("")}
    </div>
    <label class="label">설명문 + 챕터 + 해시태그</label>
    <pre class="copybox" id="seoDesc">${esc(desc)}</pre>
    <div class="row" style="margin-top:8px">
      <button class="btn small" data-copy-el="seoDesc">설명문 원클릭 복사</button>
      <button class="btn ghost small" data-copy="${esc((pack.hashtags || p.hashtags || []).join(" "))}">해시태그만 복사</button>
    </div>
    <label class="label">고정댓글</label>
    <pre class="copybox" id="seoPinned">${esc(pinned)}</pre>
    <button class="btn small" data-copy-el="seoPinned">고정댓글 복사</button>
  `;

  panel.innerHTML = `
    <div class="card-head">
      <h2 class="detail-title">${esc(p.title)}</h2>
      <span class="badge ${done ? "on" : ""}">${done ? "완성" : `${pct}%`}</span>
    </div>
    <div class="detail-meta">${esc(p.genre_label || "")} · ${esc(p.format?.label || "")} · ${esc(p.aspect || p.format?.aspect || "")}</div>
    <div class="tagrow">
      <span class="tag">${p.source === "gemini" ? "AI 대본" : "예시 대본"}</span>
      <span class="tag">이미지 ${planFiles.length}장</span>
      <span class="tag">${esc(p.options?.voice_mode === "multi" ? "다중 성우" : p.options?.voice_mode === "female" ? "여성 낭독" : "남성 낭독")}</span>
      <span class="tag">${esc(p.options?.subtitle_size === "basic" ? "자막 70px" : "자막 92px")}</span>
      ${p.duration ? `<span class="tag">${mmss(p.duration)}</span>` : ""}
    </div>
    ${warnings}
    ${done ? `<video controls preload="metadata" src="${fileUrl(p.id, "video")}" style="width:100%;border-radius:14px;background:#000;margin-bottom:12px"></video>` : ""}
    ${planFiles.length ? `<div class="requestbox">
      <div class="row">
        <button class="btn primary small" id="btnGhRequest">📤 케빈에게 이미지 요청하기</button>
        <a class="btn ghost small" href="${fileUrl(p.id, "request")}" target="_blank">요청서 보기</a>
      </div>
      <p class="hint small">요청 누르시면 케빈이 5분 이내에 자동 감지해서 이미지를 깃허브로 보내드립니다 (따로 톡 안 주셔도 됩니다!)</p>
    </div>` : ""}
    <div class="result-links">${links.join("")}</div>
    ${(p.outputs?.video) ? `<div class="ytbox">
      <label class="label">유튜브에 올리기</label>
      <div class="row">
        <select id="projYtTitle">${(pack.titles || [p.title]).map((t, i) => `<option value="${i}" ${i === (p.options?.youtube_title_index || 0) ? "selected" : ""}>${i + 1}안 · ${esc(t)}</option>`).join("")}</select>
        <button class="btn small" id="btnProjYt">지금 이 프로젝트 업로드</button>
      </div>
      ${p.youtube?.url ? `<p class="hint small">이미 업로드됨: <a href="${esc(p.youtube.url)}" target="_blank" style="color:#e8be5c">${esc(p.youtube.url)}</a> · ${esc(p.youtube.privacy)}${p.youtube.publish_at ? " · 공개 예약 " + esc(p.youtube.publish_at) : ""}</p>` : `<p class="hint small">공개 방식·예약 시간은 위 [유튜브 자동 업로드] 설정을 따릅니다.</p>`}
    </div>` : ""}
    ${seo}
    <div class="row" style="margin-top:10px">
      <button class="btn small" id="btnOpenFolder">폴더 열기</button>
      ${need.length ? `<button class="btn primary small" id="btnAssemble">영상 조립 시작 (${planFiles.length - need.length}/${planFiles.length}장 준비)</button>`
        : (done ? `<button class="btn ghost small" id="btnAssemble">다시 조립</button>` : `<button class="btn primary small" id="btnAssemble">영상 조립 시작</button>`)}
      ${p.outputs?.video ? `<button class="btn ghost small" id="btnShorts">📱 50초 쇼츠 뽑기</button>` : ""}
      ${p.outputs?.shorts ? `<a class="btn small" href="${fileUrl(p.id, "shorts")}" target="_blank">쇼츠 보기</a>` : ""}
    </div>
    ${need.length ? `<p class="hint small">이미지 ${need.length}장이 아직 없습니다: ${need.slice(0, 8).map(esc).join(", ")}</p>` : ""}
    <label class="label">장면 이미지 (${have.size}/${planFiles.length})</label>
    <div class="img-grid">${images}</div>
    <div class="drop" id="dropZone">이미지 파일을 여기에 끌어다 놓거나 클릭해 선택하세요<br><small>s01.png, s02.png … 이름 그대로</small></div>
    <input type="file" id="imgInput" accept="image/*,.zip" multiple hidden>
    <label class="label">썸네일 문구 (수정 후 바로 재생성)</label>
    <div class="thumb-edit">
      <input id="th1a" value="${esc(p.thumbnail?.style1?.[0] || "")}" placeholder="인물형 1번째 줄">
      <input id="th1b" value="${esc(p.thumbnail?.style1?.[1] || "")}" placeholder="인물형 2번째 줄">
      ${[0, 1, 2, 3, 4].map((i) => `<input id="th2${i}" value="${esc(p.thumbnail?.style2?.[i] || "")}" placeholder="대문짝 ${i + 1}번째 줄">`).join("")}
      <button class="btn small" id="btnThumb">썸네일 다시 만들기</button>
    </div>
    <label class="label">대본 미리보기</label>
    <div class="script">${scenes || '<p class="hint">대본이 없습니다.</p>'}</div>
  `;

  $$("[data-copy]").forEach((b) => b.addEventListener("click", () => copyText(b.dataset.copy)));
  $$("[data-copy-el]").forEach((b) => b.addEventListener("click", () => {
    const el = document.getElementById(b.dataset.copyEl);
    copyText(el ? el.textContent : "");
  }));
  $("#btnProjYt")?.addEventListener("click", () => uploadToYoutube(p.id));
  $("#btnGhRequest")?.addEventListener("click", () => requestKevinsImages(p.id));
  $("#btnShorts")?.addEventListener("click", () => makeShorts(p.id));
  $("#btnOpenFolder")?.addEventListener("click", async () => {
    try { await api(`/api/projects/${p.id}/open`, { method: "POST" }); }
    catch (e) { toast(e.message, true); }
  });
  $("#btnAssemble")?.addEventListener("click", () => assemble(p.id));
  const drop = $("#dropZone");
  const input = $("#imgInput");
  drop?.addEventListener("click", () => input.click());
  input?.addEventListener("change", () => uploadImages(p.id, input.files));
  drop?.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("hover"); });
  drop?.addEventListener("dragleave", () => drop.classList.remove("hover"));
  drop?.addEventListener("drop", (e) => {
    e.preventDefault(); drop.classList.remove("hover");
    uploadImages(p.id, e.dataTransfer.files);
  });
  $("#btnThumb")?.addEventListener("click", () => regenThumb(p.id));
}

function ytPrivacyPayload() {
  const sel = $("#ytPrivacy").value;
  return {
    privacy: sel === "scheduled" ? "private" : sel,
    publish_at: sel === "scheduled" ? $("#ytPublishAt").value : "",
    title_index: Number($("#ytTitleIndex").value || 0),
  };
}

// ── 채널 전략 ────────────────────────────────────────────────────────────
let STRATEGY = null;

async function loadStrategy() {
  try {
    const d = await api("/api/strategy");
    if (d && d.cards && d.cards.length) { STRATEGY = d; renderStrategy(d); }
  } catch (e) { /* 무시 */ }
}

function renderStrategy(d) {
  const basis = { youtube: "내 유튜브 채널 데이터", local: "이 맥북의 제작 이력", benchmark: "시니어 사연 벤치마크", none: "—" }[d.basis] || d.basis;
  $("#strategyStatus").textContent = `분석 기준: ${basis} · ${d.generated_at || ""}${d.note ? " · " + d.note : ""}`;
  const analysis = d.analysis || {};
  const stats = analysis.count ? `최근 영상 ${analysis.count}개 · 평균 조회 ${analysis.avg_views}회 · 최고 시간 ${analysis.best_hour}시` : "";
  $("#strategyCards").innerHTML = (d.cards || []).map((c, i) => `
    <div class="strategy-card">
      <div class="strategy-head"><span class="tag">${esc(c.badge || "전략")}</span>
        <b>${esc(c.title)}</b></div>
      <ul>${(c.reason || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      <div class="strategy-foot">
        <span class="hint small">${esc(c.summary || "")}</span>
        <button class="btn primary small" data-card="${i}">✅ 승인하고 바로 진행</button>
      </div>
    </div>`).join("");
  $$("[data-card]").forEach((b) => b.addEventListener("click", () => executeStrategy(Number(b.dataset.card))));
  if (stats) $("#strategyStatus").textContent += ` · ${stats}`;
}

async function analyzeStrategy() {
  $("#btnStrategy").disabled = true;
  try {
    const { job } = await api("/api/strategy/analyze", { method: "POST" });
    watchJob(job, { onDone: (j) => {
      if (j.result?.cards) { STRATEGY = j.result; renderStrategy(j.result); }
    }});
  } catch (e) { toast(e.message, true); }
  finally { $("#btnStrategy").disabled = false; }
}

async function executeStrategy(i) {
  const card = (STRATEGY?.cards || [])[i];
  if (!card) return;
  const mode = document.querySelector("input[name=imageMode]:checked")?.value || "B";
  try {
    $("#detailPanel").hidden = true;
    const { job } = await api("/api/strategy/execute", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: card.action, image_mode: mode }),
    });
    watchJob(job, { onDone: async () => { await loadProjects(); await loadStrategy(); } });
    toast(card.action?.type === "weekend" ? "합본 제작을 시작합니다." : "제안대로 제작을 시작합니다.");
  } catch (e) { toast(e.message, true); }
}

// ── 폰 접속 ──────────────────────────────────────────────────────────────
async function loadRemote() {
  try {
    const r = await api("/api/remote");
    $("#remoteLan").value = r.lan_url || "";
    $("#remoteTs").value = r.tailscale_url || "";
    $("#remoteBadge").textContent = r.pin_set ? "비밀번호 켜짐" : "비밀번호 없음";
    $("#remoteBadge").className = "badge " + (r.pin_set ? "on" : "");
    $("#caffeinate").checked = !!r.caffeinate;
    $("#remoteQr").src = `/api/remote/qr.png?url=${encodeURIComponent(r.lan_url || "")}&t=${Date.now()}`;
  } catch (e) { /* 무시 */ }
}

async function savePin() {
  const pin = ($("#remotePin").value || "").replace(/[^0-9]/g, "").slice(0, 8);
  try {
    await api("/api/remote/pin", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }) });
    toast(pin ? "접속 비밀번호를 켰습니다." : "접속 비밀번호를 껐습니다.");
    await loadRemote();
  } catch (e) { toast(e.message, true); }
}

async function toggleCaffeinate() {
  try {
    const r = await api("/api/remote/caffeinate", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on: $("#caffeinate").checked }) });
    toast(r.message || "설정을 바꿨습니다.", !r.on && $("#caffeinate").checked);
  } catch (e) { toast(e.message, true); }
}

// ── 자동 스케줄 ──────────────────────────────────────────────────────────
async function loadSchedule() {
  try {
    const d = await api("/api/schedule");
    const s = d.settings || {};
    $("#schedAuto").checked = !!s.auto_daily;
    $("#schedTime").value = s.daily_time || "04:00";
    $("#schedPublish").value = s.daily_publish_time || "21:00";
    $("#schedGenre").value = s.daily_genre || "tear_family";
    $("#schedPreset").value = s.daily_preset || "full40";
    $("#schedMode").value = s.daily_image_mode || "B";
    $("#schedBadge").textContent = s.auto_daily ? "켜짐" : "꺼짐";
    $("#schedBadge").className = "badge " + (s.auto_daily ? "on" : "");
    $("#schedMsg").textContent = d.state?.last_run
      ? `마지막 자동 실행: ${d.state.last_run}${d.state.last_result?.note ? " · " + d.state.last_result.note : ""}`
      : "아직 자동 실행 기록이 없습니다.";
  } catch (e) { /* 무시 */ }
}

async function saveSchedule() {
  try {
    await api("/api/schedule", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        auto_daily: $("#schedAuto").checked, daily_time: $("#schedTime").value,
        daily_publish_time: $("#schedPublish").value, daily_genre: $("#schedGenre").value,
        daily_preset: $("#schedPreset").value, daily_image_mode: $("#schedMode").value,
      }) });
    toast("자동 스케줄을 저장했습니다.");
    await loadSchedule();
  } catch (e) { toast(e.message, true); }
}

async function runScheduleNow() {
  try {
    const { job } = await api("/api/schedule/run-now", { method: "POST" });
    watchJob(job, { onDone: async () => { await loadSchedule(); await loadProjects(); } });
  } catch (e) { toast(e.message, true); }
}

// ── 댓글 관리 ────────────────────────────────────────────────────────────
async function loadComments() {
  $("#commentList").innerHTML = `<p class="hint small">불러오는 중…</p>`;
  try {
    const d = await api("/api/comments");
    if (d.error) {
      $("#commentList").innerHTML = `<div class="warn">${esc(d.error)}<br>유튜브 채널을 다시 연동해 주세요(댓글 권한 포함).</div>`;
      return;
    }
    if (!d.items.length) {
      $("#commentList").innerHTML = `<p class="hint small">표시할 댓글이 없습니다.</p>`;
      return;
    }
    $("#commentList").innerHTML = d.items.map((c, i) => `
      <div class="comment">
        <div class="cmeta"><b>${esc(c.author)}</b> · ${esc((c.published_at || "").slice(0, 10))}
          ${c.video_url ? `· <a href="${esc(c.video_url)}" target="_blank">영상</a>` : ""}</div>
        <p class="ctext">${esc(c.text)}</p>
        <textarea id="reply${i}" rows="2" placeholder="답글을 쓰거나 [초안 만들기]를 누르세요"></textarea>
        <div class="row"><button class="btn ghost small" data-draft="${i}">초안 만들기</button>
          <button class="btn small" data-reply="${i}">답글 등록</button></div>
      </div>`).join("");
    $$("[data-draft]").forEach((b) => b.addEventListener("click", async () => {
      const i = Number(b.dataset.draft), c = d.items[i];
      b.disabled = true;
      try {
        const r = await api("/api/comments/draft", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: c.text, video_title: "" }) });
        $(`#reply${i}`).value = r.draft || "";
      } catch (e) { toast(e.message, true); }
      finally { b.disabled = false; }
    }));
    $$("[data-reply]").forEach((b) => b.addEventListener("click", async () => {
      const i = Number(b.dataset.reply), c = d.items[i];
      const text = $(`#reply${i}`).value.trim();
      if (!text) return toast("답글을 입력해 주세요.", true);
      b.disabled = true;
      try {
        await api("/api/comments/reply", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ comment_id: c.comment_id, text }) });
        toast("답글을 등록했습니다.");
        await loadComments();
      } catch (e) { toast(e.message, true); }
      finally { b.disabled = false; }
    }));
  } catch (e) {
    $("#commentList").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
  }
}

// ── 50초 쇼츠 ────────────────────────────────────────────────────────────
async function makeShorts(id) {
  try {
    const { job } = await api(`/api/projects/${id}/shorts`, { method: "POST" });
    watchJob(job, { onDone: async () => { await loadProjects(); await openProject(id); } });
    toast("가장 임팩트 있는 50초 구간을 뽑고 있습니다.");
  } catch (e) { toast(e.message, true); }
}

// ── 케빈에게 이미지 요청 (깃허브) ────────────────────────────────
let GH = { repo: "", has_token: false };

async function loadGhStatus() {
  try {
    const d = await api("/api/github/status");
    GH = d;
    const badge = $("#ghBadge");
    badge.textContent = d.has_token ? "토큰 저장됨 · 자동 등록" : "토큰 없음 · 1클릭 등록";
    badge.className = "badge " + (d.has_token ? "on" : "");
    $("#ghMsg").textContent = `저장소 ${d.repo} · 라벨 ${d.label}`
      + (d.token_masked ? ` · 저장된 토큰 ${d.token_masked}` : " · 토큰은 선택입니다");
  } catch (e) { /* 무시 */ }
}

async function saveGhToken() {
  const v = $("#ghToken").value.trim();
  if (!v) return toast("토큰을 입력해 주세요. (토큰 없이도 1클릭 등록으로 보낼 수 있습니다)", true);
  try {
    await api("/api/config", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ github_token: v }),
    });
    $("#ghToken").value = "";
    toast("깃허브 토큰을 저장했습니다. 이제 버튼 한 번에 이슈가 등록됩니다.");
    await loadGhStatus();
  } catch (e) { toast(e.message, true); }
}

async function testGhToken() {
  $("#btnGhTest").disabled = true;
  try {
    const r = await api("/api/github/test", { method: "POST" });
    if (r.ok) toast(`${r.login || "연결"} · ${r.repo} 확인 (${r.can_push ? "이슈 등록 가능" : "권한 부족"})`);
    else toast(r.error || "연결하지 못했습니다.", true);
  } catch (e) { toast(e.message, true); }
  finally { $("#btnGhTest").disabled = false; }
}

async function requestKevinsImages(id) {
  // 팝업 차단을 피하려고 클릭 시점에 빈 창을 먼저 열어 둔다
  let win = null;
  try { win = window.open("", "_blank"); } catch (e) { win = null; }
  const btn = $("#btnGhRequest");
  if (btn) { btn.disabled = true; btn.textContent = "요청 보내는 중…"; }
  const open = (url) => {
    if (win && !win.closed) win.location.href = url;
    else window.open(url, "_blank");
  };
  try {
    const r = await api(`/api/projects/${id}/github-request`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "auto" }),
    });
    open(r.url);
    if (r.fallback_error) toast("토큰 등록 실패 — 1클릭 등록 화면으로 넘어갑니다: " + r.fallback_error, true);
    if (r.mode === "api") {
      toast(`깃허브 이미지 요청 이슈 #${r.number} 등록 완료 · 케빈이 5분 이내에 자동 감지해서 이미지를 보내드립니다.`);
      return;
    }
    const copied = r.copy_body ? await copyText(r.body, true) : false;
    if (r.prefill === "none") {
      toast(copied
        ? "깃허브 새 이슈 화면을 열었습니다. 본문 칸에서 ⌘V로 붙여넣고 [Create issue]를 누르세요."
        : "깃허브 새 이슈 화면을 열었습니다. [요청서 보기]의 내용을 붙여넣고 [Create issue]를 누르세요.", true);
    } else {
      toast("깃허브 새 이슈 화면이 열렸습니다. [Create issue]만 누르면 케빈에게 전달됩니다."
        + (copied ? " (요청서 전문은 클립보드에 복사해 두었습니다)" : ""));
    }
  } catch (e) {
    if (win && !win.closed) win.close();
    toast(e.message, true);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "📤 케빈에게 이미지 요청하기"; }
  }
}

// ── 자동 이미지 수신 ────────────────────────────────────────────────
let INBOX_SEQ = null;

async function loadAutoInbox() {
  try {
    const d = await api("/api/inbox/auto");
    const on = !!d.enabled;
    const btn = $("#btnAutoInbox");
    btn.classList.toggle("recv-on", on);
    btn.classList.toggle("recv-off", !on);
    $("#autoInboxState").textContent = on ? "ON" : "OFF";
    const last = d.last_check ? d.last_check.slice(11, 19) : "—";
    $("#autoInboxMsg").textContent = on
      ? `${d.is_git ? "깃허브 확인 중" : "깃허브 저장소 아님"} · 마지막 ${last}`
      : "자동 수신 꺼짐";
    $("#autoInboxDetail").textContent = d.is_git
      ? `20초마다 확인합니다 · 마지막 확인 ${d.last_check || "아직"} · ${d.last_message || "대기 중"}`
      : "이 폴더는 git 저장소가 아닙니다. README 의 [설치]처럼 git clone 으로 받으면 20초 자동 수신이 켜집니다.";
    $("#autoAssemble").checked = !!d.auto_assemble;
    const badge = $("#inboxAutoBadge");
    badge.textContent = on ? "자동 수신 ON" : "자동 수신 OFF";
    badge.className = "badge " + (on ? "on" : "");
    renderInboxEvents(d.events || []);
    if (INBOX_SEQ !== null && d.seq > INBOX_SEQ && (d.events || []).length) {
      const e = d.events[d.events.length - 1];
      toast(`🎉 케빈이 올린 이미지 자동 수신 완료! (${e.count}장 · 남은 ${e.missing}장)`);
      await loadProjects();
      if (CURRENT && CURRENT.id === e.project_id) await openProject(e.project_id);
    }
    INBOX_SEQ = d.seq;
  } catch (e) { /* 무시 */ }
}

function renderInboxEvents(events) {
  const box = $("#inboxEvents");
  if (!box) return;
  if (!events.length) { box.innerHTML = ""; return; }
  box.innerHTML = events.slice().reverse().slice(0, 6).map((e) => `
    <div class="inbox-event"><b>${esc(e.message || "이미지 도착")}</b>
      <div>${esc(e.project_id)} · ${esc(e.folder || "기본 폴더")} · ${e.count}장 · 남은 ${e.missing}장 · ${esc(e.time)}</div>
    </div>`).join("");
}

async function toggleAutoInbox() {
  const turnOn = $("#autoInboxState").textContent !== "ON";
  try {
    await api("/api/inbox/auto", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: turnOn }),
    });
    toast(turnOn ? "자동 이미지 수신을 켰습니다. 20초마다 확인합니다." : "자동 이미지 수신을 껐습니다.");
    await loadAutoInbox();
  } catch (e) { toast(e.message, true); }
}

async function saveAutoAssemble() {
  try {
    await api("/api/inbox/auto", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ auto_assemble: $("#autoAssemble").checked }),
    });
    toast($("#autoAssemble").checked ? "이미지가 다 모이면 자동으로 조립합니다." : "자동 조립을 껐습니다.");
  } catch (e) { toast(e.message, true); }
}

async function checkInboxNow() {
  try {
    const { job } = await api("/api/inbox/check", { method: "POST" });
    watchJob(job, { quiet: true, onDone: async (j) => {
      const r = j.result || {};
      $("#updateMsg").textContent = r.message || "확인 완료";
      await loadAutoInbox();
      await loadInbox();
      await loadProjects();
      if (CURRENT) await openProject(CURRENT.id);
    }});
  } catch (e) { toast(e.message, true); }
}

// ── 업데이트 · 이미지 인박스 ─────────────────────────────────────────────
async function updatePull() {
  $("#updateMsg").textContent = "최신 버전 확인 중…";
  try {
    const { job } = await api("/api/update/pull", { method: "POST" });
    watchJob(job, { onDone: async (j) => {
      $("#updateMsg").textContent = j.result?.message || "완료";
      await loadInbox();
    }});
  } catch (e) { $("#updateMsg").textContent = e.message; }
}

async function loadInbox() {
  try {
    const d = await api("/api/inbox");
    if (!d.folders?.length) {
      $("#inboxList").innerHTML = `<p class="hint small">받아온 이미지 묶음이 없습니다. (케빈이 깃허브 assets_inbox 에 올리면 여기에 나타납니다)</p>`;
      return;
    }
    $("#inboxList").innerHTML = d.folders.map((f, i) => `
      <div class="inbox-row">
        <b>${esc(f.folder || "기본 폴더")}</b>
        <span class="hint small">이미지 ${f.count}장</span>
        <button class="btn small" data-inbox="${i}">📥 프로젝트에 가져오기</button>
      </div>`).join("");
    $$("[data-inbox]").forEach((b) => b.addEventListener("click", async () => {
      if (!CURRENT) return toast("먼저 [내 사연들]에서 이미지를 넣을 사연을 열어 주세요.", true);
      const f = d.folders[Number(b.dataset.inbox)];
      try {
        const r = await api("/api/inbox/import", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_id: CURRENT.id, folder: f.folder }) });
        toast(`${r.saved.length}장을 가져왔습니다. 남은 이미지 ${r.missing.length}장.`);
        await openProject(CURRENT.id);
      } catch (e) { toast(e.message, true); }
    }));
  } catch (e) { /* 무시 */ }
}

async function loadYtStatus() {
  try {
    const st = await api("/api/youtube/status");
    const badge = $("#ytBadge");
    if (st.connected) {
      badge.textContent = "채널 연결됨";
      badge.className = "badge on";
      const c = st.channel || {};
      $("#ytChannel").textContent = `${c.title || "채널"}${c.handle ? " " + c.handle : ""}`;
      $("#ytChannel").className = "chip ok";
    } else if (st.has_client) {
      badge.textContent = "파일만 있음";
      badge.className = "badge";
      $("#ytChannel").textContent = "연동 필요";
      $("#ytChannel").className = "chip";
    } else {
      badge.textContent = "미설정";
      badge.className = "badge";
      $("#ytChannel").textContent = "연결 안 됨";
      $("#ytChannel").className = "chip";
    }
    $("#ytSecretMsg").textContent = st.has_client
      ? "client_secret.json 이 저장되어 있습니다."
      : "아직 올리지 않았습니다.";
  } catch (e) { /* 무시 */ }
}

async function uploadSecret() {
  const f = $("#ytSecret").files[0];
  if (!f) return toast("client_secret.json 파일을 선택해 주세요.", true);
  const fd = new FormData();
  fd.append("file", f);
  try {
    await api("/api/youtube/client-secret", { method: "POST", body: fd });
    toast("OAuth 파일을 저장했습니다. 이제 [채널 연동]을 눌러 주세요.");
    await loadYtStatus();
  } catch (e) { toast(e.message, true); }
}

async function connectYoutube() {
  try {
    const { job } = await api("/api/youtube/connect", { method: "POST" });
    watchJob(job, { onDone: loadYtStatus });
    toast("브라우저 창에서 구글 로그인을 마쳐 주세요.");
  } catch (e) { toast(e.message, true); }
}

async function disconnectYoutube() {
  try {
    await api("/api/youtube/disconnect", { method: "POST" });
    toast("연동을 해제했습니다.");
    await loadYtStatus();
  } catch (e) { toast(e.message, true); }
}

async function saveYtSettings() {
  const p = ytPrivacyPayload();
  try {
    await api("/api/youtube/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ privacy: p.privacy, publish_at: p.publish_at,
        title_index: p.title_index, auto_upload: $("#ytAuto").checked }),
    });
    toast("업로드 설정을 저장했습니다.");
    saveLocal();
  } catch (e) { toast(e.message, true); }
}

async function uploadToYoutube(id) {
  if (!$("#ytChannel").className.includes("ok")) return toast("먼저 유튜브 채널을 연동해 주세요.", true);
  const p = ytPrivacyPayload();
  const idx = Number($("#projYtTitle")?.value || p.title_index || 0);
  try {
    $("#detailPanel").hidden = true;
    const { job } = await api(`/api/projects/${id}/youtube/upload`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title_index: idx, privacy: p.privacy, publish_at: p.publish_at }),
    });
    watchJob(job);
  } catch (e) { toast(e.message, true); }
}

async function copyText(text, silent = false) {
  if (!text) {
    if (!silent) toast("복사할 내용이 없습니다.", true);
    return false;
  }
  try {
    await navigator.clipboard.writeText(text);
    if (!silent) toast("복사했습니다. 유튜브에 붙여넣으세요.");
    return true;
  } catch (e) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      if (!silent) toast(ok ? "복사했습니다." : "복사하지 못했습니다. 요청서에서 직접 복사해 주세요.", !ok);
      return ok;
    } catch (e2) {
      if (!silent) toast("복사하지 못했습니다. 요청서에서 직접 복사해 주세요.", true);
      return false;
    }
  }
}

async function uploadImages(id, files) {
  if (!files || !files.length) return;
  const fd = new FormData();
  Array.from(files).forEach((f) => fd.append("files", f));
  toast("이미지 올리는 중…");
  try {
    const r = await api(`/api/projects/${id}/images`, { method: "POST", body: fd });
    if (r.saved?.length) toast(`${r.saved.length}장을 넣었습니다. 남은 이미지 ${r.missing.length}장.`);
    else toast("이름이 맞는 이미지가 없습니다. s01.png 형식으로 넣어 주세요.", true);
    await openProject(id);
    await loadProjects();
  } catch (e) { toast(e.message, true); }
}

async function assemble(id) {
  try {
    const { job } = await api(`/api/projects/${id}/assemble`, { method: "POST" });
    $("#detailPanel").hidden = true;
    watchJob(job);
  } catch (e) { toast(e.message, true); }
}

async function regenThumb(id) {
  const body = {
    style1: [$("#th1a").value, $("#th1b").value],
    style2: [0, 1, 2, 3, 4].map((i) => $(`#th2${i}`).value),
  };
  toast("썸네일 다시 만드는 중…");
  try {
    await api(`/api/projects/${id}/thumbnail`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    toast("썸네일 2종을 다시 만들었습니다.");
    await openProject(id);
    await loadProjects();
  } catch (e) { toast(e.message, true); }
}

// ── 주말 합본 ────────────────────────────────────────────────────────────
async function loadWeekendOptions() {
  const list = await api("/api/projects");
  const done = list.filter((p) => p.outputs?.video && p.status?.stage === "done");
  const box = $("#weekendProjects");
  if (!done.length) {
    box.innerHTML = `<p class="hint small">완성된 사연이 아직 없습니다.</p>`;
    return;
  }
  const checked = new Set(Array.from(box.querySelectorAll("input:checked")).map((x) => x.value));
  box.innerHTML = done.map((p) => `<label><input type="checkbox" value="${p.id}" ${checked.has(p.id) ? "checked" : ""}>
    ${esc(p.title)} <span class="hint small">(${esc(p.format || "")})</span></label>`).join("");
}

async function compile() {
  const ids = Array.from($("#weekendProjects").querySelectorAll("input:checked")).map((x) => x.value);
  if (ids.length < 2) return toast("완성된 사연을 2개 이상 골라 주세요.", true);
  try {
    const { job } = await api("/api/compile", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_ids: ids, title: $("#weekendTitle").value.trim() }),
    });
    watchJob(job, { onDone: async () => { await loadProjects(); } });
  } catch (e) { toast(e.message, true); }
}

function showCompileResult(r) {
  $("#jobResult").innerHTML = `<a href="/api/projects/${r.id}/file/video" target="_blank">합본 영상 열기 <span>${mmss(r.duration)}</span></a>`;
}

function bind() {
  $("#btnSaveKey").addEventListener("click", saveKey);
  $("#btnStrategy").addEventListener("click", analyzeStrategy);
  $("#btnPinSave").addEventListener("click", savePin);
  $("#caffeinate").addEventListener("change", toggleCaffeinate);
  $("#btnSchedSave").addEventListener("click", saveSchedule);
  $("#btnSchedNow").addEventListener("click", runScheduleNow);
  $("#btnComments").addEventListener("click", loadComments);
  $("#btnUpdate").addEventListener("click", updatePull);
  $("#btnInboxCheck").addEventListener("click", checkInboxNow);
  $("#btnAutoInbox").addEventListener("click", toggleAutoInbox);
  $("#autoAssemble").addEventListener("change", saveAutoAssemble);
  $("#btnGhSave").addEventListener("click", saveGhToken);
  $("#btnGhTest").addEventListener("click", testGhToken);
  $("#btnYtSecret").addEventListener("click", uploadSecret);
  $("#btnYtConnect").addEventListener("click", connectYoutube);
  $("#btnYtDisconnect").addEventListener("click", disconnectYoutube);
  $("#btnYtSave").addEventListener("click", saveYtSettings);
  $("#ytPrivacy").addEventListener("change", () => {
    $("#ytPublishAt").disabled = $("#ytPrivacy").value !== "scheduled";
  });
  $("#btnTestKey").addEventListener("click", testKey);
  $("#btnCreate").addEventListener("click", createProject);
  $("#btnRefresh").addEventListener("click", loadProjects);
  $("#btnCompile").addEventListener("click", compile);
  $("#rate").addEventListener("input", () => { $("#rateOut").textContent = $("#rate").value + "%"; saveLocal(); });
  $("#btnAvatarFile").addEventListener("click", () => $("#avatarFile").click());
  $("#avatarFile").addEventListener("change", () => {
    if ($("#avatarFile").files.length) {
      $("#avatarKind").value = "custom";
      toast("내 사진은 조립할 때 반영됩니다. (이미지는 프로젝트 폴더에 저장)");
    }
  });
  $$("input[name=imageMode]").forEach((r) => r.addEventListener("change", () => { onPresetChange(); saveLocal(); }));
  ["topic", "hook15", "sequel", "teaserMode", "teaserText", "voiceMode", "avatar", "avatarKind",
   "likeVoice", "likeBanner", "outroCta", "endScreen", "sleepRain", "likeVoiceText", "ctaText"].forEach((id) => {
    const el = $("#" + id);
    el?.addEventListener("change", saveLocal);
    el?.addEventListener("input", () => { if (id === "teaserText") toggleTeaserBox(); });
  });
  $$("input[name=subSize]").forEach((r) => r.addEventListener("change", saveLocal));
  $("#teaserMode").addEventListener("change", () => { toggleTeaserBox(); saveLocal(); });
  toggleTeaserBox();
  setInterval(loadHealth, 30000);
}

function toggleTeaserBox() {
  const manual = $("#teaserMode").value === "manual";
  $("#teaserText").disabled = !manual;
  $("#teaserText").style.opacity = manual ? "1" : ".55";
}

document.addEventListener("DOMContentLoaded", init);
