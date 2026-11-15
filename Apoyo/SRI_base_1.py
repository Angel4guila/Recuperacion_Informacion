import re
from collections import Counter

# Stopwords en español
STOPWORDS_ES = {
    "el", "la", "los", "las", "de", "del", "al", "a", "en", "con", "por", "para",
    "y", "o", "que", "donde", "como", "porque", "si", "no", "pero", "sino",
    "este", "esta", "estos", "estas", "un", "una", "unos", "unas", "muy", "mas",
    "es", "son", "ser", "fue", "hay", "ha", "han", "estar", "estado", "tiene",
    "tener", "hacer", "poder", "decir", "ver", "dar", "saber", "querer", "ir"
}

def normalize_text(text):
    """Normaliza: minúsculas y conserva acentos para mostrarlos correctamente."""
    text = text.lower()
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'[^\w\sáéíóúüñÁÉÍÓÚÜÑ]', ' ', text, flags=re.UNICODE)
    return ' '.join(text.split())

def remove_stopwords(tokens):
    """Elimina stopwords del listado de tokens."""
    return [t for t in tokens if t not in STOPWORDS_ES]

def simple_stemmer(word):
    """Stemming simple: elimina sufijos comunes del español."""
    suffixes = ['ando', 'iendo', 'ado', 'ido', 'ar', 'er', 'ir', 'os', 'as', 'es', 'a', 'o', 's', 'n', 'r']
    for suffix in suffixes:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[:-len(suffix)]
    return word

def extract_noun_groups(tokens):
    """Extrae grupos de dos palabras consecutivas (heurística simple)."""
    return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1) 
            if len(tokens[i]) > 3 and len(tokens[i+1]) > 3]

def get_keywords(tokens, top_n=10):
    """Obtiene las keywords por frecuencia."""
    return Counter(tokens).most_common(top_n)

def ir_pipeline(documento):
    """Ejecuta todo el pipeline de IR."""
    print("=" * 70)
    print("SISTEMA DE RECUPERACIÓN DE INFORMACIÓN - DEMOSTRACIÓN")
    print("=" * 70)
    
    # Paso 1: Original
    print("\n1. DOCUMENTO ORIGINAL:")
    print(documento[:150] + "...")
    
    # Paso 2: Normalización
    normalizado = normalize_text(documento)
    print(f"\n2. NORMALIZADO (sin acentos, minúsculas):")
    print(normalizado[:150] + "...")
    
    # Paso 3: Tokenización
    tokens = normalizado.split()
    print(f"\n3. TOKENIZACIÓN ({len(tokens)} tokens):")
    print(tokens[:40], "...")
    
    # Paso 4: Sin stopwords
    filtrados = remove_stopwords(tokens)
    print(f"\n4. SIN STOPWORDS ({len(filtrados)} tokens):")
    print(filtrados[:15], "...")
    
    # Paso 5: Stemming
    stems = [simple_stemmer(t) for t in filtrados]
    print(f"\n5. STEMMING (raíces):")
    print(stems[:15], "...")
    
    # Paso 6: Grupos sustantivos
    grupos = extract_noun_groups(filtrados)
    print(f"\n6. GRUPOS SUSTANTIVOS:")
    print(grupos[:8])
    
    # Paso 7: Keywords
    keywords = get_keywords(stems)
    print(f"\n7. KEYWORDS (top 10):")
    for term, freq in keywords:
        print(f"   {term}: {freq}")
    
    # Paso 8: Indexación
    print(f"\n8. INDEXACIÓN:")
    print(f"   Doc_001 -> {{{', '.join([t for t, _ in keywords[:10]])}}}")
    
    print("\n" + "=" * 70)

# Documento de ejemplo
doc_ejemplo = """
La computación cuántica representa un cambio paradigmático respecto a la informática clásica al aprovechar las propiedades fundamentales de la mecánica cuántica. Mientras que los sistemas tradicionales procesan información mediante bits binarios que representan un cero o un uno, los ordenadores cuánticos utilizan qubits. Estos pueden existir en estados de superposición, procesando múltiples combinaciones simultáneamente, y entrelazamiento, permitiendo que el estado de un qubit influya instantáneamente en otro.
"""

# Ejecutar
ir_pipeline(doc_ejemplo)