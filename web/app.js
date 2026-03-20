// Browser compatibility check
(function() {
  var isOK = window.fetch && window.CSS && CSS.supports && CSS.supports("gap", "1px");
  if (!isOK) {
    var w = document.createElement("div");
    w.style.cssText = "background:#b33;color:#fff;padding:12px 20px;text-align:center;font-family:sans-serif;font-size:14px;";
    w.innerHTML = "Your browser may not fully support DupeFinder. For the best experience, please use a recent version of Chrome, Firefox, Edge, or Safari.";
    document.body.insertBefore(w, document.body.firstChild);
  }
})();

/* ==================================================================
   DupeFinder SPA - State, Router, API, Views
   ================================================================== */

// ---- Global State ----
var state = {
  groups: [],
  filteredIndices: [],
  currentGroupIndex: 0,
  decisions: {},
  currentReport: null,
  settings: {}
};

// ---- Utilities ----
function formatBytes(bytes) {
  if (!bytes || bytes < 0) return "0 B";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

function formatTime(seconds) {
  if (!seconds || seconds < 0) return "0:00";
  var m = Math.floor(seconds / 60);
  var s = Math.floor(seconds % 60);
  return m + ":" + (s < 10 ? "0" : "") + s;
}

function getFilename(fp) {
  if (!fp) return "";
  var sep = fp.indexOf("\\") >= 0 ? "\\" : "/";
  var parts = fp.split(sep);
  return parts[parts.length - 1];
}

function getFolder(fp) {
  if (!fp) return "";
  var sep = fp.indexOf("\\") >= 0 ? "\\" : "/";
  var parts = fp.split(sep);
  parts.pop();
  return parts.slice(-2).join(sep);
}

// ---- Toast ----
function toast(message, type) {
  type = type || "success";
  var container = document.getElementById("toastContainer");
  var el = document.createElement("div");
  el.className = "toast toast-" + type;
  el.textContent = message;
  container.appendChild(el);
  // Warning/error toasts blink and stay longer
  var duration = (type === "warning" || type === "error") ? 6000 : 4000;
  if (type === "warning" || type === "error") {
    el.style.animation = "toast-blink 0.5s ease-in-out 3";
  }
  setTimeout(function() { el.remove(); }, duration);
}

// ---- Confirm Dialog ----
var _dialogCallback = null;
function showDialog(title, message, confirmText, confirmClass, onConfirm) {
  document.getElementById("dialogTitle").textContent = title;
  document.getElementById("dialogMessage").textContent = message;
  var btn = document.getElementById("dialogConfirmBtn");
  btn.textContent = confirmText || "Confirm";
  btn.className = "btn " + (confirmClass || "btn-danger");
  btn.style.display = "";
  document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-secondary").style.display = "";
  _dialogCallback = onConfirm;
  document.getElementById("dialogOverlay").classList.add("active");
}
function closeDialog() {
  document.getElementById("dialogOverlay").classList.remove("active");
  _dialogCallback = null;
}
function dialogConfirmAction() {
  var cb = _dialogCallback;
  closeDialog();
  if (cb) cb();
}

// ---- Lightbox ----
var _lightboxFilePath = "";
function openLightbox(encodedPath) {
  _lightboxFilePath = decodeURIComponent(encodedPath);
  document.getElementById("lightboxImg").src = "/api/image?path=" + encodedPath;
  document.getElementById("lightbox").classList.add("active");
  // Show controls in browser and review views
  var view = parseHash().view;
  var showControls = (view === "browser" || view === "review");
  document.getElementById("lightboxControls").style.display = showControls ? "flex" : "none";
}
function closeLightbox() {
  document.getElementById("lightbox").classList.remove("active");
  document.getElementById("lightboxImg").src = "";
  _lightboxFilePath = "";
}
function deleteLightboxFile() {
  if (!_lightboxFilePath) return;
  var filename = _lightboxFilePath.split("\\").pop();
  showDialog(
    "Delete File",
    "Send " + filename + " to the Recycle Bin?",
    "Delete",
    "btn-danger",
    function() {
      var deletedPath = _lightboxFilePath;
      api("POST", "/api/browser/delete", { path: deletedPath }).then(function(r) {
        if (r.success) {
          closeLightbox();
          var view = parseHash().view;
          if (view === "browser") {
            // Remove the item from the browser grid
            var items = document.querySelectorAll(".browser-item");
            for (var i = 0; i < items.length; i++) {
              var img = items[i].querySelector("img");
              if (img && img.src.indexOf(encodeURIComponent(deletedPath)) !== -1) {
                items[i].remove();
                break;
              }
            }
            var countEl = document.getElementById("browserCount");
            var match = (countEl.textContent || "").match(/(\d+)/);
            if (match) countEl.textContent = (parseInt(match[1]) - 1) + " items";
          } else if (view === "review") {
            // Remove the deleted file from group data and re-render
            var realIdx = state.filteredIndices[state.currentGroupIndex];
            var group = state.groups[realIdx];
            if (group) {
              if (group.keep === deletedPath) {
                // Deleted the keep file — promote first dupe to keep
                if (group.duplicates && group.duplicates.length > 0) {
                  group.keep = group.duplicates.shift();
                }
              } else if (group.duplicates) {
                group.duplicates = group.duplicates.filter(function(d) { return d !== deletedPath; });
              }
              group.files = 1 + (group.duplicates ? group.duplicates.length : 0);
            }
            renderReviewGroup();
          }
          toast("File deleted");
        } else {
          toast("Delete failed: " + (r.error || "Unknown error"), "error");
        }
      }).catch(function(err) {
        toast("Delete failed: " + err.message, "error");
      });
    }
  );
}

// ---- Bookmark ----
function bookmarkPage() {
  toast("Press Ctrl+D to bookmark this page");
  localStorage.setItem("dupefinder_bookmarked", "1");
  var btn = document.getElementById("bookmarkBtn");
  btn.disabled = true;
  btn.innerHTML = "&#10003; Bookmarked";
}

function dismissBookmarkNotice() {
  localStorage.setItem("dupefinder_bookmarked", "1");
  document.getElementById("bookmarkNotice").style.display = "none";
}

// ---- Shutdown ----
function shutdownServer() {
  showDialog(
    "Shut Down Server",
    "This will stop DupeFinder. You will need to relaunch it from the desktop shortcut.",
    "Shut Down",
    "btn-danger",
    function() {
      fetch("/api/shutdown", { method: "POST" }).catch(function() {});
      document.querySelector(".status-dot").style.background = "var(--danger)";
      document.querySelector(".status-dot").style.animation = "none";
      document.querySelector(".status-bar-left span:first-child").innerHTML =
        '<span class="status-dot" style="background:var(--danger);animation:none"></span>Server stopped';
      document.querySelector(".btn-shutdown").disabled = true;
      document.querySelector(".btn-shutdown").textContent = "Stopped";
    }
  );
}

function restartServer() {
  showDialog(
    "Restart Server",
    "This will restart DupeFinder. The page will reload automatically once the server is back up.",
    "Restart",
    "btn-secondary",
    function() {
      fetch("/api/restart", { method: "POST" }).catch(function() {});
      document.querySelector(".status-dot").style.background = "var(--warning)";
      document.querySelector(".status-dot").style.animation = "none";
      document.querySelector(".status-bar-left span:first-child").innerHTML =
        '<span class="status-dot" style="background:var(--warning);animation:none"></span>Restarting...';
      // Poll until server is back
      var attempts = 0;
      var poll = setInterval(function() {
        attempts++;
        fetch("/api/heartbeat").then(function() {
          clearInterval(poll);
          location.reload();
        }).catch(function() {
          if (attempts > 30) {
            clearInterval(poll);
            document.querySelector(".status-bar-left span:first-child").innerHTML =
              '<span class="status-dot" style="background:var(--danger);animation:none"></span>Restart failed';
          }
        });
      }, 1000);
    }
  );
}

// ---- Resume Dialog ----
function showResumeDialog(title, detail, onResume, onFresh) {
  document.getElementById("dialogTitle").textContent = "Resume Previous Scan?";
  document.getElementById("dialogMessage").innerHTML =
    '<div style="margin-bottom:12px;">' + escHtml(title) + '</div>' +
    '<div style="font-size:12px;color:var(--text-dim);font-family:monospace;margin-bottom:16px;">' +
    escHtml(detail) + '</div>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end;">' +
    '<button class="btn btn-secondary" id="resumeFreshBtn">Start Fresh</button>' +
    '<button class="btn btn-primary" id="resumeResumeBtn">Resume Scan</button>' +
    '</div>' +
    '<div style="border-top:1px solid var(--border);margin-top:14px;padding-top:12px;font-size:13px;color:var(--text-dim);">' +
    '<span style="color:#fff;font-weight:600;">Resume</span> picks up where the last scan left off, saving time.<br><br>' +
    '<span style="color:#fff;font-weight:600;">Start Fresh</span> starts a brand new scan from scratch.' +
    '</div>' +
    '<div style="margin-top:12px;"><button class="btn btn-ghost" onclick="closeDialog()">Cancel</button></div>';
  document.getElementById("dialogConfirmBtn").style.display = "none";
  document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-secondary").style.display = "none";
  document.getElementById("dialogOverlay").classList.add("active");

  document.getElementById("resumeResumeBtn").onclick = function() {
    closeDialog();
    document.getElementById("dialogConfirmBtn").style.display = "";
    document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-secondary").style.display = "";
    onResume();
  };
  document.getElementById("resumeFreshBtn").onclick = function() {
    closeDialog();
    document.getElementById("dialogConfirmBtn").style.display = "";
    document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-secondary").style.display = "";
    onFresh();
  };
}

// ---- Activity Log ----
function loadActivity() {
  fetch("/api/activity?limit=100").then(function(r) { return r.json(); }).then(function(data) {
    var el = document.getElementById("activityList");
    var entries = data.entries || [];
    if (entries.length === 0) {
      el.innerHTML = '<div style="padding:24px;color:var(--text-dim);">No activity recorded yet.</div>';
      return;
    }
    var html = "";
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      var ts = new Date(e.timestamp).toLocaleString();
      var evt = e.event || "";
      var badge = "shutdown";
      if (evt.indexOf("started") >= 0 || evt === "server_started") badge = "started";
      else if (evt.indexOf("completed") >= 0) badge = "completed";
      else if (evt.indexOf("cancelled") >= 0) badge = "cancelled";
      else if (evt.indexOf("error") >= 0) badge = "error";
      else if (evt.indexOf("resumed") >= 0) badge = "resumed";

      var details = "";
      var d = e.details || {};
      if (d.directory) details += d.directory + " ";
      if (d.mode) details += "(" + d.mode + ") ";
      if (d.groups) details += d.groups + " groups ";
      if (d.reclaimable_mb) details += d.reclaimable_mb + " MB ";
      if (d.duration) details += "in " + d.duration + "s ";
      if (d.progress) details += "at " + d.progress + " ";
      if (d.error) details += d.error + " ";
      if (d.reason) details += d.reason + " ";
      if (d.port) details += "port " + d.port + " ";
      if (d.cached_hashes) details += d.cached_hashes + " cached hashes ";
      if (d.source) details += "(" + d.source + ") ";

      html += '<div class="activity-entry">' +
        '<span class="activity-time">' + escHtml(ts) + '</span>' +
        '<span class="activity-badge ' + badge + '">' + escHtml(evt.replace(/_/g, " ")) + '</span>' +
        '<span class="activity-details">' + escHtml(details.trim()) + '</span>' +
        '</div>';
    }
    el.innerHTML = html;
  }).catch(function() {
    document.getElementById("activityList").innerHTML =
      '<div style="padding:24px;color:var(--text-dim);">Failed to load activity log.</div>';
  });
}

