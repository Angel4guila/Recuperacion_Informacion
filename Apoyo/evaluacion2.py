import re
import unicodedata
from collections import Counter, defaultdict

from pathlib import Path

try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

STOPWORDS_ES = {
    "a", "al", "ante", "bajo", "con", "contra", "de", "del", "desde", "durante", "en", "entre",
    "hacia", "hasta", "para", "por", "según", "segun", "sin", "sobre", "tras", "y", "e", "o", "u", "ni",
    "que", "como", "cómo", "cuando", "cuándo", "donde", "dónde", "quien", "quién", "el", "él", "la",
    "los", "las", "un", "una", "unos", "unas", "mi", "mí", "tu", "tú", "su", "sus", "este", "esta",
    "estos", "estas", "es", "son", "ser", "fue", "eran", "hay", "ha", "han", "se", "lo", "le", "les",
    "me", "te", "nos", "más", "mas", "muy"
}

""" DOCUMENTOS = {
    "D1": "Los sistemas de recuperación de información permiten encontrar documentos relevantes en colecciones digitales.",
    "D2": "La indexación de documentos usa términos de índice para acelerar la búsqueda de información.",
    "D3": "El procesamiento de lenguaje natural elimina stopwords y reduce palabras a sus raíces mediante stemming.",
    "D4": "Las bases de datos almacenan registros y permiten consultas mediante lenguaje SQL.",
    "D5": "Un motor de búsqueda utiliza índices invertidos para recuperar documentos relacionados con una consulta.",
    "D6": "La precisión y la exhaustividad son métricas empleadas para evaluar sistemas de recuperación de información.",
    "D7": "Los algoritmos de aprendizaje automático pueden clasificar documentos y detectar temas relevantes.",
    "D8": "La biblioteca digital contiene libros, artículos científicos y recursos de investigación académica."
}  """

"""Guardo la direccion exacta de mi carpeta"""
direccion_actual= Path(".");
"""Enlisto todos los archivos de tipo txt que hay en mi carpeta"""
archivos_txt= list(direccion_actual.glob("*.txt"))

"""Obtengo el numero exacto de los archivos que hay"""
total_txt = len(archivos_txt)

DOCUMENTOS = {}

for i in range(1, total_txt+1):
    clave = f"D{i}"
    nombre_archivo = f"D{i}.txt"
    with open(nombre_archivo, "r", encoding= "UTF_8") as archivo:
        DOCUMENTOS[clave]= archivo.read()
    
RELEVANTES = {"D1", "D2", "D5", "D6"}
CONSULTA = "recuperación de información indexación de documentos"

def normalizar(texto):
    texto = texto.lower()
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"[^a-záéíóúàèìòùäëïöüñ\s]", " ", texto)
    return " ".join(texto.split())

def eliminar_stopwords(tokens):
    return [t for t in tokens if t not in STOPWORDS_ES]

def stem_simple(palabra):
    sufijos = (
        "amientos", "imientos", "aciones", "ación", "acion", "adores", "adoras",
        "mente", "idades", "idad", "ando", "iendo", "ados", "idos", "es", "os", "as", "ar", "er", "ir", "o", "a", "s"
    )
    for sufijo in sufijos:
        if palabra.endswith(sufijo) and len(palabra) > len(sufijo) + 2:
            return palabra[:-len(sufijo)]
    return palabra

def procesar(texto):
    normalizado = normalizar(texto)
    tokens = normalizado.split()
    sin_stopwords = eliminar_stopwords(tokens)
    stems = [stem_simple(t) for t in sin_stopwords] 
    return stems

def crear_indice_invertido(documentos):
    indice = defaultdict(set)
    for doc_id, texto in documentos.items():
        for termino in set(procesar(texto)):
            indice[termino].add(doc_id)
    return dict(indice)

def buscar(consulta, indice, documentos):
    terminos = procesar(consulta)
    puntuaciones = Counter()
    for termino in terminos:
        for doc_id in indice.get(termino, set()):
            puntuaciones[doc_id] += 1
    return [doc for doc, _ in sorted(puntuaciones.items(), key=lambda x: (-x[1], x[0]))], terminos, puntuaciones

