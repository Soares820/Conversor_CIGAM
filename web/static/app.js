// Interacoes da interface web do conversor CIGAM. A navegacao entre
// etapas continua sendo feita por paginas normais do Flask; este script
// cuida so de detalhes de UX no cliente (nenhum estado de negocio aqui).

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function formatarTamanho(bytes) {
  const unidades = ["B", "KB", "MB", "GB"];
  let n = bytes;
  for (const u of unidades) {
    if (n < 1024) return u === "B" ? `${Math.round(n)} ${u}` : `${n.toFixed(1)} ${u}`;
    n /= 1024;
  }
  return `${n.toFixed(1)} TB`;
}

function initTheme() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  const root = document.documentElement;
  btn.addEventListener("click", () => {
    const atual = root.getAttribute("data-theme") ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const proximo = atual === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", proximo);
    try { localStorage.setItem("cigam-theme", proximo); } catch (e) { /* sem storage disponivel */ }
  });
}

function initTopbarScroll() {
  const wrap = document.getElementById("topbar-wrap");
  if (!wrap) return;
  const aplicar = () => wrap.classList.toggle("scrolled", window.scrollY > 6);
  aplicar();
  window.addEventListener("scroll", aplicar, { passive: true });
}

function initToasts() {
  const stack = document.getElementById("toast-stack");
  if (!stack) return;
  const fechar = (toast) => {
    toast.classList.add("closing");
    setTimeout(() => toast.remove(), 200);
  };
  stack.querySelectorAll("[data-toast]").forEach((toast) => {
    const btn = toast.querySelector("[data-toast-close]");
    if (btn) btn.addEventListener("click", () => fechar(toast));
    setTimeout(() => { if (toast.isConnected) fechar(toast); }, 6000);
  });
}

function initDropzones() {
  document.querySelectorAll("[data-dropzone]").forEach((zone) => {
    const input = zone.querySelector('input[type="file"]');
    const nomeSpan = zone.querySelector("[data-filename]");
    const textoEl = nomeSpan ? nomeSpan.querySelector("[data-filename-text]") : null;
    if (!input) return;

    const mostrarArquivo = () => {
      if (input.files && input.files.length > 0) {
        const f = input.files[0];
        if (textoEl) textoEl.textContent = `${f.name} · ${formatarTamanho(f.size)}`;
        if (nomeSpan) nomeSpan.hidden = false;
        zone.classList.add("has-file");
      } else {
        if (nomeSpan) nomeSpan.hidden = true;
        zone.classList.remove("has-file");
      }
    };

    input.addEventListener("change", mostrarArquivo);

    ["dragenter", "dragover"].forEach((evt) => {
      zone.addEventListener(evt, (e) => {
        e.preventDefault();
        zone.classList.add("drag-over");
      });
    });
    ["dragleave", "drop"].forEach((evt) => {
      zone.addEventListener(evt, (e) => {
        e.preventDefault();
        zone.classList.remove("drag-over");
      });
    });
    zone.addEventListener("drop", (e) => {
      const arquivos = e.dataTransfer.files;
      if (arquivos && arquivos.length > 0) {
        input.files = arquivos;
        mostrarArquivo();
      }
    });
  });
}

function initAdvancedToggle() {
  const toggle = document.querySelector("[data-advanced-toggle]");
  const panel = document.querySelector("[data-advanced-panel]");
  if (!toggle || !panel) return;
  toggle.addEventListener("click", () => {
    const aberto = panel.classList.toggle("open");
    toggle.classList.toggle("open", aberto);
  });
}

function initFiltroLista(inputId, itemSelector, textoSelector, emptyId) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const emptyEl = emptyId ? document.getElementById(emptyId) : null;

  const aplicar = () => {
    const q = input.value.toLowerCase();
    let visiveis = 0;
    document.querySelectorAll(itemSelector).forEach((item) => {
      const alvo = textoSelector ? item.querySelector(textoSelector) : item;
      const bate = (alvo || item).textContent.toLowerCase().includes(q);
      item.hidden = !bate;
      if (bate) visiveis += 1;
    });
    if (emptyEl) emptyEl.hidden = visiveis !== 0;
  };

  input.addEventListener("input", aplicar);
}

