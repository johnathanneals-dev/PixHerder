/* ==================================================================
   SETTINGS
   ================================================================== */
function initSettings() {
  api("GET", "/api/settings").then(function(settings) {
    state.settings = settings;
    state._settingsStale = false;
    // Workflow mode
    var modeEl = document.getElementById("setWorkflowMode");
    if (modeEl) {
      modeEl.value = settings.workflow_mode || "hybrid";
      onModeChange(modeEl);
    }
    document.getElementById("setThreshold").value = settings.threshold || 5;
    document.getElementById("setThresholdVal").textContent = settings.threshold || 5;
    document.getElementById("setMoveDir").value = settings.move_destination || "";
    document.getElementById("setKeepStrategy").value = settings.keep_strategy || "largest";
    document.getElementById("setPort").value = settings.port || 8787;
    document.getElementById("setBatchSize").value = settings.scan_batch_size || 2000;
    document.getElementById("setShowHints").checked = settings.show_hints !== false;
    document.getElementById("setShowTooltips").checked = settings.show_tooltips !== false;
    document.getElementById("setShowExplanations").checked = settings.show_explanations !== false;
    document.getElementById("setShowOneDrivePrompts").checked = settings.show_onedrive_prompts !== false;
    document.getElementById("setShowWelcome").checked = settings.show_welcome !== false;
    document.getElementById("setOpenFullscreen").checked = settings.open_fullscreen !== false;
    var exts = settings.extensions || [];
    document.getElementById("setExtensions").value = exts.join(", ");
  });
  // Check logging status (session-only, not in saved settings)
  api("GET", "/api/logs/status").then(function(data) {
    _updateLoggingUI(data.enabled);
  }).catch(function() {});
}

function saveSettings() {
  var extsStr = document.getElementById("setExtensions").value;
  var exts = extsStr.split(",").map(function(s) { return s.trim(); }).filter(function(s) { return s; });

  var oldPort = (state.settings && state.settings.port) || 8787;
  var newPort = parseInt(document.getElementById("setPort").value) || 8787;

  // Preserve settings not shown in the UI (persistent_logging, debug_mode)
  var preserved = state.settings || {};
  var data = {
    workflow_mode: document.getElementById("setWorkflowMode").value || "hybrid",
    threshold: parseInt(document.getElementById("setThreshold").value) || 5,
    move_destination: document.getElementById("setMoveDir").value.trim(),
    keep_strategy: document.getElementById("setKeepStrategy").value,
    port: newPort,
    scan_batch_size: parseInt(document.getElementById("setBatchSize").value) || 2000,
    show_hints: document.getElementById("setShowHints").checked,
    show_tooltips: document.getElementById("setShowTooltips").checked,
    show_explanations: document.getElementById("setShowExplanations").checked,
    show_onedrive_prompts: document.getElementById("setShowOneDrivePrompts").checked,
    show_welcome: document.getElementById("setShowWelcome").checked,
    open_fullscreen: document.getElementById("setOpenFullscreen").checked,
    persistent_logging: preserved.persistent_logging || false,
    debug_mode: preserved.debug_mode || false,
    extensions: exts
  };

  api("POST", "/api/settings", data).then(function(saved) {
    state.settings = saved;
    _updateStatusBarToggles(saved);
    if (newPort !== oldPort) {
      toast("Port changed. Close and reopen PixHerder for this to take effect.");
    } else {
      toast("Settings saved");
    }
  }).catch(function(err) {
    toast("Error saving settings: " + err.message, "error");
  });
}

