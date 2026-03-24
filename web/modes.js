/* ==================================================================
   WORKFLOW MODES
   4 modes: easy, autonomous, hybrid, manual
   Locked for this version -- no additional modes.
   ================================================================== */

// ---- Mode Accessors ----

function getCurrentMode() {
  return (state.settings && state.settings.workflow_mode) || "";
}

function setCurrentMode(mode) {
  if (state.settings) state.settings.workflow_mode = mode;
}

// ---- Nav Visibility Config ----
// true = visible, false = hidden via display:none
// IDs match the nav button data-view or id attributes

var _modeNavConfig = {
  easy: {
    navMigrate: true,
    navScan: false,
    navReview: false,
    navFinalize: false,
    navMyFiles: false,
    navDupes: false,
    navKeepers: false,
    navLogs: false
  },
  autonomous: {
    navMigrate: false,
    navScan: false,
    navReview: false,
    navFinalize: false,
    navMyFiles: false,
    navDupes: false,
    navKeepers: false,
    navLogs: false
  },
  hybrid: {
    navMigrate: true,
    navScan: true,
    navReview: true,
    navFinalize: true,
    navMyFiles: true,
    navDupes: true,
    navKeepers: true,
    navLogs: true
  },
  manual: {
    navMigrate: true,
    navScan: true,
    navReview: true,
    navFinalize: true,
    navMyFiles: true,
    navDupes: true,
    navKeepers: true,
    navLogs: true
  }
};

// Map data-view to actual element ids for nav buttons that use id attrs
var _navIdMap = {
  navMigrate: "navMigrate",
  navScan: "navScan",
  navReview: "navReview",
  navFinalize: "navFinalize",
  navMyFiles: "navMyFiles",
  navDupes: "navDupes",
  navKeepers: "navKeepers",
  navLogs: null  // Scan Logs uses data-view="activity", no id
};

// ---- Apply Mode to UI ----

function applyModeToUI(mode) {
  if (!mode) return;

  var cfg = _modeNavConfig[mode] || _modeNavConfig["hybrid"];

  // Nav visibility
  var keys = Object.keys(cfg);
  for (var i = 0; i < keys.length; i++) {
    var key = keys[i];
    var el = null;

    if (key === "navLogs") {
      // Scan Logs has no id -- find by data-view
      var allLinks = document.querySelectorAll(".nav-link");
      for (var j = 0; j < allLinks.length; j++) {
        if (allLinks[j].getAttribute("data-view") === "activity") {
          el = allLinks[j];
          break;
        }
      }
    } else {
      el = document.getElementById(key);
    }

    if (el) {
      el.style.display = cfg[key] ? "" : "none";
    }
  }

  // Easy mode: force hints/tooltips/explanations visible
  if (mode === "easy") {
    var hintsBar = document.getElementById("hintsBar");
    if (hintsBar) hintsBar.style.display = "block";
  }
}

// ---- Mode-Aware Dashboard ----

function modeAwareDashboard(mode) {
  if (!mode) return;

  var directScanBtn = document.getElementById("dashDirectScanBtn");
  var continueBtn = document.getElementById("dashContinueBtn");
  var moreOptions = document.getElementById("dashAdvancedOptions");

  if (mode === "easy") {
    // Hide Direct Scan, hide More Options (overwhelming for beginners)
    if (directScanBtn) directScanBtn.style.display = "none";
    if (moreOptions) moreOptions.style.display = "none";
    // Make guided cleanup button prominent
    if (continueBtn) {
      continueBtn.style.fontSize = "18px";
      continueBtn.style.padding = "16px 32px";
    }
  } else if (mode === "autonomous") {
    // Hide More Options, repurpose Continue button for autonomous
    if (directScanBtn) directScanBtn.style.display = "none";
    if (moreOptions) moreOptions.style.display = "none";
    // Show "Run Duplicate Cleanup" button -- replaces Continue Guided Cleanup
    if (continueBtn) {
      continueBtn.textContent = "Run Duplicate Cleanup";
      continueBtn.onclick = function() { navigate("autonomous"); };
    }
  } else if (mode === "manual") {
    // Hide wizard-style Continue button, make Direct Scan primary
    if (directScanBtn) {
      directScanBtn.className = "btn btn-primary btn-lg";
    }
    // Change Continue button to "Import Files" (step 1 only)
    var hasAnyFiles = !!(_dashFolderPaths.staging || _dashFolderPaths.dupes || _dashFolderPaths.keepers);
    if (continueBtn && !hasAnyFiles) {
      continueBtn.textContent = "Import Files";
      continueBtn.onclick = function() { _navToWizardStep(1); };
    }
  }
  // hybrid: no changes needed -- current behavior
}

