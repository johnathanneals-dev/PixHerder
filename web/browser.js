// ---- File Browser ----
var browserState = {
  rootPath: null,
  currentPath: null,
  currentPage: 1,
  hasMore: false,
  loading: false,
  type: null,
  returnTo: "wizard"
};
var _browserObserver = null;

function openBrowser(type) {
  if (type === "staging") {
    browserState.rootPath = wizardState.stagingDir;
    browserState.type = "staging";
  } else if (type === "dupes") {
    browserState.rootPath = wizardState.dupesDir || (state.settings && state.settings.move_destination) || "";
    browserState.type = "dupes";
  }
  browserState.currentPath = browserState.rootPath;
  browserState.currentPage = 1;
  browserState.returnTo = "wizard";
  navigate("browser");
}

function initBrowser() {
  if (!browserState.rootPath) {
    // No folder in memory (page refresh/restart) -- go to dashboard
    navigate("dashboard");
    return;
  }
  // Validate root path still exists via API before loading (Issue 12)
  api("GET", "/api/browse?path=" + encodeURIComponent(browserState.rootPath) + "&page=1&page_size=1").then(function(data) {
    if (data.error) {
      toast("Folder no longer available", "warning");
      navigate("dashboard");
      return;
    }
    _initBrowserContent();
  }).catch(function() {
    toast("Folder no longer available", "warning");
    navigate("dashboard");
  });
}

function _initBrowserContent() {
  // Show the nav bar browser row
  var navBar = document.getElementById("browserNavBar");
  if (navBar) navBar.style.display = "flex";

  var backLabel = browserState.returnTo === "dashboard" ? "Back to Dashboard" : "Back to Finalize";
  var backBtn = document.getElementById("browserBackBtn2");
  if (backBtn) backBtn.innerHTML = "&larr; " + backLabel;

  // Show promote button only when browsing dupes
  var promoteBtn = document.getElementById("browserPromoteBtn2");
  if (promoteBtn) promoteBtn.style.display = (browserState.type === "dupes") ? "" : "none";
  browserState.currentPage = 1;
  document.getElementById("browserGrid").innerHTML = "";

  // Delegated click handler for folder items and folder delete buttons
  var grid = document.getElementById("browserGrid");
  grid.onclick = function(ev) {
    // Check if delete button was clicked
    var delBtn = ev.target.closest(".browser-folder-del");
    if (delBtn && delBtn.dataset.delpath) {
      ev.stopPropagation();
      deleteFolderItem(delBtn.dataset.delpath);
      return;
    }
    var item = ev.target.closest(".browser-folder");
    if (item && item.dataset.path) {
      browserNavigate(item.dataset.path);
    }
  };

  browserLoadPage(true);
  // Set up infinite scroll
  if (_browserObserver) _browserObserver.disconnect();
  _browserObserver = new IntersectionObserver(function(entries) {
    if (entries[0].isIntersecting && browserState.hasMore && !browserState.loading) {
      browserLoadPage(false);
    }
  });
  _browserObserver.observe(document.getElementById("browserSentinel"));
}

function browserLoadPage(replace) {
  browserState.loading = true;
  document.getElementById("browserLoading").style.display = "block";
  var sort = document.getElementById("browserSort2").value || "name";
  var url = "/api/browse?path=" + encodeURIComponent(browserState.currentPath)
    + "&page=" + browserState.currentPage
    + "&page_size=50&sort=" + sort;

  api("GET", url).then(function(data) {
    browserState.loading = false;
    document.getElementById("browserLoading").style.display = "none";

    if (data.error) {
      document.getElementById("browserGrid").innerHTML =
        '<div class="browser-loading">Error: ' + escHtml(data.error) + '</div>';
      return;
    }

    browserState.hasMore = data.has_more;

    // Update breadcrumb
    buildBreadcrumb(data.path);
    document.getElementById("browserCount2").textContent =
      data.total + " items";

    // Render items
    var html = "";
    for (var i = 0; i < data.entries.length; i++) {
      var e = data.entries[i];
      if (e.is_dir) {
        html += '<div class="browser-item browser-folder" data-path="' + escHtml(e.path) + '">'
          + '<div class="browser-thumb"><div class="browser-folder-icon">&#128193;</div></div>'
          + '<div class="browser-meta"><div class="browser-name">' + escHtml(e.name) + '</div>'
          + '<div class="browser-size">Folder</div></div>'
          + '<button class="browser-folder-del" data-delpath="' + escHtml(e.path) + '" title="Delete folder">&#10005;</button>'
          + '</div>';
      } else {
        var imgUrl = "/api/image?path=" + encodeURIComponent(e.path);
        var sizeStr = e.size > 1048576 ? (e.size / 1048576).toFixed(1) + " MB"
          : Math.round(e.size / 1024) + " KB";
        html += '<div class="browser-item" onclick="openLightbox(\'' + encodeURIComponent(e.path) + '\')">'
          + '<div class="browser-thumb"><img src="' + imgUrl + '" loading="lazy" alt=""></div>'
          + '<div class="browser-meta"><div class="browser-name">' + escHtml(e.name) + '</div>'
          + '<div class="browser-size">' + sizeStr + '</div></div></div>';
      }
    }

    if (replace) {
      document.getElementById("browserGrid").innerHTML = html;
    } else {
      document.getElementById("browserGrid").innerHTML += html;
    }
    browserState.currentPage++;

    if (data.total === 0) {
      var isRoot = browserState.currentPath === browserState.rootPath;
      var emptyHtml = '<div class="browser-loading">This folder is empty.';
      if (!isRoot) {
        emptyHtml += '<br><button class="btn btn-danger" style="margin-top:12px;" '
          + 'onclick="deleteCurrentFolder()">Delete This Folder</button>';
      }
      emptyHtml += '</div>';
      document.getElementById("browserGrid").innerHTML = emptyHtml;
    }
  }).catch(function(err) {
    browserState.loading = false;
    document.getElementById("browserLoading").style.display = "none";
    document.getElementById("browserGrid").innerHTML =
      '<div class="browser-loading">Error: ' + escHtml(err.message || "Failed to load") + '</div>';
  });
}

