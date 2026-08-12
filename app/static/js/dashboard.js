/* Dashboard: lazy-load open PRs into the per-repo PR menus. */
(function () {
  "use strict";

  function loadPRs(menu) {
    var owner = menu.dataset.owner;
    var repo = menu.dataset.repo;
    var target = menu.querySelector(".pr-menu-list");
    fetch(
      "/api/ide/prs?owner=" + encodeURIComponent(owner) + "&repo=" + encodeURIComponent(repo)
    )
      .then(function (resp) {
        if (resp.status === 401) {
          window.location.href = "/login";
          throw new Error("auth");
        }
        return resp.json();
      })
      .then(function (data) {
        if (!data.prs || !data.prs.length) {
          target.innerHTML = '<span class="pr-none">No open PRs</span>';
          return;
        }
        target.innerHTML = "";
        data.prs.forEach(function (p) {
          var a = document.createElement("a");
          a.className = "pr-item";
          a.href = "/ide/" + owner + "/" + repo + "/pr/" + p.number;
          a.textContent = "#" + p.number + " " + p.title;
          target.appendChild(a);
        });
      })
      .catch(function () {
        target.innerHTML = '<span class="pr-none">Failed to load</span>';
      });
  }

  document.addEventListener("click", function (ev) {
    var summary = ev.target.closest(".pr-menu summary");
    if (!summary) return;
    var menu = summary.closest(".pr-menu");
    var list = menu.querySelector(".pr-menu-list");
    if (list && list.dataset.loaded !== "1") {
      list.dataset.loaded = "1";
      loadPRs(menu);
    }
  });
})();