// ---- Mode-Aware Hints ----

function getModeHintText(mode, view) {
  if (!mode || mode === "hybrid") return null; // null = use default hints

  if (mode === "easy") {
    var easyHints = {
      "dashboard": "Welcome! Start by importing your photos, then we'll find duplicates together.",
      "wizard": "Follow each step in order. We'll guide you through the whole process.",
      "scan-config": "Choose your scan settings. The defaults work well for most photos.",
      "scan-progress": "Sit tight! We're scanning your photos for duplicates.",
      "review": "Click images to mark them as keepers or duplicates. Take your time.",
      "actions": "Review what's about to happen, then click Execute when ready.",
      "finish": "Almost done! Review the summary, then send your files home.",
      "browser": "Browse through your files. Click any image to zoom in.",
      "settings": "Adjust your preferences here. Click Save when done."
    };
    return easyHints[view] || null;
  }

  if (mode === "autonomous") {
    var autoHints = {
      "dashboard": "Select a folder and PixHerder will automatically find and separate duplicates.",
      "autonomous": "PixHerder is working. Duplicates will be placed in a subfolder next to your originals.",
      "settings": "Adjust your preferences here. Click Save when done."
    };
    return autoHints[view] || null;
  }

  if (mode === "manual") {
    // Manual mode: terse hints, only for key views
    var manualHints = {
      "dashboard": "Import files, then scan from the dashboard or nav menu.",
      "scan-config": "Configure scan parameters.",
      "review": "Click images to toggle. Action bar below.",
      "scan-progress": "Scanning...",
      "actions": "Pending operations. Execute when ready."
    };
    return manualHints[view] || "";
  }

  return null;
}

// ---- Mode-Aware Wizard Behavior ----

function modeWizardComplete(stepNum) {
  // Called from wizardMarkComplete to handle mode-specific behavior
  // Returns true if the mode handled navigation (caller should NOT auto-advance)
  var mode = getCurrentMode();

  if (mode === "manual" && stepNum === 1) {
    // Manual: after migration, go straight to dashboard
    navigate("dashboard");
    return true;
  }

  if (mode === "autonomous" && stepNum === 1) {
    // Autonomous: after migration, go to autonomous pipeline
    navigate("autonomous");
    return true;
  }

  return false; // default: let wizard auto-advance as normal
}

// ---- Mode Selector (First Launch) ----

