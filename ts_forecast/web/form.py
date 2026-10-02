from __future__ import annotations

import html

from ..core.config import ForecastConfig
from ..core.models import model_catalog

CFG = ForecastConfig()
MODEL_OPTIONS = model_catalog(CFG.ets_trends, CFG.ets_seasonals)


def render_form(
    selected_models: list[str] | None = None,
    use_all: bool = True,
    fill_missing_with_mean: bool = False,
) -> str:
    selected = set(selected_models or [])
    options_html = "\n".join(
        f'<option value="{html.escape(name)}"{" selected" if (use_all or name in selected) else ""}>'
        f"{html.escape(name)}</option>"
        for name in MODEL_OPTIONS
    )
    use_all_checked = " checked" if use_all else ""
    fill_checked = " checked" if fill_missing_with_mean else ""
    return f"""<!doctype html>
<meta charset="utf-8">
<title>OForecast</title>
<style>
body {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; padding: 24px; }}
textarea {{ width: 100%; max-width: 900px; height: 320px; }}
select {{ width: 100%; max-width: 900px; height: 180px; }}
pre {{ white-space: pre-wrap; background: #f6f6f6; padding: 12px; border: 1px solid #ddd; }}
#scroll-top {{
  position: fixed;
  right: 24px;
  bottom: 24px;
  width: 44px;
  height: 44px;
  border: 1px solid #999;
  background: #fff;
  color: #111;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  display: none;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
}}
#scroll-top.is-visible {{ display: block; }}
</style>
<h1>OForecast</h1>
<form id="forecast-form" method="post" action="/forecast/form">
  <textarea id="raw" name="raw" placeholder="Paste data here (same format as data.txt)"></textarea>
  <div>
    <label><input type="checkbox" id="fill_missing_with_mean" name="fill_missing_with_mean"{fill_checked}> Fill missing recognized periods by interpolation</label>
  </div>
  <div>
    <label><input type="checkbox" id="use_all" name="use_all"{use_all_checked}> Use all models</label>
  </div>
  <div>
    <select id="models" name="models" multiple>
      {options_html}
    </select>
  </div>
  <br><button id="run-btn" type="submit">Run forecast</button>
</form>
<div style="display: flex; align-items: center; gap: 12px;">
  <h2 style="margin: 0;">Progress</h2>
  <button id="copy-log" type="button">Copy output</button>
  <button id="cancel-run" type="button" disabled>Cancel</button>
  <span id="timer">00:00</span>
</div>
<pre id="log"></pre>
<button id="scroll-top" type="button" aria-label="Back to top" title="Back to top">↑</button>
<script>
const form = document.getElementById("forecast-form");
const log = document.getElementById("log");
const copyBtn = document.getElementById("copy-log");
const cancelBtn = document.getElementById("cancel-run");
const timer = document.getElementById("timer");
const rawInput = document.getElementById("raw");
const modelsSelect = document.getElementById("models");
const useAll = document.getElementById("use_all");
const fillMissing = document.getElementById("fill_missing_with_mean");
const scrollTopBtn = document.getElementById("scroll-top");
let abortController = null;
let timerId = null;
let startTs = 0;
let runId = null;
const syncModels = () => {{
  modelsSelect.disabled = useAll.checked;
}};
useAll.addEventListener("change", syncModels);
syncModels();
const syncScrollTop = () => {{
  scrollTopBtn.classList.toggle("is-visible", window.scrollY > window.innerHeight / 2);
}};
window.addEventListener("scroll", syncScrollTop, {{ passive: true }});
scrollTopBtn.addEventListener("click", () => {{
  window.scrollTo({{ top: 0, behavior: "smooth" }});
}});
syncScrollTop();
form.addEventListener("submit", async (e) => {{
  e.preventDefault();
  log.textContent = "";
  if (timerId) clearInterval(timerId);
  timerId = null;
  cancelBtn.disabled = false;
  startTs = Date.now();
  timer.textContent = "00:00";
  timerId = setInterval(() => {{
    const elapsed = Math.floor((Date.now() - startTs) / 1000);
    const minutes = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const seconds = String(elapsed % 60).padStart(2, "0");
    timer.textContent = `${{minutes}}:${{seconds}}`;
  }}, 1000);
  const selected = Array.from(modelsSelect.selectedOptions).map((o) => o.value);
  runId = (crypto.randomUUID && crypto.randomUUID()) || (Date.now().toString(36) + Math.random().toString(36).slice(2));
  const payload = {{
    raw: rawInput.value,
    models: selected,
    use_all: useAll.checked,
    fill_missing_with_mean: fillMissing.checked,
    run_id: runId
  }};
  abortController = new AbortController();
  try {{
    const resp = await fetch("/forecast/stream", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload),
      signal: abortController.signal
    }});
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {{
      const {{ value, done }} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {{ stream: true }});
      const parts = buffer.split("\\n\\n");
      buffer = parts.pop();
      for (const part of parts) {{
        const lines = part.split("\\n");
        for (const line of lines) {{
          if (!line.startsWith("data:")) continue;
          let msg = line.slice(5);
          if (msg.startsWith(" ")) msg = msg.slice(1);
          if (msg === "[done]") continue;
          log.textContent += msg + "\\n";
          log.scrollTop = log.scrollHeight;
        }}
      }}
    }}
  }} catch (err) {{
    if (err.name === "AbortError") {{
      log.textContent += "cancelled by user\\n";
    }} else {{
      log.textContent += `error: ${{err}}\\n`;
    }}
  }} finally {{
    abortController = null;
    cancelBtn.disabled = true;
    if (timerId) clearInterval(timerId);
    timerId = null;
    runId = null;
  }}
}});
cancelBtn.addEventListener("click", async () => {{
  if (abortController) {{
    abortController.abort();
  }}
  if (runId) {{
    try {{
      await fetch("/forecast/cancel", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ run_id: runId }})
      }});
    }} catch (err) {{}}
  }}
}});
copyBtn.addEventListener("click", async () => {{
  const text = log.textContent.trim();
  if (!text) return;
  try {{
    await navigator.clipboard.writeText(text);
  }} catch (err) {{
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "absolute";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    document.body.removeChild(area);
  }}
}});
</script>
"""
