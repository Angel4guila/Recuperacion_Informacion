import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
DATA_DIR = BASE_DIR / "data"
sys.path.insert(0, str(BACKEND_DIR))

from motor_busqueda import buscar, cargar_json


def calcular_metricas(resultados, relevantes, k):
    relevantes = set(relevantes)
    primeros = [url for url, _ in resultados[:k]]
    verdaderos_positivos = len(set(primeros) & relevantes)
    precision = verdaderos_positivos / k if k else 0.0
    recall = verdaderos_positivos / len(relevantes)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def validar_juicios(datos, urls_corpus):
    k = datos.get("k")
    consultas = datos.get("consultas")
    if not isinstance(k, int) or k < 1:
        raise ValueError("'k' debe ser un entero positivo.")
    if not isinstance(consultas, list) or not consultas:
        raise ValueError("Agrega consultas etiquetadas en 'consultas'; revisa docs/Evaluacion.md.")

    particiones = {"ajuste": [], "prueba": []}
    consultas_vistas = set()
    for numero, item in enumerate(consultas, 1):
        consulta = item.get("consulta", "").strip()
        relevantes = item.get("relevantes")
        particion = item.get("particion")
        if not consulta or not isinstance(relevantes, list) or not relevantes:
            raise ValueError(f"La consulta {numero} requiere texto y al menos una URL relevante.")
        if particion not in particiones:
            raise ValueError(f"La consulta {numero}: 'particion' debe ser 'ajuste' o 'prueba'.")
        clave = consulta.casefold()
        if clave in consultas_vistas:
            raise ValueError(f"La consulta '{consulta}' está repetida; usa consultas distintas entre particiones.")
        consultas_vistas.add(clave)
        if len(set(relevantes)) != len(relevantes):
            raise ValueError(f"La consulta {numero} contiene URLs relevantes repetidas.")

        desconocidas = set(relevantes) - urls_corpus
        if desconocidas:
            raise ValueError(f"La consulta {numero} contiene URLs fuera del corpus: {sorted(desconocidas)}")
        particiones[particion].append({"consulta": consulta, "relevantes": relevantes})

    if not particiones["ajuste"] or not particiones["prueba"]:
        raise ValueError("Se necesita al menos una consulta en cada partición: 'ajuste' y 'prueba'.")
    return k, particiones


def evaluar_consultas(consultas, indice, pagerank, total_docs, k, peso_texto):
    peso_pagerank = 1.0 - peso_texto
    resultados = []
    for item in consultas:
        ranking = buscar(
            item["consulta"], indice, pagerank, total_docs,
            peso_texto=peso_texto,
            peso_pagerank=peso_pagerank,
            top_n=k
        )
        metricas = calcular_metricas(ranking, item["relevantes"], k)
        resultados.append({**item, **metricas})
    return resultados


def promedio(resultados, metrica):
    return sum(item[metrica] for item in resultados) / len(resultados)


def mostrar_resultados(titulo, resultados):
    print(f"\n{titulo}")
    for item in resultados:
        print(
            f"  {item['consulta']}: P@k={item['precision']:.3f}, "
            f"Recall@k={item['recall']:.3f}, F1@k={item['f1']:.3f}"
        )
    print(
        "  Promedio macro: "
        f"P@k={promedio(resultados, 'precision'):.3f}, "
        f"Recall@k={promedio(resultados, 'recall'):.3f}, "
        f"F1@k={promedio(resultados, 'f1'):.3f}"
    )


def main():
    parser = argparse.ArgumentParser(description="Evalúa y calibra el ranking con juicios de relevancia.")
    parser.add_argument(
        "--juicios",
        type=Path,
        default=DATA_DIR / "evaluacion" / "juicios_relevancia.json",
        help="JSON de consultas y URLs juzgadas como relevantes.",
    )
    args = parser.parse_args()

    datos_indice = cargar_json(DATA_DIR / "indice" / "indice_invertido.json")
    indice = datos_indice["indice"]
    total_docs = datos_indice["estadisticas"]["total_documentos"]
    pagerank = cargar_json(DATA_DIR / "graph" / "pagerank.json")
    urls_corpus = set(pagerank)
    for documentos in indice.values():
        urls_corpus.update(documentos)

    with args.juicios.open("r", encoding="utf-8") as archivo:
        datos_juicios = json.load(archivo)
    k, particiones = validar_juicios(datos_juicios, urls_corpus)

    pesos_candidatos = [paso / 10 for paso in range(11)]
    evaluaciones_ajuste = {
        peso: evaluar_consultas(particiones["ajuste"], indice, pagerank, total_docs, k, peso)
        for peso in pesos_candidatos
    }
    mejor_peso_texto = max(
        pesos_candidatos,
        key=lambda peso: (
            promedio(evaluaciones_ajuste[peso], "f1"),
            -abs(peso - 0.7),
        ),
    )

    resultados_ajuste = evaluaciones_ajuste[mejor_peso_texto]
    resultados_prueba = evaluar_consultas(
        particiones["prueba"], indice, pagerank, total_docs, k, mejor_peso_texto
    )
    mostrar_resultados("Ajuste con los pesos seleccionados", resultados_ajuste)
    mostrar_resultados("Evaluación en consultas reservadas", resultados_prueba)

    ruta_pesos = DATA_DIR / "evaluacion" / "pesos_ranking.json"
    ruta_pesos.parent.mkdir(parents=True, exist_ok=True)
    with ruta_pesos.open("w", encoding="utf-8") as archivo:
        json.dump(
            {
                "peso_texto": mejor_peso_texto,
                "peso_pagerank": 1.0 - mejor_peso_texto,
            },
            archivo,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"\nPesos guardados en {ruta_pesos.relative_to(BASE_DIR)}: "
        f"TF-IDF={mejor_peso_texto:.1f}, PageRank={1.0 - mejor_peso_texto:.1f}."
    )
    print("Reinicia la aplicación web o la CLI para cargar los pesos nuevos.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(f"Error de evaluación: {error}", file=sys.stderr)
        sys.exit(1)
