/* ==================================================================
   DASHBOARD
   ================================================================== */
var _dashFolderPaths = { staging: "", dupes: "", keepers: "" };

var _dashContinueTarget = "finish"; // default
var _dashHintTarget = null;
var _sessionScanCompleted = false; // set true when a scan completes in this session

// ---- Flow Guidance ----

function _dashUpdateFlowGuide(hasStaging, hasDupes, hasKeepers, hasScans) {
  var guide = document.getElementById("dashFlowGuide");
  if (!guide) return;

  // Check if hints are enabled in settings
  var hintsEnabled = !state.settings || state.settings.show_hints !== false;

  // Determine step states
  var hasFiles = hasStaging || hasDupes || hasKeepers;
  if (!hasFiles || !hintsEnabled) {
    guide.style.display = "none";
    return;
  }
  guide.style.display = "block";

  var steps = [
    { num: 1, label: "Import", state: "locked" }, // locked when files exist (can't import more)
    { num: 2, label: "Scan", state: hasScans ? "completed" : (hasStaging ? "current" : "pending") },
    { num: 3, label: "Review", state: hasDupes ? (hasScans ? "current" : "completed") : "pending" },
    { num: 4, label: "Finish", state: (!hasStaging && !hasDupes && hasKeepers) ? "current" : "pending" }
  ];

  // If has dupes and scans, review is current
  if (hasDupes && hasScans) {
    steps[2].state = "current";
    steps[1].state = "completed";
  }
  // If no staging but has dupes, finish might be next
  if (!hasStaging && hasDupes) {
    steps[3].state = "current";
    steps[2].state = "completed";
  }

  // Build stepper HTML
  var stepper = document.getElementById("dashStepper");
  var html = "";
  for (var i = 0; i < steps.length; i++) {
    var s = steps[i];
    var numContent = (s.state === "completed" || s.state === "locked") ? "&#10003;" : s.num;
    html += '<div class="flow-step ' + s.state + '" onclick="_dashStepClick(' + s.num + ')">';
    html += '<span class="step-num">' + numContent + '</span>';
    html += '<span class="step-label">' + s.label + '</span>';
    html += '</div>';
    if (i < steps.length - 1) {
      var connState = (steps[i].state === "completed") ? "completed" : "";
      html += '<div class="flow-connector ' + connState + '"></div>';
    }
  }
  stepper.innerHTML = html;

  // Build hint
  var hintText = document.getElementById("dashHintText");
  var hintBtn = document.getElementById("dashHintAction");

  hintBtn.style.display = "none";

  if (hasStaging && !hasScans) {
    hintText.textContent = "Ready to scan. Use the scan buttons below to find duplicates in your files.";
  } else if (hasScans && hasDupes) {
    hintText.textContent = "Duplicates found. Review them to decide what to keep.";
  } else if (hasStaging && !hasDupes && hasScans) {
    hintText.textContent = "Scan complete. Try a different threshold, or send files home if you're satisfied.";
  } else if (!hasStaging && hasDupes) {
    hintText.textContent = "Review your removed duplicates, or send your files home to finish.";
  } else if (!hasStaging && !hasDupes && hasKeepers) {
    hintText.textContent = "Your files are ready. Send them home to finish up.";
  } else {
    hintText.textContent = "Use the scan buttons below, or access wizard steps for more options.";
  }
}

function _dashHintClick() {
  if (_dashHintTarget) _dashHintTarget();
}

function _dashStepClick(step) {
  // Skip to Step 2 when files already exist in the system
  if (step === 1 && _dashFolderPaths.staging) {
    _navToWizardStep(2);
    return;
  }
  if (step === 1) _navToWizardStep(1);
  else if (step === 2) _rescanFolder("staging");
  else if (step === 3) _navToReview();
  else if (step === 4) navigate("finish");
}

function _dashStartWizard() {
  // Check folder state fresh to decide whether to skip Step 1
  api("GET", "/api/folders/status").then(function(data) {
    if (data.staging && data.staging.exists && data.staging.file_count > 0) {
      // Files exist — go straight to scan config instead of wizard Step 1
      _scanContext = "staging";
      document.getElementById("scanDir").value = data.staging.path;
      navigate("scan-config");
    } else {
      navigate("wizard");
    }
  }).catch(function() {
    navigate("wizard");
  });
}

