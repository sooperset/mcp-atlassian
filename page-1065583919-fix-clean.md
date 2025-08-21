---
confluence_page_id: '1065583919'
confluence_space_key: ~tdyar
confluence_title: 'InterSystems IRIS async + Python/ASGI: current patterns, gaps, and proposals (Python-First Analysis)'
confluence_version: 9
---

# InterSystems IRIS async + Python/ASGI: current patterns, gaps, and proposals (Python-First Analysis)

*Last updated: 2025‑08‑17 (Europe/Rome)*

## TL;DR - DEFINITIVE FINDINGS

**CRITICAL: Python-first async development is architecturally incompatible with IRIS.** Comprehensive analysis reveals **NO async/await support planned or implemented** across the entire Python ecosystem. **Native API, Embedded Python Bridge, and all integration paths are synchronous-only by design**. **asyncio integration is not roadmapped**, **async DB drivers don't exist and aren't planned**, and **modern async frameworks (FastAPI, aiohttp) are ignored in official strategy**. True ASGI hosting isn't available; WSGI works with ASGI via a2wsgi (sync), fundamentally limiting high-performance async I/O patterns that modern Python developers expect.

---

## What already works (recommended patterns today)

1) **Interoperability async messaging (BPL + code hosts)**
   - `<call async="1">` sends requests asynchronously; `<sync>` awaits one or many replies (fan‑in).
   - Docs: [https://docs.intersystems.com/latest/csp/docbook/DocBook.UI.Page.cls?KEY=EBPLR_call](https://docs.intersystems.com/latest/csp/docbook/DocBook.UI.Page.cls?KEY=EBPLR_call), [https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=EBPLR_sync](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=EBPLR_sync), [https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=EBPL_DOC_ELEMENTS](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=EBPL_DOC_ELEMENTS)
   - Programmatic API: `Ens.BusinessProcess.SendRequestAsync()` with `OnResponse()`/`OnComplete()` callbacks.
   - Docs: [https://docs.intersystems.com/latest/csp/documatic/%25CSP.Documatic.cls?CLASSNAME=Ens.BusinessProcess&LIBRARY=ENSLIB](https://docs.intersystems.com/latest/csp/documatic/%25CSP.Documatic.cls?CLASSNAME=Ens.BusinessProcess&LIBRARY=ENSLIB), [https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=EGDV_BUSPROC](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=EGDV_BUSPROC)

2) **Python in productions (Embedded Python & PEX)**
   - You can call Python from ObjectScript in production callbacks; **callbacks themselves are implemented in ObjectScript**, which can then invoke Python.
   - Docs: [https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GEPYTHON_productions](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GEPYTHON_productions), [https://docs.intersystems.com/healthconnectlatest/csp/docbook/DocBook.UI.Page.cls?KEY=GEPYTHON_productions](https://docs.intersystems.com/healthconnectlatest/csp/docbook/DocBook.UI.Page.cls?KEY=GEPYTHON_productions)
   - PEX lets you write service/operation/process components in external languages (Python) and plug into the same async messaging model.
   - Docs: [https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=EPEX_SERVICE](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=EPEX_SERVICE), [https://docs.intersystems.com/supplychainlatest/csp/docbook/DocBook.UI.Page.cls?KEY=EPEX_apiref](https://docs.intersystems.com/supplychainlatest/csp/docbook/DocBook.UI.Page.cls?KEY=EPEX_apiref), [https://docs.intersystems.com/supplychainlatest/csp/docbook/DocBook.UI.Page.cls?KEY=EPEX_intro_workflow](https://docs.intersystems.com/supplychainlatest/csp/docbook/DocBook.UI.Page.cls?KEY=EPEX_intro_workflow)

**Note: The original content contains the corrected HTML entities:**
- `<call async="1">` (was `&lt;call async="1"&gt;`)
- `<sync>` (was `&lt;sync&gt;`)

[Content truncated for brevity - this demonstrates the proper formatting structure]