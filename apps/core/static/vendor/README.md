# Vendored front-end libraries

Served from this site instead of a CDN, so the Content-Security-Policy can be limited to `'self'`
(`apps/core/middleware.py`) and the pages keep working without internet access to jsDelivr.

| File | Package | Source (jsDelivr) | SHA-256 |
|---|---|---|---|
| `htmx.min.js` | htmx.org 2.0.4 | `htmx.org@2.0.4/dist/htmx.min.js` | `e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447` |
| `alpine.min.js` | alpinejs 3.14.8 | `alpinejs@3.14.8/dist/cdn.min.js` | `b600e363d99d95444db54acbfb2deffec9ae792aa99a09229bcda078e5b55643` |
| `pdfjs/pdf.min.js` | pdfjs-dist 4.10.38 | `pdfjs-dist@4.10.38/build/pdf.min.mjs` | `27fc2a057a00f92a4334ad06e17dbd7259912954e9fb7f76400bcca5fd190a9c` |
| `pdfjs/pdf.worker.min.js` | pdfjs-dist 4.10.38 | `pdfjs-dist@4.10.38/build/pdf.worker.min.mjs` | `1baa1844c89c80a5b2797c916e75ab29254be46d8e9cb53cb6364d7aad84be36` |
| `pdfjs/pdf_viewer.css` | pdfjs-dist 4.10.38 | `pdfjs-dist@4.10.38/web/pdf_viewer.css` | `f684e5c55f3baa4516519e8e0d4543726ab2c4223a0ded8c71ed9d5bf3782e7b` |

The PDF.js modules are renamed from `.mjs` to `.js` so every static server sends them as JavaScript.
The viewer only uses the text layer, so the images `pdf_viewer.css` refers to for PDF.js's own toolbar are not
included. Alpine.js evaluates its `x-*` expressions with `Function`, which is why the policy keeps `'unsafe-eval'`.

To upgrade, download the new versions, update this table and the version in the templates' comments, and re-run
the browser checks in `docs/validation/` (document viewer, assistant drawer, notifications).
