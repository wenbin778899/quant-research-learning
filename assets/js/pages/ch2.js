/* ch2.js — 第 2 章图表渲染器：C6 预处理三态 / C7 行业中性化 */
(function () {
  "use strict";
  var CK = window.ChartKit;

  function histogram(vals, bins) {
    /* 简易直方图：输入值数组（含 null），输出 {data, edges} */
    var v = vals.filter(function (x) { return x !== null && x !== undefined && isFinite(x); });
    if (!v.length) return { data: [], edges: [] };
    var lo = Math.min.apply(null, v), hi = Math.max.apply(null, v);
    if (hi === lo) hi = lo + 1;
    var w = (hi - lo) / bins;
    var counts = new Array(bins).fill(0);
    v.forEach(function (x) {
      var i = Math.min(bins - 1, Math.floor((x - lo) / w));
      counts[i]++;
    });
    var edges = [];
    for (var i = 0; i < bins; i++) edges.push(+(lo + i * w).toFixed(4));
    return { data: counts, edges: edges };
  }

  /* ---- C6 预处理三态（EP 因子） ---- */
  CK.register("c6", function (chart, box, theme) {
    return CK.loadData("distribution.json").then(function (d) {
      var BINS = 24;
      var raw = histogram(d.raw, BINS);
      var zo = histogram(d.z_only, BINS);
      var zn = histogram(d.z_neutral, BINS);
      function series(label, h, color, axis) {
        return {
          name: label, type: "bar", data: h.data, barGap: "5%",
          xAxisIndex: axis, yAxisIndex: axis,
          itemStyle: { color: color, opacity: 0.85, borderRadius: [3, 3, 0, 0] },
        };
      }
      var opt = CK.baseOpts(theme, {
        tooltip: { trigger: "axis" },
        legend: { data: ["原始 EP", "z-score 后", "中性化后"] },
        grid: [{ left: 50, right: 240, top: 40, bottom: 44 },
               { left: 480, right: 20, top: 40, bottom: 44 }],
        xAxis: [
          { type: "category", data: raw.edges, axisLabel: { rotate: 45, fontSize: 10 } },
          { type: "category", gridIndex: 1, data: zo.edges, axisLabel: { rotate: 45, fontSize: 10 } },
        ],
        yAxis: [
          { type: "value", name: "频数" },
          { type: "value", gridIndex: 1, name: "频数" },
        ],
        series: [
          series("原始 EP", raw, CK.PALETTE[theme][0], 0),
          series("z-score 后", zo, CK.PALETTE[theme][1], 1),
          series("中性化后", zn, CK.PALETTE[theme][2], 1),
        ],
      });
      chart.setOption(opt);
    });
  });

  /* ---- C7 行业中性化前后对比（分组箱线） ---- */
  CK.register("c7", function (chart, box, theme) {
    return CK.loadData("distribution.json").then(function (d) {
      var inds = d.industries;
      var nInd = inds.length;
      function boxesFor(arr) {
        // 按行业分组 → ECharts boxplot 数据 [min, q1, med, q3, max]
        var out = [];
        for (var j = 0; j < nInd; j++) {
          var g = [];
          arr.forEach(function (v, i) {
            if (v !== null && d.industry_of[i] === j) g.push(v);
          });
          g.sort(function (a, b) { return a - b; });
          function q(p) { return g[Math.min(g.length - 1, Math.floor(p * g.length))]; }
          out.push([q(0.01), q(0.25), q(0.5), q(0.75), q(0.99)]);
        }
        return out;
      }
      var xLabels = [];
      inds.forEach(function (nm) { xLabels.push(nm + "·仅标准化"); });
      inds.forEach(function (nm) { xLabels.push(nm + "·中性化后"); });
      var opt = CK.baseOpts(theme, {
        tooltip: { trigger: "item" },
        grid: { left: 50, right: 20, top: 34, bottom: 70 },
        xAxis: { type: "category", data: xLabels, axisLabel: { rotate: 55, fontSize: 10 } },
        yAxis: { type: "value", name: "z 值" },
        series: [
          { name: "仅标准化", type: "boxplot", data: boxesFor(d.z_only), itemStyle: { color: CK.PALETTE[theme][0], borderColor: CK.PALETTE[theme][0] } },
          { name: "中性化后", type: "boxplot", data: boxesFor(d.z_neutral), itemStyle: { color: CK.PALETTE[theme][2], borderColor: CK.PALETTE[theme][2] } },
        ],
      });
      chart.setOption(opt);
    });
  });
})();
