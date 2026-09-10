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
