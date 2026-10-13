"""Local annotation tool for the LongMemEval key audit. Enforces the PLAN.md order: the auditor
locks his own answer before the server will send the gold answer, evidence flags or prior reports.

Usage:
    python -I tools/annotate.py --pass first                  serve http://127.0.0.1:8791
    python -I tools/annotate.py --pass first --summary        counts only, never answers
    python -I tools/annotate.py --pass second --ids-file ids.json   override the queue (blind re-annotation)

Storage is append-only JSON Lines at annotations/<pass>.jsonl. Only that pass's file is read, so a
later pass never sees labels from another pass. Standard library only.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import threading
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

SCHEMA = 1
HOST = "127.0.0.1"
DEFAULT_PORT = 8791
MAX_BODY = 1_000_000
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CODES = {
    "OK": "Gold answer is the only answer the evidence supports",
    "WRONG_GOLD": "Evidence supports a different answer",
    "MULTIPLE": "Evidence supports more than one answer and the gold names one",
    "UNSUPPORTED": "Evidence does not determine an answer (non-abstention questions)",
    "ABSTENTION_ANSWERABLE": "Abstention question whose evidence does answer it",
    "UNCLEAR_QUESTION": "Question is ambiguous or has a false premise",
    "EVIDENCE_LABEL": "Gold answer is right but answer_session_ids or has_answer is incomplete or wrong",
}
TIERS = ("definite", "ambiguous")
NOT_ANSWERABLE_TEXT = "Not answerable from this evidence"


class ToolError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_events(path):
    """Replay a JSONL file. A malformed line (for example a torn final write) is skipped with a warning."""
    events = []
    if not os.path.exists(path):
        return events
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                print(f"warning: skipping malformed line {n} in {path}", file=sys.stderr)
    return events


def build_queue(data, prior_path, sample_path, ids_file=None):
    """Return [(question_id, stratum)]: prior-reported (sorted), then the sample by sorted stratum key."""
    known = {q["question_id"] for q in data}
    if ids_file:
        ids = load_json(ids_file)
        missing = [i for i in ids if i not in known]
        if missing:
            raise SystemExit(f"--ids-file has {len(missing)} id(s) not in the data, first: {missing[0]}")
        strata = {}
        if os.path.exists(sample_path):
            sample = load_json(sample_path)
            for k, v in sample["sample"].items():
                strata.update({i: k for i in v})
            strata.update({i: "prior-reported" for i in sample["prior_reported_stratum"]})
        return [(i, strata.get(i, "custom")) for i in dict.fromkeys(ids)]
    with open(prior_path, encoding="utf-8", newline="") as f:
        prior = sorted({row["question_id"] for row in csv.DictReader(f)} & known)
    queue = [(i, "prior-reported") for i in prior]
    sample = load_json(sample_path)["sample"]
    for key in sorted(sample):
        queue += [(i, key) for i in sample[key]]
    return _dedupe(queue)


def _dedupe(queue):
    seen, out = set(), []
    for qid, stratum in queue:
        if qid not in seen:
            seen.add(qid)
            out.append((qid, stratum))
    return out


class Store:
    """Queue, data and the replayed event log. All access goes through one lock."""

    def __init__(self, data_path, counts_path, prior_path, sample_path, ann_dir, pass_name, ids_file=None, log_session=True):
        want = load_json(counts_path)["sha256"]
        self.sha = sha256_file(data_path)
        if self.sha != want:
            raise SystemExit(f"data SHA-256 {self.sha} does not match counts.json {want}; refusing to start")
        self.items = {q["question_id"]: q for q in load_json(data_path)}
        self.queue = build_queue(list(self.items.values()), prior_path, sample_path, ids_file)
        self.stratum = dict(self.queue)
        self.prior = {}
        with open(prior_path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                self.prior.setdefault(row["question_id"], []).append(row)
        self.pass_name = pass_name
        self.path = os.path.join(ann_dir, pass_name + ".jsonl")
        if log_session:
            os.makedirs(ann_dir, exist_ok=True)
        self.lock_ = threading.Lock()
        self.locks, self.labels = {}, {}
        for e in read_events(self.path):
            self._apply(e)
        if log_session:
            self._append({"event": "session", "data_sha256": self.sha, "queue_size": len(self.queue)})

    def _apply(self, e):
        qid = e.get("question_id")
        if e.get("event") == "lock":
            self.locks.setdefault(qid, e)
        elif e.get("event") == "label":
            self.labels.setdefault(qid, []).append(e)

    def _append(self, rec):
        rec = {"event": rec["event"], "pass": self.pass_name, "timestamp": now_iso(), "schema": SCHEMA,
               **{k: v for k, v in rec.items() if k != "event"}}
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        prefix = b""
        if os.path.exists(self.path) and os.path.getsize(self.path) > 0:
            with open(self.path, "rb") as f:  # repair a torn final line so the new record starts cleanly
                f.seek(-1, os.SEEK_END)
                prefix = b"" if f.read(1) == b"\n" else b"\n"
        with open(self.path, "ab") as f:
            f.write(prefix + line.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        return rec

    def _need(self, qid):
        if qid not in self.stratum:
            raise ToolError(404, "unknown question_id")
        return self.items[qid]

    def status(self, qid):
        if qid in self.labels:
            return "labelled"
        return "locked" if qid in self.locks else "new"

    def state(self):
        rows = [{"question_id": q, "stratum": s, "status": self.status(q)} for q, s in self.queue]
        first = next((i for i, r in enumerate(rows) if r["status"] != "labelled"), None)
        per = {}
        for r in rows:
            c = per.setdefault(r["stratum"], {"total": 0, "locked": 0, "labelled": 0})
            c["total"] += 1
            c["locked"] += r["status"] != "new"
            c["labelled"] += r["status"] == "labelled"
        return {"pass": self.pass_name, "queue": rows, "first_open": first, "per_stratum": per,
                "labelled": sum(r["status"] == "labelled" for r in rows), "total": len(rows)}

    def pre_lock(self, qid):
        """The only item data sent before the lock: no answer, no has_answer, no answer_session_ids."""
        q = self._need(qid)
        sessions = [{"session_id": sid, "date": date,
                     "turns": [{"role": t["role"], "content": t["content"]} for t in turns]}
                    for sid, date, turns in zip(q["haystack_session_ids"], q["haystack_dates"], q["haystack_sessions"])]
        out = {"question_id": qid, "question_type": q["question_type"], "question": q["question"],
               "question_date": q["question_date"], "sessions": sessions, "status": self.status(qid)}
        if qid in self.locks:
            lk = self.locks[qid]
            out["lock"] = {k: lk[k] for k in ("answer", "quote", "not_answerable", "timestamp")}
        return out

    def lock(self, qid, answer, quote, not_answerable):
        with self.lock_:
            self._need(qid)
            if qid in self.locks:
                raise ToolError(409, "answer already locked; it cannot be changed")
            answer = answer.strip() if isinstance(answer, str) else ""
            if not_answerable:
                answer = answer or NOT_ANSWERABLE_TEXT
            if not answer:
                raise ToolError(400, "answer must not be empty")
            quote = quote.strip() if isinstance(quote, str) else ""
            e = self._append({"event": "lock", "question_id": qid, "answer": answer, "quote": quote,
                              "not_answerable": bool(not_answerable)})
            self._apply(e)
        return self.pre_lock(qid)

    def reveal(self, qid):
        q = self._need(qid)
        if qid not in self.locks:
            raise ToolError(403, "lock your answer before the gold answer is revealed")
        ev = [{"session_id": sid, "turn": i}
              for sid, turns in zip(q["haystack_session_ids"], q["haystack_sessions"])
              for i, t in enumerate(turns) if t.get("has_answer")]
        labels = self.labels.get(qid, [])
        return {"question_id": qid, "gold": str(q["answer"]), "answer_session_ids": q["answer_session_ids"],
                "evidence_turns": ev,
                "prior_reports": [{k: r[k] for k in ("source_url", "reporter", "claim", "owner_response")}
                                  for r in self.prior.get(qid, [])],
                "label": labels[-1] if labels else None, "label_revisions": max(len(labels) - 1, 0)}

    def label(self, qid, body):
        with self.lock_:
            self._need(qid)
            if qid not in self.locks:
                raise ToolError(403, "lock an answer before labelling")
            code = body.get("code")
            if code not in CODES:
                raise ToolError(400, "unknown code")
            flag = bool(body.get("evidence_label"))
            if flag and code in ("OK", "EVIDENCE_LABEL"):
                raise ToolError(400, "evidence_label flag only goes with a non-OK, non-EVIDENCE_LABEL code")
            tier = body.get("tier") or None
            if code == "OK":
                tier = None
            elif tier not in TIERS:
                raise ToolError(400, "tier (definite or ambiguous) is required for a non-OK code")
            just = body.get("justification")
            just = just.strip() if isinstance(just, str) else ""
            if not just:
                raise ToolError(400, "justification is required")
            note = body.get("note")
            note = note.strip() if isinstance(note, str) else ""
            e = self._append({"event": "label", "question_id": qid, "code": code, "evidence_label": flag,
                              "tier": tier, "justification": just, "note": note})
            self._apply(e)
        return self.reveal(qid)

    def summary(self):
        s = self.state()
        latest = [v[-1] for v in self.labels.values()]
        return {"pass": self.pass_name, "queue": s["total"], "locked": len(self.locks), "labelled": len(self.labels),
                "per_code": dict(sorted(Counter(e["code"] for e in latest).items())),
                "evidence_label_flag": sum(bool(e["evidence_label"]) for e in latest),
                "per_tier": dict(sorted(Counter(e["tier"] for e in latest if e["tier"]).items())),
                "per_stratum": dict(sorted(s["per_stratum"].items()))}


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LongMemEval key audit</title>
<style>
:root{--bg:#fbfaf7;--fg:#1d1d1b;--mut:#6b6a64;--card:#fff;--line:#dcd9d0;--user:#e8f0fb;--asst:#f1efe8;--hit:#fff1a8;--acc:#1f5fbf;--bad:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#e8e6df;--mut:#9a988f;--card:#1f1f1c;--line:#38372f;--user:#1c2a40;--asst:#272620;--hit:#5a4b00;--acc:#7aa7f0;--bad:#f2837c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:8px 16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center}
main{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:20px;max-width:1200px;margin:0 auto;padding:16px}
@media (max-width:900px){main{grid-template-columns:1fr}}
.col{min-width:0}.read{max-width:75ch}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin-bottom:14px}
h2{font-size:1.05rem;margin:.2em 0 .5em}.mut{color:var(--mut);font-size:.9rem}
.sess h3{font-size:.95rem;margin:0 0 6px;color:var(--mut)}
.turn{padding:8px 12px;border-radius:6px;margin:6px 0;white-space:pre-wrap;overflow-wrap:anywhere;border-left:4px solid transparent}
.turn.user{background:var(--user);border-left-color:var(--acc)}.turn.assistant{background:var(--asst)}
.turn.hit{outline:3px solid var(--hit);background:var(--hit);color:inherit}
.role{display:block;font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;color:var(--mut)}
input[type=text],textarea,select{width:100%;font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
textarea{min-height:60px}label{display:block;margin:8px 0 2px;font-weight:600}label.inl{font-weight:400;display:flex;gap:6px;align-items:center}
button{font:inherit;padding:7px 14px;border-radius:6px;border:1px solid var(--acc);background:var(--acc);color:#fff;cursor:pointer}
button.sec{background:transparent;color:var(--acc)}button:disabled{opacity:.4;cursor:not-allowed}
.cmp{display:grid;grid-template-columns:1fr 1fr;gap:12px}.err{color:var(--bad);min-height:1.2em}
.codes label{font-weight:400;margin:4px 0}.codes small{color:var(--mut)}
.hide{display:none}table{border-collapse:collapse;font-size:.85rem}td,th{padding:2px 8px;border-bottom:1px solid var(--line);text-align:left}
</style></head><body>
<header><strong id="prog">...</strong><button class="sec" id="prev">Previous</button><button class="sec" id="next">Next</button>
<span class="mut" id="where"></span></header>
<main><div class="col read" id="left"></div><div class="col" id="right">
<div class="card"><h2>Progress by stratum</h2><div id="strata"></div></div>
<div class="card"><h2>Date helper</h2>
<label for="d1">Date A</label><input type="date" id="d1"><label for="d2">Date B</label><input type="date" id="d2">
<div id="diff" class="mut"></div><hr>
<label for="d3">Date</label><input type="date" id="d3"><label for="n">N</label><input type="number" id="n" value="1">
<select id="u"><option value="1">days</option><option value="7">weeks</option></select>
<select id="dir"><option value="-1">before</option><option value="1">after</option></select>
<div id="calc" class="mut"></div></div></div></main>
<script>
const DAYS=["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
const CODES=__CODES__;
let S=null,idx=0,cur=null,rev=null;
const $=id=>document.getElementById(id);
const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!==undefined)e.textContent=x;return e};
async function api(path,body){const r=await fetch(path,body?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:{});
  const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);return j}
function parseD(s){const m=/(\d{4})[\/-](\d{2})[\/-](\d{2})/.exec(s||"");return m?Date.UTC(+m[1],+m[2]-1,+m[3]):null}
function fmt(ms){const d=new Date(ms);return d.toISOString().slice(0,10)+" "+DAYS[d.getUTCDay()]}
function weekday(s){const t=parseD(s);return t===null?"":DAYS[new Date(t).getUTCDay()]}
async function refresh(){S=await api("/api/state");
  $("prog").textContent=S.labelled+" of "+S.total+" labelled";
  const t=el("table");t.innerHTML="<tr><th>stratum</th><th>locked</th><th>labelled</th><th>total</th></tr>";
  for(const k of Object.keys(S.per_stratum).sort()){const c=S.per_stratum[k],r=el("tr");
    [k,c.locked,c.labelled,c.total].forEach(v=>r.appendChild(el("td","",v)));t.appendChild(r)}
  $("strata").replaceChildren(t)}
async function show(i){if(!S.queue.length){$("left").textContent="Queue is empty.";return}
  idx=Math.max(0,Math.min(i,S.queue.length-1));const q=S.queue[idx];
  cur=await api("/api/item/"+encodeURIComponent(q.question_id));rev=null;
  if(cur.status!=="new")rev=await api("/api/reveal/"+encodeURIComponent(q.question_id));
  $("where").textContent="item "+(idx+1)+" of "+S.total+" - "+q.question_id+" - "+q.stratum+" - "+cur.status;render()}
function render(){const L=$("left");L.replaceChildren();
  const hits=new Set((rev?rev.evidence_turns:[]).map(e=>e.session_id+"#"+e.turn));
  const c=el("div","card");c.appendChild(el("h2","","Question ("+cur.question_type+")"));
  c.appendChild(el("div","",cur.question));
  c.appendChild(el("div","mut","Question date: "+cur.question_date+(weekday(cur.question_date)?" - "+weekday(cur.question_date):"")));
  L.appendChild(c);
  cur.sessions.forEach(s=>{const d=el("div","card sess");
    d.appendChild(el("h3","",s.date+(weekday(s.date)?" - "+weekday(s.date):"")+" - "+s.session_id));
    s.turns.forEach((t,i)=>{const x=el("div","turn "+t.role+(hits.has(s.session_id+"#"+i)?" hit":""));
      x.appendChild(el("span","role",t.role+(hits.has(s.session_id+"#"+i)?" - has_answer":"")));x.appendChild(document.createTextNode(t.content));d.appendChild(x)});
    L.appendChild(d)});
  L.appendChild(cur.lock?reviewForm():lockForm())}
function lockForm(){const f=el("div","card");f.appendChild(el("h2","","Your answer (gold is hidden until you lock)"));
  f.innerHTML+='<label for="ans">My answer</label><textarea id="ans"></textarea><label for="quo">Supporting quote</label><textarea id="quo"></textarea>'+
  '<label class="inl"><input type="checkbox" id="na"> '+"Not answerable from this evidence"+'</label>';
  const b=el("button","","Lock answer and reveal gold");b.disabled=true;const e=el("div","err");f.append(b,e);
  setTimeout(()=>{const a=$("ans"),na=$("na");
    const upd=()=>b.disabled=!a.value.trim();
    a.oninput=upd;na.onchange=()=>{if(na.checked&&!a.value.trim())a.value="Not answerable from this evidence";upd()};
    b.onclick=async()=>{b.disabled=true;try{await api("/api/lock",{question_id:cur.question_id,answer:a.value,quote:$("quo").value,not_answerable:na.checked});
      S.queue[idx].status="locked";await show(idx);await refresh()}catch(x){e.textContent=x.message;upd()}}},0);return f}
function reviewForm(){const w=el("div");const f=el("div","card");f.appendChild(el("h2","","Compare"));
  const g=el("div","cmp");const a=el("div"),b=el("div");
  a.append(el("strong","","My locked answer"),el("div","",cur.lock.answer),el("div","mut","Quote: "+(cur.lock.quote||"(none)")));
  b.append(el("strong","","Gold answer"),el("div","",rev.gold),el("div","mut","answer_session_ids: "+rev.answer_session_ids.join(", ")));
  g.append(a,b);f.appendChild(g);
  if(rev.prior_reports.length){f.appendChild(el("h2","","Prior reports"));
    rev.prior_reports.forEach(p=>f.appendChild(el("div","mut",p.reporter+" ("+p.source_url+"): "+p.claim+" | owner: "+p.owner_response)))}
  w.appendChild(f);
  const L=rev.label,k=el("div","card codes");k.appendChild(el("h2","","Label"+(rev.label_revisions?" (revised "+rev.label_revisions+"x)":"")));
  Object.entries(CODES).forEach(([c,m])=>{const l=el("label");l.innerHTML='<input type="radio" name="code" value="'+c+'"> <b>'+c+'</b> <small>'+m+'</small>';k.appendChild(l)});
  k.insertAdjacentHTML("beforeend",'<div id="tierbox"><label for="tier">Tier</label><select id="tier"><option value="">choose</option><option>definite</option><option>ambiguous</option></select></div>'+
   '<label class="inl" id="evbox"><input type="checkbox" id="ev"> evidence labels also wrong or incomplete</label>'+
   '<label for="just">Justification (one line)</label><input type="text" id="just"><label for="note">Note (optional)</label><textarea id="note"></textarea>');
  const sv=el("button","","Save and next"),er=el("div","err");k.append(sv,er);w.appendChild(k);
  setTimeout(()=>{const sync=()=>{const c=(document.querySelector("input[name=code]:checked")||{}).value;
      $("tierbox").classList.toggle("hide",!c||c==="OK");$("evbox").classList.toggle("hide",!c||c==="OK"||c==="EVIDENCE_LABEL")};
    document.querySelectorAll("input[name=code]").forEach(r=>r.onchange=sync);
    if(L){document.querySelector("input[name=code][value="+L.code+"]").checked=true;$("tier").value=L.tier||"";$("ev").checked=L.evidence_label;$("just").value=L.justification;$("note").value=L.note}
    sync();
    sv.onclick=async()=>{const c=(document.querySelector("input[name=code]:checked")||{}).value;
      try{await api("/api/label",{question_id:cur.question_id,code:c,tier:$("tier").value,evidence_label:$("ev").checked&&!$("evbox").classList.contains("hide"),justification:$("just").value,note:$("note").value});
        await refresh();await show(Math.min(idx+1,S.queue.length-1))}catch(x){er.textContent=x.message}}},0);return w}
$("prev").onclick=()=>show(idx-1);$("next").onclick=()=>show(idx+1);
function dateHelp(){const a=parseD($("d1").value),b=parseD($("d2").value);
  $("diff").textContent=(a!==null?fmt(a):"")+(b!==null?"  /  "+fmt(b):"");
  if(a!==null&&b!==null){const n=Math.round((b-a)/864e5),m=Math.abs(n);
    $("diff").textContent+="  |  "+n+" days = "+Math.floor(m/7)+" weeks + "+(m%7)+" days"+(n<0?" (B is earlier)":"")}
  const c=parseD($("d3").value),n=+$("n").value;
  $("calc").textContent=c!==null&&!isNaN(n)?fmt(c+n*(+$("u").value)*(+$("dir").value)*864e5):""}
["d1","d2","d3","n","u","dir"].forEach(i=>$(i).oninput=dateHelp);
(async()=>{await refresh();await show(S.first_open===null?0:S.first_open)})().catch(e=>{$("left").textContent=e.message});
</script></body></html>
"""


