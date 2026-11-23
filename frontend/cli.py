import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
DATA_DIR = BASE_DIR / "data"
RESULTADOS_POR_PAGINA = 5

sys.path.append(str(BACKEND_DIR))

from evaluacion import calcular_metricas, cargar_juicios
from motor_busqueda import (
    buscar,
    cargar_json,
    construir_mapa_formas,
    contexto_primer_resultado_del_corpus,
    sugerir_consulta,
)


def elegir_consulta(consultas):
    if not consultas:
        print("No hay consultas etiquetadas disponibles.")
        return None

    print("\nConsultas de prueba")
    for numero, consulta in enumerate(consultas, 1):
        print(f"  {numero:2}. {consulta}")

    opcion = input("Elige un número o presiona Enter para volver: ").strip()
    if not opcion:
        return None
    if opcion not in {str(numero) for numero in range(1, len(consultas) + 1)}:
        print("Elige uno de los números de la lista.")
        return None
    return consultas[int(opcion) - 1]


def mostrar_resumen(consulta, resultados, relevantes, k, info_paginas):
    total = len(resultados)
    print(f'\nInformación de "{consulta}"')
    print(f"Documentos recuperados: {total}")
    if relevantes:
        print(f"Relevantes etiquetados: {len(relevantes)}")
        for encabezado, corte in (("Toda la lista", total), (f"Primeros {k}", k)):
            metricas = calcular_metricas(resultados, relevantes, corte)
            sufijo = f"@{corte}" if corte else ""
            print(
                f"{encabezado} — Precision{sufijo}: {metricas['precision']:.2%} | "
                f"Recall{sufijo}: {metricas['recall']:.2%} | F1{sufijo}: {metricas['f1']:.2%}"
            )

        puestos = {url: puesto for puesto, (url, _) in enumerate(resultados, 1)}
        print("\nDocumentos esperados")
        for url in relevantes:
            titulo = info_paginas.get(url, {}).get("titulo", url.rsplit("/", 1)[-1])
            titulo = titulo.split("|", 1)[0].strip()
            puesto = puestos.get(url)
            estado = f"Puesto {puesto}" if puesto is not None else "Sin recuperar"
            if puesto is not None and puesto > k:
                estado += f" · fuera del top {k}"
            print(f"  {titulo} — {estado}")

    contexto = contexto_primer_resultado_del_corpus(resultados, info_paginas)
    if contexto:
        print(f"\nLa búsqueda pertenece a {contexto['facultad']}")
        print(f"  {contexto['area']}")


def mostrar_pagina(consulta, resultados, pagina, info_paginas):
    if not resultados:
        print(f'\nNo se encontraron resultados para "{consulta}".')
        return

    total_paginas = (len(resultados) + RESULTADOS_POR_PAGINA - 1) // RESULTADOS_POR_PAGINA
    inicio = (pagina - 1) * RESULTADOS_POR_PAGINA
    fin = inicio + RESULTADOS_POR_PAGINA
    print(f'\nResultados para "{consulta}" · Página {pagina} de {total_paginas}')
    print("-" * 65)
    for puesto, (url, puntaje) in enumerate(resultados[inicio:fin], inicio + 1):
        pagina_info = info_paginas.get(url, {})
        titulo = pagina_info.get("titulo", "Sin título").split("|", 1)[0].strip()
        texto = pagina_info.get("texto", "No hay descripción disponible para esta página.")
        resumen = " ".join(texto.split()[:22]) + "..."
        print(f"{puesto}. {titulo}")
        print(f" > {url}")
        print(f" > {resumen}")
        print(f" > Puntaje de relevancia: {puntaje:.4f}")
        print("-" * 65)


