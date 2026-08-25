/* common.js — 全站公共逻辑：导航注入 / TOC 生成 / 代码复制 / 主题切换 */
(function () {
  "use strict";

  var NAV = [
    { href: "index.html", label: "学习路径" },
    { href: "chapters/ch1-data.html", label: "1 数据" },
    { href: "chapters/ch2-factor.html", label: "2 因子" },
    { href: "chapters/ch3-testing.html", label: "3 检验" },
    { href: "chapters/ch4-synthesis.html", label: "4 合成" },
    { href: "chapters/ch5-portfolio.html", label: "5 组合" },
    { href: "chapters/ch6-backtest.html", label: "6 回测" },
    { href: "chapters/ch7-attribution.html", label: "7 归因" },
    { href: "appendix.html", label: "附录" },
    { href: "process.html", label: "研究过程" },
  ];

  function base() {
    // 从当前页面路径推导项目根（相对路径前缀）
    var p = location.pathname.split("/");
    var file = p[p.length - 1];
    return file.indexOf(".html") === -1 ? "" : "";
  }

  /* ---- 导航注入 ---- */
  function injectNav() {
    var navEl = document.getElementById("site-nav");
    if (!navEl) return;
    var cur = location.pathname.split("/").pop() || "index.html";
    navEl.innerHTML = NAV.map(function (n) {
      var cls = cur === n.href ? " class=\"active\"" : "";
      return "<a href=\"" + n.href + "\"" + cls + ">" + n.label + "</a>";
    }).join("");
  }

  /* ---- 主题切换 ---- */
  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem("qr-theme"); } catch (e) { /* ignore */ }
    var theme = saved === "dark" || saved === "light" ? saved
      : (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
    var btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.textContent = theme === "dark" ? "☀ 浅色" : "🌙 深色";
      btn.addEventListener("click", function () {
        var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        btn.textContent = next === "dark" ? "☀ 浅色" : "🌙 深色";
        try { localStorage.setItem("qr-theme", next); } catch (e) { /* ignore */ }
        if (window.ChartKit) ChartKit.applyTheme(next);
        window.dispatchEvent(new CustomEvent("qr:theme", { detail: { theme: next } }));
      });
    }
  }

  /* ---- 页内目录（TOC） ---- */
  function initToc() {
    var toc = document.getElementById("page-toc");
    if (!toc) return;
    var content = document.querySelector(".content");
    if (!content) return;
    var heads = content.querySelectorAll("h2, h3");
    if (heads.length < 2) { toc.style.display = "none"; return; }
    var html = "<h4>本页目录</h4>";
    var items = [];
    heads.forEach(function (h, i) {
      if (!h.id) h.id = "sec-" + i;
      html += "<a href=\"#" + h.id + "\" data-target=\"" + h.id + "\" class=\"" +
        (h.tagName === "H3" ? "h3" : "") + "\">" + h.textContent + "</a>";
      items.push({ id: h.id, el: h });
    });
    toc.innerHTML = html;
    // 滚动高亮
    var links = toc.querySelectorAll("a");
    var current = "";
    function onScroll() {
      var pos = window.scrollY + 100;
      var cur = "";
      items.forEach(function (it) {
        if (it.el.offsetTop <= pos) cur = it.id;
      });
      if (cur !== current) {
        current = cur;
        links.forEach(function (a) {
          a.classList.toggle("active", a.dataset.target === cur);
        });
      }
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* ---- 代码块：语言标签 + 复制按钮 ---- */
  function initCodeBlocks() {
    document.querySelectorAll("pre").forEach(function (pre) {
      if (pre.parentElement.classList.contains("code-block")) return;
      var wrapper = document.createElement("div");
      wrapper.className = "code-block";
      pre.parentNode.insertBefore(wrapper, pre);
      wrapper.appendChild(pre);
      // 语言标签
      var first = (pre.textContent || "").trim();
      var lang = "";
      var m = first.match(/^(?:#|\/\/|\/\*)?\s*(?:python|python3|bash|json|sql)\b/i);
      if (m) lang = m[1].toLowerCase() || m[0].toLowerCase();
      if (/^# -\*-/.test(first) || /import (pandas|numpy)/.test(first)) lang = "python";
      if (lang) {
        var tag = document.createElement("span");
        tag.className = "lang";
        tag.textContent = lang;
        wrapper.appendChild(tag);
      }
      // 复制按钮
      var btn = document.createElement("button");
      btn.className = "copy-btn";
      btn.textContent = "复制";
      btn.addEventListener("click", function () {
        navigator.clipboard.writeText(pre.textContent).then(function () {
          btn.textContent = "✓ 已复制";
          setTimeout(function () { btn.textContent = "复制"; }, 1500);
        });
      });
      wrapper.appendChild(btn);
    });
  }

  /* ---- 图表渲染（数据为预计算 JSON，直接渲染，无需懒加载） ---- */
  function initCharts() {
    var boxes = document.querySelectorAll(".chart-box");
    boxes.forEach(function (box) {
      var name = box.dataset.chart;
      if (name && window.ChartKit) ChartKit.render(box, name);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    injectNav();
    initTheme();
    initToc();
    initCodeBlocks();
    initCharts();
  });
})();