function browserNavigate(path) {
  browserState.currentPath = path;
  browserState.currentPage = 1;
  document.getElementById("browserGrid").innerHTML = "";
  browserLoadPage(true);
}

function browserRefresh() {
  // Reload from page 1 to get consistent state (Issue 11)
  // but preserve current scroll position intent by keeping currentPage
  var savedPage = browserState.currentPage;
  browserState.currentPage = 1;
  document.getElementById("browserGrid").innerHTML = "";
  browserLoadPage(true);
  // Note: infinite scroll will reload subsequent pages as user scrolls
}

function buildBreadcrumb(fullPath) {
  var root = browserState.rootPath.replace(/\\/g, "/");
  var current = fullPath.replace(/\\/g, "/");
  var rootLabel = browserState.type === "staging" ? "My Files" : "Removed Duplicates";

  var html = '<span class="browser-crumb" data-nav="' + escHtml(browserState.rootPath) + '">'
    + escHtml(rootLabel) + '</span>';

  if (current !== root && current.indexOf(root) === 0) {
    var rel = current.substring(root.length).replace(/^\//, "");
    var parts = rel.split("/");
    var built = browserState.rootPath;
    for (var i = 0; i < parts.length; i++) {
      if (!parts[i]) continue;
      built = built + "\\" + parts[i];
      html += '<span class="browser-crumb-sep">/</span>'
        + '<span class="browser-crumb" data-nav="' + escHtml(built) + '">'
        + escHtml(parts[i]) + '</span>';
    }
  }

  var bc = document.getElementById("browserBreadcrumb");
  // Hide breadcrumb at root level (top nav already shows location)
  var isAtRoot = (current === root || current.replace(/[\\/]+$/, "") === root.replace(/[\\/]+$/, ""));
  bc.style.display = isAtRoot ? "none" : "";
  bc.innerHTML = html;
  bc.onclick = function(ev) {
    var crumb = ev.target.closest(".browser-crumb");
    if (crumb && crumb.dataset.nav) {
      browserNavigate(crumb.dataset.nav);
    }
  };
}

function closeBrowser() {
  if (_browserObserver) _browserObserver.disconnect();
  navigate(browserState.returnTo || "wizard");
}

function deleteCurrentFolder() {
  var dir = browserState.currentPath;
  if (!dir || dir === browserState.rootPath) return;
  var folderName = dir.split("\\").pop();
  showDialog(
    "Delete Folder",
    "Delete the empty folder \"" + folderName + "\"?",
    "Delete",
    "btn-danger",
    function() {
      api("POST", "/api/browser/delete-folder", { path: dir }).then(function(r) {
        if (r.success) {
          // Navigate to parent
          var parent = dir.substring(0, dir.lastIndexOf("\\"));
          if (!parent || parent.length < browserState.rootPath.length) {
            parent = browserState.rootPath;
          }
          browserNavigate(parent);
          toast("Folder deleted");
          _refreshFolderPaths();
        } else {
          toast("Delete failed: " + (r.error || "Unknown error"), "error");
        }
      }).catch(function(err) {
        toast("Delete failed: " + err.message, "error");
      });
    }
  );
}

function deleteFolderItem(path) {
  var folderName = path.split("\\").pop();
  showDialog(
    "Delete Folder",
    "Send the folder \"" + folderName + "\" and all its contents to the Recycle Bin?",
    "Delete",
    "btn-danger",
    function() {
      api("POST", "/api/browser/delete-folder", { path: path }).then(function(r) {
        if (r.success) {
          // Remove from grid
          var items = document.querySelectorAll(".browser-folder");
          for (var i = 0; i < items.length; i++) {
            if (items[i].dataset.path === path) {
              items[i].remove();
              break;
            }
          }
          var countEl = document.getElementById("browserCount2");
          var match = (countEl.textContent || "").match(/(\d+)/);
          if (match) countEl.textContent = (parseInt(match[1]) - 1) + " items";
          toast("Folder deleted");
          _refreshFolderPaths();
        } else {
          toast("Delete failed: " + (r.error || "Unknown error"), "error");
        }
      }).catch(function(err) {
        toast("Delete failed: " + err.message, "error");
      });
    }
  );
}

function openInExplorer() {
  var dir = browserState.currentPath || browserState.rootPath;
  if (!dir) return;
  api("POST", "/api/browser/open-explorer", { path: dir }).then(function() {
    // Explorer opens natively in pywebview
  }).catch(function(err) {
    toast("Could not open Explorer: " + err.message, "error");
  });
}

// Auto-refresh browser when tab regains focus (catches changes made in Explorer)
document.addEventListener("visibilitychange", function() {
  if (!document.hidden && parseHash().view === "browser" && browserState.rootPath) {
    browserRefresh();
  }
});

function scanFromBrowser() {
  var dir = browserState.rootPath;
  if (!dir) return;
  // Set scan context based on current browser folder
  _scanContext = browserState.type || null;
  document.getElementById("scanDir").value = dir;
  navigate("scan-config");
}

// escAttr is defined near end of script -- handles HTML entity escaping