def metricas(recuperados, relevantes, R=None):
    if R is not None:
        recuperados = recuperados[:R]

    recuperados_set = set(recuperados)

    vp = len(recuperados_set & relevantes)
    fp = len(recuperados_set - relevantes)
    fn = len(relevantes - recuperados_set)

    precision = vp / len(recuperados) if recuperados else 0.0
    exhaustividad = vp / len(relevantes) if relevantes else 0.0

    if (precision + exhaustividad) > 0:
        f1 = 2 * (precision * exhaustividad) / (precision + exhaustividad)
    else:
        f1 = 0.0

    return {
        "vp": vp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "exhaustividad": exhaustividad,
        "f1": f1
    }

def calcular_precision_R(recuperados, relevantes):
    precisiones_R = {}
    for R in range(1, len(recuperados) + 1):
        m = metricas(recuperados, relevantes, R=R)
        precisiones_R[f"P@{R}"] = m["precision"]
    return precisiones_R

def graficar(recuperados, relevantes):
    if plt is None:
        print("\nNo se generaron gráficas: instala matplotlib con 'pip install matplotlib'.")
        return

    Rs = list(range(1, len(recuperados) + 1))
    precisiones = []

    for R in Rs:
        m = metricas(recuperados, relevantes, R=R)
        precisiones.append(m["precision"])

    m_global = metricas(recuperados, relevantes)

    # Gráfica Global
    plt.figure(figsize=(8, 5))
    barras = plt.bar(
        ["Precisión", "Exhaustividad", "F1"],
        [m_global["precision"], m_global["exhaustividad"], m_global["f1"]],
        color=["#2563eb", "#16a34a", "#d97706"]
    )
    plt.ylim(0, 1.1)
    plt.ylabel("Valor de la métrica")
    plt.title("Evaluación Global de la Consulta")
    for barra, valor in zip(barras, [m_global["precision"], m_global["exhaustividad"], m_global["f1"]]):
        plt.text(barra.get_x() + barra.get_width()/2, valor + .03, f"{valor:.2f}", ha="center")
    plt.tight_layout()
    plt.savefig("grafica_metricas_globales.png", dpi=150)
    plt.close()

    # Curva de Precisión@R
    plt.figure(figsize=(8, 5))
    plt.plot(Rs, precisiones, marker="o", label="Precisión@R", color="#2563eb")
    plt.xticks(Rs)
    plt.ylim(0, 1.1)
    plt.xlabel("Número de documentos recuperados (R)")
    plt.ylabel("Precisión")
    plt.title("Evolución de Precisión@R")
    plt.legend()
    plt.grid(alpha=.3)
    plt.tight_layout()
    plt.savefig("curva_precision_R.png", dpi=150)
    plt.close()

    print("\nGráficas guardadas: 'grafica_metricas_globales.png' y 'curva_precision_R.png'")

def main():
    indice = crear_indice_invertido(DOCUMENTOS)
    recuperados, terminos_consulta, puntuaciones = buscar(CONSULTA, indice, DOCUMENTOS)

    m = metricas(recuperados, RELEVANTES)
    p_at_R = calcular_precision_R(recuperados, RELEVANTES)

    print("=" * 70)
    print("EVALUACIÓN DE RECUPERACIÓN DE INFORMACIÓN")
    print("=" * 70)
    print(f"\nConsulta: {CONSULTA}")
    print(f"Términos procesados: {terminos_consulta}")

    print("\nDocumentos recuperados:")
    for doc_id in recuperados:
        etiqueta = "RELEVANTE" if doc_id in RELEVANTES else "NO RELEVANTE"
        print(f"  {doc_id}: coincidencias={puntuaciones[doc_id]} - {etiqueta}")

    print(f"\nVerdaderos Positivos (VP): {m['vp']}")
    print(f"Falsos Positivos (FP):     {m['fp']}")
    print(f"Falsos Negativos (FN):     {m['fn']}")

    print("\nMÉTRICAS GENERALES")
    print(f"Precisión     = VP / (VP + FP) = {m['precision']:.2%}")
    print(f"Exhaustividad = VP / (VP + FN) = {m['exhaustividad']:.2%}")
    print(f"F1            = 2 (P * E) / (P + E) = {m['f1']:.4f} ({m['f1']:.2%})")

    print("\nPRECISIÓN EN R (Precisión@R)")
    for r_tag, value in p_at_R.items():
        print(f"  {r_tag}: {value:.2%}")

    graficar(recuperados, RELEVANTES)

if __name__ == "__main__":
    main()
