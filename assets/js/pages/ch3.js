/* ch3.js — 第 3 章图表渲染器：C8 月度IC / C9 IC均值 / C10 累积IC / C11 分层净值 / C12 分层月收益
 * 交互：因子选择器 + C8 点击联动 + 时间轴缩放
 */
(function () {
  "use strict";
  var CK = window.ChartKit;

  var FACTOR_CN = { EP: "盈利估值", SIZE: "规模", MOM60: "60日动量", REV5: "5日反转",
                    VOL20: "低波动", TURN: "低换手", ROE: "质量", GROW: "成长" };
  var state = { factor: "EP", listeners: [] };
  window.QRS = state;

  function emit() {
    state.listeners.forEach(function (fn) { fn(state.factor); });
  }

  function setFactor(f) {
    if (f === state.factor) return;
    state.factor = f;
    document.querySelectorAll("#factor-switch button").forEach(function (b) {
      b.classList.toggle("active", b.dataset.f === f);
    });
    emit();
  }

  function rerender(name) {
    document.querySelectorAll('.chart-box[data-chart="' + name + '"]').forEach(function (box) {
      CK.render(box, name);
    });
  }

  /* ---- 因子选择器 ---- */
  function initSwitch() {
    var el = document.getElementById("factor-switch");
    if (!el) return;
    var html = '<span style="font-size:13px;color:var(--ink-3);margin-right:6px">当前因子：</span>';
    Object.keys(FACTOR_CN).forEach(function (f) {
      html += '<button data-f="' + f + '" class="' + (f === "EP" ? "active" : "") + '">' + FACTOR_CN[f] + "</button>";
    });
    el.innerHTML = html;
    el.querySelectorAll("button").forEach(function (b) {
      b.addEventListener("click", function () { setFactor(b.dataset.f); });
    });
  }

  /* ---- C8 月度 IC 序列（8 因子可切换；当前因子加粗） ---- */
  CK.register("c8", function (chart, box, theme) {
    return CK.loadData("ic.json").then(function (d) {
      var f = state.factor;
      var series = [];
      d.factors.forEach(function (name, i) {
        var isCur = name === f;
        series.push({
          name: name, type: "line", data: d.ic[name],
          symbol: "none", lineStyle: { width: isCur ? 2.5 : 1.2, color: isCur ? CK.PALETTE[theme][0] : CK.INK[theme][2] },
          itemStyle: { color: CK.PALETTE[theme][0] },
          emphasis: { lineStyle: { width: 3 } },
          z: isCur ? 3 : 1,
        });
      });
      var opt = CK.baseOpts(theme, {
        legend: { show: false },
        grid: { left: 52, right: 16, top: 24, bottom: 56 },
        xAxis: { type: "category", data: d.dates.map(function (x) { return x.slice(0, 7); }), axisLabel: { interval: 9 } },
        yAxis: { type: "value", axisLabel: { formatter: function (v) { return v.toFixed(2); } }, splitLine: { lineStyle: { color: CK.GRID[theme] } } },
        dataZoom: CK.dataZoomOpts(theme),
        series: series,
      });
      chart.setOption(opt);
      chart.off("click");
      chart.on("click", function (p) { if (p.seriesName) setFactor(p.seriesName); });
      chart.off("datazoom");
      chart.on("datazoom", function () { state.zoom = null; });
    });
  });

  /* ---- C9 IC 均值与 ICIR（误差线 + t 值标注） ---- */
  CK.register("c9", function (chart, box, theme) {
    return CK.loadData("ic.json").then(function (d) {
      var names = d.factors.slice();
      var means = names.map(function (f) { return d.summary[f].mean; });
      var stds = names.map(function (f) { return d.summary[f].std; });
      var opt = CK.baseOpts(theme, {
        legend: { show: false },
        grid: { left: 52, right: 20, top: 26, bottom: 44 },
        xAxis: { type: "category", data: names },
        yAxis: { type: "value" },
        series: [{
          name: "IC 均值", type: "bar", data: names.map(function (f) {
            return { value: d.summary[f].mean };
          }),
          barWidth: "42%",
          itemStyle: {
            color: function (p) {
              return p.dataIndex === names.indexOf(state.factor) ? CK.PALETTE[theme][0] : CK.INK[theme][2];
            },
            borderRadius: [4, 4, 0, 0],
          },
          markLine: { symbol: "none", lineStyle: { color: CK.PALETTE[theme][3], type: "dashed", width: 1 } },
          label: {
            show: true, position: "top", fontSize: 10,
            formatter: function (p) {
              var f = names[p.dataIndex];
              return "ICIR " + d.summary[f].icir + "\nt " + d.summary[f].t;
            },
            color: CK.INK[theme][2],
          },
        }],
      });
      // 误差线（±1σ）
      opt.series[0].data.forEach(function (item, i) { item.stderr = stds[i]; });
      chart.setOption(opt);
      // 手动叠加误差线系列
      chart.setOption({
        series: [{
          type: "custom",
          silent: true,
          renderItem: function (params, api) {
            var x = api.coord([api.value(0), 0]);
            var yHi = api.coord([api.value(0), api.value(2)]);
            var yLo = api.coord([api.value(0), api.value(3)]);
            return {
              type: "group",
              children: [{
                type: "line",
                shape: { x1: x[0], y1: yLo[1], x2: x[0], y2: yHi[1] },
                style: { stroke: CK.INK[theme][2], lineWidth: 1 },
              }],
            };
          },
          encode: { x: 0, y: [2, 3] },
          data: names.map(function (f, i) {
            return [i, means[i], means[i] + stds[i], means[i] - stds[i]];
          }),
        }],
      });
    });
  });

  /* ---- C10 累积 IC ---- */
  CK.register("c10", function (chart, box, theme) {
    return CK.loadData("ic.json").then(function (d) {
      var f = state.factor;
      var opt = CK.baseOpts(theme, {
        legend: { show: false },
        grid: { left: 52, right: 16, top: 24, bottom: 56 },
        xAxis: { type: "category", data: d.dates.map(function (x) { return x.slice(0, 7); }), axisLabel: { interval: 9 } },
        yAxis: { type: "value" },
        dataZoom: CK.dataZoomOpts(theme),
        series: [{
          name: f, type: "line", data: d.cum_ic[f],
          symbol: "none", lineStyle: { width: 2, color: CK.PALETTE[theme][0] },
          areaStyle: { color: CK.PALETTE[theme][0], opacity: 0.08 },
        }],
      });
      chart.setOption(opt);
    });
  });

  /* ---- C11 十分位分层净值（单色序渐变） ---- */
  CK.register("c11", function (chart, box, theme) {
    return CK.loadData("layers.json").then(function (d) {
      var f = state.factor;
      var nav = d.nav[f];
      var seq = CK.SEQ[theme];
      var series = [];
      for (var k = 1; k <= 10; k++) {
        series.push({
          name: "层 " + k, type: "line", data: nav["L" + k],
          symbol: "none", lineStyle: { width: 1.3, color: seq[k - 1] },
          emphasis: { lineStyle: { width: 2.4 } },
        });
      }
      series.push({
        name: "多空(层10−层1)", type: "line", data: nav.LS,
        symbol: "none", lineStyle: { width: 2.4, color: CK.PALETTE[theme][1] },
      });
      var opt = CK.baseOpts(theme, {
        grid: { left: 56, right: 16, top: 30, bottom: 56 },
        xAxis: { type: "category", data: d.dates.map(function (x) { return x.slice(0, 7); }), axisLabel: { interval: 9 } },
        yAxis: { type: "value", scale: true },
        dataZoom: CK.dataZoomOpts(theme),
        series: series,
      });
      chart.setOption(opt);
    });
  });

  /* ---- C12 分层平均月收益 ---- */
  CK.register("c12", function (chart, box, theme) {
    return CK.loadData("layers.json").then(function (d) {
      var f = state.factor;
      function avg(key) {
        var v = d.monthly[f][key].filter(function (x) { return x !== null && x !== undefined; });
        return v.length ? v.reduce(function (a, b) { return a + b; }, 0) / v.length : 0;
      }
      var data = [];
      for (var k = 1; k <= 10; k++) data.push(avg("L" + k));
      var ls = avg("L10") - avg("L1");
      var opt = CK.baseOpts(theme, {
        legend: { show: false },
        grid: { left: 56, right: 20, top: 26, bottom: 44 },
        xAxis: { type: "category", data: ["层1", "层2", "层3", "层4", "层5", "层6", "层7", "层8", "层9", "层10", "多空"] },
        yAxis: { type: "value", axisLabel: { formatter: function (v) { return (v * 100).toFixed(1) + "%"; } } },
        series: [{
          type: "bar",
          data: data.concat([ls]).map(function (v, i) {
            return {
              value: v,
              itemStyle: {
                color: i === 10 ? CK.PALETTE[theme][1]
                  : (i + 1 === 10 || i === 0 ? CK.PALETTE[theme][0] : CK.INK[theme][2]),
                borderRadius: [3, 3, 0, 0],
              },
            };
          }),
          label: { show: true, position: "top", formatter: function (p) { return (p.value * 100).toFixed(2) + "%"; }, fontSize: 10, color: CK.INK[theme][2] },
        }],
      });
      chart.setOption(opt);
    });
  });

  /* ---- 联动注册 ---- */
  state.listeners.push(function (f) {
    ["c8", "c9", "c10", "c11", "c12"].forEach(rerender);
  });
  document.addEventListener("DOMContentLoaded", initSwitch);
})();
