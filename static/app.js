/* 세월의 사연극장 스튜디오 v2.0.0 — 4단계 위자드 */
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const mmss = (s) => {
  s = Math.max(0, Math.round(s || 0));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};
const kstClock = (iso) => {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const p2 = (x) => String(x).padStart(2, "0");
    return `${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`;
  } catch (e) { return String(iso).slice(5, 16).replace("T", " "); }
};

let META = null;
let CURRENT = null;          // 지금 열어 둔 사연(전체)
let STEP = 1;                // 1~4
let POLL = null;             // 작업(job) 폴링
let STUDIO_TIMER = null;
let GALLERY_TIMER = null;
let KEVIN_TIMER = null;
let GALLERY_SIG = "";        // 이미지 지문(같으면 DOM 을 다시 그리지 않아 깜빡임 0)
let GALLERY_ROWS = [];
let DETAIL_SIG = "";
let RESTART_WAIT = false;
let LB_IDX = 0;
let SCRIPT_MODE = "";        // "" | "read" | "edit"
let SCRIPT_DIRTY = false;    // 저장하지 않은 대본 수정
let IDEAS = [];
let RENDER_STAGES = { "성우": 0, "BGM": 0, "자막": 0, "인코딩": 0 };
let INBOX_SEQ = null;
let JOB = { kind: "", id: null };   // 지금 도는 작업 (2·3단계 진행 문구 보호)

const STORE = "sewol.studio.settings.v2";
const LAST_PROJECT = "sewol.studio.lastProject.v2";
const STEP_KEY = "sewol.studio.step.v2";
const DEFAULTS = {
  genre: "tear_family", preset: "short50", hook15: true, sequel: true, teaserMode: "auto_sequel",
  teaserText: "", voiceMode: "multi", tone: "warm", rate: 0, avatar: true, avatarKind: "auto", liveBadge: true,
  subSize: "senior", imageMode: "B", likeVoice: true, likeBanner: true, outroCta: true,
  endScreen: true, sleepRain: false, topic: "", likeVoiceText: "", ctaText: "",
};

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
const SPEAKER_LABEL = { narrator: "해설", old_male: "노인", old_female: "할머니", female: "여성", young_male: "청년", child: "아이" };
const EMOTION_LABEL = { conflict: "갈등", twist: "반전", heal: "치유" };
const PLACEMENT_LABEL = { after_hook: "되감기 카드", teaser: "후속편 예고", mid: "좋아요 멘트", end: "구독·지역 인사" };
const STEP_TITLES = { 1: "1단계 · 대본 설계·검토", 2: "2단계 · 이미지·음성 검토", 3: "3단계 · 영상 렌더링", 4: "4단계 · 최종 확인·업로드" };

function toast(msg, bad = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (bad ? " bad" : "");
  t.hidden = false;
  clearTimeout(t._t);
  t._t = setTimeout(() => (t.hidden = true), 4400);
}

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  const text = await r.text();
  let data = {};
  try { data = JSON.parse(text); } catch (e) { data = { raw: text }; }
  if (!r.ok) throw new Error(data.detail || data.error || data.message || `HTTP ${r.status}`);
  return data;
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
      if (!silent) toast(ok ? "복사했습니다." : "복사하지 못했습니다.", !ok);
      return ok;
    } catch (e2) {
      if (!silent) toast("복사하지 못했습니다.", true);
      return false;
    }
  }
}

function growTextarea(el) {
  if (!el || el.tagName !== "TEXTAREA") return;
  el.style.height = "auto";
  el.style.height = Math.min(320, el.scrollHeight + 4) + "px";
}

// ── 4단계 스텝 ────────────────────────────────────────────────────────────
function setStep(n, opts = {}) {
  n = Math.max(1, Math.min(4, Number(n) || 1));
  if (n > 1 && !CURRENT && !opts.force) {
    toast("먼저 1단계에서 대본을 만들어 주세요.", true);
    n = 1;
  }
  STEP = n;
  $$(".panel").forEach((el) => { el.hidden = Number(el.dataset.step) !== n; });
  $$("#stepBar .stepbtn").forEach((el) => {
    const k = Number(el.dataset.step);
    el.classList.toggle("active", k === n);
    el.classList.toggle("done", k < n && (!!CURRENT || k === 1));
  });
  try { localStorage.setItem(STEP_KEY, String(n)); } catch (e) {}
  const foot = { 1: "#step1Foot", 2: "#step2Foot", 3: "#step3Foot", 4: "#step4Foot" }[n];
  $("#runTitle").textContent = CURRENT ? `${STEP_TITLES[n]} · ${CURRENT.title || ""}` : STEP_TITLES[n];
  if (n === 2) renderStep2();
  if (n === 3) renderStep3();
  if (n === 4) renderStep4();
  if (foot && CURRENT === null && n > 1) $(foot) && ($(foot).textContent = "먼저 1단계에서 대본을 만들어 주세요.");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function currentStepFor(p) {
  if (!p) return 1;
  if (p.outputs && p.outputs.video) return 4;
  const stage = (p.status || {}).stage || "";
  if (stage === "done") return 4;
  if (stage === "render" || stage === "audio" || stage === "timeline") return 3;
  if (stage === "tts" || stage === "images" || (p.receive_log || []).length) return 2;
  return 1;
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
  await loadSchedule();
  await loadRemote();
  await loadInbox();
  await loadAutoInbox();
  setInterval(() => loadAutoInbox(), 10000);
  setInterval(loadHealth, 30000);
  let last = null;
  try { last = localStorage.getItem(LAST_PROJECT); } catch (e) {}
  if (last) {
    try { await openProject(last, { keepStep: true }); } catch (e) { /* 지워졌을 수 있음 */ }
  }
  let saved = 1;
  try { saved = Number(localStorage.getItem(STEP_KEY) || 1); } catch (e) {}
  setStep(saved || 1, { force: true });
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
  if ($("#btnCreate")) {
    $("#btnCreate").disabled = isWeekend;
    $("#btnCreate").textContent = isWeekend
      ? "아래 [합본 만들기]를 사용하세요"
      : (document.querySelector("input[name=imageMode]:checked")?.value === "A"
        ? "완전자동 제작 시작 (모드 A)" : "대본 만들기");
  }
  if (isWeekend) loadWeekendOptions();
}

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
  if (m.version && $("#verTag")) $("#verTag").textContent = "v" + m.version;
  applyTtsConfig(conf);
  applyScriptConfig(conf);
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

// ── 설정 저장/복구 ───────────────────────────────────────────────────────
function saveLocal() {
  try { localStorage.setItem(STORE, JSON.stringify(collect())); } catch (e) {}
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
    $("#storyTone").value = d.tone || "warm";
    $("#rate").value = d.rate ?? 0;
    $("#rateOut").textContent = ($("#rate").value || 0) + "%";
    $("#avatar").checked = d.avatar !== false;
    $("#avatarKind").value = d.avatarKind || "auto";
    $("#liveBadge").checked = d.liveBadge !== false;
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
    if (d.genre) {
      const g = document.querySelector(`#genreGrid label[data-genre="${d.genre}"]`);
      if (g) { $$("#genreGrid label").forEach((x) => x.classList.remove("on")); g.classList.add("on"); }
    }
    if (d.preset) {
      const p = document.querySelector(`#presetGrid label[data-preset="${d.preset}"]`);
      if (p) { $$("#presetGrid label").forEach((x) => x.classList.remove("on")); p.classList.add("on"); }
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
    tone: $("#storyTone").value,
    rate: Number($("#rate").value || 0),
    avatar: $("#avatar").checked,
    avatar_kind: $("#avatarKind").value,
    live_badge: $("#liveBadge").checked,
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

function toggleTeaserBox() {
  const manual = $("#teaserMode").value === "manual";
  $("#teaserText").disabled = !manual;
  $("#teaserText").style.opacity = manual ? "1" : ".55";
}

// ── API 키 · 대본 엔진 · 음성 엔진 ──────────────────────────────────────
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
    applyScriptConfig(conf);
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

function applyTtsConfig(conf) {
  conf = conf || {};
  const engine = conf.tts_engine === "openai" ? "openai" : "edge";
  if ($("#ttsEngine")) $("#ttsEngine").value = engine;
  if ($("#openaiModel")) $("#openaiModel").value = conf.openai_tts_model || "gpt-4o-mini-tts";
  if ($("#ttsFallback")) $("#ttsFallback").checked = conf.openai_fallback_edge !== false;
  const badge = $("#ttsBadge");
  if (badge) {
    badge.textContent = engine === "openai"
      ? (conf.has_openai_key ? "OpenAI 감성 TTS · 키 저장됨" : "OpenAI 감성 TTS · 키 없음")
      : "무료 edge-tts";
    badge.className = "badge " + (engine === "openai" && conf.has_openai_key ? "on" : "");
  }
  const msg = $("#ttsKeyMsg");
  if (msg && conf.has_openai_key && conf.openai_key_masked) {
    msg.innerHTML = `저장된 OpenAI 키: ${esc(conf.openai_key_masked)} · 모델 ${esc(conf.openai_tts_model || "")}`
      + ` · <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener">platform.openai.com/api-keys</a> 에서 새 키 발급`;
  }
}

async function saveTts(silent = false) {
  const body = {
    tts_engine: $("#ttsEngine").value,
    openai_tts_model: $("#openaiModel").value,
    openai_fallback_edge: $("#ttsFallback").checked,
  };
  const key = $("#openaiKey").value.trim();
  if (key) body.openai_api_key = key;
  try {
    const conf = await api("/api/config", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    $("#openaiKey").value = "";
    applyTtsConfig(conf);
    applyScriptConfig(conf);
    if (silent) return;
    if (conf.tts_engine === "openai" && !conf.has_openai_key) {
      toast("저장했습니다. OpenAI API 키를 넣어야 감성 TTS 로 제작됩니다.", true);
    } else if (conf.tts_engine === "openai") {
      toast("OpenAI 감성 TTS 로 저장했습니다.");
    } else {
      toast("무료 edge-tts 로 저장했습니다.");
    }
  } catch (e) { toast(e.message, true); }
}

async function testTts() {
  const btn = $("#btnTtsTest");
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = "확인 중…";
  $("#ttsPreview").textContent = "OpenAI 에 짧은 한국어 문장을 보내 목소리를 만드는 중입니다 (3~10초)…";
  try {
    const r = await api("/api/config/test", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ engine: "openai_tts" }),
    });
    if (r.ok) {
      $("#ttsPreview").innerHTML = `✅ ${esc(r.message)}`
        + (r.preview_url ? ` · <a href="${esc(r.preview_url)}" target="_blank" rel="noopener">🔊 미리듣기</a>` : "");
      toast("OpenAI 감성 TTS 연결 성공");
    } else {
      $("#ttsPreview").innerHTML = `❌ ${esc(r.error || "연결하지 못했습니다.")}`;
      toast("연결 실패: " + (r.error || ""), true);
    }
  } catch (e) {
    $("#ttsPreview").textContent = "연결 실패 — " + e.message;
    toast(e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
}

const SCRIPT_ENGINE_LABEL = { auto: "자동", gemini: "Gemini 단독", openai: "OpenAI 단독" };

function applyScriptConfig(conf) {
  conf = conf || {};
  const mode = ["auto", "gemini", "openai"].includes(conf.script_engine) ? conf.script_engine : "auto";
  if ($("#scriptEngine")) $("#scriptEngine").value = mode;
  const hasG = !!conf.has_key;
  const hasO = !!conf.has_openai_key;
  const badge = $("#scriptEngineBadge");
  if (badge) {
    const keys = hasG && hasO ? "키 2개" : (hasG || hasO ? "키 1개" : "키 없음");
    badge.textContent = `${SCRIPT_ENGINE_LABEL[mode]} · ${keys}`;
    badge.className = "badge " + (hasG || hasO ? "on" : "");
  }
  const state = $("#scriptEngineState");
  if (state) {
    const parts = [];
    if (mode === "auto") {
      parts.push(hasG ? "Gemini 로 먼저 만들고, 실패하면 OpenAI 로 이어서" :
        (hasO ? "Gemini 키가 없어 OpenAI 로 만듭니다" : "Gemini·OpenAI 키가 모두 없어 예시 대본으로 만듭니다"));
    } else if (mode === "gemini") {
      parts.push(hasG ? "Gemini 단독" : "Gemini 키가 없어 예시 대본으로 만듭니다");
    } else {
      parts.push(hasO ? `OpenAI ${conf.openai_script_model || "gpt-4o-mini"} 단독` : "OpenAI 키가 없어 예시 대본으로 만듭니다");
    }
    if (mode === "auto" && hasO) parts.push(`보조: OpenAI ${conf.openai_script_model || "gpt-4o-mini"}`);
    state.textContent = parts.join(" · ");
  }
}

async function saveScriptEngine() {
  try {
    const conf = await api("/api/config", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ script_engine: $("#scriptEngine").value }),
    });
    applyScriptConfig(conf);
    toast(`대본 엔진: ${SCRIPT_ENGINE_LABEL[conf.script_engine] || conf.script_engine} 로 저장했습니다.`);
  } catch (e) { toast(e.message, true); }
}

