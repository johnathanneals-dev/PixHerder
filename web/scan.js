/* ==================================================================
   SCAN CONFIG
   ================================================================== */
var _lastScanContext = null; // Tracks which folder was being scanned

function _returnToScanFolder() {
  if (_lastScanContext) {
    // Use the scan directory directly if dashFolderPaths isn't populated
    var scanDir = document.getElementById("scanDir");
    var path = scanDir ? scanDir.value : "";
    if (path && _lastScanContext) {
      browserState.rootPath = path;
      browserState.type = _lastScanContext;
      browserState.currentPath = path;
      browserState.currentPage = 1;
      browserState.returnTo = "dashboard";
      navigate("browser");
    } else {
      openBrowserFromDashboard(_lastScanContext);
    }
  } else {
    navigate("dashboard");
  }
}

function fillScanDir(type) {
  if (type === "staging") {
    // Try staging session, then API, then settings default
    if (_stagingSession && _stagingSession.staging_dir) {
      document.getElementById("scanDir").value = _stagingSession.staging_dir;
      return;
    }
    api("GET", "/api/staging/status").then(function(d) {
      if (d.staging_dir) {
        document.getElementById("scanDir").value = d.staging_dir;
      } else {
        api("GET", "/api/settings").then(function(s) {
          document.getElementById("scanDir").value = s.staging_dir || "";
        });
      }
    }).catch(function() {});
  } else if (type === "dupes") {
    var s = state.settings || {};
    document.getElementById("scanDir").value = s.move_destination || "";
  }
}

function initScanConfig() {
  var ctx = typeof _scanContext !== "undefined" ? _scanContext : null;
  var title = document.querySelector("#view-scan-config h1");
  var subtitle = document.querySelector("#view-scan-config .subtitle");
  var folderGroup = document.getElementById("scanFolderGroup");
  var keepersSection = document.getElementById("scanKeepersSection");

  // Context-aware layout
  var ctxConfig = {
    staging: { title: "Configure Staging Scan",  subtitle: "Scan your files to find duplicates.",                                    showFolder: false, label: "Staging"  },
    dupes:   { title: "Configure Recovery Scan", subtitle: "Review your removed duplicates with different scan settings.",           showFolder: false, label: "Recovery" },
    keepers: { title: "Configure Keepers Scan",  subtitle: "Rescan your verified keepers to check for remaining duplicates.",       showFolder: false, label: "Keepers"  }
  };
  var cfg = ctxConfig[ctx] || { title: "Configure Scan", subtitle: "Choose a folder and scanning options.", showFolder: true, label: null };

  title.textContent = cfg.title;
  subtitle.textContent = cfg.subtitle;
  if (folderGroup) folderGroup.style.display = cfg.showFolder ? "block" : "none";
  if (keepersSection) keepersSection.style.display = "none";

  // Save context for return button, then reset (so menu link shows full options)
  _lastScanContext = ctx;
  _scanContext = null;

  // Show return-to-folder button on config page if launched from a folder
  var retConfigBtn = document.getElementById("scanReturnFolderConfigBtn");
  if (retConfigBtn) {
    if (cfg.label) {
      retConfigBtn.textContent = "Return to " + cfg.label;
      retConfigBtn.style.display = "inline-flex";
    } else {
      retConfigBtn.style.display = "none";
    }
  }

  api("GET", "/api/settings").then(function(settings) {
    state.settings = settings;
    document.getElementById("scanThreshold").value = settings.threshold || 5;
    document.getElementById("thresholdVal").textContent = settings.threshold || 5;
    document.getElementById("scanRecursive").checked = settings.recursive !== false;
    // Set scan limit dropdown default
    var limitEl = document.getElementById("scanLimit");
    if (limitEl) limitEl.value = "2000";
  });
  // Update quick-fill buttons with file counts
  api("GET", "/api/folders/status").then(function(data) {
    var sBtn = document.getElementById("scanFillStagingBtn");
    var dBtn = document.getElementById("scanFillDupesBtn");
    if (data.staging && data.staging.exists && data.staging.file_count > 0) {
      sBtn.textContent = "Staging (" + data.staging.file_count.toLocaleString() + ")";
      sBtn.disabled = false;
    } else {
      sBtn.textContent = "Staging (empty)";
      sBtn.disabled = true;
    }
    if (data.dupes && data.dupes.exists && data.dupes.file_count > 0) {
      dBtn.textContent = "Recovery (" + data.dupes.file_count.toLocaleString() + ")";
      dBtn.disabled = false;
      if (!ctx) document.getElementById("scanKeepersSection").style.display = "block";
    } else {
      dBtn.textContent = "Recovery (empty)";
      dBtn.disabled = true;
      document.getElementById("scanKeepersSection").style.display = "none";
    }
  }).catch(function() {});
}