def make_handler(store, port_getter):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, status, body, ctype="application/json; charset=utf-8"):
            raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _guard(self):
            # Reject DNS-rebinding and cross-site requests: only our own origin may talk to us.
            host = self.headers.get("Host", "")
            if host != f"{HOST}:{port_getter()}":
                raise ToolError(403, "bad Host header")
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{host}":
                raise ToolError(403, "bad Origin")

        def _route(self, method):
            try:
                self._guard()
                path = self.path.split("?", 1)[0]
                if method == "GET" and path == "/":
                    return self._send(200, PAGE.replace("__CODES__", json.dumps(CODES)).encode("utf-8"),
                                      "text/html; charset=utf-8")
                if method == "GET" and path == "/api/state":
                    return self._send(200, store.state())
                m = re.fullmatch(r"/api/(item|reveal)/([^/]+)", path)
                if method == "GET" and m:
                    qid = unquote(m.group(2))
                    return self._send(200, store.pre_lock(qid) if m.group(1) == "item" else store.reveal(qid))
                if method == "POST" and path in ("/api/lock", "/api/label"):
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > MAX_BODY:
                        raise ToolError(413, "body too large")
                    try:
                        body = json.loads(self.rfile.read(n) or b"{}")
                    except ValueError:
                        raise ToolError(400, "invalid JSON")
                    if not isinstance(body, dict):
                        raise ToolError(400, "body must be an object")
                    qid = body.get("question_id")
                    if path == "/api/lock":
                        out = store.lock(qid, body.get("answer"), body.get("quote"), body.get("not_answerable"))
                    else:
                        out = store.label(qid, body)
                    return self._send(200, out)
                raise ToolError(404, "not found")
            except ToolError as e:
                self._send(e.status, {"error": str(e)})

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

    return Handler