def iniciar_cli():
    ruta_indice = DATA_DIR / "indice" / "indice_invertido.json"
    ruta_pagerank = DATA_DIR / "graph" / "pagerank.json"
    ruta_rastreo = DATA_DIR / "sin_procesar" / "resultados_rastreo.json"
    ruta_juicios = DATA_DIR / "evaluacion" / "juicios_relevancia.json"

    if not ruta_indice.exists() or not ruta_pagerank.exists():
        print("Error: Faltan archivos de índice o PageRank.")
        return

    print("Cargando base de datos de búsqueda y PageRank...")
    datos_indice = cargar_json(ruta_indice)
    indice = datos_indice["indice"]
    total_docs = datos_indice["estadisticas"]["total_documentos"]
    pagerank = cargar_json(ruta_pagerank)
    datos_rastreo = cargar_json(ruta_rastreo) if ruta_rastreo.exists() else {"paginas": []}
    info_paginas = {p["url"]: p for p in datos_rastreo.get("paginas", [])}
    formas_terminos = construir_mapa_formas(datos_rastreo.get("paginas", []), indice)

    k = None
    consultas_evaluadas = {}
    if ruta_juicios.is_file():
        try:
            k, particiones = cargar_juicios(ruta_juicios, indice, pagerank)
            consultas_evaluadas = {
                item["consulta"].casefold(): item
                for consultas in particiones.values()
                for item in consultas
            }
        except (OSError, ValueError, TypeError, AttributeError) as error:
            print(f"No se pudieron cargar las consultas de evaluación: {error}", file=sys.stderr)

    opciones = [item["consulta"] for item in consultas_evaluadas.values()]
    print("\n" + "=" * 65)
    print("     MINI-GOOGLE BUAP (CLI)")
    print("=" * 65)
    print("Usa :pruebas para elegir una consulta etiquetada.")
    print("Usa :siguiente o :anterior para cambiar de página.")

    consulta_actual = ""
    resultados = []
    pagina = 1
    while True:
        entrada = input("\nIngresa tu búsqueda (o escribe 'salir'): ").strip()
        comando = entrada.casefold()
        if comando == "salir":
            print("Hasta la próxima.")
            break
        if not entrada:
            continue

        if comando in {":siguiente", ":anterior"}:
            nueva_pagina = pagina + (1 if comando == ":siguiente" else -1)
            total_paginas = (len(resultados) + RESULTADOS_POR_PAGINA - 1) // RESULTADOS_POR_PAGINA
            if 1 <= nueva_pagina <= total_paginas:
                pagina = nueva_pagina
                mostrar_pagina(consulta_actual, resultados, pagina, info_paginas)
            else:
                print("No hay más resultados en esa dirección.")
            continue

        consulta = elegir_consulta(opciones) if comando == ":pruebas" else entrada
        if consulta is None:
            continue

        consulta_actual = consulta
        pagina = 1
        resultados = buscar(consulta_actual, indice, pagerank, total_docs, top_n=None)
        juicio = consultas_evaluadas.get(consulta_actual.casefold())

        if not resultados:
            sugerencia = sugerir_consulta(consulta_actual, indice, formas_terminos)
            if sugerencia:
                respuesta = input(f"No se encontraron resultados. ¿Quisiste decir '{sugerencia}'? (s/n): ")
                if respuesta.strip().casefold() in {"s", "si", "sí"}:
                    if juicio is not None:
                        mostrar_resumen(consulta_actual, resultados, juicio["relevantes"], k, info_paginas)
                    consulta_actual = sugerencia
                    resultados = buscar(consulta_actual, indice, pagerank, total_docs, top_n=None)
                    juicio = consultas_evaluadas.get(consulta_actual.casefold())

        relevantes = juicio["relevantes"] if juicio is not None else None
        mostrar_resumen(consulta_actual, resultados, relevantes, k, info_paginas)
        mostrar_pagina(consulta_actual, resultados, pagina, info_paginas)


if __name__ == "__main__":
    try:
        iniciar_cli()
    except (EOFError, KeyboardInterrupt):
        print("\nHasta la próxima.")
