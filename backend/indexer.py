import re
import json
import os
from collections import defaultdict, Counter

STOPWORDS_ES = {
    "a", "al", "ante", "bajo", "con", "contra", "de", "del", "desde", "durante", "en", "entre",
    "hacia", "hasta", "para", "por", "según", "segun", "sin", "sobre", "tras", "y", "e", "o", "u", "ni",
    "que", "como", "cómo", "cuando", "cuándo", "donde", "dónde", "quien", "quién", "el", "él", "la",
    "los", "las", "un", "una", "unos", "unas", "mi", "mí", "tu", "tú", "su", "sus", "este", "esta",
    "estos", "estas", "es", "son", "ser", "fue", "eran", "hay", "ha", "han", "se", "lo", "le", "les",
    "me", "te", "nos", "más", "mas", "muy"
}

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

# --- 2. NUEVA FUNCIÓN: CREAR ÍNDICE DESDE EL JSON DEL RASTREADOR ---
def crear_indice_desde_json():
    ruta_entrada = os.path.join("..", "data", "sin_procesar", "resultados_rastreo.json")
    ruta_salida = os.path.join("..", "data", "indice", "indice_invertido.json")

    print("Cargando datos del rastreador...")
    with open(ruta_entrada, 'r', encoding='utf-8') as f:
        datos = json.load(f)

    paginas = datos.get("paginas", [])
    indice_invertido = defaultdict(dict)
    vocabulario = set()

    print(f"Indexando {len(paginas)} documentos...")

    for pagina in paginas:
        url = pagina["url"]
        # Juntamos todo el texto útil del documento
        texto_crudo = f"{pagina.get('titulo', '')} {pagina.get('descripcion', '')} {pagina.get('texto', '')}"
        
        # Procesamos con tu pipeline
        terminos = procesar(texto_crudo)
        
        # Contamos frecuencias (TF)
        frecuencias = Counter(terminos)
        
        # Llenamos el índice invertido
        for palabra, freq in frecuencias.items():
            indice_invertido[palabra][url] = freq
            vocabulario.add(palabra)

    # Estructura final
    resultado = {
        "estadisticas": {
            "total_documentos": len(paginas),
            "total_terminos_unicos": len(vocabulario)
        },
        "indice": dict(indice_invertido)
    }

    # Guardamos el archivo
    os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)
    with open(ruta_salida, 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"\n¡Índice creado con éxito!")
    print(f"Términos únicos en el vocabulario: {len(vocabulario)}")
    print(f"Guardado en: {ruta_salida}")

if __name__ == "__main__":
    crear_indice_desde_json()