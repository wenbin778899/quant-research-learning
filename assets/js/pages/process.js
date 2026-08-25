/* process.js — 研究过程页：时间线 / 方法论 / C25 分类统计 / 提问卡片 */
(function () {
  "use strict";
  var CK = window.ChartKit;

  var ADOPT_CN = { adopt: "已采纳", partial: "部分采纳", reject: "未采纳" };
  var state = { cat: "全部", kw: "" };

  /* ---- C25 分类统计 ---- */
  CK.register("c25", function (chart, box, theme) {
    return CK.loadData("questions.json").then(function (d) {
      var counts = {};
      d.categories.forEach(function (c) { counts[c] = 0; });
      d.questions.forEach(function (q) { counts[q.cat] = (counts[q.cat] || 0) + 1; });
      var labels = d.categories.filter(function (c) { return counts[c] > 0; });
      var opt = CK.baseOpts(theme, {
        legend: { show: false },
        grid: { left: 110, right: 20, top: 20, bottom: 36 },
        xAxis: { type: "value", minInterval: 1 },
        yAxis: { type: "category", data: labels },
        series: [{
          type: "bar", data: labels.map(function (c) { return counts[c]; }),
          barWidth: "55%",
          itemStyle: { color: CK.PALETTE[theme][0], borderRadius: [0, 4, 4, 0] },
          label: { show: true, position: "right", color: CK.INK[theme][2], fontSize: 11 },
        }],
      });
      chart.setOption(opt);
    });
  });

  /* ---- 时间线 ---- */
  function renderTimeline(d) {
    var el = document.getElementById("timeline");
    if (!el) return;
    el.innerHTML = d.timeline.map(function (t) {
      return '<div class="tl-item"><div class="tl-time">' + t.time +
        '</div><div class="tl-title">' + t.title +
        '</div><div class="tl-desc">' + t.desc + "</div></div>";
    }).join("");
  }

  /* ---- 方法论 ---- */
  function renderMethodology(d) {
    var el = document.getElementById("methodology");
    if (el) el.innerHTML = "<p>" + d.methodology + "</p>";
  }

  /* ---- 提问卡片 ---- */
  function renderList(d) {
    var el = document.getElementById("q-list");
    if (!el) return;
    var list = d.questions.filter(function (q) {
      var okCat = state.cat === "全部" || q.cat === state.cat;
      var okKw = !state.kw || (q.title + q.original + q.answer + q.reason + q.reflect).indexOf(state.kw) >= 0;
      return okCat && okKw;
    });
    el.innerHTML = list.map(function (q) {
      var dec = q.decision ? '<div class="q-decision"><b class="' + q.adopt + '">' + ADOPT_CN[q.adopt] + '</b>：' + q.decision + "</div>" : "";
      var refl = q.reflect ? '<div class="q-reflect">💡 反思：' + q.reflect + "</div>" : "";
      return '<details class="q-card" open>' +
        "<summary>" + q.id + " · " + q.title + "</summary>" +
        '<div class="q-meta">' +
        '<span class="pill cat">' + q.cat + "</span>" +
        '<span class="pill">' + q.date + "</span>" +
        '<span class="pill">' + ADOPT_CN[q.adopt] + "</span>" +
        "</div>" +
        '<div class="q-original"><b>提问原文：</b>' + q.original + "</div>" +
        '<div class="q-answer"><b>AI 回答摘要：</b>' + q.answer + "</div>" +
        dec + refl +
        "</details>";
    }).join("") || '<p style="color:var(--ink-3)">无匹配记录</p>';
  }

  /* ---- 筛选器 ---- */
  function initFilters(d) {
    var el = document.getElementById("q-filters");
    if (!el) return;
    var cats = ["全部"].concat(d.categories);
    el.innerHTML = cats.map(function (c) {
      return '<button class="' + (c === "全部" ? "active" : "") + '" data-cat="' + c + '">' + c + "</button>";
    }).join("");
    el.querySelectorAll("button").forEach(function (b) {
      b.addEventListener("click", function () {
        state.cat = b.dataset.cat;
        el.querySelectorAll("button").forEach(function (x) { x.classList.toggle("active", x === b); });
        renderList(d);
      });
    });
    var search = document.getElementById("q-search");
    if (search) {
      search.addEventListener("input", function () {
        state.kw = search.value.trim();
        renderList(d);
      });
    }
  }

  CK.loadData("questions.json").then(function (d) {
    renderTimeline(d);
    renderMethodology(d);
    initFilters(d);
    renderList(d);
  });
})();
