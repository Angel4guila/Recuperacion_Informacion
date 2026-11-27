from flask import Flask, render_template_string, request, send_file
import sys
from pathlib import Path

# Configuración de rutas para importar el backend
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR / 'backend'))

from evaluacion import calcular_metricas, cargar_juicios
from motor_busqueda import (
    cargar_json, buscar, construir_mapa_formas, contexto_primer_resultado_del_corpus, sugerir_consulta,
)

app = Flask(__name__)

# Cargar recursos una sola vez al iniciar el servidor web para que sea rápido
DATA_DIR = BASE_DIR / 'data'
ruta_indice = DATA_DIR / "indice" / "indice_invertido.json"
ruta_pagerank = DATA_DIR / "graph" / "pagerank.json"
ruta_rastreo = DATA_DIR / "sin_procesar" / "resultados_rastreo.json"
ruta_juicios = DATA_DIR / "evaluacion" / "juicios_relevancia.json"

datos_indice = cargar_json(ruta_indice)
indice = datos_indice["indice"]
total_docs = datos_indice["estadisticas"]["total_documentos"]
pagerank = cargar_json(ruta_pagerank)
datos_rastreo = cargar_json(ruta_rastreo) if ruta_rastreo.exists() else {"paginas": []}
info_paginas = {p["url"]: p for p in datos_rastreo.get("paginas", [])}
formas_terminos = construir_mapa_formas(datos_rastreo.get("paginas", []), indice)
RESULTADOS_POR_PAGINA = 5
consultas_evaluadas = {}
k_evaluacion = None
if ruta_juicios.is_file():
    try:
        k_evaluacion, particiones = cargar_juicios(ruta_juicios, indice, pagerank)
        consultas_evaluadas = {
            item["consulta"].casefold(): item
            for consultas in particiones.values()
            for item in consultas
        }
    except (OSError, ValueError, TypeError, AttributeError) as error:
        app.logger.warning("No se pudieron cargar las consultas de evaluación: %s", error)

