import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / 'backend'
DATA_DIR = BASE_DIR / 'data'

sys.path.append(str(BACKEND_DIR))

# Importamos la lógica del motor de búsqueda de tu compañero
# (Asegúrate de que motor_busqueda.py tenga expuestas o estructuradas las funciones o podemos replicar/llamar la lógica)
from motor_busqueda import stem_simple, buscar, cargar_json

def iniciar_cli():
    # Rutas absolutas seguras hacia los datos
    ruta_indice = DATA_DIR / "indice" / "indice_invertido.json"
    ruta_pagerank = DATA_DIR / "graph" / "pagerank.json"
    ruta_rastreo = DATA_DIR / "sin_procesar" / "resultados_rastreo.json"

    # Validaciones iniciales
    if not ruta_indice.exists() or not ruta_pagerank.exists():
        print("Error: Faltan archivos de índice o PageRank.")
        return

    print("Cargando base de datos de búsqueda y PageRank...")
    datos_indice = cargar_json(ruta_indice)
    indice = datos_indice["indice"]
    total_docs = datos_indice["estadisticas"]["total_documentos"]
    
    pagerank = cargar_json(ruta_pagerank)
    
    # Opcional: Cargamos resultados de rastreo para poder extraer el título real y un fragmento de texto
    datos_rastreo = cargar_json(ruta_rastreo) if ruta_rastreo.exists() else {"paginas": []}
    # Creamos un diccionario rápido de URL -> Información de la página
    info_paginas = {p["url"]: p for p in datos_rastreo.get("paginas", [])}

    print("\n" + "=" * 65)
    print("     MINI-GOOGLE BUAP (CLI)     ")
    print("=" * 65)

    while True:
        consulta = input("\nIngresa tu búsqueda (o escribe 'salir'): ").strip()
        if consulta.lower() == 'salir':
            print("Hasta la proxima...")
            break
            
        if not consulta:
            continue

        resultados = buscar(consulta, indice, pagerank, total_docs)
        
        if not resultados:
            print(f"\nNo se encontraron resultados para '{consulta}'.")
            continue
            
        print(f"\nResultados de la búsqueda para: [ {consulta} ]\n" + "-" * 65)
        
        for i, (url, puntaje) in enumerate(resultados, 1):
            # Extraer info complementaria del rastreo si existe
            pagina_info = info_paginas.get(url, {})
            titulo = pagina_info.get("titulo", "Sin título")
            # Limpiar título feo de "| Corpus académico..." si lo trae
            titulo = titulo.split('|')[0].strip()
            
            # Obtener un extracto del texto (primeras 150 palabras)
            texto_completo = pagina_info.get("texto", "No hay descripción disponible para esta página.")
            resumen = " ".join(texto_completo.split()[:22]) + "..."

            # Formato Estilo Google
            print(f"{i}. {titulo}")
            print(f" > {url}")
            print(f" > {resumen}")
            print(f" > Puntaje de relevancia: {puntaje:.4f}")
            print("-" * 65)

if __name__ == "__main__":
    iniciar_cli()