function _dashUpdateContinueButton(hasStaging, hasDupes, hasKeepers) {
  var hint = document.getElementById("dashContinueHint");
  if (!hint) return;

  // Update hint text based on state
  if (hasStaging && hasDupes) {
    hint.textContent = "Use the scan buttons above, or access wizard steps for more options.";
  } else if (hasStaging && !hasDupes) {
    hint.textContent = "Scan My Files to find duplicates.";
  } else if (hasDupes && !hasStaging) {
    hint.textContent = "Removed Duplicates has files. Use Rescue & Review or finish up from wizard steps.";
  } else if (hasKeepers) {
    hint.textContent = "Verified Keepers are ready to go home. Access wizard steps to finish up.";
  } else {
    hint.textContent = "";
  }

  // Nav states updated by _dashUpdateFolders
}

function _dashContinue() {
  if (_dashContinueTarget === "wizard-step2") {
    wizardState.completedSteps = { 1: true };
    wizardState.currentStep = 2;
    navigate("wizard");
  } else if (_dashContinueTarget === "wizard-step4") {
    wizardState.completedSteps = { 1: true, 2: true, 3: true };
    wizardState.currentStep = 4;
    navigate("wizard");
  } else {
    navigate("finish");
  }
}

function _dashStagePicker() {
  document.getElementById("dialogTitle").textContent = "Choose a Step";
  document.getElementById("dialogMessage").innerHTML =
    '<div style="display:flex;flex-direction:column;gap:10px;">' +
    '<button class="btn btn-secondary btn-fixed" onclick="closeDialog(); wizardState.completedSteps={}; wizardState.currentStep=1; navigate(\'wizard\');">Step 1: Import Files</button>' +
    '<button class="btn btn-secondary btn-fixed" onclick="closeDialog(); wizardState.completedSteps={1:true}; wizardState.currentStep=2; navigate(\'wizard\');">Step 2: Scan for Duplicates</button>' +
    '<button class="btn btn-secondary btn-fixed" id="stagePickReview" onclick="closeDialog(); _stagePickReview();">Step 3: Review Duplicates</button>' +
    '<button class="btn btn-secondary btn-fixed" onclick="closeDialog(); wizardState.completedSteps={1:true,2:true,3:true}; wizardState.currentStep=4; navigate(\'wizard\');">Step 4: Finalize</button>' +
    '<button class="btn btn-primary btn-fixed" onclick="closeDialog(); navigate(\'finish\');">Finish Up</button>' +
    '</div>' +
    '<div style="margin-top:12px;"><button class="btn btn-ghost" onclick="closeDialog()">Cancel</button></div>';
  document.getElementById("dialogConfirmBtn").style.display = "none";
  document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-secondary").style.display = "none";
  document.getElementById("dialogOverlay").classList.add("active");
}

function _stagePickReview() {
  // Find the most recent scan with groups to review
  api("GET", "/api/scans").then(function(scans) {
    for (var i = 0; i < scans.length; i++) {
      if (scans[i].total_groups > 0) {
        navigate("review", { report: scans[i].filename });
        return;
      }
    }
    toast("No scan results with duplicates to review");
  });
}

