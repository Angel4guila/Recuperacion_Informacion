def pagerank(grafo, factor_estancia = 0.85, epsilon=1e-6, max_iteraciones = 100):
    nodos = list(grafo.keys())
    n= len(nodos)

    #vector pagerank 1/n
    pr={nodo: 1.0/ n for nodo in nodos}

    #enclaces salientes c(T) para cada nodo
    enlace_salida = {nodo: len(links) for nodo, links in grafo.items()}

    #Mepeo de enlaces entrantes para cada nodo
    Ti = {nodo: [] for nodo in nodos}
    for nodo, links in grafo.items():
        for objetivo in links:
            Ti[objetivo].append(nodo)

    print(f"PR Inicial (0): {[round(pr[nodo],4) for nodo in nodos]}\n")

    iteracion = 0
    while iteracion < max_iteraciones:
        pr_nuervo ={}
        max_diferencia=0

        for u in nodos:
            #Sumatoria: PR(ti)/C(ti)
            sumatoria = 0
            for t in Ti[u]:
                sumatoria += pr[t]/enlace_salida[t]

            #Formula pageRank
            pr_nuervo[u] = (1 - factor_estancia) / n + factor_estancia * sumatoria

            #medir la diferencia con respecto a la iteracion anterior
            diferencia = abs(pr_nuervo[u] - pr[u])
            if diferencia > max_diferencia:
                max_diferencia = diferencia

        iteracion += 1
        print(f"Iteración ({iteracion}): {[round(pr_nuervo[nodo], 4) for nodo in nodos]}")

        #condicion de parada
        if max_diferencia < epsilon:
            print(f"\n Convergencia alcanzada en la iteración {iteracion}")
            break

        pr = pr_nuervo

    return pr



grafo_ejemplo = {'A': ['B', 'C'], 'B': ['D'], 'C': ['D'], 'D': ['A']}
# A apunta a B y C (salientes: 2)
# B apunta a D (saliente: 1)
# C apunta a D (saliente: 1)
# D apunta a A (saliente: 1)

resultados = pagerank(grafo_ejemplo)