function showModeSelector(onSelect) {
  _modeSelectorCallback = onSelect;
  var overlay = document.getElementById("modeSelectOverlay");
  if (!overlay) return;
  overlay.style.display = "flex";

  var cards = document.getElementById("modeCards");
  if (!cards) return;

  var modes = [
    {
      id: "easy",
      name: "Easy",
      subtitle: "Guided",
      desc: "Step-by-step wizard with full explanations. Best for first-time users.",
      icon: "1"
    },
    {
      id: "autonomous",
      name: "Autonomous",
      subtitle: "One-Click",
      desc: "Set it and forget it. Auto-finds and separates all duplicates into a subfolder.",
      icon: "2"
    },
    {
      id: "hybrid",
      name: "Hybrid",
      subtitle: "Recommended",
      desc: "Wizard for setup, dashboard for control. The best of both worlds.",
      icon: "3"
    },
    {
      id: "manual",
      name: "Manual",
      subtitle: "Power User",
      desc: "Dashboard and nav menu only. Maximum control for experienced users.",
      icon: "4"
    }
  ];

  var html = "";
  for (var i = 0; i < modes.length; i++) {
    var m = modes[i];
    var recommended = m.id === "easy" ? ' style="border-color:var(--accent);"' : "";
    html += '<div class="mode-card" data-mode="' + m.id + '"' + recommended + '>';
    html += '<div class="mode-card-header">';
    html += '<span class="mode-card-name">' + m.name + '</span>';
    html += '<span class="mode-card-subtitle">' + m.subtitle + '</span>';
    html += '</div>';
    html += '<div class="mode-card-desc">' + m.desc + '</div>';
    if (m.id === "easy") {
      html += '<div class="mode-card-badge">Recommended</div>';
    }
    html += '</div>';
  }
  // Bypass button -- subtle, below the mode cards, spans full grid width
  html += '<div style="text-align:center;margin-top:8px;margin-bottom:-14px;grid-column:1/-1;">';
  html += '<button class="btn btn-ghost" style="font-size:12px;color:var(--text-dim);padding:4px 10px;" ';
  html += 'onclick="_bypassModeSelector()">Continue to Dashboard</button>';
  html += '</div>';
  cards.innerHTML = html;

  // Attach click handlers
  var cardEls = cards.querySelectorAll(".mode-card");
  for (var i = 0; i < cardEls.length; i++) {
    (function(el) {
      el.onclick = function() {
        var mode = el.getAttribute("data-mode");
        overlay.style.display = "none";
        if (onSelect) onSelect(mode);
      };
    })(cardEls[i]);
  }
}

function closeModeSelector() {
  var overlay = document.getElementById("modeSelectOverlay");
  if (overlay) overlay.style.display = "none";
}

// ---- Mode-Aware Landing View ----

function getModeLandingView(mode) {
  if (mode === "easy") return "wizard";
  if (mode === "autonomous") return "autonomous";
  return "dashboard"; // hybrid + manual both land on dashboard
}

// ---- Autonomous Pipeline ----

var _autoState = {
  phase: "",        // migrate, scan, move, complete
  sourceDir: "",
  stagingDir: "",
  reportFile: "",
  totalMoved: 0,
  dupesFolder: ""
};

function initAutonomous() {
  // Reset UI phases
  document.getElementById("autoSetup").style.display = "block";
  document.getElementById("autoProgress").style.display = "none";
  document.getElementById("autoComplete").style.display = "none";

  // Pre-fill source dir if we know it from app state
  api("GET", "/api/app/state").then(function(appState) {
    if (appState && appState.session && appState.session.source_dir) {
      document.getElementById("autoSourceDir").value = appState.session.source_dir;
    }
  }).catch(function() {});
}

function _startAutonomous() {
  var sourceDir = document.getElementById("autoSourceDir").value.trim();
  if (!sourceDir) {
    toast("Please select a source folder", "error");
    return;
  }

  _autoState.sourceDir = sourceDir;
  _autoState.dupesFolder = sourceDir + "\\PixHerder_Duplicates";

  // Check OneDrive before starting
  checkOneDriveBeforeOperation(sourceDir, "autonomous cleanup", function() {
    _autoPhase1_migrate(sourceDir);
  });
}

function _autoUpdatePhase(phase, label) {
  _autoState.phase = phase;
  document.getElementById("autoSetup").style.display = "none";
  document.getElementById("autoProgress").style.display = "block";
  document.getElementById("autoComplete").style.display = "none";
  document.getElementById("autoPhaseLabel").textContent = label;
  document.getElementById("autoProgressFill").style.width = "0%";
  document.getElementById("autoProgressPct").textContent = "0%";
  document.getElementById("autoProgressLeft").textContent = "";
  document.getElementById("autoStageLabel").textContent = "";
}