# Plantilla HTML incrustada minimalista estilo buscador clásico
HTML_TEMPLATE = """
{% macro mostrar_metricas(valores, k=none) -%}
    <dl class="metrics">
        {% for clave, etiqueta in (("precision", "Precision"), ("recall", "Recall"), ("f1", "F1")) %}
            <div>
                <dt>{{ etiqueta }}{% if k is not none %}@{{ k }}{% endif %}</dt>
                <dd>{{ "%.2f"|format(valores[clave] * 100) }} %</dd>
            </div>
        {% endfor %}
    </dl>
{%- endmacro %}
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Mini-Google BUAP</title>
    <style>
        * { box-sizing: border-box; }
        body {
            --texto: #f8fafb;
            --texto-suave: #d6dde0;
            --borde-vidrio: rgba(255, 255, 255, .23);
            --superficie-vidrio: rgba(17, 23, 28, .79);
            --filtro-fondo: rgba(9, 13, 16, .24);
            isolation: isolate;
            min-height: 100vh;
            margin: 0;
            font-family: Arial, sans-serif;
            background: #141a1f;
            color: var(--texto);
        }
        body::before {
            content: "";
            position: fixed;
            z-index: -1;
            inset: 0;
            background: linear-gradient(var(--filtro-fondo), var(--filtro-fondo)),
                        url("{{ url_for('fondo') }}") 60% center / cover no-repeat;
            pointer-events: none;
        }
        .has-results { --filtro-fondo: rgba(9, 13, 16, .5); }
        .has-results::before { inset: -24px; filter: blur(18px); }
        .container {
            max-width: 1240px;
            margin-inline: max(0px, calc((100% - 1280px) / 2)) auto;
            padding: 28px clamp(16px, 3vw, 36px);
        }
        .home .container {
            display: grid;
            align-content: center;
            min-height: 100vh;
            min-height: 100svh;
        }
        .home .layout {
            grid-template-columns: minmax(0, 540px);
            grid-template-areas: "content" "side";
            gap: 18px;
        }
        .home .test-form { max-width: 355px; }
        .layout {
            display: grid;
            grid-template-columns: minmax(0, 290px) minmax(0, 1fr);
            grid-template-areas: "side content";
            gap: 24px;
            align-items: start;
        }
        .side-column { grid-area: side; display: grid; gap: 14px; }
        .search-column { grid-area: content; display: grid; gap: 16px; min-width: 0; }
        .panel, .result, .primary-form input, button, .pagination {
            background: var(--superficie-vidrio);
            border: 1px solid var(--borde-vidrio);
            backdrop-filter: blur(12px);
        }
        .panel { padding: 18px; border-radius: 16px; }
        .panel h2 { font-size: 16px; margin: 0 0 12px; }
        .panel p { font-size: 14px; line-height: 1.45; margin: 8px 0 0; }
        .panel a { color: inherit; overflow-wrap: anywhere; text-underline-offset: 3px; }
        .search-panel { align-self: stretch; display: grid; gap: 10px; align-content: start; }
        .test-form { position: relative; z-index: 1; }
        .test-form h2 { margin: 0; }
        .test-picker { position: relative; min-width: 0; }
        .test-picker summary {
            display: flex; align-items: center; justify-content: space-between; gap: 12px;
            min-height: 42px; padding: 10px 12px; border: 1px solid var(--borde-vidrio);
            border-radius: 10px; background: rgba(255, 255, 255, .08);
            font-size: 14px; list-style: none; cursor: pointer;
        }
        .test-picker summary::-webkit-details-marker { display: none; }
        .test-picker summary::after {
            content: ""; flex: 0 0 7px; height: 7px; border: solid var(--texto-suave);
            border-width: 0 1px 1px 0; transform: rotate(45deg);
        }
        .test-picker[open] summary::after { transform: rotate(225deg); }
        .test-options {
            position: absolute; inset: calc(100% + 8px) 0 auto; max-height: min(320px, 36vh);
            margin: 0; padding: 6px; list-style: none; overflow: auto; overscroll-behavior: contain;
            scrollbar-width: thin; scrollbar-color: #78948f #253036;
            border: 1px solid var(--borde-vidrio); border-radius: 12px;
            background: rgba(27, 34, 39, .97); backdrop-filter: blur(16px);
            box-shadow: 0 12px 28px rgba(0, 0, 0, .32);
        }
        .home .test-options { inset: auto 0 calc(100% + 8px); }
        .test-options button {
            width: 100%; padding: 9px 10px; font-size: 14px; line-height: 1.35; text-align: left;
            background: none; backdrop-filter: none; border-color: transparent;
        }
        .test-options button:is(:hover, :focus-visible, [aria-current="true"]) {
            background: rgba(171, 218, 209, .14);
            color: #c1ebe2;
        }
        .test-options button:focus-visible { outline-offset: -2px; }
        button { border-radius: 8px; padding: 10px 15px; color: inherit; font: inherit; cursor: pointer; }
        button:hover { background: rgba(52, 59, 64, .88); }
        :focus-visible { outline: 2px solid #fff; outline-offset: 3px; }
        .search-box { max-width: 590px; margin: 0 auto 28px; text-align: center; }
        .search-box h1 { margin: 0 0 14px; font-size: clamp(24px, 4vw, 32px); }
        .search-box h1 a { color: inherit; text-decoration: none; }
        .search-box h1 a:hover { text-decoration: underline; text-underline-offset: 5px; }
        .home .search-box { max-width: 540px; margin: 0 0 12px; text-align: left; }
        .home .search-box h1 { font-size: clamp(34px, 6vw, 64px); letter-spacing: -.045em; }
        .search-box span { color: var(--texto-suave); }
        .search-box h1, .results-heading { text-shadow: 0 2px 12px rgba(0, 0, 0, .72); }
        .search-form { display: flex; gap: 8px; }
        .primary-form { width: 100%; max-width: 590px; gap: 10px; }
        .primary-form input { flex: 1; min-width: 0; padding: 12px 16px; font-size: 16px; color: inherit; border-radius: 24px; }
        .primary-form input::placeholder { color: var(--texto-suave); }
        .primary-form button { padding: 12px 20px; font-size: 16px; border-radius: 24px; }
        #titulo-resumen, #titulo-contexto { overflow-wrap: anywhere; }
        .context-section { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--borde-vidrio); }
        .context-section h3 { margin: 0; font-size: 15px; }
        .summary, .metrics { margin: 0; }
        .summary > div, .metrics > div { display: flex; justify-content: space-between; gap: 10px; margin: 8px 0; font-size: 14px; }
        .summary dd, .metrics dd { margin: 0; font-weight: bold; white-space: nowrap; }
        .metrics { margin-top: 12px; padding-top: 4px; border-top: 1px solid var(--borde-vidrio); }
        .metrics-cutoff { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--borde-vidrio); }
        .metrics-cutoff summary { font-size: 14px; font-weight: bold; cursor: pointer; }
        .metrics-cutoff .metrics { margin-top: 4px; border-top: 0; }
        .expected { margin: 12px 0 0; padding-left: 18px; font-size: 14px; line-height: 1.45; }
        .expected li + li { margin-top: 6px; }
        .expected span { display: block; color: var(--texto-suave); }
        .results-heading { font-size: 18px; margin: 0 0 14px; overflow-wrap: anywhere; }
        .result { padding: 20px; margin-bottom: 15px; border-radius: 16px; }
        .url { color: #a8d6cd; font-size: 13px; margin-bottom: 6px; overflow-wrap: anywhere; }
        .title { color: #fff9ed; font-size: 18px; text-decoration: none; font-weight: bold; }
        .title:hover { text-decoration: underline; }
        .snippet { color: #c8d0d5; font-size: 14px; line-height: 1.45; margin-top: 5px; }
        .score { color: #b9c2c8; font-size: 12px; margin-top: 8px; }
        .score strong { color: #edcda5; font-variant-numeric: tabular-nums; }
        .empty-state { text-align: center; }
        .pagination { display: flex; justify-content: center; align-items: center; gap: 16px; margin: 24px auto; width: fit-content; padding: 10px 16px; border-radius: 24px; }
        .pagination a { color: inherit; text-decoration: none; }
        .pagination a:hover { text-decoration: underline; }
        @media (max-width: 680px) {
            .has-results .layout {
                grid-template-columns: minmax(0, 1fr);
                grid-template-areas: "search" "test" "summary" "results";
                gap: 18px;
            }
            .has-results .search-column, .has-results .side-column { display: contents; }
            .has-results .primary-form { grid-area: search; }
            .has-results .test-form { grid-area: test; }
            .has-results .sidebar { grid-area: summary; }
            .has-results .results { grid-area: results; }
            .home .container { align-content: end; padding-bottom: 10svh; }
            .search-box { margin-bottom: 18px; }
        }
    </style>
</head>
<body class="{{ 'has-results' if query else 'home' }}">
    <div class="container">
    <header class="search-box">
        <h1><a href="{{ url_for('index') }}">Mini-Google <span>BUAP</span></a></h1>
    </header>
    <div class="layout">
    {% if consultas_evaluadas or query %}
    <div class="side-column">
        {% if consultas_evaluadas %}
            <form class="panel search-panel test-form" aria-labelledby="titulo-pruebas" method="GET" action="{{ url_for('index') }}">
                <h2 id="titulo-pruebas">Consultas de prueba</h2>
                <details class="test-picker" id="consulta-prueba">
                    <summary>{{ consulta_evaluada.consulta if consulta_evaluada else 'Elige una consulta' }}</summary>
                    <ul class="test-options">
                        {% for item in consultas_evaluadas %}
                            <li><button type="submit" name="q" value="{{ item.consulta }}"
                                {% if item == consulta_evaluada %}aria-current="true"{% endif %}>{{ item.consulta }}</button></li>
                        {% endfor %}
                    </ul>
                </details>
            </form>
        {% endif %}
    {% if query %}
    <aside class="sidebar" aria-label="Información de búsqueda">
            <section class="panel" aria-labelledby="titulo-resumen">
                <h2 id="titulo-resumen">Información de "{{ query }}"</h2>
                <dl class="summary">
                    <div><dt>Documentos recuperados</dt><dd>{{ total_resultados }}</dd></div>
                    {% if metricas is not none %}
                        <div><dt>Relevantes etiquetados</dt><dd>{{ documentos_esperados|length }}</dd></div>
                    {% endif %}
                </dl>
                {% if metricas is not none %}
                <p><strong>Métricas de toda la lista</strong></p>
                {{ mostrar_metricas(metricas_totales, total_resultados or none) }}
                <details class="metrics-cutoff">
                    <summary>Métricas de los primeros {{ k_evaluacion }}</summary>
                    {{ mostrar_metricas(metricas, k_evaluacion) }}
                </details>
                <ul class="expected" aria-label="Documentos esperados">
                    {% for documento in documentos_esperados %}
                        <li>
                            <a href="{{ documento.url }}">{{ documento.titulo }}</a>
                            {% if documento.puesto is none %}
                                <span>Sin recuperar</span>
                            {% else %}
                                <span>Puesto {{ documento.puesto }}{% if documento.puesto > k_evaluacion %} · fuera del top {{ k_evaluacion }}{% endif %}</span>
                            {% endif %}
                        </li>
                    {% endfor %}
                </ul>
                {% endif %}
                {% if contexto %}
                    <section class="context-section" aria-labelledby="titulo-contexto">
                        <h3 id="titulo-contexto">La búsqueda pertenece a:</h3>
                        <p><a href="{{ contexto.url_facultad }}">{{ contexto.facultad }}</a></p>
                        <p>{{ contexto.area }}</p>
                    </section>
                {% endif %}
            </section>
    </aside>
    {% endif %}
    </div>
    {% endif %}
    <div class="search-column">
        <form class="search-form primary-form" method="GET" action="{{ url_for('index') }}">
            <input type="text" name="q" value="{{ query }}" aria-label="Búsqueda académica" placeholder="Escribe tu búsqueda…" required>
            <button type="submit">Buscar</button>
        </form>
    {% if query %}
    <main class="results">
        <h2 class="results-heading">Resultados para "{{ query }}"</h2>
        {% for url, puntaje, titulo, resumen in resultados %}
            <div class="result">
                <div class="url">{{ url }}</div>
                <a href="{{ url }}" class="title" target="_blank">{{ titulo }}</a>
                <div class="snippet">{{ resumen }}</div>
                <div class="score">Puntaje de relevancia combinada (TF-IDF + PageRank): <strong>{{ "%.4f"|format(puntaje) }}</strong></div>
            </div>
        {% else %}
            {% if sugerencia %}
                <p class="panel empty-state">No se encontraron resultados. ¿Quisiste decir <a href="{{ url_for('index', q=sugerencia) }}">{{ sugerencia }}</a>?</p>
            {% else %}
                <p class="panel empty-state">No se encontraron resultados.</p>
            {% endif %}
        {% endfor %}
        {% if total_paginas > 1 %}
            <nav class="pagination" aria-label="Paginación de resultados">
                {% if pagina > 1 %}
                    <a href="{{ url_for('index', q=query, page=pagina - 1) }}" aria-label="Página anterior">Anterior</a>
                {% endif %}
                <span>Página {{ pagina }} de {{ total_paginas }}</span>
                {% if pagina < total_paginas %}
                    <a href="{{ url_for('index', q=query, page=pagina + 1) }}" aria-label="Página siguiente">Siguiente</a>
                {% endif %}
            </nav>
        {% endif %}
    </main>
    {% endif %}
    </div>
    </div>
    </div>
    <script>
        const consultas = document.getElementById('consulta-prueba');
        if (consultas) {
            document.addEventListener('click', (event) => {
                if (!consultas.contains(event.target)) consultas.open = false;
            });
            consultas.addEventListener('keydown', (event) => {
                if (event.key === 'Escape' && consultas.open) {
                    consultas.open = false;
                    consultas.querySelector('summary').focus();
                }
            });
        }
    </script>
</body>
</html>
"""


