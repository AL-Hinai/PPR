// Notes panel next to the PDF viewer: the note is filed on the page being read, with the text
// selected in the document (if any) as its quote. The original PDF is never changed.
const form = document.querySelector("[data-note-form]");
if (form) {
  const pageInput = document.querySelector('#pdf-viewer [data-role="page"]');
  const pageLabel = form.querySelector('[data-role="note-page"]');
  const quoteBox = form.querySelector('[data-role="note-quote"]');
  const quoteText = quoteBox.querySelector("span");
  let quote = "";

  const syncPage = () => { pageLabel.textContent = pageInput.value || "1"; };
  window.addEventListener("scroll", () => requestAnimationFrame(syncPage), { passive: true });
  document.getElementById("pdf-viewer").addEventListener("click", () => setTimeout(syncPage));
  pageInput.addEventListener("change", syncPage);

  const setQuote = (text) => {
    quote = text;
    quoteText.textContent = text;
    quoteBox.hidden = !text;
  };
  document.addEventListener("selectionchange", () => {
    const selection = document.getSelection();
    if (!selection || selection.isCollapsed) return;
    if (!selection.anchorNode?.parentElement?.closest("#pdf-viewer .textLayer")) return;
    setQuote(selection.toString().replace(/\s+/g, " ").trim().slice(0, 1000));
  });
  quoteBox.querySelector("button").addEventListener("click", () => setQuote(""));

  form.addEventListener("htmx:configRequest", (event) => {
    event.detail.parameters.page = pageInput.value || "1";
    event.detail.parameters.quote = quote;
  });
  form.addEventListener("htmx:afterRequest", (event) => {
    if (event.detail.successful) { form.reset(); setQuote(""); }
  });
}
