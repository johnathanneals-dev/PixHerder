// ---- Finish Flow ----
var _finishSSE = null;
var _finishCounts = { staging: 0, dupes: 0, keepers: 0 };
var _finishSourceDir = "";

function initFinish() {
  document.getElementById("finishSummary").style.display = "block";
  document.getElementById("finishProgress").style.display = "none";
  document.getElementById("finishComplete").style.display = "none";
  document.getElementById("finishTitle").textContent = "Finishing Up";
  document.getElementById("finishSubtitle").textContent = "Review what will happen, then confirm.";

  // Single source of truth: derive state from filesystem
  getAppState().then(function(appState) {
    var session = appState.session;
    if (session.active) {
      _stagingSession = { source_dir: session.source_dir, staging_dir: session.staging_dir };
    } else {
      _stagingSession = null;
    }

    _finishCounts.staging = appState.folders.staging.count || 0;
    _finishCounts.dupes = appState.folders.dupes.count || 0;
    _finishCounts.keepers = appState.folders.keepers.count || 0;
    document.getElementById("finishStagingCount").textContent = _finishCounts.staging.toLocaleString();
    document.getElementById("finishDupesCount").textContent = _finishCounts.dupes.toLocaleString();
    document.getElementById("finishKeepersCount").textContent = _finishCounts.keepers.toLocaleString();
    document.getElementById("finishKeepersRow").style.display = _finishCounts.keepers > 0 ? "flex" : "none";

    var btn = document.getElementById("finishNowBtn");
    if (!_stagingSession) {
      btn.disabled = true;
      btn.textContent = "No staging session found";
    } else {
      btn.disabled = false;
      btn.textContent = "Finish Now";
    }
  });
}

function _finishConfirm() {
  var sourceDir = _stagingSession ? _stagingSession.source_dir : "";
  // Build finish confirmation with embedded OneDrive warning
  api("POST", "/api/onedrive/status", { directory: sourceDir }).then(function(od) {
    var isOd = od && od.is_onedrive && od.running && od.show_prompts;
    _showFinishConfirmDialog(isOd);
  }).catch(function() {
    _showFinishConfirmDialog(false);
  });
}

function _showFinishConfirmDialog(showOneDriveWarning) {
  document.getElementById("dialogTitle").textContent = "Confirm Finish";
  var html = '<div style="margin-bottom:14px;">';
  if (_finishCounts.staging > 0 || _finishCounts.keepers > 0) {
    var homeCount = _finishCounts.staging + _finishCounts.keepers;
    html += homeCount.toLocaleString() + " files from Staging";
    if (_finishCounts.keepers > 0) html += " and Keepers";
    html += " will be placed back in their original folder. ";
  }
  if (_finishCounts.dupes > 0) {
    html += _finishCounts.dupes.toLocaleString() + " files in Recovery will be sent to the Recycle Bin. ";
  }
  html += "The recovery archive will also be cleared.</div>";
  if (showOneDriveWarning) {
    html += '<div style="background:var(--warning-bg);border:1px solid var(--warning);border-radius:var(--radius-sm);padding:12px;margin-bottom:14px;">' +
      '<div style="font-weight:600;color:var(--warning);margin-bottom:4px;">OneDrive is running</div>' +
      '<div style="font-size:13px;color:var(--text);line-height:1.5;">' +
        'For best results, pause OneDrive syncing first. ' +
        '<a href="#" onclick="event.preventDefault(); closeDialog(); _showOneDriveHowToPause(function() { _showFinishConfirmDialog(true); })" ' +
          'style="color:var(--accent);text-decoration:underline;">How to pause</a>' +
      '</div>' +
    '</div>';
  }
  html += '<div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;">' +
    '<button class="btn btn-primary" onclick="closeDialog(); _executeFinish()" data-tip="Send files home and recycle duplicates">Yes, Finish</button>' +
    '</div>';
  document.getElementById("dialogMessage").innerHTML = html;
  document.getElementById("dialogConfirmBtn").style.display = "none";
  var ghostBtn = document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-ghost");
  if (ghostBtn) ghostBtn.style.display = "";
  document.getElementById("dialogOverlay").classList.add("active");
}

