// ---- Wizard ----
var wizardState = {
  currentStep: 1,
  completedSteps: {},
  stagingDir: null,
  sourceDir: null,
  lastReport: null,
  dupesDir: null,
  browserReturnTo: "wizard"
};

function initWizard() {
  // If RnR already set up the wizard state, validate directory exists (Issue 27)
  if (wizardState.completedSteps[1] && wizardState.stagingDir) {
    // Quick check - will be validated properly by the async path below
    _wizardDetermineStep();
  }

  // Load settings first — also detect existing staging session
  // so restart/refresh lands on the right step
  api("GET", "/api/settings").then(function(s) {
    wizardState.dupesDir = s.move_destination || "";
    var defaultSource = s.default_pictures_path || "";
    document.getElementById("wizSourceDir").value = wizardState.sourceDir || defaultSource;

    // Check for existing staging session (in-memory first, then on-disk manifest)
    return api("GET", "/api/staging/status").then(function(d) {
      if (d.status === "complete" && d.staging_dir) {
        wizardState.stagingDir = d.staging_dir;
        wizardState.sourceDir = d.source_dir;
        wizardState.completedSteps[1] = true;
        document.getElementById("wizSourceDir").value = d.source_dir || defaultSource;
        _stagingSession = { source_dir: d.source_dir, staging_dir: d.staging_dir };
        return _wizardCheckScans();
      }
      // Check on-disk manifest via staging/check
      var src = document.getElementById("wizSourceDir").value;
      return api("POST", "/api/staging/check", { directory: src }).then(function(result) {
        if (result.existing_session && result.existing_session.staging_dir) {
          wizardState.stagingDir = result.existing_session.staging_dir;
          wizardState.sourceDir = src;
          wizardState.completedSteps[1] = true;
          _stagingSession = { source_dir: src, staging_dir: result.existing_session.staging_dir };
          return _wizardCheckScans();
        }
        // Last resort: check if staging folder has files (e.g. from Rescue & Review)
        return api("GET", "/api/folders/status").then(function(fs) {
          if (fs.staging && fs.staging.exists && fs.staging.file_count > 0) {
            wizardState.stagingDir = fs.staging.path;
            wizardState.completedSteps[1] = true;
            return _wizardCheckScans();
          }
          _wizardDetermineStep();
        });
      });
    });
  }).catch(function() { _wizardDetermineStep(); });
}

function _wizardCheckScans() {
  return api("GET", "/api/scans").then(function(scans) {
    for (var i = 0; i < scans.length; i++) {
      if (scans[i].directory === wizardState.stagingDir && scans[i].total_groups > 0) {
        wizardState.lastReport = scans[i].filename;
        wizardState.completedSteps[2] = true;
        break;
      }
    }
    _wizardDetermineStep();
  }).catch(function() { _wizardDetermineStep(); });
}

function _wizardDetermineStep() {
  // Find the first incomplete step
  var step = 1;
  if (wizardState.completedSteps[1]) step = 2;
  if (wizardState.completedSteps[2]) step = 3;
  if (wizardState.completedSteps[3]) step = 4;
  wizardGoToStep(step);
}

function wizardGoToStep(n) {
  wizardState.currentStep = n;
  // Show/hide panels
  for (var i = 1; i <= 4; i++) {
    var panel = document.getElementById("wizardStep" + i);
    if (panel) panel.classList.toggle("active", i === n);
  }
  updateStepper();
  // Step-specific init
  if (n === 1) {
    if (wizardState.completedSteps[1]) {
      document.getElementById("wizMigrateBtn").disabled = true;
      document.getElementById("wizMigrateBtn").textContent = "Migration Complete";
      document.getElementById("wizMigrateComplete").style.display = "block";
      document.getElementById("wizMigrateCompleteMsg").textContent =
        "Files staged to: " + (wizardState.stagingDir || "");
    }
  }
  if (n === 2) {
    // Load settings for threshold
    api("GET", "/api/settings").then(function(s) {
      document.getElementById("wizThreshold").value = s.threshold || 5;
      document.getElementById("wizThresholdVal").textContent = s.threshold || 5;
    }).catch(function() {});
  }
  if (n === 3 && wizardState.lastReport) {
    document.getElementById("wizReviewInfoText").textContent =
      "Report: " + wizardState.lastReport;
  }
  if (n === 4) {
    // Fetch file counts for browse buttons
    api("GET", "/api/folders/status").then(function(data) {
      var sBtn = document.getElementById("wizStagingBtn");
      var dBtn = document.getElementById("wizDupesBtn");
      if (data.staging && data.staging.exists && data.staging.file_count > 0) {
        sBtn.textContent = "My Files (" + data.staging.file_count.toLocaleString() + ")";
        sBtn.disabled = false;
      } else {
        sBtn.textContent = "My Files (empty)";
        sBtn.disabled = true;
      }
      if (data.dupes && data.dupes.exists && data.dupes.file_count > 0) {
        dBtn.textContent = "Removed Duplicates (" + data.dupes.file_count.toLocaleString() + ")";
        dBtn.disabled = false;
      } else {
        dBtn.textContent = "Removed Duplicates (empty)";
        dBtn.disabled = true;
      }
    }).catch(function() {});
  }
}

