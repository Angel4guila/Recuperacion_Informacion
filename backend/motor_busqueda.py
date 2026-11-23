import json
import os
import math
import re
from collections import Counter

NOMBRES_AREAS = {
    "area_ciencias_economico_administrativas": "Área de Ciencias Económico-Administrativas",
    "area_ciencias_exactas_tecnologia": "Área de Ciencias Exactas y Tecnología",
    "area_ciencias_naturales_salud": "Área de Ciencias Naturales y de la Salud",
    "area_ciencias_sociales_humanidades": "Área de Ciencias Sociales y Humanidades",
}


def contexto_primer_resultado_del_corpus(resultados, info_paginas):
    for url, _ in resultados:
        base, separador, ruta = url.partition("/corpus/")
        directorios = ruta.split("/")
        if not separador or len(directorios) != 3:
            continue
        area, facultad, _ = directorios
        url_facultad = f"{base}/corpus/{area}/{facultad}/index.html"
        if area not in NOMBRES_AREAS or url_facultad not in info_paginas:
            continue
        titulo = info_paginas[url_facultad].get("titulo", "Sin título").split("|", 1)[0].strip()
        return {
            "facultad": titulo,
            "url_facultad": url_facultad,
            "area": NOMBRES_AREAS[area],
        }
    return None


#Funcion stemming del indexer
def stem_simple(palabra):
    sufijos = (
        "amientos", "imientos", "aciones", "ación", "acion", "adores", "adoras",
        "mente", "idades", "idad", "ando", "iendo", "ados", "idos", "es", "os", "as", "ar", "er", "ir", "o", "a", "s"
    )
    for sufijo in sufijos:
        if palabra.endswith(sufijo) and len(palabra) > len(sufijo) + 2:
            return palabra[:-len(sufijo)]
    return palabra

def cargar_json(ruta):
    with open(ruta, 'r', encoding='utf-8') as f:
        return json.load(f)

def cargar_pesos_predeterminados():
    ruta_pesos = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "evaluacion", "pesos_ranking.json"
    )
    if not os.path.exists(ruta_pesos):
        return 0.7, 0.3

    datos = cargar_json(ruta_pesos)
    return datos["peso_texto"], datos["peso_pagerank"]

PESO_TEXTO, PESO_PAGERANK = cargar_pesos_predeterminados()

def normalizar_puntajes(puntajes):
    if not puntajes:
        return {}

    minimo = min(puntajes.values())
    rango = max(puntajes.values()) - minimo
    if rango == 0:
        return {url: 0.0 for url in puntajes}

    return {url: (puntaje - minimo) / rango for url, puntaje in puntajes.items()}

def construir_mapa_formas(paginas, indice):
    frecuencias = Counter()
    for pagina in paginas:
        texto = " ".join((
            pagina.get("titulo", ""),
            pagina.get("descripcion", ""),
            pagina.get("texto", ""),
        )).lower()
        for palabra in re.findall(r"[a-záéíóúüñ]+", texto):
            termino = stem_simple(palabra)
            if termino in indice:
                frecuencias[(termino, palabra)] += 1

    formas = {}
    for (termino, palabra), _ in frecuencias.most_common():
        formas.setdefault(termino, palabra)
    return formas

def distancia_edicion(primera, segunda):
    if len(primera) > len(segunda):
        primera, segunda = segunda, primera

    anterior = list(range(len(primera) + 1))
    for indice_segunda, letra_segunda in enumerate(segunda, 1):
        actual = [indice_segunda]
        for indice_primera, letra_primera in enumerate(primera, 1):
            costo = 0 if letra_primera == letra_segunda else 1
            actual.append(min(
                actual[-1] + 1,
                anterior[indice_primera] + 1,
                anterior[indice_primera - 1] + costo,
            ))
        anterior = actual
    return anterior[-1]

def sugerir_consulta(consulta, indice, formas_terminos=None, umbral=0.8):
    terminos = re.findall(r"[a-záéíóúüñ]+", consulta.lower())
    vocabulario = tuple(indice)
    formas_terminos = formas_terminos or {}
    sugeridos = []
    hubo_cambio = False

    for palabra in terminos:
        termino = stem_simple(palabra)
        if termino in indice or len(termino) < 4:
            sugeridos.append(palabra)
            continue

        mejor_candidato = None
        mejor_puntaje = -1
        for candidato in vocabulario:
            distancia = distancia_edicion(termino, candidato)
            similitud = 1 - distancia / max(len(termino), len(candidato))
            es_prefijo = len(termino) >= 5 and candidato.startswith(termino)
            if similitud < umbral and not es_prefijo:
                continue

            puntaje = 0.8 + 0.2 * len(termino) / len(candidato) if es_prefijo else similitud
            if puntaje > mejor_puntaje or (
                puntaje == mejor_puntaje
                and len(indice[candidato]) > len(indice[mejor_candidato])
            ):
                mejor_candidato = candidato
                mejor_puntaje = puntaje

        if mejor_candidato is None:
            sugeridos.append(palabra)
        else:
            sugeridos.append(formas_terminos.get(mejor_candidato, mejor_candidato))
            hubo_cambio = True

    sugerencia = " ".join(sugeridos)
    return sugerencia if hubo_cambio and sugerencia != consulta.lower().strip() else None

