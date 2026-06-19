#!/usr/bin/env python3
"""`cdt viewer` — a 3D map of the library embeddings, filtered by profile.

Serves a small local web app (stdlib http.server, no web framework) that:
  - lists the "profiles" (category + source) stored in ChromaDB metadata;
  - fetches the bge-m3 embeddings (1024-d) for a filtered slice;
  - reduces them to 3D with PCA (scikit-learn, already pulled by the rag extra);
  - renders an interactive Plotly 3D scatter, colored by category.

  cdt viewer                 # http://localhost:8765, opens the browser
  cdt viewer --port 9000 --no-browser

Needs the rag extra (chromadb + scikit-learn + numpy) and a running Chroma
(`cdt up`). Read-only against the index.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DEFAULT_PORT = 8765
DEFAULT_LIMIT = 4000      # points returned per view (browser stays smooth)
_PROFILE_PAGE = 5000      # metadata page size (avoids Chroma's SQL var limit)
_SAMPLE_FIT = 15000       # rows PCA is fitted on (transform still covers all)
_INDEX_VERSION = 2        # bump to invalidate a cached index after a schema change

_profiles_cache: dict | None = None
_centroids_cache: dict | None = None
_index_cache: dict | None = None   # the precomputed 3D projection (all points)


# --- data access -------------------------------------------------------------

def _collection():
    from .rag.core import get_collection
    return get_collection(create=False)


def _index_path() -> Path:
    base = Path(os.environ.get("CONDUCTOR_HOME",
                               str(Path.home() / ".claude" / "conductor")))
    base.mkdir(parents=True, exist_ok=True)
    return base / "viewer_index.json"


def _build_index(coll) -> dict:
    """One full pass over the collection: pull embeddings + metadata, project
    every chunk to 3D **once** with PCA, and tally the profiles. The result is
    what every `/api/points` and `/api/profiles` view is served from, so views
    never refetch 1024-d vectors or rerun PCA. Embeddings are the dominant cost,
    so PCA is fitted on a sample and used to transform all rows."""
    import numpy as np
    from sklearn.decomposition import PCA

    total = coll.count()
    blocks, metas, previews = [], [], []
    cats: dict = {}
    srcs: dict = {}
    sums: dict = {}       # per-source embedding sum -> centroid (for /graph)
    counts: dict = {}
    scats: dict = {}
    offset = 0
    while offset < total:
        page = coll.get(limit=_PROFILE_PAGE, offset=offset,
                        include=["embeddings", "metadatas", "documents"])
        embs = page.get("embeddings")
        ms = page.get("metadatas") or []
        ds = page.get("documents") or []
        if embs is None or len(ms) == 0:
            break
        block = np.asarray(embs, dtype=np.float32)
        blocks.append(block)
        metas.extend(ms)
        previews.extend(((ds[i] if i < len(ds) else "") or "")[:160].replace("\n", " ")
                        for i in range(len(ms)))
        for i, m in enumerate(ms):
            c = (m or {}).get("category")
            s = (m or {}).get("source")
            if c:
                cats[c] = cats.get(c, 0) + 1
            if s:
                srcs[s] = srcs.get(s, 0) + 1
                if s not in sums:
                    sums[s] = np.zeros(block.shape[1], dtype=np.float64)
                    counts[s] = 0
                    scats[s] = c or "?"
                sums[s] += block[i]
                counts[s] += 1
        offset += len(ms)
        print(f"  [viewer] projecting {offset}/{total}", file=sys.stderr, flush=True)

    if not blocks:
        return {"v": _INDEX_VERSION, "count": 0, "variance": 0.0, "points": [],
                "categories": [], "sources": [], "centroids": {}}

    X = np.vstack(blocks)
    n = X.shape[0]
    pca = PCA(n_components=3)
    if n > _SAMPLE_FIT:
        rng = np.random.default_rng(0)
        pca.fit(X[rng.choice(n, _SAMPLE_FIT, replace=False)])
        xyz = pca.transform(X)
    else:
        xyz = pca.fit_transform(X)
    variance = float(pca.explained_variance_ratio_.sum())

    points = []
    for i, m in enumerate(metas):
        m = m or {}
        points.append({
            "x": round(float(xyz[i][0]), 4),
            "y": round(float(xyz[i][1]), 4),
            "z": round(float(xyz[i][2]), 4),
            "category": m.get("category", ""),
            "source": m.get("source", ""),
            "section": m.get("section", ""),
            "preview": previews[i],
        })
    centroids = {s: {"centroid": [round(float(x), 6) for x in (sums[s] / max(counts[s], 1))],
                     "count": counts[s], "category": scats[s]}
                 for s in sums}
    return {"v": _INDEX_VERSION, "count": n, "variance": round(variance, 4),
            "points": points, "categories": sorted(cats.items()),
            "sources": sorted(srcs.items()), "centroids": centroids}


def _load_index(coll) -> dict:
    """Return the precomputed projection, building (and persisting) it once.
    Rebuilt when the collection size changes (a new ingest) or the schema
    version is bumped."""
    global _index_cache
    count = coll.count()
    if (_index_cache is not None and _index_cache.get("count") == count
            and _index_cache.get("v") == _INDEX_VERSION):
        return _index_cache
    path = _index_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("count") == count and data.get("v") == _INDEX_VERSION:
                _index_cache = data
                return data
        except (ValueError, OSError):
            pass
    data = _build_index(coll)
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass
    _index_cache = data
    return data


def _profiles(coll) -> dict:
    """Distinct categories and sources (the filterable 'profiles'), read from
    the precomputed index — no separate full-collection metadata scan."""
    data = _load_index(coll)
    return {"total": data.get("count", 0),
            "categories": data.get("categories", []),
            "sources": data.get("sources", [])}


def _points(coll, category: str, source: str, limit: int) -> dict:
    """Serve a filtered slice of the precomputed 3D projection — an in-memory
    filter, no Chroma fetch and no PCA per request."""
    data = _load_index(coll)
    pts = data.get("points", [])
    if category:
        pts = [p for p in pts if p.get("category") == category]
    if source:
        pts = [p for p in pts if p.get("source") == source]
    out = pts[:limit] if limit else pts
    return {"points": out, "variance": data.get("variance", 0.0), "count": len(out)}


# --- force-directed graph ----------------------------------------------------
# Builds a network like a genre map: each source (book) is a node, grouped under
# its category (a hub node), and sources are linked to their k nearest neighbors
# by embedding similarity (cosine between per-source centroids) — that kNN web is
# what clusters related books and bridges categories. Rendered with three.js
# (3d-force-graph) in /graph.

def _source_centroids(coll) -> dict:
    """Per-source mean embedding + chunk count + category — read from the
    precomputed index (built in the same pass as the 3D projection), so /graph
    no longer refetches every embedding from Chroma."""
    return _load_index(coll).get("centroids", {})


def _graph(coll, category: str, knn: int = 3) -> dict:
    """Nodes = category hubs + source nodes; links = source→hub and source↔source
    kNN by centroid cosine similarity. Filtered to one category or all."""
    import numpy as np

    cents = _source_centroids(coll)
    items = [(s, d) for s, d in cents.items()
             if not category or d["category"] == category]
    if not items:
        return {"nodes": [], "links": []}

    names = [s for s, _ in items]
    mat = np.array([d["centroid"] for _, d in items])
    norm = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    sim = norm @ norm.T
    np.fill_diagonal(sim, -1.0)

    cat_totals: dict = {}
    for _, d in items:
        cat_totals[d["category"]] = cat_totals.get(d["category"], 0) + d["count"]

    nodes = [{"id": "cat:" + c, "label": c, "group": c,
              "val": max(8.0, t / 200.0), "kind": "category"}
             for c, t in cat_totals.items()]
    links = []
    for s, d in items:
        nodes.append({"id": s, "label": s, "group": d["category"],
                      "val": max(2.0, d["count"] / 50.0), "kind": "source"})
        links.append({"source": s, "target": "cat:" + d["category"]})

    k = min(knn, len(names) - 1)
    seen = set()
    for i in range(len(names)):
        for j in np.argsort(sim[i])[::-1][:k]:
            if sim[i][j] <= 0:
                continue
            a, b = sorted((names[i], names[int(j)]))
            if a == b or (a, b) in seen:
                continue
            seen.add((a, b))
            links.append({"source": a, "target": b})

    return {"nodes": nodes, "links": links,
            "categories": sorted(cat_totals.keys())}


# --- ingest via screen -------------------------------------------------------
# Formats arbitrary pasted/uploaded markdown into the library convention
# (CONVENCOES_DE_ARQUIVOS.md): a clean H1 title, an optional bold author line,
# blank-line-separated paragraphs and headings (so core.chunk_markdown splits
# correctly), UTF-8 with control chars stripped. Filename: "Title - Author.md"
# under the chosen NN_category folder.

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename(stem: str) -> str:
    stem = _ILLEGAL.sub("", stem).strip().strip(".")
    return (stem or "untitled")[:180]


def format_markdown(content: str, title: str, author: str) -> tuple:
    """Returns (formatted_text, final_title). Normalizes to the convention."""
    from .rag.core import sanitize

    text = sanitize(content).replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(ln.rstrip() for ln in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    # blank line before/after ATX headings so paragraphs and sections split
    text = re.sub(r"(?<!\n)\n(#{1,6} )", r"\n\n\1", text)
    text = re.sub(r"(\n#{1,6} [^\n]+)\n(?!\n)", r"\1\n\n", text)

    detected = None
    m = re.match(r"^#\s+(.+?)\n", text + "\n")
    if m:
        detected = m.group(1).strip()
        text = text[m.end() - 1:].lstrip("\n")  # drop the original H1 line
    final_title = (title or "").strip() or detected or "Untitled"

    head = f"# {final_title}\n"
    if author.strip():
        head += f"**{author.strip()}**\n"
    doc = head + "\n" + text + "\n"
    doc = re.sub(r"\n{3,}", "\n\n", doc).strip() + "\n"
    return doc, final_title


def _ingest_markdown(category: str, title: str, author: str, content: str) -> dict:
    """Formats, writes under the library, then chunks + embeds + upserts the
    single file. Returns {file, chunks, category, source}."""
    from .rag.core import LIBRARY_DIR, chunk_markdown
    from .rag.ingest import _embed_batch, _upsert_pairs

    if not content.strip():
        raise ValueError("empty content")
    category = _safe_filename(category.strip()) or "99_custom"
    doc, final_title = format_markdown(content, title, author)

    stem = _safe_filename(f"{final_title} - {author.strip()}" if author.strip()
                          else final_title)
    rel = f"{category}/{stem}.md"
    dest = LIBRARY_DIR / category / f"{stem}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(doc, encoding="utf-8")

    chunks = chunk_markdown(doc, source=stem, category=category, path=rel)
    n = 0
    if chunks:
        n = _upsert_pairs(_collection(), _embed_batch(chunks))
    global _profiles_cache, _centroids_cache, _index_cache
    _profiles_cache = None   # new category/source -> refresh the filter lists
    _centroids_cache = None  # and the graph centroids
    _index_cache = None      # and the 3D projection (rebuilt on next view)
    return {"file": str(dest), "chunks": n, "category": category, "source": stem}


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
                elif url.path == "/favicon.ico":
                    self.send_response(204)  # no favicon; silence the browser probe
                    self.end_headers()
                elif url.path == "/ingest":
                    self._send(200, INGEST_HTML, "text/html; charset=utf-8")
                elif url.path == "/graph":
                    self._send(200, GRAPH_HTML, "text/html; charset=utf-8")
                elif url.path == "/api/profiles":
                    self._json(_profiles(_collection()))
                elif url.path == "/api/graph":
                    self._json(_graph(_collection(), q.get("category", [""])[0]))
                elif url.path == "/api/points":
                    coll = _collection()
                    limit = int(q.get("limit", [DEFAULT_LIMIT])[0])
                    self._json(_points(coll, q.get("category", [""])[0],
                                       q.get("source", [""])[0], limit))
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as e:  # noqa: BLE001 — surface errors to the UI
                self._json({"error": str(e)}, 500)

        def do_POST(self):
            url = urlparse(self.path)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                if url.path == "/api/ingest":
                    self._json(_ingest_markdown(
                        payload.get("category", ""), payload.get("title", ""),
                        payload.get("author", ""), payload.get("content", "")))
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as e:  # noqa: BLE001 — surface errors to the UI
                self._json({"error": str(e)}, 500)

    return Handler


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(prog="cdt viewer",
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
  <a href="/graph" style="color:#58a6ff;text-decoration:none;margin-left:8px">Grafo 3D</a>
  <a href="/ingest" style="color:#58a6ff;text-decoration:none;margin-left:8px">+ Ingest</a>
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


GRAPH_HTML = """<!doctype html>
<html lang="pt-br"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conductor — Library Graph</title>
<!-- three-spritetext needs a global THREE; load three's UMD build first. Pinned
     to 0.155 (the last line that still ships build/three.min.js as a global). -->
