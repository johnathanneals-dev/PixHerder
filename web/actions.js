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

