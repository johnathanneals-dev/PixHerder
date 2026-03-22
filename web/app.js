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
  settings: {},
  _currentView: null
};

// Shared wizard state (declared here for load-order safety, wizard.js overwrites)
var wizardState = wizardState || {
  currentStep: 1, completedSteps: {}, stagingDir: null,
  sourceDir: null, lastReport: null, dupesDir: null,
  browserReturnTo: "wizard"
};
var _stagingSession = _stagingSession || null;

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
function moveLightboxToKeepers() {
  if (!_lightboxFilePath) return;
  var filename = _lightboxFilePath.split("\\").pop();
  showDialog(
    "Move to Verified Keepers",
    "Move " + filename + " to Verified Keepers?",
    "Move to Keepers",
    "btn-primary",
    function() {
      var filePath = _lightboxFilePath;
      api("POST", "/api/browser/move-to-keepers", { path: filePath }).then(function(r) {
        if (r.success) {
          closeLightbox();
          toast("Moved to Verified Keepers");
          // Remove from browser grid
          var items = document.querySelectorAll(".browser-item");
          for (var i = 0; i < items.length; i++) {
            var img = items[i].querySelector("img");
            if (img && img.src.indexOf(encodeURIComponent(filePath)) !== -1) {
              items[i].remove();
              break;
            }
          }
          var countEl = document.getElementById("browserCount");
          var match = (countEl.textContent || "").match(/(\d+)/);
          if (match) {
            var newCount = parseInt(match[1]) - 1;
            countEl.textContent = newCount + " items";
            // Adjust page if on boundary (Issue 13)
            var itemsLeft = document.querySelectorAll(".browser-item").length;
            if (itemsLeft === 0 && newCount > 0 && browserState.currentPage > 2) {
              browserState.currentPage = browserState.currentPage - 1;
            }
          }
          // Refresh folder paths to update nav states (Issue 9)
          _refreshFolderPaths();
        } else {
          toast("Move failed: " + (r.error || "unknown error"), "error");
        }
      }).catch(function(err) {
        toast("Move failed: " + err.message, "error");
      });
    }
  );
}