function scriptTag(p) {
  const src = String(p?.script_engine || p?.source || "").toLowerCase();
  if (src === "openai") return "AI 대본 (OpenAI)";
  if (src === "gemini") return "AI 대본 (Gemini)";
  if (src === "template") return "예시 대본";
  return p?.script_engine_tag || "대본";
}

// ── 1단계: 시나리오 추천 ────────────────────────────────────────────────
async function suggestIdeas() {
  const btn = $("#btnIdeas");
  btn.disabled = true;
  btn.textContent = "추천 받는 중…";
  $("#ideaMsg").textContent = "AI가 이 장르에 맞는 주제·훅을 고르는 중입니다…";
  try {
    const r = await api("/api/scenario/suggest", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        genre: document.querySelector(".genre-grid label.on")?.dataset.genre || "tear_family",
        preset: document.querySelector(".preset-grid label.on")?.dataset.preset || "short50",
        count: 5,
      }),
    });
    IDEAS = r.ideas || [];
    renderIdeas();
    $("#ideaMsg").textContent = r.message || "";
  } catch (e) {
    $("#ideaMsg").textContent = "추천 실패 — " + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "✨ 시나리오 추천받기";
  }
}

function renderIdeas() {
  const box = $("#ideaList");
  if (!box) return;
  if (!IDEAS.length) { box.hidden = true; box.innerHTML = ""; return; }
  box.hidden = false;
  box.innerHTML = IDEAS.map((it, i) => `
    <button type="button" class="idea" data-idea="${i}">
      <b>${esc(it.topic)}</b>
      <span class="idea-hook">${esc(it.hook || "")}</span>
      ${it.why ? `<span class="idea-why">${esc(it.why)}</span>` : ""}
    </button>`).join("");
  $$("[data-idea]").forEach((b) => b.addEventListener("click", () => {
    const it = IDEAS[Number(b.dataset.idea)];
    if (!it) return;
    $("#topic").value = it.topic + (it.hook ? ` — ${it.hook}` : "");
    saveLocal();
    $$("[data-idea]").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    toast("주제를 넣었습니다. [대본 만들기]를 눌러 주세요.");
  }));
}

