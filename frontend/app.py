from flask import Flask, render_template_string, request
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
        body { font-family: Arial, sans-serif; margin: 0; background: #f9f9f9; color: #333; }
        .container { max-width: 1180px; margin: 0 auto; padding: 28px clamp(16px, 4vw, 40px); }
        .layout {
            display: grid;
            grid-template-columns: minmax(0, 290px) minmax(0, 1fr);
            grid-template-areas: "side content";
            gap: 24px;
            align-items: start;
        }
        .side-column { grid-area: side; display: grid; gap: 14px; color: #253248; }
        .search-column { grid-area: content; display: grid; gap: 16px; min-width: 0; }
        .panel { background: white; padding: 18px; border: 1px solid #dfe5ef; border-radius: 12px; }
        .panel h2 { font-size: 16px; margin: 0 0 12px; }
        .panel p { font-size: 14px; line-height: 1.45; margin: 8px 0 0; }
        .panel a { color: #214cb0; overflow-wrap: anywhere; }
        .search-panel { align-self: stretch; display: grid; gap: 10px; align-content: start; }
        .search-panel label { font-size: 16px; font-weight: bold; }
        .test-form select { width: 100%; min-width: 0; padding: 10px 8px; font: inherit; border: 1px solid #c4cfe0; border-radius: 8px; background: white; }
        .search-panel :is(input, select, button) { min-height: 42px; font-size: 14px; }
        .test-form button { padding-inline: 10px; }
        button { border: 0; border-radius: 8px; padding: 10px 15px; background: #2455bb; color: white; font: inherit; cursor: pointer; }
        button:hover { background: #1c4497; }
        .search-box { max-width: 590px; margin: 0 auto 28px; text-align: center; }
        .search-box h1 { margin: 0 0 14px; font-size: clamp(24px, 4vw, 32px); }
        .search-box h1 a { color: inherit; text-decoration: none; }
        .search-box h1 a:hover { text-decoration: underline; text-underline-offset: 5px; }
        .search-box span { color: rgb(11, 34, 184); }
        .search-form { display: flex; gap: 8px; }
        .primary-form { width: 100%; max-width: 590px; gap: 10px; }
        .primary-form input { flex: 1; min-width: 0; padding: 12px; font-size: 16px; border: 1px solid #dfe1e5; border-radius: 24px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .primary-form button { padding: 12px 20px; font-size: 16px; background: #4285f4; border-radius: 4px; }
        .primary-form button:hover { background: #357ae8; }
        #titulo-resumen, #titulo-contexto { overflow-wrap: anywhere; }
        .context-section { margin-top: 16px; padding-top: 14px; border-top: 1px solid #dfe5ef; }
        .context-section h3 { margin: 0; font-size: 15px; }
        .summary, .metrics { margin: 0; }
        .summary > div, .metrics > div { display: flex; justify-content: space-between; gap: 10px; margin: 8px 0; font-size: 14px; }
        .summary dd, .metrics dd { margin: 0; font-weight: bold; white-space: nowrap; }
        .metrics { margin-top: 12px; padding-top: 4px; border-top: 1px solid #dfe5ef; }
        .metrics-cutoff { margin-top: 12px; padding-top: 10px; border-top: 1px solid #dfe5ef; }
        .metrics-cutoff summary { color: #214cb0; font-size: 14px; font-weight: bold; cursor: pointer; }
        .metrics-cutoff .metrics { margin-top: 4px; border-top: 0; }
        .expected { margin: 12px 0 0; padding-left: 18px; font-size: 14px; line-height: 1.45; }
        .expected li + li { margin-top: 6px; }
        .expected span { display: block; color: #506077; }
        .results-heading { font-size: 18px; margin: 0 0 14px; overflow-wrap: anywhere; }
        .result { background: white; padding: 20px; margin-bottom: 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .url { color: #006621; font-size: 14px; margin-bottom: 4px; overflow-wrap: anywhere; }
        .title { color: #1a0dab; font-size: 18px; text-decoration: none; font-weight: bold; }
        .title:hover { text-decoration: underline; }
        .snippet { color: #545454; font-size: 14px; margin-top: 5px; }
        .score { color: #888; font-size: 12px; margin-top: 8px; }
        .pagination { display: flex; justify-content: center; align-items: center; gap: 16px; margin: 24px auto; }
        .pagination a { color: #1a0dab; text-decoration: none; }
        .pagination a:hover { text-decoration: underline; }
        @media (max-width: 680px) {
            .layout {
                grid-template-columns: minmax(0, 1fr);
                grid-template-areas: "search" "test" "summary" "results";
                gap: 18px;
            }
            .search-column, .side-column { display: contents; }
            .primary-form { grid-area: search; }
            .test-form { grid-area: test; }
            .sidebar { grid-area: summary; color: #253248; }
            .results { grid-area: results; }
            .search-box { margin-bottom: 18px; }
        }
    </style>
</head>
<body>
    <div class="container">
    <header class="search-box">
        <h1><a href="{{ url_for('index') }}">Mini-Google <span>BUAP</span></a></h1>
    </header>
    <div class="layout">
    {% if consultas_evaluadas or query %}
    <div class="side-column">
        {% if consultas_evaluadas %}
            <form class="panel search-panel test-form" method="GET" action="{{ url_for('index') }}">
                <label for="consulta-prueba">Consultas de prueba</label>
                <div class="search-form">
                    <select id="consulta-prueba" name="q" required>
                        <option value="" disabled {% if not consulta_evaluada %}selected{% endif %}>Elige una consulta</option>
                        {% for item in consultas_evaluadas %}
                            <option value="{{ item.consulta }}" {% if item == consulta_evaluada %}selected{% endif %}>
                                {{ item.consulta }}
                            </option>
                        {% endfor %}
                    </select>
                    <button type="submit">Evaluar</button>
                </div>
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
            <input type="text" name="q" value="{{ query }}" aria-label="Búsqueda académica" placeholder="Escribe tu búsqueda académica..." required>
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
                <div class="score">Puntaje de relevancia combinada (TF-IDF + PageRank): {{ "%.4f"|format(puntaje) }}</div>
            </div>
        {% else %}
            {% if sugerencia %}
                <p style="text-align:center;">No se encontraron resultados. ¿Quisiste decir <a href="{{ url_for('index', q=sugerencia) }}">{{ sugerencia }}</a>?</p>
            {% else %}
                <p style="text-align:center;">No se encontraron resultados.</p>
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
</body>
</html>
"""


def titulo_documento(url, predeterminado="Sin título"):
    return info_paginas.get(url, {}).get("titulo", predeterminado).split("|", 1)[0].strip()


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