function deleteLightboxFile() {
  if (!_lightboxFilePath) return;
  var filename = _lightboxFilePath.split("\\").pop();
  showDialog(
    "Recycle File",
    "Send " + filename + " to the Recycle Bin?",
    "Send to Recycle Bin",
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
            if (match) {
              var newCount = parseInt(match[1]) - 1;
              countEl.textContent = newCount + " items";
              // Adjust page if on boundary (Issue 13)
              var itemsLeft = document.querySelectorAll(".browser-item").length;
              if (itemsLeft === 0 && newCount > 0 && browserState.currentPage > 2) {
                browserState.currentPage = browserState.currentPage - 1;
              }
            }
            // Refresh folder paths to update nav states (Issue 10)
            _refreshFolderPaths();
          } else if (view === "review") {
            // Remove the deleted file from group data and re-render
            var realIdx = state.filteredIndices[state.currentGroupIndex];
            var group = state.groups[realIdx];
            if (group) {
              if (group.keep === deletedPath) {
                // Deleted the keep file -- promote first dupe to keep
                if (group.duplicates && group.duplicates.length > 0) {
                  group.keep = group.duplicates.shift();
                }
              } else if (group.duplicates) {
                group.duplicates = group.duplicates.filter(function(d) { return d !== deletedPath; });
              }
              group.files = 1 + (group.duplicates ? group.duplicates.length : 0);
              // If group has no files left, remove from filtered indices (Issue 17)
              if (group.files <= 0 || (!group.keep && (!group.duplicates || group.duplicates.length === 0))) {
                state.filteredIndices.splice(state.currentGroupIndex, 1);
                if (state.currentGroupIndex >= state.filteredIndices.length) {
                  state.currentGroupIndex = Math.max(0, state.filteredIndices.length - 1);
                }
              }
            }
            renderReviewGroup();
            updateReviewActionInfo();
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
  api("GET", "/api/activity?limit=100").then(function(data) {
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
    api("POST", "/api/activity/clear").then(function() {
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
  api("GET", "/api/browse-folders?path=" + encodeURIComponent(path))
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

// ---- API Helper ----
// Bridge method map: "METHOD /api/path" -> bridge method name
var _bridgeMap = {
  "GET /api/scans": "get_scans",
  "GET /api/settings": "get_settings",
  "GET /api/folders/status": "get_folders_status",
  "GET /api/activity": "get_activity",
  "GET /api/scan/check-resume": "check_resume",
  "GET /api/groups": "get_groups",
  "GET /api/decisions/load": "decisions_load",
  "GET /api/staging/status": "staging_status",
  "GET /api/browse": "browse",
  "GET /api/browse-folders": "browse_folders",
  "POST /api/scan/start": "scan_start",
  "POST /api/scan/cancel": "scan_cancel_op",
  "POST /api/action/move": "action_move",
  "POST /api/action/delete": "action_delete",
  "POST /api/action/rescue": "action_rescue",
  "POST /api/settings": "save_settings",
  "POST /api/oddball/run": "oddball_run",
  "POST /api/decisions/save": "decisions_save",
  "POST /api/scans/delete": "scans_delete",
  "POST /api/activity/clear": "clear_activity",
  "POST /api/staging/check": "staging_check",
  "POST /api/staging/start": "staging_start",
  "POST /api/staging/cancel": "staging_cancel_op",
  "POST /api/staging/syncback": "staging_syncback",
  "POST /api/staging/cleanup": "staging_cleanup",
  "POST /api/staging/reset": "staging_reset",
  "POST /api/staging/recycle-bin": "staging_recycle_bin",
  "POST /api/staging/restore": "staging_restore",
  "POST /api/staging/recycle": "staging_recycle",
  "POST /api/dupes/purge": "dupes_purge",
  "POST /api/dupes/promote": "dupes_promote",
  "POST /api/consolidate": "consolidate",
  "POST /api/browser/delete": "browser_delete",
  "POST /api/browser/delete-folder": "browser_delete_folder",
  "POST /api/browser/open-explorer": "open_explorer",
  "POST /api/browser/open-recycle-bin": "open_recycle_bin",
  "POST /api/browser/move-to-keepers": "move_to_keepers",
  "GET /api/recovery/status": "recovery_status",
  "GET /api/recovery/list": "recovery_list",
  "POST /api/recovery/restore": "recovery_restore",
  "POST /api/recovery/clear": "recovery_clear"
};

function _useBridge() {
  return !!(window.pywebview && window.pywebview.api);
}

function api(method, path, body) {
  if (_useBridge()) {
    var basePath = path.split("?")[0];
    var key = method + " " + basePath;
    var bridgeMethod = _bridgeMap[key];
    if (bridgeMethod === null) return Promise.resolve({status: "ok"});
    if (!bridgeMethod) return Promise.reject(new Error("Unknown API: " + key));
    var args = body || {};
    var qIdx = path.indexOf("?");
    if (qIdx >= 0) {
      path.substring(qIdx + 1).split("&").forEach(function(pair) {
        var kv = pair.split("=");
        if (kv.length === 2) args[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1]);
      });
    }
    return window.pywebview.api[bridgeMethod](args).then(function(r) {
      if (r && r.error) throw new Error(r.error);
      return r;
    });
  }
  // HTTP fetch (internal server for images + static files)
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
    if (!r.success) toast("Could not open Recycle Bin", "error");
  }).catch(function() { toast("Could not open Recycle Bin", "error"); });
}

var _scanContext = null; // null = full options, "dupes" or "keepers" = focused rescan

function _rescanFolder(type) {
  var path = _dashFolderPaths[type];
  if (!path) { toast("No folder to scan", "warning"); return; }
  _scanContext = type;
  document.getElementById("scanDir").value = path;
  navigate("scan-config");
}

function _navToWizardStep(step) {
  wizardState.currentStep = step;
  if (step === 1) wizardState.completedSteps = {};
  navigate("wizard");
}

function _navToReview() {
  // Always fetch fresh scan list to avoid referencing deleted reports (Issue 7)
  api("GET", "/api/scans").then(function(scans) {
    if (!scans || scans.length === 0) {
      toast("No scan results to review", "warning");
      return;
    }
    // Use lastReport if it still exists in the scan list
    if (state.lastReport) {
      for (var i = 0; i < scans.length; i++) {
        if (scans[i].filename === state.lastReport) {
          navigate("review", { report: state.lastReport });
          return;
        }
      }
    }
    // Fall back to most recent scan
    navigate("review", { report: scans[0].filename });
  }).catch(function() {
    toast("Could not load scan results", "error");
  });
}

function _updateNavStates() {
  // Grey out nav items based on current app state
  var migrate = document.getElementById("navMigrate");
  var scan = document.getElementById("navScan");
  var review = document.getElementById("navReview");
  var finalize = document.getElementById("navFinalize");

  // Migrate: disabled when files are in the system (must finish current session first)
  var hasAnyFiles = !!(_dashFolderPaths.staging || _dashFolderPaths.dupes || _dashFolderPaths.keepers);
  migrate.classList.toggle("disabled", hasAnyFiles);

  // Scan: available if staging session exists (files migrated)
  var hasStagingSession = !!(wizardState.stagingDir || (_stagingSession && _stagingSession.staging_dir));
  scan.classList.toggle("disabled", !hasStagingSession);

  // Review: available if there are scan results
  var hasScans = !!(state.lastReport || (state.scans && state.scans.length > 0));
  review.classList.toggle("disabled", !hasScans);

  // Finalize: available if staging has files
  var hasFiles = hasStagingSession;
  finalize.classList.toggle("disabled", !hasFiles);

  // Folder nav links: available if folders have files
  var navMyFiles = document.getElementById("navMyFiles");
  var navDupes = document.getElementById("navDupes");
  var navKeepers = document.getElementById("navKeepers");
  if (navMyFiles) navMyFiles.classList.toggle("disabled", !_dashFolderPaths.staging);
  if (navDupes) navDupes.classList.toggle("disabled", !_dashFolderPaths.dupes);
  if (navKeepers) navKeepers.classList.toggle("disabled", !_dashFolderPaths.keepers);
}

function route() {
  var parsed = parseHash();
  var view = parsed.view;
  var params = parsed.params;

  // View teardown: clear cached data when leaving certain views (Issue 34)
  var prevView = state._currentView || "";
  if (prevView === "review" && view !== "review" && view !== "actions") {
    // Don't clear when going to actions -- it needs groups and decisions
    state.groups = [];
    state.filteredIndices = [];
    state.currentGroupIndex = 0;
    state.currentReport = null;
  }
  if (prevView === "browser" && view !== "browser") {
    browserState.currentPage = 1;
  }
  if (prevView === "settings" && view !== "settings") {
    // Issue 33: invalidate cached settings so next use fetches fresh
    state.settings = null;
  }
  state._currentView = view;

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
  } else if (view === "browser") {
    if (browserState.type === "staging") navView = "browser-staging";
    else if (browserState.type === "dupes") navView = "browser-dupes";
    else if (browserState.type === "keepers") navView = "browser-keepers";
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
   INIT — called from index.html after all scripts load
   ================================================================== */
function _refreshFolderPaths() {
  // Keep folder paths up-to-date for navigation from any view
  api("GET", "/api/folders/status").then(function(data) {
    if (data.staging && data.staging.exists && data.staging.file_count > 0) {
      _dashFolderPaths.staging = data.staging.path;
    } else {
      _dashFolderPaths.staging = "";
    }
    if (data.dupes && data.dupes.exists && data.dupes.file_count > 0) {
      _dashFolderPaths.dupes = data.dupes.path;
    } else {
      _dashFolderPaths.dupes = "";
    }
    if (data.keepers && data.keepers.exists && data.keepers.file_count > 0) {
      _dashFolderPaths.keepers = data.keepers.path;
    } else {
      _dashFolderPaths.keepers = "";
    }
    _updateNavStates();
  }).catch(function() {});
}

// ---- Tooltips ----
var _tipTimer = null;
var _tipHelpSection = null;

function _initTooltips() {
  var tip = document.getElementById("tooltip");
  if (!tip) {
    // Create tooltip if not found in HTML
    tip = document.createElement("div");
    tip.id = "tooltip";
    document.body.appendChild(tip);
  }

  document.addEventListener("mouseover", function(e) {
    var el = e.target.closest("[data-tip]");
    if (!el) return;
    if (state.settings && state.settings.show_hints === false) return;

    clearTimeout(_tipTimer);
    _tipTimer = setTimeout(function() {
      var text = el.getAttribute("data-tip");
      var help = el.getAttribute("data-help");
      _tipHelpSection = help;

      var html = '<div class="tip-text">' + text + '</div>';
      if (help) {
        html += '<a class="tip-link" onclick="_tooltipHelp()">Learn more</a>';
      }
      tip.innerHTML = html;

      // Position tooltip
      var rect = el.getBoundingClientRect();
      var tipW = 280;
      var left = rect.left + (rect.width / 2) - (tipW / 2);
      if (left < 8) left = 8;
      if (left + tipW > window.innerWidth - 8) left = window.innerWidth - tipW - 8;

      tip.style.left = left + "px";
      tip.style.maxWidth = tipW + "px";

      // Show above or below based on space
      tip.style.display = "block";
      var tipH = tip.offsetHeight;
      if (rect.top > tipH + 12) {
        tip.style.top = (rect.top - tipH - 8) + "px";
      } else {
        tip.style.top = (rect.bottom + 8) + "px";
      }
    }, 500);
  });

  document.addEventListener("mouseout", function(e) {
    var el = e.target.closest("[data-tip]");
    if (!el) return;
    clearTimeout(_tipTimer);
    // Delay before hiding to allow moving cursor to tooltip for clicking
    setTimeout(function() {
      var tip = document.getElementById("tooltip");
      if (tip && !tip.matches(":hover")) {
        tip.style.display = "none";
      }
    }, 400);
  });

  // Also hide when leaving the tooltip itself
  tip.addEventListener("mouseleave", function() {
    tip.style.display = "none";
  });
}

function _tooltipHelp() {
  document.getElementById("tooltip").style.display = "none";
  if (_tipHelpSection) {
    // TODO: navigate to help section when built
    toast("Help section coming soon: " + _tipHelpSection);
  }
}

function _appInit() {
  _initTooltips();
  if (window.pywebview) {
    window.addEventListener("pywebviewready", function() {
      _refreshFolderPaths();
      route();
    });
  } else {
    _refreshFolderPaths();
    route();
  }
}