function _autoUpdateProgress(current, total, stageText) {
  if (total > 0) {
    var pct = Math.round((current / total) * 100);
    document.getElementById("autoProgressFill").style.width = pct + "%";
    document.getElementById("autoProgressPct").textContent = pct + "%";
    document.getElementById("autoProgressLeft").textContent = current.toLocaleString() + " / " + total.toLocaleString();
  }
  if (stageText) {
    document.getElementById("autoStageLabel").textContent = stageText;
  }
}

function _autoPhase1_migrate(sourceDir) {
  _autoUpdatePhase("migrate", "Phase 1: Importing your files...");

  api("POST", "/api/staging/start", { source_dir: sourceDir }).then(function(d) {
    if (d.status === "started" || d.status === "already_running") {
      _autoState.stagingDir = d.staging_dir || "";
      // Subscribe to staging progress
      if (window.pywebview && window.pywebview.api) {
        window._onStagingProgress = function(p) {
          _autoUpdateProgress(p.current || 0, p.total || 0, "Copying files...");
          if (p.status === "complete" || p.status === "done") {
            window._onStagingProgress = null;
            _autoState.stagingDir = p.staging_dir || _autoState.stagingDir;
            _autoPhase2_scan();
          } else if (p.status === "error") {
            window._onStagingProgress = null;
            _autoComplete(0, "Migration failed: " + (p.message || "Unknown error"));
          }
        };
        window.pywebview.api.subscribe_staging_progress();
      }
    } else if (d.status === "exists") {
      // Already migrated -- skip to scan
      _autoState.stagingDir = d.staging_dir || "";
      _autoPhase2_scan();
    } else {
      _autoComplete(0, "Migration failed: " + (d.message || "Unknown error"));
    }
  }).catch(function(err) {
    _autoComplete(0, "Migration failed: " + (err.message || "Unknown error"));
  });
}

function _autoPhase2_scan() {
  _autoUpdatePhase("scan", "Phase 2: Scanning for duplicates...");

  var scanDir = _autoState.stagingDir;
  if (!scanDir) {
    _autoComplete(0, "No staging directory found.");
    return;
  }

  var settings = state.settings || {};
  api("POST", "/api/scan/start", {
    directory: scanDir,
    mode: "both",
    threshold: settings.threshold || 5,
    recursive: true,
    resume: false,
    auto_recycle_exact: false,
    hash_size: settings.hash_size || 16,
    scan_batch_size: 0  // scan all at once
  }).then(function() {
    // Subscribe to scan progress
    if (window.pywebview && window.pywebview.api) {
      window._onScanProgress = function(d) {
        var stage = d.stage || "";
        var stageLabels = {
          "discovering": "Discovering images...",
          "md5": "Computing checksums...",
          "phash": "Computing perceptual hashes...",
          "comparing": "Comparing images...",
          "saving": "Saving results...",
          "auto_recycling": "Auto-recycling exact duplicates..."
        };
        _autoUpdateProgress(d.current || 0, d.total || 0, stageLabels[stage] || stage);

        if (d.status === "complete") {
          window._onScanProgress = null;
          if (d.result_file) {
            _autoState.reportFile = d.result_file;
            var groups = (d.summary && d.summary.total_groups) || 0;
            if (groups === 0) {
              _autoComplete(0, "No duplicates found. Your files look clean!");
            } else {
              _autoPhase3_move(d.result_file);
            }
          } else {
            _autoComplete(0, "Scan completed but no results file was generated.");
          }
        } else if (d.status === "error") {
          window._onScanProgress = null;
          _autoComplete(0, "Scan failed: " + (d.message || "Unknown error"));
        } else if (d.status === "cancelled") {
          window._onScanProgress = null;
          _autoComplete(0, "Scan was cancelled.");
        }
      };
      window.pywebview.api.subscribe_scan_progress();
    }
  }).catch(function(err) {
    _autoComplete(0, "Scan failed: " + (err.message || "Unknown error"));
  });
}

