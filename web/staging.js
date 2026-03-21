// ---- Staging ----
var _stagingSSE = null;
var _stagingSession = null;  // { source_dir, staging_dir, manifest_path }

function startStaging(sourceDir, stagingDir, mode, threshold, recursive) {
  _stagingSession = { source_dir: sourceDir, staging_dir: stagingDir,
                      mode: mode, threshold: threshold, recursive: recursive };
  api("POST", "/api/staging/start", {
    source_dir: sourceDir, staging_dir: stagingDir
  }).then(function() {
    navigate("staging-progress");
  }).catch(function(err) {
    toast("Staging error: " + err.message, "error");
  });
}

function initStagingProgress() {
  document.getElementById("stagingActions").style.display = "block";
  document.getElementById("stagingCompleteBox").style.display = "none";
  document.getElementById("stagingProgressFill").style.width = "0%";
  document.getElementById("stagingProgressPct").textContent = "0%";

  if (_useBridge()) {
    window._onStagingProgress = function(d) {
      updateStagingUI(d);
      if (d.status === "complete" || d.status === "error" || d.status === "cancelled") {
        window._onStagingProgress = null;
      }
    };
    window.pywebview.api.subscribe_staging_progress();
  } else {
    if (_stagingSSE) _stagingSSE.close();
    _stagingSSE = new EventSource("/api/staging/progress");
    _stagingSSE.onmessage = function(e) {
      var d = JSON.parse(e.data);
      updateStagingUI(d);
      if (d.status === "complete" || d.status === "error" || d.status === "cancelled") {
        _stagingSSE.close();
      }
    };
  }
}

function updateStagingUI(d) {
  var pct = d.total > 0 ? Math.round((d.current / d.total) * 100) : 0;
  document.getElementById("stagingProgressFill").style.width = pct + "%";
  document.getElementById("stagingProgressPct").textContent = pct + "%";
  document.getElementById("stagingProgressLeft").textContent = d.current + " / " + d.total + " files";
  var mbCopied = d.bytes_copied ? Math.round(d.bytes_copied / (1024*1024)) : 0;
  var mbTotal = d.bytes_total ? Math.round(d.bytes_total / (1024*1024)) : 0;
  document.getElementById("stagingProgressRight").textContent = mbCopied + " / " + mbTotal + " MB";
  document.getElementById("stagingStage").textContent = d.stage || "staging";

  // Grey out cancel button at point of no return (finalizing/saving manifest)
  var noReturn = (d.stage === "saving" || d.stage === "finalizing" || d.status === "complete");
  var cancelBtn = document.getElementById("stagingCancelBtn");
  var wizCancelBtn = document.getElementById("wizStagingCancelBtn");
  if (cancelBtn) cancelBtn.disabled = noReturn;
  if (wizCancelBtn) wizCancelBtn.disabled = noReturn;

  document.getElementById("stagingCopied").textContent = d.copied || 0;
  document.getElementById("stagingSkipped").textContent = d.skipped || 0;
  document.getElementById("stagingFailed").textContent = d.failed || 0;

  if (d.status === "complete") {
    document.getElementById("stagingActions").style.display = "none";
    document.getElementById("stagingCompleteBox").style.display = "block";
    document.getElementById("stagingCompleteTitle").textContent = "Staging Complete";
    document.getElementById("stagingCompleteMsg").textContent = d.message || "";
    if (_stagingSession) {
      _stagingSession.manifest_path = d.manifest_path;
      _stagingSession.staging_dir = d.staging_dir || _stagingSession.staging_dir;
    }
    // Wire up the scan button to scan the staged folder
    document.getElementById("stagingScanBtn").onclick = function() {
      if (_stagingSession) {
        _doStartScan(_stagingSession.staging_dir, _stagingSession.mode,
                      _stagingSession.threshold, _stagingSession.recursive, false);
      }
    };
  } else if (d.status === "error") {
    document.getElementById("stagingActions").style.display = "none";
    document.getElementById("stagingCompleteBox").style.display = "block";
    document.getElementById("stagingCompleteTitle").textContent = "Staging Failed";
    document.getElementById("stagingCompleteTitle").style.color = "var(--danger)";
    document.getElementById("stagingCompleteMsg").textContent = d.message || "";
  } else if (d.status === "cancelled") {
    document.getElementById("stagingActions").style.display = "none";
    document.getElementById("stagingCompleteBox").style.display = "block";
    document.getElementById("stagingCompleteTitle").textContent = "Staging Cancelled";
    document.getElementById("stagingCompleteTitle").style.color = "var(--warning)";
    document.getElementById("stagingCompleteMsg").textContent = d.message || "";
  }
}

function cancelStaging() {
  api("POST", "/api/staging/cancel").catch(function() {});
}