function _executeFinish() {
  _finishSourceDir = _stagingSession ? _stagingSession.source_dir : "";
  document.getElementById("finishSummary").style.display = "none";
  document.getElementById("finishProgress").style.display = "block";
  document.getElementById("finishTitle").textContent = "Finishing Up...";
  document.getElementById("finishSubtitle").textContent = "";

  var totalPhases = (_finishCounts.staging > 0 || _finishCounts.keepers > 0 ? 1 : 0) + (_finishCounts.dupes > 0 ? 1 : 0) + 1;
  var curPhase = 0;

  // Phase 1: Restore all kept files (Staging + Keepers) to source — threaded with progress
  if ((_finishCounts.staging > 0 || _finishCounts.keepers > 0) && _stagingSession) {
    curPhase++;
    document.getElementById("finishPhaseLabel").textContent = "Step " + curPhase + " of " + totalPhases + ": Returning your files...";
    document.getElementById("finishStage").textContent = "Copying files back to original folder";

    // Subscribe to progress BEFORE starting restore to avoid race condition
    function _onRestore(d) {
      var pct = d.total > 0 ? Math.round((d.current / d.total) * 100) : 0;
      document.getElementById("finishProgressFill").style.width = pct + "%";
      document.getElementById("finishProgressPct").textContent = pct + "%";
      document.getElementById("finishProgressLeft").textContent =
        (d.current || 0) + " / " + (d.total || 0) + " files";
      document.getElementById("finishStage").textContent =
        d.phase === "cleanup" ? "Cleaning up workspace..." : "Copying files back to original folder";

      if (d.status === "complete") {
        window._onRestoreProgress = null;
        _finishPhase2({copied: d.copied, skipped: d.skipped, errors: d.errors});
      } else if (d.status === "error") {
        window._onRestoreProgress = null;
        _finishError(d.message || "Restore failed");
      }
    }
    window._onRestoreProgress = _onRestore;
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.subscribe_restore_progress();
    }

    api("POST", "/api/staging/restore", {
      staging_dir: _stagingSession.staging_dir,
      source_dir: _stagingSession.source_dir,
      include_keepers: true
    }).catch(function(err) {
      window._onRestoreProgress = null;
      _finishError("Restore failed: " + err.message);
    });
  } else {
    _finishPhase2({});
  }
}

function _finishPhase2(syncResult) {
  // Phase 2: Recycle dupes
  if (_finishCounts.dupes > 0) {
    document.getElementById("finishPhaseLabel").textContent = "Step 2 of 2: Recycling duplicates...";
    document.getElementById("finishStage").textContent = "Sending duplicates to Recycle Bin";
    document.getElementById("finishProgressFill").style.width = "0%";
    document.getElementById("finishProgressPct").textContent = "0%";
    document.getElementById("finishProgressLeft").textContent = "";

    api("POST", "/api/staging/recycle-bin", { folder: "dupes" }).then(function(r) {
      if (r.status === "recycled") {
        _finishPhase3(syncResult, r);
      } else {
        _finishError("Recycle failed: " + (r.error || "Unknown error"));
      }
    }).catch(function(err) {
      _finishError("Recycle failed: " + err.message);
    });
  } else {
    _finishPhase3(syncResult, {});
  }
}

function _finishPhase3(restoreResult, recycleResult) {
  // Phase 3: Clean up all system folders
  document.getElementById("finishStage").textContent = "Cleaning up workspace...";
  var cleanupPromises = [];
  if (_stagingSession) {
    cleanupPromises.push(
      api("POST", "/api/staging/cleanup", {
        staging_dir: _stagingSession.staging_dir
      }).catch(function() {})
    );
  }

  Promise.all(cleanupPromises).then(function() {
    // Clear in-memory staging session on the server
    if (_stagingSession) {
      api("POST", "/api/staging/reset").catch(function() {});
    }

    // Clear recovery archive on finish
    api("POST", "/api/recovery/clear").catch(function() {});

    // Show completion -- clear all stale state
    resetAppState();
    document.getElementById("finishProgress").style.display = "none";
    document.getElementById("finishComplete").style.display = "block";
    document.getElementById("finishTitle").textContent = "All Done!";
    document.getElementById("finishSubtitle").textContent = "";

    var restoredCount = (restoreResult && restoreResult.copied) || _finishCounts.staging || 0;
    var summary = "";
    if (restoreResult && restoreResult.copied > 0) {
      summary += restoreResult.copied.toLocaleString() + " files returned to their original folder<br>";
    } else if (_finishCounts.staging > 0) {
      summary += _finishCounts.staging.toLocaleString() + " files returned safely<br>";
    }
    if (recycleResult && recycleResult.files_recycled > 0) {
      summary += recycleResult.files_recycled.toLocaleString() + " duplicates sent to Recycle Bin<br>";
    }
    summary += "Local workspace cleaned up.";
    document.getElementById("finishCompleteSummary").innerHTML = summary;

    // Show OneDrive explainer if files went back to OneDrive
    if (restoredCount > 0 && _finishSourceDir) {
      api("POST", "/api/onedrive/status", { directory: _finishSourceDir }).then(function(od) {
        if (od.is_onedrive && od.show_prompts) {
          showOneDriveRestoreExplainer(restoredCount);
        }
      }).catch(function() {});
    }
  }); // end Promise.all
}

function _finishSendHome() {
  var total = _finishCounts.staging + _finishCounts.dupes + _finishCounts.keepers;
  if (total === 0) {
    toast("No files to send home");
    return;
  }
  // Reuse dashboard's combined dialog (OneDrive warning + confirmation in one)
  _sendHomeConfirmDialog(total);
}

function _finishError(msg) {
  document.getElementById("finishProgress").style.display = "none";
  document.getElementById("finishComplete").style.display = "block";
  document.getElementById("finishTitle").textContent = "Finish Incomplete";
  document.getElementById("finishSubtitle").textContent = "";
  var card = document.querySelector("#finishComplete .card h3");
  card.style.color = "var(--danger)";
  card.textContent = "Something went wrong";
  document.getElementById("finishCompleteSummary").textContent = msg;
}

