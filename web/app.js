/* ==================================================================
   PixHerder SPA - State, Router, API, Views
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

function formatDate(timestamp) {
  if (!timestamp) return "";
  var d = new Date(timestamp * 1000);
  var y = d.getFullYear();
  var m = ("0" + (d.getMonth() + 1)).slice(-2);
  var day = ("0" + d.getDate()).slice(-2);
  return y + "-" + m + "-" + day;
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
  // Success toasts get a white checkmark
  if (type === "success") {
    el.textContent = "\u2713 " + message;
  } else {
    el.textContent = message;
  }
  container.appendChild(el);
  // All toasts blink (CSS handles it). Warning/error stay longer.
  var duration = (type === "warning" || type === "error") ? 7000 : 5000;
  setTimeout(function() { el.remove(); }, duration);
}

// ---- Confirm Dialog ----
var _dialogCallback = null;
function showDialog(title, message, confirmText, confirmClass, onConfirm) {
  // Capture original dialog-actions HTML on first call for restoration
  if (!_dialogActionsOriginal) {
    var actionsDiv = document.querySelector("#dialogOverlay > .dialog > .dialog-actions");
    if (actionsDiv) _dialogActionsOriginal = actionsDiv.innerHTML;
  }
  document.getElementById("dialogTitle").textContent = title;
  document.getElementById("dialogMessage").textContent = message;
  var btn = document.getElementById("dialogConfirmBtn");
  btn.textContent = confirmText || "Confirm";
  btn.className = "btn " + (confirmClass || "btn-danger");
  btn.style.display = "";
  var _cancelBtn = document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-danger");
  if (_cancelBtn) _cancelBtn.style.display = "";
  _dialogCallback = onConfirm;
  document.getElementById("dialogOverlay").classList.add("active");
}
var _dialogActionsOriginal = "";
function closeDialog() {
  document.getElementById("dialogOverlay").classList.remove("active");
  _dialogCallback = null;
  // Restore standard dialog-actions if they were replaced by custom dialogs
  var actionsDiv = document.querySelector("#dialogOverlay > .dialog > .dialog-actions");
  if (actionsDiv && _dialogActionsOriginal && actionsDiv.innerHTML !== _dialogActionsOriginal) {
    actionsDiv.innerHTML = _dialogActionsOriginal;
  }
}
function dialogConfirmAction() {
  var cb = _dialogCallback;
  closeDialog();
  if (cb) cb();
}

// ---- OneDrive Sync Prompts ----

/**
 * Check OneDrive status and show pause-sync prompt if needed.
 * Calls onContinue() when the user is ready to proceed (either after
 * acknowledging the prompt or if prompts are disabled/OneDrive not running).
 * @param {string} sourceDir - The directory being operated on
 * @param {string} operation - "migration" | "restore" | "finish"
 * @param {function} onContinue - Called when user is ready to proceed
 */
function checkOneDriveBeforeOperation(sourceDir, operation, onContinue) {
  try {
    api("POST", "/api/onedrive/status", { directory: sourceDir }).then(function(od) {
      if (!od || !od.is_onedrive || !od.running || !od.show_prompts) {
        onContinue();
        return;
      }
      try {
        _showOneDrivePauseDialog(operation, onContinue);
      } catch (e) {
        toast("OneDrive dialog error: " + e.message, "error");
        onContinue();
      }
    }).catch(function(err) {
      // If check fails, don't block the user
      onContinue();
    });
  } catch (e) {
    onContinue();
  }
}

function _showOneDrivePauseDialog(operation, onContinue) {
  // Capture original dialog-actions HTML for restoration
  if (!_dialogActionsOriginal) {
    var ad = document.querySelector("#dialogOverlay > .dialog > .dialog-actions");
    if (ad) _dialogActionsOriginal = ad.innerHTML;
  }
  var title = "Pause OneDrive Sync";
  var opLabel = operation === "migration" ? "importing files"
    : operation === "finish" ? "finishing up"
    : "sending files home";

  document.getElementById("dialogTitle").textContent = title;
  document.getElementById("dialogMessage").innerHTML =
    '<div style="margin-bottom:16px;">OneDrive is running and may interfere with ' + opLabel + '. ' +
    'For best results, pause syncing first.</div>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;">' +
      '<button class="btn btn-secondary" onclick="closeDialog(); _showOneDriveHowToPause(function() { (' + _escCb(onContinue) + ')(); })"' +
        ' data-tip="Step-by-step instructions to pause OneDrive">How to Pause</button>' +
      '<button class="btn btn-primary" onclick="closeDialog(); (' + _escCb(onContinue) + ')()"' +
        ' data-tip="Continue after pausing OneDrive sync">I\'ve Paused It</button>' +
    '</div>' +
    '<div style="border-top:1px solid var(--border);margin-top:14px;padding-top:12px;">' +
      '<div style="font-size:13px;color:var(--text-dim);line-height:1.6;">' +
        '<span style="color:#fff;font-weight:600;">How to Pause</span> shows step-by-step instructions.<br>' +
        '<span style="color:#fff;font-weight:600;">I\'ve Paused It</span> continues with ' + opLabel + '.' +
      '</div>' +
    '</div>' +
    '<div style="margin-top:14px;display:flex;gap:8px;align-items:center;">' +
      '<button class="btn btn-danger" onclick="closeDialog()"' +
        ' data-tip="Cancel and return to dashboard">Cancel</button>' +
      '<button class="btn btn-ghost" onclick="closeDialog(); (' + _escCb(onContinue) + ')()"' +
        ' style="font-size:12px;">Continue without pausing</button>' +
    '</div>';
  document.getElementById("dialogConfirmBtn").style.display = "none";
  // Hide the standard dialog Cancel button (replaced by inline Cancel)
  var stdCancel = document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-danger");
  if (stdCancel) stdCancel.style.display = "none";
  document.getElementById("dialogOverlay").classList.add("active");
}

