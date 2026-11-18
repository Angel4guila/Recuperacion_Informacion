from flask import Flask, render_template_string, request
import sys
from pathlib import Path

# Configuración de rutas para importar el backend
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR / 'backend'))

from motor_busqueda import cargar_json, buscar

app = Flask(__name__)

# Cargar recursos una sola vez al iniciar el servidor web para que sea rápido
DATA_DIR = BASE_DIR / 'data'
ruta_indice = DATA_DIR / "indice" / "indice_invertido.json"
ruta_pagerank = DATA_DIR / "graph" / "pagerank.json"
ruta_rastreo = DATA_DIR / "sin_procesar" / "resultados_rastreo.json"

datos_indice = cargar_json(ruta_indice)
indice = datos_indice["indice"]
total_docs = datos_indice["estadisticas"]["total_documentos"]
pagerank = cargar_json(ruta_pagerank)
datos_rastreo = cargar_json(ruta_rastreo) if ruta_rastreo.exists() else {"paginas": []}
info_paginas = {p["url"]: p for p in datos_rastreo.get("paginas", [])}

# Plantilla HTML incrustada minimalista estilo buscador clásico
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Mini-Google BUAP</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 50px; background-color: #f9f9f9; color: #333; }
        .search-box { text-align: center; margin-bottom: 40px; }
        input[type="text"] { width: 50%; padding: 12px; font-size: 16px; border: 1px solid #dfe1e5; border-radius: 24px; outline: none; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        input[type="submit"] { padding: 12px 20px; font-size: 16px; background-color: #4285f4; color: white; border: none; border-radius: 4px; cursor: pointer; margin-left: 10px; }
        input[type="submit"]:hover { background-color: #357ae8; }
        .result { background: white; padding: 20px; margin-bottom: 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); width: 60%; margin-left: auto; margin-right: auto; }
        .url { color: #006621; font-size: 14px; margin-bottom: 4px; }
        .title { color: #1a0dab; font-size: 18px; text-decoration: none; font-weight: bold; }
        .title:hover { text-decoration: underline; }
        .snippet { color: #545454; font-size: 14px; margin-top: 5px; }
        .score { color: #888; font-size: 12px; margin-top: 8px; }
    </style>
</head>
<body>
    <div class="search-box">
        <h1>Mini-Google <span style="color: rgb(11, 34, 184);">BUAP</span></h1>
        <form method="GET" action="/">
            <input type="text" name="q" value="{{ query }}" placeholder="Escribe tu búsqueda académica..." required>
            <input type="submit" value="Buscar">
        </form>
    </div>

    {% if query %}
        <p style="text-align:center; color: #666;">Resultados para: <b>{{ query }}</b></p>
        {% for url, puntaje, titulo, resumen in resultados %}
            <div class="result">
                <div class="url">{{ url }}</div>
                <a href="{{ url }}" class="title" target="_blank">{{ titulo }}</a>
                <div class="snippet">{{ resumen }}</div>
                <div class="score">Puntaje de relevancia combinada (TF-IDF + PageRank): {{ "%.4f"|format(puntaje) }}</div>
            </div>
        {% else %}
            <p style="text-align:center;">No se encontraron resultados.</p>
        {% endfor %}
    {% endif %}
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    query = request.args.get("q", "")
    resultados_formateados = []
    
    if query:
        resultados_crudos = buscar(query, indice, pagerank, total_docs)
        for url, puntaje in resultados_crudos:
            p_info = info_paginas.get(url, {})
            titulo = p_info.get("titulo", "Sin título").split('|')[0].strip()
            texto = p_info.get("texto", "Sin descripción.")
            resumen = " ".join(texto.split()[:25]) + "..."
            resultados_formateados.append((url, puntaje, titulo, resumen))
            
    return render_template_string(HTML_TEMPLATE, query=query, resultados=resultados_formateados)

if __name__ == "__main__":
    # El host='0.0.0.0' permite que otros dispositivos (tu celular) se conecten
    app.run(host='0.0.0.0', debug=True, port=5000)