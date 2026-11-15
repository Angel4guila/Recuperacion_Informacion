#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rastreador.py  ·  Rastreador web didáctico (solo biblioteca estándar)
=====================================================================

Objetivo: mostrar, con código legible, las decisiones que toma un robot de
buscador cuando visita un sitio. NO es Google ni pretende serlo: es un
laboratorio de 300 líneas para ver el mecanismo por dentro.

El recorrido que implementa es el mismo del README:

    PASO 1  Descargar  /robots.txt  y aprender qué se puede visitar.
    PASO 2  Leer la línea "Sitemap:" y descargar el sitemap.
    PASO 3  Poner en cola las URLs del sitemap.
    PASO 4  Descargar cada página respetando las reglas de robots.txt.
    PASO 5  Extraer título, descripción, h1, canonical, JSON-LD y enlaces.
    PASO 6  Seguir los enlaces internos (sin salir del dominio, sin nofollow).

Uso:
    python3 rastreador.py
    python3 rastreador.py --url http://localhost/ --max 10 --verbose
    python3 rastreador.py --user-agent GPTBot          # simular un robot de IA
    python3 rastreador.py --url http://localhost/ --delay 0

Requisitos: Python 3.9 o superior. Sin dependencias externas (no hace falta
requests ni BeautifulSoup), precisamente para que se vea qué hay debajo.

Aviso ético: rastrea solo sitios propios o con permiso, identifícate con un
User-Agent real y deja una pausa entre peticiones. Un crawler mal educado es
un problema para el servidor de otra persona.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from html.parser import HTMLParser
from xml.etree import ElementTree

# ---------------------------------------------------------------------------
# Configuración por defecto
# ---------------------------------------------------------------------------
AGENTE = "DemostradorBot/1.0 (+ejemplo didáctico; contacto: ejemplo@localhost)"
TIEMPO_MAXIMO = 10          # segundos por petición
MAX_PAGINAS = 20            # freno de seguridad: nunca rastrear sin límite
RETARDO = 0.3               # pausa entre peticiones (cortesía con el servidor)


# ===========================================================================
# UTILIDADES DE URL
# ===========================================================================
def normalizar(url: str, base: str | None = None) -> str | None:
    """Convierte una URL relativa en absoluta y elimina el fragmento (#...).

    Devuelve None si no es una URL http/https navegable.
    """
    absoluta = urllib.parse.urljoin(base, url.strip())
    partes = urllib.parse.urlsplit(absoluta)

    if partes.scheme not in ("http", "https"):
        return None

    ruta = partes.path or "/"
    # El fragmento (#seccion) no se envía al servidor: se descarta.
    return urllib.parse.urlunsplit(
        (partes.scheme, partes.netloc, ruta, partes.query, "")
    )


