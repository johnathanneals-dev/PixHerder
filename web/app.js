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
