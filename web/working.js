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

