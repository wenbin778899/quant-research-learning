/* ch6.js — 第 6 章图表渲染器：C19 净值+回撤双面板 / C20 滚动超额 / C21 指标卡 */
(function () {
  "use strict";
  var CK = window.ChartKit;

  /* ---- C19 净值 + 回撤（双面板联动） ---- */
  CK.register("c19", function (chart, box, theme) {
    return CK.loadData("backtest.json").then(function (d) {
      var dates = d.dates.map(function (x) { return x.slice(0, 7); });
      var opt = CK.baseOpts(theme, {
        tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
        legend: { data: ["组合", "基准", "多空"], top: 0 },
        grid: [
          { left: 56, right: 16, top: 32, bottom: 120 },
          { left: 56, right: 16, top: 250, bottom: 46 },
        ],
        xAxis: [
          { type: "category", data: dates, axisLabel: { interval: 9 } },
          { type: "category", gridIndex: 1, data: dates, axisLabel: { interval: 9 } },
        ],
        yAxis: [
          { type: "value", scale: true, name: "净值" },
          { type: "value", gridIndex: 1, name: "回撤", axisLabel: { formatter: function (v) { return (v * 100).toFixed(0) + "%"; } } },
        ],
        dataZoom: CK.dataZoomOpts(theme, { xAxisIndex: [0, 1] }),
        series: [
          { name: "组合", type: "line", data: d.nav.portfolio, symbol: "none", lineStyle: { width: 2.4, color: CK.PALETTE[theme][0] } },
          { name: "基准", type: "line", data: d.nav.benchmark, symbol: "none", lineStyle: { width: 1.8, color: CK.INK[theme][2] } },
          { name: "多空", type: "line", data: d.nav.long_short, symbol: "none", lineStyle: { width: 1.8, color: CK.PALETTE[theme][1] } },
          { name: "组合回撤", type: "line", xAxisIndex: 1, yAxisIndex: 1, data: d.drawdown.portfolio, symbol: "none",
            lineStyle: { width: 0 }, areaStyle: { color: CK.PALETTE[theme][7], opacity: 0.35 }, tooltip: { show: true } },
          { name: "基准回撤", type: "line", xAxisIndex: 1, yAxisIndex: 1, data: d.drawdown.benchmark, symbol: "none",
            lineStyle: { width: 1, color: CK.INK[theme][2], type: "dashed" } },
        ],
      });
      chart.setOption(opt);
    });
  });

  /* ---- C20 滚动 12 个月超额 ---- */
  CK.register("c20", function (chart, box, theme) {
    return CK.loadData("backtest.json").then(function (d) {
      var dates = d.dates.map(function (x) { return x.slice(0, 7); });
      var vals = d.rolling_excess;
      // 从第 12 个点开始有值（12 期滚动窗口）
      var data = vals.map(function (v, i) {
        return v === null || v === undefined ? "-" : v;
      });
      var opt = CK.baseOpts(theme, {
        legend: { show: false },
        grid: { left: 56, right: 16, top: 26, bottom: 56 },
        xAxis: { type: "category", data: dates, axisLabel: { interval: 9 } },
        yAxis: { type: "value", axisLabel: { formatter: function (v) { return (v * 100).toFixed(0) + "%"; } } },
        dataZoom: CK.dataZoomOpts(theme),
        series: [{
          name: "滚动12M超额", type: "bar", data: data, barWidth: "55%",
          itemStyle: {
            color: function (p) { return p.value === "-" ? "transparent" : (p.value >= 0 ? "#0ca30c" : "#d03b3b"); },
            borderRadius: [2, 2, 0, 0],
          },
        }],
      });
      chart.setOption(opt);
    });
  });

  /* ---- C21 绩效指标卡（HTML 渲染） ---- */
  CK.register("c21", function (chart, box, theme) {
    return CK.loadData("backtest.json").then(function (d) {
      var m = d.metrics;
      function fmt(v, digits) { return v === null || v === undefined ? "—" : v.toFixed(digits); }
      function pctFmt(v) { return v === null || v === undefined ? "—" : (v * 100).toFixed(1) + "%"; }
      var cards = [
        { label: "年化收益", value: pctFmt(m.portfolio.annual_return), cls: "good" },
        { label: "年化波动", value: pctFmt(m.portfolio.annual_vol) },
        { label: "夏普比率", value: fmt(m.portfolio.sharpe, 2), cls: m.portfolio.sharpe > 1 ? "good" : "" },
        { label: "最大回撤", value: pctFmt(m.portfolio.max_drawdown), cls: "bad" },
        { label: "Calmar", value: fmt(m.portfolio.calmar, 2) },
        { label: "月度胜率", value: pctFmt(m.portfolio.win_rate) },
        { label: "超额年化", value: pctFmt(m.excess.excess_annual), cls: (m.excess.excess_annual || 0) > 0 ? "good" : "bad" },
        { label: "信息比率", value: fmt(m.excess.info_ratio, 2), cls: (m.excess.info_ratio || 0) > 0.5 ? "good" : "" },
      ];
      var html = '<div class="metric-grid">' + cards.map(function (c) {
        return '<div class="metric"><div class="value ' + (c.cls || "") + '">' + c.value +
          '</div><div class="label">' + c.label + "</div></div>";
      }).join("") + "</div>";
      var host = box.querySelector(".chart") || box;
      host.innerHTML = html;
      var label = document.createElement("p");
      label.className = "chart-note";
      label.innerHTML = "<strong>怎么看：</strong>组合（合成因子 Top20 等权）扣 10 bps 单边成本后的月度调仓回测。夏普 1.7+、Calmar 3+ 属于稳健水平；注意这些指标基于模拟数据，教学重点在<em>读法</em>而非数值。";
      box.appendChild(label);
      return null;
    });
  });
})();
