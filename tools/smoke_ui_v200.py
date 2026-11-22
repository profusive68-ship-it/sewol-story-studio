"""app.js 스모크 테스트 — quickjs 위에 최소 DOM 대역을 올려 bind()·렌더 함수가
예외 없이 도는지 확인한다(브라우저 없이 잡을 수 있는 실수를 잡는다).

    python3 tools/smoke_ui_v200.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

SHIM = r"""
const __els = {};
function __el(sel){
  if (__els[sel]) return __els[sel];
  const cl = new Set();
  const el = {
    tagName: "DIV", value: "", checked: false, textContent: "", innerHTML: "",
    hidden: false, disabled: false, options: [], files: [], dataset: {}, style: {},
    classList: {
      add(c){ cl.add(c); }, remove(c){ cl.delete(c); },
      toggle(c, on){ if (on === undefined) { cl.has(c) ? cl.delete(c) : cl.add(c); } else if (on) cl.add(c); else cl.delete(c); },
      contains(c){ return cl.has(c); }
    },
    addEventListener(){}, removeEventListener(){},
    appendChild(){}, remove(){}, focus(){}, click(){},
    scrollIntoView(){}, setSelectionRange(){}, closest(){ return null; },
    querySelector(s){ return __el(sel + " >> " + s); },
    querySelectorAll(){ return []; },
    play(){ return Promise.resolve(); },
    showModal(){}, reset(){}
  };
  __els[sel] = el;
  return el;
}
const document = {
  body: __el("body"),
  activeElement: null,
  querySelector(s){ return __el(s); },
  querySelectorAll(s){ return []; },
  getElementById(s){ return __el("#" + s); },
  createElement(){ return __el("created-" + Math.random()); },
  addEventListener(){}, execCommand(){ return true; }
};
const localStorage = {
  _d: {},
  getItem(k){ return Object.prototype.hasOwnProperty.call(this._d, k) ? this._d[k] : null; },
  setItem(k, v){ this._d[k] = String(v); },
  removeItem(k){ delete this._d[k]; }
};
const navigator = { clipboard: { writeText(){ return Promise.resolve(); } } };
const window = {
  scrollTo(){}, open(){ return null; }, location: { reload(){}, href: "" },
  setInterval(){ return 1; }, clearInterval(){}, setTimeout(){ return 1; }, clearTimeout(){}
};
const location = { reload(){}, hash: "" };
const setInterval = window.setInterval, clearInterval = window.clearInterval;
const setTimeout = window.setTimeout, clearTimeout = window.clearTimeout;
function confirm(){ return false; }
function alert(){}
function fetch(){ return new Promise(function(){}); }
function FormData(){ this.append = function(){}; }
function FileReader(){}
"""

CHECKS = r"""
(function(){
  const out = [];
  function step(name, fn) {
    try { fn(); out.push(["ok", name]); }
    catch (e) { out.push(["fail", name + " :: " + (e && e.message ? e.message : e)]); }
  }
  step("renderGenres", function(){ renderGenres(); });
  step("renderPresets", function(){ renderPresets(); });
  step("onPresetChange", function(){ onPresetChange(); });
  step("restoreLocal", function(){ restoreLocal(); });
  step("collect", function(){ const c = collect(); if (!c.genre || !c.preset) throw new Error("collect 빈 값 " + JSON.stringify(c)); });
  step("saveLocal", function(){ saveLocal(); });
  step("bind", function(){ bind(); });
  step("setStep(1)", function(){ setStep(1, {force:true}); });
  step("setStep(4)", function(){ setStep(4, {force:true}); });
  step("renderStep2(빈 상태)", function(){ CURRENT = null; renderStep2(); });
  step("renderStep3(빈 상태)", function(){ CURRENT = null; renderStep3(); });
  step("renderStep4(빈 상태)", function(){ CURRENT = null; renderStep4(); });
  step("renderIdeas", function(){ IDEAS = [{topic:"t", hook:"h", why:"w"}]; renderIdeas(); });
  step("updateStageBars", function(){ updateStageBars({"성우":50,"BGM":0,"자막":0,"인코딩":0}); });
  step("labelRoute", function(){ if (labelRoute("api") !== "GitHub API") throw new Error("route label"); });
  step("scriptTag", function(){ if (scriptTag({source:"openai"}) !== "AI 대본 (OpenAI)") throw new Error("tag"); });
  step("mmss", function(){ if (mmss(65) !== "01:05") throw new Error(mmss(65)); });
  step("esc", function(){ if (esc("<b>") !== "&lt;b&gt;") throw new Error(esc("<b>")); });
  step("renderInboxEvents", function(){ renderInboxEvents([{message:"m", project_id:"p", count:1, missing:2, time:"t"}]); });
  step("renderVoicePlan", function(){
    CURRENT = {voices:{plan:{engine:"openai", speed:1.0, narrator:{voice:"onyx", label:"해설"},
      speakers:{"female|30대|female":{role:"female", label:"여성", voice:"shimmer", speed:1.0}}}}};
    renderVoicePlan();
  });
  step("renderLineList", function(){
    CURRENT = {id:"p1"};
    renderLineList([{id:"s01", speaker:"narrator", emotion:"heal", text:"안녕"}]);
  });
  step("renderStep2(자료 있음)", function(){
    CURRENT = {id:"p1", title:"테스트", status:{stage:"tts", percent:40}, options:{image_mode:"A"},
      outputs:{}, duration: 30, images:{total:9, found:3, missing:["s04.png"]},
      receive:{last_check:"2026-11-22 15:00:00", route:"scoped_checkout", last_message:"받는 중",
               last_error:"", inbox_files:["s01.png","s02.png","s03.png"]},
      voices:{plan:{engine:"openai", speed:1.0, breath_gap:0.32,
        narrator:{voice:"onyx", label:"해설"},
        speakers:{"narrator":{role:"narrator", label:"해설", voice:"onyx", speed:1.0},
                  "female|30대|female":{role:"female", label:"여성", voice:"shimmer", speed:1.0}}},
        report:"OpenAI ...", speed_uniform:true},
      request_log:[{time:"t"}], image_plan:[{file:"s01.png"}]};
    renderStep2();
    if ($("#tlImages").textContent.indexOf("3/9") !== 0) throw new Error("이미지 도착 수 표시: " + $("#tlImages").textContent);
  });
  step("renderStep3(영상 있음)", function(){
    CURRENT = {id:"p1", outputs:{video:"output/final.mp4"}, duration:50, images:{missing:[]}};
    renderStep3();
  });
  step("renderStep4(자료 있음)", function(){
    CURRENT = {id:"p1", title:"테스트", thumbnail:{style1:["a","b"], style2:["c"]},
      outputs:{video:"output/final.mp4", thumb_style1:"output/thumb/t1.png",
               thumb_style2:"output/thumb/t2.png", srt:"output/subtitles.srt", shorts:"output/s.mp4"},
      pack:{titles:["t1","t2","t3"], description:"설명", hashtags:["#사연"], pinned_comment:"고정"},
      publish:{decision:"hold", updated:"2026-11-22"}};
    renderStep4();
    if ($("#pubTitle").innerHTML.indexOf("t1") < 0) throw new Error("제목 선택 비어 있음");
  });
  step("updateRunBar", function(){
    CURRENT = {title:"테스트", status:{stage:"render", percent:50}, images:{found:9, total:9},
      outputs:{}, voices:{plan:{speakers:{narrator:{role:"narrator"}}}}, receive:{last_message:"확인"}};
    updateRunBar();
  });
  step("renderGallery", function(){
    renderGallery("p1", {found:1, total:2, images:[
      {idx:1, file:"s01.png", found:true, url:"/img/1", caption:"장면", prompt:"p", line:"l"},
      {idx:2, file:"s02.png", found:false, url:"", caption:"", prompt:"", line:""}]});
  });
  step("renderStep2(연결 없음)", function(){ CURRENT = null; renderStep2(); });
  CURRENT = null;
  return JSON.stringify(out);
})()
"""


def main() -> int:
    try:
        import quickjs
    except Exception as e:  # pragma: no cover
        print("quickjs 가 없어 건너뜁니다:", e)
        return 0
    ctx = quickjs.Context()
    ctx.eval(SHIM)
    try:
        ctx.eval(JS)
    except Exception as e:
        print("❌ app.js 문법/정의 오류:", e)
        return 2
    try:
        raw = ctx.eval(CHECKS)
    except Exception as e:
        print("❌ 스모크 실행 오류:", e)
        return 2
    results = json.loads(raw)
    fails = [r for r in results if r[0] == "fail"]
    for kind, name in results:
        print(("  ✅ " if kind == "ok" else "  ❌ ") + name)
    print(f"\n통과 {len(results) - len(fails)} · 실패 {len(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
