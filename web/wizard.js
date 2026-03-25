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
  // Single source of truth: derive wizard state from filesystem
  getAppState().then(function(appState) {
    var s = appState.folders.staging;
    var session = appState.session;

    // Load settings for dupes dir
    api("GET", "/api/settings").then(function(settings) {
      wizardState.dupesDir = settings.move_destination || "";
    }).catch(function() {});

    document.getElementById("wizSourceDir").value = wizardState.sourceDir || "";

    // Step 1: Do we have files in staging with a known source?
    if (session.active && s.count > 0) {
      wizardState.stagingDir = session.staging_dir;
      wizardState.sourceDir = session.source_dir;
      wizardState.completedSteps[1] = true;
      document.getElementById("wizSourceDir").value = session.source_dir || "";
      _stagingSession = { source_dir: session.source_dir, staging_dir: session.staging_dir };

      // Step 2: Do we have scans for this staging dir?
      for (var i = 0; i < appState.scans.length; i++) {
        if (appState.scans[i].directory === session.staging_dir && appState.scans[i].total_groups > 0) {
          wizardState.lastReport = appState.scans[i].filename;
          wizardState.completedSteps[2] = true;
          break;
        }
      }
    } else if (s.exists && s.count > 0) {
      // Staging has files but no manifest (e.g. from Rescue & Review)
      wizardState.stagingDir = s.path;
      wizardState.completedSteps[1] = true;
    }

    _wizardDetermineStep();
  }).catch(function() {
    _wizardDetermineStep();
  });
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

var _wizardStepHandlers = {
  1: function() {
    if (wizardState.completedSteps[1]) {
      document.getElementById("wizMigrateBtn").disabled = true;
      document.getElementById("wizMigrateBtn").textContent = "Migration Complete";
      document.getElementById("wizMigrateComplete").style.display = "block";
      document.getElementById("wizMigrateCompleteMsg").textContent =
        "Files staged to: " + (wizardState.stagingDir || "");
    }
  },
  2: function() {
    // Load settings for threshold
    api("GET", "/api/settings").then(function(s) {
      document.getElementById("wizThreshold").value = s.threshold || 5;
      document.getElementById("wizThresholdVal").textContent = s.threshold || 5;
    }).catch(function() {});
    // Show file count for staging folder
    var countEl = document.getElementById("wizScanFileCount");
    if (wizardState.stagingDir) {
      api("POST", "/api/staging/check", { directory: wizardState.stagingDir }).then(function(r) {
        var count = r.source_count;
        if (typeof count === "object") count = count[0] || 0;
        if (count > 0) {
          countEl.textContent = count.toLocaleString() + " images ready to scan";
          countEl.style.display = "block";
        } else {
          countEl.style.display = "none";
        }
      }).catch(function() { countEl.style.display = "none"; });
    }
  },
  3: function() {
    if (wizardState.lastReport) {
      document.getElementById("wizReviewInfoText").textContent =
        "Report: " + wizardState.lastReport;
    }
  },
  4: function() {
    // Fetch file counts for browse buttons
    api("GET", "/api/folders/status").then(function(data) {
      var sBtn = document.getElementById("wizStagingBtn");
      var dBtn = document.getElementById("wizDupesBtn");
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
      } else {
        dBtn.textContent = "Recovery (empty)";
        dBtn.disabled = true;
      }
    }).catch(function() {});
  }
};

function wizardGoToStep(n) {
  wizardState.currentStep = n;
  // Show/hide panels
  for (var i = 1; i <= 4; i++) {
    var panel = document.getElementById("wizardStep" + i);
    if (panel) panel.classList.toggle("active", i === n);
  }
  updateStepper();
  // Step-specific init
  var handler = _wizardStepHandlers[n];
  if (handler) handler();
}

function updateStepper() {
  var steps = document.querySelectorAll(".wizard-step");
  for (var i = 0; i < steps.length; i++) {
    var stepNum = parseInt(steps[i].getAttribute("data-step"));
    steps[i].classList.remove("active", "completed", "clickable");
    steps[i].onclick = null;

    if (wizardState.completedSteps[stepNum]) {
      steps[i].classList.add("completed");
      document.getElementById("wizStep" + stepNum + "Circle").innerHTML = "&#10003;";
      // Step 1 is locked once complete -- users can't re-migrate while files exist
      if (stepNum !== 1) {
        steps[i].classList.add("clickable");
        (function(n) {
          steps[i].onclick = function() { wizardGoToStep(n); };
        })(stepNum);
      }
    } else if (stepNum === wizardState.currentStep) {
      steps[i].classList.add("active", "clickable");
      document.getElementById("wizStep" + stepNum + "Circle").textContent = stepNum;
      (function(n) {
        steps[i].onclick = function() { wizardGoToStep(n); };
      })(stepNum);
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
  // Check if mode wants to handle navigation differently
  if (typeof modeWizardComplete === "function" && modeWizardComplete(n)) {
    return; // mode handled it (e.g., manual goes to dashboard after step 1)
  }
  // Auto-advance to next step
  if (n < 4) wizardGoToStep(n + 1);
}

function wizardStartMigration() {
  var dir = document.getElementById("wizSourceDir").value.trim();
  if (!dir) { toast("Please enter a source folder", "error"); return; }

  wizardState.sourceDir = dir;
  // Check OneDrive before starting migration
  checkOneDriveBeforeOperation(dir, "migration", function() {
    _doWizardMigration(dir);
  });
}

function _doWizardMigration(dir) {
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
        // If no files were migrated, go back to dashboard
        if (d.total === 0 || d.current === 0) {
          document.getElementById("wizMigrateBtn").disabled = false;
          toast("No image files found in that folder.", "warning");
          navigate("dashboard");
          return;
        }
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

  // Start scan and navigate to the dedicated full-screen progress page
  api("POST", "/api/scan/start", {
    directory: wizardState.stagingDir, mode: mode,
    threshold: threshold, recursive: recursive, resume: false
  }).then(function() {
    navigate("scan-progress");
  }).catch(function(err) {
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