// ── 1단계: 대본 만들기 ─────────────────────────────────────────────────
async function createProject() {
  const payload = collect();
  if (payload.preset === "weekend") return toast("주말 합본은 오른쪽 [합본 만들기]를 눌러 주세요.", true);
  payload.auto_assemble = false;         // 4단계 위자드에서는 단계별로 진행한다
  $("#btnCreate").disabled = true;
  $("#btnCreate").textContent = "대본 만드는 중…";
  try {
    const { job } = await api("/api/projects", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    watchJob(job, { quiet: true, onDone: async (j) => {
      const p = j.result?.project;
      if (p?.id) {
        await loadProjects();
        await openProject(p.id, { keepStep: true });
        setStep(1, { force: true });
        $("#scriptBox").scrollIntoView({ behavior: "smooth", block: "start" });
        openScriptRead(p.id);
        const pi = j.result?.project;
        if (pi?.warnings?.length) toast(pi.warnings[pi.warnings.length - 1], true);
        else toast("대본을 만들었습니다. 아래에서 확인·수정하세요.");
      }
    }});
  } catch (e) {
    toast(e.message, true);
  } finally {
    $("#btnCreate").disabled = false;
    onPresetChange();
  }
}

// ── 작업(job) 진행 ───────────────────────────────────────────────────────
function watchJob(jobId, opts = {}) {
  if (POLL) clearInterval(POLL);
  JOB = { kind: opts.kind || "", id: jobId };
  let lastLogLen = 0;
  const tick = async () => {
    let j;
    try { j = await api(`/api/jobs/${jobId}`); }
    catch (e) {
      clearInterval(POLL); POLL = null;
      if (RESTART_WAIT) { waitForServerAndReload(); return; }
      toast(e.message, true); return;
    }
    if (opts.onProgress) opts.onProgress(j);
    if (j.stages) updateStageBars(j.stages);
    if (j.kind === "render") {
      $("#renderBar").style.width = `${j.percent || 0}%`;
      $("#renderMsg").textContent = `${j.percent || 0}% · ${j.message || ""}`;
      const log = (j.log || []).slice(-12).join("\n");
      if (log !== $("#renderLog").textContent) {
        $("#renderLog").textContent = log;
        $("#renderLog").scrollTop = $("#renderLog").scrollHeight;
      }
    }
    if (j.kind === "tts") {
      $("#ttsBar").style.width = `${j.percent || 0}%`;
      $("#ttsMsg").textContent = `${j.percent || 0}% · ${j.message || ""}`;
      $("#tlVoice").textContent = `${j.percent || 0}% · ${j.message || ""}`;
    }
    if (j.status === "done") {
      clearInterval(POLL); POLL = null;
      JOB = { kind: "", id: null };
      RESTART_WAIT = false;
      if (j.kind === "youtube_connect") {
        toast(j.result?.channel?.title ? `채널 연동 완료 — ${j.result.channel.title}` : "채널 연동 완료");
        await loadYtStatus();
      } else if (j.kind === "youtube_upload") {
        const y = j.result || {};
        $("#publishMsg").innerHTML = y.url
          ? `<a href="${esc(y.url)}" target="_blank">유튜브 영상 열기</a> · ${esc(y.privacy || "")}`
          : "업로드 요청을 마쳤습니다.";
        toast("유튜브 업로드가 끝났습니다.");
        if (j.result?.project_id) await openProject(j.result.project_id, { keepStep: true });
      } else if (j.kind === "render") {
        toast("렌더링이 끝났습니다. 4단계에서 감수하세요.");
        RENDER_STAGES = { "성우": 100, "BGM": 100, "자막": 100, "인코딩": 100 };
        updateStageBars(RENDER_STAGES);
        if (CURRENT?.id) await openProject(CURRENT.id, { keepStep: true });
        renderStep3();
      } else if (j.kind === "tts") {
        toast("성우 음성을 만들었습니다.");
        if (CURRENT?.id) await openProject(CURRENT.id, { keepStep: true });
      } else if (j.result?.project?.id) {
        await openProject(j.result.project.id, { keepStep: true });
      } else if (j.result?.video) {
        showCompileResult(j.result);
      }
      await loadProjects();
      opts.onDone && opts.onDone(j);
      if (!opts.quiet && !["render", "tts"].includes(j.kind)) toast("완성되었습니다.");
    } else if (j.status === "error") {
      clearInterval(POLL); POLL = null;
      JOB = { kind: "", id: null };
      RESTART_WAIT = false;
      if (j.kind === "render") {
        $("#renderMsg").textContent = "오류 — " + (j.message || "");
        $("#renderLog").textContent = j.error || "";
        $("#step3Badge").textContent = "오류";
        $("#step3Badge").className = "badge bad";
      }
      if (j.kind === "tts") $("#tlVoice").textContent = "오류 — " + (j.message || "");
      toast(j.message || "오류", true);
    }
  };
  tick();
  POLL = setInterval(tick, 1400);
}

// ── 프로젝트 목록 ────────────────────────────────────────────────────────
async function loadProjects() {
  try {
    const list = await api("/api/projects");
    if (!list.length) {
      $("#projectList").innerHTML = `<p class="hint">아직 만든 사연이 없습니다. 1단계에서 첫 사연을 만들어 보세요.</p>`;
      return;
    }
    $("#projectList").innerHTML = list.map((p) => {
      const done = (p.status?.stage === "done");
      const pct = p.status?.percent || 0;
      return `<div class="project ${CURRENT && CURRENT.id === p.id ? "on" : ""}">
        <b>${esc(p.title || "(제목 없음)")}</b>
        <div class="meta">${esc(p.genre_label || "")} · ${esc(p.format || "")} · ${esc(p.created_at || "")}</div>
        <div class="mini-bar"><div style="width:${done ? 100 : pct}%"></div></div>
        <div class="meta">${done ? "완성" : esc(p.status?.message || "작업 중")} ${done ? "" : `· ${pct}%`}</div>
        <div class="acts">
          <button data-open="${p.id}" type="button">열기</button>
          ${p.outputs?.video ? `<a href="/api/projects/${p.id}/file/video" target="_blank">영상</a>` : ""}
          ${p.outputs?.thumb_style1 ? `<a href="/api/projects/${p.id}/file/thumb1" target="_blank">썸네일</a>` : ""}
          ${p.outputs?.video ? `<button data-shorts="${p.id}" type="button">쇼츠</button>` : ""}
          <a href="/api/projects/${p.id}/file/copy" target="_blank">카피</a>
        </div>
      </div>`;
    }).join("");
    $$("[data-open]").forEach((b) => b.addEventListener("click", () => openProject(b.dataset.open)));
    $$("[data-shorts]").forEach((b) => b.addEventListener("click", () => makeShorts(b.dataset.shorts)));
    loadWeekendOptions();
  } catch (e) { /* 조용히 */ }
}

async function openProject(id, opts = {}) {
  const p = await api(`/api/projects/${id}`);
  CURRENT = p;
  try { localStorage.setItem(LAST_PROJECT, id); } catch (e) {}
  GALLERY_SIG = "";
  DETAIL_SIG = "";
  SCRIPT_MODE = "";
  renderStep1Summary();
  renderLineList(p.scenes || []);
  await refreshStudio(true);
  startStudioPolling(id);
  loadGallery(id, true);
  loadKevinTimeline(id);
  if ((p.scenes || []).length && !SCRIPT_MODE) openScriptRead(id);
  if (!opts.keepStep) setStep(currentStepFor(p), { force: true });
  else setStep(STEP, { force: true });
  await loadProjects();
}

// ── 스튜디오 상태 묶음(/studio) ─────────────────────────────────────────
function stopStudioPolling() {
  ["STUDIO_TIMER", "GALLERY_TIMER", "KEVIN_TIMER"].forEach((k) => {
    if (window[k]) { clearInterval(window[k]); window[k] = null; }
  });
  if (STUDIO_TIMER) { clearInterval(STUDIO_TIMER); STUDIO_TIMER = null; }
  if (GALLERY_TIMER) { clearInterval(GALLERY_TIMER); GALLERY_TIMER = null; }
  if (KEVIN_TIMER) { clearInterval(KEVIN_TIMER); KEVIN_TIMER = null; }
}

function startStudioPolling(pid) {
  if (window.STUDIO_TIMER) { clearInterval(window.STUDIO_TIMER); window.STUDIO_TIMER = null; }
  if (window.GALLERY_TIMER) { clearInterval(window.GALLERY_TIMER); window.GALLERY_TIMER = null; }
  if (window.KEVIN_TIMER) { clearInterval(window.KEVIN_TIMER); window.KEVIN_TIMER = null; }
  window.STUDIO_TIMER = setInterval(() => {
    if (CURRENT && CURRENT.id === pid) refreshStudio(false);
  }, 4000);
  window.GALLERY_TIMER = setInterval(() => {
    if (CURRENT && CURRENT.id === pid) loadGallery(pid);
  }, 5000);
  window.KEVIN_TIMER = setInterval(() => {
    if (CURRENT && CURRENT.id === pid) loadKevinTimeline(pid);
  }, 12000);
}

function _typing() {
  const a = document.activeElement;
  if (!a || !a.closest) return false;
  if (!a.closest("#panel2") && !a.closest("#panel1") && !a.closest("#panel4")) return false;
  return ["INPUT", "TEXTAREA", "SELECT"].includes(a.tagName);
}

async function refreshStudio(force = false) {
  if (!CURRENT?.id) return;
  if (!force && (SCRIPT_DIRTY || _typing())) return;
  try {
    const d = await api(`/api/projects/${CURRENT.id}/studio`);
    CURRENT.status = d.project.status;
    CURRENT.outputs = d.project.outputs;
    CURRENT.duration = d.project.duration;
    CURRENT.images = d.project.images;
    CURRENT.publish = d.project.publish;
    CURRENT.warnings = d.project.warnings;
    CURRENT.pack = d.pack;
    CURRENT.voices = d.voices;
    CURRENT.receive = d.receive;
    CURRENT.youtube = d.project.youtube;
    updateRunBar();
    renderStep2();
    renderStep4();
  } catch (e) { /* 다음 폴링에서 재시도 */ }
}

function updateRunBar() {
  if (!CURRENT) return;
  const imgs = CURRENT.images || { found: 0, total: (CURRENT.image_plan || []).length };
  const stage = (CURRENT.status || {}).stage || "";
  const pct = (CURRENT.status || {}).percent || 0;
  $("#runTitle").textContent = `${STEP_TITLES[STEP]} · ${CURRENT.title || ""}`;
  const voices = CURRENT.voices?.plan?.speakers || {};
  const voiceReady = Object.values(voices).length ? "배정 완료" : "대기";
  const ttsPct = stage === "tts" ? pct : (CURRENT.outputs?.audio ? 100 : 0);
  $("#runMedia").textContent = `음성 ${voiceReady}${ttsPct ? " · " + ttsPct + "%" : ""}`;
  $("#runImages").textContent = `이미지 ${imgs.found || 0}/${imgs.total || 0}장`;
  $("#runRender").textContent = CURRENT.outputs?.video ? "영상 완성" : (stage === "render" ? `렌더링 ${pct}%` : "렌더링 전");
  const rec = CURRENT.receive || {};
  $("#runNote").textContent = rec.last_error ? ("⚠ " + rec.last_error.slice(0, 90))
    : (rec.last_message ? rec.last_message.slice(0, 90) : "");
}

// ── 1단계 요약(대본 상태) ──────────────────────────────────────────────
function renderStep1Summary() {
  if (!CURRENT) {
    $("#step1Badge").textContent = "대본 없음";
    $("#step1Badge").className = "badge";
    $("#scriptSummary").textContent = "아직 대본이 없습니다. [대본 만들기]를 먼저 눌러 주세요.";
    return;
  }
  const scenes = CURRENT.scenes || [];
  const seconds = scenes.reduce((a, s) => a + Math.max(1.2, String(s.text || "").length / 4.3), 0);
  const tag = scriptTag(CURRENT);
  $("#step1Badge").textContent = CURRENT.script_dirty ? "수정본 저장됨" : tag;
  $("#step1Badge").className = "badge " + (CURRENT.script_dirty ? "" : "on");
  $("#scriptSummary").textContent = `${CURRENT.title || ""} · 장면 ${scenes.length}개 · 약 ${mmss(seconds)} · ${tag}`
    + (CURRENT.script_dirty ? " · 수정본 저장됨(영상은 아직 예전 대본)" : "");
  $("#btnScriptEdit").disabled = !scenes.length;
  $("#btnScriptRead").disabled = !scenes.length;
  $("#topic").value = CURRENT.options?.topic || $("#topic").value;
  $("#step1Foot").textContent = scenes.length
    ? `대본 ${scenes.length}장면 · ${tag}. 2단계에서 성우와 이미지를 만듭니다.`
    : "대본을 만든 뒤 2단계로 넘어가세요.";
}

// ── 2단계 화면 ──────────────────────────────────────────────────────────
function renderStep2() {
  if (!CURRENT) {
    $("#step2Badge").textContent = "대본 필요";
    $("#step2Badge").className = "badge";
    $("#tlVoice").textContent = "1단계에서 대본을 먼저 만들어 주세요.";
    return;
  }
  const stage = (CURRENT.status || {}).stage || "";
  const imgs = CURRENT.images || {};
  const rec = CURRENT.receive || {};
  const plan = CURRENT.voices?.plan || {};
  const speakers = plan.speakers || {};
  const dialogCount = Object.values(speakers).filter((s) => s.role !== "narrator").length;

  $("#step2Badge").textContent = imgs.found && imgs.total && imgs.found >= imgs.total
    ? "이미지 준비 완료" : (stage === "tts" ? "음성 만드는 중" : "진행 중");
  $("#step2Badge").className = "badge " + (imgs.found && imgs.found >= imgs.total ? "on" : "");

  if (!(JOB.kind === "tts" && POLL)) {
    $("#tlVoice").textContent = CURRENT.outputs?.audio
      ? "음성 준비 완료 — 대사별 미리듣기로 확인하세요."
      : `목소리 ${Object.keys(speakers).length}명 배정 (대화 인물 ${dialogCount}명 · 해설 1명) · [성우 음성 만들기]를 누르세요.`;
  }
  $("#voiceSummary").textContent = CURRENT.voices?.report
    ? CURRENT.voices.report
    : "해설과 인물의 목소리가 겹치지 않게 배정됩니다.";
  const speedNote = CURRENT.voices?.speed_uniform === false ? " ⚠ 속도가 화자마다 다릅니다." : "";
  const gap = CURRENT.voices?.breath_gap;
  $("#voiceSummary").textContent += speedNote + (gap ? ` · 호흡 간격 ${gap}초` : "");
  $("#ttsMsg").textContent = CURRENT.outputs?.audio
    ? `음성 준비 완료${CURRENT.duration ? " · 전체 " + mmss(CURRENT.duration) : ""}`
    : "—";

  const total = imgs.total || (CURRENT.image_plan || []).length;
  const found = imgs.found || 0;
  $("#tlImages").textContent = `${found}/${total}장 도착${imgs.missing && imgs.missing.length ? " · 남은 " + imgs.missing.length + "장" : ""}`;
  $("#tlImagesBar").style.width = total ? `${Math.round(100 * found / total)}%` : "0%";
  $("#tlRequest").textContent = (CURRENT.request_log || []).length
    ? `요청 ${CURRENT.request_log.length}회 등록 · 케빈 진행은 아래 타임라인`
    : "아직 요청하지 않았습니다. [케빈에게 이미지 요청하기]를 누르세요.";
  $("#tlReview").textContent = (found >= total && total > 0)
    ? "이미지가 다 모였습니다. 컷별 수정이 필요 없으면 3단계로 넘어가세요."
    : "음성·이미지를 확인하고 3단계로 넘어가세요.";
  const voiceDone = !!(CURRENT.outputs?.audio || stage === "tts");
  $$("#mediaTimeline .tl-item").forEach((el) => {
    const k = el.dataset.tl;
    const on = (k === "voice" && voiceDone) || (k === "request" && (CURRENT.request_log || []).length)
      || (k === "images" && found > 0) || (k === "review" && found >= total && total > 0);
    el.classList.toggle("on", !!on);
  });

  // 이미지 수신 상태(원인 바로 보기)
  const bits = [];
  if (rec.last_check) bits.push(`마지막 확인 ${esc(rec.last_check)}`);
  if (rec.route) bits.push(`경로 ${esc(labelRoute(rec.route))}`);
  if (rec.inbox_files?.length) bits.push(`받은 파일 ${rec.inbox_files.length}장`);
  if (rec.last_message) bits.push(esc(rec.last_message));
  $("#inboxStatus").innerHTML = (rec.last_error
    ? `<div class="warn">⚠ ${esc(rec.last_error)}</div>`
    : "") + (bits.length
      ? `<div class="hint small">${bits.join(" · ")}</div>`
      : `<div class="hint small">아직 확인하지 않았습니다. 20초마다 자동으로 확인합니다.</div>`)
    + (imgs.missing && imgs.missing.length
      ? `<div class="hint small">아직 없는 파일: ${imgs.missing.slice(0, 10).map(esc).join(", ")}</div>` : "");

  const gen = $("#btnGenImages");
  if (gen) gen.hidden = (CURRENT.options?.image_mode || "B") !== "A";
  const counter = $("#imgCount");
  if (counter) counter.textContent = `장면 이미지 (${found}/${total})`;
}

function labelRoute(route) {
  return { pull: "git pull", scoped_checkout: "assets_inbox만 받기", api: "GitHub API", failed: "실패", none: "저장소 아님" }[route] || route || "";
}

// ── 2단계: 목소리 배정 보기 ─────────────────────────────────────────────
function renderVoicePlan() {
  const box = $("#voicePlanBox");
  if (!box) return;
  const plan = CURRENT?.voices?.plan;
  if (!plan) return;
  box.hidden = false;
  const rows = [plan.narrator, ...Object.values(plan.speakers || {})];
  box.innerHTML = `<div class="hint small">해설과 인물은 같은 목소리를 쓰지 않습니다${plan.engine === "edge" ? " (무료 음성은 3종이라 피치로 구분)" : ""} · 속도 x${Number(plan.speed).toFixed(2)} 공통</div>
    <table class="vptable"><thead><tr><th>화자</th><th>목소리</th><th>속도</th></tr></thead><tbody>
    ${rows.map((s) => `<tr class="${s.role === "narrator" ? "narr" : ""}">
      <td>${esc(s.label || SPEAKER_LABEL[s.role] || s.role)}</td>
      <td>${esc(s.voice || "")}${s.pitch ? " " + esc(s.pitch) : ""}</td>
      <td>x${Number(s.speed ?? plan.speed).toFixed(2)}</td></tr>`).join("")}
    </tbody></table>`;
}

// ── 2단계: 대사별 미리듣기·재녹음 ──────────────────────────────────────
function renderLineList(scenes) {
  const box = $("#lineList");
  if (!box) return;
  if (!scenes || !scenes.length) {
    box.innerHTML = `<p class="hint small">대본이 있으면 대사별 미리듣기·재녹음이 여기에 나옵니다.</p>`;
    return;
  }
  const pid = CURRENT?.id;
  box.innerHTML = scenes.map((s) => `<div class="lline" data-sid="${esc(s.id)}">
      <div class="lline-head">
        <b>${esc(s.id)}</b>
        <select data-role="speaker">${Object.entries(SPEAKER_LABEL).map(([k, v]) => `<option value="${k}" ${k === (s.speaker || "narrator") ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
        <select data-role="emotion">${Object.entries(EMOTION_LABEL).map(([k, v]) => `<option value="${k}" ${k === (s.emotion || "heal") ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
        ${s.placement ? `<span class="tag">${esc(PLACEMENT_LABEL[s.placement] || s.placement)}</span>` : ""}
        <button class="btn ghost small" data-play="${esc(s.id)}" type="button">▶ 들어보기</button>
        <button class="btn small" data-record="${esc(s.id)}" type="button">🎙 재녹음</button>
        <audio id="audio-${esc(s.id)}" preload="none"></audio>
      </div>
      <textarea data-role="text" rows="2">${esc(s.text || "")}</textarea>
    </div>`).join("");
  box.querySelectorAll("textarea").forEach(growTextarea);
  box.querySelectorAll("[data-play]").forEach((b) => b.addEventListener("click", () => {
    const id = b.dataset.play;
    const a = document.getElementById("audio-" + id);
    if (!a) return;
    a.src = `/api/projects/${pid}/tts/${id}?v=${Date.now()}`;
    a.play().then(() => { b.textContent = "⏸ 재생 중"; }).catch(() => {
      toast("아직 음성이 없습니다. [성우 음성 만들기]를 먼저 눌러 주세요.", true);
      b.textContent = "▶ 들어보기";
    });
    a.onended = () => { b.textContent = "▶ 들어보기"; };
  }));
  box.querySelectorAll("[data-record]").forEach((b) => b.addEventListener("click", () => recordLine(pid, b.dataset.record, b)));
  box.querySelectorAll("textarea, select").forEach((el) => el.addEventListener("input", () => {
    SCRIPT_DIRTY = true;
    $("#scriptSaveResult").innerHTML = `<div class="revise-result">수정한 대사가 있습니다. [🎙 재녹음]을 누르면 이 대사만 새로 녹음하고 저장할 수 있습니다.</div>`;
  }));
}

function lineValues(sid) {
  const row = document.querySelector(`.lline[data-sid="${sid}"]`);
  if (!row) return {};
  return {
    text: row.querySelector("[data-role=text]")?.value ?? "",
    speaker: row.querySelector("[data-role=speaker]")?.value || "narrator",
    emotion: row.querySelector("[data-role=emotion]")?.value || "heal",
  };
}

async function recordLine(pid, sid, btn) {
  const v = lineValues(sid);
  const old = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = "녹음 중…"; }
  try {
    const r = await api(`/api/projects/${pid}/tts/preview`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scene_id: sid, text: v.text, speaker: v.speaker, emotion: v.emotion,
                             save: true, commit: true }),
    });
    SCRIPT_DIRTY = false;
    toast(`재녹음 완료 — ${r.label || sid} · ${r.voice || ""} · ${r.seconds || "?"}초`);
    const a = document.getElementById("audio-" + sid);
    if (a) { a.src = r.url; a.play().catch(() => {}); }
    if (CURRENT?.id === pid) {
      CURRENT = await api(`/api/projects/${pid}`);
      renderLineList(CURRENT.scenes || []);
      renderStep1Summary();
    }
  } catch (e) {
    toast(e.message, true);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = old || "🎙 재녹음"; }
  }
}

