/* CannEx — 客户端 Mermaid 渲染器
 * agent 流式输出纯文本含 ```mermaid 围栏块；本脚本扫描消息 DOM，
 * 用 CDN mermaid 渲染为 SVG。agent 侧零改动。设计见
 * docs/superpowers/specs/2026-05-31-webchat-output-visualization-design.md
 *
 * 关键 1：Chainlit 的代码块组件把 ```mermaid 渲染成
 *   <div class="relative my-2">           ← 代码卡片（锚点）
 *     <header><span>mermaid</span> 复制按钮</header>
 *     <pre class="m-0"><code class="language-txt ...">源码</code></pre>
 * 因为 mermaid 不是 highlight.js 注册语言，<code> 的 class 被降级成 language-txt，
 * 故不能靠 class 选择器识别，改用「首行关键字特征 + mermaid.parse 校验」检测。
 *
 * 关键 2：美化不靠默认皮肤。theme:'base' + themeVariables 动态读取 Chainlit
 * 的 shadcn CSS 调色板（--foreground/--border/--muted 等），随暗/亮主题切换；
 * 布局优先用 ELK（正交、边不交叉），CDN 失败则回退默认 dagre。
 */
(function () {
  const MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/+esm";
  const ELK_CDN = "https://cdn.jsdelivr.net/npm/@mermaid-js/layout-elk@0/+esm";
  // mermaid 各图种的首行关键字（用于在丢失 language class 时识别代码块）
  const MERMAID_RE =
    /^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|gantt|pie|journey|mindmap|timeline|gitGraph|quadrantChart|requirementDiagram|xychart-beta|sankey-beta|block-beta|C4Context)\b/;
  let mermaidPromise = null;
  let seq = 0;

  function currentTheme() {
    return document.documentElement.classList.contains("dark") ? "dark" : "default";
  }

  // 读取 Chainlit 的 shadcn CSS 变量（HSL 三元组，如 "340 92% 52%"）并包成颜色串。
  // 读的是「当前生效值」，故天然跟随暗/亮主题。
  function cssColor(name, fallback) {
    try {
      const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return raw ? `hsl(${raw})` : fallback;
    } catch (e) {
      return fallback;
    }
  }

  function buildThemeVariables() {
    const fg = cssColor("--foreground", "#1f2328");
    const border = cssColor("--border", "#d0d7de");
    const muted = cssColor("--muted", "#eaeef2");
    const mutedFg = cssColor("--muted-foreground", "#656d76");
    const card = cssColor("--card", "#ffffff");
    const bg = cssColor("--background", "#ffffff");
    return {
      fontFamily: 'ui-monospace, "JetBrains Mono", Menlo, Consolas, "PingFang SC", monospace',
      fontSize: "14px",
      // 节点：跟卡片色做淡填充 + 细边框 + 正文色文字（干净、不刺眼）
      primaryColor: card,
      mainBkg: card,
      primaryBorderColor: border,
      nodeBorder: border,
      primaryTextColor: fg,
      nodeTextColor: fg,
      // 次要/第三类节点（菱形、分支等）用 muted 区分层次
      secondaryColor: muted,
      tertiaryColor: muted,
      secondaryBorderColor: border,
      tertiaryBorderColor: border,
      // 连线 + 边标签
      lineColor: mutedFg,
      edgeLabelBackground: bg,
      // 子图（subgraph）容器
      clusterBkg: muted,
      clusterBorder: border,
      titleColor: fg,
    };
  }

  function loadMermaid() {
    if (!mermaidPromise) {
      mermaidPromise = import(MERMAID_CDN)
        .then(async (m) => {
          const mermaid = m.default;
          // 尝试加载 ELK 布局引擎（正交布局、边不交叉），失败则用默认 dagre
          let layout = "dagre";
          try {
            const elk = await import(ELK_CDN);
            mermaid.registerLayoutLoaders(elk.default);
            layout = "elk";
          } catch (e) {
            console.warn("[cannex] ELK 布局加载失败，回退默认布局", e);
          }
          mermaid.initialize({
            startOnLoad: false,
            securityLevel: "strict",
            theme: "base",
            themeVariables: buildThemeVariables(),
            layout: layout,
            flowchart: {
              curve: "basis",
              nodeSpacing: 48,
              rankSpacing: 56,
              padding: 14,
              useMaxWidth: true,
              htmlLabels: true,
            },
          });
          // theme 仍记录当前明暗，供 rerenderAll 判定（themeVariables 已含实际色值）
          mermaid.__cannexTheme = currentTheme();
          return mermaid;
        })
        .catch((e) => {
          console.warn("[cannex] mermaid CDN 加载失败，保留源码块降级", e);
          mermaidPromise = null;
          throw e;
        });
    }
    return mermaidPromise;
  }

  function hashCode(s) {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
    return String(h) + "_" + s.length;
  }

  function looksLikeMermaid(text) {
    const first = text.split("\n").map((s) => s.trim()).find((s) => s.length > 0) || "";
    return MERMAID_RE.test(first);
  }

  async function renderBlock(codeEl, source) {
    // 锚点：整张代码卡片（含 mermaid 标签头 + 复制按钮），渲染后整体隐藏。
    // 找不到卡片则退回 <pre>（仅隐藏源码，标签头会残留，但图仍渲染）。
    const card = codeEl.closest("div.relative.my-2") || codeEl.closest("pre");
    if (!card) return;

    const h = hashCode(source);
    if (card.dataset.mmdHash === h && card.dataset.mmdState === "done") {
      // 已渲染：确认 SVG 容器还在（React 重渲染可能抹掉我们注入的兄弟节点）。
      // 还在则跳过；被抹掉则向下走重新渲染，实现自愈。
      const sib = card.nextElementSibling;
      if (sib && sib.classList && sib.classList.contains("cannex-mermaid")) return;
    }
    // 全局去重：该源码的图已在别处渲染（React 重建卡片产生的重复卡片）
    // → 只隐藏本卡片，不再渲染新 host，避免重复 + 抖动
    if (document.querySelector('.cannex-mermaid[data-mmd-hash="' + h + '"]')) {
      card.style.display = "none";
      card.dataset.mmdHash = h;
      card.dataset.mmdState = "done";
      return;
    }
    if (card.dataset.mmdState === "rendering") return;
    card.dataset.mmdState = "rendering";

    let mermaid;
    try {
      mermaid = await loadMermaid();
    } catch (e) {
      delete card.dataset.mmdState;
      return;
    }

    try {
      await mermaid.parse(source);
    } catch (e) {
      delete card.dataset.mmdState;
      return; // 不完整/非法：保留源码块，等下次 mutation 重试
    }

    card.dataset.mmdHash = h;
    try {
      const id = "mmd-" + seq++;
      const { svg } = await mermaid.render(id, source);
      let host = card.nextElementSibling;
      if (!(host && host.classList && host.classList.contains("cannex-mermaid"))) {
        host = document.createElement("div");
        host.className = "cannex-mermaid";
        card.after(host);
      }
      // securityLevel:"strict" 下 mermaid 已消毒 SVG，innerHTML 安全；依赖 CDN 完整性
      host.innerHTML = svg;
      host.dataset.mmdHash = h; // 供 GC 按源码去重
      card.style.display = "none";
      card.dataset.mmdState = "done";
    } catch (e) {
      card.style.display = "";
      card.dataset.mmdState = "error";
    }
  }

  // GC：清掉被 React 重渲染孤立/重复的旧图。
  // React 流式重渲染会重建代码卡片节点，使之前注入的 SVG host 游离堆积。
  // 规则：host 必须紧跟在一张「隐藏的 done 卡片」之后，且同一源码 hash 只保留第一个。
  function gcMermaidHosts() {
    const seen = new Set();
    document.querySelectorAll(".cannex-mermaid").forEach((host) => {
      const prev = host.previousElementSibling;
      const backed = prev && prev.dataset && prev.dataset.mmdState === "done";
      const key = host.dataset.mmdHash || "";
      if (!backed || seen.has(key)) {
        host.remove();
        return;
      }
      seen.add(key);
    });
  }

  function scan() {
    gcMermaidHosts();
    // 覆盖两种代码块出口：有语言的 <pre><code>、无语言的 <code class="whitespace-pre-wrap">
    document.querySelectorAll("pre code, code.whitespace-pre-wrap").forEach((codeEl) => {
      const source = (codeEl.textContent || "").trim();
      if (!source) return;
      if (!(codeEl.classList.contains("language-mermaid") || looksLikeMermaid(source))) return;
      renderBlock(codeEl, source);
    });
  }

  let timer = null;
  function debouncedScan() {
    clearTimeout(timer);
    timer = setTimeout(scan, 120);
  }

  function rerenderAll() {
    // 删掉所有已渲染的图（host），并复位所有卡片，让 scan 用新主题重渲染
    document.querySelectorAll(".cannex-mermaid").forEach((host) => host.remove());
    document.querySelectorAll("[data-mmd-state]").forEach((card) => {
      delete card.dataset.mmdHash;
      delete card.dataset.mmdState;
      card.style.display = "";
    });
    mermaidPromise = null; // 用新主题的 themeVariables 重新 init
    debouncedScan();
  }

  new MutationObserver(debouncedScan).observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });

  let themeTimer = null;
  new MutationObserver(() => {
    clearTimeout(themeTimer);
    themeTimer = setTimeout(rerenderAll, 80);
  }).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  });

  debouncedScan();
})();