// Store callbacks for use in inline onclick handlers
var _oneDriveCbStore = {};
var _oneDriveCbId = 0;
function _escCb(fn) {
  var id = "_odCb" + (++_oneDriveCbId);
  _oneDriveCbStore[id] = fn;
  return "_oneDriveCbStore['" + id + "']";
}

function _showOneDriveHowToPause(onContinue) {
  document.getElementById("dialogTitle").textContent = "How to Pause OneDrive";
  document.getElementById("dialogMessage").innerHTML =
    '<div style="font-size:14px;line-height:1.8;color:var(--text);">' +
      '<ol style="margin:0;padding-left:20px;">' +
        '<li>Look for the <strong>OneDrive cloud icon</strong> in your system tray (bottom-right of your taskbar, near the clock).</li>' +
        '<li>Click the icon to open the OneDrive menu.</li>' +
        '<li>Click the <strong>gear icon</strong> (Settings).</li>' +
        '<li>Select <strong>"Pause syncing"</strong> and choose <strong>2 hours</strong> or more.</li>' +
        '<li>The icon will show a pause symbol when syncing is paused.</li>' +
      '</ol>' +
    '</div>' +
    '<div style="border-top:1px solid var(--border);margin-top:14px;padding-top:12px;font-size:13px;color:var(--text-dim);line-height:1.6;">' +
      'You can resume syncing anytime by clicking the OneDrive icon and selecting <strong style="color:#fff;">Resume syncing</strong>. ' +
      'PixHerder will remind you when your operation is done.' +
    '</div>';
  document.getElementById("dialogConfirmBtn").style.display = "none";
  var cancelBtn = document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-danger");
  if (cancelBtn) cancelBtn.style.display = "none";
  var cbRef = _escCb(onContinue);
  var actionsDiv = document.querySelector("#dialogOverlay > .dialog > .dialog-actions");
  actionsDiv.innerHTML =
    '<button class="btn btn-danger" onclick="closeDialog()" style="margin-right:auto;">Cancel</button>' +
    '<button class="btn btn-primary" onclick="closeDialog(); (' + cbRef + ')()" data-tip="Continue with the operation">I\'ve Paused It</button>';
  document.getElementById("dialogOverlay").classList.add("active");
}

/**
 * Show an informational dialog after restoring files to OneDrive,
 * explaining the "Keep or Delete" dialog they may see.
 * @param {number} fileCount - Number of files restored
 * @param {function} onDismiss - Called when user closes the dialog
 */
