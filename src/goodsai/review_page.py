"""Operator review screen served by the HTTP API (PRODUCT-001).

A single self-contained page: the operator enters a card, the page calls the same
``POST /predict`` as any client, highlights every evidence span in the original text
and records the operator decision for each attribute. Decisions are exported as JSONL
in the browser; the server stores nothing and the prediction path is not changed.
"""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# Shown to the operator next to an abstain or a rejected candidate.
REASONS = {
    "not_found_by_rules": "В тексте не нашлось подходящего фрагмента. Если значение в тексте есть — заполните вручную, это кандидат на новое правило; если нет — запросите у продавца.",
    "conflicting_evidence": "В карточке несколько несовместимых значений. Выберите верное по первоисточнику — конфликт часто означает ошибку продавца.",
    "invalid_text_only_input": "Строка нарушает формат входа: уберите готовые поля каталога (vendor, model, params) и проверьте типы.",
    "relation_accessory_product": "Значение относится к аксессуару, а не к самому товару.",
    "relation_foreign_entity": "Значение относится к другому товару или бренду, упомянутому в тексте.",
    "relation_bundle_item": "Значение относится к предмету из комплекта.",
    "relation_other_object": "Значение описывает другой объект.",
    "relation_negated": "Рядом стоит отрицание — значение не подтверждено.",
    "relation_nonvisible_evidence": "Цитата находится в невидимой части HTML.",
    "relation_instruction_or_example": "Фрагмент — инструкция или пример, а не характеристика товара.",
    "relation_name_token": "Слово входит в название, а не описывает характеристику.",
    "relation_material_not_color": "Это материал, а не цвет.",
    "relation_unknown_color_modifier": "Неизвестный оттенок цвета — нужна ручная проверка.",
    "llm_skipped_no_signal": "LLM не вызывалась: в тексте нет формы, которую можно подтвердить цитатой.",
    "llm_not_found": "LLM не нашла значение в тексте.",
    "conflicting_llm_evidence": "LLM предложила несколько разных значений — выберите вручную.",
    "llm_blocked_by_data_policy": "Карточка не отправлялась в LLM по политике данных.",
}
REASON_PREFIXES = {
    "relation_": "Кандидат найден, но относится не к самому товару — проверьте вручную.",
    "verifier_": "Кандидат не прошёл проверку (единицы, диапазон или роль значения).",
    "llm_": "LLM не дала подтверждённого значения или была недоступна — результат правил не изменён.",
}