function _dashUpdateFolders() {
  api("GET", "/api/folders/status").then(function(data) {
    var box = document.getElementById("dashFolders");
    var stagingBtn = document.getElementById("dashStagingBtn");
    var dupesBtn = document.getElementById("dashDupesBtn");
    var stagingHint = document.getElementById("dashStagingHint");
    var dupesHint = document.getElementById("dashDupesHint");

    var hasAny = false;

    if (data.staging && data.staging.exists && data.staging.file_count > 0) {
      stagingBtn.disabled = false;
      stagingBtn.textContent = "My Files (" + data.staging.file_count.toLocaleString() + ")";
      stagingHint.textContent = "";
      _dashFolderPaths.staging = data.staging.path;
      hasAny = true;
    } else {
      stagingBtn.disabled = true;
      stagingBtn.textContent = "My Files";
      stagingHint.textContent = "No staged files";
      _dashFolderPaths.staging = "";
    }

    if (data.dupes && data.dupes.exists && data.dupes.file_count > 0) {
      dupesBtn.disabled = false;
      dupesBtn.textContent = "Removed Duplicates (" + data.dupes.file_count.toLocaleString() + ")";
      dupesHint.textContent = "";
      _dashFolderPaths.dupes = data.dupes.path;
      hasAny = true;
    } else {
      dupesBtn.disabled = true;
      dupesBtn.textContent = "Removed Duplicates";
      dupesHint.textContent = "No files yet";
      _dashFolderPaths.dupes = "";
    }

    // Keepers folder
    var keepersBtn = document.getElementById("dashKeepersBtn");
    var keepersHint = document.getElementById("dashKeepersHint");
    if (data.keepers && data.keepers.exists && data.keepers.file_count > 0) {
      keepersBtn.disabled = false;
      keepersBtn.textContent = "Verified Keepers (" + data.keepers.file_count.toLocaleString() + ")";
      keepersHint.textContent = "";
      _dashFolderPaths.keepers = data.keepers.path;
      hasAny = true;
    } else {
      keepersBtn.disabled = true;
      keepersBtn.textContent = "Verified Keepers";
      keepersHint.textContent = "No files yet";
      _dashFolderPaths.keepers = "";
    }

    box.style.display = hasAny ? "block" : "none";

    var hasStaging = data.staging && data.staging.exists && data.staging.file_count > 0;
    var hasDupes = data.dupes && data.dupes.exists && data.dupes.file_count > 0;
    var hasKeepers = data.keepers && data.keepers.exists && data.keepers.file_count > 0;

    // Update total files stat card
    var totalFiles = (data.staging ? data.staging.file_count || 0 : 0)
                   + (data.dupes ? data.dupes.file_count || 0 : 0)
                   + (data.keepers ? data.keepers.file_count || 0 : 0);
    var totalEl = document.getElementById("dStatTotal");
    if (totalEl) totalEl.textContent = totalFiles.toLocaleString();

    // Dynamic continue button
    var hasAnySystemFiles = hasStaging || hasDupes || hasKeepers;
    document.getElementById("dashContinueAction").style.display = hasAnySystemFiles ? "block" : "none";
    if (hasAnySystemFiles) {
      _dashUpdateContinueButton(hasStaging, hasDupes, hasKeepers);
    }

    // Flow guidance — use session flag to determine if a scan was done this session
    // hasDupes also implies a scan was done (files moved to dupes folder)
    var hasScans = _sessionScanCompleted || hasDupes;
    _dashUpdateFlowGuide(hasStaging, hasDupes, hasKeepers, hasScans);

    // Scan buttons (positioned under their respective browse buttons)
    var rescanStagingBox = document.getElementById("dashRescanStagingBox");
    var rescanDupesBox = document.getElementById("dashRescanBoxes");
    var rescanKeepersBox = document.getElementById("dashRescanKeepersBox");
    var rescanDupesBtn = document.getElementById("dashRescanDupesBtn");
    var rescanKeepersBtn = document.getElementById("dashRescanKeepersBtn");
    if (rescanStagingBox) rescanStagingBox.style.display = hasStaging ? "block" : "none";
    if (rescanDupesBox) rescanDupesBox.style.display = (hasStaging || hasDupes || hasKeepers) ? "block" : "none";
    if (rescanDupesBtn) rescanDupesBtn.disabled = !hasDupes;
    if (rescanKeepersBox) rescanKeepersBox.style.display = (hasStaging || hasDupes || hasKeepers) ? "block" : "none";
    if (rescanKeepersBtn) rescanKeepersBtn.disabled = !hasKeepers;

    // Update wizard button label based on state
    var wizBtn = document.getElementById("dashWizardBtn");
    if (wizBtn) {
      wizBtn.textContent = hasStaging ? "Continue Guided Cleanup" : "Start Guided Cleanup";
    }

    // Update nav states
    _updateNavStates();

    // Show advanced options section when any folder has files
    document.getElementById("dashAdvancedOptions").style.display = (hasStaging || hasDupes || hasKeepers) ? "block" : "none";

    // Show send-home/cleanup actions when staging folder has files
    document.getElementById("dashStagingActions").style.display = hasStaging ? "block" : "none";

    // Show rescue/purge actions when dupes folder has files
    document.getElementById("dashDupeActions").style.display = hasDupes ? "block" : "none";
  }).catch(function() {});
}