function _autoPhase3_move(reportFile) {
  _autoUpdatePhase("move", "Phase 3: Separating duplicates...");

  // Load groups from the scan report
  api("GET", "/api/groups?report=" + encodeURIComponent(reportFile)).then(function(data) {
    var groups = data.groups || [];
    if (groups.length === 0) {
      _autoComplete(0, "No duplicate groups found.");
      return;
    }

    // Move ALL duplicate files (auto-mark everything as dupe)
    var destination = _autoState.dupesFolder;

    api("POST", "/api/action/move", {
      groups: groups,
      destination: destination,
      report: reportFile
    }).then(function() {
      // Subscribe to action progress
      if (window.pywebview && window.pywebview.api) {
        window._onActionProgress = function(d) {
          _autoUpdateProgress(d.current || 0, d.total || 0, "Moving duplicates...");

          if (d.status === "complete") {
            window._onActionProgress = null;
            var result = d.result || {};
            _autoState.totalMoved = result.moved || 0;
            _autoComplete(_autoState.totalMoved, null);
          } else if (d.status === "error") {
            window._onActionProgress = null;
            _autoComplete(0, "Move failed: " + (d.message || "Unknown error"));
          }
        };
        window.pywebview.api.subscribe_action_progress();
      }
    }).catch(function(err) {
      _autoComplete(0, "Move failed: " + (err.message || "Unknown error"));
    });
  }).catch(function(err) {
    _autoComplete(0, "Could not load scan results: " + (err.message || "Unknown error"));
  });
}

function _autoComplete(movedCount, errorMsg) {
  document.getElementById("autoSetup").style.display = "none";
  document.getElementById("autoProgress").style.display = "none";
  document.getElementById("autoComplete").style.display = "block";

  var title = document.getElementById("autoCompleteTitle");
  var summary = document.getElementById("autoCompleteSummary");

  if (errorMsg) {
    title.textContent = "Something went wrong";
    title.style.color = "var(--danger)";
    summary.innerHTML = '<p style="color:var(--text-dim);">' + _escHtml(errorMsg) + '</p>';
  } else if (movedCount === 0) {
    title.textContent = "All Clean!";
    title.style.color = "var(--accent)";
    summary.innerHTML = '<p style="color:var(--text-dim);">No duplicates found. Your files are all unique!</p>';
  } else {
    title.textContent = "Done!";
    title.style.color = "var(--accent)";
    summary.innerHTML =
      '<p style="font-size:24px;font-family:monospace;color:var(--accent);margin-bottom:8px;">' +
      movedCount.toLocaleString() + ' duplicates separated</p>' +
      '<p style="color:var(--text-dim);">Duplicates moved to:<br>' +
      '<span style="font-family:monospace;color:var(--text);">' + _escHtml(_autoState.dupesFolder) + '</span></p>' +
      '<p style="color:var(--text-dim);margin-top:12px;">Your originals are untouched. Review the duplicates folder at your leisure.</p>';
  }
}

function _autoOpenDupesFolder() {
  if (_autoState.dupesFolder) {
    api("POST", "/api/browser/open-explorer", { path: _autoState.dupesFolder }).catch(function() {
      toast("Could not open folder", "error");
    });
  }
}

function _autoRescan() {
  // Reset and run again with the same source
  _startAutonomous();
}

