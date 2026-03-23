// ---- Sync Back ----

function initSyncback() {
  document.getElementById("syncbackStart").style.display = "block";
  document.getElementById("syncbackProgress").style.display = "none";
  document.getElementById("syncbackCompleteBox").style.display = "none";
}

function startSyncback() {
  if (!_stagingSession) {
    toast("No staging session to sync back", "error");
    return;
  }
  // Validate staging session matches filesystem before starting (Issue 31)
  api("GET", "/api/staging/status").then(function(status) {
    if (status.staging_dir) {
      _stagingSession.staging_dir = status.staging_dir;
      _stagingSession.source_dir = status.source_dir || _stagingSession.source_dir;
    }
    _doStartSyncback();
  }).catch(function() {
    _doStartSyncback();
  });
}

function _doStartSyncback() {
  document.getElementById("syncbackStart").style.display = "none";
  document.getElementById("syncbackProgress").style.display = "block";

  api("POST", "/api/staging/syncback", {
    staging_dir: _stagingSession.staging_dir,
    source_dir: _stagingSession.source_dir
  }).then(function() {
    function _onSyncProg(d) {
      var pct = d.total > 0 ? Math.round((d.current / d.total) * 100) : 0;
      document.getElementById("syncbackProgressFill").style.width = pct + "%";
      document.getElementById("syncbackProgressPct").textContent = pct + "%";
      document.getElementById("syncbackProgressLeft").textContent = d.current + " / " + d.total;
      document.getElementById("syncbackStage").textContent = d.message || "Syncing";
      if (d.status === "complete") {
        window._onSyncbackProgress = null;
        document.getElementById("syncbackProgress").style.display = "none";
        document.getElementById("syncbackCompleteBox").style.display = "block";
        document.getElementById("syncbackCompleteMsg").textContent = d.message || "";
        _refreshFolderPaths();
      } else if (d.status === "error") {
        window._onSyncbackProgress = null;
        document.getElementById("syncbackProgress").style.display = "none";
        document.getElementById("syncbackCompleteBox").style.display = "block";
        document.getElementById("syncbackCompleteTitle").textContent = "Sync Failed";
        document.getElementById("syncbackCompleteTitle").style.color = "var(--danger)";
        document.getElementById("syncbackCompleteMsg").textContent = d.message || "";
      }
    }
    window._onSyncbackProgress = _onSyncProg;
    window.pywebview.api.subscribe_syncback_progress();
  });
}

function cleanupStaging() {
  // Check if staging has files -- if empty, just remove the folder
  api("GET", "/api/folders/status").then(function(data) {
    // Ensure staging session is set from folder status
    if (!_stagingSession && data.staging && data.staging.path) {
      _stagingSession = { staging_dir: data.staging.path };
    }
    if (!_stagingSession) {
      toast("No workspace to remove", "warning");
      return;
    }
    var count = (data.staging && data.staging.file_count) || 0;
    if (count === 0) {
      api("POST", "/api/staging/cleanup", {
        staging_dir: _stagingSession.staging_dir
      }).then(function() {
        toast("Staging folder cleaned up");
        resetAppState();
        navigate("dashboard");
      });
      return;
    }
    // Has files -- show decision dialog
    document.getElementById("dialogTitle").textContent = "Remove Workspace";
    document.getElementById("dialogMessage").innerHTML =
      '<div style="margin-bottom:16px;">You have <strong>' + count.toLocaleString() +
      '</strong> files in Staging. What would you like to do with them?</div>' +
      '<div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;">' +
      '<button class="btn btn-danger" onclick="_recycleStagingConfirm(' + count + ')">Send to Recycle Bin</button>' +
      '<button class="btn btn-primary" onclick="closeDialog(); sendFilesHome()">Send Files Home</button>' +
      '</div>' +
      '<div style="border-top:1px solid var(--border);margin-top:14px;padding-top:12px;font-size:13px;color:var(--text-dim);">' +
      '<span style="color:#fff;font-weight:600;">Send Files Home</span> puts everything back where it came from. Nothing gets deleted.<br><br>' +
      '<span style="color:#fff;font-weight:600;">Send to Recycle Bin</span> removes the files but you can recover them from the Recycle Bin if needed.' +
      '</div>' +
      '<div style="margin-top:12px;"><button class="btn btn-ghost" onclick="closeDialog()">Cancel</button></div>';
    document.getElementById("dialogConfirmBtn").style.display = "none";
    document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-secondary").style.display = "none";
    document.getElementById("dialogOverlay").classList.add("active");
  });
}

function _recycleStagingConfirm(count) {
  closeDialog();
  showDialog(
    "Confirm Recycle",
    "This will send " + count.toLocaleString() + " files to the Windows Recycle Bin. " +
    "You can recover them from there if needed.",
    "Send to Recycle Bin", "btn-danger",
    function() {
      _executeRecycleStaging();
    }
  );
}

function _executeRecycleStaging() {
  if (!_stagingSession) return;
  closeDialog();
  startWorkingView(
    "Recycling Workspace",
    "Sending Staging to the Recycle Bin.",
    function(done) {
      api("POST", "/api/staging/recycle-bin", {
        staging_dir: _stagingSession.staging_dir
      }).then(function(r) {
        if (r.status === "recycled") {
          resetAppState();
          var msg = r.files_recycled.toLocaleString() + " files sent to the Recycle Bin.";
          if (r.errors > 0) msg += " " + r.errors + " files could not be removed.";
          done("Recycle Complete", msg);
        } else {
          done("Recycle Failed", r.error || "Unknown error");
        }
      }).catch(function(err) {
        done("Recycle Failed", err.message);
      });
    },
    "dashboard"
  );
}