PAGE = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GoodsAI — проверка карточки</title>
<link rel="icon" href="data:,">
<style>
:root{--ink:#17212b;--soft:#4b5563;--line:#d6d3c8;--bg:#f4f3ee;--card:#fbfaf6;--blue:#22599a;--blue-t:#dce7f3;--orange:#b4501c;--orange-t:#f6e2d3;--green:#2f6b3a;--green-t:#dcefdc;--mark:#fde9a8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
header{padding:16px 24px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
header h1{font-size:20px;margin:0}
header span{color:var(--soft)}
header a{color:var(--blue)}
main{display:grid;grid-template-columns:minmax(300px,420px) 1fr;gap:20px;padding:20px 24px;max-width:1500px}
@media (max-width:900px){main{grid-template-columns:1fr}}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
h2{font-size:16px;margin:0 0 12px}
label{display:block;font-weight:600;margin:10px 0 4px}
input,select,textarea{width:100%;font:inherit;padding:8px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink)}
textarea{min-height:110px;resize:vertical}
button{font:inherit;padding:6px 10px;border-radius:6px;border:1px solid var(--line);background:#fff;color:var(--ink);cursor:pointer}
button.primary{background:var(--blue);border-color:var(--blue);color:#fff;font-weight:600}
button:disabled{opacity:.5;cursor:not-allowed}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.muted{color:var(--soft)}
.small{font-size:13px}
.msg{padding:10px 12px;border-radius:6px;margin:10px 0}
.msg.err{background:var(--orange-t);border:1px solid #e7c3a8}
.msg.info{background:var(--blue-t);border:1px solid #b9cde6}
.text{white-space:pre-wrap;word-break:break-word;background:#fff;border:1px solid var(--line);border-radius:6px;padding:10px;margin:4px 0 12px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:14px}
mark{background:var(--mark);border-radius:3px;padding:0 1px;cursor:pointer}
mark.auto{background:var(--green-t)}
mark.focus{outline:2px solid var(--blue);outline-offset:1px}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;vertical-align:top;padding:8px;border-bottom:1px solid var(--line)}
th{font-size:13px;color:var(--soft);font-weight:600}
tr.focus td{background:var(--blue-t)}
td:last-child{min-width:300px}
td .row{gap:6px}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.b-review{background:var(--mark)}
.b-auto{background:var(--green-t);color:var(--green)}
.b-abstain{background:#e6e4dc}
.st{font-size:13px;margin-top:4px}
.st.done{color:var(--green);font-weight:600}
.st.rej{color:var(--orange);font-weight:600}
.edit{display:flex;gap:6px;margin-top:6px}
.edit input{width:140px}
.value{font-weight:600}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px}
details{margin-top:12px}
</style>
</head>
<body>
<header>
<h1>GoodsAI — проверка карточки</h1>
<span>Сервис предлагает значения с цитатой, решение принимает оператор.</span>
<a href="docs">API</a>
</header>
<main>
<section aria-labelledby="in-h">
<h2 id="in-h">1. Карточка</h2>
<div class="row small"><span class="muted">Пример:</span>
<button type="button" data-example="phone">смартфон</button>
<button type="button" data-example="conflict">конфликт</button>
<button type="button" data-example="kettle">чайник</button></div>
<label for="category">Категория</label>
<select id="category">
<option value="761">761 — смартфоны</option>
<option value="482">482 — электрочайники</option>
<option value="999">999 — нет в схеме (для проверки отказа)</option>
</select>
<label for="sku">SKU</label>
<input id="sku" autocomplete="off">
<label for="title">Название (title)</label>
<input id="title" autocomplete="off">
<label for="description">Описание (description)</label>
<textarea id="description"></textarea>
<div class="row" style="margin-top:12px"><button type="button" class="primary" id="check">Проверить</button>
<span class="muted small" id="busy" aria-live="polite"></span></div>
<div id="error" role="alert"></div>
<h2 style="margin-top:20px">3. Выгрузка решений</h2>
<p class="small muted" id="export-info">Пока ничего не добавлено.</p>
<div class="row"><button type="button" id="add" disabled>Добавить карточку в выгрузку</button>
<button type="button" id="download" disabled>Скачать JSONL</button></div>
<p class="small muted">Решения хранятся только в этой вкладке браузера и скачиваются файлом; сервер их не сохраняет.</p>
</section>
<section aria-labelledby="out-h">
<h2 id="out-h">2. Предложения сервиса</h2>
<div id="empty" class="muted">Заполните карточку или выберите пример и нажмите «Проверить».</div>
<div id="result" hidden>
<div class="row small muted" id="summary"></div>
<div class="small muted" style="margin-top:10px">Текст показан как в карточке, включая HTML-разметку; подсвечены цитаты. Нажмите на подсветку или строку таблицы.</div>
<div id="texts"></div>
<table><thead><tr><th>Атрибут</th><th>Предложение</th><th>Основание</th><th>Решение оператора</th></tr></thead><tbody id="rows"></tbody></table>
<details><summary class="small">Ответ API (JSON)</summary><pre class="text" id="raw"></pre></details>
</div>
</section>
</main>
<script>
"use strict";
const LABELS = {brand:"Бренд", model:"Модель", storage_gb:"Встроенная память", ram_gb:"Оперативная память", screen_inches:"Диагональ экрана", battery_mah:"Ёмкость аккумулятора", color:"Цвет", capacity_l:"Объём", power_w:"Мощность"};
const UNITS = {GB:"ГБ", inch:"дюйма", mAh:"мА·ч", L:"л", W:"Вт"};
const REASONS = __REASONS__;
const REASON_PREFIXES = __REASON_PREFIXES__;
const HTTP_ERRORS = {
  400: "Тело запроса не является JSON-объектом в UTF-8.",
  413: "Карточка слишком большая: сократите описание.",
  415: "Сервис принимает только application/json.",
  422: "Карточка не прошла проверку формата: нужны sku_id и title, готовые поля каталога запрещены.",
  500: "Внутренняя ошибка извлечения. Повторите запрос и сообщите команде время."
};
const EXAMPLES = {
  phone: {category_id:"761", sku_id:"demo-phone", title:"Смартфон Samsung Nova X86 12/512GB белый", description:"Экран 6,4 дюйма. Аккумулятор 4600 мАч."},
  conflict: {category_id:"761", sku_id:"demo-conflict", title:"Смартфон Samsung Nova X86 8/256GB черный", description:"<p>Встроенная память 128 ГБ.</p><p>Экран&nbsp;6,1 дюйма.</p>"},
  kettle: {category_id:"482", sku_id:"demo-kettle", title:"Электрочайник Vexa KT-17 1,7 л 2200 Вт серебристый", description:""}
};
const $ = (id) => document.getElementById(id);
const el = (tag, attrs, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v; else if (k.startsWith("on")) node.addEventListener(k.slice(2), v); else node.setAttribute(k, v);
  }
  for (const kid of kids) if (kid !== null && kid !== undefined) node.append(kid);
  return node;
};
let current = null;
const exported = [];

function reasonText(code) {
  if (REASONS[code]) return REASONS[code];
  for (const [prefix, text] of Object.entries(REASON_PREFIXES)) if (code.startsWith(prefix)) return text;
  return "Причина: " + code;
}
function shown(a) { return a.value === null ? "—" : a.value + (a.unit ? " " + (UNITS[a.unit] || a.unit) : ""); }
function fillForm(example) {
  $("category").value = example.category_id; $("sku").value = example.sku_id;
  $("title").value = example.title; $("description").value = example.description || "";
}
function product() {
  const p = {schema_version: "0.1", sku_id: $("sku").value.trim() || ("op-" + Date.now()),
             category_id: $("category").value, title: $("title").value};
  const d = $("description").value; if (d.trim()) p.description = d;
  return p;
}
function showError(text) { $("error").replaceChildren(text ? el("div", {class: "msg err"}, text) : ""); }

async function check() {
  showError(""); $("busy").textContent = "Запрос…"; $("check").disabled = true;
  const request = product();
  try {
    const response = await fetch("predict", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(request)});
    let body = null; try { body = await response.json(); } catch (e) { body = null; }
    if (!response.ok) {
      const code = body && body.error ? body.error.code : "http_" + response.status;
      showError((HTTP_ERRORS[response.status] || "Ошибка запроса.") + " Код: " + code + ".");
      return;
    }
    start(request, body);
  } catch (e) {
    showError("Сервис недоступен. Проверьте соединение и повторите.");
  } finally { $("busy").textContent = ""; $("check").disabled = false; }
}

function start(request, response) {
  const rows = response.attributes.map((a) => ({a, action: a.decision === "auto_accept" ? "accepted" : null,
                                                  final: a.decision === "auto_accept" ? a.value : null, editing: false}));
  current = {request, response, rows, focus: null};
  $("empty").hidden = true; $("result").hidden = false;
  $("raw").textContent = JSON.stringify(response, null, 2);
  render();
}

function render() {
  const {request, response, rows} = current;
  const summary = $("summary"); summary.replaceChildren();
  if (response.status === "unsupported_category") {
    summary.append(el("div", {class: "msg info"}, "Категория " + request.category_id + " не поддерживается: атрибутов нет. Карточку нужно заполнить вручную."));
  } else {
    const found = rows.filter((r) => r.a.value !== null).length, auto = rows.filter((r) => r.a.decision === "auto_accept").length;
    const done = rows.filter((r) => r.action).length;
    summary.append(el("span", {}, "Найдено " + found + " из " + rows.length + (auto ? ", принято автоматически " + auto : "") + ". Решено оператором: " + done + " из " + rows.length + "."));
  }
  renderTexts(); renderRows();
  $("add").disabled = !rows.every((r) => r.action) ;
}

function renderTexts() {
  const box = $("texts"); box.replaceChildren();
  for (const field of ["title", "description"]) {
    const text = current.request[field]; if (!text) continue;
    const chars = Array.from(text); const owners = chars.map(() => []);
    current.rows.forEach((r, i) => {
      const e = r.a.evidence; if (!e || e.field !== field) return;
      for (let k = e.start; k < e.end && k < chars.length; k++) owners[k].push(i);
    });
    const block = el("div", {class: "text", "aria-label": field});
    let k = 0;
    while (k < chars.length) {
      const key = owners[k].join(","); let j = k;
      while (j < chars.length && owners[j].join(",") === key) j++;
      const piece = chars.slice(k, j).join("");
      if (!owners[k].length) block.append(piece);
      else {
        const idx = owners[k];
        const names = idx.map((i) => LABELS[current.rows[i].a.attribute] || current.rows[i].a.attribute).join(", ");
        const cls = (idx.every((i) => current.rows[i].a.decision === "auto_accept") ? "auto" : "") + (idx.includes(current.focus) ? " focus" : "");
        block.append(el("mark", {class: cls.trim(), title: names, onclick: () => focus(idx[0])}, piece));
      }
      k = j;
    }
    box.append(el("div", {class: "small muted"}, field), block);
  }
}

function badge(a) {
  if (a.decision === "auto_accept") return el("span", {class: "badge b-auto"}, "принято автоматически");
  if (a.decision === "review") return el("span", {class: "badge b-review"}, "нужна проверка");
  return el("span", {class: "badge b-abstain"}, "значения нет");
}

function status(r) {
  const map = {accepted: ["принято", "done"], corrected: ["исправлено → " + r.final, "done"], rejected: ["отклонено", "rej"],
               filled: ["заполнено вручную → " + r.final, "done"], confirmed_empty: ["подтверждено: значения нет", "done"]};
  if (!r.action) return el("div", {class: "st muted"}, "ожидает решения");
  const [text, cls] = map[r.action]; return el("div", {class: "st " + cls}, text);
}

function renderRows() {
  const body = $("rows"); body.replaceChildren();
  current.rows.forEach((r, i) => {
    const a = r.a; const found = a.value !== null;
    const proposal = el("td", {}, el("div", {class: "value"}, shown(a)), badge(a),
                        found && a.confidence !== null ? el("div", {class: "small muted"}, "score " + a.confidence + " (эвристика, не вероятность)") : null);
    const basis = el("td", {class: "small"});
    if (a.evidence) basis.append(el("div", {}, "«" + a.evidence.text + "»"), el("div", {class: "muted"}, a.evidence.field + " [" + a.evidence.start + ":" + a.evidence.end + "], " + (a.method === "llm" ? "LLM" : "правило")));
    for (const code of a.reason_codes) basis.append(el("div", {}, reasonText(code)));
    const actions = el("td", {});
    const buttons = el("div", {class: "row"});
    if (found) {
      buttons.append(el("button", {type: "button", onclick: () => decide(i, "accepted", a.value)}, "Принять"),
                     el("button", {type: "button", onclick: () => edit(i)}, "Исправить"),
                     el("button", {type: "button", onclick: () => decide(i, "rejected", null)}, "Отклонить"));
    } else {
      buttons.append(el("button", {type: "button", onclick: () => edit(i)}, "Заполнить"),
                     el("button", {type: "button", onclick: () => decide(i, "confirmed_empty", null)}, "Значения нет"));
    }
    actions.append(buttons);
    if (r.editing) {
      const input = el("input", {"aria-label": "Значение " + (LABELS[a.attribute] || a.attribute), value: r.final || a.value || ""});
      const save = () => { const v = input.value.trim(); if (v) decide(i, found ? "corrected" : "filled", v); };
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") save(); });
      actions.append(el("div", {class: "edit"}, input, el("button", {type: "button", onclick: save}, "Сохранить")));
      setTimeout(() => input.focus(), 0);
    }
    actions.append(status(r));
    const tr = el("tr", {class: current.focus === i ? "focus" : "", onclick: (e) => { if (e.target.tagName !== "BUTTON" && e.target.tagName !== "INPUT") focus(i); }},
                  el("td", {}, el("div", {class: "value"}, LABELS[a.attribute] || a.attribute), el("code", {}, a.attribute)), proposal, basis, actions);
    body.append(tr);
  });
}

function focus(i) { current.focus = current.focus === i ? null : i; render(); }
function edit(i) { current.rows.forEach((r, k) => { r.editing = k === i ? !r.editing : false; }); render(); }
function decide(i, action, value) { const r = current.rows[i]; r.action = action; r.final = value; r.editing = false; render(); }

function addToExport() {
  const {request, response, rows} = current; const at = new Date().toISOString();
  for (const r of rows) exported.push({sku_id: response.sku_id, category_id: response.category_id, run_id: response.run_id,
    attribute: r.a.attribute, proposed_value: r.a.value, proposed_unit: r.a.unit, service_decision: r.a.decision,
    confidence: r.a.confidence, evidence: r.a.evidence, reason_codes: r.a.reason_codes,
    operator_action: r.action, final_value: r.final, decided_at: at});
  const cards = new Set(exported.map((x) => x.sku_id)).size;
  $("export-info").textContent = "В выгрузке: " + exported.length + " решений по " + cards + " карточкам.";
  $("download").disabled = false; $("add").disabled = true;
}

function download() {
  const blob = new Blob([exported.map((x) => JSON.stringify(x)).join("\n") + "\n"], {type: "application/x-ndjson"});
  const link = el("a", {href: URL.createObjectURL(blob), download: "goodsai-review-" + new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-") + ".jsonl"});
  document.body.append(link); link.click(); link.remove();
}

document.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", () => fillForm(EXAMPLES[b.dataset.example])));
$("check").addEventListener("click", check);
$("add").addEventListener("click", addToExport);
$("download").addEventListener("click", download);
fillForm(EXAMPLES.phone);
</script>
</body>
</html>
"""

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                               "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def render() -> str:
    import json
    return (PAGE.replace("__REASONS__", json.dumps(REASONS, ensure_ascii=False))
                .replace("__REASON_PREFIXES__", json.dumps(REASON_PREFIXES, ensure_ascii=False)))


def register(app: FastAPI) -> None:
    page = render()

    @app.get("/review", response_class=HTMLResponse, summary="Экран проверки карточки для оператора")
    def review_page():
        return HTMLResponse(page, headers=SECURITY_HEADERS)