function showOneDriveRestoreExplainer(fileCount, onDismiss) {
  if (!_dialogActionsOriginal) {
    var ad = document.querySelector("#dialogOverlay > .dialog > .dialog-actions");
    if (ad) _dialogActionsOriginal = ad.innerHTML;
  }
  document.getElementById("dialogTitle").textContent = "Files Sent Home";
  document.getElementById("dialogMessage").innerHTML =
    '<div style="margin-bottom:16px;">' +
      '<strong>' + fileCount.toLocaleString() + '</strong> files have been returned to your original folder.' +
    '</div>' +
    '<div style="background:var(--warning-bg);border:1px solid var(--warning);border-radius:var(--radius-sm);padding:14px;margin-bottom:14px;">' +
      '<div style="font-weight:600;color:var(--warning);margin-bottom:6px;">OneDrive may ask you about these files</div>' +
      '<div style="font-size:13px;color:var(--text);line-height:1.6;">' +
        'When OneDrive notices the changes, it may show a <strong>"Keep or Delete"</strong> prompt. ' +
        'If you see this:<br><br>' +
        '<strong style="color:var(--accent);">Choose "Keep"</strong> to keep your sorted files in place. ' +
        'This preserves all the work you just did.<br><br>' +
        'If you had OneDrive sync paused, you can resume it now.' +
      '</div>' +
    '</div>';
  document.getElementById("dialogConfirmBtn").style.display = "none";
  var cancelBtn = document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-danger");
  if (cancelBtn) cancelBtn.style.display = "none";
  var actionsDiv = document.querySelector("#dialogOverlay > .dialog > .dialog-actions");
  var cbRef = onDismiss ? _escCb(onDismiss) : null;
  actionsDiv.innerHTML =
    '<button class="btn btn-primary" onclick="closeDialog();' + (cbRef ? ' (' + cbRef + ')();' : '') + '" data-tip="Close this message">Got It</button>';
  document.getElementById("dialogOverlay").classList.add("active");
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
  // Show metadata if available
  var infoEl = document.getElementById("lightboxInfo");
  if (infoEl) {
    var info = (state._fileInfo || {})[_lightboxFilePath];
    if (info) {
      var parts = [];
      if (info.width && info.height) parts.push(info.width + " x " + info.height);
      if (info.size) parts.push(formatBytes(info.size));
      if (info.mtime) parts.push(formatDate(info.mtime));
      infoEl.textContent = parts.join("  |  ");
      infoEl.style.display = "block";
    } else {
      infoEl.style.display = "none";
    }
  }
}
function closeLightbox() {
  document.getElementById("lightbox").classList.remove("active");
  document.getElementById("lightboxImg").src = "";
  _lightboxFilePath = "";
  var infoEl = document.getElementById("lightboxInfo");
  if (infoEl) infoEl.style.display = "none";
}
function moveLightboxToKeepers() {
  if (!_lightboxFilePath) return;
  var filename = _lightboxFilePath.split("\\").pop();
  showDialog(
    "Move to Keepers",
    "Move " + filename + " to Keepers?",
    "Move to Keepers",
    "btn-primary",
    function() {
      var filePath = _lightboxFilePath;
      api("POST", "/api/browser/move-to-keepers", { path: filePath }).then(function(r) {
        if (r.success) {
          closeLightbox();
          toast("Moved to Keepers");
          // Remove from browser grid
          var items = document.querySelectorAll(".browser-item");
          for (var i = 0; i < items.length; i++) {
            var img = items[i].querySelector("img");
            if (img && img.src.indexOf(encodeURIComponent(filePath)) !== -1) {
              items[i].remove();
              break;
            }
          }
          var countEl = document.getElementById("browserCount2");
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
            var countEl = document.getElementById("browserCount2");
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
    '<div style="margin-top:12px;"><button class="btn btn-danger" onclick="closeDialog()">Cancel</button></div>';
  document.getElementById("dialogConfirmBtn").style.display = "none";
  document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-secondary").style.display = "none";
  document.getElementById("dialogOverlay").classList.add("active");

  document.getElementById("resumeResumeBtn").onclick = function() {
    closeDialog();
    document.getElementById("dialogConfirmBtn").style.display = "";
    var _cancelBtn = document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-danger");
  if (_cancelBtn) _cancelBtn.style.display = "";
    onResume();
  };
  document.getElementById("resumeFreshBtn").onclick = function() {
    closeDialog();
    document.getElementById("dialogConfirmBtn").style.display = "";
    var _cancelBtn = document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-danger");
  if (_cancelBtn) _cancelBtn.style.display = "";
    onFresh();
  };
}

// ---- Activity Log ----
function _loadScanList() {
  var list = document.getElementById("scanList");
  if (!list) return;
  api("GET", "/api/scans").then(function(scans) {
    if (!scans || scans.length === 0) {
      list.innerHTML = '<div class="empty-state"><p>No scans yet.</p></div>';
      return;
    }
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
      html += '<div class="scan-item" data-tip="' + s.total_groups + ' duplicate groups, ' + formatBytes(s.reclaimable_bytes || 0) + ' reclaimable">';
      html += '<div class="scan-item-info">';
      html += '<div class="scan-item-name">' + badge + " " + escHtml(s.filename) + '</div>';
      html += '<div class="scan-item-meta">' + escHtml(meta) + '</div>';
      html += '</div>';
      html += '<div class="scan-item-actions">';
      html += '<button class="btn btn-primary btn-sm" onclick="navigate(\'review\',{report:\'' + escAttr(s.filename) + '\'})" data-tip="Open this scan for review">Review</button>';
      if (s.source === "scan") {
        html += '<button class="btn btn-secondary btn-sm" onclick="deleteScan(\'' + escAttr(s.filename) + '\')" data-tip="Remove this scan from the list">Delete</button>';
      }
      html += '</div></div>';
    }
    list.innerHTML = html;
  }).catch(function() {
    list.innerHTML = '<div class="empty-state"><p>Could not load scans.</p></div>';
  });
}

function loadActivity() {
  _loadScanList();
  api("GET", "/api/logs/status").then(function(data) {
    _updateLoggingUI(data.enabled);
  }).catch(function() {});
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
var _cachedPicturesPath = "";

function _quickFill(which) {
  api("GET", "/api/settings").then(function(s) {
    var home = s.default_pictures_path || "";
    var userProfile = home.replace(/\\OneDrive\\Pictures$/i, "")
                         .replace(/\\Pictures$/i, "");
    var path = "";
    if (which === "onedrive") path = home;
    else if (which === "pictures") path = userProfile + "\\Pictures";
    else if (which === "desktop") path = userProfile + "\\Desktop";
    if (path) {
      document.getElementById("wizSourceDir").value = path;
      // Quick check if the path has image files
      api("POST", "/api/staging/check", { directory: path }).then(function(r) {
        var count = r.source_count;
        if (typeof count === "object") count = count[0] || 0;
        if (count === 0) {
          toast("No image files found in " + path.split("\\").pop(), "warning");
        }
      }).catch(function() {});
    }
  });
}

function openFolderPicker(targetInputId) {
  _folderPickerTarget = targetInputId;
  var startPath = document.getElementById(targetInputId).value.trim();
  // Show loading state immediately
  document.getElementById("folderPickerList").innerHTML =
    '<div style="padding:12px;color:var(--text-dim);">Loading folders...</div>';
  document.getElementById("folderPickerOverlay").classList.add("active");
  if (!startPath) {
    // Start at drive list so user can navigate to any location
    _loadFolderPicker("__drives__");
  } else {
    _loadFolderPicker(startPath);
  }
}

function closeFolderPicker() {
  document.getElementById("folderPickerOverlay").classList.remove("active");
  _folderPickerTarget = null;
}

function selectFolder() {
  if (_folderPickerPath === "My Computer") {
    toast("Please select a folder, not the drive list", "warning");
    return;
  }
  if (_folderPickerTarget && _folderPickerPath) {
    document.getElementById(_folderPickerTarget).value = _folderPickerPath;
    // Check for image files and show feedback
    var path = _folderPickerPath;
    api("POST", "/api/staging/check", { directory: path }).then(function(r) {
      var count = r.source_count;
      if (typeof count === "object") count = count[0] || 0;
      if (count === 0) {
        toast("No image files found in " + path.split("\\").pop(), "warning");
      } else {
        toast(count.toLocaleString() + " image" + (count !== 1 ? "s" : "") + " found", "success");
      }
    }).catch(function() {});
  }
  closeFolderPicker();
}

var _folderPickerLoading = false;
var _cachedDriveList = null;

function _warmUpDriveList() {
  api("GET", "/api/browse-folders?path=__drives__")
    .then(function(data) { _cachedDriveList = data; })
    .catch(function() {});
}

function _loadFolderPicker(path) {
  // Debounce: ignore rapid clicks (double-click fires onclick twice)
  if (_folderPickerLoading) return;
  _folderPickerLoading = true;
  setTimeout(function() { _folderPickerLoading = false; }, 300);

  // Use cached drive list for instant display
  if (path === "__drives__" && _cachedDriveList) {
    _renderFolderPicker(_cachedDriveList);
    return;
  }

  api("GET", "/api/browse-folders?path=" + encodeURIComponent(path))
    .then(function(data) { _renderFolderPicker(data); })
    .catch(function() {
      document.getElementById("folderPickerList").innerHTML =
        '<div style="padding:12px;color:var(--danger);">Could not load folder</div>';
    });
}

function _renderFolderPicker(data) {
  _folderPickerPath = data.path;

  // Breadcrumb with clickable path segments
  var bcEl = document.getElementById("folderPickerBreadcrumb");
  if (data.is_drives) {
    bcEl.innerHTML = "My Computer";
  } else {
    var crumbs = '<span style="cursor:pointer;text-decoration:underline;color:var(--accent);" ' +
      'onclick="_loadFolderPicker(\'__drives__\')" ' +
      'title="Show all drives">My Computer</span>';
    // Split path into clickable segments: C:\Users\foo -> [C:, Users, foo]
    var parts = data.path.split("\\");
    var built = "";
    for (var ci = 0; ci < parts.length; ci++) {
      if (!parts[ci]) continue;
      built += (ci === 0) ? parts[ci] : ("\\" + parts[ci]);
      // Add trailing backslash for drive root (C: -> C:\)
      var segPath = (ci === 0 && parts[ci].length === 2 && parts[ci][1] === ":") ? built + "\\" : built;
      if (ci < parts.length - 1) {
        crumbs += ' <span style="color:var(--text-dim);">&rsaquo;</span> ' +
          '<span style="cursor:pointer;text-decoration:underline;color:var(--accent);" ' +
          'onclick="_loadFolderPicker(\'' + escAttr(segPath) + '\')">' + parts[ci] + '</span>';
      } else {
        // Current folder -- not clickable
        crumbs += ' <span style="color:var(--text-dim);">&rsaquo;</span> ' + parts[ci];
      }
    }
    bcEl.innerHTML = crumbs;
  }

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
    var full = data.is_drives ? name : (data.path + "\\" + name);
    var icon = data.is_drives ? "&#128187;" : "&#128193;";
    html += '<div style="padding:6px 10px;cursor:pointer;border-radius:4px;" ' +
      'onmouseover="this.style.background=\'var(--surface-2)\'" ' +
      'onmouseout="this.style.background=\'none\'" ' +
      'onclick="_loadFolderPicker(\'' + escAttr(full) + '\')">' +
      '<span style="margin-right:6px;">' + icon + '</span> ' + name + '</div>';
  }
  if (!data.folders.length && !data.parent) {
    html = '<div style="padding:12px;color:var(--text-dim);">No subfolders found</div>';
  }
  document.getElementById("folderPickerList").innerHTML = html;
}

// ---- API Helper ----
// Bridge method map: "METHOD /api/path" -> bridge method name
var _bridgeMap = {
  "GET /api/app/state": "app_state",
  "POST /api/app/reset": "reset_state",
  "POST /api/state/validate": "validate_state",
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
  "POST /api/onedrive/status": "onedrive_status",
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
  "POST /api/recovery/clear": "recovery_clear",
  "POST /api/recycle-source-dupes": "recycle_source_dupes",
  "POST /api/move-dupes-to-folder": "move_dupes_to_folder",
  "GET /api/logs/status": "logs_status",
  "POST /api/logs/enable": "logs_enable",
  "POST /api/logs/disable": "logs_disable",
  "POST /api/logs/read": "logs_read",
  "POST /api/logs/clear": "logs_clear"
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

function _navToScan() {
  // Go directly to scan config, skip wizard Step 1
  api("GET", "/api/folders/status").then(function(data) {
    if (data.staging && data.staging.exists && data.staging.file_count > 0) {
      _scanContext = "staging";
      document.getElementById("scanDir").value = data.staging.path;
      navigate("scan-config");
    } else {
      toast("No files in Staging to scan", "warning");
    }
  }).catch(function() {
    toast("Could not check folder status", "error");
  });
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

  // Scan: available if staging has files or session exists
  var hasStagingSession = !!(wizardState.stagingDir || (_stagingSession && _stagingSession.staging_dir) || _dashFolderPaths.staging);
  scan.classList.toggle("disabled", !hasStagingSession);

  // Review: available if there are scan results
  var hasScans = !!(state.lastReport || (state.scans && state.scans.length > 0));
  review.classList.toggle("disabled", !hasScans);

  // Finalize: available if dupes or keepers have files (not just staging alone)
  var hasDupesOrKeepers = !!(_dashFolderPaths.dupes || _dashFolderPaths.keepers);
  finalize.classList.toggle("disabled", !hasDupesOrKeepers);

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
    var navBar = document.getElementById("browserNavBar");
    if (navBar) navBar.style.display = "none";
  }
  if (prevView === "settings" && view !== "settings") {
    // Issue 33: mark stale so initSettings refetches, but keep values for route() toggles
    state._settingsStale = true;
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
  _refreshFolderPaths();  // Always refresh nav from filesystem

  // Apply workflow mode to UI (nav visibility, forced settings)
  applyModeToUI(getCurrentMode());
  // Progressive nav: Easy mode shows links as workflow progresses
  updateEasyModeNav();

  // Show hints bar when hints enabled, with contextual flow text
  var _curMode = getCurrentMode();
  var hintsOn = !state.settings || state.settings.show_hints !== false;
  // Easy mode forces hints on regardless of setting
  if (_curMode === "easy") hintsOn = true;
  // Keyboard shortcuts: only in review, and only if setting is on
  var kbdOn = view === "review" && (!state.settings || state.settings.show_kbd_shortcuts !== false);
  // If kbd shortcuts should show, force hints bar visible even if hints are off
  if (kbdOn) hintsOn = true;
  document.getElementById("hintsBar").style.display = hintsOn ? "block" : "none";
  document.getElementById("kbdShortcuts").style.display = kbdOn ? "inline-flex" : "none";
  var _hbt = document.getElementById("hintsBarText");
  if (_hbt && view !== "dashboard") {
    // Check for mode-specific hint text first
    var modeHint = getModeHintText(_curMode, view);
    if (modeHint !== null) {
      _hbt.textContent = modeHint;
    } else {
      // Default hints (hybrid mode or fallback)
      if (view === "review") _hbt.textContent = "Click images to toggle keep/dupe. Use the action bar to apply decisions.";
      else if (view === "scan-config") _hbt.textContent = "Choose a scan mode and threshold, then click Start Scan.";
      else if (view === "scan-progress") _hbt.textContent = "Scanning in progress. You can cancel at any time.";
      else if (view === "finish") _hbt.textContent = "Review the summary, then click Finish Now to send files home and clean up.";
      else if (view === "actions") _hbt.textContent = "Review pending operations, then click Execute to apply.";
      else if (view === "browser") _hbt.textContent = "Browse your files. Click any image to zoom.";
      else if (view === "settings") _hbt.textContent = "Adjust your preferences. Click Save Settings when done.";
      else if (view === "wizard") _hbt.textContent = "Follow the steps to find and clean up duplicate images.";
      else _hbt.textContent = "";
    }
  }

  // Toggle explanation text visibility (Settings view is always verbose)
  var explainOn = view === "settings" || !state.settings || state.settings.show_explanations !== false;
  var explEls = document.querySelectorAll(".explanation-text");
  for (var ei = 0; ei < explEls.length; ei++) {
    explEls[ei].style.display = explainOn ? "" : "none";
  }

  // Activate view
  var viewEl = document.getElementById("view-" + view);
  if (viewEl) {
    viewEl.classList.add("active");
  } else {
    document.getElementById("view-dashboard").classList.add("active");
    view = "dashboard";
  }

  // On fresh page load, redirect to mode-appropriate landing
  if (!_appNavigated) {
    var _landing = getModeLandingView(getCurrentMode());
    if (view !== _landing && view !== "settings" && view !== "activity" && view !== "help") {
      navigate(_landing);
      return;
    }
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
  else if (view === "logs") initLogs();
  else if (view === "settings") initSettings();
  else if (view === "autonomous") initAutonomous();
}

window.onhashchange = route;

// Prevent mouse back/forward buttons from navigating (WebView2 default behavior)
document.addEventListener("mousedown", function(e) {
  if (e.button === 3 || e.button === 4) e.preventDefault();
}, true);

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
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") return;

  // Escape: close dialog first, then lightbox
  if (e.key === "Escape") {
    if (document.getElementById("dialogOverlay").classList.contains("active")) {
      closeDialog();
    } else {
      closeLightbox();
    }
    return;
  }

  // Only in review view
  if (parseHash().view !== "review") return;

  if (e.key === "ArrowLeft") { e.preventDefault(); reviewNav(-1); }
  if (e.key === "ArrowRight") { e.preventDefault(); reviewNav(1); }
  if (e.key === "s" || e.key === "S") { e.preventDefault(); reviewMarkSkip(); }
  if (e.key === "m" || e.key === "M") { e.preventDefault(); reviewMarkMove(); }
  if (e.key === "d" || e.key === "D") { e.preventDefault(); reviewMarkDelete(); }
  if (e.key === "e" || e.key === "E") { e.preventDefault(); goToActions(); }
  if (e.key === " ") {
    e.preventDefault();
    var lb = document.getElementById("lightbox");
    if (lb.classList.contains("active")) {
      closeLightbox();
    } else if (state.filteredIndices && state.filteredIndices.length > 0) {
      var realIdx = state.filteredIndices[state.currentGroupIndex];
      var group = state.groups[realIdx];
      if (group && group.keep) {
        openLightbox(encodeURIComponent(group.keep));
      }
    }
  }
});

// ---- Persistent Logging Toggle (Ctrl+Shift+F5) ----
document.addEventListener("keydown", function(e) {
  if (e.ctrlKey && e.shiftKey && e.key === "F5") {
    e.preventDefault();
    _togglePersistentLogging();
  }
  // Ctrl+Shift+F6: navigate to console (only from console/dashboard, not mid-operation)
  if (e.ctrlKey && e.shiftKey && e.key === "F6") {
    e.preventDefault();
    var curView = parseHash().view;
    if (curView === "logs") {
      navigate("dashboard");
    } else if (curView === "dashboard" || curView === "activity" || curView === "settings") {
      navigate("logs");
    } else {
      toast("Navigate to Dashboard first", "warning");
    }
  }
  // Ctrl+Shift+F7: toggle debug mode (pywebview devtools)
  if (e.ctrlKey && e.shiftKey && e.key === "F7") {
    e.preventDefault();
    _toggleDebugMode();
  }
});

function _toggleDebugMode() {
  api("GET", "/api/settings").then(function(settings) {
    var current = settings.debug_mode || false;
    var newVal = !current;
    return api("POST", "/api/settings", Object.assign({}, settings, { debug_mode: newVal }));
  }).then(function(saved) {
    var enabled = saved.debug_mode;
    var badge = document.getElementById("debugModeBadge");
    if (badge) badge.style.display = enabled ? "inline" : "none";
    if (enabled) {
      toast("Debug mode enabled. Restart PixHerder to see DevTools window.");
    } else {
      toast("Debug mode disabled. Takes effect on next restart.");
    }
  });
}

function _togglePersistentLogging() {
  api("GET", "/api/settings").then(function(settings) {
    var current = settings.persistent_logging || false;
    var newVal = !current;
    return api("POST", "/api/settings", Object.assign({}, settings, { persistent_logging: newVal }));
  }).then(function(saved) {
    var enabled = saved.persistent_logging;
    if (enabled) {
      api("POST", "/api/logs/enable").then(function() {
        toast("Persistent logging enabled (Ctrl+Shift+F5 to disable)");
        _updatePersistentLogBadge(true);
      });
    } else {
      api("POST", "/api/logs/disable").then(function() {
        toast("Persistent logging disabled");
        _updatePersistentLogBadge(false);
      });
    }
  });
}

function _updatePersistentLogBadge(enabled) {
  var badge = document.getElementById("persistentLogBadge");
  if (badge) badge.style.display = enabled ? "inline" : "none";
}

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
// ---- Centralized State ----
// Single source of truth: derives app state from filesystem, not in-memory caches.

function getAppState() {
  return api("GET", "/api/app/state");
}

function resetAppState() {
  // Clear backend in-memory progress dicts, then validate artifacts
  api("POST", "/api/app/reset").then(function() {
    return api("POST", "/api/state/validate");
  }).catch(function() {});
  // Clear frontend state
  _stagingSession = null;
  wizardState.currentStep = 1;
  wizardState.completedSteps = {};
  wizardState.stagingDir = null;
  wizardState.sourceDir = null;
  wizardState.lastReport = null;
  state.groups = [];
  state.filteredIndices = [];
  state.currentGroupIndex = 0;
  state.decisions = {};
  state.currentReport = null;
  _dashFolderPaths = { staging: "", dupes: "", keepers: "" };
  _sessionScanCompleted = false;
}

function _refreshFolderPaths() {
  // Keep folder paths up-to-date for navigation from any view
  getAppState().then(function(appState) {
    var f = appState.folders;
    _dashFolderPaths.staging = (f.staging.exists && f.staging.count > 0) ? f.staging.path : "";
    _dashFolderPaths.dupes = (f.dupes.exists && f.dupes.count > 0) ? f.dupes.path : "";
    _dashFolderPaths.keepers = (f.keepers.exists && f.keepers.count > 0) ? f.keepers.path : "";
    // Update session from filesystem too
    if (appState.session.active) {
      _stagingSession = { source_dir: appState.session.source_dir, staging_dir: appState.session.staging_dir };
    }
    _updateNavStates();
  }).catch(function() {});
}

// ---- Logging ----
var _currentLogType = "debug";

function _toggleLogging(enable) {
  if (enable) {
    showDialog(
      "Enable Verbose Logging",
      "Verbose logging captures detailed debug information for every operation. This may slow down scans and file operations while enabled. Logging resets to off when PixHerder is restarted.",
      "Enable Logging", "btn-warning",
      function() {
        api("POST", "/api/logs/enable").then(function() {
          toast("Verbose logging enabled");
          _updateLoggingUI(true);
        });
      }
    );
    // If user cancels dialog, uncheck the box
    var cb = document.getElementById("setEnableLogging");
    if (cb) cb.checked = false;
  } else {
    api("POST", "/api/logs/disable").then(function() {
      toast("Logging disabled");
      _updateLoggingUI(false);
    });
  }
}

function _updateLoggingUI(enabled) {
  var cb = document.getElementById("setEnableLogging");
  if (cb) cb.checked = enabled;
  var btn = document.getElementById("viewLogsBtn");
  var hint = document.getElementById("viewLogsHint");
  if (btn) btn.disabled = !enabled;
  if (hint) hint.style.display = enabled ? "none" : "inline";
}

function initLogs() {
  _loadLogContent(_currentLogType);
}

function _loadLogContent(type) {
  _currentLogType = type;
  var pre = document.getElementById("logContent");
  pre.textContent = "Loading...";
  api("POST", "/api/logs/read", { type: type, lines: 500 }).then(function(data) {
    pre.textContent = data.content || "(empty)";
    pre.scrollTop = pre.scrollHeight;
  }).catch(function(err) {
    pre.textContent = "Error: " + err.message;
  });
}

function _refreshLogs() {
  _loadLogContent(_currentLogType);
}

function _clearLogs() {
  showDialog("Clear Logs", "Delete all debug and error log files?", "Clear", "btn-danger", function() {
    api("POST", "/api/logs/clear").then(function() {
      toast("Logs cleared");
      _loadLogContent(_currentLogType);
    });
  });
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
    // Settings view and data-tip-always elements always show tooltips
    if (state.settings && state.settings.show_tooltips === false
        && state._currentView !== "settings"
        && !el.hasAttribute("data-tip-always")) return;

    clearTimeout(_tipTimer);
    _tipTimer = setTimeout(function() {
      var text = el.getAttribute("data-tip");
      var help = el.getAttribute("data-help");
      _tipHelpSection = help;

      var html = '<div class="tip-text">' + text + '</div>';
      if (help) {
        html += '<a class="tip-link" id="tipLearnMore">Learn more</a>';
      }
      tip.innerHTML = html;

      // Attach click handler to Learn more link
      var learnMore = document.getElementById("tipLearnMore");
      if (learnMore) {
        learnMore.onclick = function(e) {
          e.stopPropagation();
          _tooltipHelp();
        };
      }

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

  // Hide tooltip on mousedown (fires before click, prevents blocking)
  document.addEventListener("mousedown", function() {
    tip.style.display = "none";
    clearTimeout(_tipTimer);
  }, true);

  // Handle clicks inside tooltip (for Learn more link)
  tip.addEventListener("click", function(e) {
    var link = e.target.closest(".tip-link");
    if (link) {
      e.preventDefault();
      e.stopPropagation();
      _tooltipHelp();
    }
  });
}

function _tooltipHelp() {
  var section = _tipHelpSection;
  var tip = document.getElementById("tooltip");
  if (tip) tip.style.display = "none";
  toast("Help section coming soon: " + (section || "general"));
}

function _checkPersistentLogging() {
  api("GET", "/api/settings").then(function(s) {
    if (s && s.persistent_logging) {
      // Show badge immediately from settings, don't wait for logs/enable
      _updatePersistentLogBadge(true);
      _updateLoggingUI(true);
      api("POST", "/api/logs/enable").catch(function() {});
    }
    if (s && s.debug_mode) {
      var badge = document.getElementById("debugModeBadge");
      if (badge) badge.style.display = "inline";
    }
  }).catch(function() {
    setTimeout(function() {
      api("GET", "/api/settings").then(function(s) {
        if (s && s.persistent_logging) {
          _updatePersistentLogBadge(true);
          _updateLoggingUI(true);
          api("POST", "/api/logs/enable").catch(function() {});
        }
        if (s && s.debug_mode) {
          var badge = document.getElementById("debugModeBadge");
          if (badge) badge.style.display = "inline";
        }
      }).catch(function() {});
    }, 1000);
  });
}

function _updateStatusBarPort() {
  api("GET", "/api/settings").then(function(s) {
    var port = s.port || 8787;
    var el = document.getElementById("statusBarPort");
    if (el) el.textContent = "127.0.0.1:" + port;
    _updateStatusBarToggles(s);
  }).catch(function() {});
}

function _updateStatusBarToggles(settings) {
  var el = document.getElementById("statusBarToggles");
  if (!el) return;
  var s = settings || state.settings || {};
  var tooltips = s.show_tooltips !== false;
  var hints = s.show_hints !== false;
  var parts = [];
  if (tooltips) parts.push("Tooltips enabled");
  if (hints) parts.push("Hints enabled");
  if (parts.length > 0) {
    el.innerHTML = '<span style="color:var(--accent);font-style:italic;">Enable/Disable in Settings</span>' +
      ' &nbsp;&middot;&nbsp; ' +
      '<span style="color:var(--accent);">' + parts.join(' &middot; ') + '</span>' +
      ' &middot; ';
  } else {
    el.textContent = "";
  }
}

function _appInit() {
  _initTooltips();
  _updateStatusBarPort();

  // Note: right-click context menus and Ctrl+V/C/X/A are enabled natively
  // via debug=True in pixherder_app.py (WebView2 ties these to debug mode)

  function _postValidateInit() {
    _refreshFolderPaths();
    _checkPersistentLogging();
    _warmUpDriveList();
    // Load settings to check workflow mode and cache pictures path
    api("GET", "/api/settings").then(function(s) {
      state.settings = s;
      _cachedPicturesPath = s.default_pictures_path || "";
      if (!s.workflow_mode) {
        // First launch: show tour then mode selector
        var _afterModeSelect = function(mode) {
          s.workflow_mode = mode;
          s.show_welcome = false;  // Auto-disable after first selection
          s.show_tour = false;
          api("POST", "/api/settings", s).then(function(saved) {
            state.settings = saved;
            route();
          }).catch(function() {
            state.settings.workflow_mode = mode;
            route();
          });
        };
        showTour(function() {
          showModeSelector(_afterModeSelect);
        });
      } else if (s.show_welcome !== false) {
        // Returning user with show_welcome enabled
        var _modeSelectCb = function(mode) {
          s.workflow_mode = mode;
          api("POST", "/api/settings", s).then(function(saved) {
            state.settings = saved;
            route();
          }).catch(function() {
            state.settings.workflow_mode = mode;
            route();
          });
        };
        if (s.show_tour !== false) {
          // Tour + welcome screen
          showTour(function() { showModeSelector(_modeSelectCb); });
        } else {
          // Welcome screen only (no tour)
          showModeSelector(_modeSelectCb);
        }
      } else {
        route();
      }
    }).catch(function() {
      route();
    });
  }

  if (window.pywebview) {
    window.addEventListener("pywebviewready", function() {
      // Validate state before anything else -- clean up stale artifacts
      api("POST", "/api/state/validate").then(function(r) {
        var total = (r.manifests_removed || 0) + (r.orphan_staging_removed || 0) +
                    (r.stale_decisions_removed || 0) + (r.stale_checkpoints_removed || 0) +
                    (r.recovery_slots_cleared || 0);
        if (total > 0) console.log("State validator cleaned " + total + " artifacts");
      }).catch(function() {}).finally(function() {
        _postValidateInit();
      });
    });
  } else {
    _postValidateInit();
  }
}
