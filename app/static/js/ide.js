/* Code Review Agent — web IDE frontend */
(function () {
  "use strict";

  var conf = window.IDE_CONF || {};
  var owner = conf.owner, repo = conf.repo, mode = conf.mode;
  var prNumber = conf.prNumber || null;
  var monacoBase =
    (conf.monacoBase || "/static/vendor/monaco") + "/vs";

  var state = {
    branch: null,
    files: [],            // [{path, sha, size, lintable, status?}]
    prs: [],
    prHeadSha: null,
    problems: {},         // path -> [ {file,line,column,end_line,end_column,severity,rule,message,linter,source} ]
    tabs: {},             // path -> {model, markers, decorations}
    tabOrder: [],
    active: null,
    filters: { error: true, warning: true, suggestion: true },
    cleared: false,
    loading: false,
  };

  var editor = null;
  var els = {};

  /* ------------------------------------------------------------ */
  /* Monaco bootstrap                                              */
  /* ------------------------------------------------------------ */
  var requireMonaco = window.require || null;

  window.MonacoEnvironment = {
    getWorkerUrl: function () {
      return (
        "data:text/javascript;charset=utf-8," +
        encodeURIComponent(
          "self.MonacoEnvironment={baseUrl:" + JSON.stringify(monacoBase) + "};" +
            "importScripts(" + JSON.stringify(monacoBase + "/base/worker/workerMain.js") + ");"
        )
      );
    },
  };

  function langForPath(path) {
    var ext = path.split(".").pop().toLowerCase();
    switch (ext) {
      case "py": return "python";
      case "js": case "mjs": case "cjs": return "javascript";
      case "jsx": return "javascriptreact";
      case "ts": return "typescript";
      case "tsx": return "typescriptreact";
      case "java": return "java";
      case "json": return "json";
      case "md": return "markdown";
      case "html": return "html";
      case "css": return "css";
      case "sh": case "bash": return "shell";
      default: return "plaintext";
    }
  }

  function apiCall(url, opts) {
    return fetch(url, opts).then(function (resp) {
      if (resp.status === 401) {
        window.location.href = "/login";
        throw new Error("Not authenticated");
      }
      return resp.json().then(function (data) {
        if (!resp.ok) {
          throw new Error(data.error || ("HTTP " + resp.status));
        }
        return data;
      });
    });
  }

  function qs(params) {
    var out = [];
    Object.keys(params || {}).forEach(function (k) {
      out.push(encodeURIComponent(k) + "=" + encodeURIComponent(params[k]));
    });
    return out.length ? "?" + out.join("&") : "";
  }

  /* ------------------------------------------------------------ */
  /* Toast + helpers                                               */
  /* ------------------------------------------------------------ */
  function toast(msg) {
    var t = els.toast;
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(t._t);
    t._t = setTimeout(function () { t.hidden = true; }, 2600);
  }

  function severityClass(sev) {
    if (sev === "critical" || sev === "error") return "sev-error";
    if (sev === "warning") return "sev-warning";
    return "sev-info";
  }

  function chipSeverity(sev) {
    if (sev === "critical" || sev === "error") return "error";
    if (sev === "warning") return "warning";
    return "suggestion";
  }

  function severityThreshold(sev) {
    return chipSeverity(sev);
  }

  /* ------------------------------------------------------------ */
  /* Load meta: info, PRs                                          */
  /* ------------------------------------------------------------ */
  function loadInfo() {
    return apiCall("/api/ide/info" + qs({ owner: owner, repo: repo })).then(function (info) {
      state.branch = info.default_branch;
      return info;
    });
  }

  function loadPRs() {
    return apiCall("/api/ide/prs" + qs({ owner: owner, repo: repo })).then(function (data) {
      state.prs = data.prs || [];
      return state.prs;
    });
  }

  /* ------------------------------------------------------------ */
  /* Populate selects                                              */
  /* ------------------------------------------------------------ */
  function fillBranches() {
    els.branchSelect.hidden = false;
    els.branchSelect.innerHTML = "";
    els.branchSelect.appendChild(new Option("Branch: " + state.branch, state.branch));
  }

  function fillPRs() {
    els.prSelect.hidden = false;
    els.prSelect.innerHTML = "";
    if (!state.prs.length) {
      els.prSelect.appendChild(new Option("No open PRs", ""));
      return;
    }
    state.prs.forEach(function (p) {
      els.prSelect.appendChild(
        new Option("#" + p.number + " — " + p.title, String(p.number))
      );
    });
  }

  /* ------------------------------------------------------------ */
  /* Tree loading                                                  */
  /* ------------------------------------------------------------ */
  function loadTree() {
    return apiCall(
      "/api/ide/tree" + qs({ owner: owner, repo: repo, branch: state.branch })
    ).then(function (data) {
      state.branch = data.branch || state.branch;
      state.files = data.files || [];
      renderTree();
    });
  }

  function loadPRFiles() {
    return apiCall(
      "/api/ide/pr-files" + qs({ owner: owner, repo: repo, pr_number: prNumber })
    ).then(function (data) {
      state.files = (data.files || []).map(function (f) {
        var isLint = /\.(py|js|jsx|mjs|cjs|ts|tsx|java)$/i.test(f.path);
        return {
          path: f.path,
          sha: "",
          size: 0,
          lintable: isLint,
          status: f.status,
        };
      });
      state.files.sort(function (a, b) {
        return a.path.localeCompare(b.path);
      });
      renderTree();
      return state.files;
    });
  }

  /* ------------------------------------------------------------ */
  /* Tree rendering                                                */
  /* ------------------------------------------------------------ */
  function buildNodes(files) {
    var root = { children: {} };
    files.forEach(function (f) {
      var parts = f.path.split("/");
      var node = root;
      parts.forEach(function (part, i) {
        var isFile = i === parts.length - 1;
        var key = part;
        if (!node.children[key]) {
          node.children[key] = {
            name: part,
            path: parts.slice(0, i + 1).join("/"),
            isFile: isFile,
            file: isFile ? f : null,
            children: {},
            expanded: false,
          };
        }
        node = node.children[key];
      });
    });
    // Mark top-level dirs expanded.
    Object.keys(root.children).forEach(function (k) {
      if (!root.children[k].isFile) root.children[k].expanded = true;
    });
    return root;
  }

  function renderTree() {
    var root = buildNodes(state.files);
    var body = els.treeBody;
    body.innerHTML = "";
    Object.keys(root.children)
      .sort(function (a, b) { return dirRank(root.children[a]) - dirRank(root.children[b]) || a.localeCompare(b); })
      .forEach(function (k) {
        body.appendChild(renderNode(root.children[k], 0));
      });
  }

  function dirRank(node) {
    return node.isFile ? 1 : 0;
  }

  function renderNode(node, depth) {
    var li = document.createElement("li");
    li.className = "tree-item" + (node.isFile && node.file ? "" : " tree-dir");
    li.style.paddingLeft = 8 + depth * 14 + "px";

    if (!node.isFile) {
      var chev = document.createElement("span");
      chev.className = "tree-chevron" + (node.expanded ? " open" : "");
      chev.textContent = node.expanded ? "▼" : "▶";
      chev.addEventListener("click", function (ev) {
        ev.stopPropagation();
        node.expanded = !node.expanded;
        renderTree();
      });
      li.appendChild(chev);

      var dirLabel = document.createElement("span");
      dirLabel.className = "tree-label tree-label-dir";
      dirLabel.textContent = node.name;
      dirLabel.addEventListener("click", function () {
        node.expanded = !node.expanded;
        renderTree();
      });
      li.appendChild(dirLabel);

      if (node.expanded) {
        Object.keys(node.children)
          .sort(function (a, b) { return dirRank(node.children[a]) - dirRank(node.children[b]) || a.localeCompare(b); })
          .forEach(function (k) {
            li.appendChild(renderNode(node.children[k], depth + 1));
          });
      }
      return li;
    }

    var fileLabel = document.createElement("span");
    fileLabel.className = "tree-label tree-label-file";
    if (node.file.status) {
      fileLabel.textContent = node.name + "  [" + node.file.status + "]";
    } else {
      fileLabel.textContent = node.name;
    }
    fileLabel.addEventListener("click", function () {
      openFile(node.file.path);
    });
    li.appendChild(fileLabel);
    return li;
  }

  /* ------------------------------------------------------------ */
  /* Tabs                                                          */
  /* ------------------------------------------------------------ */
  function openFile(path) {
    if (!state.tabs[path]) {
      var file = state.files.find(function (f) { return f.path === path; });
      if (!file) return;
      var model = null;
      // browser-level check avoids refetch when we already have a model
      loadContent(path, file).then(function (content) {
        model = editor.createModel(content, langForPath(path));
        state.tabs[path] = { model: model, file: file };
        state.tabOrder.push(path);
        setActive(path);
        renderTabs();
        if (file.lintable) lintFile(path);
        if (mode === "pr") loadPRProblems();
        saveSession();
      });
      return;
    }
    setActive(path);
    renderTabs();
  }

  function loadContent(path, file) {
    if (file.sha || mode === "branch") {
      return apiCall(
        "/api/ide/content" +
          qs({
            owner: owner,
            repo: repo,
            path: path,
            ref: mode === "pr" ? state.prHeadSha : state.branch,
            blob: file.sha,
            size: file.size,
          })
      ).then(function (data) { return data.content; });
    }
    // PR mode: fetch via ref alone
    return apiCall(
      "/api/ide/content" + qs({ owner: owner, repo: repo, path: path, ref: state.prHeadSha, blob: "", size: "" })
    ).then(function (data) { return data.content; });
  }

  function setActive(path) {
    state.active = path;
    if (state.tabs[path]) {
      editor.setModel(state.tabs[path].model);
      applyMarkers(path);
    }
  }

  function closeTab(path, ev) {
    ev.stopPropagation();
    var t = state.tabs[path];
    if (t && t.model) t.model.dispose();
    delete state.tabs[path];
    state.tabOrder = state.tabOrder.filter(function (p) { return p !== path; });
    delete state.problems[path];
    renderTabBar();
    if (state.active === path) {
      if (state.tabOrder.length) {
        setActive(state.tabOrder[state.tabOrder.length - 1]);
      } else {
        editor.setModel(null);
        state.active = null;
      }
    }
    renderTabs();
    renderConsole();
    saveSession();
  }

  function renderTabs() {
    var bar = els.tabs;
    bar.innerHTML = "";
    state.tabOrder.forEach(function (path) {
      var tab = document.createElement("div");
      tab.className = "ide-tab" + (path === state.active ? " active" : "");
      tab.textContent = path.split("/").pop();
      tab.title = path;
      tab.addEventListener("click", function () {
        setActive(path);
        renderTabs();
      });
      var close = document.createElement("span");
      close.className = "tab-close";
      close.textContent = "×";
      close.addEventListener("click", function (ev) { closeTab(path, ev); });
      tab.appendChild(close);
      bar.appendChild(tab);
    });
    els.lintBtn.disabled = !state.active;
    els.refactorBtn.disabled = !state.active;
  }

  function renderTabBar() { renderTabs(); }

  /* ------------------------------------------------------------ */
  /* Linting                                                       */
  /* ------------------------------------------------------------ */
  function lintFile(path) {
    if (!state.tabs[path]) return;
    var file = state.tabs[path].file;
    var ref = mode === "pr" ? state.prHeadSha : state.branch;
    clearProblems(path);
    setStatus("Linting " + path.split("/").pop() + "…");
    apiCall("/api/ide/lint" + qs({ owner: owner, repo: repo, path: path, sha: ref }))
      .then(function (data) {
        (data.findings || []).forEach(function (f) {
          addProblem(path, f, "linter");
        });
        applyMarkers(path);
        renderConsole();
        setStatus("");
      })
      .catch(function (err) {
        setStatus(err.message);
        showErr(path, err.message);
      });
  }

  function runRefactor() {
    if (!state.active) return;
    var path = state.active;
    var ref = mode === "pr" ? state.prHeadSha : state.branch;
    setStatus("Running AI refactor…");
    els.refactorBtn.disabled = true;
    apiCall(
      "/api/ide/refactor" + qs({}),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owner: owner, repo: repo, path: path, sha: ref }),
      }
    )
      .then(function (data) {
        (data.suggestions || []).forEach(function (s) {
          addProblem(path, { linter: "ai", rule: "refactor", message: s.message, severity: s.severity, line: s.line }, "ai");
        });
        applyMarkers(path);
        renderConsole();
        setStatus("");
        els.refactorBtn.disabled = false;
        if ((data.suggestions || []).length) toast("AI suggestions added");
      })
      .catch(function (err) {
        setStatus(err.message);
        els.refactorBtn.disabled = false;
      });
  }

  function loadPRProblems() {
    apiCall(
      "/api/ide/pr-findings" + qs({ owner: owner, repo: repo, pr_number: prNumber })
    ).then(function (data) {
      var files = data.files || {};
      Object.keys(files).forEach(function (path) {
        (files[path] || []).forEach(function (row) {
          addProblem(path, row, row.source === "ai" ? "ai" : "pr");
        });
      });
      Object.keys(state.tabs).forEach(function (p) { applyMarkers(p); });
      renderConsole();
    }).catch(function () { /* ignore */ });
  }

  function runPRAnalysis() {
    if (!state.prHeadSha) return;
    setStatus("Analyzing PR…");
    apiCall(
      "/api/ide/pr-analyze" + qs({}),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          owner: owner, repo: repo, pr_number: prNumber, head_sha: state.prHeadSha,
        }),
      }
    )
      .then(function () {
        setStatus("");
        toast("PR analysis complete");
        loadPRProblems();
      })
      .catch(function (err) { setStatus(err.message); });
    }

  /* ------------------------------------------------------------ */
  /* Problems management                                           */
  /* ------------------------------------------------------------ */
  function addProblem(path, f, source) {
    var list = (state.problems[path] = state.problems[path] || []);
    list.push({
      file: path,
      line: f.line != null ? f.line : 1,
      column: f.column,
      end_line: f.end_line,
      end_column: f.end_column,
      severity: f.severity || "warning",
      rule: f.rule || "",
      message: f.message || "",
      linter: f.linter || source,
      source: source,
    });
  }

  function clearProblems(path) {
    if (path != null && state.problems[path]) delete state.problems[path];
    else if (path == null) state.problems = {};
  }

  function applyMarkers(path) {
    var t = state.tabs[path];
    if (!t || !t.model) return;
    var problems = state.problems[path] || [];
    var markerSeverity = {
      critical: monaco.MarkerSeverity.Error,
      error: monaco.MarkerSeverity.Error,
      warning: monaco.MarkerSeverity.Warning,
      suggestion: monaco.MarkerSeverity.Info,
    };
    var markers = [];
    var decorations = [];
    problems.forEach(function (p) {
      if (state.cleared) return;
      if (!state.filters[severityThreshold(p.severity)]) return;
      markers.push({
        severity: markerSeverity[p.severity] || monaco.MarkerSeverity.Info,
        message: "[" + p.linter + "/" + p.rule + "] " + p.message,
        startLineNumber: p.line,
        startColumn: p.column || 1,
        endLineNumber: p.end_line || p.line,
        endColumn: p.end_column || (p.column || 1) + 1,
      });
    });
    monaco.editor.setModelMarkers(t.model, "cri", markers);
    t.markers = markers;
    t.decorations = editor.deltaDecorations(t.decorations || [], decorations);
  }

  function flashLine(path, line) {
    var t = state.tabs[path];
    if (!t) return;
    var deco = {
      range: new monaco.Range(line, 1, line, 1),
      options: { isWholeLine: true, className: "flash-line" },
    };
    var handle = editor.deltaDecorations([], [deco]);
    setTimeout(function () { editor.deltaDecorations(handle, []); }, 900);
  }

  /* ------------------------------------------------------------ */
  /* Console                                                       */
  /* ------------------------------------------------------------ */
  function resolveProblemSource(path) {
    return state.problems;
  }

  function renderConsole() {
    var body = els.consoleBody;
    body.innerHTML = "";
    var all = [];
    Object.keys(state.problems || {}).forEach(function (path) {
      (state.problems[path] || []).forEach(function (p) { all.push(p); });
    });

    var filtered = all.filter(function (p) {
      if (state.cleared) return false;
      return state.filters[severityThreshold(p.severity)];
    });

    countAll(all);
    var grouped = {};
    filtered.forEach(function (p) {
      (grouped[p.file] = grouped[p.file] || []).push(p);
    });

    var files = Object.keys(grouped).sort();
    if (!files.length) {
      var empty = document.createElement("div");
      empty.className = "console-empty";
      empty.textContent = state.cleared ? "Problems hidden." : "No problems.";
      body.appendChild(empty);
      return;
    }

    files.forEach(function (path) {
      var section = document.createElement("div");
      section.className = "console-file";
      var head = document.createElement("div");
      head.className = "console-file-head";
      head.textContent = path;
      section.appendChild(head);

      grouped[path].sort(function (a, b) {
        return severityRank(a.severity) - severityRank(b.severity) || (a.line - b.line);
      }).forEach(function (p) {
        section.appendChild(renderProblemRow(path, p));
      });
      body.appendChild(section);
    });
  }

  function severityRank(sev) {
    if (sev === "critical") return 0;
    if (sev === "error") return 1;
    if (sev === "warning") return 2;
    return 3;
  }

  function countAll(all) {
    var total = all.filter(function (p) { return !state.cleared; }).length;
    els.problemCount.textContent = String(total);
  }

  function renderProblemRow(path, p) {
    var row = document.createElement("div");
    row.className = "console-row " + severityClass(p.severity);

    if (p.line != null) {
      var loc = document.createElement("span");
      loc.className = "console-loc";
      loc.textContent = "Ln " + p.line;
      row.appendChild(loc);
    }

    var sev = document.createElement("span");
    sev.className = "console-sev";
    sev.textContent = p.severity;
    row.appendChild(sev);

    var tag = document.createElement("span");
    tag.className = "console-linter";
    tag.textContent = p.linter;
    row.appendChild(tag);

    var msg = document.createElement("span");
    msg.className = "console-msg";
    msg.textContent = p.message;
    row.appendChild(msg);

    row.addEventListener("click", function () {
      openFile(path);
      setTimeout(function () {
        editor.revealLineInCenter(p.line);
        editor.setPosition({ lineNumber: p.line, column: (p.column || 1) });
        editor.focus();
        flashLine(path, p.line);
      }, 40);
    });
    return row;
  }

  /* ------------------------------------------------------------ */
  /* Status + session                                              */
  /* ------------------------------------------------------------ */
  var statusEl = null;
  function setStatus(msg) {
    if (!statusEl) {
      statusEl = document.createElement("div");
      statusEl.className = "ide-status";
      document.body.appendChild(statusEl);
    }
    statusEl.textContent = msg;
    statusEl.classList.toggle("visible", !!msg);
  }

  function showErr(path, msg) {
    // surface linter run errors in the console
    (function (m) {
      var list = (state.problems[path] = state.problems[path] || []);
      if (!list.some(function (p) { return p.message === m; })) {
        list.unshift({ file: path, line: 1, severity: "critical", rule: "run", message: m, linter: "linter" });
      }
    })(msg);
    renderConsole();
  }

  function saveSession() {
    try {
      localStorage.setItem(
        "cri-ide:" + owner + "/" + repo,
        JSON.stringify({ tabs: state.tabOrder.slice(0, 12), active: state.active, mode: mode, prNumber: prNumber })
      );
    } catch (e) { /* ignore */ }
  }

  function restoreSession() {
    try {
      var raw = localStorage.getItem("cri-ide:" + owner + "/" + repo);
      if (!raw) return null;
      var s = JSON.parse(raw);
      if (s.mode !== mode || (s.mode === "pr" && s.prNumber !== prNumber)) return null;
      return s;
    } catch (e) { return null; }
  }

  /* ------------------------------------------------------------ */
  /* Filters                                                       */
  /* ------------------------------------------------------------ */
  function toggleFilter(sev, btn) {
    state.filters[sev] = !state.filters[sev];
    btn.classList.toggle("off", !state.filters[sev]);
    Object.keys(state.tabs).forEach(function (p) { applyMarkers(p); });
    renderConsole();
  }

  function initFilters() {
    var btns = document.querySelectorAll(".chip[data-sev]");
    Array.prototype.forEach.call(btns, function (btn) {
      btn.addEventListener("click", function () {
        toggleFilter(btn.dataset.sev, btn);
      });
    });
    els.clearBtn.addEventListener("click", function () {
      state.cleared = !state.cleared;
      els.clearBtn.classList.toggle("off", state.cleared);
      Object.keys(state.tabs).forEach(function (p) { applyMarkers(p); });
      renderConsole();
    });
  }

  /* ------------------------------------------------------------ */
  /* Boot                                                          */
  /* ------------------------------------------------------------ */
  function setupSelects() {
    els.branchSelect.addEventListener("change", function () {
      window.location.href = "/ide/" + owner + "/" + repo;
    });
    els.prSelect.addEventListener("change", function () {
      var v = els.prSelect.value;
      if (v) window.location.href = "/ide/" + owner + "/" + repo + "/pr/" + v;
    });
  }

  function boot(requireFn) {
    if (!requireFn) {
      astray();
      return;
    }
    requireFn.config({ paths: { vs: monacoBase } });
    requireFn(["vs/editor/editor.main"], function () {
      els = {
        treeBody: document.getElementById("ide-tree-body"),
        tabs: document.getElementById("ide-tabs"),
        consoleBody: document.getElementById("console-body"),
        problemCount: document.getElementById("problem-count"),
        branchSelect: document.getElementById("branch-select"),
        prSelect: document.getElementById("pr-select"),
        clearBtn: document.getElementById("btn-clear-problems"),
        lintBtn: document.getElementById("btn-lint"),
        refactorBtn: document.getElementById("btn-refactor"),
        toast: document.getElementById("toast"),
      };

      editor = monaco.editor.create(document.getElementById("editor"), {
        theme: "vs-dark",
        automaticLayout: true,
        readOnly: true,
        minimap: { enabled: true },
        fontSize: 13,
        tabSize: 4,
        scrollBeyondLastLine: false,
      });

      initFilters();
      setupSelects();
      els.lintBtn.addEventListener("click", function () {
        if (state.active) lintFile(state.active);
      });
      els.refactorBtn.addEventListener("click", runRefactor);

      if (mode === "pr") {
        var head = document.querySelector(".ide-actions");
        var analyzeBtn = document.createElement("button");
        analyzeBtn.className = "btn btn-sm";
        analyzeBtn.textContent = "Run analysis";
        analyzeBtn.title = "Run this PR through the linters + AI";
        analyzeBtn.addEventListener("click", runPRAnalysis);
        head.insertBefore(analyzeBtn, els.lintBtn);
      }

      loadInfo()
        .then(function () {
          fillBranches();
          if (mode === "pr") {
            return loadPRs().then(function () {
              var pr = state.prs.find(function (p) {
                return p.number === prNumber;
              });
              if (pr) state.prHeadSha = pr.head;
              return loadPRFiles();
            });
          }
          return loadTree().then(loadPRs);
        })
        .then(function () {
          if (mode === "pr") fillPRs();
          start();
        })
        .catch(function (err) {
          setStatus("Load failed: " + err.message);
          toast(err.message);
        });
    });
  }

  function start() {
    loadPRProblems();
    var sess = restoreSession();
    var paths =
      sess && sess.tabs && sess.tabs.length
        ? sess.tabs
        : state.files
            .filter(function (f) { return f.lintable; })
            .slice(0, 12)
            .map(function (f) { return f.path; });

    if (!paths.length) {
      renderTabs();
      renderConsole();
      toast("Nothing to open in this repo");
      return;
    }

    paths.forEach(function (p) {
      var file = state.files.find(function (f) { return f.path === p; });
      if (!file) return;
      var ref = mode === "pr" ? state.prHeadSha : state.branch;
      apiCall(
        "/api/ide/content" +
          qs({ owner: owner, repo: repo, path: p, ref: ref, blob: file.sha, size: file.size })
      )
        .then(function (data) {
          var model = editor.createModel(data.content, langForPath(p));
          state.tabs[p] = { model: model, file: file };
          state.tabOrder.push(p);
          if (file.lintable) lintFile(p);
          renderTabs();
          renderConsole();
          saveSession();
        })
        .catch(function (err) {
          setStatus("Open failed: " + err.message);
        });
    });

    var focus =
      sess && sess.active && state.files.some(function (f) { return f.path === sess.active; })
        ? sess.active
        : paths[0];
    openFile(focus);
  }

  // If require/AMD failed to load monaco, tell the user gracefully.
  function astray() {
    var box = document.createElement("div");
    box.className = "toast";
    box.style.display = "block";
    box.textContent = "Monaco failed to load — check /static/vendor/monaco";
    document.body.appendChild(box);
  }

  if (requireMonaco) boot(requireMonaco);
  else {
    // fallback: wait for loader to define require
    window.addEventListener("load", function () {
      if (window.require) boot(window.require);
      else astray();
    });
  }
})();