function updateStepper() {
  var steps = document.querySelectorAll(".wizard-step");
  for (var i = 0; i < steps.length; i++) {
    var stepNum = parseInt(steps[i].getAttribute("data-step"));
    steps[i].classList.remove("active", "completed", "clickable");
    steps[i].onclick = null;

    if (wizardState.completedSteps[stepNum]) {
      steps[i].classList.add("completed", "clickable");
      document.getElementById("wizStep" + stepNum + "Circle").innerHTML = "&#10003;";
      (function(n) {
        steps[i].onclick = function() { wizardGoToStep(n); };
      })(stepNum);
    } else if (stepNum === wizardState.currentStep) {
      steps[i].classList.add("active");
      document.getElementById("wizStep" + stepNum + "Circle").textContent = stepNum;
    } else {
      document.getElementById("wizStep" + stepNum + "Circle").textContent = stepNum;
      // Allow clicking steps up to current
      if (stepNum <= wizardState.currentStep) {
        steps[i].classList.add("clickable");
        (function(n) {
          steps[i].onclick = function() { wizardGoToStep(n); };
        })(stepNum);
      }
    }
  }
  // Update connecting lines
  for (var i = 1; i <= 3; i++) {
    var line = document.getElementById("wizLine" + i);
    if (line) line.classList.toggle("done", !!wizardState.completedSteps[i]);
  }
}

function wizardMarkComplete(n) {
  wizardState.completedSteps[n] = true;
  updateStepper();
  // Auto-advance to next step
  if (n < 4) wizardGoToStep(n + 1);
}

function wizardStartMigration() {
  var dir = document.getElementById("wizSourceDir").value.trim();
  if (!dir) { toast("Please enter a source folder", "error"); return; }

  wizardState.sourceDir = dir;
  document.getElementById("wizMigrateBtn").disabled = true;
  document.getElementById("wizMigrateProgress").style.display = "block";
  document.getElementById("wizMigrateInfo").style.display = "none";

  api("POST", "/api/staging/start", { source_dir: dir }).then(function(d) {
    wizardState.stagingDir = d.staging_dir;
    // Connect progress stream
    function _onWizStaging(d) {
      var pct = d.total > 0 ? Math.round((d.current / d.total) * 100) : 0;
      document.getElementById("wizMigFill").style.width = pct + "%";
      document.getElementById("wizMigPct").textContent = pct + "%";
      document.getElementById("wizMigLeft").textContent = d.current + " / " + d.total + " files";
      var mb = d.bytes_copied ? Math.round(d.bytes_copied / (1024*1024)) : 0;
      var mbT = d.bytes_total ? Math.round(d.bytes_total / (1024*1024)) : 0;
      document.getElementById("wizMigRight").textContent = mb + " / " + mbT + " MB";

      if (d.status === "complete") {
        window._onStagingProgress = null;
        document.getElementById("wizMigrateProgress").style.display = "none";
        document.getElementById("wizMigrateComplete").style.display = "block";
        document.getElementById("wizMigrateCompleteMsg").textContent = d.message || "Migration complete";
        wizardState.stagingDir = d.staging_dir || wizardState.stagingDir;
        _stagingSession = {
          source_dir: wizardState.sourceDir,
          staging_dir: wizardState.stagingDir
        };
        _refreshFolderPaths();
        wizardMarkComplete(1);
      } else if (d.status === "error" || d.status === "cancelled") {
        window._onStagingProgress = null;
        document.getElementById("wizMigrateProgress").style.display = "none";
        document.getElementById("wizMigrateBtn").disabled = false;
        toast(d.message || "Migration failed", "error");
      }
    }
    window._onStagingProgress = _onWizStaging;
    window.pywebview.api.subscribe_staging_progress();
  }).catch(function(err) {
    document.getElementById("wizMigrateBtn").disabled = false;
    document.getElementById("wizMigrateProgress").style.display = "none";
    toast("Migration error: " + err.message, "error");
  });
}

