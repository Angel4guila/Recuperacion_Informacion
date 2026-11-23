# Evaluación del buscador

El evaluador usa las mismas búsquedas y el mismo ranking que la aplicación. Necesita juicios humanos: para cada consulta, registra las URLs relevantes de todo el corpus. Las URLs no incluidas se consideran no relevantes, por lo que recall solo es válido si la lista de relevantes está completa para esa consulta.

El archivo incluido contiene dos etiquetas mínimas de demostración para que puedas ejecutar el programa. No tomes sus métricas ni los pesos resultantes como una evaluación representativa: agrega varias consultas y completa sus juicios de relevancia antes de sacar conclusiones.

Edita `data/evaluacion/juicios_relevancia.json` con este formato:

```json
{
  "k": 5,
  "consultas": [
    {
      "consulta": "medicina",
      "particion": "ajuste",
      "relevantes": [
        "http://localhost/sitio_web/corpus/ruta/a/medicina.html"
      ]
    },
    {
      "consulta": "facultad de medicina",
      "particion": "prueba",
      "relevantes": [
        "http://localhost/sitio_web/corpus/ruta/a/medicina.html"
      ]
    }
  ]
}
```

Usa consultas distintas en `ajuste` y `prueba`. Las consultas de ajuste seleccionan el peso TF-IDF/PageRank que maximiza F1@k; las de prueba reportan precision@k, recall@k y F1@k sin participar en esa selección. Incluye varias consultas representativas en cada partición para reducir el sobreajuste.

Ejecuta desde la raíz del proyecto:

```bash
python backend/evaluacion.py
```

El programa guarda los pesos seleccionados en `data/evaluacion/pesos_ranking.json`. El motor los carga al iniciarse; reinicia la aplicación o la CLI después de calibrar. Sin ese archivo, los pesos iniciales son 0.7 para TF-IDF y 0.3 para PageRank.

Precision@k es la cantidad de resultados relevantes en los primeros k, dividida entre k. Recall@k es esa misma cantidad dividida entre el total de documentos relevantes juzgados para la consulta. F1@k es la media armónica de ambas y es el objetivo usado para seleccionar los pesos.