function rescueAndReview() {
  // Check folder status first to give actionable guidance
  api("GET", "/api/folders/status").then(function(data) {
    var stagingHasFiles = data.staging && data.staging.exists && data.staging.file_count > 0;
    var dupesHasFiles = data.dupes && data.dupes.exists && data.dupes.file_count > 0;

    if (!dupesHasFiles) {
      toast("No files in the Removed Duplicates folder to review", "warning");
      return;
    }

    if (stagingHasFiles) {
      document.getElementById("dialogTitle").textContent = "My Files Has Files";
      document.getElementById("dialogMessage").innerHTML =
        '<div style="margin-bottom:16px;">My Files still has <strong>' +
        data.staging.file_count.toLocaleString() + '</strong> files. How would you like to proceed?</div>' +
        '<div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;">' +
        '<button class="btn btn-primary" onclick="_rnrMerge()">Merge Dupes</button>' +
        '<button class="btn btn-secondary" onclick="_rnrSyncAndRecycle()">Return / Reload</button>' +
        '</div>' +
        '<div style="border-top:1px solid var(--border);margin-top:14px;padding-top:12px;font-size:13px;color:var(--text-dim);">' +
        '<span style="color:#fff;font-weight:600;">Merge Dupes</span> files from Removed Duplicates will be merged with the files in My Files. You\'ll find all the files in the My Files folder again.<br><br>' +
        '<span style="color:#fff;font-weight:600;">Return / Reload</span> sends your My Files home first, then brings the Removed Duplicates back for another review.' +
        '</div>' +
        '<div style="margin-top:12px;"><button class="btn btn-ghost" onclick="closeDialog()">Cancel</button></div>';
      document.getElementById("dialogConfirmBtn").style.display = "none";
      document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-secondary").style.display = "none";
      document.getElementById("dialogOverlay").classList.add("active");
      return;
    }

    showDialog(
      "Rescue & Review",
      "This will move " + data.dupes.file_count.toLocaleString() + " files from Removed Duplicates " +
      "into My Files for scanning and review.\n\nContinue?",
      "Start",
      "btn-primary",
      function() {
        startWorkingView(
          "Loading Files for Review",
          "Moving files from Removed Duplicates to My Files.",
          function(done) {
            api("POST", "/api/staging/recycle").then(function(r) {
              if (r.success) {
                wizardState.stagingDir = r.staging_path;
                wizardState.completedSteps = { 1: true };
                wizardState.currentStep = 2;
                done("Files Loaded", r.files_moved.toLocaleString() + " files ready for scanning in My Files.");
                _workingConfig.destination = "wizard";
              } else {
                done("Failed", r.error || "Unknown error");
              }
            }).catch(function(err) {
              done("Failed", err.message || "Failed to load files");
            });
          },
          "wizard"
        );
      }
    );
  });
}

function _rnrMerge() {
  closeDialog();
  startWorkingView(
    "Merging Files",
    "Moving files from Removed Duplicates to My Files.",
    function(done) {
      api("POST", "/api/staging/recycle", { force: true }).then(function(r) {
        if (r.success) {
          wizardState.stagingDir = r.staging_path;
          wizardState.completedSteps = { 1: true };
          api("GET", "/api/folders/status").then(function(fs) {
            var cleanedCount = (fs.staging && fs.staging.file_count) || 0;
            var dupesCount = (fs.dupes && fs.dupes.file_count) || 0;
            var msg = r.files_moved.toLocaleString() + " files moved to My Files.\n" +
              "My Files now has " + cleanedCount.toLocaleString() + " files.";
            if (dupesCount > 0) msg += " Removed Duplicates has " + dupesCount.toLocaleString() + " remaining.";
            done("Merge Complete", msg);
          });
        } else {
          done("Merge Failed", r.error || "Unknown error");
        }
      }).catch(function(err) {
        done("Merge Failed", err.message);
      });
    },
    "dashboard"
  );
}

function _rnrSyncAndRecycle() {
  closeDialog();
  startWorkingView(
    "Return / Reload",
    "Sending My Files home, then loading Removed Duplicates for review.",
    function(done) {
      api("GET", "/api/staging/status").then(function(status) {
        var stagingDir = status.staging_dir || _dashFolderPaths.staging || "";
        var sourceDir = status.source_dir || (state.settings && state.settings.default_pictures_path) || "";
        if (!stagingDir || !sourceDir) {
          done("Failed", "Could not determine file locations.");
          return;
        }
        document.getElementById("workingStatus").textContent = "Sending My Files home...";
        api("POST", "/api/staging/restore", { staging_dir: stagingDir, source_dir: sourceDir }).then(function(r) {
          if (!r.success) { done("Failed", r.error || "Restore failed"); return; }
          document.getElementById("workingStatus").textContent = "Cleaning up workspace...";
          api("POST", "/api/staging/cleanup", { staging_dir: stagingDir }).then(function() {
            document.getElementById("workingStatus").textContent = "Loading Removed Duplicates...";
            api("POST", "/api/staging/recycle").then(function(r2) {
              if (r2.success) {
                wizardState.stagingDir = r2.staging_path;
                wizardState.completedSteps = { 1: true };
                wizardState.currentStep = 2;
                done("Ready for Review", r2.files_moved.toLocaleString() + " files loaded into My Files.");
                _workingConfig.destination = "wizard";
              } else {
                done("Failed", r2.error || "Unknown error");
              }
            }).catch(function(err) { done("Failed", err.message); });
          }).catch(function(err) { done("Failed", err.message); });
        }).catch(function(err) { done("Failed", err.message); });
      });
    },
    "wizard"
  );
}