function startScan() {
  var dir = document.getElementById("scanDir").value.trim();
  if (!dir) { toast("Please enter a folder path", "error"); return; }

  var modeEl = document.querySelector('input[name="scanMode"]:checked');
  var mode = modeEl ? modeEl.value : "both";
  var threshold = parseInt(document.getElementById("scanThreshold").value) || 5;
  var recursive = document.getElementById("scanRecursive").checked;
  var autoRecycle = document.getElementById("scanAutoRecycle").checked;
  var scanLimitEl = document.getElementById("scanLimit");
  var scanLimit = scanLimitEl ? parseInt(scanLimitEl.value) || 0 : 0;

  // Check if this is a OneDrive path
  api("POST", "/api/staging/check", { directory: dir }).then(function(result) {
    if (result.is_onedrive) {
      // Show staging dialog
      var msg = result.file_count + " files (~" + result.estimated_gb + " GB). "
        + "Free space: " + (result.free_space_gb || "?") + " GB.";
      if (result.existing_session) {
        msg += "\nA previous staging session exists (" + result.existing_session.file_count
          + " files staged on " + new Date(result.existing_session.created).toLocaleString() + ").";
      }
      showStagingDialog(dir, result.staging_dir, msg, result.existing_session,
        mode, threshold, recursive);
    } else {
      _checkResumeAndStart(dir, mode, threshold, recursive, autoRecycle, scanLimit);
    }
  }).catch(function() {
    _checkResumeAndStart(dir, mode, threshold, recursive, autoRecycle, scanLimit);
  });
}

function showStagingDialog(dir, stagingDir, info, existingSession, mode, threshold, recursive) {
  document.getElementById("dialogTitle").textContent = "Synced Folder Detected";
  var html = '<div style="margin-bottom:12px;">This folder appears to be synced (OneDrive). '
    + 'Make a working copy for reliable scanning?</div>'
    + '<div style="font-size:12px;color:var(--text-dim);font-family:monospace;margin-bottom:16px;">'
    + escHtml(info) + '</div>'
    + '<div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;">'
    + '<button class="btn btn-secondary" id="stagingSkipBtn">Scan Directly</button>';
  if (existingSession) {
    html += '<button class="btn btn-secondary" id="stagingReuseBtn">Use Existing Copy</button>';
  }
  html += '<button class="btn btn-primary" id="stagingGoBtn">Copy Locally First</button></div>'
    + '<div style="border-top:1px solid var(--border);margin-top:14px;padding-top:12px;font-size:13px;color:var(--text-dim);">'
    + '<span style="color:#fff;font-weight:600;">Copy Locally First</span> is recommended. It avoids sync issues during scanning.<br><br>'
    + '<span style="color:#fff;font-weight:600;">Scan Directly</span> scans the folder as-is. May have issues with cloud-only files or sync locks.'
    + '</div>'
    + '<div style="margin-top:12px;"><button class="btn btn-danger" onclick="closeDialog()">Cancel</button></div>';

  document.getElementById("dialogMessage").innerHTML = html;
  document.getElementById("dialogConfirmBtn").style.display = "none";
  document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-secondary").style.display = "none";
  document.getElementById("dialogOverlay").classList.add("active");

  document.getElementById("stagingGoBtn").onclick = function() {
    closeDialog();
    document.getElementById("dialogConfirmBtn").style.display = "";
    document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-secondary").style.display = "";
    startStaging(dir, stagingDir, mode, threshold, recursive);
  };
  document.getElementById("stagingSkipBtn").onclick = function() {
    closeDialog();
    document.getElementById("dialogConfirmBtn").style.display = "";
    document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-secondary").style.display = "";
    _checkResumeAndStart(dir, mode, threshold, recursive);
  };
  if (existingSession) {
    document.getElementById("stagingReuseBtn").onclick = function() {
      closeDialog();
      document.getElementById("dialogConfirmBtn").style.display = "";
      document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-secondary").style.display = "";
      _stagingSession = { source_dir: dir, staging_dir: existingSession.staging_dir,
                          mode: mode, threshold: threshold, recursive: recursive };
      _checkResumeAndStart(existingSession.staging_dir, mode, threshold, recursive);
    };
  }
}

