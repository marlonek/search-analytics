import json
import datetime
from pathlib import Path
from collections import defaultdict

def load_data():
    p = Path("data/clicks.json")
    if not p.exists():
        return {"clicks": [], "last_keywords": {}}
    return json.loads(p.read_text(encoding="utf-8"))

def load_config():
    p = Path("config/projects.json")
    if not p.exists():
        return {"projects": []}
    return json.loads(p.read_text(encoding="utf-8"))

def generate():
    data = load_data()
    config = load_config()
    clicks = data.get("clicks", [])
    projects = config.get("projects", [])
    today = datetime.date.today().isoformat()

    # Stats per keyword
    kw_counts = defaultdict(int)
    kw_ok = defaultdict(int)
    for c in clicks:
        kw_counts[c["keyword"]] += 1
        if c.get("status") == "ok":
            kw_ok[c["keyword"]] += 1

    # Stats per project
    proj_stats = {}
    for p in projects:
        pid = p["id"]
        total = sum(1 for c in clicks if c["project_id"] == pid)
        today_cnt = sum(1 for c in clicks if c["project_id"] == pid and c["date"] == today)
        ok_cnt = sum(1 for c in clicks if c["project_id"] == pid and c.get("status") == "ok")
        proj_stats[pid] = {"total": total, "today": today_cnt, "ok": ok_cnt,
                           "limit": p["daily_clicks"], "domain": p["domain"], "name": p["name"]}

    # Last 7 days
    days = []
    day_counts = []
    for i in range(6, -1, -1):
        d = (datetime.date.today() - datetime.timedelta(days=i)).isoformat()
        days.append(d[5:])  # MM-DD
        day_counts.append(sum(1 for c in clicks if c["date"] == d and c.get("status") == "ok"))

    # Recent logs (last 30)
    recent = sorted(clicks, key=lambda x: x.get("timestamp",""), reverse=True)[:30]

    # Build keyword rows
    sorted_kw = sorted(kw_counts.items(), key=lambda x: x[1], reverse=True)
    max_cnt = sorted_kw[0][1] if sorted_kw else 1

    kw_rows = ""
    for kw, cnt in sorted_kw[:20]:
        ok = kw_ok[kw]
        pct = round(cnt / max_cnt * 100)
        status_color = "#22c55e" if ok == cnt else "#f59e0b"
        kw_rows += f"""
        <tr>
          <td style="padding:10px 12px;font-size:13px;color:#1e293b;">{kw}</td>
          <td style="padding:10px 12px;">
            <div style="display:flex;align-items:center;gap:8px;">
              <div style="flex:1;height:6px;background:#e2e8f0;border-radius:3px;">
                <div style="width:{pct}%;height:6px;background:#3b82f6;border-radius:3px;"></div>
              </div>
              <span style="font-size:13px;font-weight:600;min-width:20px;text-align:right;color:#1e293b;">{cnt}</span>
            </div>
          </td>
          <td style="padding:10px 12px;text-align:center;">
            <span style="font-size:12px;color:{status_color};font-weight:600;">{ok}/{cnt}</span>
          </td>
        </tr>"""

    # Build project rows
    proj_rows = ""
    for p in projects:
        pid = p["id"]
        s = proj_stats.get(pid, {"total":0,"today":0,"ok":0,"limit":p["daily_clicks"]})
        status_ok = s["today"] < s["limit"]
        badge = '<span style="background:#dcfce7;color:#166534;font-size:11px;padding:2px 8px;border-radius:99px;">aktywny</span>' if status_ok else '<span style="background:#fef9c3;color:#854d0e;font-size:11px;padding:2px 8px;border-radius:99px;">limit</span>'
        proj_rows += f"""
        <tr>
          <td style="padding:10px 12px;font-size:13px;font-weight:500;color:#1e293b;">{p['name']}</td>
          <td style="padding:10px 12px;font-size:13px;color:#64748b;">{p['domain']}</td>
          <td style="padding:10px 12px;font-size:13px;text-align:center;">{s['today']} / {s['limit']}</td>
          <td style="padding:10px 12px;font-size:13px;text-align:center;color:#1e293b;">{s['total']}</td>
          <td style="padding:10px 12px;text-align:center;">{badge}</td>
        </tr>"""

    # Build log rows
    log_rows = ""
    for c in recent:
        ts = c.get("timestamp","")[:16].replace("T"," ")
        status = c.get("status","?")
        sc = "#22c55e" if status == "ok" else "#ef4444"
        log_rows += f"""
        <tr>
          <td style="padding:8px 12px;font-size:12px;color:#64748b;white-space:nowrap;">{ts}</td>
          <td style="padding:8px 12px;font-size:12px;color:#1e293b;">{c.get('project_name','')}</td>
          <td style="padding:8px 12px;font-size:12px;color:#475569;">{c.get('keyword','')}</td>
          <td style="padding:8px 12px;font-size:12px;color:#64748b;">{c.get('domain','')}</td>
          <td style="padding:8px 12px;text-align:center;"><span style="font-size:11px;color:{sc};font-weight:600;">{status}</span></td>
        </tr>"""

    total_all = len(clicks)
    total_ok = sum(1 for c in clicks if c.get("status") == "ok")
    today_all = sum(1 for c in clicks if c["date"] == today)
    num_projects = len(projects)
    num_keywords = sum(len(p.get("keywords",[])) for p in projects)

    days_js = str(days).replace("'", '"')
    counts_js = str(day_counts)

    html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Search Analytics Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#f8fafc; color:#1e293b; }}
