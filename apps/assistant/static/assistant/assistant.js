/*
 * The dossier assistant drawer (Alpine.js), ported from Roaa's assistant store + drawer.
 *
 * Loaded without `defer`, before Alpine starts, so `assistant()` exists when
 * Alpine evaluates `x-data`. Context is the page URL; the server resolves it to
 * a medicine / sequence / document. Answers stream as newline-delimited JSON.
 */
(function () {
  const OPEN_KEY = "ppr-assistant-open";
  const PIN_KEY = "ppr-assistant-pin";
  const FOLLOW_SLACK = 0.1;

  function store(kind, key, value) {
    try {
      const s = kind === "local" ? window.localStorage : window.sessionStorage;
      if (value === undefined) return s.getItem(key);
      if (value === null) s.removeItem(key);
      else s.setItem(key, value);
    } catch (e) {
      return null;
    }
    return null;
  }

  function csrf() {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (match) return decodeURIComponent(match[1]);
    const header = document.body.getAttribute("hx-headers");
    try {
      return JSON.parse(header)["X-CSRFToken"];
    } catch (e) {
      return "";
    }
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  window.assistant = function () {
    return {
      config: { urls: {}, t: {} },
      t: { source: {}, stopped: {} },
      open: false,
      status: "idle",
      provider: "",
      context: null,
      links: {},
      messages: [],
      pinned: null,
      draft: "",
      thinking: false,
      answer: "",
      liveSteps: [],
      failure: "",
      following: true,

      init() {
        const node = document.getElementById("assistant-config");
        this.config = node ? JSON.parse(node.textContent) : this.config;
        this.t = this.config.t;
        try {
          this.pinned = JSON.parse(store("session", PIN_KEY) || "null");
        } catch (e) {
          this.pinned = null;
        }
        // The drawer stays open across page loads, as Roaa's root store keeps it across routes.
        if (store("local", OPEN_KEY) === "1") this.show();
        // Back from the PDF tab: the document just opened is now the context.
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "visible" && this.open && !this.thinking) this.load();
        });
      },

      page() {
        return window.location.pathname + window.location.search;
      },

      async show() {
        this.open = true;
        store("local", OPEN_KEY, "1");
        await this.load();
        this.$nextTick(() => this.$refs.composer && this.$refs.composer.focus());
      },

      close() {
        this.open = false;
        store("local", OPEN_KEY, "0");
      },

      async load() {
        if (this.status !== "ready") this.status = "loading";
        const params = new URLSearchParams({ page: this.page() });
        if (this.pinned) params.set("pinned", JSON.stringify(this.pinned));
        try {
          const response = await fetch(this.config.urls.session + "?" + params, {
            headers: { Accept: "application/json" },
            credentials: "same-origin",
          });
          if (!response.ok) throw new Error(response.status);
          const data = await response.json();
          this.context = data.context;
          this.messages = data.messages;
          this.links = data.links || {};
          this.provider = data.provider;
          if (this.pinned && data.context.document_source !== "pinned") this.unpin(false);
          this.status = "ready";
          this.scroll(true);
        } catch (e) {
          this.status = "failed";
        }
      },

      pin(detail) {
        this.pinned = { sequence_id: detail.sequence_id, path: detail.path };
        store("session", PIN_KEY, JSON.stringify(this.pinned));
        this.show();
      },

      unpin(reload = true) {
        this.pinned = null;
        store("session", PIN_KEY, null);
        if (reload) this.load();
      },

      suggestions() {
        if (this.context && this.context.document) return this.t.suggest_doc;
        if (this.context && this.context.application) return this.t.suggest_app;
        return this.t.suggest_none;
      },

      send() {
        const question = this.draft.trim();
        if (!question || this.thinking) return;
        this.draft = "";
        this.ask(question);
      },

      async ask(question) {
        this.failure = "";
        this.answer = "";
        this.liveSteps = [];
        this.thinking = true;
        this.following = true;
        this.messages.push({ id: "pending-" + Date.now(), role: "user", content: question });
        this.scroll(true);
        try {
          const response = await fetch(this.config.urls.ask, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
            body: JSON.stringify({ question, page: this.page(), pinned: this.pinned }),
          });
          if (!response.ok || !response.body) throw new Error(response.status);
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let newline;
            while ((newline = buffer.indexOf("\n")) >= 0) {
              const line = buffer.slice(0, newline).trim();
              buffer = buffer.slice(newline + 1);
              if (line) this.handle(JSON.parse(line));
            }
          }
          if (buffer.trim()) this.handle(JSON.parse(buffer));
        } catch (e) {
          this.failure = this.t.failed;
        } finally {
          this.thinking = false;
          this.answer = "";
          this.liveSteps = [];
          this.scroll();
          this.$nextTick(() => this.$refs.composer && this.$refs.composer.focus());
        }
      },

      handle(event) {
        switch (event.type) {
          case "context":
            this.context = event.context;
            Object.assign(this.links, event.links || {});
            break;
          case "step":
            // Prose written before a tool call is narration, not the answer.
            this.answer = "";
            this.liveSteps.push(event);
            break;
          case "text":
            this.answer += event.text;
            break;
          case "done":
            this.messages.push(event.message);
            break;
          case "stopped":
            this.failure = this.t.stopped[event.reason] || event.reason;
            break;
          case "error":
            this.failure = this.t.unavailable;
            break;
        }
        this.scroll();
      },

      onScroll() {
        const log = this.$refs.log;
        const remaining = log.scrollHeight - log.scrollTop - log.clientHeight;
        this.following = remaining <= log.clientHeight * FOLLOW_SLACK;
      },

      scroll(force = false) {
        this.$nextTick(() => {
          const log = this.$refs.log;
          if (log && (force || this.following)) log.scrollTop = log.scrollHeight;
        });
      },

      async newChat() {
        if (this.thinking) return;
        await fetch(this.config.urls.new, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": csrf() },
        });
        this.messages = [];
        this.failure = "";
        this.load();
      },

      fileUrl(application, number, path, page) {
        const sequences = this.links[String(application)] || {};
        const id = sequences[number];
        if (!id) return "";
        const url = this.config.urls.file
          .replace("999999", application)
          .replace("888888", id)
          .replace("PATH", path.split("/").map(encodeURIComponent).join("/"));
        return page ? url + "#page=" + page : url;
      },

      /* A small, safe Markdown: escape first, then bullets, quotes, bold, code and citations. */
      render(text, application) {
        const inline = (line) =>
          line
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/`([^`]+)`/g, '<code class="rounded bg-white px-1 font-mono text-[12px] ring-1 ring-slate-200">$1</code>')
            .replace(/\[(\d{4})\/([^\]\s]+?)(?:,?\s+p(?:age|\.)?\s*(\d+)(?:[–-]\d+)?)?\]/g, (match, number, path, page) => {
              const name = path.split("/").pop();
              const label = name + (page ? " p." + page : "");
              const href = application ? this.fileUrl(application, number, path, page) : "";
              const chip = "inline-flex max-w-full items-center gap-1 rounded-md bg-white px-1.5 py-0.5 align-baseline font-mono text-[11px] text-brand-700 ring-1 ring-brand-200";
              return href
                ? `<a href="${href}" target="_blank" rel="noopener" class="${chip} hover:bg-brand-50" title="${number}/${path}" dir="ltr">${label}</a>`
                : `<span class="${chip}" title="${number}/${path}" dir="ltr">${label}</span>`;
            });
        const out = [];
        let list = null;
        for (const raw of escapeHtml(text || "").split("\n")) {
          const line = raw.trimEnd();
          const bullet = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
          if (bullet) {
            if (!list) {
              list = [];
              out.push(list);
            }
            list.push(inline(bullet[1]));
            continue;
          }
          list = null;
          if (!line.trim()) out.push("");
          else if (/^&gt;\s?/.test(line)) out.push(`<blockquote class="border-s-2 border-brand-300 ps-2 text-slate-600">${inline(line.replace(/^&gt;\s?/, ""))}</blockquote>`);
          else out.push(`<p>${inline(line)}</p>`);
        }
        return out
          .map((item) => (Array.isArray(item) ? `<ul class="list-disc space-y-0.5 ps-5">${item.map((li) => `<li>${li}</li>`).join("")}</ul>` : item))
          .filter((item) => item !== "")
          .join("");
      },
    };
  };
})();