function clearActivity() {
  showDialog("Clear Activity Log", "This will remove all activity history.", "Clear", "btn-danger", function() {
    fetch("/api/activity/clear", { method: "POST" }).then(function() {
      loadActivity();
      toast("Activity log cleared");
    });
  });
}

// ---- Folder Picker ----
var _folderPickerTarget = null;
var _folderPickerPath = "";

function _quickFill(which) {
  api("GET", "/api/settings").then(function(s) {
    var home = s.default_pictures_path || "";
    var userProfile = home.replace(/\\OneDrive\\Pictures$/i, "")
                         .replace(/\\Pictures$/i, "");
    var path = "";
    if (which === "onedrive") path = home;
    else if (which === "pictures") path = userProfile + "\\Pictures";
    else if (which === "desktop") path = userProfile + "\\Desktop";
    if (path) document.getElementById("wizSourceDir").value = path;
  });
}

function openFolderPicker(targetInputId) {
  _folderPickerTarget = targetInputId;
  var startPath = document.getElementById(targetInputId).value.trim();
  _loadFolderPicker(startPath || "");
  document.getElementById("folderPickerOverlay").classList.add("active");
}

function closeFolderPicker() {
  document.getElementById("folderPickerOverlay").classList.remove("active");
  _folderPickerTarget = null;
}

function selectFolder() {
  if (_folderPickerTarget && _folderPickerPath) {
    document.getElementById(_folderPickerTarget).value = _folderPickerPath;
  }
  closeFolderPicker();
}

function _loadFolderPicker(path) {
  fetch("/api/browse-folders?path=" + encodeURIComponent(path))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      _folderPickerPath = data.path;

      // Breadcrumb
      document.getElementById("folderPickerBreadcrumb").textContent = data.path;

      // Build folder list
      var html = "";
      if (data.parent) {
        html += '<div style="padding:6px 10px;cursor:pointer;border-radius:4px;" ' +
          'onmouseover="this.style.background=\'var(--surface-2)\'" ' +
          'onmouseout="this.style.background=\'none\'" ' +
          'onclick="_loadFolderPicker(\'' + escAttr(data.parent) + '\')">' +
          '<span style="margin-right:6px;">&#8593;</span> ..</div>';
      }
      for (var i = 0; i < data.folders.length; i++) {
        var name = data.folders[i];
        var full = data.path + "\\" + name;
        html += '<div style="padding:6px 10px;cursor:pointer;border-radius:4px;" ' +
          'onmouseover="this.style.background=\'var(--surface-2)\'" ' +
          'onmouseout="this.style.background=\'none\'" ' +
          'onclick="_loadFolderPicker(\'' + escAttr(full) + '\')">' +
          '<span style="margin-right:6px;">&#128193;</span> ' + name + '</div>';
      }
      if (!data.folders.length && !data.parent) {
        html = '<div style="padding:12px;color:var(--text-dim);">No subfolders found</div>';
      }
      document.getElementById("folderPickerList").innerHTML = html;
    })
    .catch(function() {
      document.getElementById("folderPickerList").innerHTML =
        '<div style="padding:12px;color:var(--danger);">Could not load folder</div>';
    });
}

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
var _wizScanSSE = null;
var _wizStagingSSE = null;

