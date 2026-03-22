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
  // Rearrange dialog buttons: Cancel left, Next Batch + Take a Break right
  var msg = document.getElementById("dialogMessage");
  msg.innerHTML = msg.textContent +
    '<div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:16px;">' +
    '<button class="btn btn-warning" onclick="closeDialog(); reviewBulkMove()">Mark All Remaining</button>' +
    '<button class="btn btn-secondary" onclick="closeDialog(); reviewBulkSkip()">Keep All Remaining</button>' +
    '</div>' +
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;border-top:1px solid var(--border);padding-top:14px;">' +
    '<button class="btn btn-ghost" onclick="closeDialog()">Cancel</button>' +
    '<div style="display:flex;gap:8px;">' +
    '<button class="btn btn-secondary" onclick="closeDialog(); _saveDecisionsNow(); navigate(\'dashboard\')">Take a Break</button>' +
    '<button class="btn btn-primary" onclick="closeDialog(); _showChunkCheckpoint_nextBatch()">Next Batch</button>' +
    '</div></div>';
  // Hide the default dialog buttons since we have custom layout
  document.getElementById("dialogConfirmBtn").style.display = "none";
  var cancelBtn = document.querySelector("#dialogOverlay > .dialog > .dialog-actions > .btn-secondary");
  if (cancelBtn) cancelBtn.style.display = "none";
}

function _showChunkCheckpoint_nextBatch() {
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
          if (!saved.decisions.hasOwnProperty(k)) continue;
          var idx = parseInt(k);
          // Validate decision still matches the group (Issue 16, 32)
          if (idx >= 0 && idx < state.groups.length) {
            state.decisions[k] = saved.decisions[k];
          }
          // Skip decisions for groups that no longer exist
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
  if (decision === "delete") html += ' <span class="decision-badge decision-delete">RECYCLE</span>';
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

function reviewBulkDelete() {
  var unreviewed = 0;
  for (var i = 0; i < state.filteredIndices.length; i++) {
    if (!state.decisions[state.filteredIndices[i]]) unreviewed++;
  }
  if (unreviewed === 0) {
    toast("All groups already reviewed");
    return;
  }
  showDialog(
    "Recycle All Remaining",
    "Send duplicates from " + unreviewed + " unreviewed groups to the Recycle Bin? Your previous decisions will be kept.",
    "Recycle Remaining", "btn-danger",
    function() {
      var marked = 0;
      for (var i = 0; i < state.filteredIndices.length; i++) {
        if (!state.decisions[state.filteredIndices[i]]) {
          state.decisions[state.filteredIndices[i]] = "delete";
          marked++;
        }
      }
      renderReviewGroup();
      updateReviewActionInfo();
      _saveDecisionsNow();
      toast("Marked " + marked + " groups for recycling");
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
  var reviewed = 0, moveFiles = 0, deleteFiles = 0, moveBytes = 0, deleteBytes = 0;
  for (var k in state.decisions) {
    reviewed++;
    var g = state.groups[parseInt(k)];
    var fileCount = g ? (g.duplicates ? g.duplicates.length : (g.files ? g.files - 1 : 0)) : 0;
    if (state.decisions[k] === "move") {
      moveFiles += fileCount;
      if (g) moveBytes += (g.reclaimable_bytes || 0);
    }
    if (state.decisions[k] === "delete") {
      deleteFiles += fileCount;
      if (g) deleteBytes += (g.reclaimable_bytes || 0);
    }
  }
  document.getElementById("reviewActionInfo").textContent =
    "Reviewed: " + reviewed + " / " + state.groups.length +
    " | Move: " + moveFiles + " files | Recycle: " + deleteFiles + " files" +
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
    toast("No groups marked for move or recycle yet", "warning");
    return;
  }
  navigate("actions");
}

