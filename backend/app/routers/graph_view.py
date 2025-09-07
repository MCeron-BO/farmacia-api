# app/routers/graph_view.py
from fastapi import APIRouter, Response

router = APIRouter()

MERMAID = r"""
%%{init: {
  "theme": "dark",
  "flowchart": {
    "curve": "basis",
    "htmlLabels": true,
    "padding": 22,
    "nodeSpacing": 120,
    "rankSpacing": 120
  },
  "themeVariables": {
    "fontFamily": "Inter, ui-sans-serif, system-ui, Segoe UI, Roboto, Arial",
    "fontSize": "18px",
    "textWrapWidth": 340,
    "primaryColor": "#0f172a",
    "primaryTextColor": "#e5e7eb",
    "primaryBorderColor": "#3b82f6",
    "clusterBkg": "#0b1220",
    "clusterBorderColor": "#334155",
    "lineColor": "#94a3b8"
  }
}}%%

flowchart TB

  %% ====== NODOS (primero definimos todo, sin aristas) ======
  start([Start]):::init
  guard{policy guard?}:::safety
  safe([safety message<br>*4141 / 131 / telemed]):::safety
  classify([classify]):::analysis

  need_loc{need location?}:::route
  vdm([search vademecum]):::agent
  smtk([smalltalk via<br>vademecum]):::agent
  fb([fallback message]):::agent

  ask_loc([ask for location]):::cta
  pharm([find open<br>pharmacies]):::agent

  persist([persist memory]):::final
  reply([Reply]):::final

  %% ====== ARISTAS (luego conectamos) ======
  start --> guard
  guard -- Yes --> safe
  safe --> persist
  guard -- No --> classify

  classify -- pharmacy --> need_loc
  classify -- vademecum --> vdm
  classify -- smalltalk --> smtk
  classify -- unknown --> fb

  need_loc -- No --> ask_loc
  ask_loc --> persist
  need_loc -- Yes --> pharm
  pharm --> persist

  vdm --> persist
  smtk --> persist
  fb  --> persist
  persist --> reply

  %% ====== SECCIONES ======
  subgraph S0[Inicializacion]
    start
  end

  subgraph S1[Seguridad]
    guard
    safe
  end

  subgraph S2[Analisis]
    classify
  end

  subgraph S3[Enrutamiento / Requisitos]
    need_loc
    vdm
    smtk
    fb
  end

  subgraph S4[Agentes especializados]
    ask_loc
    pharm
  end

  subgraph S5[Finalizacion]
    persist
    reply
  end

  %% ====== ESTILOS ======
  classDef init     fill:#1f2937,stroke:#334155,color:#e5e7eb,stroke-width:1.5px;
  classDef analysis fill:#1e3a8a,stroke:#3b82f6,color:#e5e7eb,stroke-width:1.6px;
  classDef route    fill:#374151,stroke:#4b5563,color:#e5e7eb,stroke-width:1.5px;
  classDef agent    fill:#283548,stroke:#3b4961,color:#e5e7eb,stroke-width:1.5px;
  classDef final    fill:#111827,stroke:#334155,color:#e5e7eb,stroke-width:1.5px;
  classDef cta      fill:#185a37,stroke:#2e7d4c,color:#e5e7eb,stroke-width:1.5px;
  classDef safety   fill:#3a2f18,stroke:#eab308,color:#fef9c3,stroke-width:1.7px;
"""

HTML = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Graph</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <style>
    :root {{ color-scheme: dark; }}
    body {{ background:#0b1220; color:#e5e7eb; font-family:Inter,system-ui,Segoe UI,Roboto,Arial; }}
    .wrap {{ max-width:1600px; margin:24px auto; padding:12px; }}
    .row {{ display:flex; gap:8px; align-items:center; margin-bottom:12px; flex-wrap:wrap; }}
    a {{ color:#93c5fd; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    button {{ background:#111827; border:1px solid #1f2937; color:#e5e7eb; padding:8px 12px; border-radius:10px; cursor:pointer; }}
    button:hover {{ border-color:#3b82f6; }}
    #graph {{ background:#0f1828; border:1px solid #1f2a3a; border-radius:12px; padding:12px; overflow:auto; }}
    #graph svg {{ width:100%; height:auto; }}
    .err {{ margin-top:10px; color:#fca5a5; white-space:pre-wrap; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h2>Graph</h2>
    <div class="row">
      <button onclick="location.reload()">⟳ Recargar</button>
      <button onclick="navigator.clipboard.writeText(window.__MM);">📋 Copiar Mermaid</button>
      <small>Si algo falla, abre <a href="/debug/graph.txt" target="_blank">/debug/graph.txt</a>.</small>
    </div>
    <div id="graph">Renderizando…</div>
    <div id="err" class="err"></div>
  </div>

  <script>
    (function() {{
      const mm = {MERMAID!r};
      window.__MM = mm;

      try {{
        mermaid.initialize({{
          startOnLoad: false,
          theme: "dark",
          securityLevel: "loose",
          flowchart: {{ curve: "basis", htmlLabels: true, padding: 22, nodeSpacing: 120, rankSpacing: 120 }},
          themeVariables: {{
            fontFamily: "Inter, ui-sans-serif, system-ui, Segoe UI, Roboto, Arial",
            fontSize: "18px",
            textWrapWidth: 340
          }}
        }});
        mermaid.parse(mm);
        mermaid.render("graphSvg", mm).then(({{
          svg, bindFunctions
        }}) => {{
          const c = document.getElementById("graph");
          c.innerHTML = svg;
          if (bindFunctions) bindFunctions(c);
        }}).catch(e => {{
          document.getElementById("graph").textContent = "No se pudo renderizar.";
          document.getElementById("err").textContent = "Render error: " + (e && e.message ? e.message : e);
        }});
      }} catch (e) {{
        document.getElementById("graph").textContent = "No se pudo inicializar Mermaid.";
        document.getElementById("err").textContent = "Init error: " + (e && e.message ? e.message : e);
      }}
    }})();
  </script>
</body>
</html>
"""

@router.get("/debug/graph", tags=["debug"])
def view_graph():
    return Response(content=HTML, media_type="text/html")

@router.get("/debug/graph.txt", tags=["debug"])
def view_graph_txt():
    return Response(content=MERMAID, media_type="text/plain; charset=utf-8")
