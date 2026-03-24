// ---- Working View (blocking progress) ----
var _workingConfig = { title: "", message: "", callback: null, destination: "dashboard" };
var _workingTimeout = null;

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

  // Timeout escape: if operation hangs, let user return to dashboard
  _workingTimeout = setTimeout(function() {
    var spinner = document.getElementById("workingSpinner");
    if (spinner && spinner.style.display !== "none") {
      document.getElementById("workingStatus").innerHTML =
        'This is taking longer than expected. ' +
        '<button class="btn btn-warning btn-sm" onclick="_workingEscape()" style="margin-top:8px;">Return to Dashboard</button>';
    }
  }, 120000);

  if (_workingConfig.callback) {
    _workingConfig.callback(function(resultTitle, resultMsg) {
      // Called by the operation when done
      clearTimeout(_workingTimeout);
      document.getElementById("workingSpinner").style.display = "none";
      document.getElementById("workingComplete").style.display = "block";
      document.getElementById("workingCompleteTitle").textContent = resultTitle || "Done";
      document.getElementById("workingCompleteMsg").textContent = resultMsg || "";
    });
  }
}

function _workingContinue() {
  clearTimeout(_workingTimeout);
  // Refresh folder paths after working operation completes (Issue 23)
  _refreshFolderPaths();
  navigate(_workingConfig.destination);
}

function _workingEscape() {
  clearTimeout(_workingTimeout);
  toast("Operation may still be running in the background", "warning");
  navigate("dashboard");
}