function wizardStartScan() {
  if (!wizardState.stagingDir) { toast("Complete migration first", "error"); return; }

  var modeEl = document.querySelector('input[name="wizScanMode"]:checked');
  var mode = modeEl ? modeEl.value : "exact";
  var threshold = parseInt(document.getElementById("wizThreshold").value) || 5;
  var recursive = document.getElementById("wizRecursive").checked;

  document.getElementById("wizScanActions").style.display = "none";
  document.getElementById("wizScanProgress").style.display = "block";
  document.getElementById("wizScanComplete").style.display = "none";

  // Check for resume first
  api("GET", "/api/scan/check-resume?directory=" + encodeURIComponent(wizardState.stagingDir) + "&mode=" + mode)
    .then(function(data) {
      var resume = false;
      if (data.has_checkpoint) {
        // Auto-resume in wizard mode
        resume = true;
      }
      return api("POST", "/api/scan/start", {
        directory: wizardState.stagingDir, mode: mode,
        threshold: threshold, recursive: recursive, resume: resume
      });
    })
    .then(function() {
      function _onWizScan(d) {
        var pct = d.total > 0 ? Math.round((d.current / d.total) * 100) : 0;
        document.getElementById("wizScanFill").style.width = pct + "%";
        document.getElementById("wizScanPct").textContent = pct + "%";
        document.getElementById("wizScanLeft").textContent = d.current + " / " + d.total;
        document.getElementById("wizScanStage").textContent = d.stage || "scanning";
        if (d.status === "complete") {
          window._onScanProgress = null;
          document.getElementById("wizScanProgress").style.display = "none";
          document.getElementById("wizScanComplete").style.display = "block";
          document.getElementById("wizScanCompleteMsg").textContent = d.message || "Scan complete";
          wizardState.lastReport = d.result_file;
          wizardMarkComplete(2);
        } else if (d.status === "error" || d.status === "cancelled") {
          window._onScanProgress = null;
          document.getElementById("wizScanProgress").style.display = "none";
          document.getElementById("wizScanActions").style.display = "block";
          toast(d.message || "Scan failed", "error");
        }
      }
      window._onScanProgress = _onWizScan;
      window.pywebview.api.subscribe_scan_progress();
    })
    .catch(function(err) {
      document.getElementById("wizScanProgress").style.display = "none";
      document.getElementById("wizScanActions").style.display = "block";
      toast("Scan error: " + err.message, "error");
    });
}

function wizardStartReview() {
  if (!wizardState.lastReport) { toast("Complete a scan first", "error"); return; }
  // Validate report still exists before navigating (Issue 28)
  api("GET", "/api/scans").then(function(scans) {
    var found = false;
    for (var i = 0; i < scans.length; i++) {
      if (scans[i].filename === wizardState.lastReport) { found = true; break; }
    }
    if (found) {
      wizardState.browserReturnTo = "wizard";
      navigate("review", { report: wizardState.lastReport, returnTo: "wizard" });
    } else {
      // Report was deleted -- try to find another matching scan
      for (var j = 0; j < scans.length; j++) {
        if (scans[j].directory === wizardState.stagingDir && scans[j].total_groups > 0) {
          wizardState.lastReport = scans[j].filename;
          wizardState.browserReturnTo = "wizard";
          navigate("review", { report: wizardState.lastReport, returnTo: "wizard" });
          return;
        }
      }
      wizardState.lastReport = null;
      wizardState.completedSteps[2] = false;
      toast("Scan report no longer available. Please rescan.", "warning");
      wizardGoToStep(2);
    }
  }).catch(function() {
    // If API fails, try navigating anyway and let review handle the error
    wizardState.browserReturnTo = "wizard";
    navigate("review", { report: wizardState.lastReport, returnTo: "wizard" });
  });
}

