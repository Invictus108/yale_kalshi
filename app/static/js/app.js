document.getElementById("navToggle")?.addEventListener("click", () => {
  const nav = document.getElementById("siteNav");
  const btn = document.getElementById("navToggle");
  if (!nav || !btn) return;
  const open = nav.classList.toggle("open");
  btn.setAttribute("aria-expanded", open ? "true" : "false");
});