function sendFilesHome() {
  // Ensure staging session is loaded
  var p = _stagingSession
    ? Promise.resolve()
    : api("GET", "/api/staging/status").then(function(d) {
        if (d.staging_dir && d.source_dir) {
          _stagingSession = { source_dir: d.source_dir, staging_dir: d.staging_dir };
        }
      });
  p.then(function() {
    if (!_stagingSession) {
      toast("No staging session found. Files may have been staged outside the wizard.", "error");
      return;
    }
    return api("GET", "/api/folders/status").then(function(data) {
      var stagingCount = (data.staging && data.staging.file_count) || 0;
      var dupesCount = (data.dupes && data.dupes.file_count) || 0;
      var totalCount = stagingCount + dupesCount;
      if (totalCount === 0) {
        toast("No files to send home");
        return;
      }
      showDialog(
        "Send Files Home",
        "Send " + totalCount.toLocaleString() + " files back to their original folder?",
        "Continue", "btn-primary",
        function() {
          showDialog(
            "Confirm",
            "All files will be returned and My Files will be cleaned up. Continue?",
            "Send Home", "btn-primary",
            function() { _confirmSendHome(); }
          );
        }
      );
    });
  });
}

function _confirmSendHome() {
  if (!_stagingSession) {
    toast("No staging session found", "error");
    return;
  }
  closeDialog();
  startWorkingView(
    "Sending Files Home",
    "Returning your files to their original folder.",
    function(done) {
      api("POST", "/api/staging/restore", {
        staging_dir: _stagingSession.staging_dir,
        source_dir: _stagingSession.source_dir,
        full_restore: true
      }).then(function(r) {
        if (r.success) {
          _stagingSession = null;
          done("All Files Sent Home", r.copied.toLocaleString() + " files returned to their original folder.");
        } else {
          done("Restore Failed", r.error || "Unknown error");
        }
      }).catch(function(err) {
        done("Restore Failed", err.message);
      });
    },
    "dashboard"
  );
}

function _restartAllFiles() {
  api("GET", "/api/folders/status").then(function(data) {
    var dupesCount = (data.dupes && data.dupes.file_count) || 0;
    var keepersCount = (data.keepers && data.keepers.file_count) || 0;
    var total = dupesCount + keepersCount;
    if (total === 0) {
      toast("No files to move back");
      return;
    }
    showDialog(
      "Start Over",
      "Put all " + total.toLocaleString() + " files from Removed Duplicates" +
      (keepersCount > 0 ? " and Verified Keepers" : "") +
      " back into My Files so you can rescan everything?",
      "Start Over", "btn-warning",
      function() {
        startWorkingView(
          "Starting Over",
          "Moving all files back to My Files.",
          function(done) {
            api("POST", "/api/consolidate").then(function(r) {
              if (r.success) {
                done("Ready to Rescan", r.moved.toLocaleString() + " files moved back to My Files.");
              } else {
                done("Failed", r.error || "Unknown error");
              }
            }).catch(function(err) {
              done("Failed", err.message);
            });
          },
          "dashboard"
        );
      }
    );
  });
}

function promoteToKeepers() {
  api("GET", "/api/folders/status").then(function(data) {
    var count = (data.dupes && data.dupes.file_count) || 0;
    if (count === 0) {
      toast("No files in Removed Duplicates to promote");
      return;
    }
    showDialog(
      "Move to Keepers",
      "Move " + count.toLocaleString() + " files from Removed Duplicates to Verified Keepers?",
      "Move", "btn-primary",
      function() {
        startWorkingView(
          "Moving to Keepers",
          "Saving files from Removed Duplicates as Verified Keepers.",
          function(done) {
            api("POST", "/api/dupes/promote").then(function(r) {
              if (r.success) {
                done("Moved to Keepers", r.moved.toLocaleString() + " files saved as Verified Keepers.");
              } else {
                done("Failed", r.error || "Unknown error");
              }
            }).catch(function(err) {
              done("Failed", err.message);
            });
          },
          "dashboard"
        );
      }
    );
  });
}