function _checkResumeAndStart(dir, mode, threshold, recursive, autoRecycle, scanLimit) {
  api("GET", "/api/scan/check-resume?directory=" + encodeURIComponent(dir) + "&mode=" + mode)
    .then(function(data) {
      if (data.has_checkpoint) {
        var info = data.checkpoint_info;
        var cached = (info.md5_hashed || 0) + (info.phash_hashed || 0);
        var ts = info.timestamp ? new Date(info.timestamp).toLocaleString() : "unknown";
        showResumeDialog(
          "An interrupted scan was found for this folder.",
          "Stage: " + info.stage + " | Hashes cached: " + cached + " | Last active: " + ts,
          function() { _doStartScan(dir, mode, threshold, recursive, true, autoRecycle, scanLimit); },
          function() { _doStartScan(dir, mode, threshold, recursive, false, autoRecycle, scanLimit); }
        );
      } else {
        _doStartScan(dir, mode, threshold, recursive, false, autoRecycle, scanLimit);
      }
    })
    .catch(function() {
      _doStartScan(dir, mode, threshold, recursive, false, autoRecycle, scanLimit);
    });
}

function _doStartScan(dir, mode, threshold, recursive, resume, autoRecycle, scanLimit) {
  _lastScanMode = mode;
  api("POST", "/api/scan/start", {
    directory: dir, mode: mode, threshold: threshold, recursive: recursive,
    resume: resume, auto_recycle: !!autoRecycle, scan_limit: scanLimit || 0
  }).then(function() {
    navigate("scan-progress");
  }).catch(function(err) {
    toast("Error: " + err.message, "error");
  });
}

/* ==================================================================
   SCAN PROGRESS
   ================================================================== */
var _scanStartTime = null;
var _lastScanMode = "exact";

function initScanProgress() {
  // Reset UI
  document.getElementById("scanProgressActions").style.display = "block";
  document.getElementById("scanCompleteBox").style.display = "none";
  document.getElementById("scanProgressFill").style.width = "0%";
  document.getElementById("scanProgressPct").textContent = "0%";
  _scanStartTime = Date.now();

  // Connect progress stream
  window._onScanProgress = function(d) {
    updateScanUI(d);
    if (d.status === "complete" || d.status === "error" || d.status === "cancelled") {
      window._onScanProgress = null;
      showScanComplete(d);
    }
  };
  window.pywebview.api.subscribe_scan_progress();
}

function updateScanUI(d) {
  var stageNames = {
    "discovering": "Discovering images...",
    "md5": "Computing checksums...",
    "auto_recycling": "Auto-recycling exact duplicates...",
    "phash_hash": "Computing perceptual hashes...",
    "phash_compare": "Comparing images...",
    "saving": "Saving results...",
    "done": "Complete"
  };
  document.getElementById("scanStage").textContent = stageNames[d.stage] || d.stage || "Working...";
  document.getElementById("scanErrors").textContent = d.errors || 0;

  // Grey out cancel button at point of no return (saving phase)
  var noReturn = (d.stage === "saving" || d.stage === "auto_recycling" || d.stage === "done");
  var cancelBtn = document.getElementById("scanCancelBtn");
  var wizCancelBtn = document.getElementById("wizScanCancelBtn");
  if (cancelBtn) cancelBtn.disabled = noReturn;
  if (wizCancelBtn) wizCancelBtn.disabled = noReturn;

  // Weighted overall progress so the bar never sits at 100% while work remains.
  // Weights depend on which scan mode is active.
  var pct = 0;
  var stage = d.stage || "";
  var stagePct = (d.total > 0) ? (d.current / d.total) : 0;
  var mode = d.mode || _lastScanMode || "exact";

  if (mode === "exact") {
    // exact only: discovering 0-5, md5 5-95, saving 95-100
    if (stage === "discovering") pct = stagePct * 5;
    else if (stage === "md5") pct = 5 + stagePct * 90;
    else if (stage === "saving") pct = 95;
    else if (stage === "done") pct = 100;
  } else if (mode === "perceptual") {
    // perceptual only: discovering 0-5, phash_hash 5-55, phash_compare 55-95, saving 95-100
    if (stage === "discovering") pct = stagePct * 5;
    else if (stage === "phash_hash") pct = 5 + stagePct * 50;
    else if (stage === "phash_compare") pct = 55 + stagePct * 40;
    else if (stage === "saving") pct = 95;
    else if (stage === "done") pct = 100;
  } else {
    // both: discovering 0-5, md5 5-25, phash_hash 25-60, phash_compare 60-95, saving 95-100
    if (stage === "discovering") pct = stagePct * 5;
    else if (stage === "md5") pct = 5 + stagePct * 20;
    else if (stage === "phash_hash") pct = 25 + stagePct * 35;
    else if (stage === "phash_compare") pct = 60 + stagePct * 35;
    else if (stage === "saving") pct = 95;
    else if (stage === "done") pct = 100;
  }

  pct = Math.round(pct);
  document.getElementById("scanProgressFill").style.width = pct + "%";
  document.getElementById("scanProgressPct").textContent = pct + "%";

  // Show per-stage counts for context
  if (d.total > 0) {
    document.getElementById("scanProgressLeft").textContent =
      (d.current || 0).toLocaleString() + " / " + (d.total || 0).toLocaleString();
  } else {
    document.getElementById("scanProgressLeft").textContent = "";
  }

  var elapsed = (Date.now() - _scanStartTime) / 1000;
  document.getElementById("scanElapsed").textContent = formatTime(elapsed);

  if (pct > 0 && pct < 95) {
    var remaining = (elapsed / pct) * (100 - pct);
    document.getElementById("scanETA").textContent = formatTime(remaining);
  } else {
    document.getElementById("scanETA").textContent = "--";
  }
}

