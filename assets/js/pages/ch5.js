/* ch5.js — 第 5 章图表渲染器：C16 持仓结构 / C17 换手率 / C18 成本敏感性 */
(function () {
  "use strict";
  var CK = window.ChartKit;

  /* ---- C16 持仓结构（个股权重柱 + 行业环形） ---- */
  CK.register("c16", function (chart, box, theme) {
    return CK.loadData("portfolio.json").then(function (d) {
      var top = d.top_weights || [];
      var ind = d.industry_weights || [];
      var opt = CK.baseOpts(theme, {
        tooltip: { trigger: "item" },
        legend: { data: ["持仓"], top: 4 },
        grid: { left: 52, right: 200, top: 40, bottom: 60 },
        xAxis: { type: "category", data: top.map(function (x) { return x.code + "·" + x.industry; }), axisLabel: { rotate: 45, fontSize: 9 } },
        yAxis: { type: "value", axisLabel: { formatter: function (v) { return (v * 100).toFixed(0) + "%"; } } },
        series: [{
          name: "持仓", type: "bar", data: top.map(function (x) { return x.weight; }),
          barWidth: "55%", itemStyle: { borderRadius: [3, 3, 0, 0] },
        }],
      });
      // 右侧行业环形图：用第二个 grid 不优雅，改为右下角用 legend 提示
      chart.setOption(opt);
      // 叠加一个独立的行业分布小图（graphic 文字说明）
      var indHtml = document.createElement("div");
      indHtml.style.cssText = "position:absolute;right:14px;top:46px;width:170px;font-size:12px";
      indHtml.innerHTML = "<div style='color:var(--ink-3);margin-bottom:6px'>组合行业分布</div>" +
        ind.map(function (x) {
          return "<div style='display:flex;justify-content:space-between;margin:2px 0'>" +
            "<span>" + x.industry + "</span><b>" + (x.weight * 100).toFixed(0) + "%</b></div>";
        }).join("");
      var chartEl = box.querySelector(".chart");
      chartEl.style.position = "relative";
      chartEl.appendChild(indHtml);
      return null;
    });
  });

  /* ---- C17 月度换手率 ---- */
  CK.register("c17", function (chart, box, theme) {
    return CK.loadData("portfolio.json").then(function (d) {
      var dates = d.dates.map(function (x) { return x.slice(0, 7); });
      var turn = d.turnover;
      var avg = turn.reduce(function (a, b) { return a + b; }, 0) / turn.length;
      var opt = CK.baseOpts(theme, {
        legend: { show: false },
        grid: { left: 56, right: 16, top: 26, bottom: 56 },
        xAxis: { type: "category", data: dates, axisLabel: { interval: 9 } },
        yAxis: { type: "value", axisLabel: { formatter: function (v) { return (v * 100).toFixed(0) + "%"; } } },
        dataZoom: CK.dataZoomOpts(theme),
        series: [{
          name: "换手率", type: "bar", data: turn, barWidth: "60%",
          itemStyle: { color: CK.PALETTE[theme][1], borderRadius: [2, 2, 0, 0] },
          markLine: {
            symbol: "none", data: [{ yAxis: avg }],
            lineStyle: { color: CK.PALETTE[theme][0], type: "dashed" },
            label: { formatter: "均值 " + (avg * 100).toFixed(0) + "%", color: CK.INK[theme][2], fontSize: 10 },
          },
        }],
      });
      chart.setOption(opt);
    });
  });

  /* ---- C18 成本敏感性 ---- */
  CK.register("c18", function (chart, box, theme) {
    return CK.loadData("portfolio.json").then(function (d) {
      var dates = d.dates.map(function (x) { return x.slice(0, 7); });
      var colors = CK.PALETTE[theme];
      var series = [
        { name: "0 bps（毛收益）", type: "line", data: d.nav_costs["0"], symbol: "none", lineStyle: { width: 2.4, color: colors[0] } },
        { name: "5 bps", type: "line", data: d.nav_costs["5"], symbol: "none", lineStyle: { width: 1.6, color: colors[1] } },
        { name: "10 bps", type: "line", data: d.nav_costs["10"], symbol: "none", lineStyle: { width: 1.6, color: colors[3] } },
        { name: "20 bps", type: "line", data: d.nav_costs["20"], symbol: "none", lineStyle: { width: 1.6, color: colors[7] } },
      ];
      var opt = CK.baseOpts(theme, {
        legend: { data: ["0 bps（毛收益）", "5 bps", "10 bps", "20 bps"] },
        grid: { left: 56, right: 16, top: 40, bottom: 56 },
        xAxis: { type: "category", data: dates, axisLabel: { interval: 9 } },
        yAxis: { type: "value", scale: true },
        dataZoom: CK.dataZoomOpts(theme),
        series: series,
      });
      chart.setOption(opt);
    });
  });
})();