function purgeAllDupes() {
  // First get the count for the confirmation
  api("GET", "/api/folders/status").then(function(data) {
    var count = (data.dupes && data.dupes.file_count) || 0;
    if (count === 0) {
      toast("No files to delete");
      return;
    }
    showDialog(
      "Delete All Duplicates",
      "This will send " + count.toLocaleString() + " files from Removed Duplicates to the Recycle Bin. " +
      "You can recover them from there if needed.",
      "Send to Recycle Bin",
      "btn-danger",
      function() {
        startWorkingView(
          "Recycling Files",
          "Sending files from Removed Duplicates to the Recycle Bin.",
          function(done) {
            api("POST", "/api/dupes/purge").then(function(r) {
              if (r.success) {
                var msg = r.deleted.toLocaleString() + " files sent to the Recycle Bin.";
                if (r.errors) msg += " " + r.errors + " files could not be removed.";
                done("Files Recycled", msg);
              } else {
                done("Failed", r.error || "Unknown error");
              }
            }).catch(function(err) {
              done("Failed", err.message || "Purge failed");
            });
          },
          "dashboard"
        );
      }
    );
  });
}

function openBrowserFromDashboard(type) {
  if (type === "staging" && _dashFolderPaths.staging) {
    browserState.rootPath = _dashFolderPaths.staging;
    browserState.type = "staging";
  } else if (type === "dupes" && _dashFolderPaths.dupes) {
    browserState.rootPath = _dashFolderPaths.dupes;
    browserState.type = "dupes";
  } else if (type === "keepers" && _dashFolderPaths.keepers) {
    browserState.rootPath = _dashFolderPaths.keepers;
    browserState.type = "keepers";
  } else {
    return;
  }
  browserState.currentPath = browserState.rootPath;
  browserState.currentPage = 1;
  browserState.returnTo = "dashboard";
  navigate("browser");
}

function initDashboard() {
  // Load settings for later use
  api("GET", "/api/settings").then(function(s) {
    state.settings = s;
  }).catch(function() {});

  // Fetch folder status for browse buttons
  _dashUpdateFolders();

  // Check recovery archive
  _dashUpdateRecovery();

  api("GET", "/api/scans").then(function(scans) {
    var list = document.getElementById("scanList");
    var statsBox = document.getElementById("dashboardStats");

    if (!scans || scans.length === 0) {
      list.innerHTML = '<div class="empty-state"><h3>No scans yet</h3><p>Click "Start New Scan" to find duplicates.</p></div>';
      // Still show stats box if we have files (total count comes from folder status)
      var totalEl = document.getElementById("dStatTotal");
      if (totalEl && totalEl.textContent !== "0") {
        statsBox.style.display = "grid";
      } else {
        statsBox.style.display = "none";
      }
      return;
    }

    // Stats from most recent scan
    var latest = scans[0];
    var totalGroups = latest.total_groups || 0;
    var totalDupes = latest.total_dupes || 0;
    var totalSpace = latest.reclaimable_bytes || 0;
    document.getElementById("dStatGroups").textContent = totalGroups.toLocaleString();
    document.getElementById("dStatDupes").textContent = totalDupes.toLocaleString();
    document.getElementById("dStatSpace").textContent = formatBytes(totalSpace);
    statsBox.style.display = "grid";

    // Scan list
    var html = "";
    for (var i = 0; i < scans.length; i++) {
      var s = scans[i];
      var badge = s.source === "legacy"
        ? '<span class="scan-badge scan-badge-legacy">legacy</span>'
        : '<span class="scan-badge scan-badge-scan">scan</span>';
      var meta = s.total_groups + " groups";
      if (s.reclaimable_bytes) meta += " | " + formatBytes(s.reclaimable_bytes) + " reclaimable";
      if (s.directory) meta += " | " + s.directory;
      if (s.timestamp) meta += " | " + s.timestamp.substring(0, 19);

      html += '<div class="scan-item">';
      html += '<div class="scan-item-info">';
      html += '<div class="scan-item-name">' + badge + " " + escHtml(s.filename) + '</div>';
      html += '<div class="scan-item-meta">' + escHtml(meta) + '</div>';
      html += '</div>';
      html += '<div class="scan-item-actions">';
      html += '<button class="btn btn-primary btn-sm" onclick="navigate(\'review\',{report:\'' + escAttr(s.filename) + '\'})">Review</button>';
      if (s.source === "scan") {
        html += '<button class="btn btn-secondary btn-sm" onclick="deleteScan(\'' + escAttr(s.filename) + '\')">Delete</button>';
      }
      html += '</div></div>';
    }
    list.innerHTML = html;
  }).catch(function(err) {
    document.getElementById("scanList").innerHTML =
      '<div class="empty-state" style="color:var(--danger);">Error loading scans: ' + escHtml(String(err)) + '</div>';
  });
}