.header {{ background:#1e40af; color:white; padding:20px 32px; display:flex; align-items:center; justify-content:space-between; }}
.header h1 {{ font-size:20px; font-weight:600; }}
.header .sub {{ font-size:13px; opacity:0.75; margin-top:2px; }}
.updated {{ font-size:12px; opacity:0.7; }}
.container {{ max-width:1200px; margin:0 auto; padding:24px 20px; }}
.metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px; }}
.metric {{ background:white; border:1px solid #e2e8f0; border-radius:10px; padding:16px; }}
.metric-label {{ font-size:12px; color:#64748b; margin-bottom:4px; }}
.metric-value {{ font-size:26px; font-weight:600; color:#1e293b; }}
.metric-sub {{ font-size:11px; color:#94a3b8; margin-top:2px; }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:16px; }}
.card {{ background:white; border:1px solid #e2e8f0; border-radius:10px; padding:20px; }}
.card-title {{ font-size:12px; font-weight:600; color:#64748b; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:14px; }}
table {{ width:100%; border-collapse:collapse; }}
th {{ font-size:11px; color:#94a3b8; font-weight:500; padding:8px 12px; border-bottom:1px solid #f1f5f9; text-align:left; }}
tr:hover td {{ background:#f8fafc; }}
.tabs {{ display:flex; gap:4px; border-bottom:1px solid #e2e8f0; margin-bottom:16px; }}
.tab {{ padding:8px 16px; font-size:13px; cursor:pointer; color:#64748b; border-bottom:2px solid transparent; margin-bottom:-1px; }}
.tab.active {{ color:#1e40af; border-bottom-color:#1e40af; font-weight:500; }}
.tab-content {{ display:none; }}
.tab-content.active {{ display:block; }}
@media(max-width:768px){{
  .metrics{{grid-template-columns:1fr 1fr;}}
  .grid2{{grid-template-columns:1fr;}}
}}
</style>
</head>
<body>

<div class="header">
  <div>
    <div class="h1">Search Analytics Dashboard</div>
    <div class="sub">Automatyczny monitoring klikniec z Google</div>
  </div>
  <div class="updated">Ostatnia aktualizacja: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}</div>
</div>

<div class="container">

  <div class="metrics">
    <div class="metric">
      <div class="metric-label">Klikniecia dzisiaj</div>
      <div class="metric-value">{today_all}</div>
      <div class="metric-sub">dzien: {today}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Lacznie wszystkich</div>
      <div class="metric-value">{total_all}</div>
      <div class="metric-sub">skutecznych: {total_ok}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Aktywne projekty</div>
      <div class="metric-value">{num_projects}</div>
      <div class="metric-sub">zdefiniowanych</div>
    </div>
    <div class="metric">
      <div class="metric-label">Slowa kluczowe</div>
      <div class="metric-value">{num_keywords}</div>
      <div class="metric-sub">lacznie we wszystkich</div>
    </div>
  </div>

  <div class="tabs">
    <div class="tab active" onclick="switchTab('overview')">Przeglad</div>
    <div class="tab" onclick="switchTab('projects')">Projekty</div>
    <div class="tab" onclick="switchTab('logs')">Logi</div>
  </div>

  <div id="tab-overview" class="tab-content active">
    <div class="grid2">
      <div class="card">
        <div class="card-title">Klikniecia wg frazy</div>
        <table>
          <thead><tr><th>Fraza</th><th>Klikniecia</th><th>OK</th></tr></thead>
          <tbody>{kw_rows if kw_rows else '<tr><td colspan="3" style="padding:20px;text-align:center;color:#94a3b8;font-size:13px;">Brak danych</td></tr>'}</tbody>
        </table>
      </div>
      <div class="card">
        <div class="card-title">Ostatnie 7 dni</div>
        <canvas id="weekChart" style="width:100%;height:200px;"></canvas>
      </div>
    </div>
  </div>

  <div id="tab-projects" class="tab-content">
    <div class="card">
      <div class="card-title">Status projektow</div>
      <table>
        <thead><tr><th>Projekt</th><th>Domena</th><th>Dzis / limit</th><th>Lacznie</th><th>Status</th></tr></thead>
        <tbody>{proj_rows if proj_rows else '<tr><td colspan="5" style="padding:20px;text-align:center;color:#94a3b8;font-size:13px;">Brak projektow</td></tr>'}</tbody>
      </table>
    </div>
  </div>

  <div id="tab-logs" class="tab-content">
    <div class="card">
      <div class="card-title">Historia klikniec (ostatnie 30)</div>
      <table>
        <thead><tr><th>Czas</th><th>Projekt</th><th>Fraza</th><th>Domena</th><th>Status</th></tr></thead>
        <tbody>{log_rows if log_rows else '<tr><td colspan="5" style="padding:20px;text-align:center;color:#94a3b8;font-size:13px;">Brak logow</td></tr>'}</tbody>
      </table>
    </div>
  </div>

</div>

<script>
function switchTab(name) {{
  document.querySelectorAll('.tab').forEach((t,i) => {{
    const names = ['overview','projects','logs'];
    t.classList.toggle('active', names[i] === name);
  }});
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
}}

const ctx = document.getElementById('weekChart');
if (ctx) {{
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: {days_js},
      datasets: [{{ data: {counts_js}, backgroundColor: '#bfdbfe', borderColor: '#3b82f6', borderWidth: 1, borderRadius: 4 }}]
    }},
    options: {{
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        y: {{ beginAtZero: true, ticks: {{ precision: 0, font: {{ size: 11 }} }}, grid: {{ color: 'rgba(0,0,0,0.05)' }} }},
        x: {{ ticks: {{ font: {{ size: 11 }} }}, grid: {{ display: false }} }}
      }},
      responsive: true, maintainAspectRatio: false
    }}
  }});
}}
</script>
</body>
</html>"""

    Path("docs").mkdir(exist_ok=True)
    Path("docs/index.html").write_text(html, encoding="utf-8")
    print(f"Dashboard wygenerowany: docs/index.html ({len(clicks)} klikniec w bazie)")

if __name__ == "__main__":
    generate()
