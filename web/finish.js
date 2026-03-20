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
    : api("GET", "/api/staging/status").then(function(d) {
        if (d.staging_dir && d.source_dir) {
          _stagingSession = { source_dir: d.source_dir, staging_dir: d.staging_dir };
        }
      });

  p.then(function() {
    return api("GET", "/api/folders/status").then(function(data) {
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
      api("POST", "/api/staging/reset").catch(function() {});
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

