/* chartkit.js — ECharts 图表基础设施
 *  - 明暗双主题（色板经色盲安全验证）
 *  - 数据加载缓存（fetch data/*.json）
 *  - 图表渲染器注册与调度（.chart-box[data-chart="name"]）
 *  - 主题切换时自动重建全部实例
 *  - 页面脚本通过 ChartKit.register(name, fn) 注册渲染器
 */
var ChartKit = (function () {
  "use strict";

  var PALETTE = {
    light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    dark:  ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
  };
  // 蓝色单色序（分层 10 组：L1 浅 → L10 深）
  var SEQ = {
    light: ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
            "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab"],
    dark:  ["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf",
            "#2a78d6", "#3987e5", "#5598e7", "#6da7ec", "#86b6ef"],
  };
  var SURFACE = { light: "#fcfcfb", dark: "#1a1a19" };
  var INK = { light: ["#0b0b0b", "#52514e", "#898781"], dark: ["#ffffff", "#c3c2b7", "#898781"] };
  var GRID = { light: "#e1e0d9", dark: "#2c2c2a" };

  var cache = {};
  /* 从 chartkit.js 的脚本 URL 推导站点根目录（支持根目录与 chapters/ 子目录页面） */
  function siteRoot() {
    var scripts = document.getElementsByTagName("script");
    for (var i = 0; i < scripts.length; i++) {
      var src = scripts[i].src || "";
      var idx = src.indexOf("/assets/js/chartkit.js");
      if (idx >= 0) return src.slice(0, idx + 1);
    }
    return "./";
  }
  var DATA_PREFIX = siteRoot() + "data/";
  function loadData(name) {
    if (cache[name]) return Promise.resolve(cache[name]);
    return fetch(DATA_PREFIX + name)
      .then(function (r) { if (!r.ok) throw new Error("加载 " + name + " 失败: " + r.status); return r.json(); })
      .then(function (d) { cache[name] = d; return d; });
  }

  var renderers = {};
  function register(name, fn) { renderers[name] = fn; }

  var instances = [];   // {dom, chart, name, theme}
  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function render(box, name) {
    var theme = currentTheme();
    // 同容器重渲染前先释放旧实例（因子切换/主题切换场景）
    var old = instances.filter(function (x) { return x.dom === box; });
    old.forEach(function (x) { try { x.chart.dispose(); } catch (e) { /* ignore */ } });
    instances = instances.filter(function (x) { return x.dom !== box; });
    var chart = echarts.init(box.querySelector(".chart") || box, theme);
    var entry = { dom: box, chart: chart, name: name, theme: theme };
    instances.push(entry);
    var fn = renderers[name];
    if (!fn) {
      console.warn("未注册图表渲染器: " + name);
      return;
    }
    fn(chart, box, theme).catch(function (err) {
      console.error("图表 " + name + " 渲染失败:", err);
    });
    return entry;
  }

  function applyTheme(theme) {
    instances.forEach(function (entry) {
      if (entry.theme === theme) return;
      var box = entry.dom;
      var name = entry.name;
      entry.chart.dispose();
      render(box, name);
    });
  }

  /* ---- 通用 ECharts 配置工厂（遵循 dataviz 规范）---- */
  function baseOpts(theme, extra) {
    var t = theme || currentTheme();
    var ink = INK[t];
    var opt = {
      backgroundColor: "transparent",
      textStyle: { color: ink[0], fontFamily: "system-ui, 'Microsoft YaHei', sans-serif" },
      color: PALETTE[t],
      tooltip: {
        trigger: "axis",
        confine: true,
        backgroundColor: SURFACE[t],
        borderColor: GRID[t],
        textStyle: { color: ink[0], fontSize: 12 },
        axisPointer: { type: "cross", lineStyle: { color: GRID[t] }, label: { backgroundColor: ink[2] } },
      },
      legend: {
        type: "scroll", top: 0, textStyle: { color: ink[1], fontSize: 11 },
        inactiveColor: ink[2], itemWidth: 14, itemHeight: 9,
      },
      grid: { left: 48, right: 20, top: 34, bottom: 46, containLabel: false },
      xAxis: {
        type: "category",
        axisLine: { lineStyle: { color: GRID[t] } },
        axisTick: { show: false },
        axisLabel: { color: ink[2], fontSize: 11 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: GRID[t] } },
        axisLabel: { color: ink[2], fontSize: 11 },
      },
    };
    Object.assign(opt, extra || {});
    return opt;
  }

  function dataZoomOpts(theme, opts) {
    var t = theme || currentTheme();
    var o = {
      type: "inside",
      filterMode: "none",
      startValue: 0,
      endValue: 59,
    };
    if (opts) Object.assign(o, opts);
    var slider = {
      type: "slider",
      height: 16,
      bottom: 6,
      borderColor: GRID[t],
      backgroundColor: SURFACE[t],
      fillerColor: "rgba(42,120,214,0.15)",
      handleStyle: { color: PALETTE[t][0] },
      textStyle: { color: INK[t][2], fontSize: 10 },
    };
    if (opts && opts.slider === false) return [o];
    return [o, slider];
  }

  function yFmt(v) { return v.toFixed(3); }

  function pct(v) { return (v * 100).toFixed(1) + "%"; }

  /* ---- 数字千分位 ---- */
  function numFmt(v) {
    return v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  }

  return {
    PALETTE: PALETTE, SEQ: SEQ, SURFACE: SURFACE, INK: INK, GRID: GRID,
    loadData: loadData, register: register, render: render, applyTheme: applyTheme,
    baseOpts: baseOpts, dataZoomOpts: dataZoomOpts, yFmt: yFmt, pct: pct, numFmt: numFmt,
    currentTheme: currentTheme, siteRoot: siteRoot,
  };
})();