def buscar(consulta, indice, pagerank, total_docs, peso_texto=None, peso_pagerank=None, top_n=5):
    if peso_texto is None and peso_pagerank is None:
        peso_texto, peso_pagerank = PESO_TEXTO, PESO_PAGERANK
    elif peso_texto is None or peso_pagerank is None:
        raise ValueError("Debes proporcionar ambos pesos o ninguno.")

    if peso_texto < 0 or peso_pagerank < 0 or peso_texto + peso_pagerank == 0:
        raise ValueError("Los pesos deben ser no negativos y al menos uno debe ser mayor que cero.")
    if top_n is not None and top_n < 0:
        raise ValueError("top_n debe ser no negativo o None.")

    #se procesa la consulta con el mismo stemmer del indice
    terminos_crudos = consulta.lower().split()
    terminos = dict.fromkeys(stem_simple(t) for t in terminos_crudos)

    puntajes_texto = Counter()
    
    for termino in terminos:
        documentos_con_palabra = indice.get(termino, {})
        df = len(documentos_con_palabra)
        if not 0 < df < total_docs:
            continue

        idf = math.log(total_docs / df)
        for url, tf in documentos_con_palabra.items():
            puntajes_texto[url] += tf * idf

    if not puntajes_texto:
        return []

    puntajes_autoridad = {
        url: pagerank.get(url, 0)
        for url in puntajes_texto
    }
    texto_normalizado = normalizar_puntajes(puntajes_texto)
    autoridad_normalizada = normalizar_puntajes(puntajes_autoridad)

    suma_pesos = peso_texto + peso_pagerank
    peso_texto /= suma_pesos
    peso_pagerank /= suma_pesos

    puntajes = {
        url: peso_texto * texto_normalizado[url] + peso_pagerank * autoridad_normalizada[url]
        for url in puntajes_texto
    }
    resultados = sorted(puntajes.items(), key=lambda item: (-item[1], item[0]))

    return resultados if top_n is None else resultados[:top_n]

if __name__ == "__main__":
    #rutas relativas
    ruta_indice = os.path.join("..", "data", "indice", "indice_invertido.json")
    ruta_pagerank = os.path.join("..", "data", "graph", "pagerank.json")

    # Verificacion de los archivos antes de abrirlo
    if not os.path.exists(ruta_indice):
        print(f"ERROR: No se encontró el índice en: {os.path.abspath(ruta_indice)}")
        print("Verifica que estés ejecutando desde la carpeta 'backend' y que la carpeta 'indice' exista.")
        exit()
        
    if not os.path.exists(ruta_pagerank):
        print(f"ERROR: No se encontró el PageRank en: {os.path.abspath(ruta_pagerank)}")
        print("Pídele a tu compañero que te confirme la ruta exacta donde guardó pagerank.json.")
        exit()

    print("Cargando Índice Invertido y PageRank...")
    datos_indice = cargar_json(ruta_indice)
    indice = datos_indice["indice"]
    total_docs = datos_indice["estadisticas"]["total_documentos"]
    
    pagerank = cargar_json(ruta_pagerank)

    print("=" * 60)
    print(" MINI-GOOGLE BUAP ")
    print("=" * 60)
    
    while True:
        consulta = input("\nEjemplo:\nmedicina\ncomputacion\nderecho\nIngresa tu búsqueda (o escribe 'salir'): ")
        if consulta.lower() == 'salir':
            break
            
        resultados = buscar(consulta, indice, pagerank, total_docs)
        
        if not resultados:
            print("No se encontraron resultados.")
            continue
            
        print(f"\nTop 5 resultados para '{consulta}':")
        for i, (url, puntaje) in enumerate(resultados, 1):
            url_corta = url.replace("http://localhost/sitio_web/corpus/", "")
            print(f"{i}. {url_corta}")
            print(f"   Puntaje final: {puntaje:.4f}")
            print()