def descargar(url: str, agente: str) -> tuple[int, str, bytes, str]:
    """Hace una petición GET y devuelve (estado, content-type, bytes, charset)."""
    peticion = urllib.request.Request(
        url,
        headers={
            # Identificarse es parte de la buena práctica: el webmaster puede
            # saber quién llama y bloquearlo si molesta.
            "User-Agent": agente,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(peticion, timeout=TIEMPO_MAXIMO) as respuesta:
        datos = respuesta.read()
        tipo = respuesta.headers.get("Content-Type", "")
        charset = respuesta.headers.get_content_charset() or "utf-8"
        return respuesta.status, tipo, datos, charset


# ===========================================================================
# PASO 1 · robots.txt
# ===========================================================================
class Robots:
    """Lector mínimo del protocolo de exclusión de robots (RFC 9309).

    Estructura del archivo:

        User-agent: Googlebot
        Allow: /                      <- puede rastrear todo
        Disallow: /privado.html       <- menos esta ruta

        User-agent: *
        Disallow: /

    Reglas que implementamos:
      * Varios "User-agent" seguidos comparten las mismas reglas.
      * Se aplica el grupo del robot concreto; si no existe, el grupo "*".
      * Si varias reglas coinciden, gana la más específica (patrón más largo).
      * En empate, gana "Allow".
      * "*" comodín y "$" fin de ruta, como en Google.
    """

    def __init__(self) -> None:
        self.reglas: dict[str, list[tuple[bool, str]]] = {}
        self.sitemaps: list[str] = []
        self.existe = False
        self.error: str | None = None

    # -- construcción -----------------------------------------------------
    @classmethod
    def desde_url(cls, url: str, agente: str) -> "Robots":
        robots = cls()
        try:
            _, _, datos, _ = descargar(url, agente)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                # Sin permiso explícito: se asume todo prohibido.
                robots.existe = True
                robots.reglas["*"] = [(False, "/")]
                robots.error = f"HTTP {e.code}: se asume todo prohibido"
            elif e.code == 404:
                robots.error = "HTTP 404: no hay robots.txt, se permite todo"
            else:
                robots.error = f"HTTP {e.code}: se permite todo"
            return robots
        except Exception as e:  # red caída, DNS, TLS...
            robots.error = f"{type(e).__name__}: se permite todo"
            return robots

        robots.existe = True
        robots.desde_texto(datos.decode("utf-8", "replace"))
        return robots

    def desde_texto(self, texto: str) -> None:
        agente_actual: str | None = None

        for linea in texto.splitlines():
            # Los comentarios empiezan por # y pueden ir tras la directiva.
            linea = linea.split("#", 1)[0].strip()
            if not linea or ":" not in linea:
                continue

            campo, valor = linea.split(":", 1)
            campo = campo.strip().lower()
            valor = valor.strip()

            if campo == "user-agent":
                agente_actual = valor.lower()
                self.reglas.setdefault(agente_actual, [])
            elif campo in ("allow", "disallow") and agente_actual is not None:
                if valor:  # "Disallow:" vacío significa "no bloquear nada"
                    self.reglas[agente_actual].append((campo == "allow", valor))
            elif campo == "sitemap":
                self.sitemaps.append(valor)

    # -- consulta ---------------------------------------------------------
    @staticmethod
    def _token(agente: str) -> str:
        """De 'DemostradorBot/1.0 (+...)' extrae 'demostradorbot'."""
        return agente.split("/")[0].strip().lower()

    def reglas_para(self, agente: str) -> list[tuple[bool, str]]:
        token = self._token(agente)
        if token in self.reglas:
            return self.reglas[token]
        return self.reglas.get("*", [])

    def permite(self, agente: str, url: str) -> bool:
        """¿Puede este robot pedir esta URL?"""
        if not self.existe:
            return True

        partes = urllib.parse.urlsplit(url)
        objetivo = partes.path or "/"
        if partes.query:
            objetivo += "?" + partes.query

        mejor: tuple[int, int] | None = None   # (longitud del patrón, 1=allow)
        for permitido, patron in self.reglas_para(agente):
            if _coincide(patron, objetivo):
                candidato = (len(patron), 1 if permitido else 0)
                if mejor is None or candidato > mejor:
                    mejor = candidato

        # Si ninguna regla coincide, se permite.
        return True if mejor is None else mejor[1] == 1


def _coincide(patron: str, ruta: str) -> bool:
    """Traduce un patrón de robots.txt (* y $) a una expresión regular."""
    regex = ""
    for i, caracter in enumerate(patron):
        if caracter == "*":
            regex += ".*"
        elif caracter == "$" and i == len(patron) - 1:
            regex += "$"
        else:
            regex += re.escape(caracter)
    return re.match("^" + regex, ruta) is not None


# ===========================================================================
# PASO 2 · sitemap.xml
# ===========================================================================
def leer_sitemap(url: str, agente: str, profundidad: int = 1) -> list[str]:
    """Devuelve las URLs de un sitemap. Soporta <sitemapindex> anidado."""
    estado, _, datos, _ = descargar(url, agente)
    raiz = ElementTree.fromstring(datos)

    def etiqueta(elemento) -> str:
        # Los sitemaps usan un namespace XML: "{http://...}loc" -> "loc"
        return elemento.tag.split("}")[-1]

    locs = [
        normalizar(elemento.text)
        for elemento in raiz.iter()
        if etiqueta(elemento) == "loc" and elemento.text
    ]
    locs = [u for u in locs if u]

    if etiqueta(raiz) == "sitemapindex" and profundidad > 0:
        # Un sitemap índice no contiene páginas, sino otros sitemaps.
        urls: list[str] = []
        for hijo in locs:
            urls.extend(leer_sitemap(hijo, agente, profundidad - 1))
        return urls

    return locs


# ===========================================================================
# PASO 5 · extracción del HTML
# ===========================================================================
class ExtractorHTML(HTMLParser):
    """Saca del HTML justo lo que un buscador usa para entender la página.

    Se usa html.parser de la biblioteca estándar: no interpreta CSS ni ejecuta
    JavaScript, igual que el primer rastreo de la mayoría de buscadores.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.titulo = ""
        self.descripcion: str | None = None
        self.robots_meta: str | None = None
        self.canonical: str | None = None
        self.h1: list[str] = []
        self.enlaces: list[tuple[str, str]] = []   # (href, rel)
        self.json_ld: list[str] = []
        self._texto: list[str] = []

        self._en_titulo = False
        self._en_h1 = False
        self._h1_actual = ""
        self._en_script = False
        self._script_tipo = ""
        self._script_datos = ""
        self._ignorar = 0      # dentro de <style> o <noscript>

    # -- etiquetas --------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)

        if tag == "title":
            self._en_titulo = True
        elif tag == "h1":
            self._en_h1 = True
            self._h1_actual = ""
        elif tag == "meta":
            nombre = (atributos.get("name") or "").lower()
            contenido = (atributos.get("content") or "").strip()
            if nombre == "description":
                self.descripcion = contenido
            elif nombre == "robots":
                self.robots_meta = contenido
        elif tag == "link":
            if (atributos.get("rel") or "").lower() == "canonical":
                self.canonical = atributos.get("href")
        elif tag == "a":
            href = atributos.get("href")
            if href:
                self.enlaces.append((href, (atributos.get("rel") or "").lower()))
        elif tag == "script":
            self._en_script = True
            self._script_tipo = (atributos.get("type") or "").lower()
            self._script_datos = ""
        elif tag in ("style", "noscript"):
            self._ignorar += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._en_titulo = False
        elif tag == "h1":
            self._en_h1 = False
            self.h1.append(self._h1_actual.strip())
        elif tag == "script":
            if "ld+json" in self._script_tipo and self._script_datos.strip():
                self.json_ld.append(self._script_datos.strip())
            self._en_script = False
            self._script_datos = ""
        elif tag in ("style", "noscript") and self._ignorar > 0:
            self._ignorar -= 1

    def handle_data(self, data):
        if self._en_titulo:
            self.titulo += data
        elif self._en_h1:
            self._h1_actual += data
        elif self._en_script:
            self._script_datos += data
        elif self._ignorar == 0:
            self._texto.append(data)

    # -- resultado --------------------------------------------------------
    def palabras(self) -> int:
        return len(" ".join(self._texto).split())


# ===========================================================================
# PASOS 3, 4, 5 y 6 · el bucle de rastreo
# ===========================================================================
def rastrear(
    inicio: str,
    agente: str,
    maximo: int,
    retardo: float,
    verbose: bool,
) -> dict:
    partes = urllib.parse.urlsplit(inicio)
    host = partes.netloc.lower()
    robots_url = f"{partes.scheme}://{host}/robots.txt"

    # ------------------------------------------------------------------
    # PASO 1: robots.txt
    # ------------------------------------------------------------------
    print(f"\n[1] robots.txt  ->  {robots_url}")
    robots = Robots.desde_url(robots_url, agente)

    if robots.existe:
        print(f"    OK · {sum(len(r) for r in robots.reglas.values())} reglas leídas")
    elif robots.error:
        print(f"    aviso: {robots.error}")

    if verbose:
        for nombre, reglas in robots.reglas.items():
            print(f"    grupo '{nombre}':")
            for permitido, patron in reglas:
                print(f"      {'Allow' if permitido else 'Disallow'}: {patron}")
        print(f"    reglas aplicables a '{Robots._token(agente)}': "
              f"{robots.reglas_para(agente) or 'ninguna (todo permitido)'}")

    # ------------------------------------------------------------------
    # PASO 2: sitemap
    # ------------------------------------------------------------------
    sitemap_urls: list[str] = []
    candidato = f"{partes.scheme}://{host}/sitemap.xml"

    print("\n[2] sitemap.xml")

    # Primero, lo que declare robots.txt; si no hay, la convención /sitemap.xml.
    declarados = robots.sitemaps
    if not declarados:
        print("    robots.txt no declara ninguno; se prueba /sitemap.xml por convención")
        declarados = [candidato]

    for sitemap in declarados:
        sm = urllib.parse.urlsplit(sitemap)
        if sm.netloc.lower() != host:
            # ¡Lección importante! Si robots.txt apunta a otro dominio, sus URLs
            # no sirven para este sitio: se avisa y se usa el sitemap local.
            print(f"    ⚠ el sitemap declarado es de OTRO dominio: {sitemap}")
            print("      -> se ignora y se usa el sitemap por convención")
            continue
        try:
            encontradas = leer_sitemap(sitemap, agente)
            print(f"    {sitemap}  ->  {len(encontradas)} URLs")
            sitemap_urls.extend(encontradas)
        except Exception as e:
            print(f"    ⚠ no se pudo leer {sitemap}: {type(e).__name__}: {e}")

    if not sitemap_urls:
        try:
            sitemap_urls = leer_sitemap(candidato, agente)
            print(f"    {candidato}  ->  {len(sitemap_urls)} URLs")
        except Exception as e:
            print(f"    ⚠ sin sitemap utilizable ({type(e).__name__}: {e})")

    # ------------------------------------------------------------------
    # PASO 3: cola de URLs (sitemap + URL inicial)
    # ------------------------------------------------------------------
    cola: deque[str] = deque()
    origen: dict[str, str] = {}

    def encolar(url: str, fuente: str) -> None:
        destino = normalizar(url)
        if not destino:
            return
        if urllib.parse.urlsplit(destino).netloc.lower() != host:
            return                       # fuera del sitio: no se rastrea
        if destino not in origen:
            origen[destino] = fuente
            cola.append(destino)

    encolar(inicio, "URL inicial")
    for url in sitemap_urls:
        encolar(url, "sitemap.xml")

    print(f"\n[3] cola inicial: {len(cola)} URLs "
          f"({sum(1 for f in origen.values() if f == 'sitemap.xml')} del sitemap)")

    # ------------------------------------------------------------------
    # PASOS 4-6: bucle
    # ------------------------------------------------------------------
    visitadas: dict[str, dict] = {}
    bloqueadas: list[str] = []
    errores: list[tuple[str, str]] = []
    externos: set[str] = set()
    nofollow: set[str] = set()

    print(f"\n[4] rastreando (máximo {maximo} páginas, "
          f"pausa {retardo}s, agente {agente.split('/')[0]})\n")

    while cola and len(visitadas) < maximo:
        url = cola.popleft()
        if url in visitadas:
            continue

        # PASO 4a: ¿lo permite robots.txt?
        if not robots.permite(agente, url):
            bloqueadas.append(url)
            print(f"    ⛔ BLOQUEADA por robots.txt: {url}")
            continue

        if retardo:
            time.sleep(retardo)          # cortesía: no saturar el servidor

        try:
            estado, tipo, datos, charset = descargar(url, agente)
        except urllib.error.HTTPError as e:
            errores.append((url, f"HTTP {e.code}"))
            print(f"    ✘ HTTP {e.code}: {url}")
            continue
        except Exception as e:
            errores.append((url, type(e).__name__))
            print(f"    ✘ {type(e).__name__}: {url}")
            continue

        print(f"    ✔ {estado} {url}")

        if "html" not in tipo.lower():
            # Un enlace puede apuntar a un PDF, un CSS o un XML: se descarga
            # (si robots lo permite), pero no se analiza como página.
            print(f"      ↳ no es HTML ({tipo.split(';')[0] or 'sin tipo'}), "
                  "se omite el análisis")
            continue

        html = datos.decode(charset, "replace")

        # PASO 5: extraer la información
        extractor = ExtractorHTML()
        extractor.feed(html)

        noindex = "noindex" in (extractor.robots_meta or "").lower()

        visitadas[url] = {
            "url": url,
            "origen": origen.get(url, "?"),
            "estado": estado,
            "titulo": " ".join(extractor.titulo.split()),
            "descripcion": " ".join((extractor.descripcion or "").split()),
            "h1": extractor.h1,
            "canonical": extractor.canonical,
            "robots_meta": extractor.robots_meta,
            "noindex": noindex,
            "json_ld": len(extractor.json_ld),
            "palabras": extractor.palabras(),
        }

        # PASO 6: seguir enlaces
        for href, rel in extractor.enlaces:
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue

            destino = normalizar(href, base=url)
            if not destino:
                continue

            if urllib.parse.urlsplit(destino).netloc.lower() != host:
                externos.add(destino)    # se registra, no se rastrea
                continue

            if "nofollow" in rel:
                nofollow.add(destino)    # el autor pide no seguir el enlace
                continue

            encolar(destino, url)

    return {
        "inicio": inicio,
        "agente": agente,
        "robots": {
            "encontrado": robots.existe,
            "error": robots.error,
            "sitemaps_declarados": robots.sitemaps,
            "reglas_aplicadas": [
                f"{'Allow' if p else 'Disallow'}: {pat}"
                for p, pat in robots.reglas_para(agente)
            ],
        },
        "sitemap": {"urls": sitemap_urls},
        "paginas": list(visitadas.values()),
        "bloqueadas": bloqueadas,
        "errores": errores,
        "enlaces_externos": sorted(externos),
        "nofollow": sorted(nofollow),
        "estadisticas": {
            "paginas_visitadas": len(visitadas),
            "bloqueadas": len(bloqueadas),
            "errores": len(errores),
            "enlaces_externos": len(externos),
            "urls_en_sitemap": len(sitemap_urls),
        },
    }


# ===========================================================================
# INFORME
# ===========================================================================
def recortar(texto: str, ancho: int) -> str:
    return texto if len(texto) <= ancho else texto[: ancho - 1] + "…"


def imprimir_informe(resultado: dict) -> None:
    print("\n" + "=" * 74)
    print("RESUMEN DEL RASTREO")
    print("=" * 74)

    print("\nPáginas rastreadas e información extraída:\n")
    for pagina in resultado["paginas"]:
        print(f"  URL:   {pagina['url']}")
        print(f"  Title: {recortar(pagina['titulo'] or '(SIN TITLE)', 70)}")
        if pagina["descripcion"]:
            print(f"  Meta:  {recortar(pagina['descripcion'], 70)}")
        else:
            print("  Meta:  ⚠ sin meta description")

        if len(pagina["h1"]) == 1:
            print(f"  H1:    {recortar(pagina['h1'][0], 70)}")
        elif not pagina["h1"]:
            print("  H1:    ⚠ la página no tiene <h1>")
        else:
            print(f"  H1:    ⚠ {len(pagina['h1'])} etiquetas <h1> (debería haber 1)")

        print(f"  Datos: {pagina['json_ld']} bloque(s) JSON-LD · "
              f"{pagina['palabras']} palabras · origen: {pagina['origen']}")

        if pagina["canonical"]:
            print(f"  Canonical: {pagina['canonical']}")
        if pagina["noindex"]:
            print("  ⚠ meta robots: noindex -> NO debería indexarse")
        print()

    print("-" * 74)
    print("Bloqueadas por robots.txt:")
    for url in resultado["bloqueadas"] or ["(ninguna)"]:
        print(f"  ⛔ {url}")

    if resultado["errores"]:
        print("\nErrores de descarga:")
        for url, motivo in resultado["errores"]:
            print(f"  ✘ {motivo}: {url}")

    if resultado["nofollow"]:
        print("\nEnlaces nofollow (no seguidos):")
        for url in resultado["nofollow"]:
            print(f"  ⊘ {url}")

    if resultado["enlaces_externos"]:
        print(f"\nEnlaces externos encontrados (no rastreados): "
              f"{len(resultado['enlaces_externos'])}")
        for url in resultado["enlaces_externos"][:5]:
            print(f"  ↗ {recortar(url, 70)}")
        if len(resultado["enlaces_externos"]) > 5:
            print(f"  … y {len(resultado['enlaces_externos']) - 5} más")

    # Contenido duplicado: dos URLs con el mismo título y el mismo número de
    # palabras suelen ser la misma página servida con dos direcciones
    # (por ejemplo, "/" y "/index.html").
    grupos: dict[tuple[str, int], list[str]] = {}
    for pagina in resultado["paginas"]:
        if pagina["titulo"]:
            clave = (pagina["titulo"], pagina["palabras"])
            grupos.setdefault(clave, []).append(pagina["url"])

    duplicados = {clave: urls for clave, urls in grupos.items() if len(urls) > 1}
    if duplicados:
        print("\nPosibles duplicados (mismo título y nº de palabras):")
        for (titulo, _), urls in duplicados.items():
            print(f"  ⚠ «{recortar(titulo, 50)}»")
            for url in urls:
                print(f"      {url}")
        print('  Solución: deja una sola URL o indica la preferida con <link rel="canonical">.')

    print("\n" + "-" * 74)
    print("Cobertura del sitemap:")
    en_sitemap = set(resultado["sitemap"]["urls"])
    visitadas = {p["url"] for p in resultado["paginas"]}
    bloqueadas = set(resultado["bloqueadas"])

    for url in sorted(en_sitemap):
        if url in visitadas:
            print(f"  ✔ rastreada   {url}")
        elif url in bloqueadas:
            print(f"  ⛔ bloqueada   {url}  (¡incoherencia: está en el sitemap!)")
        else:
            print(f"  ?  no visitada {url}")

    print("\n" + "-" * 74)
    stats = resultado["estadisticas"]
    print(
        f"Totales: {stats['paginas_visitadas']} páginas · "
        f"{stats['bloqueadas']} bloqueadas · {stats['errores']} errores · "
        f"{stats['urls_en_sitemap']} URLs en el sitemap"
    )
    print("=" * 74 + "\n")


# ===========================================================================
# PROGRAMA PRINCIPAL
# ===========================================================================
def main(argv: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(
        description="Rastreador web didáctico: robots.txt, sitemap.xml y enlaces.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    analizador.add_argument(
        "--url", default="http://172.26.160.223",
        help="URL de inicio del sitio",
    )
    analizador.add_argument(
        "--max", type=int, default=MAX_PAGINAS,
        help="número máximo de páginas a descargar",
    )
    analizador.add_argument(
        "--delay", type=float, default=RETARDO,
        help="segundos de pausa entre peticiones",
    )
    analizador.add_argument(
        "--user-agent", default=AGENTE,
        help="User-Agent con el que identificarse (ej. GPTBot, Googlebot)",
    )
    analizador.add_argument(
        "--verbose", action="store_true",
        help="mostrar las reglas de robots.txt leídas",
    )
    analizador.add_argument(
        "--salida", default="resultados_rastreo.json",
        help="archivo JSON donde guardar el resultado",
    )
    argumentos = analizador.parse_args(argv)

    inicio = normalizar(argumentos.url)
    if not inicio:
        print(f"URL no válida: {argumentos.url}", file=sys.stderr)
        return 2

    print("=" * 74)
    print("RASTREADOR DIDÁCTICO")
    print(f"Sitio:    {inicio}")
    print(f"Agente:   {argumentos.user_agent}")
    print(f"Límite:   {argumentos.max} páginas · pausa {argumentos.delay}s")
    print("=" * 74)

    try:
        resultado = rastrear(
            inicio=inicio,
            agente=argumentos.user_agent,
            maximo=argumentos.max,
            retardo=argumentos.delay,
            verbose=argumentos.verbose,
        )
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.", file=sys.stderr)
        return 130

    imprimir_informe(resultado)

    with open(argumentos.salida, "w", encoding="utf-8") as archivo:
        json.dump(resultado, archivo, ensure_ascii=False, indent=2)
    print(f"Resultado guardado en: {argumentos.salida}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