function showScanComplete(d) {
  document.getElementById("scanProgressActions").style.display = "none";
  document.getElementById("scanCompleteBox").style.display = "block";
  document.getElementById("scanProgressPct").textContent = d.status === "complete" ? "Done" : d.status;

  // Show Finalize button if there are files to finalize (dupes or keepers)
  var finalizeBtn = document.getElementById("scanFinalizeBtn");
  if (finalizeBtn) {
    var hasDupesOrKeepers = !!(_dashFolderPaths.dupes || _dashFolderPaths.keepers);
    finalizeBtn.style.display = hasDupesOrKeepers ? "inline-flex" : "none";
  }

  if (d.status === "complete") {
    _sessionScanCompleted = true;
    document.getElementById("scanCompleteTitle").textContent = "Scan Complete";
    document.getElementById("scanCompleteTitle").style.color = "var(--accent)";
  } else if (d.status === "cancelled") {
    document.getElementById("scanCompleteTitle").textContent = "Scan Cancelled";
    document.getElementById("scanCompleteTitle").style.color = "var(--warning)";
  } else {
    document.getElementById("scanCompleteTitle").textContent = "Scan Error";
    document.getElementById("scanCompleteTitle").style.color = "var(--danger)";
  }

  document.getElementById("scanCompleteMsg").textContent = d.message || "";

  // Show return-to-folder button if scan was launched from a folder
  var retBtn = document.getElementById("scanReturnFolderBtn");
  if (retBtn) {
    if (_lastScanContext) {
      var labels = { staging: "Staging", dupes: "Recovery", keepers: "Keepers" };
      retBtn.textContent = "Return to " + (labels[_lastScanContext] || "Folder");
      retBtn.style.display = "inline-flex";
    } else {
      retBtn.style.display = "none";
    }
  }

  if (d.summary) {
    var s = d.summary;
    var html = '<div class="card-grid">';
    html += '<div class="stat-card"><div class="num">' + s.total_images + '</div><div class="label">Images Scanned</div></div>';
    html += '<div class="stat-card"><div class="num">' + s.total_groups + '</div><div class="label">Duplicate Groups</div></div>';
    html += '<div class="stat-card"><div class="num">' + (s.total_duplicate_files || 0) + '</div><div class="label">Duplicate Files</div></div>';
    html += '<div class="stat-card"><div class="num">' + s.reclaimable_mb + ' MB</div><div class="label">Reclaimable</div></div>';
    html += '<div class="stat-card"><div class="num">' + formatTime(s.duration) + '</div><div class="label">Duration</div></div>';
    if (s.auto_recycled && s.auto_recycled > 0) {
      html += '<div class="stat-card"><div class="num">' + s.auto_recycled + '</div><div class="label">Auto-Recycled</div></div>';
    }
    html += '</div>';
    document.getElementById("scanCompleteSummary").innerHTML = html;
  }

  if (d.result_file) {
    var totalGroups = (d.summary && d.summary.total_groups) || 0;
    if (totalGroups === 0) {
      // No dupes found — hide review, show message. Rescan/Dashboard already in static buttons.
      document.getElementById("scanReviewBtn").style.display = "none";
      document.getElementById("scanCompleteSummary").innerHTML +=
        '<div style="margin-top:16px;text-align:center;">' +
        '<p style="color:var(--text-dim);">No duplicates found at this threshold. Try a different scan mode or a higher perceptual threshold.</p>' +
        '</div>';
    } else {
      var btn = document.getElementById("scanReviewBtn");
      btn.style.display = "inline-flex";
      btn.onclick = function() { navigate("review", { report: d.result_file }); };
      // Easy mode: add power loop quick-move button
      if (typeof addPowerLoopButton === "function") {
        addPowerLoopButton(d.result_file, "#scanCompleteSummary");
      }
    }
  }
}

function cancelScan() {
  api("POST", "/api/scan/cancel").then(function() {
    toast("Cancelling scan...", "warning");
  });
}