def make_server(store, port):
    box = {}
    server = ThreadingHTTPServer((HOST, port), make_handler(store, lambda: box["port"]))
    box["port"] = server.server_address[1]
    server.daemon_threads = True
    return server


def parse_args(argv):
    p = argparse.ArgumentParser(description="LongMemEval key audit annotation tool")
    p.add_argument("--pass", dest="pass_name", required=True, help="pass name, e.g. first")
    p.add_argument("--ids-file", help="JSON list of question ids; overrides the queue")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--summary", action="store_true", help="print counts only and exit")
    p.add_argument("--data", default=os.path.join(ROOT, "data", "longmemeval_oracle.json"))
    p.add_argument("--counts", default=os.path.join(ROOT, "counts.json"))
    p.add_argument("--prior", default=os.path.join(ROOT, "prior_reports.csv"))
    p.add_argument("--sample", default=os.path.join(ROOT, "sample_v01.json"))
    p.add_argument("--annotations", default=os.path.join(ROOT, "annotations"))
    a = p.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.pass_name):
        p.error("--pass may contain only letters, digits, _ and -")
    if a.port == 8765:
        p.error("port 8765 is reserved")
    return a


def main(argv=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    store = Store(a.data, a.counts, a.prior, a.sample, a.annotations, a.pass_name, a.ids_file, log_session=not a.summary)
    if a.summary:
        print(json.dumps(store.summary(), indent=2))
        return
    server = make_server(store, a.port)
    print(f"http://{HOST}:{server.server_address[1]}  (pass {a.pass_name}, {len(store.queue)} items)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