async function generateImagesNow() {
  if (!CURRENT) return;
  const btn = $("#btnGenImages");
  btn.disabled = true;
  $("#inboxStatus").innerHTML = `<div class="hint small">Gemini 로 장면 이미지를 만드는 중입니다… (컷마다 10~30초)</div>`;
  try {
    const { job } = await api(`/api/projects/${CURRENT.id}/images/generate`, { method: "POST" });
    watchJob(job, { quiet: true, kind: "images", onDone: async () => {
      if (CURRENT) { await refreshStudio(true); loadGallery(CURRENT.id, true); }
    }});
  } catch (e) {
    toast(e.message, true);
    $("#inboxStatus").innerHTML = `<div class="warn">⚠ ${esc(e.message)}</div>`;
  } finally {
    setTimeout(() => { btn.disabled = false; }, 3000);
  }
}

async function runTts() {
  if (!CURRENT) return toast("먼저 대본을 만들어 주세요.", true);
  const btn = $("#btnTtsRun");
  btn.disabled = true;
  $("#tlVoice").textContent = "성우 녹음 시작…";
  try {
    const { job } = await api(`/api/projects/${CURRENT.id}/tts`, { method: "POST" });
    watchJob(job, { quiet: true, kind: "tts", onDone: async () => { if (CURRENT) await refreshStudio(true); } });
  } catch (e) {
    toast(e.message, true);
    btn.disabled = false;
  } finally {
    setTimeout(() => { btn.disabled = false; }, 2000);
  }
}

// ── 3단계 화면 ──────────────────────────────────────────────────────────
function updateStageBars(stages) {
  stages = stages || {};
  $$("#stageBars .stagebar").forEach((el) => {
    const key = el.dataset.stage;
    const v = Math.max(0, Math.min(100, Number(stages[key] || 0)));
    el.querySelector(".bar > div").style.width = v + "%";
    el.querySelector(".sb-head span").textContent = v + "%";
    el.classList.toggle("done", v >= 100);
  });
}

function renderStep3() {
  if (!CURRENT) return;
  const hasVideo = !!(CURRENT.outputs && CURRENT.outputs.video);
  const missing = (CURRENT.images && CURRENT.images.missing) || (CURRENT.missing_images || []);
  $("#step3Badge").textContent = hasVideo ? "영상 완성" : "대기";
  $("#step3Badge").className = "badge " + (hasVideo ? "on" : "");
  $("#renderState").textContent = hasVideo
    ? `완성된 영상이 있습니다${CURRENT.duration ? " · " + mmss(CURRENT.duration) : ""}. 다시 렌더링할 수도 있습니다.`
    : (missing.length ? `이미지 ${missing.length}장이 아직 없습니다 — 2단계에서 받아 주세요.` : "렌더링 준비 완료.");
  if (hasVideo) {
    $("#renderResult").innerHTML = `<a href="/api/projects/${CURRENT.id}/file/video" target="_blank">완성 영상 열기 <span>${mmss(CURRENT.duration || 0)}</span></a>
      <a href="/api/projects/${CURRENT.id}/file/copy" target="_blank">업로드 카피 <span>문서</span></a>`;
  }
}