def titulo_documento(url, predeterminado="Sin título"):
    return info_paginas.get(url, {}).get("titulo", predeterminado).split("|", 1)[0].strip()


@app.get("/fondo.jpg")
def fondo():
    return send_file(BASE_DIR / "docs" / "imagenes" / "fondouno.jpg")


@app.route("/", methods=["GET"])
def index():
    query = request.args.get("q", "")
    consulta_evaluada = consultas_evaluadas.get(query.strip().casefold())
    metricas = None
    metricas_totales = None
    documentos_esperados = []
    contexto = None
    pagina = max(1, request.args.get("page", 1, type=int))
    resultados_formateados = []
    sugerencia = None
    total_resultados = 0
    total_paginas = 0
    
    # 1. Obtener la IP actual (si entras desde el cel, agarra el 192.168..., si entras desde la lap, agarra localhost)
    host_actual = request.host.split(':')[0] 

    if query:
        resultados_crudos = buscar(query, indice, pagerank, total_docs, top_n=None)
        total_resultados = len(resultados_crudos)
        contexto = contexto_primer_resultado_del_corpus(resultados_crudos, info_paginas)
        if contexto is not None:
            contexto["url_facultad"] = contexto["url_facultad"].replace("localhost", host_actual)
        if consulta_evaluada is not None:
            relevantes = consulta_evaluada["relevantes"]
            metricas = calcular_metricas(resultados_crudos, relevantes, k_evaluacion)
            metricas_totales = calcular_metricas(resultados_crudos, relevantes, total_resultados)
            puestos = {url: puesto for puesto, (url, _) in enumerate(resultados_crudos, 1)}
            documentos_esperados = [
                {
                    "url": url.replace("localhost", host_actual),
                    "titulo": titulo_documento(url, url.rsplit("/", 1)[-1]),
                    "puesto": puestos.get(url),
                }
                for url in relevantes
            ]
        total_paginas = (total_resultados + RESULTADOS_POR_PAGINA - 1) // RESULTADOS_POR_PAGINA

        if not resultados_crudos:
            sugerencia = sugerir_consulta(query, indice, formas_terminos)

        if total_paginas:
            pagina = min(pagina, total_paginas)
            inicio = (pagina - 1) * RESULTADOS_POR_PAGINA
            fin = inicio + RESULTADOS_POR_PAGINA
            resultados_pagina = resultados_crudos[inicio:fin]
        else:
            resultados_pagina = []

        for url, puntaje in resultados_pagina:
            # 2. LA MAGIA: Reemplazamos 'localhost' por la IP real
            url_corregida = url.replace("localhost", host_actual)
            
            p_info = info_paginas.get(url, {})
            titulo = titulo_documento(url)
            texto = p_info.get("texto", "Sin descripción.")
            resumen = " ".join(texto.split()[:25]) + "..."
            
            # 3. Guardamos la URL corregida en los resultados
            resultados_formateados.append((url_corregida, puntaje, titulo, resumen))
            
    return render_template_string(
        HTML_TEMPLATE,
        query=query,
        consultas_evaluadas=consultas_evaluadas.values(),
        consulta_evaluada=consulta_evaluada,
        metricas=metricas,
        metricas_totales=metricas_totales,
        documentos_esperados=documentos_esperados,
        contexto=contexto,
        k_evaluacion=k_evaluacion,
        resultados=resultados_formateados,
        sugerencia=sugerencia,
        pagina=pagina,
        total_paginas=total_paginas,
        total_resultados=total_resultados,
    )

if __name__ == "__main__":
    # El host='0.0.0.0' permite que otros dispositivos (tu celular) se conecten
    app.run(host='0.0.0.0', debug=True, port=5000)