function initWizard() {
  // If RnR already set up the wizard state, jump to the right step immediately
  // before any async fetches (prevents Step 1 flash)
  if (wizardState.completedSteps[1] && wizardState.stagingDir) {
    _wizardDetermineStep();
  }

  // Load settings first — also detect existing staging session
  // so restart/refresh lands on the right step
  fetch("/api/settings").then(function(r) { return r.json(); }).then(function(s) {
    wizardState.dupesDir = s.move_destination || "";
    var defaultSource = s.default_pictures_path || "";
    document.getElementById("wizSourceDir").value = wizardState.sourceDir || defaultSource;

    // Check for existing staging session (in-memory first, then on-disk manifest)
    return fetch("/api/staging/status").then(function(r) { return r.json(); }).then(function(d) {
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
        return fetch("/api/folders/status").then(function(r2) { return r2.json(); }).then(function(fs) {
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
  return fetch("/api/scans").then(function(r) { return r.json(); }).then(function(scans) {
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
    fetch("/api/settings").then(function(r) { return r.json(); }).then(function(s) {
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
    fetch("/api/folders/status").then(function(r) { return r.json(); }).then(function(data) {
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
    // Connect SSE
    if (_wizStagingSSE) _wizStagingSSE.close();
    _wizStagingSSE = new EventSource("/api/staging/progress");
    _wizStagingSSE.onmessage = function(e) {
      var d = JSON.parse(e.data);
      var pct = d.total > 0 ? Math.round((d.current / d.total) * 100) : 0;
      document.getElementById("wizMigFill").style.width = pct + "%";
      document.getElementById("wizMigPct").textContent = pct + "%";
      document.getElementById("wizMigLeft").textContent = d.current + " / " + d.total + " files";
      var mb = d.bytes_copied ? Math.round(d.bytes_copied / (1024*1024)) : 0;
      var mbT = d.bytes_total ? Math.round(d.bytes_total / (1024*1024)) : 0;
      document.getElementById("wizMigRight").textContent = mb + " / " + mbT + " MB";

      if (d.status === "complete") {
        _wizStagingSSE.close();
        document.getElementById("wizMigrateProgress").style.display = "none";
        document.getElementById("wizMigrateComplete").style.display = "block";
        document.getElementById("wizMigrateCompleteMsg").textContent = d.message || "Migration complete";
        wizardState.stagingDir = d.staging_dir || wizardState.stagingDir;
        // Also set up _stagingSession for compatibility
        _stagingSession = {
          source_dir: wizardState.sourceDir,
          staging_dir: wizardState.stagingDir
        };
        wizardMarkComplete(1);
      } else if (d.status === "error" || d.status === "cancelled") {
        _wizStagingSSE.close();
        document.getElementById("wizMigrateProgress").style.display = "none";
        document.getElementById("wizMigrateBtn").disabled = false;
        toast(d.message || "Migration failed", "error");
      }
    };
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
  fetch("/api/scan/check-resume?directory=" + encodeURIComponent(wizardState.stagingDir) + "&mode=" + mode)
    .then(function(r) { return r.json(); })
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
      if (_wizScanSSE) _wizScanSSE.close();
      _wizScanSSE = new EventSource("/api/scan/progress");
      _wizScanSSE.onmessage = function(e) {
        var d = JSON.parse(e.data);
        var pct = d.total > 0 ? Math.round((d.current / d.total) * 100) : 0;
        document.getElementById("wizScanFill").style.width = pct + "%";
        document.getElementById("wizScanPct").textContent = pct + "%";
        document.getElementById("wizScanLeft").textContent = d.current + " / " + d.total;
        document.getElementById("wizScanStage").textContent = d.stage || "scanning";

        if (d.status === "complete") {
          _wizScanSSE.close();
          document.getElementById("wizScanProgress").style.display = "none";
          document.getElementById("wizScanComplete").style.display = "block";
          document.getElementById("wizScanCompleteMsg").textContent = d.message || "Scan complete";
          wizardState.lastReport = d.result_file;
          wizardMarkComplete(2);
        } else if (d.status === "error" || d.status === "cancelled") {
          _wizScanSSE.close();
          document.getElementById("wizScanProgress").style.display = "none";
          document.getElementById("wizScanActions").style.display = "block";
          toast(d.message || "Scan failed", "error");
        }
      };
    })
    .catch(function(err) {
      document.getElementById("wizScanProgress").style.display = "none";
      document.getElementById("wizScanActions").style.display = "block";
      toast("Scan error: " + err.message, "error");
    });
}

function wizardStartReview() {
  if (!wizardState.lastReport) { toast("Complete a scan first", "error"); return; }
  wizardState.browserReturnTo = "wizard";
  navigate("review", { report: wizardState.lastReport, returnTo: "wizard" });
}

// ---- File Browser ----
var browserState = {
  rootPath: null,
  currentPath: null,
  currentPage: 1,
  hasMore: false,
  loading: false,
  type: null,
  returnTo: "wizard"
};
var _browserObserver = null;

function openBrowser(type) {
  if (type === "staging") {
    browserState.rootPath = wizardState.stagingDir;
    browserState.type = "staging";
  } else if (type === "dupes") {
    browserState.rootPath = wizardState.dupesDir || (state.settings && state.settings.move_destination) || "";
    browserState.type = "dupes";
  }
  browserState.currentPath = browserState.rootPath;
  browserState.currentPage = 1;
  browserState.returnTo = "wizard";
  navigate("browser");
}

function initBrowser() {
  if (!browserState.rootPath) {
    // No folder in memory (page refresh/restart) — go to dashboard
    navigate("dashboard");
    return;
  }
  var backLabel = browserState.returnTo === "dashboard" ? "Back to Dashboard" : "Back to Finalize";
  document.getElementById("browserBackBtn").innerHTML = "&larr; " + backLabel;
  // Show scan button for both staging and dupes folders
  document.getElementById("browserScanBtn").style.display = "";
  browserState.currentPage = 1;
  document.getElementById("browserGrid").innerHTML = "";

  // Delegated click handler for folder items and folder delete buttons
  var grid = document.getElementById("browserGrid");
  grid.onclick = function(ev) {
    // Check if delete button was clicked
    var delBtn = ev.target.closest(".browser-folder-del");
    if (delBtn && delBtn.dataset.delpath) {
      ev.stopPropagation();
      deleteFolderItem(delBtn.dataset.delpath);
      return;
    }
    var item = ev.target.closest(".browser-folder");
    if (item && item.dataset.path) {
      browserNavigate(item.dataset.path);
    }
  };

  browserLoadPage(true);
  // Set up infinite scroll
  if (_browserObserver) _browserObserver.disconnect();
  _browserObserver = new IntersectionObserver(function(entries) {
    if (entries[0].isIntersecting && browserState.hasMore && !browserState.loading) {
      browserLoadPage(false);
    }
  });
  _browserObserver.observe(document.getElementById("browserSentinel"));
}

function browserLoadPage(replace) {
  browserState.loading = true;
  document.getElementById("browserLoading").style.display = "block";
  var sort = document.getElementById("browserSort").value || "name";
  var url = "/api/browse?path=" + encodeURIComponent(browserState.currentPath)
    + "&page=" + browserState.currentPage
    + "&page_size=50&sort=" + sort;

  fetch(url).then(function(r) { return r.json(); }).then(function(data) {
    browserState.loading = false;
    document.getElementById("browserLoading").style.display = "none";

    if (data.error) {
      document.getElementById("browserGrid").innerHTML =
        '<div class="browser-loading">Error: ' + escHtml(data.error) + '</div>';
      return;
    }

    browserState.hasMore = data.has_more;

    // Update breadcrumb
    buildBreadcrumb(data.path);
    document.getElementById("browserCount").textContent =
      data.total + " items";

    // Render items
    var html = "";
    for (var i = 0; i < data.entries.length; i++) {
      var e = data.entries[i];
      if (e.is_dir) {
        html += '<div class="browser-item browser-folder" data-path="' + escHtml(e.path) + '">'
          + '<div class="browser-thumb"><div class="browser-folder-icon">&#128193;</div></div>'
          + '<div class="browser-meta"><div class="browser-name">' + escHtml(e.name) + '</div>'
          + '<div class="browser-size">Folder</div></div>'
          + '<button class="browser-folder-del" data-delpath="' + escHtml(e.path) + '" title="Delete folder">&#10005;</button>'
          + '</div>';
      } else {
        var imgUrl = "/api/image?path=" + encodeURIComponent(e.path);
        var sizeStr = e.size > 1048576 ? (e.size / 1048576).toFixed(1) + " MB"
          : Math.round(e.size / 1024) + " KB";
        html += '<div class="browser-item" onclick="openLightbox(\'' + encodeURIComponent(e.path) + '\')">'
          + '<div class="browser-thumb"><img src="' + imgUrl + '" loading="lazy" alt=""></div>'
          + '<div class="browser-meta"><div class="browser-name">' + escHtml(e.name) + '</div>'
          + '<div class="browser-size">' + sizeStr + '</div></div></div>';
      }
    }

    if (replace) {
      document.getElementById("browserGrid").innerHTML = html;
    } else {
      document.getElementById("browserGrid").innerHTML += html;
    }
    browserState.currentPage++;

    if (data.total === 0) {
      var isRoot = browserState.currentPath === browserState.rootPath;
      var emptyHtml = '<div class="browser-loading">This folder is empty.';
      if (!isRoot) {
        emptyHtml += '<br><button class="btn btn-danger" style="margin-top:12px;" '
          + 'onclick="deleteCurrentFolder()">Delete This Folder</button>';
      }
      emptyHtml += '</div>';
      document.getElementById("browserGrid").innerHTML = emptyHtml;
    }
  }).catch(function(err) {
    browserState.loading = false;
    document.getElementById("browserLoading").style.display = "none";
    document.getElementById("browserGrid").innerHTML =
      '<div class="browser-loading">Error: ' + escHtml(err.message || "Failed to load") + '</div>';
  });
}

function browserNavigate(path) {
  browserState.currentPath = path;
  browserState.currentPage = 1;
  document.getElementById("browserGrid").innerHTML = "";
  browserLoadPage(true);
}

function browserRefresh() {
  browserState.currentPage = 1;
  document.getElementById("browserGrid").innerHTML = "";
  browserLoadPage(true);
}

function buildBreadcrumb(fullPath) {
  var root = browserState.rootPath.replace(/\\/g, "/");
  var current = fullPath.replace(/\\/g, "/");
  var rootLabel = browserState.type === "staging" ? "My Files" : "Removed Duplicates";

  var html = '<span class="browser-crumb" data-nav="' + escHtml(browserState.rootPath) + '">'
    + escHtml(rootLabel) + '</span>';

  if (current !== root && current.indexOf(root) === 0) {
    var rel = current.substring(root.length).replace(/^\//, "");
    var parts = rel.split("/");
    var built = browserState.rootPath;
    for (var i = 0; i < parts.length; i++) {
      if (!parts[i]) continue;
      built = built + "\\" + parts[i];
      html += '<span class="browser-crumb-sep">/</span>'
        + '<span class="browser-crumb" data-nav="' + escHtml(built) + '">'
        + escHtml(parts[i]) + '</span>';
    }
  }

  var bc = document.getElementById("browserBreadcrumb");
  bc.innerHTML = html;
  bc.onclick = function(ev) {
    var crumb = ev.target.closest(".browser-crumb");
    if (crumb && crumb.dataset.nav) {
      browserNavigate(crumb.dataset.nav);
    }
  };
}

function closeBrowser() {
  if (_browserObserver) _browserObserver.disconnect();
  navigate(browserState.returnTo || "wizard");
}

function deleteCurrentFolder() {
  var dir = browserState.currentPath;
  if (!dir || dir === browserState.rootPath) return;
  var folderName = dir.split("\\").pop();
  showDialog(
    "Delete Folder",
    "Delete the empty folder \"" + folderName + "\"?",
    "Delete",
    "btn-danger",
    function() {
      api("POST", "/api/browser/delete-folder", { path: dir }).then(function(r) {
        if (r.success) {
          // Navigate to parent
          var parent = dir.substring(0, dir.lastIndexOf("\\"));
          if (!parent || parent.length < browserState.rootPath.length) {
            parent = browserState.rootPath;
          }
          browserNavigate(parent);
          toast("Folder deleted");
        } else {
          toast("Delete failed: " + (r.error || "Unknown error"), "error");
        }
      }).catch(function(err) {
        toast("Delete failed: " + err.message, "error");
      });
    }
  );
}

function deleteFolderItem(path) {
  var folderName = path.split("\\").pop();
  showDialog(
    "Delete Folder",
    "Send the folder \"" + folderName + "\" and all its contents to the Recycle Bin?",
    "Delete",
    "btn-danger",
    function() {
      api("POST", "/api/browser/delete-folder", { path: path }).then(function(r) {
        if (r.success) {
          // Remove from grid
          var items = document.querySelectorAll(".browser-folder");
          for (var i = 0; i < items.length; i++) {
            if (items[i].dataset.path === path) {
              items[i].remove();
              break;
            }
          }
          var countEl = document.getElementById("browserCount");
          var match = (countEl.textContent || "").match(/(\d+)/);
          if (match) countEl.textContent = (parseInt(match[1]) - 1) + " items";
          toast("Folder deleted");
        } else {
          toast("Delete failed: " + (r.error || "Unknown error"), "error");
        }
      }).catch(function(err) {
        toast("Delete failed: " + err.message, "error");
      });
    }
  );
}

function openInExplorer() {
  var dir = browserState.currentPath || browserState.rootPath;
  if (!dir) return;
  api("POST", "/api/browser/open-explorer", { path: dir }).then(function() {
    window.blur();
  }).catch(function(err) {
    toast("Could not open Explorer: " + err.message, "error");
  });
}

// Auto-refresh browser when tab regains focus (catches changes made in Explorer)
document.addEventListener("visibilitychange", function() {
  if (!document.hidden && parseHash().view === "browser" && browserState.rootPath) {
    browserRefresh();
  }
});

function scanFromBrowser() {
  var dir = browserState.rootPath;
  if (!dir) return;
  // Pre-fill scan config with this folder and navigate there
  navigate("scan-config");
  // Wait for view to render, then set the directory
  setTimeout(function() {
    document.getElementById("scanDir").value = dir;
  }, 100);
}

// escAttr is defined near end of script -- handles HTML entity escaping

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

function updateStagingUI(d) {
  var pct = d.total > 0 ? Math.round((d.current / d.total) * 100) : 0;
  document.getElementById("stagingProgressFill").style.width = pct + "%";
  document.getElementById("stagingProgressPct").textContent = pct + "%";
  document.getElementById("stagingProgressLeft").textContent = d.current + " / " + d.total + " files";
  var mbCopied = d.bytes_copied ? Math.round(d.bytes_copied / (1024*1024)) : 0;
  var mbTotal = d.bytes_total ? Math.round(d.bytes_total / (1024*1024)) : 0;
  document.getElementById("stagingProgressRight").textContent = mbCopied + " / " + mbTotal + " MB";
  document.getElementById("stagingStage").textContent = d.stage || "staging";
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

// ---- Sync Back ----
var _syncbackSSE = null;

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
  document.getElementById("syncbackStart").style.display = "none";
  document.getElementById("syncbackProgress").style.display = "block";

  api("POST", "/api/staging/syncback", {
    staging_dir: _stagingSession.staging_dir,
    source_dir: _stagingSession.source_dir
  }).then(function() {
    if (_syncbackSSE) _syncbackSSE.close();
    _syncbackSSE = new EventSource("/api/staging/syncback/progress");
    _syncbackSSE.onmessage = function(e) {
      var d = JSON.parse(e.data);
      var pct = d.total > 0 ? Math.round((d.current / d.total) * 100) : 0;
      document.getElementById("syncbackProgressFill").style.width = pct + "%";
      document.getElementById("syncbackProgressPct").textContent = pct + "%";
      document.getElementById("syncbackProgressLeft").textContent = d.current + " / " + d.total;
      document.getElementById("syncbackStage").textContent = d.message || "Syncing";

      if (d.status === "complete") {
        _syncbackSSE.close();
        document.getElementById("syncbackProgress").style.display = "none";
        document.getElementById("syncbackCompleteBox").style.display = "block";
        document.getElementById("syncbackCompleteMsg").textContent = d.message || "";
      } else if (d.status === "error") {
        _syncbackSSE.close();
        document.getElementById("syncbackProgress").style.display = "none";
        document.getElementById("syncbackCompleteBox").style.display = "block";
        document.getElementById("syncbackCompleteTitle").textContent = "Sync Failed";
        document.getElementById("syncbackCompleteTitle").style.color = "var(--danger)";
        document.getElementById("syncbackCompleteMsg").textContent = d.message || "";
      }
    };
  });
}

function cleanupStaging() {
  if (!_stagingSession) return;
  // Check if staging has files -- if empty, just remove the folder
  fetch("/api/folders/status").then(function(r) { return r.json(); }).then(function(data) {
    var count = (data.staging && data.staging.file_count) || 0;
    if (count === 0) {
      api("POST", "/api/staging/cleanup", {
        staging_dir: _stagingSession.staging_dir
      }).then(function() {
        toast("Staging folder cleaned up");
        _stagingSession = null;
        navigate("dashboard");
      });
      return;
    }
    // Has files -- show decision dialog
    document.getElementById("dialogTitle").textContent = "Remove Workspace";
    document.getElementById("dialogMessage").innerHTML =
      '<div style="margin-bottom:16px;">You have <strong>' + count.toLocaleString() +
      '</strong> files in My Files. What would you like to do with them?</div>' +
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
    "Sending My Files to the Recycle Bin.",
    function(done) {
      api("POST", "/api/staging/recycle-bin", {
        staging_dir: _stagingSession.staging_dir
      }).then(function(r) {
        if (r.status === "recycled") {
          _stagingSession = null;
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

// ---- Working View (blocking progress) ----
var _workingConfig = { title: "", message: "", callback: null, destination: "dashboard" };

function startWorkingView(title, message, callback, destination) {
  _workingConfig.title = title;
  _workingConfig.message = message;
  _workingConfig.callback = callback;
  _workingConfig.destination = destination || "dashboard";
  navigate("working");
}

function initWorking() {
  document.getElementById("workingTitle").textContent = _workingConfig.title || "Working...";
  document.getElementById("workingMessage").textContent = _workingConfig.message || "Please wait.";
  document.getElementById("workingSpinner").style.display = "block";
  document.getElementById("workingComplete").style.display = "none";
  document.getElementById("workingStatus").textContent = "Processing...";

  if (_workingConfig.callback) {
    _workingConfig.callback(function(resultTitle, resultMsg) {
      // Called by the operation when done
      document.getElementById("workingSpinner").style.display = "none";
      document.getElementById("workingComplete").style.display = "block";
      document.getElementById("workingCompleteTitle").textContent = resultTitle || "Done";
      document.getElementById("workingCompleteMsg").textContent = resultMsg || "";
    });
  }
}

function _workingContinue() {
  navigate(_workingConfig.destination);
}

// ---- Finish Flow ----
var _finishSSE = null;
var _finishCounts = { staging: 0, dupes: 0, keepers: 0 };

function initFinish() {
  document.getElementById("finishSummary").style.display = "block";
  document.getElementById("finishProgress").style.display = "none";
  document.getElementById("finishComplete").style.display = "none";
  document.getElementById("finishTitle").textContent = "Finishing Up";
  document.getElementById("finishSubtitle").textContent = "Review what will happen, then confirm.";

  // Ensure staging session is loaded
  var p = _stagingSession
    ? Promise.resolve()
    : fetch("/api/staging/status").then(function(r) { return r.json(); }).then(function(d) {
        if (d.staging_dir && d.source_dir) {
          _stagingSession = { source_dir: d.source_dir, staging_dir: d.staging_dir };
        }
      });

  p.then(function() {
    return fetch("/api/folders/status").then(function(r) { return r.json(); }).then(function(data) {
      _finishCounts.staging = (data.staging && data.staging.file_count) || 0;
      _finishCounts.dupes = (data.dupes && data.dupes.file_count) || 0;
      _finishCounts.keepers = (data.keepers && data.keepers.file_count) || 0;
      document.getElementById("finishStagingCount").textContent = _finishCounts.staging.toLocaleString();
      document.getElementById("finishDupesCount").textContent = _finishCounts.dupes.toLocaleString();
      document.getElementById("finishKeepersCount").textContent = _finishCounts.keepers.toLocaleString();
      document.getElementById("finishKeepersRow").style.display = _finishCounts.keepers > 0 ? "flex" : "none";

      // Disable finish if no staging session
      var btn = document.getElementById("finishNowBtn");
      if (!_stagingSession) {
        btn.disabled = true;
        btn.textContent = "No staging session found";
      } else {
        btn.disabled = false;
        btn.textContent = "Finish Now";
      }
    });
  });
}

function _finishConfirm() {
  var msg = "";
  if (_finishCounts.staging > 0) {
    msg += _finishCounts.staging.toLocaleString() + " files from My Files will be returned to their original folder. ";
  }
  if (_finishCounts.keepers > 0) {
    msg += _finishCounts.keepers.toLocaleString() + " Verified Keepers will also be returned. ";
  }
  if (_finishCounts.dupes > 0) {
    msg += _finishCounts.dupes.toLocaleString() + " duplicates will be removed (recoverable from Recycle Bin, if needed). ";
  }
  msg += "Your originals are never deleted. Continue?";
  showDialog("Confirm Finish", msg, "Yes, Finish", "btn-primary", function() {
    _executeFinish();
  });
}

function _executeFinish() {
  document.getElementById("finishSummary").style.display = "none";
  document.getElementById("finishProgress").style.display = "block";
  document.getElementById("finishTitle").textContent = "Finishing Up...";
  document.getElementById("finishSubtitle").textContent = "";

  var totalPhases = (_finishCounts.staging > 0 || _finishCounts.keepers > 0 ? 1 : 0) + (_finishCounts.dupes > 0 ? 1 : 0) + 1;
  var curPhase = 0;

  // Phase 1: Restore all kept files (My Files + Keepers) to source — safe copy, no deletions
  if ((_finishCounts.staging > 0 || _finishCounts.keepers > 0) && _stagingSession) {
    curPhase++;
    document.getElementById("finishPhaseLabel").textContent = "Step " + curPhase + " of " + totalPhases + ": Returning your files...";
    document.getElementById("finishStage").textContent = "Copying files back to original folder";

    api("POST", "/api/staging/restore", {
      staging_dir: _stagingSession.staging_dir,
      source_dir: _stagingSession.source_dir,
      include_keepers: true
    }).then(function(r) {
      _finishPhase2(r || {});
    }).catch(function(err) {
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
      api("POST", "/api/staging/restore", {
        staging_dir: "cleared",
        source_dir: "cleared",
        full_restore: true
      }).catch(function() {});
    }

    // Show completion
    _stagingSession = null;
    document.getElementById("finishProgress").style.display = "none";
    document.getElementById("finishComplete").style.display = "block";
    document.getElementById("finishTitle").textContent = "All Done!";
    document.getElementById("finishSubtitle").textContent = "";

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
  }); // end Promise.all
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

// ---- Heartbeat ----
setInterval(function() {
  fetch("/api/heartbeat").catch(function() {});
}, 5000);

// ---- API Helper ----
function api(method, path, body) {
  var opts = { method: method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  return fetch(path, opts).then(function(r) {
    if (!r.ok) return r.json().then(function(d) { throw new Error(d.error || "Request failed"); });
    return r.json();
  });
}

// ---- Router ----
var _appNavigated = false;
function navigate(view, params) {
  // Auto-save decisions when leaving review
  if (state.currentReport && state.decisions && Object.keys(state.decisions).length > 0) {
    _saveDecisionsNow();
  }
  _appNavigated = true;
  var hash = "#" + view;
  if (params) {
    var parts = [];
    for (var k in params) parts.push(k + "=" + encodeURIComponent(params[k]));
    if (parts.length) hash += "?" + parts.join("&");
  }
  if (window.location.hash === hash) {
    // Already on this view — force a refresh
    route();
  } else {
    window.location.hash = hash;
  }
}

function parseHash() {
  var hash = window.location.hash.replace(/^#/, "") || "dashboard";
  var qIdx = hash.indexOf("?");
  var view = qIdx >= 0 ? hash.substring(0, qIdx) : hash;
  var params = {};
  if (qIdx >= 0) {
    var qs = hash.substring(qIdx + 1);
    qs.split("&").forEach(function(pair) {
      var kv = pair.split("=");
      if (kv.length === 2) params[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1]);
    });
  }
  return { view: view, params: params };
}

function _openRecycleBin() {
  api("POST", "/api/browser/open-recycle-bin").then(function(r) {
    if (r.success) window.blur();
    else toast("Could not open Recycle Bin", "error");
  }).catch(function() { toast("Could not open Recycle Bin", "error"); });
}

function _rescanFolder(type) {
  var path = _dashFolderPaths[type];
  if (!path) { toast("No folder to scan", "warning"); return; }
  // Pre-fill the scan config with this folder path
  document.getElementById("scanDir").value = path;
  navigate("scan-config");
}

function _navToWizardStep(step) {
  wizardState.currentStep = step;
  if (step === 1) wizardState.completedSteps = {};
  navigate("wizard");
}

function _navToReview() {
  // Find the most recent scan report
  if (state.lastReport) {
    navigate("review", { report: state.lastReport });
  } else {
    fetch("/api/scans").then(function(r) { return r.json(); }).then(function(scans) {
      if (scans.length > 0) {
        navigate("review", { report: scans[0].filename });
      } else {
        toast("No scan results to review", "warning");
      }
    });
  }
}

function _updateNavStates() {
  // Grey out nav items based on current app state
  var migrate = document.getElementById("navMigrate");
  var scan = document.getElementById("navScan");
  var review = document.getElementById("navReview");
  var finalize = document.getElementById("navFinalize");

  // Migrate: always available
  migrate.classList.remove("disabled");

  // Scan: available if staging session exists (files migrated)
  var hasStagingSession = !!(wizardState.stagingDir || (_stagingSession && _stagingSession.staging_dir));
  scan.classList.toggle("disabled", !hasStagingSession);

  // Review: available if there are scan results
  var hasScans = !!(state.lastReport || (state.scans && state.scans.length > 0));
  review.classList.toggle("disabled", !hasScans);

  // Finalize: available if staging has files
  var hasFiles = hasStagingSession;
  finalize.classList.toggle("disabled", !hasFiles);
}

function route() {
  var parsed = parseHash();
  var view = parsed.view;
  var params = parsed.params;

  // Hide all views
  var views = document.querySelectorAll(".view");
  for (var i = 0; i < views.length; i++) views[i].classList.remove("active");

  // Update nav — map wizard steps to nav items
  var navView = view;
  if (view === "wizard") {
    var step = wizardState.currentStep || 1;
    if (step === 1) navView = "wizard-migrate";
    else if (step === 2) navView = "wizard-scan";
    else if (step === 3) navView = "review";
    else if (step === 4) navView = "finish";
  } else if (view === "scan-config" || view === "scan-progress") {
    navView = "wizard-scan";
  }
  var links = document.querySelectorAll(".nav-link");
  for (var i = 0; i < links.length; i++) {
    links[i].classList.toggle("active", links[i].getAttribute("data-view") === navView);
  }
  _updateNavStates();

  // Show kbd hints only in review
  document.getElementById("kbdHints").style.display = view === "review" ? "flex" : "none";

  // Activate view
  var viewEl = document.getElementById("view-" + view);
  if (viewEl) {
    viewEl.classList.add("active");
  } else {
    document.getElementById("view-dashboard").classList.add("active");
    view = "dashboard";
  }

  // On fresh page load, redirect stateful views to dashboard
  if (!_appNavigated && view !== "dashboard" && view !== "settings" && view !== "activity") {
    navigate("dashboard");
    return;
  }

  // View-specific init
  if (view === "dashboard") initDashboard();
  else if (view === "scan-config") initScanConfig();
  else if (view === "scan-progress") initScanProgress();
  else if (view === "review") initReview(params.report, params.returnTo);
  else if (view === "actions") initActions();
  else if (view === "oddball") initOddball(params.report);
  else if (view === "wizard") initWizard();
  else if (view === "browser") initBrowser();
  else if (view === "staging-progress") initStagingProgress();
  else if (view === "syncback") initSyncback();
  else if (view === "finish") initFinish();
  else if (view === "working") initWorking();
  else if (view === "activity") loadActivity();
  else if (view === "settings") initSettings();
}

window.onhashchange = route;

// ---- Radio helper ----
function selectRadio(el, name) {
  var siblings = el.parentElement.querySelectorAll(".radio-option");
  for (var i = 0; i < siblings.length; i++) siblings[i].classList.remove("selected");
  el.classList.add("selected");
  el.querySelector("input").checked = true;
}

/* ==================================================================
   DASHBOARD
   ================================================================== */
var _dashFolderPaths = { staging: "", dupes: "", keepers: "" };

var _dashContinueTarget = "finish"; // default

function _dashUpdateContinueButton(hasStaging, hasDupes, hasKeepers) {
  var btn = document.getElementById("dashContinueBtn");
  var hint = document.getElementById("dashContinueHint");

  // Determine the most logical next step
  if (hasStaging && hasDupes) {
    // Has both — user has been scanning, likely wants to finalize or rescan
    btn.textContent = "Continue to Finalize";
    hint.textContent = "Browse your files and finish up, or rescan for more duplicates.";
    _dashContinueTarget = "wizard-step4";
  } else if (hasStaging && !hasDupes) {
    // Has files but no dupes yet — needs to scan
    btn.textContent = "Continue to Scan";
    hint.textContent = "Scan My Files to find duplicates.";
    _dashContinueTarget = "wizard-step2";
  } else if (hasDupes && !hasStaging) {
    // Only dupes — maybe wants to review or rescue
    btn.textContent = "Continue to Review";
    hint.textContent = "Removed Duplicates has files. Rescue & Review or finish up.";
    _dashContinueTarget = "finish";
  } else if (hasKeepers) {
    btn.textContent = "Finish Up";
    hint.textContent = "Verified Keepers are ready to go home.";
    _dashContinueTarget = "finish";
  } else {
    btn.textContent = "Continue";
    hint.textContent = "";
    _dashContinueTarget = "finish";
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
  fetch("/api/folders/status").then(function(r) { return r.json(); }).then(function(data) {
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

    // Dynamic continue button
    var hasAnySystemFiles = hasStaging || hasDupes || hasKeepers;
    document.getElementById("dashContinueAction").style.display = hasAnySystemFiles ? "block" : "none";
    if (hasAnySystemFiles) {
      _dashUpdateContinueButton(hasStaging, hasDupes, hasKeepers);
    }

    // Rescan boxes
    var rescanBox = document.getElementById("dashRescanBoxes");
    var rescanDupesBtn = document.getElementById("dashRescanDupesBtn");
    var rescanKeepersBtn = document.getElementById("dashRescanKeepersBtn");
    var rescanDupesHint = document.getElementById("dashRescanDupesHint");
    var rescanKeepersHint = document.getElementById("dashRescanKeepersHint");
    rescanBox.style.display = (hasDupes || hasKeepers) ? "block" : "none";
    rescanDupesBtn.disabled = !hasDupes;
    rescanDupesHint.textContent = hasDupes ? data.dupes.file_count.toLocaleString() + " files" : "No files";
    rescanKeepersBtn.disabled = !hasKeepers;
    rescanKeepersHint.textContent = hasKeepers ? data.keepers.file_count.toLocaleString() + " files" : "No files";

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
  fetch("/api/folders/status").then(function(r) { return r.json(); }).then(function(data) {
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
          fetch("/api/folders/status").then(function(r2) { return r2.json(); }).then(function(fs) {
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
      fetch("/api/staging/status").then(function(r) { return r.json(); }).then(function(status) {
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
    : fetch("/api/staging/status").then(function(r) { return r.json(); }).then(function(d) {
        if (d.staging_dir && d.source_dir) {
          _stagingSession = { source_dir: d.source_dir, staging_dir: d.staging_dir };
        }
      });
  p.then(function() {
    if (!_stagingSession) {
      toast("No staging session found. Files may have been staged outside the wizard.", "error");
      return;
    }
    return fetch("/api/folders/status").then(function(r) { return r.json(); }).then(function(data) {
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
  fetch("/api/folders/status").then(function(r) { return r.json(); }).then(function(data) {
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
  fetch("/api/folders/status").then(function(r) { return r.json(); }).then(function(data) {
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
  fetch("/api/folders/status").then(function(r) { return r.json(); }).then(function(data) {
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
  // Show bookmark notice if not yet dismissed
  var bmNotice = document.getElementById("bookmarkNotice");
  if (localStorage.getItem("dupefinder_bookmarked")) {
    bmNotice.style.display = "none";
  } else {
    bmNotice.style.display = "flex";
  }

  // Load settings for later use
  api("GET", "/api/settings").then(function(s) {
    state.settings = s;
  }).catch(function() {});

  // Fetch folder status for browse buttons
  _dashUpdateFolders();

  api("GET", "/api/scans").then(function(scans) {
    var list = document.getElementById("scanList");
    var statsBox = document.getElementById("dashboardStats");

    if (!scans || scans.length === 0) {
      list.innerHTML = '<div class="empty-state"><h3>No scans yet</h3><p>Click "Start New Scan" to find duplicates.</p></div>';
      statsBox.style.display = "none";
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

/* ==================================================================
   SCAN CONFIG
   ================================================================== */
function fillScanDir(type) {
  if (type === "staging") {
    // Try staging session, then API, then settings default
    if (_stagingSession && _stagingSession.staging_dir) {
      document.getElementById("scanDir").value = _stagingSession.staging_dir;
      return;
    }
    fetch("/api/staging/status").then(function(r) { return r.json(); }).then(function(d) {
      if (d.staging_dir) {
        document.getElementById("scanDir").value = d.staging_dir;
      } else {
        fetch("/api/settings").then(function(r) { return r.json(); }).then(function(s) {
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
  api("GET", "/api/settings").then(function(settings) {
    state.settings = settings;
    document.getElementById("scanThreshold").value = settings.threshold || 5;
    document.getElementById("thresholdVal").textContent = settings.threshold || 5;
    document.getElementById("scanRecursive").checked = settings.recursive !== false;
  });
  // Update quick-fill buttons with file counts
  fetch("/api/folders/status").then(function(r) { return r.json(); }).then(function(data) {
    var sBtn = document.getElementById("scanFillStagingBtn");
    var dBtn = document.getElementById("scanFillDupesBtn");
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
      document.getElementById("scanKeepersSection").style.display = "block";
    } else {
      dBtn.textContent = "Removed Duplicates (empty)";
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
      _checkResumeAndStart(dir, mode, threshold, recursive);
    }
  }).catch(function() {
    _checkResumeAndStart(dir, mode, threshold, recursive);
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
    + '<div style="margin-top:12px;"><button class="btn btn-ghost" onclick="closeDialog()">Cancel</button></div>';

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

function _checkResumeAndStart(dir, mode, threshold, recursive) {
  fetch("/api/scan/check-resume?directory=" + encodeURIComponent(dir) + "&mode=" + mode)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.has_checkpoint) {
        var info = data.checkpoint_info;
        var cached = (info.md5_hashed || 0) + (info.phash_hashed || 0);
        var ts = info.timestamp ? new Date(info.timestamp).toLocaleString() : "unknown";
        showResumeDialog(
          "An interrupted scan was found for this folder.",
          "Stage: " + info.stage + " | Hashes cached: " + cached + " | Last active: " + ts,
          function() { _doStartScan(dir, mode, threshold, recursive, true); },
          function() { _doStartScan(dir, mode, threshold, recursive, false); }
        );
      } else {
        _doStartScan(dir, mode, threshold, recursive, false);
      }
    })
    .catch(function() {
      _doStartScan(dir, mode, threshold, recursive, false);
    });
}

function _doStartScan(dir, mode, threshold, recursive, resume) {
  _lastScanMode = mode;
  api("POST", "/api/scan/start", {
    directory: dir, mode: mode, threshold: threshold, recursive: recursive,
    resume: resume
  }).then(function() {
    navigate("scan-progress");
  }).catch(function(err) {
    toast("Error: " + err.message, "error");
  });
}

/* ==================================================================
   SCAN PROGRESS
   ================================================================== */
var _scanSSE = null;
var _scanStartTime = null;
var _lastScanMode = "exact";

function initScanProgress() {
  // Reset UI
  document.getElementById("scanProgressActions").style.display = "block";
  document.getElementById("scanCompleteBox").style.display = "none";
  document.getElementById("scanProgressFill").style.width = "0%";
  document.getElementById("scanProgressPct").textContent = "0%";
  _scanStartTime = Date.now();

  // Connect SSE
  if (_scanSSE) _scanSSE.close();
  _scanSSE = new EventSource("/api/scan/progress");
  _scanSSE.onmessage = function(e) {
    var d = JSON.parse(e.data);
    updateScanUI(d);

    if (d.status === "complete" || d.status === "error" || d.status === "cancelled") {
      _scanSSE.close();
      _scanSSE = null;
      showScanComplete(d);
    }
  };
  _scanSSE.onerror = function() {
    if (_scanSSE) _scanSSE.close();
    _scanSSE = null;
  };
}

function updateScanUI(d) {
  var stageNames = {
    "discovering": "Discovering images...",
    "md5": "Computing checksums...",
    "phash_hash": "Computing perceptual hashes...",
    "phash_compare": "Comparing images...",
    "saving": "Saving results...",
    "done": "Complete"
  };
  document.getElementById("scanStage").textContent = stageNames[d.stage] || d.stage || "Working...";
  document.getElementById("scanErrors").textContent = d.errors || 0;

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

  if (d.status === "complete") {
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

  if (d.summary) {
    var s = d.summary;
    var html = '<div class="card-grid">';
    html += '<div class="stat-card"><div class="num">' + s.total_images + '</div><div class="label">Images Scanned</div></div>';
    html += '<div class="stat-card"><div class="num">' + s.total_groups + '</div><div class="label">Duplicate Groups</div></div>';
    html += '<div class="stat-card"><div class="num">' + s.reclaimable_mb + ' MB</div><div class="label">Reclaimable</div></div>';
    html += '<div class="stat-card"><div class="num">' + formatTime(s.duration) + '</div><div class="label">Duration</div></div>';
    html += '</div>';
    document.getElementById("scanCompleteSummary").innerHTML = html;
  }

  if (d.result_file) {
    var totalGroups = (d.summary && d.summary.total_groups) || 0;
    if (totalGroups === 0) {
      // No dupes found — show rescan/done options instead of review
      document.getElementById("scanReviewBtn").style.display = "none";
      document.getElementById("scanCompleteSummary").innerHTML +=
        '<div style="margin-top:16px;text-align:center;">' +
        '<p style="color:var(--text-dim);margin-bottom:12px;">No duplicates found at this threshold. Try a different scan mode or a higher perceptual threshold.</p>' +
        '<div style="display:flex;gap:12px;justify-content:center;">' +
        '<button class="btn btn-primary" onclick="navigate(\'wizard\'); setTimeout(function(){wizardGoToStep(2);},100);">Rescan</button>' +
        '<button class="btn btn-secondary" onclick="navigate(\'dashboard\')">Done</button>' +
        '</div></div>';
    } else {
      var btn = document.getElementById("scanReviewBtn");
      btn.style.display = "inline-flex";
      btn.onclick = function() { navigate("review", { report: d.result_file }); };
    }
  }
}

function cancelScan() {
  api("POST", "/api/scan/cancel").then(function() {
    toast("Cancelling scan...", "warning");
  });
}

/* ==================================================================
   REVIEW
   ================================================================== */
// ---- Decision persistence and chunked review ----
var _decisionSaveTimer = null;

function _saveDecisions() {
  if (!state.currentReport) return;
  clearTimeout(_decisionSaveTimer);
  _decisionSaveTimer = setTimeout(function() {
    api("POST", "/api/decisions/save", {
      report: state.currentReport,
      decisions: state.decisions
    }).catch(function() {}); // silent save
  }, 3000); // debounce 3 seconds
}

function _saveDecisionsNow() {
  if (!state.currentReport) return;
  clearTimeout(_decisionSaveTimer);
  api("POST", "/api/decisions/save", {
    report: state.currentReport,
    decisions: state.decisions
  }).catch(function() {});
}

function _updateChunkDisplay() {
  if (!state.groups || state.groups.length === 0) return;
  var total = state.groups.length;
  var chunkStart = state.chunkIndex * state.chunkSize;
  var chunkEnd = Math.min(chunkStart + state.chunkSize, total);
  var totalChunks = Math.ceil(total / state.chunkSize);

  // Update chunk info in the toolbar
  var info = document.getElementById("reviewChunkInfo");
  if (info) {
    if (state.chunkSize >= total) {
      info.textContent = total.toLocaleString() + " groups";
    } else {
      info.textContent = "Batch " + (state.chunkIndex + 1) + " of " + totalChunks +
        " (groups " + (chunkStart + 1) + "-" + chunkEnd + " of " + total.toLocaleString() + ")";
    }
  }
}

function _showChunkCheckpoint() {
  var total = state.groups.length;
  var reviewed = 0;
  for (var i = 0; i < total; i++) { if (state.decisions[i]) reviewed++; }
  var remaining = total - reviewed;

  showDialog(
    "Batch Complete",
    "You've reviewed this batch. " + reviewed.toLocaleString() + " of " +
    total.toLocaleString() + " groups decided (" + remaining.toLocaleString() + " remaining).",
    "Next Batch", "btn-primary",
    function() {
      state.chunkIndex++;
      var chunkStart = state.chunkIndex * state.chunkSize;
      if (chunkStart >= state.groups.length) {
        toast("All groups reviewed!");
        state.chunkIndex = Math.max(0, state.chunkIndex - 1);
      }
      state.currentGroupIndex = 0;
      _updateChunkDisplay();
      applyReviewFilters();
    }
  );
  // Add extra buttons to the dialog
  var msg = document.getElementById("dialogMessage");
  msg.innerHTML = msg.textContent +
    '<div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:16px;">' +
    '<button class="btn btn-warning" onclick="closeDialog(); reviewBulkMove()">Mark All Remaining</button>' +
    '<button class="btn btn-secondary" onclick="closeDialog(); reviewBulkSkip()">Keep All Remaining</button>' +
    '<button class="btn btn-secondary" onclick="closeDialog(); _saveDecisionsNow(); navigate(\'dashboard\')">Take a Break</button>' +
    '</div>';
}

function _checkChunkEnd() {
  // If chunking is active and we've reached the end of the current chunk
  if (state.chunkSize >= state.groups.length) return; // all groups shown
  var chunkEnd = (state.chunkIndex + 1) * state.chunkSize;
  if (state.currentGroupIndex >= state.filteredIndices.length - 1 && chunkEnd < state.groups.length) {
    _showChunkCheckpoint();
  }
}

function _setChunkSize(size) {
  state.chunkSize = size;
  state.chunkIndex = 0;
  state.currentGroupIndex = 0;
  _updateChunkDisplay();
  applyReviewFilters();
}

function initReview(report, returnTo) {
  // Update back button destination
  var backBtn = document.getElementById("reviewBackBtn");
  if (returnTo === "wizard") {
    backBtn.onclick = function() { navigate("wizard"); };
    state._reviewReturnTo = "wizard";
  } else {
    backBtn.onclick = function() { navigate("dashboard"); };
    state._reviewReturnTo = null;
  }
  // Fall back to last loaded report or wizard report
  if (!report) {
    report = state.currentReport || (typeof wizardState !== "undefined" && wizardState.lastReport) || null;
  }
  if (!report) {
    document.getElementById("reviewContent").innerHTML =
      '<div class="empty-state"><h3>No report selected</h3><p>Go to the dashboard and choose a scan to review.</p></div>';
    return;
  }

  // If same report and we have data, just re-render
  if (state.currentReport === report && state.groups.length > 0) {
    applyReviewFilters();
    return;
  }

  state.currentReport = report;
  state.decisions = {};
  state.currentGroupIndex = 0;
  state.chunkIndex = 0;
  state.chunkSize = state.chunkSize || 250;

  document.getElementById("reviewContent").innerHTML =
    '<div class="empty-state"><p>Loading groups...</p></div>';

  api("GET", "/api/groups?report=" + encodeURIComponent(report)).then(function(data) {
    state.groups = data.groups || [];
    state._scanMetadata = data.metadata || {};
    state.filteredIndices = [];
    for (var i = 0; i < state.groups.length; i++) state.filteredIndices.push(i);

    // Load saved decisions if they exist
    return api("GET", "/api/decisions/load?report=" + encodeURIComponent(report)).then(function(saved) {
      if (saved.decisions && typeof saved.decisions === "object") {
        for (var k in saved.decisions) {
          if (saved.decisions.hasOwnProperty(k)) state.decisions[k] = saved.decisions[k];
        }
        // Find first unreviewed group to resume from
        var firstUnreviewed = 0;
        for (var i = 0; i < state.groups.length; i++) {
          if (!state.decisions[i]) { firstUnreviewed = i; break; }
        }
        state.currentGroupIndex = firstUnreviewed;
        state.chunkIndex = Math.floor(firstUnreviewed / state.chunkSize);
      }
      return null;
    }).catch(function() { /* ignore load errors */ });
  }).then(function() {
    document.getElementById("reviewTotalLabel").textContent = state.groups.length;
    document.getElementById("reviewTitle").textContent =
      "Review: " + report + " (" + state.groups.length + " groups)";

    // Hide Move buttons if scan was on the dupes folder (move would be circular)
    var scanDir = (state._scanMetadata.directory || "").replace(/\\/g, "/").toLowerCase();
    var dupesDir = ((state.settings && state.settings.move_destination) || "").replace(/\\/g, "/").toLowerCase();
    var isDupesScan = scanDir && dupesDir && scanDir.indexOf(dupesDir) === 0;
    document.getElementById("reviewMoveSingleBtn").style.display = isDupesScan ? "none" : "";
    document.getElementById("reviewMoveBulkBtn").style.display = isDupesScan ? "none" : "";

    _updateChunkDisplay();
    applyReviewFilters();
  }).catch(function(err) {
    document.getElementById("reviewContent").innerHTML =
      '<div class="empty-state" style="color:var(--danger);">Error: ' + escHtml(String(err)) + '</div>';
  });
}

function applyReviewFilters() {
  var sortBy = document.getElementById("reviewSort").value;
  var filterBy = document.getElementById("reviewFilter").value;
  var search = document.getElementById("reviewSearch").value.toLowerCase().trim();

  // Build filtered indices
  var indices = [];
  for (var i = 0; i < state.groups.length; i++) {
    var g = state.groups[i];
    var decision = state.decisions[i];

    // Filter
    if (filterBy === "unreviewed" && decision) continue;
    if (filterBy === "move" && decision !== "move") continue;
    if (filterBy === "delete" && decision !== "delete") continue;
    if (filterBy === "skip" && decision !== "skip") continue;

    // Search
    if (search) {
      var haystack = (g.keep || "").toLowerCase();
      for (var j = 0; j < (g.duplicates || []).length; j++) {
        haystack += " " + (g.duplicates[j] || "").toLowerCase();
      }
      if (haystack.indexOf(search) < 0) continue;
    }

    indices.push(i);
  }

  // Sort
  if (sortBy === "size_desc") {
    indices.sort(function(a, b) {
      return (state.groups[b].files || 0) - (state.groups[a].files || 0);
    });
  } else if (sortBy === "space_desc") {
    indices.sort(function(a, b) {
      return (state.groups[b].reclaimable_bytes || 0) - (state.groups[a].reclaimable_bytes || 0);
    });
  } else if (sortBy === "distance_asc" || sortBy === "distance_desc") {
    var mult = sortBy === "distance_asc" ? 1 : -1;
    indices.sort(function(a, b) {
      var da = getGroupDistance(state.groups[a]);
      var db = getGroupDistance(state.groups[b]);
      return (da - db) * mult;
    });
  }

  // Apply chunk pagination (only if not showing all)
  if (state.chunkSize < state.groups.length) {
    var chunkStart = state.chunkIndex * state.chunkSize;
    var chunkEnd = chunkStart + state.chunkSize;
    var chunked = [];
    for (var ci = 0; ci < indices.length; ci++) {
      if (indices[ci] >= chunkStart && indices[ci] < chunkEnd) chunked.push(indices[ci]);
    }
    state.filteredIndices = chunked;
  } else {
    state.filteredIndices = indices;
  }

  // Clamp current index
  if (state.currentGroupIndex >= state.filteredIndices.length) {
    state.currentGroupIndex = Math.max(0, state.filteredIndices.length - 1);
  }

  document.getElementById("reviewFilterInfo").textContent =
    "Showing " + state.filteredIndices.length + " of " + state.groups.length + " groups";
  document.getElementById("reviewTotalLabel").textContent = state.filteredIndices.length;

  renderReviewGroup();
  updateReviewActionInfo();
}

function getGroupDistance(group) {
  if (group.distance !== undefined) return group.distance;
  var dists = group.distances;
  if (dists) {
    var vals = [];
    for (var k in dists) vals.push(dists[k]);
    if (vals.length) return Math.max.apply(null, vals);
  }
  return -1;
}

function renderReviewGroup() {
  var content = document.getElementById("reviewContent");

  if (state.filteredIndices.length === 0) {
    content.innerHTML = '<div class="empty-state"><h3>No groups to show</h3>'
      + '<p>No duplicates were found with the current settings. Try a different scan mode or a higher perceptual threshold.</p>'
      + '<div style="margin-top:16px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">'
      + '<button class="btn btn-primary" onclick="navigate(\'dashboard\')">Back to Dashboard</button>'
      + '<button class="btn btn-secondary" onclick="navigate(\'scan-config\')">Rescan with Different Settings</button>'
      + '</div></div>';
    return;
  }

  var realIdx = state.filteredIndices[state.currentGroupIndex];
  var group = state.groups[realIdx];
  var decision = state.decisions[realIdx];

  document.getElementById("reviewJumpInput").value = state.currentGroupIndex + 1;
  document.getElementById("reviewPrevBtn").disabled = state.currentGroupIndex === 0;
  document.getElementById("reviewNextBtn").disabled = state.currentGroupIndex >= state.filteredIndices.length - 1;

  var html = "";

  // Group header
  html += '<div class="group-header">';
  html += '<div class="group-title">Group ' + (realIdx + 1);
  if (decision === "skip") html += ' <span class="decision-badge decision-skip">KEEPING</span>';
  if (decision === "move") html += ' <span class="decision-badge decision-move">DUPLICATE</span>';
  if (decision === "delete") html += ' <span class="decision-badge decision-delete">DELETE</span>';
  html += '</div>';

  html += '<div class="group-meta">';
  html += (group.files || ((group.duplicates || []).length + 1)) + " files";
  html += " | " + formatBytes(group.reclaimable_bytes || 0) + " reclaimable";

  var dist = getGroupDistance(group);
  if (dist >= 0) {
    var distClass = dist <= 2 ? "dist-low" : (dist <= 8 ? "dist-med" : "dist-high");
    html += ' | <span class="distance-badge ' + distClass + '">distance: ' + dist + '</span>';
  }
  html += '</div></div>';

  // Image grid — show all files, use _userKeeps for badge
  html += '<div class="image-grid">';
  var allFiles = [group.keep].concat(group.duplicates || []);
  var seen = {};
  for (var i = 0; i < allFiles.length; i++) {
    if (seen[allFiles[i]]) continue;
    seen[allFiles[i]] = true;
    var isKeep = group._userKeeps ? !!group._userKeeps[allFiles[i]] : (allFiles[i] === group.keep);
    var fileDist = null;
    if (group.distances && group.distances[allFiles[i]] !== undefined) {
      fileDist = group.distances[allFiles[i]];
    }
    html += makeImageCardHtml(allFiles[i], isKeep ? "keep" : "dupe", fileDist, realIdx);
  }
  html += '</div>';

  content.innerHTML = html;
  window.scrollTo(0, 0);
}

function makeImageCardHtml(filepath, type, distance, groupIdx) {
  var encoded = encodeURIComponent(filepath);
  var badgeClass = type === "keep" ? "badge-keep" : "badge-dupe";
  var badgeText = type === "keep" ? "KEEP" : "DUPE";
  var cardClass = type;

  var html = '<div class="image-card ' + cardClass + '" style="cursor:pointer;" onclick="toggleKeepDupe(' + groupIdx + ',\'' + escAttr(filepath) + '\')">';
  html += '<div class="image-wrapper">';
  html += '<span class="badge ' + badgeClass + '">' + badgeText + '</span>';
  html += '<img src="/api/image?path=' + escAttr(encoded) + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<span style=color:var(--text-dim);font-size:12px>Could not load</span>\'">';
  html += '<button class="btn btn-ghost" style="position:absolute;bottom:4px;right:4px;font-size:10px;padding:2px 8px;background:rgba(0,0,0,0.7);color:#fff;border-radius:4px;" onclick="event.stopPropagation(); openLightbox(\'' + escAttr(encoded) + '\')">Zoom</button>';
  html += '</div>';
  html += '<div class="card-info">';
  html += '<div class="card-filename">' + escHtml(getFilename(filepath)) + '</div>';
  html += '<div class="card-meta">' + escHtml(getFolder(filepath));
  if (distance !== null && distance !== undefined) {
    html += ' | dist: ' + distance;
  }
  html += '</div>';
  html += '</div></div>';
  return html;
}

function toggleKeepDupe(groupIdx, filepath) {
  var group = state.groups[groupIdx];
  if (!group) return;

  // Initialize user selections if not yet set
  if (!group._userKeeps) {
    group._userKeeps = {};
    group._userKeeps[group.keep] = true;
  }

  if (group._userKeeps[filepath]) {
    // Currently KEEP — toggle to DUPE
    // Must keep at least one file
    var keepCount = 0;
    for (var k in group._userKeeps) { if (group._userKeeps[k]) keepCount++; }
    if (keepCount <= 1) {
      toast("At least one file must be kept");
      return;
    }
    delete group._userKeeps[filepath];
  } else {
    // Currently DUPE — toggle to KEEP
    group._userKeeps[filepath] = true;
  }

  // Rebuild keep/duplicates from user selections
  var allFiles = [group.keep].concat(group.duplicates || []);
  // Deduplicate
  var seen = {};
  var unique = [];
  for (var i = 0; i < allFiles.length; i++) {
    if (!seen[allFiles[i]]) { seen[allFiles[i]] = true; unique.push(allFiles[i]); }
  }

  var newKeep = null;
  var newDupes = [];
  for (var j = 0; j < unique.length; j++) {
    if (group._userKeeps[unique[j]]) {
      if (!newKeep) newKeep = unique[j];
      else newDupes.push(unique[j]); // additional keeps still need to not be in dupes
    } else {
      newDupes.push(unique[j]);
    }
  }

  // The "keep" field is the primary keeper; additional keeps are NOT in duplicates
  group.keep = newKeep || unique[0];
  group.duplicates = newDupes;

  renderReviewGroup();
}

function reviewNav(dir) {
  state.currentGroupIndex = Math.max(0, Math.min(state.filteredIndices.length - 1, state.currentGroupIndex + dir));
  renderReviewGroup();
}

function reviewJumpTo(val) {
  var n = parseInt(val);
  if (n >= 1 && n <= state.filteredIndices.length) {
    state.currentGroupIndex = n - 1;
    renderReviewGroup();
  }
}

function reviewMarkSkip() {
  if (state.filteredIndices.length === 0) return;
  var realIdx = state.filteredIndices[state.currentGroupIndex];
  state.decisions[realIdx] = "skip";
  _saveDecisions();
  if (state.currentGroupIndex < state.filteredIndices.length - 1) reviewNav(1);
  else { renderReviewGroup(); _checkChunkEnd(); }
  updateReviewActionInfo();
}

function reviewMarkMove() {
  if (state.filteredIndices.length === 0) return;
  var realIdx = state.filteredIndices[state.currentGroupIndex];
  state.decisions[realIdx] = "move";
  _saveDecisions();
  if (state.currentGroupIndex < state.filteredIndices.length - 1) reviewNav(1);
  else { renderReviewGroup(); _checkChunkEnd(); }
  updateReviewActionInfo();
}

function reviewMarkDelete() {
  if (state.filteredIndices.length === 0) return;
  var realIdx = state.filteredIndices[state.currentGroupIndex];
  state.decisions[realIdx] = "delete";
  _saveDecisions();
  if (state.currentGroupIndex < state.filteredIndices.length - 1) reviewNav(1);
  else { renderReviewGroup(); _checkChunkEnd(); }
  updateReviewActionInfo();
}

function reviewBulkMove() {
  // Count only unreviewed groups
  var unreviewed = 0;
  for (var i = 0; i < state.filteredIndices.length; i++) {
    if (!state.decisions[state.filteredIndices[i]]) unreviewed++;
  }
  if (unreviewed === 0) {
    toast("All groups already reviewed");
    return;
  }
  showDialog(
    "Mark All Remaining",
    "Mark " + unreviewed + " unreviewed groups as duplicates? Your previous decisions will be kept.",
    "Mark Remaining", "btn-warning",
    function() {
      var marked = 0;
      for (var i = 0; i < state.filteredIndices.length; i++) {
        if (!state.decisions[state.filteredIndices[i]]) {
          state.decisions[state.filteredIndices[i]] = "move";
          marked++;
        }
      }
      renderReviewGroup();
      updateReviewActionInfo();
      _saveDecisionsNow();
      toast("Marked " + marked + " groups as duplicates");
    }
  );
}

function reviewBulkSkip() {
  var kept = 0;
  for (var i = 0; i < state.filteredIndices.length; i++) {
    if (!state.decisions[state.filteredIndices[i]]) {
      state.decisions[state.filteredIndices[i]] = "skip";
      kept++;
    }
  }
  renderReviewGroup();
  updateReviewActionInfo();
  _saveDecisionsNow();
  toast("Kept " + kept + " remaining groups");
}

function updateReviewActionInfo() {
  var reviewed = 0, moves = 0, deletes = 0, moveBytes = 0, deleteBytes = 0;
  for (var k in state.decisions) {
    reviewed++;
    if (state.decisions[k] === "move") {
      moves++;
      var g = state.groups[parseInt(k)];
      if (g) moveBytes += (g.reclaimable_bytes || 0);
    }
    if (state.decisions[k] === "delete") {
      deletes++;
      var g = state.groups[parseInt(k)];
      if (g) deleteBytes += (g.reclaimable_bytes || 0);
    }
  }
  document.getElementById("reviewActionInfo").textContent =
    "Reviewed: " + reviewed + " / " + state.groups.length +
    " | Move: " + moves + " | Delete: " + deletes +
    " | Space: " + formatBytes(moveBytes + deleteBytes);
}

function goToActions() {
  // Check if anything is marked
  var hasMoves = false, hasDeletes = false;
  for (var k in state.decisions) {
    if (state.decisions[k] === "move") hasMoves = true;
    if (state.decisions[k] === "delete") hasDeletes = true;
  }
  if (!hasMoves && !hasDeletes) {
    toast("No groups marked for move or delete yet", "warning");
    return;
  }
  navigate("actions");
}

/* ==================================================================
   ACTIONS
   ================================================================== */
function initActions() {
  var moveGroups = [];
  var deleteGroups = [];
  var moveBytes = 0;
  var deleteBytes = 0;

  for (var k in state.decisions) {
    var g = state.groups[parseInt(k)];
    if (!g) continue;
    if (state.decisions[k] === "move") {
      moveGroups.push(g);
      moveBytes += (g.reclaimable_bytes || 0);
    }
    if (state.decisions[k] === "delete") {
      deleteGroups.push(g);
      deleteBytes += (g.reclaimable_bytes || 0);
    }
  }

  // Count unique files (dedup across groups that may share files)
  var moveFileSet = {}, deleteFileSet = {};
  for (var i = 0; i < moveGroups.length; i++) {
    var dupes = moveGroups[i].duplicates || [];
    for (var j = 0; j < dupes.length; j++) moveFileSet[dupes[j]] = true;
  }
  for (var i = 0; i < deleteGroups.length; i++) {
    var dupes = deleteGroups[i].duplicates || [];
    for (var j = 0; j < dupes.length; j++) deleteFileSet[dupes[j]] = true;
  }
  var moveFileCount = Object.keys(moveFileSet).length;
  var deleteFileCount = Object.keys(deleteFileSet).length;

  document.getElementById("actMoveCount").textContent = moveFileCount;
  document.getElementById("actDeleteCount").textContent = deleteFileCount;
  document.getElementById("actSpaceCount").textContent = formatBytes(moveBytes + deleteBytes);

  var settings = state.settings || {};
  document.getElementById("actMoveDir").value = settings.move_destination || "";

  // Reset UI state
  document.getElementById("actionsSummaryCard").style.display = "block";
  document.getElementById("actionProgressBox").style.display = "none";
  document.getElementById("actionResultBox").style.display = "none";

  // Store for execution
  state._moveGroups = moveGroups;
  state._deleteGroups = deleteGroups;
}

function executeActions() {
  var moveGroups = state._moveGroups || [];
  var deleteGroups = state._deleteGroups || [];
  var moveDir = document.getElementById("actMoveDir").value.trim();

  if (moveGroups.length === 0 && deleteGroups.length === 0) {
    toast("Nothing to do", "warning");
    return;
  }

  var msg = "";
  if (moveGroups.length > 0) msg += "Move " + moveGroups.length + " groups to " + moveDir + ". ";
  if (deleteGroups.length > 0) msg += "Send " + deleteGroups.length + " groups to the Recycle Bin. ";
  msg += "Continue?";

  showDialog("Confirm Execution", msg, "Execute", "btn-danger", function() {
    _doExecute(moveGroups, deleteGroups, moveDir);
  });
}

function _doExecute(moveGroups, deleteGroups, moveDir) {
  document.getElementById("actionsSummaryCard").style.display = "none";
  document.getElementById("actionProgressBox").style.display = "block";
  document.getElementById("actionResultBox").style.display = "none";

  var reportFile = state.currentReport || null;
  var pendingOps = [];
  if (moveGroups.length > 0) {
    pendingOps.push(api("POST", "/api/action/move", { groups: moveGroups, destination: moveDir, report: reportFile }));
  }
  if (deleteGroups.length > 0) {
    pendingOps.push(api("POST", "/api/action/delete", { groups: deleteGroups, report: reportFile }));
  }

  Promise.all(pendingOps).then(function() {
    // Poll for progress via SSE
    var sse = new EventSource("/api/action/progress");
    sse.onmessage = function(e) {
      var d = JSON.parse(e.data);
      if (d.total > 0) {
        var pct = Math.round((d.current / d.total) * 100);
        document.getElementById("actProgressFill").style.width = pct + "%";
        document.getElementById("actProgressLeft").textContent =
          d.current + " / " + d.total;
      }
      if (d.status === "complete" || d.status === "error") {
        sse.close();
        showActionResult(d);
      }
    };
    sse.onerror = function() {
      sse.close();
      // Try fetching final state
      setTimeout(function() {
        showActionResult({ status: "complete", result: {} });
      }, 1000);
    };
  }).catch(function(err) {
    toast("Error starting action: " + err.message, "error");
  });
}

function showActionResult(d) {
  document.getElementById("actionProgressBox").style.display = "none";
  document.getElementById("actionResultBox").style.display = "block";

  var result = d.result || {};
  var moved = result.moved || 0;
  var deleted = result.deleted || 0;
  var skipped = result.skipped || 0;
  var errors = result.errors || [];

  document.getElementById("actResultTitle").textContent = "Actions Complete";
  var msg = "Moved: " + moved + " files. Deleted: " + deleted + " files.";
  if (skipped > 0) msg += " Skipped: " + skipped + " (already processed).";
  if (errors.length > 0) msg += " Errors: " + errors.length + ".";
  document.getElementById("actResultMsg").textContent = msg;

  if (errors.length > 0) {
    var html = '<h4 style="color:var(--danger);margin-bottom:8px;">Errors (' + errors.length + ')</h4>';
    html += '<div class="error-list">';
    for (var i = 0; i < errors.length; i++) {
      html += '<div class="error-item">' + escHtml(errors[i].path) + ': ' + escHtml(errors[i].error) + '</div>';
    }
    html += '</div>';
    document.getElementById("actResultErrors").innerHTML = html;
  } else {
    document.getElementById("actResultErrors").innerHTML = "";
  }

  // Show navigation options after actions complete
  if (state._reviewReturnTo === "wizard") {
    wizardState.completedSteps[3] = true;
  }
  document.getElementById("actResultErrors").innerHTML +=
    '<div style="margin-top:24px;padding:20px;border:1px solid var(--border);border-radius:var(--radius);text-align:center;">'
    + '<p style="color:var(--text);font-weight:600;margin-bottom:12px;">What would you like to do next?</p>'
    + '<div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap;">'
    + '<button class="btn btn-secondary" onclick="navigate(\'dashboard\')">Dashboard</button>'
    + '<button class="btn btn-secondary" onclick="_navToWizardStep(2)">Scan Again</button>'
    + '<button class="btn btn-secondary" onclick="_navToReview()">Review</button>'
    + '<button class="btn btn-secondary" onclick="navigate(\'finish\')">Finalize</button>'
    + '<button class="btn btn-secondary" onclick="_openRecycleBin()">Open Recycle Bin</button>'
    + '</div></div>';

  // Clear decisions
  state.decisions = {};
  toast("Actions completed successfully");
}

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
    var sse = new EventSource("/api/oddball/progress");
    sse.onmessage = function(e) {
      var d = JSON.parse(e.data);
      if (d.total > 0) {
        var pct = Math.round((d.current / d.total) * 100);
        document.getElementById("oddProgressFill").style.width = pct + "%";
        document.getElementById("oddProgressLeft").textContent = d.current + " / " + d.total;
      }
      if (d.status === "complete" || d.status === "error") {
        sse.close();
        showOddballResults(d);
      }
    };
    sse.onerror = function() { sse.close(); };
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

/* ==================================================================
   SETTINGS
   ================================================================== */
function initSettings() {
  api("GET", "/api/settings").then(function(settings) {
    state.settings = settings;
    document.getElementById("setThreshold").value = settings.threshold || 5;
    document.getElementById("setThresholdVal").textContent = settings.threshold || 5;
    document.getElementById("setMoveDir").value = settings.move_destination || "";
    document.getElementById("setKeepStrategy").value = settings.keep_strategy || "largest";
    document.getElementById("setPort").value = settings.port || 8787;
    document.getElementById("setBatchSize").value = settings.scan_batch_size || 2000;
    var exts = settings.extensions || [];
    document.getElementById("setExtensions").value = exts.join(", ");
  });
}

function saveSettings() {
  var extsStr = document.getElementById("setExtensions").value;
  var exts = extsStr.split(",").map(function(s) { return s.trim(); }).filter(function(s) { return s; });

  var oldPort = (state.settings && state.settings.port) || 8787;
  var newPort = parseInt(document.getElementById("setPort").value) || 8787;

  var data = {
    threshold: parseInt(document.getElementById("setThreshold").value) || 5,
    move_destination: document.getElementById("setMoveDir").value.trim(),
    keep_strategy: document.getElementById("setKeepStrategy").value,
    port: newPort,
    scan_batch_size: parseInt(document.getElementById("setBatchSize").value) || 2000,
    extensions: exts
  };

  api("POST", "/api/settings", data).then(function(saved) {
    state.settings = saved;
    if (newPort !== oldPort) {
      showDialog(
        "Port Changed",
        "The server port was changed from " + oldPort + " to " + newPort + ". Restart the server for this to take effect.",
        "Restart Now",
        "btn-primary",
        function() { restartServer(); }
      );
    } else {
      toast("Settings saved");
    }
  }).catch(function(err) {
    toast("Error saving settings: " + err.message, "error");
  });
}

/* ==================================================================
   KEYBOARD SHORTCUTS
   ================================================================== */
document.addEventListener("keydown", function(e) {
  // Only in review view
  if (parseHash().view !== "review") return;
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") return;

  if (e.key === "ArrowLeft") { e.preventDefault(); reviewNav(-1); }
  if (e.key === "ArrowRight") { e.preventDefault(); reviewNav(1); }
  if (e.key === "s" || e.key === "S") { e.preventDefault(); reviewMarkSkip(); }
  if (e.key === "m" || e.key === "M") { e.preventDefault(); reviewMarkMove(); }
  if (e.key === "d" || e.key === "D") { e.preventDefault(); reviewMarkDelete(); }
  if (e.key === "Escape") closeLightbox();
});

/* ==================================================================
   HTML ESCAPE HELPERS
   ================================================================== */
function escHtml(str) {
  if (!str) return "";
  var div = document.createElement("div");
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}

function escAttr(str) {
  if (!str) return "";
  return str.replace(/\\/g, "\\\\").replace(/&/g, "&amp;").replace(/'/g, "&#39;")
    .replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/* ==================================================================
   INIT
   ================================================================== */
route();