async function runRender() {
  if (!CURRENT) return toast("먼저 대본을 만들어 주세요.", true);
  const imgs = CURRENT.images || {};
  if (imgs.missing && imgs.missing.length) {
    toast(`이미지 ${imgs.missing.length}장이 아직 없습니다: ${imgs.missing.slice(0, 4).join(", ")}`, true);
    setStep(2);
    return;
  }
  const btn = $("#btnRender");
  btn.disabled = true;
  RENDER_STAGES = { "성우": 0, "BGM": 0, "자막": 0, "인코딩": 0 };
  updateStageBars(RENDER_STAGES);
  $("#renderMsg").textContent = "렌더링을 시작합니다…";
  $("#renderLog").textContent = "";
  try {
    const { job } = await api(`/api/projects/${CURRENT.id}/render`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ remix: true }),
    });
    watchJob(job, { quiet: true, kind: "render", onDone: async () => { if (CURRENT) await openProject(CURRENT.id, { keepStep: true }); } });
  } catch (e) {
    toast(e.message, true);
    $("#renderMsg").textContent = e.message;
  } finally {
    setTimeout(() => { btn.disabled = false; }, 3000);
  }
}

// ── 4단계 화면 ──────────────────────────────────────────────────────────
function renderStep4() {
  if (!CURRENT) return;
  const pid = CURRENT.id;
  const hasVideo = !!(CURRENT.outputs && CURRENT.outputs.video);
  $("#step4Badge").textContent = hasVideo ? "감수 가능" : "영상 없음";
  $("#step4Badge").className = "badge " + (hasVideo ? "on" : "");
  if (hasVideo && !$("#finalVideo video")) {
    $("#finalVideo").innerHTML = `<video controls preload="metadata" src="/api/projects/${pid}/file/video?v=${Date.now()}" style="width:100%;border-radius:14px;background:#000"></video>`;
  }
  if (!hasVideo && $("#finalVideo").querySelector("video")) {
    $("#finalVideo").innerHTML = `<p class="hint small">아직 완성된 영상이 없습니다. 3단계에서 렌더링해 주세요.</p>`;
  }
  const o = CURRENT.outputs || {};
  $("#lnkShorts").hidden = !o.shorts;
  if (o.shorts) $("#lnkShorts").href = `/api/projects/${pid}/file/shorts`;
  $("#lnkRequest").href = `/api/projects/${pid}/file/request`;
  $("#lnkCopy").href = `/api/projects/${pid}/file/copy`;
  $("#lnkSrt").href = `/api/projects/${pid}/file/srt`;

  if (o.thumb_style1) {
    const img1 = $("#thumb1Img");
    if (!img1.dataset.sig || img1.dataset.sig !== String(o.thumb_style1)) {
      img1.src = `/api/projects/${pid}/file/thumb1?v=${Date.now()}`;
      img1.dataset.sig = String(o.thumb_style1);
    }
  }
  if (o.thumb_style2) {
    const img2 = $("#thumb2Img");
    if (!img2.dataset.sig || img2.dataset.sig !== String(o.thumb_style2)) {
      img2.src = `/api/projects/${pid}/file/thumb2?v=${Date.now()}`;
      img2.dataset.sig = String(o.thumb_style2);
    }
  }
  const th = CURRENT.thumbnail || {};
  if (document.activeElement !== $("#th1a")) $("#th1a").value = (th.style1 || [])[0] || $("#th1a").value;
  if (document.activeElement !== $("#th1b")) $("#th1b").value = (th.style1 || [])[1] || $("#th1b").value;
  [0, 1, 2, 3, 4].forEach((i) => {
    const el = $(`#th2${i}`);
    if (el && document.activeElement !== el) el.value = (th.style2 || [])[i] || el.value;
  });

  const pack = CURRENT.pack || {};
  const titles = pack.titles || [CURRENT.title];
  if ($("#pubTitle").options.length !== titles.length) {
    $("#pubTitle").innerHTML = titles.map((t, i) => `<option value="${i}">${i + 1}안 · ${esc(t)}</option>`).join("");
  }
  $("#titleCopy").innerHTML = titles.map((t, i) => `
    <div class="copy-item"><span class="copy-num">${i + 1}</span><span class="copy-text">${esc(t)}</span>
      <button class="btn small" data-copy="${esc(t)}" type="button">복사</button></div>`).join("");
  $("#seoDesc").textContent = pack.description || CURRENT.description || "";
  $("#seoPinned").textContent = pack.pinned_comment || "(조립 후 자동 생성됩니다)";
  $("#publishMsg").textContent = CURRENT.publish && CURRENT.publish.decision && CURRENT.publish.decision !== "undecided"
    ? `최근 결정: ${{ now: "즉시 업로드", schedule: "예약 업로드", hold: "보류(파일만)" }[CURRENT.publish.decision] || CURRENT.publish.decision} · ${CURRENT.publish.updated || ""}`
    : "업로드 방식을 고르고 [이 결정으로 진행]을 누르세요.";
  const pub = CURRENT.publish || {};
  if (pub.decision === "hold") {
    const r = document.querySelector('input[name=publishDecision][value="hold"]');
    if (r) r.checked = true;
  }
  $$("[data-copy]").forEach((b) => b.addEventListener("click", () => copyText(b.dataset.copy)));
}

async function regenThumb(pid) {
  const body = {
    style1: [$("#th1a").value, $("#th1b").value],
    style2: [0, 1, 2, 3, 4].map((i) => $(`#th2${i}`).value),
  };
  toast("썸네일 다시 만드는 중…");
  try {
    await api(`/api/projects/${pid}/thumbnail`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    toast("썸네일 2종을 다시 만들었습니다.");
    await openProject(pid, { keepStep: true });
  } catch (e) { toast(e.message, true); }
}

async function publishNow() {
  if (!CURRENT) return;
  const decision = document.querySelector("input[name=publishDecision]:checked")?.value || "hold";
  const privacy = $("#pubPrivacy").value;
  const publishAt = $("#pubAt").value;
  const titleIndex = Number($("#pubTitle").value || 0);
  if (decision === "schedule" && !publishAt) return toast("예약 시각을 골라 주세요.", true);
  if (decision !== "hold") {
    const label = decision === "schedule" ? `예약 업로드(${publishAt})` : `즉시 업로드(${privacy})`;
    if (!confirm(`${label} 를 진행할까요? 유튜브 계정에 실제로 올라갑니다.`)) return;
  }
  $("#btnPublish").disabled = true;
  try {
    const r = await api(`/api/projects/${CURRENT.id}/publish`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, privacy: privacy === "private" && decision === "schedule" ? "private" : privacy,
                             publish_at: publishAt, title_index: titleIndex }),
    });
    if (r.job) {
      watchJob(r.job, { quiet: true });
      $("#publishMsg").textContent = r.message || "업로드를 시작했습니다.";
    } else {
      $("#publishMsg").textContent = r.message || r.error || "";
      if (r.ok === false) toast(r.error || "진행하지 못했습니다.", true);
      else toast(r.message || "저장했습니다.");
      await refreshStudio(true);
    }
  } catch (e) {
    toast(e.message, true);
  } finally {
    $("#btnPublish").disabled = false;
  }
}

// ── 장면 이미지 갤러리(지문 비교 → 깜빡이지 않음) ─────────────────────
async function loadGallery(pid, force = false) {
  if (!CURRENT || CURRENT.id !== pid) return;
  try {
    const g = await api(`/api/projects/${pid}/images`);
    if (!force && g.signature === GALLERY_SIG) return;
    GALLERY_SIG = g.signature;
    GALLERY_ROWS = g.images || [];
    renderGallery(pid, g);
  } catch (e) { /* 다음 폴링에서 재시도 */ }
}

function renderGallery(pid, g) {
  const box = $("#imgGallery");
  if (!box) return;
  const rows = g.images || [];
  const counter = $("#imgCount");
  if (counter) counter.textContent = `장면 이미지 (${g.found}/${g.total})`;
  if (!rows.length) {
    box.innerHTML = `<p class="hint small">이 사연에는 장면 이미지 계획이 없습니다.</p>`;
    return;
  }
  box.innerHTML = rows.map((r) => {
    const caption = r.caption || (r.prompt ? r.prompt.slice(0, 90) + (r.prompt.length > 90 ? "…" : "") : "장면 설명 없음");
    return `<figure class="shot ${r.found ? "" : "missing"}" data-idx="${r.idx}">
      ${r.found
        ? `<img src="${esc(r.url)}" alt="${esc(r.file)}" loading="lazy" data-open-img="${r.idx}">`
        : `<div class="missing" data-open-img="${r.idx}">${esc(r.file)}<br>없음</div>`}
      <figcaption><b data-cut="${r.idx}" title="누르면 수정 지시에 이 컷 번호가 들어갑니다">${String(r.idx).padStart(2, "0")}</b> ${esc(r.file)}</figcaption>
      <div class="scene" title="${esc(r.caption || r.prompt || "")}" data-open-img="${r.idx}">${esc(caption)}</div>
    </figure>`;
  }).join("");
  $$("[data-open-img]").forEach((el) => el.addEventListener("click", () => openImage(Number(el.dataset.openImg))));
  $$("[data-cut]").forEach((el) => el.addEventListener("click", (e) => { e.stopPropagation(); pickCut(Number(el.dataset.cut)); }));
}

function cutByIndex(idx) { return GALLERY_ROWS.find((r) => r.idx === idx) || null; }

function ensureLightbox() {
  let lb = $("#imgLightbox");
  if (lb) return lb;
  lb = document.createElement("div");
  lb.id = "imgLightbox";
  lb.className = "lightbox";
  lb.innerHTML = `<div class="inner">
    <div class="meta">
      <b id="lbTitle">컷</b>
      <div class="row" style="gap:6px">
        <button class="btn ghost small" id="lbPrev">⬅ 이전</button>
        <button class="btn ghost small" id="lbNext">다음 ➡</button>
        <button class="btn small" id="lbPick">✏️ 이 컷 수정</button>
        <button class="btn ghost small" id="lbClose">✕ 닫기</button>
      </div>
    </div>
    <img id="lbImg" alt="">
    <div class="desc" id="lbDesc"></div>
  </div>`;
  document.body.appendChild(lb);
  lb.addEventListener("click", (e) => { if (e.target === lb) closeImage(); });
  $("#lbClose").addEventListener("click", closeImage);
  $("#lbPrev").addEventListener("click", () => openImage(LB_IDX - 1));
  $("#lbNext").addEventListener("click", () => openImage(LB_IDX + 1));
  $("#lbPick").addEventListener("click", () => {
    const r = cutByIndex(LB_IDX);
    closeImage();
    if (r) pickCut(r.idx);
  });
  document.addEventListener("keydown", (e) => {
    if (!lb.classList.contains("open")) return;
    if (e.key === "Escape") closeImage();
    else if (e.key === "ArrowLeft") openImage(LB_IDX - 1);
    else if (e.key === "ArrowRight") openImage(LB_IDX + 1);
  });
  return lb;
}