function deleteScan(filename) {
  showDialog("Delete Scan", "Remove scan result " + filename + " from the list?", "Remove", "btn-danger", function() {
    api("POST", "/api/scans/delete", { filename: filename }).then(function() {
      toast("Scan deleted");
      initDashboard();
    }).catch(function(err) { toast("Error: " + err.message, "error"); });
  });
}

// ---- Recovery Archive ----

function _dashUpdateRecovery() {
  api("GET", "/api/recovery/status").then(function(data) {
    var box = document.getElementById("dashRecovery");
    if (!data.exists || data.total_files === 0) {
      box.style.display = "none";
      return;
    }
    box.style.display = "block";
    var mb = Math.round(data.total_bytes / (1024 * 1024));
    var info = data.total_files + " files (" + mb + " MB) in "
             + data.slots.length + " recovery slot"
             + (data.slots.length > 1 ? "s" : "");
    document.getElementById("dashRecoveryInfo").textContent = info;
  }).catch(function() {
    document.getElementById("dashRecovery").style.display = "none";
  });
}

function _showRecoveryFiles() {
  api("GET", "/api/recovery/list").then(function(data) {
    if (!data.files || data.files.length === 0) {
      toast("Recovery archive is empty");
      return;
    }
    var html = '<div style="max-height:400px;overflow-y:auto;">';
    for (var i = 0; i < data.files.length; i++) {
      var f = data.files[i];
      var name = f.archived_name || "Unknown";
      var origPath = f.original_path || "";
      var shortPath = origPath.length > 60 ? "..." + origPath.substring(origPath.length - 57) : origPath;
      html += '<div style="display:flex;align-items:center;justify-content:space-between;'
        + 'padding:8px 0;border-bottom:1px solid var(--border);">'
        + '<div><div style="font-weight:500;">' + escHtml(name) + '</div>'
        + '<div style="font-size:11px;color:var(--text-dim);">' + escHtml(shortPath) + '</div></div>'
        + '<button class="btn btn-primary btn-sm" onclick="_restoreRecoveryFile(\''
        + escAttr(f.archived_path) + '\')">Restore</button></div>';
    }
    html += '</div>';

    document.getElementById("dialogTitle").textContent = "Recovery Archive";
    document.getElementById("dialogMessage").innerHTML = html;
    document.getElementById("dialogConfirmBtn").style.display = "none";
    document.getElementById("dialog").classList.add("active");
    document.getElementById("dialogOverlay").classList.add("active");
  }).catch(function() {
    toast("Could not load recovery archive", "error");
  });
}

function _restoreRecoveryFile(archivedPath) {
  api("POST", "/api/recovery/restore", { archived_path: archivedPath }).then(function(r) {
    if (r.success) {
      toast("File restored to My Files");
      closeDialog();
      _dashUpdateRecovery();
      _refreshFolderPaths();
    } else {
      toast("Restore failed: " + (r.error || "Unknown error"), "error");
    }
  }).catch(function(err) {
    toast("Restore failed: " + err.message, "error");
  });
}

function _clearRecoveryArchive() {
  showDialog(
    "Clear Recovery Archive",
    "This will permanently remove all files in the recovery archive. Files already in the Recycle Bin are not affected.",
    "Clear Archive", "btn-danger",
    function() {
      api("POST", "/api/recovery/clear").then(function() {
        toast("Recovery archive cleared");
        _dashUpdateRecovery();
      }).catch(function(err) {
        toast("Error: " + err.message, "error");
      });
    }
  );
}