function initMapaColunas() {
  const tabela = document.getElementById("tabela-mapa");
  if (!tabela) return;
  const linhas = Array.from(tabela.querySelectorAll("tbody tr"));
  const contador = document.getElementById("contador-mapeados");
  const total = linhas.length;

  const avaliarLinha = (linha) => {
    const select = linha.querySelector("select");
    const obrig = linha.querySelector('input[name="obrig"]');
    const dot = linha.querySelector("[data-warn-dot]");
    const mapeada = !!(select && select.value);
    linha.classList.toggle("mapped", mapeada);

    const semDefault = linha.dataset.semDefault === "true";
    const pendente = !!(obrig && obrig.checked) && !mapeada && semDefault;
    linha.classList.toggle("tr-atencao", pendente);
    if (dot) dot.hidden = !pendente;
    return { mapeada, pendente };
  };

  const atualizarContador = () => {
    if (!contador) return;
    let mapeados = 0;
    let pendentes = 0;
    linhas.forEach((linha) => {
      const st = avaliarLinha(linha);
      if (st.mapeada) mapeados += 1;
      if (st.pendente) pendentes += 1;
    });
    let html = `<strong>${mapeados}</strong> de ${total} colunas mapeadas`;
    if (pendentes > 0) {
      html += ` &middot; <span class="counter-warn">${pendentes} obrigatória(s) sem valor</span>`;
    }
    contador.innerHTML = html;
  };

  linhas.forEach((linha) => {
    const select = linha.querySelector("select");
    const obrig = linha.querySelector('input[name="obrig"]');
    if (select) select.addEventListener("change", atualizarContador);
    if (obrig) obrig.addEventListener("change", atualizarContador);
  });
  atualizarContador();
}

function initFiltroOcorrencias() {
  const pills = document.querySelectorAll("[data-filtro-severidade]");
  if (!pills.length) return;
  const linhas = document.querySelectorAll("table.ocorrencias tbody tr");
  pills.forEach((pill) => {
    pill.addEventListener("click", () => {
      pills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      const alvo = pill.dataset.filtroSeveridade;
      linhas.forEach((linha) => {
        linha.hidden = alvo !== "todas" && !linha.classList.contains(alvo);
      });
    });
  });
}

function initFormLoading() {
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", (e) => {
      const btn = form.querySelector('button[type="submit"]');
      if (!btn || btn.disabled) return;
      if (typeof form.reportValidity === "function" && !form.reportValidity()) return;
      btn.disabled = true;
      const texto = btn.dataset.loadingText || "Enviando...";
      btn.innerHTML = `<span class="spinner"></span> ${texto}`;
    });
  });
}

function initStagger(selector, passoMs, maxMs) {
  if (reducedMotion()) return;
  document.querySelectorAll(selector).forEach((el, i) => {
    el.style.animationDelay = `${Math.min(i * passoMs, maxMs)}ms`;
  });
}

function initContadoresAnimados() {
  const nums = document.querySelectorAll("[data-count]");
  if (!nums.length) return;
  if (reducedMotion()) return;

  nums.forEach((el) => {
    const alvo = parseInt(el.dataset.count, 10);
    if (Number.isNaN(alvo)) return;
    const duracao = 550;
    const inicio = performance.now();
    const passo = (agora) => {
      const progresso = Math.min((agora - inicio) / duracao, 1);
      el.textContent = Math.round(progresso * alvo);
      if (progresso < 1) requestAnimationFrame(passo);
      else el.textContent = alvo;
    };
    requestAnimationFrame(passo);
  });
}

function initChecklist() {
  const lista = document.getElementById("checklist-cigam");
  if (!lista) return;
  const itens = Array.from(lista.querySelectorAll(".checklist-item"));
  const barra = document.getElementById("checklist-progress-fill");
  const label = document.getElementById("checklist-progress-label");

  let salvo = {};
  try { salvo = JSON.parse(localStorage.getItem("cigam-checklist") || "{}"); } catch (e) { salvo = {}; }

  const atualizarProgresso = () => {
    const feitos = itens.filter((li) => li.classList.contains("done")).length;
    if (barra) barra.style.width = `${itens.length ? (feitos / itens.length) * 100 : 0}%`;
    if (label) label.textContent = `${feitos} de ${itens.length} concluídos`;
  };

  itens.forEach((li) => {
    const input = li.querySelector('input[type="checkbox"]');
    const id = li.dataset.itemId;
    if (!input || !id) return;
    if (salvo[id]) {
      input.checked = true;
      li.classList.add("done");
    }
    input.addEventListener("change", () => {
      li.classList.toggle("done", input.checked);
      salvo[id] = input.checked;
      try { localStorage.setItem("cigam-checklist", JSON.stringify(salvo)); } catch (e) { /* sem storage */ }
      atualizarProgresso();
    });
  });
  atualizarProgresso();
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initTopbarScroll();
  initToasts();
  initDropzones();
  initAdvancedToggle();
  initFiltroLista("filtro-abas", "#lista-abas li", null, "abas-vazio");
  initFiltroLista("filtro-colunas", "#tabela-mapa tbody tr", "td.col-coluna", "colunas-vazio");
  initMapaColunas();
  initFiltroOcorrencias();
  initFormLoading();
  initStagger(".stat-card", 60, 240);
  initStagger(".download-card", 60, 240);
  initStagger(".info-card", 60, 240);
  initStagger(".table-card:not([hidden])", 25, 300);
  initContadoresAnimados();
  initChecklist();
});
