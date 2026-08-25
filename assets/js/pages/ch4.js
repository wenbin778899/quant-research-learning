/* ch4.js — 第 4 章图表渲染器：C13 相关性热力图 / C14 权重对比 / C15 合成前后 IC */
(function () {
  "use strict";
  var CK = window.ChartKit;

  var FACTOR_CN = { EP: "盈利估值", SIZE: "规模", MOM60: "60日动量", REV5: "5日反转",
                    VOL20: "低波动", TURN: "低换手", ROE: "质量", GROW: "成长" };

  /* ---- C13 相关性热力图 ---- */
  CK.register("c13", function (chart, box, theme) {
    return CK.loadData("factor_corr.json").then(function (d) {
      var names = d.factors.map(function (f) { return FACTOR_CN[f] || f; });
      var data = [];
      d.corr.forEach(function (row, i) {
        row.forEach(function (v, j) {
          data.push([j, i, v]);
        });
      });
      var opt = CK.baseOpts(theme, {
        legend: { show: false },
        tooltip: {
          trigger: "item",
          formatter: function (p) {
            return names[p.value[1]] + " × " + names[p.value[0]] + "：<b>" + p.value[2].toFixed(3) + "</b>";
          },
        },
        grid: { left: 100, right: 20, top: 16, bottom: 70 },
        xAxis: { type: "category", data: names, axisLabel: { rotate: 40, fontSize: 10 } },
        yAxis: { type: "category", data: names, axisLabel: { fontSize: 10 } },
        visualMap: {
          min: -0.8, max: 0.8, calculable: true, orient: "vertical", right: 0, top: "center",
          textStyle: { color: CK.INK[theme][2], fontSize: 10 },
          inRange: { color: ["#d03b3b", "#fcfcfb", "#2a78d6"] },
        },
        series: [{
          type: "heatmap", data: data,
          label: {
            show: true, fontSize: 9,
            formatter: function (p) { return p.value[2].toFixed(2); },
            color: CK.INK[theme][1],
          },
          itemStyle: { borderWidth: 2, borderColor: CK.SURFACE[theme] },
        }],
      });
      chart.setOption(opt);
    });
  });

  /* ---- C14 三种权重对比 ---- */
  CK.register("c14", function (chart, box, theme) {
    return CK.loadData("combine.json").then(function (d) {
      var names = d.factors.map(function (f) { return FACTOR_CN[f] || f; });
      var opt = CK.baseOpts(theme, {
        legend: { data: ["等权", "IC 加权", "IR 加权"] },
        grid: { left: 52, right: 20, top: 40, bottom: 56 },
        xAxis: { type: "category", data: names, axisLabel: { rotate: 35, fontSize: 10 } },
        yAxis: { type: "value", axisLabel: { formatter: function (v) { return (v * 100).toFixed(0) + "%"; } } },
        series: [
          { name: "等权", type: "bar", data: d.weights.equal, barWidth: "20%", itemStyle: { borderRadius: [3, 3, 0, 0] } },
          { name: "IC 加权", type: "bar", data: d.weights.ic, barWidth: "20%", itemStyle: { borderRadius: [3, 3, 0, 0] } },
          { name: "IR 加权", type: "bar", data: d.weights.ir, barWidth: "20%", itemStyle: { borderRadius: [3, 3, 0, 0] } },
        ],
      });
      chart.setOption(opt);
    });
  });

  /* ---- C15 合成前后 IC 对比 ---- */
  CK.register("c15", function (chart, box, theme) {
    return CK.loadData("combine.json").then(function (d) {
      var names = d.factors.map(function (f) { return FACTOR_CN[f] || f; });
      var labels = names.concat(["合成·等权", "合成·IC加权", "合成·IR加权"]);
      var vals = d.factors.map(function (f) { return d.ic_compare[f]; })
        .concat([d.ic_compare.equal, d.ic_compare.ic, d.ic_compare.ir]);
      var opt = CK.baseOpts(theme, {
        legend: { show: false },
        grid: { left: 52, right: 20, top: 26, bottom: 56 },
        xAxis: { type: "category", data: labels, axisLabel: { rotate: 35, fontSize: 10 } },
        yAxis: { type: "value" },
        series: [{
          type: "bar", data: vals.map(function (v, i) {
            return {
              value: v,
              itemStyle: {
                color: i >= names.length ? CK.PALETTE[theme][1] : CK.INK[theme][2],
                borderRadius: [3, 3, 0, 0],
              },
            };
          }),
          label: { show: true, position: "top", formatter: function (p) { return p.value.toFixed(3); }, fontSize: 10, color: CK.INK[theme][2] },
        }],
      });
      chart.setOption(opt);
    });
  });
})();