// Helper: escape HTML
function _escHtml(str) {
  var div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

// ---- Power Loop (Easy Mode) ----

function _powerLoopBulkMove(reportFile) {
  // Quick bulk-move: load groups, mark all as move, execute
  // Used by Easy mode after scan complete
  startWorkingView("Moving Duplicates", "Moving all found duplicates to Recovery...");

  api("GET", "/api/groups?report=" + encodeURIComponent(reportFile)).then(function(data) {
    var groups = data.groups || [];
    if (groups.length === 0) {
      toast("No groups to move", "warning");
      navigate("dashboard");
      return;
    }

    var settings = state.settings || {};
    var destination = settings.move_destination || "";

    api("POST", "/api/action/move", {
      groups: groups,
      destination: destination,
      report: reportFile
    }).then(function() {
      if (window.pywebview && window.pywebview.api) {
        window._onActionProgress = function(d) {
          if (d.status === "complete") {
            window._onActionProgress = null;
            var moved = (d.result && d.result.moved) || 0;
            // Show result and offer rescan
            showDialog(
              "Duplicates Moved",
              moved.toLocaleString() + " files moved to Recovery. Scan again to find more?",
              function() { navigate("scan-config"); },
              "Rescan",
              "btn-primary"
            );
          }
        };
        window.pywebview.api.subscribe_action_progress();
      }
    }).catch(function(err) {
      toast("Move failed: " + (err.message || "Unknown error"), "error");
      navigate("dashboard");
    });
  }).catch(function(err) {
    toast("Could not load groups: " + (err.message || "Unknown error"), "error");
    navigate("dashboard");
  });
}

// ---- Mode-Aware Scan Complete ----

function addPowerLoopButton(resultFile, containerSelector) {
  // Add "Move All Duplicates" button for Easy mode on scan complete page
  var mode = getCurrentMode();
  if (mode !== "easy") return;

  var container = document.querySelector(containerSelector);
  if (!container) return;

  var btn = document.createElement("button");
  btn.className = "btn btn-warning";
  btn.textContent = "Move All Duplicates";
  btn.setAttribute("data-tip", "Quickly move all duplicates to Recovery without detailed review");
  btn.onclick = function() { _powerLoopBulkMove(resultFile); };

  var wrapper = document.createElement("div");
  wrapper.style.cssText = "margin-top:16px;text-align:center;";
  wrapper.appendChild(btn);
  container.appendChild(wrapper);
}

// ---- Settings Mode Change Handler ----

function onModeChange(selectEl) {
  var newMode = selectEl.value;
  var hintEl = document.getElementById("setModeHint");
  var hints = {
    easy: "Full hand-holding with step-by-step wizard. All guidance enabled.",
    autonomous: "One-click operation. Auto-finds and separates duplicates into a subfolder.",
    hybrid: "Wizard for setup, dashboard for control. Our recommendation.",
    manual: "Import files, then do everything from the dashboard. Maximum flexibility."
  };
  if (hintEl) hintEl.textContent = hints[newMode] || "";
}

// ---- Mode Selector Bypass ----

var _modeSelectorCallback = null;

function _bypassModeSelector() {
  var overlay = document.getElementById("modeSelectOverlay");
  if (overlay) overlay.style.display = "none";
  // Default to hybrid when bypassing
  if (_modeSelectorCallback) {
    _modeSelectorCallback("hybrid");
    _modeSelectorCallback = null;
  }
}

// ---- Replay Functions (Dashboard + Settings) ----

function replayWelcome() {
  showModeSelector(function(mode) {
    state.settings.workflow_mode = mode;
    api("POST", "/api/settings", state.settings).then(function(saved) {
      state.settings = saved;
      toast("Mode changed to " + mode);
      navigate("dashboard");
    }).catch(function() {
      state.settings.workflow_mode = mode;
      navigate("dashboard");
    });
  });
}

function replayTour() {
  showTour(function() {
    replayWelcome();
  });
}

// ---- Guided Tour ----

var _tourCurrentStep = 0;
var _tourOnComplete = null;

var _tourSteps = [
  {
    title: "Welcome to PixHerder",
    body: "PixHerder finds and cleans up duplicate photos on your computer. " +
          "It keeps your originals safe and never permanently deletes anything." +
          '<div style="margin-top:12px;font-size:12px;color:var(--text-muted);">For the best experience, maximize the PixHerder window.</div>'
  },
  {
    title: "How It Works",
    body: '<div style="display:flex;flex-direction:column;gap:12px;margin:8px 0;">' +
      '<div style="display:flex;align-items:center;gap:12px;">' +
        '<span style="background:var(--accent);color:var(--bg);width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;flex-shrink:0;">1</span>' +
        '<span><strong>Import</strong> your photos into a safe workspace</span>' +
      '</div>' +
      '<div style="display:flex;align-items:center;gap:12px;">' +
        '<span style="background:var(--accent);color:var(--bg);width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;flex-shrink:0;">2</span>' +
        '<span><strong>Scan</strong> for exact and visual duplicates</span>' +
      '</div>' +
      '<div style="display:flex;align-items:center;gap:12px;">' +
        '<span style="background:var(--accent);color:var(--bg);width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;flex-shrink:0;">3</span>' +
        '<span><strong>Review</strong> matches side by side and pick keepers</span>' +
      '</div>' +
      '<div style="display:flex;align-items:center;gap:12px;">' +
        '<span style="background:var(--accent);color:var(--bg);width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;flex-shrink:0;">4</span>' +
        '<span><strong>Clean up</strong> and send your files home</span>' +
      '</div>' +
    '</div>'
  },
  {
    title: "Choose Your Style",
    body: '<div style="margin:8px 0;line-height:1.7;">' +
      '<div style="margin-bottom:8px;"><strong style="color:var(--accent);">Easy</strong> -- Full guided wizard. Best for first-time users.</div>' +
      '<div style="margin-bottom:8px;"><strong style="color:var(--accent);">Autonomous</strong> -- One click. PixHerder does everything automatically.</div>' +
      '<div style="margin-bottom:8px;"><strong style="color:var(--accent);">Hybrid</strong> -- Wizard to start, then take the wheel from the dashboard.</div>' +
      '<div><strong style="color:var(--accent);">Manual</strong> -- Import your files, then do everything yourself. Full control.</div>' +
    '</div>'
  },
  {
    title: "Your Files Are Safe",
    body: "PixHerder never permanently deletes your photos. " +
          "All removals go to the Windows Recycle Bin, so you can always get them back. " +
          "Your original files are never touched until you say so."
  },
  {
    title: "Ready to Go",
    body: "Pick a mode on the next screen to get started. " +
          "You can change your mode anytime in Settings, and replay this tour from the dashboard."
  }
];

function showTour(onComplete) {
  _tourCurrentStep = 0;
  _tourOnComplete = onComplete;
  var overlay = document.getElementById("tourOverlay");
  if (!overlay) {
    if (onComplete) onComplete();
    return;
  }
  overlay.style.display = "flex";
  _tourRender();
}

function _tourRender() {
  var step = _tourSteps[_tourCurrentStep];
  var content = document.getElementById("tourContent");
  var dots = document.getElementById("tourDots");
  var backBtn = document.getElementById("tourBackBtn");
  var nextBtn = document.getElementById("tourNextBtn");

  // Content
  content.innerHTML =
    '<h2 style="margin-bottom:12px;">' + step.title + '</h2>' +
    '<div style="color:var(--text-dim);font-size:14px;line-height:1.6;">' + step.body + '</div>';

  // Dots
  var dotsHtml = "";
  for (var i = 0; i < _tourSteps.length; i++) {
    var active = i === _tourCurrentStep;
    dotsHtml += '<span class="tour-dot' + (active ? " active" : "") + '"></span> ';
  }
  dots.innerHTML = dotsHtml;

  // Back button
  backBtn.style.visibility = _tourCurrentStep === 0 ? "hidden" : "visible";

  // Next button
  if (_tourCurrentStep === _tourSteps.length - 1) {
    nextBtn.textContent = "Choose Your Mode";
  } else {
    nextBtn.textContent = "Next";
  }
}

function _tourNext() {
  if (_tourCurrentStep < _tourSteps.length - 1) {
    _tourCurrentStep++;
    _tourRender();
  } else {
    _tourClose();
  }
}

function _tourBack() {
  if (_tourCurrentStep > 0) {
    _tourCurrentStep--;
    _tourRender();
  }
}

function _tourSkip() {
  _tourClose();
}

function _tourClose() {
  var overlay = document.getElementById("tourOverlay");
  if (overlay) overlay.style.display = "none";
  if (_tourOnComplete) {
    var cb = _tourOnComplete;
    _tourOnComplete = null;
    cb();
  }
}
