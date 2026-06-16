#!/usr/bin/env python3
"""`conductor viewer` — a 3D map of the library embeddings, filtered by profile.

Serves a small local web app (stdlib http.server, no web framework) that:
  - lists the "profiles" (category + source) stored in ChromaDB metadata;
  - fetches the bge-m3 embeddings (1024-d) for a filtered slice;
  - reduces them to 3D with PCA (scikit-learn, already pulled by the rag extra);
  - renders an interactive Plotly 3D scatter, colored by category.

  conductor viewer                 # http://localhost:8765, opens the browser
  conductor viewer --port 9000 --no-browser

Needs the rag extra (chromadb + scikit-learn + numpy) and a running Chroma
(`conductor up`). Read-only against the index.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DEFAULT_PORT = 8765
DEFAULT_LIMIT = 4000      # points fetched per view (browser stays smooth)
_PROFILE_PAGE = 5000      # metadata page size (avoids Chroma's SQL var limit)

_profiles_cache: dict | None = None


# --- data access -------------------------------------------------------------

def _collection():
    from .rag.core import get_collection
    return get_collection(create=False)


def _profiles(coll) -> dict:
    """Distinct categories and sources (the filterable 'profiles'). Cached:
    the metadata is scanned once by paging through the whole collection."""
    global _profiles_cache
    if _profiles_cache is not None:
        return _profiles_cache
    cats: dict = {}
    srcs: dict = {}
    offset = 0
    total = coll.count()
    while offset < total:
        page = coll.get(limit=_PROFILE_PAGE, offset=offset, include=["metadatas"])
        metas = page.get("metadatas") or []
        if not metas:
            break
        for m in metas:
            c = (m or {}).get("category")
            s = (m or {}).get("source")
            if c:
                cats[c] = cats.get(c, 0) + 1
            if s:
                srcs[s] = srcs.get(s, 0) + 1
        offset += len(metas)
    _profiles_cache = {
        "total": total,
        "categories": sorted(cats.items()),
        "sources": sorted(srcs.items()),
    }
    return _profiles_cache


def _where(category: str, source: str):
    clauses = []
    if category:
        clauses.append({"category": category})
    if source:
        clauses.append({"source": source})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def _points(coll, category: str, source: str, limit: int) -> dict:
    """Fetches a filtered slice and reduces its embeddings to 3D via PCA."""
    import numpy as np
    from sklearn.decomposition import PCA

    res = coll.get(where=_where(category, source), limit=limit,
                   include=["embeddings", "metadatas", "documents"])
    embs = res.get("embeddings")
    embs = np.asarray(embs) if embs is not None else np.empty((0, 0))
    metas = res.get("metadatas") or []
    docs = res.get("documents") or []
    n = len(metas)
    if n == 0:
        return {"points": [], "variance": 0.0, "count": 0}

    if embs.shape[0] >= 3 and embs.shape[1] >= 3:
        pca = PCA(n_components=3)
        xyz = pca.fit_transform(embs)
        variance = float(pca.explained_variance_ratio_.sum())
    else:  # too few points to project — lay them on a line
        xyz = np.zeros((n, 3))
        variance = 0.0

    points = []
    for i in range(n):
        m = metas[i] or {}
        doc = (docs[i] if i < len(docs) else "") or ""
        preview = doc[:160].replace("\n", " ")
        points.append({
            "x": round(float(xyz[i][0]), 4),
            "y": round(float(xyz[i][1]), 4),
            "z": round(float(xyz[i][2]), 4),
            "category": m.get("category", ""),
            "source": m.get("source", ""),
            "section": m.get("section", ""),
            "preview": preview,
        })
    return {"points": points, "variance": round(variance, 4), "count": n}


# --- HTTP --------------------------------------------------------------------

def _make_handler():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj), "application/json; charset=utf-8")

        def do_GET(self):
            url = urlparse(self.path)
            q = parse_qs(url.query)
            try:
                if url.path in ("/", "/index.html"):
                    self._send(200, INDEX_HTML, "text/html; charset=utf-8")
                elif url.path == "/api/profiles":
                    self._json(_profiles(_collection()))
                elif url.path == "/api/points":
                    coll = _collection()
                    limit = int(q.get("limit", [DEFAULT_LIMIT])[0])
                    self._json(_points(coll, q.get("category", [""])[0],
                                       q.get("source", [""])[0], limit))
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as e:  # noqa: BLE001 — surface errors to the UI
                self._json({"error": str(e)}, 500)

    return Handler


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(prog="conductor viewer",
                                 description="3D map of the library embeddings.")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    try:
        import numpy  # noqa: F401
        import sklearn  # noqa: F401
    except ImportError:
        print("ERROR: the viewer needs the rag extra. Install with:\n"
              "  pip install -e \".[rag]\"   (or: pip install scikit-learn numpy)",
              file=sys.stderr)
        return 2

    server = ThreadingHTTPServer(("127.0.0.1", args.port), _make_handler())
    url = f"http://127.0.0.1:{args.port}"
    print(f"Conductor viewer at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        server.server_close()
    return 0


INDEX_HTML = """<!doctype html>
<html lang="pt-br"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conductor — Library 3D</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root { color-scheme: dark; }
  body { margin:0; font:14px system-ui,sans-serif; background:#0d1117; color:#c9d1d9; }
  header { padding:12px 16px; border-bottom:1px solid #21262d; display:flex;
           gap:12px; align-items:center; flex-wrap:wrap; }
  h1 { font-size:15px; margin:0 12px 0 0; font-weight:600; }
  select, button { background:#161b22; color:#c9d1d9; border:1px solid #30363d;
                   border-radius:6px; padding:6px 10px; font:inherit; }
  button { cursor:pointer; } button:hover { border-color:#58a6ff; }
  label { font-size:12px; color:#8b949e; margin-right:4px; }
  #status { margin-left:auto; font-size:12px; color:#8b949e; }
  #plot { width:100vw; height:calc(100vh - 54px); }
</style></head>
<body>
<header>
  <h1>Library 3D <span style="color:#8b949e;font-weight:400">· PCA(1024→3)</span></h1>
  <span><label>Categoria (perfil)</label><select id="category"></select></span>
  <span><label>Source</label><select id="source"></select></span>
  <span><label>Limite</label>
    <select id="limit">
      <option>2000</option><option selected>4000</option>
      <option>8000</option><option>15000</option>
    </select></span>
  <button id="load">Carregar</button>
  <span id="status">carregando perfis…</span>
</header>
<div id="plot"></div>
<script>
const $ = s => document.querySelector(s);
let PROFILES = null;

async function loadProfiles() {
  const r = await fetch('/api/profiles'); PROFILES = await r.json();
  if (PROFILES.error) { $('#status').textContent = 'erro: ' + PROFILES.error; return; }
  const cat = $('#category'), src = $('#source');
  cat.innerHTML = '<option value="">(todas as categorias)</option>' +
    PROFILES.categories.map(([c,n]) => `<option value="${c}">${c} (${n})</option>`).join('');
  src.innerHTML = '<option value="">(todos os sources)</option>' +
    PROFILES.sources.map(([s,n]) => `<option value="${s}">${s} (${n})</option>`).join('');
  $('#status').textContent = PROFILES.total.toLocaleString() + ' chunks no índice';
}

function palette(cats) {
  const colors = ['#58a6ff','#3fb950','#f778ba','#d29922','#a371f7','#ff7b72',
                  '#79c0ff','#56d364','#e3b341','#bc8cff'];
  const map = {}; let i = 0;
  for (const c of cats) map[c] = colors[i++ % colors.length];
  return map;
}

async function loadPoints() {
  const cat = $('#category').value, src = $('#source').value, lim = $('#limit').value;
  $('#status').textContent = 'carregando pontos…';
  const r = await fetch(`/api/points?category=${encodeURIComponent(cat)}&source=${encodeURIComponent(src)}&limit=${lim}`);
  const d = await r.json();
  if (d.error) { $('#status').textContent = 'erro: ' + d.error; return; }
  if (!d.count) { $('#status').textContent = 'nenhum ponto para esse filtro'; Plotly.purge('plot'); return; }
  // group by category for a colored legend
  const byCat = {};
  for (const p of d.points) (byCat[p.category] ??= []).push(p);
  const colorMap = palette(Object.keys(byCat));
  const traces = Object.entries(byCat).map(([c, pts]) => ({
    type:'scatter3d', mode:'markers', name:c,
    x:pts.map(p=>p.x), y:pts.map(p=>p.y), z:pts.map(p=>p.z),
    text:pts.map(p=>`<b>${p.source}</b><br>${p.section||''}<br>${p.preview}`),
    hoverinfo:'text',
    marker:{ size:2.5, color:colorMap[c], opacity:0.75 },
  }));
  Plotly.newPlot('plot', traces, {
    paper_bgcolor:'#0d1117', font:{color:'#c9d1d9'},
    margin:{l:0,r:0,t:0,b:0}, showlegend:true,
    legend:{bgcolor:'rgba(0,0,0,0)'},
    scene:{ xaxis:{title:'PC1'}, yaxis:{title:'PC2'}, zaxis:{title:'PC3'},
            bgcolor:'#0d1117' },
  }, {responsive:true});
  $('#status').textContent = `${d.count.toLocaleString()} pontos · variância 3D ${(d.variance*100).toFixed(1)}%`;
}

$('#load').addEventListener('click', loadPoints);
loadProfiles();
</script>
</body></html>"""


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
