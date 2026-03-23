#!/usr/bin/env python3
"""
PixHerder Reviewer - Local web server for reviewing duplicate image groups.
Opens a browser-based tool to view duplicates side-by-side.

Usage:
    python reviewer.py
    python reviewer.py --port 8080
    python reviewer.py --report perceptual_report.json
"""

import http.server
import json
import os
import sys
import urllib.parse
import webbrowser
import threading
import argparse
from pathlib import Path

DEFAULT_PORT = 8787
DEFAULT_REPORT = "perceptual_report.json"


def get_html():
    return r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PixHerder Reviewer</title>
<style>
  *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

  :root {
    --bg: #0a0a0c;
    --surface: #131318;
    --surface-2: #1a1a22;
    --border: #2a2a35;
    --text: #e8e8ed;
    --text-dim: #7a7a8a;
    --accent: #6ee7b7;
    --accent-dim: #2d6a54;
    --danger: #f87171;
    --danger-dim: #5c2626;
    --keep-bg: #0f2a1f;
    --keep-border: #1a5c3a;
    --dupe-bg: #2a1215;
    --dupe-border: #5c2a2e;
    --radius: 12px;
  }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }

  .header {
    position: sticky;
    top: 0;
    z-index: 100;
    background: rgba(10, 10, 12, 0.85);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid var(--border);
    padding: 16px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
    flex-wrap: wrap;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .logo {
    font-size: 22px;
    font-weight: 900;
    letter-spacing: -0.5px;
    color: var(--accent);
    font-family: monospace;
  }

  .stats {
    display: flex;
    gap: 24px;
    font-size: 13px;
    color: var(--text-dim);
    font-family: monospace;
  }

  .stats span strong { color: var(--text); font-weight: 600; }

  .nav-controls {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .nav-btn {
    background: var(--surface-2);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    transition: all 0.15s ease;
  }

  .nav-btn:hover { background: var(--border); }
  .nav-btn:disabled { opacity: 0.3; cursor: not-allowed; }

  .nav-counter {
    font-family: monospace;
    font-size: 14px;
    color: var(--text-dim);
    min-width: 100px;
    text-align: center;
  }

  .nav-counter strong { color: var(--accent); }

  .jump-input {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 12px;
    border-radius: 8px;
    font-family: monospace;
    font-size: 13px;
    width: 80px;
    text-align: center;
  }

  .jump-input:focus { outline: none; border-color: var(--accent); }

  .main {
    max-width: 1400px;
    margin: 0 auto;
    padding: 32px;
  }

  .group-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }

  .group-title { font-size: 18px; font-weight: 700; }
  .group-meta { font-size: 13px; color: var(--text-dim); font-family: monospace; }

  .image-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 20px;
    margin-bottom: 40px;
  }

  .image-card {
    background: var(--surface);
    border: 2px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    transition: all 0.2s ease;
    position: relative;
  }

  .image-card.keep { border-color: var(--keep-border); background: var(--keep-bg); }
  .image-card.dupe { border-color: var(--dupe-border); background: var(--dupe-bg); }
  .image-card:hover { transform: translateY(-2px); }

  .image-wrapper {
    width: 100%;
    aspect-ratio: 4/3;
    overflow: hidden;
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    position: relative;
  }

  .image-wrapper img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }

  .image-wrapper .loading {
    color: var(--text-dim);
    font-size: 13px;
    font-family: monospace;
  }

  .badge {
    position: absolute;
    top: 12px;
    left: 12px;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
    font-family: monospace;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    z-index: 2;
  }

  .badge.keep-badge { background: var(--accent); color: #0a0a0c; }
  .badge.dupe-badge { background: var(--danger); color: #0a0a0c; }

  .card-info { padding: 14px 16px; }

  .card-filename {
    font-size: 13px;
    font-weight: 600;
    word-break: break-all;
    margin-bottom: 6px;
    line-height: 1.3;
  }

  .card-path {
    font-size: 11px;
    color: var(--text-dim);
    font-family: monospace;
    word-break: break-all;
    opacity: 0.7;
  }

  .action-bar {
    position: sticky;
    bottom: 0;
    background: rgba(10, 10, 12, 0.9);
    backdrop-filter: blur(20px);
    border-top: 1px solid var(--border);
    padding: 16px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
  }

  .action-btn {
    padding: 10px 24px;
    border-radius: 8px;
    border: none;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .btn-move { background: var(--danger); color: #0a0a0c; }
  .btn-move:hover { background: #fca5a5; }
  .btn-skip { background: var(--surface-2); border: 1px solid var(--border); color: var(--text); }
  .btn-skip:hover { background: var(--border); }
  .btn-export { background: var(--accent); color: #0a0a0c; }
  .btn-export:hover { background: #a7f3d0; }

  .action-info { font-size: 13px; color: var(--text-dim); font-family: monospace; }

  .lightbox {
    display: none;
    position: fixed;
    inset: 0;
    z-index: 1000;
    background: rgba(0,0,0,0.95);
    align-items: center;
    justify-content: center;
    cursor: zoom-out;
  }

  .lightbox.active { display: flex; }
  .lightbox img { max-width: 95vw; max-height: 95vh; object-fit: contain; }

  .summary { text-align: center; padding: 80px 32px; }
  .summary h2 { font-size: 36px; font-weight: 900; margin-bottom: 16px; color: var(--accent); }
  .summary p { font-size: 16px; color: var(--text-dim); margin-bottom: 32px; }

  .summary-stats { display: flex; justify-content: center; gap: 40px; margin-bottom: 40px; }
  .summary-stat { text-align: center; }
  .summary-stat .num { font-size: 48px; font-weight: 900; font-family: monospace; color: var(--accent); }
  .summary-stat .label { font-size: 13px; color: var(--text-dim); margin-top: 4px; }

  .kbd-hints { display: flex; gap: 16px; font-size: 12px; color: var(--text-dim); font-family: monospace; }

  kbd {
    background: var(--surface-2);
    border: 1px solid var(--border);
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    color: var(--text);
  }
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="logo">PixHerder Reviewer</div>
    <div class="stats">
      <span>Groups: <strong id="totalGroups">0</strong></span>
      <span>Dupes: <strong id="totalDupes">0</strong></span>
      <span>Reclaimable: <strong id="totalSize">0 MB</strong></span>
    </div>
  </div>
  <div class="nav-controls">
    <div class="kbd-hints">
      <span><kbd>&#8592;</kbd> prev</span>
      <span><kbd>&#8594;</kbd> next</span>
      <span><kbd>S</kbd> skip</span>
      <span><kbd>M</kbd> mark move</span>
    </div>
    <button class="nav-btn" id="prevBtn" onclick="navigate(-1)">Prev</button>
    <div class="nav-counter">
      <input class="jump-input" id="jumpInput" type="number" min="1" onchange="jumpTo(this.value)">
      / <span id="totalLabel">0</span>
    </div>
    <button class="nav-btn" id="nextBtn" onclick="navigate(1)">Next</button>
  </div>
</div>

<div class="main" id="mainContent">
  <div style="text-align:center;padding:80px;color:var(--text-dim);">Loading groups...</div>
</div>

<div class="action-bar">
  <div class="action-info" id="actionInfo">Reviewed: 0 | Marked for move: 0</div>
  <div style="display:flex;gap:12px;">
    <button class="action-btn btn-skip" onclick="markSkip()">Skip (keep all)</button>
    <button class="action-btn btn-move" onclick="markMove()">Mark dupes for move</button>
    <button class="action-btn btn-move" style="background:#d97706;color:#0a0a0c;" onclick="markAllMove()">Mark ALL for move</button>
    <button class="action-btn btn-export" onclick="exportDecisions()">Export decisions</button>
  </div>

<div class="lightbox" id="lightbox" onclick="closeLightbox()">
  <img id="lightboxImg" src="">
</div>

<script>
var groups = [];
var currentIndex = 0;
var decisions = {};

function init() {
  fetch("/api/groups")
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
      groups = data;
      document.getElementById("totalGroups").textContent = groups.length;
      document.getElementById("totalLabel").textContent = groups.length;

      var totalDupes = 0;
      var totalBytes = 0;
      for (var i = 0; i < groups.length; i++) {
        totalDupes += groups[i].duplicates.length;
        totalBytes += groups[i].reclaimable_bytes;
      }
      document.getElementById("totalDupes").textContent = totalDupes.toLocaleString();
      document.getElementById("totalSize").textContent = (totalBytes / 1024 / 1024).toFixed(1) + " MB";

      renderGroup();
    })
    .catch(function(err) {
      document.getElementById("mainContent").innerHTML =
        '<div style="text-align:center;padding:80px;color:#f87171;">Error loading data: ' + err + '</div>';
    });
}

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function getFilename(filepath) {
  var sep = filepath.indexOf("\\") >= 0 ? "\\" : "/";
  var parts = filepath.split(sep);
  return parts[parts.length - 1];
}

function getFolder(filepath) {
  var sep = filepath.indexOf("\\") >= 0 ? "\\" : "/";
  var parts = filepath.split(sep);
  parts.pop();
  return parts.slice(-2).join(sep);
}

function makeImageCard(filepath, type) {
  var encoded = encodeURIComponent(filepath);
  var badgeClass = type === "keep" ? "keep-badge" : "dupe-badge";
  var badgeText = type === "keep" ? "KEEP" : "DUPE";
  var cardClass = type;

  var card = document.createElement("div");
  card.className = "image-card " + cardClass;

  var wrapper = document.createElement("div");
  wrapper.className = "image-wrapper";
  wrapper.onclick = function() { openLightbox(encoded); };

  var badge = document.createElement("span");
  badge.className = "badge " + badgeClass;
  badge.textContent = badgeText;

  var img = document.createElement("img");
  img.src = "/image?path=" + encoded;
  img.loading = "lazy";
  img.onerror = function() {
    wrapper.innerHTML = '<span class="loading">Could not load</span>';
  };

  wrapper.appendChild(badge);
  wrapper.appendChild(img);

  var info = document.createElement("div");
  info.className = "card-info";

  var fname = document.createElement("div");
  fname.className = "card-filename";
  fname.textContent = getFilename(filepath);

  var fpath = document.createElement("div");
  fpath.className = "card-path";
  fpath.textContent = getFolder(filepath);

  info.appendChild(fname);
  info.appendChild(fpath);

  card.appendChild(wrapper);
  card.appendChild(info);

  return card;
}

function renderGroup() {
  if (currentIndex >= groups.length) {
    showSummary();
    return;
  }

  var group = groups[currentIndex];
  var main = document.getElementById("mainContent");
  var decision = decisions[currentIndex];

  document.getElementById("jumpInput").value = currentIndex + 1;
  document.getElementById("prevBtn").disabled = currentIndex === 0;
  document.getElementById("nextBtn").disabled = currentIndex >= groups.length - 1;

  main.innerHTML = "";

  // Group header
  var header = document.createElement("div");
  header.className = "group-header";

  var title = document.createElement("div");
  title.className = "group-title";
  var titleText = "Group " + (currentIndex + 1);
  if (decision === "skip") titleText += "  [SKIPPED]";
  if (decision === "move") titleText += "  [MARKED FOR MOVE]";
  title.textContent = titleText;

  var meta = document.createElement("div");
  meta.className = "group-meta";
  meta.textContent = (group.duplicates.length + 1) + " files | " + formatBytes(group.reclaimable_bytes) + " reclaimable";

  header.appendChild(title);
  header.appendChild(meta);
  main.appendChild(header);

  // Image grid
  var grid = document.createElement("div");
  grid.className = "image-grid";

  grid.appendChild(makeImageCard(group.keep, "keep"));

  for (var i = 0; i < group.duplicates.length; i++) {
    grid.appendChild(makeImageCard(group.duplicates[i], "dupe"));
  }

  main.appendChild(grid);
  window.scrollTo(0, 0);
  updateActionInfo();
}

function navigate(dir) {
  currentIndex = Math.max(0, Math.min(groups.length - 1, currentIndex + dir));
  renderGroup();
}

function jumpTo(val) {
  var n = parseInt(val);
  if (n >= 1 && n <= groups.length) {
    currentIndex = n - 1;
    renderGroup();
  }
}

function markSkip() {
  decisions[currentIndex] = "skip";
  if (currentIndex < groups.length - 1) navigate(1);
  else renderGroup();
}

function markMove() {
  decisions[currentIndex] = "move";
  if (currentIndex < groups.length - 1) navigate(1);
  else renderGroup();
}

function markAllMove() {
  if (!confirm("Mark all " + groups.length + " groups for move? You can still undo individual ones by pressing S to skip.")) return;
  for (var i = 0; i < groups.length; i++) {
    decisions[i] = "move";
  }
  renderGroup();
  updateActionInfo();
}

function updateActionInfo() {
  var reviewed = Object.keys(decisions).length;
  var moves = 0;
  for (var k in decisions) {
    if (decisions[k] === "move") moves++;
  }
  document.getElementById("actionInfo").textContent =
    "Reviewed: " + reviewed + " / " + groups.length + " | Marked for move: " + moves;
}

function showSummary() {
  var moves = 0, skips = 0, moveBytes = 0;
  for (var k in decisions) {
    if (decisions[k] === "move") {
      moves++;
      moveBytes += groups[parseInt(k)].reclaimable_bytes;
    }
    if (decisions[k] === "skip") skips++;
  }

  var main = document.getElementById("mainContent");
  main.innerHTML =
    '<div class="summary">' +
    '<h2>Review Complete</h2>' +
    '<p>You have reviewed all duplicate groups.</p>' +
    '<div class="summary-stats">' +
    '<div class="summary-stat"><div class="num">' + moves + '</div><div class="label">Marked for move</div></div>' +
    '<div class="summary-stat"><div class="num">' + skips + '</div><div class="label">Skipped</div></div>' +
    '<div class="summary-stat"><div class="num">' + formatBytes(moveBytes) + '</div><div class="label">Space to reclaim</div></div>' +
    '</div>' +
    '<p>Click "Export decisions" to save a move script.</p>' +
    '</div>';
}

function exportDecisions() {
  var moveGroups = [];
  for (var k in decisions) {
    if (decisions[k] === "move") {
      moveGroups.push(groups[parseInt(k)]);
    }
  }

  if (moveGroups.length === 0) {
    alert("No groups marked for move yet!");
    return;
  }

  fetch("/api/export", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(moveGroups)
  })
  .then(function(resp) { return resp.json(); })
  .then(function(result) { alert(result.message); })
  .catch(function(err) { alert("Export failed: " + err); });
}

function openLightbox(encodedPath) {
  document.getElementById("lightboxImg").src = "/image?path=" + encodedPath;
  document.getElementById("lightbox").classList.add("active");
}

function closeLightbox() {
  document.getElementById("lightbox").classList.remove("active");
}

document.addEventListener("keydown", function(e) {
  if (e.target.tagName === "INPUT") return;
  if (e.key === "ArrowLeft") navigate(-1);
  if (e.key === "ArrowRight") navigate(1);
  if (e.key === "s" || e.key === "S") markSkip();
  if (e.key === "m" || e.key === "M") markMove();
  if (e.key === "Escape") closeLightbox();
});

init();
</script>
</body>
</html>"""


class ReviewerHandler(http.server.BaseHTTPRequestHandler):
    report_data = []

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/' or parsed.path == '':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(get_html().encode('utf-8'))

        elif parsed.path == '/api/groups':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(self.report_data).encode('utf-8'))

        elif parsed.path == '/image':
            params = urllib.parse.parse_qs(parsed.query)
            filepath = params.get('path', [''])[0]
            self.serve_image(filepath)

        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/api/export':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            move_groups = json.loads(body)

            script_path = os.path.join(os.getcwd(), "move_dupes.ps1")
            move_dir = os.path.join(os.getcwd(), "perceptual_dupes")

            lines = []
            lines.append('# PixHerder Reviewer - Move Script')
            lines.append('# Generated from perceptual duplicate review')
            lines.append('# ' + str(len(move_groups)) + ' groups marked for move')
            lines.append('')
            lines.append('$moveDir = "' + move_dir + '"')
            lines.append('if (-not (Test-Path $moveDir)) { New-Item -ItemType Directory -Path $moveDir | Out-Null }')
            lines.append('$moved = 0')
            lines.append('')

            count = 0
            for group in move_groups:
                for dupe in group['duplicates']:
                    safe = dupe.replace("'", "''")
                    count += 1
                    lines.append("# Group keep: " + group['keep'])
                    lines.append("try {")
                    lines.append("  Copy-Item -LiteralPath '" + safe + "' -Destination $moveDir -Force")
                    lines.append("  $moved++")
                    lines.append("} catch { Write-Host \"[!] Failed: " + safe.replace('"', '`"') + " - $_\" }")

            lines.append('')
            lines.append('Write-Host "Moved $moved files to $moveDir"')

            with open(script_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            msg = "Saved move script: " + script_path + "\n\n" + str(count) + " files will be moved.\n\nReview the script in VS Code, then run:\n  .\\move_dupes.ps1"
            result = {"message": msg}
            self.wfile.write(json.dumps(result).encode('utf-8'))
        else:
            self.send_error(404)

    def serve_image(self, filepath):
        filepath = os.path.normpath(filepath)
        if not os.path.isfile(filepath):
            self.send_error(404, "File not found")
            return

        ext = os.path.splitext(filepath)[1].lower()
        content_types = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.gif': 'image/gif',
            '.bmp': 'image/bmp', '.webp': 'image/webp',
            '.tiff': 'image/tiff', '.tif': 'image/tiff',
        }
        ct = content_types.get(ext, 'application/octet-stream')

        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'max-age=3600')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, str(e))


def main():
    parser = argparse.ArgumentParser(description="PixHerder Reviewer - Review duplicate images in your browser")
    parser.add_argument('--report', default=DEFAULT_REPORT, help='Path to JSON report (default: ' + DEFAULT_REPORT + ')')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Port to run on (default: ' + str(DEFAULT_PORT) + ')')
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        print("[ERROR] Report not found: " + str(report_path))
        print("  Run pixherder.py with --action json first.")
        sys.exit(1)

    with open(report_path) as f:
        data = json.load(f)

    print("")
    print("PixHerder Reviewer")
    print("  Report:  " + str(report_path))
    print("  Groups:  " + str(len(data)))
    print("  Port:    " + str(args.port))
    print("")

    ReviewerHandler.report_data = data

    server = http.server.HTTPServer(('127.0.0.1', args.port), ReviewerHandler)
    url = "http://127.0.0.1:" + str(args.port)

    print("  Opening browser: " + url)
    print("  Press Ctrl+C to stop")
    print("")

    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
