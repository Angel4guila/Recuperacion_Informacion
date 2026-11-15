import json
import numpy as np
from urllib.parse import urljoin
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

json_path = BASE_DIR.parent / 'data' / 'sin_procesar' / 'resultados_rastreo.json'
output_path = BASE_DIR.parent / 'data' / 'graph' / 'pagerank.json'

def construir_grafo_y_pagerank(d=0.85, E=1e-6, max_iter=100):
    # Cargar el JSON de resultados de rastreo
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    paginas = data.get('paginas', [])
    if not paginas:
        # Intentar respaldo con el sitemap si la lista de páginas estuviera vacía
        urls_sitemap = data.get('sitemap', {}).get('urls', [])
        paginas = [{'url': u, 'titulo': '', 'texto': ''} for u in urls_sitemap]

    # Mapeo de URLs e índices
    urls = [p['url'] for p in paginas]
    url_to_idx = {url: i for i, url in enumerate(urls)}
    n = len(urls)
    
    # Crear un diccionario auxiliar de títulos para vincular "Temas relacionados"
    titulo_to_url = {}
    for p in paginas:
        titulo = p.get('titulo', '').split('|')[0].strip().lower()
        if titulo:
            titulo_to_url[titulo] = p['url']

    # Inicializar matriz de adyacencia (n x n)
    matriz_adyacencia = np.zeros((n, n), dtype=float)
    
    # URL base y raíz
    base_url = data.get('inicio', 'http://localhost/sitio_web/')

    # Construcción del grafo de enlaces basado en la estructura del corpus
    for i, p in enumerate(paginas):
        current_url = p['url']
        texto = p.get('texto', '').lower()
        
        destinos = set()
        
        # Enlace estructural 1: Todas las páginas enlazan a la página de inicio / raíz
        destinos.add(base_url)
        
        # Enlace estructural 2: Enlace al índice de su facultad (si aplica)
        partes_url = current_url.split('/')
        if 'corpus' in partes_url:
            idx_corpus = partes_url.index('corpus')
            if len(partes_url) > idx_corpus + 2:
                # Construir URL del índice de la facultad correspondiente
                facultad_path = "/".join(partes_url[:idx_corpus + 3]) + "/index.html"
                destinos.add(facultad_path)

        # Enlace estructural 3: Extraer "Temas relacionados" mencionados en el texto del documento
        for titulo, t_url in titulo_to_url.items():
            if titulo in texto and t_url != current_url:
                destinos.add(t_url)

        # Registrar los enlaces en la matriz de adyacencia
        for dest in destinos:
            dest_clean = dest.split('#')[0]
            if dest_clean in url_to_idx:
                j = url_to_idx[dest_clean]
                matriz_adyacencia[i][j] = 1.0

    # Normalización de la matriz (manejo de sumideros / nodos sin enlaces salientes)
    for i in range(n):
        suma_salientes = np.sum(matriz_adyacencia[i])
        if suma_salientes == 0:
            # Distribución uniforme si es un nodo sumidero (teleportación total)
            matriz_adyacencia[i] = 1.0 / n
        else:
            matriz_adyacencia[i] = matriz_adyacencia[i] / suma_salientes

    # Cálculo de PageRank mediante método iterativo (Power Iteration)
    PR = np.ones(n) / n
    M = matriz_adyacencia.copy()

    for iteracion in range(1, max_iter + 1):
        PR_next = (1 - d) / n + d * np.dot(PR, M)
        
        # Comprobar convergencia
        if np.max(np.abs(PR_next - PR)) < E:
            PR = PR_next
            print(f"Convergencia alcanzada en la iteración {iteracion}.")
            break
        PR = PR_next

    # Creamos el directorio en caso de que no exista
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Organizar resultados y guardar en pagerank.json
    resultados = {urls[i]: float(PR[i]) for i in range(n)}
    
    # Ordenar de mayor a menor puntaje de PageRank
    resultados_ordenados = dict(sorted(resultados.items(), key=lambda item: item[1], reverse=True))

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(resultados_ordenados, f, ensure_ascii=False, indent=4)

    print(f"¡Proceso completado! Archivo '{output_path}' generado exitosamente con {n} nodos evaluados.")

if __name__ == '__main__':
    construir_grafo_y_pagerank()