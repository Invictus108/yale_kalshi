document.getElementById("navToggle")?.addEventListener("click", () => {
  const nav = document.getElementById("siteNav");
  const btn = document.getElementById("navToggle");
  if (!nav || !btn) return;
  const open = nav.classList.toggle("open");
  btn.setAttribute("aria-expanded", open ? "true" : "false");
});

const search = document.getElementById("marketSearch");
const cards = [...document.querySelectorAll(".market-card")];
const filters = [...document.querySelectorAll("[data-filter]")];
let selectedFilter = "all";
function filterMarkets() {
  const term = (search?.value || "").trim().toLowerCase();
  let count = 0;
  for (const card of cards) {
    const status = card.dataset.status;
    const matchesStatus = selectedFilter === "all" || (selectedFilter === "open" ? status === "open" : status !== "open");
    card.hidden = !(matchesStatus && card.dataset.search.includes(term));
    if (!card.hidden) count++;
  }
  const counter = document.getElementById("marketCount");
  if (counter) counter.textContent = count + (count === 1 ? " market" : " markets");
  const empty = document.getElementById("noMatches");
  if (empty) empty.hidden = count > 0 || cards.length === 0;
}
search?.addEventListener("input", filterMarkets);
filters.forEach(button => button.addEventListener("click", () => {
  selectedFilter = button.dataset.filter;
  filters.forEach(item => {
    const active = item === button;
    item.classList.toggle("active", active);
    item.setAttribute("aria-pressed", String(active));
  });
  filterMarkets();
}));
document.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    const nav = document.getElementById("siteNav");
    if (nav?.classList.contains("open")) {
      nav.classList.remove("open");
      const toggle = document.getElementById("navToggle");
      toggle?.setAttribute("aria-expanded", "false");
      toggle?.focus();
    }
  }
});
document.querySelectorAll(".chat").forEach(chat => { chat.scrollTop = chat.scrollHeight; });

/** Shared Chart.js line helper for cash / bet mark series. */
window.yalshiLineChart = function yalshiLineChart(canvas, series, opts) {
  if (!canvas || !series || series.length < 2) return null;
  if (!window.Chart) {
    const message = document.createElement("p");
    message.className = "meta";
    message.textContent = "Chart unavailable. Your balances and positions are shown above. Refresh to try again.";
    canvas.replaceWith(message);
    return null;
  }
  const valueKey = opts.valueKey || "mark";
  const label = opts.label || "Value";
  const color = opts.color || "#00356b";
  return new Chart(canvas, {
    type: "line",
    data: {
      labels: series.map((p) => p.t),
      datasets: [{
        label,
        data: series.map((p) => p[valueKey]),
        borderColor: color,
        backgroundColor: opts.fill || "rgba(0, 53, 107, 0.10)",
        fill: true,
        tension: 0.25,
        pointRadius: series.length > 24 ? 0 : 3,
        pointHoverRadius: 5,
        pointBackgroundColor: color,
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            afterLabel: (item) => {
              const p = series[item.dataIndex];
              if (!p) return "";
              const bits = [];
              if (p.note) bits.push(p.note);
              else if (p.kind) bits.push(p.kind);
              if (p.price_yes != null) bits.push(`YES ${p.price_yes}¢`);
              return bits.join(" · ");
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8, color: "#5a6b7d", font: { size: 11 } },
          grid: { display: false },
        },
        y: {
          ticks: { color: "#5a6b7d", font: { size: 11 } },
          grid: { color: "rgba(207, 216, 227, 0.7)" },
        },
      },
    },
  });
};
