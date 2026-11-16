import json
import os
import math
from collections import Counter

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

def buscar(consulta, indice, pagerank, total_docs):
    #se procesa la consulta con el mismo stemmer del indice
    terminos_crudos = consulta.lower().split()
    terminos = [stem_simple(t) for t in terminos_crudos] # STEMMER
    
    puntajes = Counter()
    
    for termino in terminos:
        if termino in indice:
            documentos_con_palabra = indice[termino]
            
            # Calcular IDF
            df = len(documentos_con_palabra)
            idf = math.log(total_docs / df) if df > 0 else 0
            
            for url, tf in documentos_con_palabra.items():
                puntaje_texto = tf * idf
                puntaje_autoridad = pagerank.get(url, 0)
                
                # COMBINACION: 70% texto, 30% autoridad
                # pageRank por 100 para balancear la escala
                puntaje_final = (puntaje_texto * 0.7) + (puntaje_autoridad * 0.3 * 100)
                
                puntajes[url] += puntaje_final

    return puntajes.most_common(5)

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