function openImage(idx) {
  if (!GALLERY_ROWS.length) return;
  const n = GALLERY_ROWS.length;
  let i = Number(idx);
  if (!Number.isFinite(i)) i = GALLERY_ROWS[0].idx;
  if (!cutByIndex(i)) i = n;
  const pos = GALLERY_ROWS.findIndex((r) => r.idx === i);
  LB_IDX = GALLERY_ROWS[(pos + n) % n].idx;
  const r = cutByIndex(LB_IDX);
  if (!r) return;
  const lb = ensureLightbox();
  $("#lbTitle").textContent = `컷 ${String(r.idx).padStart(2, "0")} · ${r.file}${r.found ? "" : " · 아직 없음"}`;
  const img = $("#lbImg");
  if (r.found) { img.src = r.url; img.style.display = "block"; }
  else { img.removeAttribute("src"); img.style.display = "none"; }
  const parts = [];
  if (r.caption) parts.push(`<b>장면:</b> ${esc(r.caption)}`);
  if (r.line) parts.push(`<b>내레이션:</b> ${esc(r.line)}`);
  if (r.prompt) parts.push(`<b>이미지 프롬프트:</b> ${esc(r.prompt)}`);
  $("#lbDesc").innerHTML = parts.length ? parts.join("<br>") : "장면·내레이션 정보가 없습니다.";
  lb.classList.add("open");
}

function closeImage() {
  const lb = $("#imgLightbox");
  if (lb) lb.classList.remove("open");
}

function pickCut(idx) {
  const inp = $("#imgReviseNote");
  if (!inp) return;
  const token = `${idx}번 컷 `;
  if (!inp.value.includes(token)) inp.value = (inp.value.trim() ? inp.value.trim() + ", " : "") + token;
  inp.focus();
  try { inp.setSelectionRange(inp.value.length, inp.value.length); } catch (e) {}
  $("#imgReviseBox")?.scrollIntoView({ behavior: "smooth", block: "center" });
}

// ── 케빈 실시간 타임라인 ────────────────────────────────────────────────
async function loadKevinTimeline(pid, force = false) {
  pid = pid || CURRENT?.id;
  const box = $("#kevinTimeline");
  if (!box || !pid) return;
  try {
    const r = await api(`/api/projects/${pid}/kevin-timeline`);
    if (!r.ok) {
      box.textContent = r.error || "타임라인을 불러오지 못했습니다.";
      return;
    }
    const events = r.events || [];
    if (!events.length) {
      box.textContent = "이 사연에 등록된 깃허브 요청이 아직 없습니다. [📤 케빈에게 이미지 요청하기] 나 [✏️ 이미지 수정 요청] 을 누르면 진행 단계가 여기에 실시간으로 쌓입니다.";
      return;
    }
    box.textContent = events.map((ev) => `[${kstClock(ev.at)}] ${ev.text}`).join("\n");
    if (force || box.scrollHeight - box.scrollTop - box.clientHeight < 40) box.scrollTop = box.scrollHeight;
  } catch (e) {
    box.textContent = `조회 오류: ${e.message}`;
  }
}

// ── 케빈에게 이미지 요청 (깃허브) ────────────────────────────────────────
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

async function requestKevinsImages(id, opts = {}) {
  const kind = opts.kind || "image_request";
  const instruction = (opts.instruction || "").trim();
  const isRev = kind === "image_revision";
  let win = null;
  try { win = window.open("", "_blank"); } catch (e) { win = null; }
  const btn = $(isRev ? "#btnImgRevise" : "#btnGhRequest");
  const idle = isRev ? "✏️ 케빈에게 이미지 수정 요청" : "📤 케빈에게 이미지 요청하기";
  if (btn) { btn.disabled = true; btn.textContent = isRev ? "수정 요청 보내는 중…" : "요청 보내는 중…"; }
  const open = (url) => {
    if (!url) return;
    if (win && !win.closed) win.location.href = url;
    else window.open(url, "_blank");
  };
  try {
    const r = await api(`/api/projects/${id}/github-request`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "auto", kind, instruction }),
    });
    open(r.url);
    if (isRev) renderReviseResult(r);
    if (r.fallback_error) toast("토큰 등록 실패 — 1클릭 등록 화면으로 넘어갑니다: " + r.fallback_error, true);
    if (r.mode === "api") toast(r.message || `깃허브 요청 이슈 #${r.number} 등록 완료`);
    else {
      const copied = r.copy_body ? await copyText(r.body, true) : false;
      toast("깃허브 등록 화면이 열렸습니다. [Create issue]만 누르면 케빈에게 전달됩니다."
        + (copied ? " (요청서 전문은 클립보드에 복사해 두었습니다)" : ""));
    }
    $("#tlRequest").textContent = `요청 등록됨 (${isRev ? "이미지 수정" : "이미지 요청"}) · 케빈 진행은 아래 타임라인`;
    await loadKevinTimeline(id, true);
    setTimeout(() => loadKevinTimeline(id, true), 4000);
    if (isRev) setTimeout(() => loadKevinTimeline(id, true), 12000);
    if (CURRENT?.id === id) { CURRENT = await api(`/api/projects/${id}`); }
  } catch (e) {
    if (win && !win.closed) win.close();
    toast(e.message, true);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = idle; }
  }
}

function renderReviseResult(r) {
  const box = $("#imgReviseResult");
  if (!box) return;
  const head = r.mode === "api" ? "✅ 깃허브 수정 요청 이슈 생성됨" : "📝 깃허브 등록 화면 열림";
  box.innerHTML = `<div class="revise-result">
    <b>${esc(head)}</b> · <span class="hint small">${esc(r.target_inbox || "")}</span>
    <div>${esc(r.message || "")}</div>
    ${r.instruction ? `<div class="hint small">지시: ${esc(r.instruction)}</div>` : ""}
    ${r.url ? `<a href="${esc(r.url)}" target="_blank">깃허브에서 열기</a>` : ""}
  </div>`;
}

// ── 자동 이미지 수신 ────────────────────────────────────────────────────
async function loadAutoInbox() {
  try {
    const d = await api("/api/inbox/auto");
    const on = !!d.enabled;
    const btn = $("#btnAutoInbox");
    btn.classList.toggle("recv-on", on);
    btn.classList.toggle("recv-off", !on);
    $("#autoInboxState").textContent = on ? "ON" : "OFF";
    const last = d.last_check ? d.last_check.slice(11, 19) : "—";
    $("#autoInboxDetail").textContent = d.is_git
      ? `20초마다 확인합니다 · 마지막 확인 ${d.last_check || "아직"} · ${d.last_error ? "⚠ " + d.last_error : (d.last_message || "대기 중")}`
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
      if (CURRENT && CURRENT.id === e.project_id) await openProject(CURRENT.id, { keepStep: true });
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
      <div>${esc(e.project_id)} · ${esc(e.folder || "기본 폴더")} · ${e.count}장 · 남은 ${e.missing}장 · ${esc(e.time)}${e.route ? " · " + esc(labelRoute(e.route)) : ""}</div>
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
      $("#inboxStatus").innerHTML = (r.last_error ? `<div class="warn">⚠ ${esc(r.last_error)}</div>` : "")
        + `<div class="hint small">${esc(r.message || "")}${r.route ? " · 경로 " + esc(labelRoute(r.route)) : ""}</div>`;
      await loadAutoInbox();
      await loadInbox();
      await loadProjects();
      if (CURRENT) await refreshStudio(true);
    }});
  } catch (e) { toast(e.message, true); }
}

// ── 업데이트 · 인박스 목록 ───────────────────────────────────────────────
async function updatePull() {
  $("#updateMsg").textContent = "최신 버전 확인 중…";
  RESTART_WAIT = true;
  try {
    const { job } = await api("/api/update/pull", { method: "POST" });
    watchJob(job, { quiet: true, onDone: async (j) => {
      const r = j.result || {};
      $("#updateMsg").textContent = r.message || "완료";
      if (r.restarting) { waitForServerAndReload(r.message); return; }
      RESTART_WAIT = false;
      await loadInbox();
      await loadHealth();
    }});
  } catch (e) {
    RESTART_WAIT = false;
    $("#updateMsg").textContent = e.message;
  }
}

