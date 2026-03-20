/* ==================================================================
   ODDBALL
   ================================================================== */
function initOddball(report) {
  state._oddballReport = report || state.currentReport;
  var settings = state.settings || {};
  document.getElementById("oddballDupesFolder").value = settings.move_destination || "";
  document.getElementById("oddballSetup").style.display = "block";
  document.getElementById("oddballProgress").style.display = "none";
  document.getElementById("oddballResults").style.display = "none";
}

function runOddball() {
  var report = state._oddballReport;
  if (!report) { toast("No report selected", "error"); return; }

  var dupesFolder = document.getElementById("oddballDupesFolder").value.trim();

  document.getElementById("oddballSetup").style.display = "none";
  document.getElementById("oddballProgress").style.display = "block";

  api("POST", "/api/oddball/run", { report: report, dupes_folder: dupesFolder }).then(function() {
    function _onOddProg(d) {
      if (d.total > 0) {
        var pct = Math.round((d.current / d.total) * 100);
        document.getElementById("oddProgressFill").style.width = pct + "%";
        document.getElementById("oddProgressLeft").textContent = d.current + " / " + d.total;
      }
      if (d.status === "complete" || d.status === "error") {
        window._onOddballProgress = null;
        showOddballResults(d);
      }
    }
    if (_useBridge()) {
      window._onOddballProgress = _onOddProg;
      window.pywebview.api.subscribe_oddball_progress();
    } else {
      var sse = new EventSource("/api/oddball/progress");
      sse.onmessage = function(e) { _onOddProg(JSON.parse(e.data)); };
      sse.onerror = function() { sse.close(); };
    }
  }).catch(function(err) {
    toast("Error: " + err.message, "error");
    document.getElementById("oddballSetup").style.display = "block";
    document.getElementById("oddballProgress").style.display = "none";
  });
}

function showOddballResults(d) {
  document.getElementById("oddballProgress").style.display = "none";
  document.getElementById("oddballResults").style.display = "block";

  var result = d.result || {};
  var oddballs = result.oddballs || [];

  var html = '<div class="card">';
  html += '<h3>Verification Complete</h3>';
  html += '<p style="color:var(--text-dim);margin-bottom:16px;">Checked: ' +
    (result.total_checked || 0) + ' pairs. Skipped: ' + (result.total_skipped || 0) +
    '. Found ' + oddballs.length + ' potential false positives (distance > 5).</p>';

  if (oddballs.length === 0) {
    html += '<p style="color:var(--accent);">No oddballs found -- all matches look genuine!</p>';
  } else {
    html += '<div style="margin-top:16px;">';
    for (var i = 0; i < oddballs.length; i++) {
      var o = oddballs[i];
      var distClass = o.distance <= 8 ? "dist-med" : "dist-high";
      html += '<div style="display:flex;gap:16px;align-items:center;padding:12px 0;border-bottom:1px solid var(--border);">';

      html += '<span class="distance-badge ' + distClass + '">dist: ' + o.distance + '</span>';

      html += '<div style="flex:1;">';
      html += '<div style="font-size:12px;"><span style="color:var(--accent);">KEEP:</span> ' + escHtml(getFilename(o.keep)) + '</div>';
      html += '<div style="font-size:12px;"><span style="color:var(--danger);">DUPE:</span> ' + escHtml(getFilename(o.duplicates[0] || "")) + '</div>';
      html += '</div>';

      html += '<div style="display:flex;gap:8px;">';
      html += '<button class="btn btn-secondary btn-sm" onclick="openLightbox(\'' + escAttr(encodeURIComponent(o.keep)) + '\')">View Keep</button>';
      html += '<button class="btn btn-secondary btn-sm" onclick="openLightbox(\'' + escAttr(encodeURIComponent(o.duplicates[0] || "")) + '\')">View Dupe</button>';
      html += '<button class="btn btn-primary btn-sm" onclick="rescueFile(\'' + escAttr(o.duplicates[0] || "") + '\',\'' + escAttr(o.original_dupe_path || o.duplicates[0] || "") + '\')">Rescue</button>';
      html += '</div>';

      html += '</div>';
    }
    html += '</div>';
  }

  html += '</div>';
  document.getElementById("oddballResults").innerHTML = html;
}

function rescueFile(source, destination) {
  showDialog("Rescue File", "Copy " + getFilename(source) + " back to its original location?", "Rescue", "btn-primary", function() {
    api("POST", "/api/action/rescue", { source: source, destination: destination }).then(function(result) {
      if (result.success) {
        toast("File rescued successfully");
      } else {
        toast("Rescue failed: " + (result.error || "Unknown error"), "error");
      }
    }).catch(function(err) {
      toast("Error: " + err.message, "error");
    });
  });
}

