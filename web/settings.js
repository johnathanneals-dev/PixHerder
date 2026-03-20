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

