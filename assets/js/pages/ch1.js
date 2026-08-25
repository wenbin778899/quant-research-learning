/* ch1.js — 第 1 章图表渲染器：C2 行业构成 / C3 K线 / C4 复权对比 / C5 数据质量 */
(function () {
  "use strict";
  var CK = window.ChartKit;

  /* ---- C2 行业构成（柱 + 折线） ---- */
  CK.register("c2", function (chart, box, theme) {
    return CK.loadData("industry.json").then(function (d) {
      var ind = d.industries;
      var opt = CK.baseOpts(theme, {
        title: { show: false },
        tooltip: { trigger: "axis" },
        legend: { data: ["股票数量", "总市值(亿元)"] },
        grid: { left: 52, right: 20, top: 40, bottom: 40 },
        xAxis: { type: "category", data: ind, axisLabel: { rotate: 30 } },
        yAxis: [
          { type: "value", name: "数量", minInterval: 1 },
          { type: "value", name: "市值(亿)", splitLine: { show: false } },
        ],
        series: [
          { name: "股票数量", type: "bar", data: d.stock_counts, barWidth: "45%", itemStyle: { borderRadius: [4, 4, 0, 0] } },
          { name: "总市值(亿元)", type: "line", yAxisIndex: 1, data: d.total_mv.map(function (v) { return +(v / 1e8).toFixed(0); }),
            lineStyle: { width: 2 }, symbolSize: 6 },
        ],
      });
      chart.setOption(opt);
    });
  });

  /* ---- C3 K线样本 ---- */
  CK.register("c3", function (chart, box, theme) {
    return CK.loadData("kline_sample.json").then(function (d) {
      var stocks = d.stocks;
      var idx = 0;
      function render(i) {
        var s = stocks[i];
        var dates = s.dates;
        var kdata = dates.map(function (_, j) {
          return [s.open[j], s.close[j], s.low[j], s.high[j]];
        });
        var opt = CK.baseOpts(theme, {
          title: { text: "000" + s.code.slice(3) + " · " + s.industry, left: 4, textStyle: { fontSize: 13, fontWeight: 600 } },
          tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
          grid: { left: 56, right: 16, top: 44, bottom: 48 },
          xAxis: { type: "category", data: dates.map(function (x) { return x.slice(5); }), boundaryGap: true, axisLabel: { interval: 15 } },
          yAxis: { scale: true },
          dataZoom: CK.dataZoomOpts(theme, { endValue: 119, slider: false }),
          series: [
            {
              name: "K线", type: "candlestick", data: kdata,
              itemStyle: { color: "#d03b3b", color0: "#0ca30c", borderColor: "#d03b3b", borderColor0: "#0ca30c" },
            },
            { name: "MA5", type: "line", data: s.ma5, smooth: true, symbol: "none", lineStyle: { width: 1.5, color: CK.PALETTE[theme][1] } },
            { name: "MA20", type: "line", data: s.ma20, smooth: true, symbol: "none", lineStyle: { width: 1.5, color: CK.PALETTE[theme][2] } },
          ],
        });
        chart.setOption(opt, true);
      }
      render(0);
      // 下拉切换（由 common.js 之外本页独立控制）
      var sel = document.createElement("select");
      sel.className = "q-search";
      sel.style.margin = "4px 8px";
      sel.innerHTML = stocks.map(function (s, i) {
        return "<option value=\"" + i + "\">" + s.code + " · " + s.industry + "</option>";
      }).join("");
      sel.addEventListener("change", function () { render(+sel.value); });
      var title = box.querySelector(".chart-title");
      if (title) title.appendChild(sel);
    });
  });

  /* ---- C4 复权对比 ---- */
  CK.register("c4", function (chart, box, theme) {
    return CK.loadData("kline_sample.json").then(function (d) {
      var s = d.stocks.find(function (x) { return x.code === "000002"; }) || d.stocks[1] || d.stocks[0];
      var dates = s.dates;
      var opt = CK.baseOpts(theme, {
        legend: { data: ["未复权", "前复权", "后复权"] },
        grid: { left: 56, right: 20, top: 40, bottom: 48 },
        xAxis: { type: "category", data: dates.map(function (x) { return x.slice(5); }), axisLabel: { interval: 15 } },
        yAxis: { scale: true },
        dataZoom: CK.dataZoomOpts(theme, { endValue: 119, slider: false }),
        series: [
          { name: "未复权", type: "line", data: s.adj_raw, symbol: "none", lineStyle: { width: 1.5, color: CK.INK[theme][2] }, itemStyle: { color: CK.INK[theme][2] } },
          { name: "前复权", type: "line", data: s.adj_fwd, symbol: "none", lineStyle: { width: 2, color: CK.PALETTE[theme][0] } },
          { name: "后复权", type: "line", data: s.adj_bwd, symbol: "none", lineStyle: { width: 2, color: CK.PALETTE[theme][1] } },
        ],
      });
      chart.setOption(opt);
    });
  });

  /* ---- C5a 缺失率 ---- */
  CK.register("c5a", function (chart, box, theme) {
    return CK.loadData("quality.json").then(function (d) {
      var opt = CK.baseOpts(theme, {
        tooltip: { trigger: "axis" },
        grid: { left: 56, right: 20, top: 30, bottom: 40 },
        xAxis: { type: "category", data: d.columns },
        yAxis: { type: "value", axisLabel: { formatter: function (v) { return (v * 100).toFixed(1) + "%"; } } },
        series: [{
          name: "缺失率", type: "bar", data: d.missing_rates, barWidth: "45%",
          itemStyle: { color: CK.PALETTE[theme][0], borderRadius: [4, 4, 0, 0] },
          label: { show: true, position: "top", formatter: function (p) { return (p.value * 100).toFixed(2) + "%"; }, fontSize: 11, color: CK.INK[theme][2] },
        }],
      });
      chart.setOption(opt);
    });
  });

  /* ---- C5b 行业收益箱线 ---- */
  CK.register("c5b", function (chart, box, theme) {
    return CK.loadData("quality.json").then(function (d) {
      var data = d.return_boxes.map(function (b) {
        return [b.min, b.q1, b.median, b.q3, b.max];
      });
      var opt = CK.baseOpts(theme, {
        tooltip: { trigger: "item" },
        grid: { left: 56, right: 20, top: 30, bottom: 60 },
        xAxis: { type: "category", data: d.return_boxes.map(function (b) { return b.industry; }), axisLabel: { rotate: 30 } },
        yAxis: { type: "value", axisLabel: { formatter: function (v) { return (v * 100).toFixed(0) + "%"; } } },
        series: [{
          name: "日收益分布", type: "boxplot", data: data,
          itemStyle: { color: CK.PALETTE[theme][0], borderColor: CK.PALETTE[theme][3] },
        }],
      });
      chart.setOption(opt);
    });
  });
})();