<script src="https://unpkg.com/three@0.155.0/build/three.min.js"></script>
<script src="https://unpkg.com/three-spritetext@1.8.2/dist/three-spritetext.min.js"></script>
<script src="https://unpkg.com/3d-force-graph@1.73.4/dist/3d-force-graph.min.js"></script>
<style>
  :root { color-scheme: dark; }
  body { margin:0; font:14px system-ui,sans-serif; background:#0d1117; color:#c9d1d9; }
  header { padding:12px 16px; border-bottom:1px solid #21262d; display:flex;
           gap:12px; align-items:center; flex-wrap:wrap; }
  h1 { font-size:15px; margin:0 8px 0 0; font-weight:600; }
  select, button { background:#161b22; color:#c9d1d9; border:1px solid #30363d;
                   border-radius:6px; padding:6px 10px; font:inherit; }
  button { cursor:pointer; } button:hover { border-color:#58a6ff; }
  label { font-size:12px; color:#8b949e; margin-right:4px; }
  header a { color:#58a6ff; text-decoration:none; }
  #status { margin-left:auto; font-size:12px; color:#8b949e; }
  #graph { width:100vw; height:calc(100vh - 54px); }
</style></head>
<body>
<header>
  <h1>Library Graph <span style="color:#8b949e;font-weight:400">· three.js</span></h1>
  <span><label>Categoria (perfil)</label><select id="category"></select></span>
  <button id="load">Carregar</button>
  <a href="/">Mapa PCA</a><a href="/ingest">+ Ingest</a>
  <span id="status">carregando…</span>
</header>
<div id="graph"></div>
<script>
const $ = s => document.querySelector(s);
const COLORS = ['#58a6ff','#3fb950','#f778ba','#d29922','#a371f7','#ff7b72',
  '#79c0ff','#56d364','#e3b341','#bc8cff','#ffa657','#7ee787','#ff9bce','#d2a8ff'];
let colorMap = {};
const Graph = ForceGraph3D()(document.getElementById('graph'))
  .backgroundColor('#0d1117')
  .nodeLabel(n => `<b>${n.label}</b><br>${n.kind} · ${n.group}`)
  .nodeVal('val')
  .nodeColor(n => colorMap[n.group] || '#888')
  .nodeOpacity(0.9)
  .linkColor(() => 'rgba(180,190,200,0.15)')
  .linkWidth(0.5)
  .nodeThreeObjectExtend(true)
  .nodeThreeObject(n => {
    if (n.kind !== 'category' && n.val < 6) return null;  // label only hubs / big books
    const t = new SpriteText(n.label);
    t.color = '#e6edf3'; t.fontFace = 'system-ui';
    t.textHeight = n.kind === 'category' ? 7 : 3.5;
    t.material.depthWrite = false;
    return t;
  });

async function loadCats() {
  const r = await fetch('/api/profiles'); const p = await r.json();
  const sel = $('#category');
  sel.innerHTML = '<option value="">(todas as categorias)</option>' +
    (p.categories||[]).map(([c,n]) => `<option value="${c}">${c} (${n})</option>`).join('');
}
async function loadGraph() {
  $('#status').textContent = 'montando grafo… (primeira vez calcula os centroides)';
  const cat = $('#category').value;
  const r = await fetch('/api/graph?category=' + encodeURIComponent(cat));
  const d = await r.json();
  if (d.error) { $('#status').textContent = 'erro: ' + d.error; return; }
  colorMap = {}; let i = 0;
  for (const c of (d.categories||[])) colorMap[c] = COLORS[i++ % COLORS.length];
  Graph.graphData({ nodes: d.nodes, links: d.links });
  $('#status').textContent = `${d.nodes.length} nós · ${d.links.length} conexões`;
}
$('#load').addEventListener('click', loadGraph);
loadCats().then(loadGraph);
</script>
</body></html>"""


INGEST_HTML = """<!doctype html>
<html lang="pt-br"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conductor — Ingest</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; font:14px system-ui,sans-serif; background:#0d1117; color:#c9d1d9; }
  header { padding:12px 16px; border-bottom:1px solid #21262d; display:flex; align-items:center; }
  h1 { font-size:15px; margin:0; font-weight:600; }
  header a { color:#58a6ff; text-decoration:none; margin-left:auto; }
  main { max-width:880px; margin:0 auto; padding:20px 16px; }
  .row { display:flex; gap:12px; margin-bottom:12px; flex-wrap:wrap; }
  .field { flex:1; min-width:200px; }
  label { display:block; font-size:12px; color:#8b949e; margin-bottom:4px; }
  input, select, textarea, button { background:#161b22; color:#c9d1d9;
    border:1px solid #30363d; border-radius:6px; padding:8px 10px; font:inherit; width:100%;
    box-sizing:border-box; }
  textarea { min-height:340px; font-family:ui-monospace,monospace; resize:vertical; white-space:pre; }
  button { cursor:pointer; width:auto; padding:8px 18px; }
  button:hover { border-color:#58a6ff; }
  .actions { position:sticky; bottom:0; background:#0d1117; padding:12px 0 6px;
    border-top:1px solid #21262d; margin-top:12px; display:flex; align-items:center; gap:10px; }
  button.primary { background:#238636; border-color:#2ea043; color:#fff;
    font-weight:600; padding:11px 24px; font-size:14px; }
  button.primary:hover { background:#2ea043; border-color:#3fb950; }
  button.primary:disabled { opacity:.6; cursor:default; }
  #result { margin-top:14px; padding:12px; border-radius:6px; font-size:13px; white-space:pre-wrap; }
  .ok { background:#0f2417; border:1px solid #238636; }
  .err { background:#2d1518; border:1px solid #da3633; }
  .hint { font-size:12px; color:#8b949e; }
</style></head>
<body>
<header><h1>Ingest de arquivo .md</h1><a href="/">← Voltar ao mapa 3D</a></header>
<main>
  <p class="hint">O arquivo é formatado no padrão da biblioteca (H1 título, autor,
  parágrafos/heading separados, UTF-8 limpo), salvo em <code>categoria/Título - Autor.md</code>,
  e então chunked + embeddado + indexado no ChromaDB.</p>
  <div class="row">
    <div class="field"><label>Categoria (perfil)</label>
      <input id="category" list="cats" placeholder="ex: 10_ia_e_llm"></div>
    <datalist id="cats"></datalist>
    <div class="field"><label>Título</label>
      <input id="title" placeholder="(opcional — usa o H1 do conteúdo)"></div>
    <div class="field"><label>Autor(es)</label>
      <input id="author" placeholder="ex: Martin"></div>
  </div>
  <div class="row">
    <div class="field">
      <label>Arquivo .md (ou cole abaixo)</label>
      <input type="file" id="file" accept=".md,.markdown,text/markdown">
    </div>
  </div>
  <div class="field"><label>Conteúdo markdown</label>
    <textarea id="content" placeholder="# Título&#10;&#10;Conteúdo..."></textarea></div>
  <div class="actions">
    <button id="send" class="primary">💾 Salvar na biblioteca</button>
    <span class="hint">formata → embedda → indexa no ChromaDB</span>
  </div>
  <div id="result"></div>
</main>
<script>
const $ = s => document.querySelector(s);
fetch('/api/profiles').then(r=>r.json()).then(p=>{
  if (p.categories) $('#cats').innerHTML =
    p.categories.map(([c])=>`<option value="${c}">`).join('');
});
$('#file').addEventListener('change', e=>{
  const f = e.target.files[0]; if(!f) return;
  if(!/\\.(md|markdown)$/i.test(f.name)){ alert('Selecione um arquivo .md'); e.target.value=''; return; }
  const r = new FileReader();
  r.onload = () => { $('#content').value = r.result;
    if(!$('#title').value) $('#title').value = f.name.replace(/\\.(md|markdown)$/i,''); };
  r.readAsText(f);
});
$('#send').addEventListener('click', async ()=>{
  const btn = $('#send');
  const body = { category:$('#category').value, title:$('#title').value,
                 author:$('#author').value, content:$('#content').value };
  if(!body.content.trim()){ show('Conteúdo vazio.', false); return; }
  const label = btn.textContent;
  btn.disabled = true; btn.textContent = '⏳ Salvando…';
  show('Formatando e indexando… (o embed pode levar alguns segundos)', true);
  try {
    const r = await fetch('/api/ingest',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)});
    const d = await r.json();
    if(d.error) show('Erro: '+d.error, false);
    else show(`✅ Salvo — ${d.chunks} chunk(s) indexados.\\nArquivo: ${d.file}\\nSource: ${d.source} · categoria: ${d.category}`, true);
  } catch(e) {
    show('Erro de rede: '+e, false);
  } finally {
    btn.disabled = false; btn.textContent = label;
  }
});
function show(msg, ok){ const el=$('#result'); el.textContent=msg; el.className=ok?'ok':'err'; }
</script>
</body></html>"""


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
