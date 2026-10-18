# Dossier assistant: data protection

The dossier assistant answers questions about a medicine's dossier. Dossiers are confidential commercial
information submitted by pharmaceutical companies. Before the assistant is switched on with a language model,
the Head of Department (with Ministry IT and legal advice) should decide where that model runs. This note
describes what data moves, and the three ways to run the assistant.

## What the assistant sends to the language model

For every question, PPR sends the configured model (`ASSISTANT_BASE_URL`):

- the question and the last few turns of the conversation;
- a system prompt naming the reader's role and the application they are working on (reference number,
  product name);
- the results of the read-only tools the model calls: the application overview, document lists, search
  passages, the text of up to 8 pages per document read (at most 16,000 characters per tool result), and the
  validation findings.

It sends only what the reader may already open: every tool is limited by `Application.objects.visible_to(user)`,
and an applicant's assistant never receives the internal assessment. Reviewers' notes on dossier pages are not
available to the assistant at all. Document files themselves (PDFs) are never uploaded; only extracted text.

PPR keeps the conversation (questions, answers, tools used and token counts) in its own database.

## Three ways to run it

| Option | Setting | Data leaves PPR? | Answer quality | Cost |
|---|---|---|---|---|
| **A. Offline** (current default without a key) | `ASSISTANT_API_KEY` empty, or `ASSISTANT_PROVIDER=offline` | No | Matching passages with page links, no written answer | None |
| **B. External API** (DeepSeek by default, any OpenAI-compatible service) | `ASSISTANT_API_KEY`, `ASSISTANT_BASE_URL`, `ASSISTANT_MODEL` | Yes, to the provider's servers, possibly outside Oman | Written, cited answers | Per-token fees |
| **C. Self-hosted model** (e.g. vLLM or Ollama on Ministry infrastructure) | `ASSISTANT_BASE_URL` pointing at the internal server | No, if the server is inside the Ministry network | Depends on the model and hardware | Hardware and operation |

With option B, the drawer tells every reader which host receives the text. Before choosing B, check the
provider's terms on data retention, use of submitted data for training, data location, and whether a data
processing agreement is available; compare them with Ministry policy on confidential commercial information.

Option C needs a server PPR can reach. A PythonAnywhere free account can only call an allow-list of hosts; a paid
account can call any host, but an internal Ministry server must also be reachable from PythonAnywhere (or PPR
hosted inside the Ministry network).

## Recommendation

Keep option A until the decision is made. If option B is approved, start with a limited group of reviewers and
review the stored conversations after the first weeks. If dossier confidentiality rules out sending text abroad,
plan option C with Ministry IT.

## Checking a configured model

After setting the key (option B) or the internal URL (option C), run:

```powershell
.venv\Scripts\python manage.py assistant_smoke_test --application <id>
```

It asks one question as the Head of Department, prints the provider, the tools used, the answer, latency and
token counts, and fails unless the answer cites dossier pages that exist. Run it once per model change.

## Decision record

| Item | Decision | Date | By |
|---|---|---|---|
| Option (A / B / C) | | | |
| Provider and model | | | |
| Data processing agreement | | | |
| Readers allowed to use the assistant | | | |
