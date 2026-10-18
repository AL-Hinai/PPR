// Small behaviours that would otherwise need inline event handlers (blocked by the Content-Security-Policy).
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-print]")) window.print();
});
document.addEventListener("change", (event) => {
  if (event.target.matches("select[data-autosubmit]")) event.target.form.submit();
});
