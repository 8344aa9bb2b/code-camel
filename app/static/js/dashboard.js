/* Dashboard: lazy-load open PRs and branches into the per-repo menus. */
(function () {
  "use strict";

  function loadMenu(url, target, buildItems) {
    fetch(url)
      .then(function (resp) {
        if (resp.status === 401) {
          window.location.href = "/login";
          throw new Error("auth");
        }
        return resp.json();
      })
      .then(function (data) {
        target.innerHTML = "";
        var items = buildItems(data);
        if (!items || !items.length) {
          target.innerHTML = '<span class="pr-none">Nothing here</span>';
          return;
        }
        items.forEach(function (item) {
          target.appendChild(item);
        });
      })
      .catch(function () {
        target.innerHTML = '<span class="pr-none">Failed to load</span>';
      });
  }

  function loadPRs(menu) {
    var owner = menu.dataset.owner;
    var repo = menu.dataset.repo;
    var target = menu.querySelector(".pr-menu-list");
    loadMenu(
      "/api/ide/prs?owner=" + encodeURIComponent(owner) + "&repo=" + encodeURIComponent(repo),
      target,
      function (data) {
        if (!data.prs || !data.prs.length) return [];
        return data.prs.map(function (p) {
          var a = document.createElement("a");
          a.className = "pr-item";
          a.href = "/ide/" + owner + "/" + repo + "/pr/" + p.number;
          a.textContent = "#" + p.number + " " + p.title;
          return a;
        });
      }
    );
  }

  function loadBranches(menu) {
    var owner = menu.dataset.owner;
    var repo = menu.dataset.repo;
    var target = menu.querySelector(".branch-menu-list");
    loadMenu(
      "/api/ide/branches?owner=" + encodeURIComponent(owner) + "&repo=" + encodeURIComponent(repo),
      target,
      function (data) {
        if (!data.branches || !data.branches.length) return [];
        return data.branches.map(function (b) {
          var a = document.createElement("a");
          a.className = "pr-item";
          a.href = "/ide/" + owner + "/" + repo + "?branch=" + encodeURIComponent(b);
          a.textContent = b;
          return a;
        });
      }
    );
  }

  document.addEventListener("click", function (ev) {
    var summary = ev.target.closest(".pr-menu summary");
    if (!summary) return;
    var menu = summary.closest(".pr-menu");
    var branchList = menu.querySelector(".branch-menu-list");
    var prList = menu.querySelector(".pr-menu-list");
    var list = branchList || prList;
    if (list && list.dataset.loaded !== "1") {
      list.dataset.loaded = "1";
      if (branchList) loadBranches(menu);
      else loadPRs(menu);
    }
  });
})();