async function waitForServerAndReload(msg) {
  const el = $("#updateMsg");
  if (el) el.textContent = msg || "새 코드로 다시 시작하는 중… 2~3초 뒤 자동 새로고침됩니다.";
  await new Promise((r) => setTimeout(r, 1200));
  for (let i = 0; i < 24; i++) {
    try {
      const res = await fetch(`/api/health?t=${Date.now()}`, { cache: "no-store" });
      if (res.ok) { location.reload(); return; }
    } catch (e) { /* 아직 준비 중 */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  location.reload();
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
        <button class="btn small" data-inbox="${i}" type="button">📥 프로젝트에 가져오기</button>
      </div>`).join("");
    $$("[data-inbox]").forEach((b) => b.addEventListener("click", async () => {
      if (!CURRENT) return toast("먼저 [내 사연들]에서 이미지를 넣을 사연을 열어 주세요.", true);
      const f = d.folders[Number(b.dataset.inbox)];
      try {
        const r = await api("/api/inbox/import", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_id: CURRENT.id, folder: f.folder }) });
        toast(`${r.saved.length}장을 가져왔습니다. 남은 이미지 ${r.missing.length}장.`);
        await refreshStudio(true);
        loadGallery(CURRENT.id, true);
      } catch (e) { toast(e.message, true); }
    }));
  } catch (e) { /* 무시 */ }
}

// ── 유튜브 ──────────────────────────────────────────────────────────────
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

function ytPrivacyPayload() {
  const sel = $("#ytPrivacy").value;
  return {
    privacy: sel === "scheduled" ? "private" : sel,
    publish_at: sel === "scheduled" ? $("#ytPublishAt").value : "",
    title_index: Number($("#ytTitleIndex").value || 0),
  };
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

// ── 채널 전략 ───────────────────────────────────────────────────────────
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
  $("#strategyCards").innerHTML = (d.cards || []).map((c, i) => `
    <div class="strategy-card">
      <div class="strategy-head"><span class="tag">${esc(c.badge || "전략")}</span>
        <b>${esc(c.title)}</b></div>
      <ul>${(c.reason || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      <div class="strategy-foot">
        <span class="hint small">${esc(c.summary || "")}</span>
        <button class="btn primary small" data-card="${i}" type="button">✅ 승인하고 바로 진행</button>
      </div>
    </div>`).join("");
  $$("[data-card]").forEach((b) => b.addEventListener("click", () => executeStrategy(Number(b.dataset.card))));
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
    const { job } = await api("/api/strategy/execute", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: card.action, image_mode: mode }),
    });
    watchJob(job, { onDone: async () => { await loadProjects(); await loadStrategy(); } });
    toast(card.action?.type === "weekend" ? "합본 제작을 시작합니다." : "제안대로 제작을 시작합니다.");
  } catch (e) { toast(e.message, true); }
}

// ── 폰 접속 ─────────────────────────────────────────────────────────────
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

// ── 자동 스케줄 ─────────────────────────────────────────────────────────
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

// ── 댓글 관리 ───────────────────────────────────────────────────────────
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
        <div class="row"><button class="btn ghost small" data-draft="${i}" type="button">초안 만들기</button>
          <button class="btn small" data-reply="${i}" type="button">답글 등록</button></div>
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

// ── 50초 쇼츠 ───────────────────────────────────────────────────────────
async function makeShorts(id) {
  try {
    const { job } = await api(`/api/projects/${id}/shorts`, { method: "POST" });
    watchJob(job, { onDone: async () => { await loadProjects(); } });
    toast("가장 임팩트 있는 50초 구간을 뽑고 있습니다.");
  } catch (e) { toast(e.message, true); }
}

// ── 이미지 업로드 ───────────────────────────────────────────────────────
async function uploadImages(id, files) {
  if (!files || !files.length) return;
  const fd = new FormData();
  Array.from(files).forEach((f) => fd.append("files", f));
  toast("이미지 올리는 중…");
  try {
    const r = await api(`/api/projects/${id}/images`, { method: "POST", body: fd });
    if (r.saved?.length) toast(`${r.saved.length}장을 넣었습니다. 남은 이미지 ${r.missing.length}장.`);
    else toast("이름이 맞는 이미지가 없습니다. s01.png 형식으로 넣어 주세요.", true);
    await refreshStudio(true);
    loadGallery(id, true);
    await loadProjects();
  } catch (e) { toast(e.message, true); }
}

// ── 대본 전체 읽기 · 직접 수정 · 재제작 ─────────────────────────────────
async function openScriptRead(pid) {
  const box = $("#scriptView");
  const editor = $("#scriptEditor");
  if (!box) return;
  SCRIPT_MODE = "read";
  if (editor) editor.hidden = true;
  box.hidden = false;
  box.innerHTML = `<p class="hint small">대본 불러오는 중…</p>`;
  let d = null;
  try { d = await api(`/api/projects/${pid}/script`); }
  catch (e) { box.innerHTML = `<div class="warn">${esc(e.message)}</div>`; return; }
  const chapters = d.chapters || [];
  if (!chapters.length) { box.innerHTML = `<p class="hint">대본이 없습니다.</p>`; return; }
  box.dataset.text = d.text || "";
  const head = `<div class="row" style="justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
      <span class="hint small">${esc(d.title || "")} · 장면 ${d.total_scenes}개 · 약 ${mmss(d.total_seconds)} · ${esc(d.script_engine_tag || "")}${d.script_dirty ? " · 수정본 저장됨" : ""}</span>
      <div class="row" style="gap:6px">
        <button class="btn ghost small" id="btnScriptCopyAll" type="button">📋 전체 복사</button>
        <button class="btn ghost small" id="btnScriptCopyLines" type="button">대사만 복사</button>
        <button class="btn ghost small" id="btnScriptClose" type="button">접기</button>
      </div>
    </div>`;
  const body = chapters.map((g) => `
    <div class="chapter-head">${g.index}장 · ${esc(g.title)} <span>약 ${mmss(g.seconds)}</span></div>
    ${(g.scenes || []).map((s) => `
      <div class="sline${s.placement ? " fixed" : ""}" data-sid="${esc(s.id)}">
        <div class="sline-head"><b>${esc(s.id)}</b> <span class="sp">${esc(s.speaker_label || "")}</span>
          ${s.placement ? `<span class="tag">${esc(PLACEMENT_LABEL[s.placement] || s.placement)}</span>` : ""}
          <span class="hint small">${esc(EMOTION_LABEL[s.emotion] || "")}${s.sfx && s.sfx.length ? " · 🔊 " + esc(s.sfx.join(", ")) : ""}</span>
        </div>
        <p>${esc(s.text)}</p>
        ${s.tone ? `<div class="hint small">연기: ${esc(s.tone)}${s.age ? " · " + esc(s.age) : ""}</div>` : ""}
      </div>`).join("")}`).join("");
  box.innerHTML = head + body;
  $("#btnScriptCopyAll")?.addEventListener("click", () => copyText(d.text || ""));
  $("#btnScriptCopyLines")?.addEventListener("click", () => {
    const lines = chapters.flatMap((g) => (g.scenes || []).map((s) => s.text)).join("\n");
    copyText(lines);
  });
  $("#btnScriptClose")?.addEventListener("click", () => { box.hidden = true; SCRIPT_MODE = ""; });
}

async function openScriptEditor(pid) {
  const box = $("#scriptEditor");
  const view = $("#scriptView");
  if (!box) return;
  SCRIPT_MODE = "edit";
  if (view) view.hidden = true;
  box.hidden = false;
  let p = CURRENT && CURRENT.id === pid ? CURRENT : await api(`/api/projects/${pid}`);
  const scenes = p.scenes || [];
  if (!scenes.length) { box.innerHTML = `<p class="hint">대본이 없습니다.</p>`; return; }
  const chapters = p.chapters || [];
  const opts = (map, cur) => Object.entries(map)
    .map(([k, v]) => `<option value="${k}" ${k === cur ? "selected" : ""}>${esc(v)}</option>`).join("");
  let html = `<p class="hint small">장면의 대사·화자·감정을 고치고 [💾 수정된 대본 저장]을 누르세요.
    빈 대사로 저장한 장면은 대본에서 빠집니다(훅·되감기·예고·엔딩 같은 고정 장면 제외).</p><div class="sedit-list">`;
  let chapter = null;
  scenes.forEach((s, i) => {
    const ch = Number(s.chapter || 1);
    if (ch !== chapter) {
      chapter = ch;
      const title = (chapters.find((c) => Number(c.index) === ch) || {}).title || s.chapter_title || `${ch}장`;
      html += `<div class="chapter-head">${ch}장 · ${esc(title)}</div>`;
    }
    const fixed = !!s.placement;
    html += `<div class="sedit" data-idx="${i}" data-id="${esc(s.id)}">
      <div class="sedit-head">
        <b>${esc(s.id)}</b>
        <select data-role="speaker">${opts(SPEAKER_LABEL, s.speaker || "narrator")}</select>
        <select data-role="emotion">${opts(EMOTION_LABEL, s.emotion || "heal")}</select>
        ${fixed ? `<span class="tag">${esc(PLACEMENT_LABEL[s.placement] || s.placement)}</span>`
                : `<button class="btn ghost small" data-del="1" title="이 장면 빼기" type="button">✕</button>`}
      </div>
      <textarea data-role="text" rows="2">${esc(s.text)}</textarea>
      ${(s.speaker_tone || (s.sfx && s.sfx.length))
        ? `<div class="hint small">${s.speaker_tone ? "연기: " + esc(s.speaker_tone) : ""}${s.sfx && s.sfx.length ? " · 🔊 " + esc(s.sfx.join(", ")) : ""}</div>`
        : ""}
    </div>`;
  });
  html += `</div>
    <div class="row" style="margin-top:10px;gap:8px;flex-wrap:wrap">
      <button class="btn primary small" id="btnScriptSave" type="button">💾 수정된 대본 저장</button>
      <button class="btn small" id="btnScriptRebuild" type="button">🎬 수정한 대본으로 성우·영상 다시 만들기</button>
      <button class="btn ghost small" id="btnScriptCancel" type="button">↩︎ 수정 취소</button>
      <span class="hint small" id="scriptDirtyMsg"></span>
    </div>`;
  box.innerHTML = html;
  SCRIPT_DIRTY = false;
  const mark = () => {
    SCRIPT_DIRTY = true;
    const m = $("#scriptDirtyMsg");
    if (m) m.textContent = "저장하지 않은 수정이 있습니다";
  };
  box.querySelectorAll("[data-role=text], [data-role=speaker], [data-role=emotion]").forEach((el) => {
    el.addEventListener("input", () => { mark(); growTextarea(el); });
    el.addEventListener("change", mark);
  });
  box.querySelectorAll("textarea").forEach(growTextarea);
  box.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => {
    b.closest(".sedit")?.remove();
    mark();
    toast("장면을 뺐습니다. [💾 수정된 대본 저장]을 눌러야 반영됩니다.");
  }));
  $("#btnScriptSave")?.addEventListener("click", () => saveScript(pid));
  $("#btnScriptRebuild")?.addEventListener("click", () => rebuildScript(pid));
  $("#btnScriptCancel")?.addEventListener("click", () => {
    SCRIPT_MODE = ""; SCRIPT_DIRTY = false;
    box.hidden = true;
    toast("대본 수정을 취소했습니다.");
  });
}

function collectScriptScenes() {
  return $$("#scriptEditor .sedit").map((row) => ({
    id: row.dataset.id || "",
    speaker: row.querySelector("[data-role=speaker]")?.value || "narrator",
    emotion: row.querySelector("[data-role=emotion]")?.value || "heal",
    text: row.querySelector("[data-role=text]")?.value ?? "",
  }));
}

async function saveScript(pid, quiet = false) {
  const btn = $("#btnScriptSave");
  const scenes = collectScriptScenes();
  if (!scenes.length) return toast("저장할 장면이 없습니다.", true);
  if (btn) { btn.disabled = true; btn.textContent = "저장 중…"; }
  try {
    const r = await api(`/api/projects/${pid}/script`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenes }),
    });
    SCRIPT_DIRTY = false;
    if (!quiet) toast(r.message || "대본을 저장했습니다.");
    CURRENT = await api(`/api/projects/${pid}`);
    renderStep1Summary();
    renderLineList(CURRENT.scenes || []);
    await refreshStudio(true);
    const box = $("#scriptSaveResult");
    if (box) box.innerHTML = `<div class="revise-result"><b>💾 대본 저장됨</b>
      <div>${esc(r.message || "")}</div>
      <div class="hint small">2단계 [성우 음성 만들기] → 3단계 [영상 렌더링]을 다시 누르면 새 대본으로 만들어집니다.</div></div>`;
    return r;
  } catch (e) {
    toast(e.message, true);
    return null;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "💾 수정된 대본 저장"; }
  }
}

async function rebuildScript(pid) {
  if (SCRIPT_DIRTY) {
    const saved = await saveScript(pid, true);
    if (!saved) return;
  }
  const missing = (CURRENT?.images?.missing) || [];
  if (missing.length) {
    toast(`이미지 ${missing.length}장이 아직 없습니다. 2단계에서 받은 뒤 다시 시도해 주세요.`, true);
    return;
  }
  try {
    const { job } = await api(`/api/projects/${pid}/script/rebuild`, { method: "POST" });
    SCRIPT_MODE = "";
    watchJob(job, { onDone: async () => { await loadProjects(); await openProject(pid, { keepStep: true }); } });
    toast("수정한 대본으로 성우부터 다시 만들고 있습니다. 고친 장면만 새로 녹음합니다.");
  } catch (e) { toast(e.message, true); }
}

// ── 주말 합본 ───────────────────────────────────────────────────────────
async function loadWeekendOptions() {
  const list = await api("/api/projects");
  const done = list.filter((p) => p.outputs?.video && p.status?.stage === "done");
  const box = $("#weekendProjects");
  if (!box) return;
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
  $("#renderResult").innerHTML = `<a href="/api/projects/${r.id}/file/video" target="_blank">합본 영상 열기 <span>${mmss(r.duration)}</span></a>`;
}

// ── 설정 드로어 ─────────────────────────────────────────────────────────
function openSettings() {
  $("#settingsDrawer").hidden = false;
  document.body.classList.add("drawer-open");
  loadStrategy();
}
function closeSettings() {
  $("#settingsDrawer").hidden = true;
  document.body.classList.remove("drawer-open");
}

// ── 이벤트 연결 ─────────────────────────────────────────────────────────
function bind() {
  $$("#stepBar .stepbtn").forEach((b) => b.addEventListener("click", () => {
    const n = Number(b.dataset.step);
    if (n > 1 && !CURRENT) return toast("먼저 1단계에서 대본을 만들어 주세요.", true);
    setStep(n, { force: true });
  }));
  $("#btnNext2").addEventListener("click", () => {
    if (!CURRENT) return toast("먼저 [대본 만들기]를 눌러 대본을 만들어 주세요.", true);
    setStep(2, { force: true });
  });
  $("#btnPrev1").addEventListener("click", () => setStep(1));
  $("#btnNext3").addEventListener("click", () => {
    const missing = (CURRENT?.images?.missing) || [];
    if (missing.length) {
      toast(`이미지 ${missing.length}장이 아직 없습니다. 받은 뒤 3단계로 넘어가세요.`, true);
      return;
    }
    setStep(3, { force: true });
  });
  $("#btnPrev2").addEventListener("click", () => setStep(2));
  $("#btnNext4").addEventListener("click", () => {
    if (!CURRENT?.outputs?.video) return toast("먼저 3단계에서 영상을 렌더링해 주세요.", true);
    setStep(4, { force: true });
  });
  $("#btnPrev3").addEventListener("click", () => setStep(3));
  $("#btnNewProject").addEventListener("click", () => {
    CURRENT = null;
    try { localStorage.removeItem(LAST_PROJECT); } catch (e) {}
    $("#scriptView").hidden = true;
    $("#scriptEditor").hidden = true;
    $("#lineList").innerHTML = `<p class="hint small">대본이 있으면 대사별 미리듣기·재녹음이 여기에 나옵니다.</p>`;
    $("#scriptSummary").textContent = "아직 대본이 없습니다. [대본 만들기]를 먼저 눌러 주세요.";
    $("#finalVideo").innerHTML = `<p class="hint small">아직 완성된 영상이 없습니다. 3단계에서 렌더링해 주세요.</p>`;
    setStep(1, { force: true });
  });

  $("#btnSettings").addEventListener("click", openSettings);
  $("#btnSettingsClose").addEventListener("click", closeSettings);
  $("#settingsDrawer").addEventListener("click", (e) => {
    if (e.target === $("#settingsDrawer")) closeSettings();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#settingsDrawer").hidden) closeSettings();
  });

  $("#btnIdeas").addEventListener("click", suggestIdeas);
  $("#btnCreate").addEventListener("click", createProject);
  $("#btnRefresh").addEventListener("click", loadProjects);
  $("#btnTtsRun").addEventListener("click", runTts);
  $("#btnVoicePlan").addEventListener("click", () => {
    const box = $("#voicePlanBox");
    if (!box.hidden) { box.hidden = true; return; }
    renderVoicePlan();
  });
  $("#btnRender").addEventListener("click", runRender);
  $("#btnPublish").addEventListener("click", publishNow);
  $("#btnThumb").addEventListener("click", () => CURRENT && regenThumb(CURRENT.id));
  $("#btnOpenFolder").addEventListener("click", async () => {
    if (!CURRENT) return;
    try { await api(`/api/projects/${CURRENT.id}/open`, { method: "POST" }); }
    catch (e) { toast(e.message, true); }
  });
  $("#btnShorts").addEventListener("click", () => CURRENT && makeShorts(CURRENT.id));
  $("#btnCopyTags").addEventListener("click", () => copyText((CURRENT?.pack?.hashtags || []).join(" ")));

  $("#btnGhRequest").addEventListener("click", () => CURRENT && requestKevinsImages(CURRENT.id));
  $("#btnImgRevise").addEventListener("click", () => {
    if (!CURRENT) return toast("먼저 사연을 열어 주세요.", true);
    const note = ($("#imgReviseNote")?.value || "").trim();
    if (!note) return toast("수정 지시를 적어 주세요. 예: 3번 컷 표정 더 놀랍게", true);
    requestKevinsImages(CURRENT.id, { kind: "image_revision", instruction: note });
  });
  $("#imgReviseNote").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("#btnImgRevise")?.click();
  });
  $("#btnKevin").addEventListener("click", () => CURRENT && loadKevinTimeline(CURRENT.id, true));
  $("#btnGenImages").addEventListener("click", generateImagesNow);
  $("#btnInboxCheck").addEventListener("click", checkInboxNow);
  $("#btnInboxCheck2").addEventListener("click", checkInboxNow);
  const drop = $("#dropZone");
  const input = $("#imgInput");
  drop?.addEventListener("click", () => input.click());
  input?.addEventListener("change", () => CURRENT && uploadImages(CURRENT.id, input.files));
  drop?.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("hover"); });
  drop?.addEventListener("dragleave", () => drop.classList.remove("hover"));
  drop?.addEventListener("drop", (e) => {
    e.preventDefault(); drop.classList.remove("hover");
    if (CURRENT) uploadImages(CURRENT.id, e.dataTransfer.files);
  });

  $$("[data-copy-el]").forEach((b) => b.addEventListener("click", () => {
    const el = document.getElementById(b.dataset.copyEl);
    copyText(el ? (el.value || el.textContent) : "");
  }));

  $("#btnSaveKey").addEventListener("click", saveKey);
  $("#btnTestKey").addEventListener("click", testKey);
  $("#btnScriptEngine")?.addEventListener("click", saveScriptEngine);
  $("#scriptEngine")?.addEventListener("change", saveScriptEngine);
  $("#btnTtsSave").addEventListener("click", () => saveTts());
  $("#btnTtsTest").addEventListener("click", testTts);
  ["ttsEngine", "openaiModel", "ttsFallback"].forEach((id) => {
    $("#" + id)?.addEventListener("change", () => saveTts(true));
  });
  $("#btnGhSave").addEventListener("click", saveGhToken);
  $("#btnGhTest").addEventListener("click", testGhToken);
  $("#btnYtSecret").addEventListener("click", uploadSecret);
  $("#btnYtConnect").addEventListener("click", connectYoutube);
  $("#btnYtDisconnect").addEventListener("click", disconnectYoutube);
  $("#btnYtSave").addEventListener("click", saveYtSettings);
  $("#ytPrivacy").addEventListener("change", () => {
    $("#ytPublishAt").disabled = $("#ytPrivacy").value !== "scheduled";
  });
  $("#btnStrategy").addEventListener("click", analyzeStrategy);
  $("#btnPinSave").addEventListener("click", savePin);
  $("#caffeinate").addEventListener("change", toggleCaffeinate);
  $("#btnSchedSave").addEventListener("click", saveSchedule);
  $("#btnSchedNow").addEventListener("click", runScheduleNow);
  $("#btnComments").addEventListener("click", loadComments);
  $("#btnUpdate").addEventListener("click", updatePull);
  $("#btnAutoInbox").addEventListener("click", toggleAutoInbox);
  $("#autoAssemble").addEventListener("change", saveAutoAssemble);
  $("#btnCompile").addEventListener("click", compile);
  $("#btnScriptRead").addEventListener("click", () => CURRENT && openScriptRead(CURRENT.id));
  $("#btnScriptEdit").addEventListener("click", () => CURRENT && openScriptEditor(CURRENT.id));

  $("#rate").addEventListener("input", () => { $("#rateOut").textContent = $("#rate").value + "%"; saveLocal(); });
  $("#btnAvatarFile").addEventListener("click", () => $("#avatarFile").click());
  $("#avatarFile").addEventListener("change", () => {
    if ($("#avatarFile").files.length) {
      $("#avatarKind").value = "custom";
      toast("내 사진은 조립할 때 반영됩니다. (이미지는 프로젝트 폴더에 저장)");
    }
  });
  $$("input[name=imageMode]").forEach((r) => r.addEventListener("change", () => { onPresetChange(); saveLocal(); }));
  ["topic", "hook15", "sequel", "teaserMode", "teaserText", "voiceMode", "storyTone", "avatar", "avatarKind",
   "liveBadge", "likeVoice", "likeBanner", "outroCta", "endScreen", "sleepRain", "likeVoiceText",
   "ctaText"].forEach((id) => {
    const el = $("#" + id);
    el?.addEventListener("change", saveLocal);
    el?.addEventListener("input", () => { if (id === "teaserText") toggleTeaserBox(); saveLocal(); });
  });
  $$("input[name=subSize]").forEach((r) => r.addEventListener("change", saveLocal));
  $("#teaserMode").addEventListener("change", () => { toggleTeaserBox(); saveLocal(); });
  toggleTeaserBox();
}

document.addEventListener("DOMContentLoaded", init);
