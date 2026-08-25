/* ch7.js — 第 7 章图表渲染器：C22 Brinson归因 / C23 风格暴露 / C24 风险分解 */
(function () {
  "use strict";
  var CK = window.ChartKit;

  var STYLE_CN = { SIZE: "规模", MOM60: "动量", VOL20: "低波动", EP: "估值", TURN: "换手" };

  /* ---- C22 Brinson 归因（季度分组柱） ---- */
  CK.register("c22", function (chart, box, theme) {
    return CK.loadData("attribution.json").then(function (d) {
      var opt = CK.baseOpts(theme, {
        tooltip: { trigger: "axis" },
        legend: { data: ["配置效应", "选股效应", "总超额"] },
        grid: { left: 56, right: 16, top: 40, bottom: 70 },
        xAxis: { type: "category", data: d.quarters.map(function (q) { return q.replace("Q", "Q"); }), axisLabel: { rotate: 45, fontSize: 10 } },
        yAxis: { type: "value", axisLabel: { formatter: function (v) { return (v * 100).toFixed(0) + "%"; } } },
        series: [
          { name: "配置效应", type: "bar", data: d.brinson.allocation, barWidth: "22%",
            itemStyle: { color: CK.INK[theme][2], borderRadius: [3, 3, 0, 0] } },
          { name: "选股效应", type: "bar", data: d.brinson.selection, barWidth: "22%",
            itemStyle: { color: CK.PALETTE[theme][0], borderRadius: [3, 3, 0, 0] } },
          { name: "总超额", type: "bar", data: d.brinson.total, barWidth: "22%",
            itemStyle: { color: CK.PALETTE[theme][1], borderRadius: [3, 3, 0, 0] } },
        ],
      });
      chart.setOption(opt);
    });
  });

  /* ---- C23 风格暴露 ---- */
  CK.register("c23", function (chart, box, theme) {
    return CK.loadData("attribution.json").then(function (d) {
      var dates = d.style_exposure.dates.map(function (x) { return x.slice(0, 7); });
      var series = d.style_exposure.factors.map(function (f) {
        return {
          name: STYLE_CN[f] || f, type: "line", data: d.style_exposure[f],
          symbol: "none", lineStyle: { width: 1.8 },
        };
      });
      var opt = CK.baseOpts(theme, {
        legend: { data: series.map(function (s) { return s.name; }) },
        grid: { left: 52, right: 16, top: 40, bottom: 56 },
        xAxis: { type: "category", data: dates, axisLabel: { interval: 9 } },
        yAxis: { type: "value", name: "暴露(z)", splitLine: { lineStyle: { color: CK.GRID[theme] } } },
        dataZoom: CK.dataZoomOpts(theme),
        series: series,
      });
      chart.setOption(opt);
    });
  });

  /* ---- C24 风险分解（堆叠面积） ---- */
  CK.register("c24", function (chart, box, theme) {
    return CK.loadData("attribution.json").then(function (d) {
      var dates = d.risk.dates.map(function (q) { return q + ""; });
      function arr(k) { return d.risk[k].map(function (v) { return v === null || v === undefined ? "-" : v; }); }
      var opt = CK.baseOpts(theme, {
        tooltip: { trigger: "axis", valueFormatter: function (v) { return v === "-" ? "—" : (v * 100).toFixed(1) + "%"; } },
        legend: { data: ["系统性", "行业", "特质"] },
        grid: { left: 52, right: 16, top: 40, bottom: 56 },
        xAxis: { type: "category", data: dates, axisLabel: { fontSize: 10 } },
        yAxis: { type: "value", max: 1, axisLabel: { formatter: function (v) { return (v * 100).toFixed(0) + "%"; } } },
        series: [
          { name: "系统性", type: "line", stack: "risk", data: arr("systematic"), symbol: "none", lineStyle: { width: 1, color: CK.PALETTE[theme][0] }, areaStyle: { color: CK.PALETTE[theme][0], opacity: 0.55 } },
          { name: "行业", type: "line", stack: "risk", data: arr("industry"), symbol: "none", lineStyle: { width: 1, color: CK.PALETTE[theme][3] }, areaStyle: { color: CK.PALETTE[theme][3], opacity: 0.55 } },
          { name: "特质", type: "line", stack: "risk", data: arr("idiosyncratic"), symbol: "none", lineStyle: { width: 1, color: CK.PALETTE[theme][2] }, areaStyle: { color: CK.PALETTE[theme][2], opacity: 0.55 } },
        ],
      });
      chart.setOption(opt);
    });
  });
})();
