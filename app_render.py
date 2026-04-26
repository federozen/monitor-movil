from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import re, unicodedata, math, random, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

app = FastAPI(title="NewsRoom Scraper API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

from fastapi.responses import FileResponse
import os

@app.get("/")
def read_root():
    return FileResponse("mobile_fixed.html")

FUENTES_NAC = [
    {"id": "ole",           "nombre": "Olé",            "url": "https://www.ole.com.ar/",                              "color": "#00a846", "es_ole": True},
    {"id": "espn",          "nombre": "ESPN AR",         "url": "https://www.espn.com.ar/",                            "color": "#cc0000"},
    {"id": "tyc",           "nombre": "TyC Sports",      "url": "https://www.tycsports.com/",                          "color": "#1565c0"},
    {"id": "infobae",       "nombre": "Infobae",         "url": "https://www.infobae.com/deportes/",                   "color": "#b00020"},
    {"id": "lanacion",      "nombre": "La Nación",       "url": "https://www.lanacion.com.ar/deportes/",               "color": "#1565c0"},
    {"id": "tn",            "nombre": "TN Deportes",     "url": "https://tn.com.ar/deportes/",                         "color": "#cc2200"},
    {"id": "clarin",        "nombre": "Clarín Dep.",     "url": "https://www.clarin.com/deportes/",                    "color": "#c00000"},
    {"id": "elgrafico",     "nombre": "El Gráfico",      "url": "https://www.elgrafico.com.ar/",                       "color": "#b07800"},
    {"id": "dobleamarilla", "nombre": "Doble Amarilla",  "url": "https://www.dobleamarilla.com.ar/",                   "color": "#a07800", "es_wp": True},
    {"id": "bolavip",       "nombre": "Bolavip",         "url": "https://bolavip.com/ar",                              "color": "#c04a00"},
    {"id": "lavoz",         "nombre": "La Voz",          "url": "https://www.lavoz.com.ar/deportes/",                  "color": "#8b0000"},
    {"id": "capital",       "nombre": "La Capital",      "url": "https://www.lacapital.com.ar/secciones/ovacion.html", "color": "#6a0d8a"},
    {"id": "ole_ult",       "nombre": "Olé Últimas",     "url": "https://www.ole.com.ar/ultimas-noticias",             "color": "#00a846"},
]
FUENTES_INT = [
    {"id": "as",        "nombre": "AS",              "url": "https://as.com/futbol/",                           "color": "#b00020"},
    {"id": "marca",     "nombre": "Marca",           "url": "https://www.marca.com/",                           "color": "#267326"},
    {"id": "mundodep",  "nombre": "Mundo Deportivo", "url": "https://www.mundodeportivo.com/",                  "color": "#1565c0"},
    {"id": "sport",     "nombre": "Sport",           "url": "https://www.sport.es/es/",                         "color": "#cc0020"},
    {"id": "globo",     "nombre": "GloboEsporte",    "url": "https://ge.globo.com/",                            "color": "#007a2f"},
    {"id": "bbc",       "nombre": "BBC Sport",       "url": "https://feeds.bbci.co.uk/sport/football/rss.xml",  "color": "#bb1919", "es_rss": True},
    {"id": "goal",      "nombre": "Goal",            "url": "https://www.goal.com/es",                          "color": "#00a878"},
    {"id": "lequipe",   "nombre": "L'Equipe",        "url": "https://www.lequipe.fr/Football/",                 "color": "#f5c400"},
    {"id": "latercera", "nombre": "La Tercera",      "url": "https://www.latercera.com/canal/el-deportivo/",    "color": "#005a9e"},
    {"id": "referi",    "nombre": "Referí Uruguay",  "url": "https://www.elobservador.com.uy/referi",           "color": "#c0392b"},
]
TODAS_FUENTES = FUENTES_NAC + FUENTES_INT
FUENTES_NAC_IDS = {f["id"] for f in FUENTES_NAC}
MAX_ITEMS = 25
SIMILITUD_UMBRAL = 0.22

STOPWORDS = {
    "de","la","el","en","y","a","los","del","se","las","por","un","para","con","una","su","al","lo",
    "como","mas","pero","sus","le","ya","o","fue","este","ha","si","porque","esta","son","entre",
    "cuando","muy","sin","sobre","tambien","me","hasta","hay","donde","quien","desde","todo","nos",
    "durante","e","esto","mi","antes","yo","otro","otras","otra","bien","asi","cada","ser","tiene",
    "habia","era","no","es","que","the","an","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","was","are","were","be","been","have","has","had","will","would","could","should",
    "may","might","can","da","do","em","com","um","uma","os","as","ao","na","nas","nos","seu","sua",
    "seus","suas","nao","apos","tras","vs","after","over","into","than","then","their","they","this","that",
}

def normalizar(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return {w for w in t.split() if len(w) > 3 and w not in STOPWORDS}

def jaccard(a, b):
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)

def calcular_tendencias(res):
    todas = [{"n": n, "f": f, "k": normalizar(n["titulo"])}
             for f in TODAS_FUENTES for n in res.get(f["id"], [])]
    clusters, asignado = [], [False] * len(todas)
    for i in range(len(todas)):
        if asignado[i]: continue
        cl = {"titulo": todas[i]["n"]["titulo"], "imagen": todas[i]["n"].get("imagen",""),
              "url": todas[i]["n"].get("url"), "fids": {todas[i]["f"]["id"]},
              "items": [{"n": todas[i]["n"], "f": todas[i]["f"]}], "k": todas[i]["k"]}
        asignado[i] = True
        for j in range(i+1, len(todas)):
            if asignado[j]: continue
            if jaccard(cl["k"], todas[j]["k"]) >= 0.20:
                cl["fids"].add(todas[j]["f"]["id"])
                cl["items"].append({"n": todas[j]["n"], "f": todas[j]["f"]})
                asignado[j] = True
        if len(cl["fids"]) >= 2:
            clusters.append(cl)
    clusters.sort(key=lambda c: (-len(c["fids"]), -len(c["items"])))
    return [{
        "titulo": c["titulo"], "imagen": c["imagen"], "url": c["url"],
        "cant_medios": len(c["fids"]), "tiene_ole": "ole" in c["fids"] or "ole_ult" in c["fids"],
        "nac": sum(1 for x in c["items"] if x["f"]["id"] in FUENTES_NAC_IDS),
        "intl": sum(1 for x in c["items"] if x["f"]["id"] not in FUENTES_NAC_IDS),
        "noticias": [{"titulo": x["n"]["titulo"], "url": x["n"].get("url"),
                      "fuente_nombre": x["f"]["nombre"], "fuente_color": x["f"]["color"]}
                     for x in c["items"]],
    } for c in clusters]

def analizar_ole(res):
    ks = {f["id"]: [{"n": n, "k": normalizar(n["titulo"])} for n in res.get(f["id"], [])]
          for f in TODAS_FUENTES}
    ole = ks.get("ole", []) + ks.get("ole_ult", [])
    exclusivos = [x["n"] for x in ole if not any(
        jaccard(x["k"], ci["k"]) >= SIMILITUD_UMBRAL
        for fid, items in ks.items() if fid not in ("ole","ole_ult") for ci in items)]
    faltantes, ya = [], []
    for f in TODAS_FUENTES:
        if f.get("es_ole") or f["id"] == "ole_ult": continue
        for x in ks.get(f["id"], []):
            if any(jaccard(x["k"], oi["k"]) >= SIMILITUD_UMBRAL for oi in ole): continue
            if any(jaccard(x["k"], k) >= SIMILITUD_UMBRAL for k in ya): continue
            ya.append(x["k"])
            faltantes.append({"titulo": x["n"]["titulo"], "url": x["n"].get("url"),
                               "imagen": x["n"].get("imagen",""),
                               "fuente_nombre": f["nombre"], "fuente_color": f["color"]})
    compartidos = []
    for x in ole:
        comp = []
        for fid, items in ks.items():
            if fid in ("ole","ole_ult"): continue
            for ci in items:
                if jaccard(x["k"], ci["k"]) >= SIMILITUD_UMBRAL:
                    fobj = next((f for f in TODAS_FUENTES if f["id"] == fid), None)
                    comp.append({"titulo": ci["n"]["titulo"], "url": ci["n"].get("url"),
                                 "fuente_nombre": fobj["nombre"] if fobj else fid,
                                 "fuente_color": fobj["color"] if fobj else "#666"})
                    break
        if comp:
            compartidos.append({"titulo_ole": x["n"]["titulo"], "url_ole": x["n"].get("url"), "competencia": comp[:4]})
    return {"exclusivos_ole": exclusivos[:40], "faltantes_en_ole": faltantes[:40], "cubiertos_por_ambos": compartidos[:30]}

def nube_palabras(res, fids, color):
    EXTRA = {"partido","partidos","juego","dice","dijo","confirmo","anuncio","hablo","tiene",
              "hoy","ayer","semana","nuevo","nueva","primer","primera","sera","puede","equipo"}
    freq = {}
    for fid in fids:
        for n in res.get(fid, []):
            for w in normalizar(n["titulo"]) - EXTRA:
                if len(w) > 3: freq[w] = freq.get(w, 0) + 1
    words = sorted(freq.items(), key=lambda x: -x[1])[:60]
    if not words: return []
    max_c, min_c = words[0][1], words[-1][1]
    rng = max_c - min_c or 1
    h = color.lstrip("#")
    cr, cg, cb = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    placed, out = [] , []
    random.seed(42)
    for word, count in words:
        t = (count - min_c) / rng
        fs = 11 + t * 26
        r = int(cr + (220-cr)*(1-t)); g = int(cg + (225-cg)*(1-t)); b = int(cb + (230-cb)*(1-t))
        hw = len(word) * fs * 0.30 / 4.8; hh = fs * 0.65 / 2.6
        for step in range(400):
            ang = step * 0.28; rad = step * 0.15
            cx = 50 + rad * math.cos(ang); cy = 50 + rad * math.sin(ang) * 0.55
            if cx-hw<1 or cx+hw>99 or cy-hh<2 or cy+hh>98: continue
            if not any(abs(cx-px)<hw+phw+1.2 and abs(cy-py)<hh+phh+1.2 for px,py,phw,phh in placed):
                placed.append((cx,cy,hw,hh))
                out.append({"word":word,"count":count,"x":round(cx,1),"y":round(cy,1),
                            "size":round(fs,1),"color":f"rgb({r},{g},{b})",
                            "weight":"700" if t>0.45 else "400","opacity":round(0.5+t*0.5,2)})
                break
    return out

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Referer": "https://www.google.com/",
}
_IMG_CACHE = {}
_GENERIC_PATS = [
    "logo","brand","favicon","default","placeholder",
    "og-default","og_default","share-default","ole-logo","ole_logo","icon",
    "espncdn.com/i/espn","espncdn.com/redesign","sprite","1x1","pixel","tracking",
]
_AUTOR_PATS = [
    "author","autor","firma","byline","avatar","perfil","profile",
    "journalist","periodista","columnist","writer","reporter","signature","bio","headshot",
]

def _generic(url): return not url or any(p in url.lower() for p in _GENERIC_PATS)

def _es_img_autor(tag):
    for parent in tag.parents:
        cls = " ".join(parent.get("class",[])).lower()
        pid = (parent.get("id") or "").lower()
        if any(p in cls or p in pid for p in _AUTOR_PATS):
            return True
        if parent.name in ("article","section","main"):
            break
    return False

def fetch_og(url):
    if not url or not url.startswith("http"): return ""
    if url in _IMG_CACHE: return _IMG_CACHE[url]
    try:
        soup = BeautifulSoup(requests.get(url, headers=HEADERS, timeout=8).text, "html.parser")
        for m in [soup.find("meta", property="og:image"), soup.find("meta", property="og:image:url"),
                  soup.find("meta", attrs={"name":"twitter:image"}), soup.find("meta", attrs={"name":"twitter:image:src"})]:
            if not m: continue
            c = m.get("content","") or m.get("value","") or ""
            if c and not _generic(c): _IMG_CACHE[url]=c; return c
    except Exception: pass
    _IMG_CACHE[url]=""; return ""

def fetch_og_batch(noticias):
    urls = [n["url"] for n in noticias if n.get("url") and n["url"] not in _IMG_CACHE]
    if not urls: return
    with ThreadPoolExecutor(max_workers=12) as ex:
        [f.result() for f in as_completed([ex.submit(fetch_og, u) for u in urls]) if not f.exception()]

def _rss_img(raw):
    for pat in [r'<media:content[^>]+url=["\']([^"\']+)["\']', r'<media:thumbnail[^>]+url=["\']([^"\']+)["\']']:
        m = re.search(pat, raw)
        if m and m.group(1).startswith("http") and not _generic(m.group(1)): return m.group(1)
    for tag in ["content:encoded","description"]:
        m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', raw, re.DOTALL)
        if m:
            ct = m.group(1)
            cd = re.search(r'<!\[CDATA\[(.*?)\]\]>', ct, re.DOTALL)
            if cd: ct = cd.group(1)
            im = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', ct)
            if im and im.group(1).startswith("http") and not _generic(im.group(1)): return im.group(1)
    return ""

def extraer_rss(xml):
    noticias, seen = [], set()
    try:
        soup = BeautifulSoup(xml, "xml")
        raws = re.findall(r'<item>(.*?)</item>', xml, re.DOTALL)
        for i, item in enumerate(soup.find_all(["item","entry"])[:MAX_ITEMS]):
            tt = item.find("title")
            if not tt: continue
            t = tt.get_text(strip=True)
            if len(t)<15 or t in seen: continue
            seen.add(t)
            lk = item.find("link")
            url = lk.get_text(strip=True) if lk else None
            img = _rss_img(raws[i]) if i < len(raws) else ""
            noticias.append({"titulo":t,"url":url,"imagen":img})
    except Exception: pass
    return noticias

# --- LOGICA DEDICADA DE TYC DE TU APP.PY ---
def extraer_tyc(html: str) -> list:
    noticias, vistos = [], set()
    soup = BeautifulSoup(html, "html.parser")
    urls_ordenadas = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            def _walk(obj):
                if isinstance(obj, dict):
                    if obj.get("@type") == "ItemList":
                        for item in obj.get("itemListElement", []):
                            u = item.get("url") or item.get("item", {}).get("url")
                            if u and u.startswith("http") and u not in urls_ordenadas:
                                urls_ordenadas.append(u)
                    for v in obj.values():
                        _walk(v)
                elif isinstance(obj, list):
                    for v in obj:
                        _walk(v)
            _walk(data)
        except Exception:
            pass
    url_to_titulo = {}
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not href.startswith("http"):
            href = "https://www.tycsports.com" + href if href.startswith("/") else None
        if not href: continue
        titulo = None
        for sel in ["h1","h2","h3","h4","[class*='title']","[class*='Title']","[class*='headline']","[class*='titular']","[class*='tit']"]:
            t_el = a.select_one(sel)
            if t_el:
                titulo = t_el.get_text(strip=True)
                break
        if not titulo: titulo = a.get_text(strip=True)
        titulo = re.sub(r"\s+", " ", titulo).strip()
        if href and titulo and 20 <= len(titulo) <= 300:
            url_to_titulo[href] = titulo

    for url in urls_ordenadas:
        if len(noticias) >= MAX_ITEMS: break
        titulo = url_to_titulo.get(url) or url_to_titulo.get(url.rstrip("/"))
        if not titulo:
            slug = url.rstrip("/").split("/")[-1]
            slug = re.sub(r"-id\d+$", "", slug)
            titulo = slug.replace("-", " ").title()
            if len(titulo) < 15: continue
        if titulo in vistos: continue
        vistos.add(titulo)
        noticias.append({"titulo": titulo, "url": url, "imagen": ""})
    return noticias[:MAX_ITEMS]

# _AUTOR_PATS definido arriba
CARD_SELS = ["article","[class*=card]","[class*=story]","[class*=nota]","[class*=item]","[class*=news]"]
TITLE_SELS = ["h1","h2","h3","h4","[class*=title]","[class*=headline]","[class*=titular]"]
IMG_ATTRS = ["src","data-src","data-lazy-src","data-original","data-url","data-image"]

def _img_score(tag, src):
    score = 0
    try:
        w = int(tag.get("width") or tag.get("data-width") or 0)
        h = int(tag.get("height") or tag.get("data-height") or 0)
        score += w + h
    except (ValueError, TypeError): pass
    cls = " ".join(tag.get("class",[])).lower()
    for g in ["featured","hero","portada","principal","cover","thumb","thumbnail",
              "featured-image","post-image","article-image","nota-img","card-img",
              "wp-post-image","attachment-","size-large","size-full","wp-block-image","entry-thumb"]:
        if g in cls: score += 500
    for b in _AUTOR_PATS:
        if b in cls: score -= 9999
    if _es_img_autor(tag): score -= 9999
    if tag.get("srcset") or tag.get("data-srcset"): score += 200
    m = re.search(r'[-/](\d{3,4})x(\d{3,4})[-/.]', src)
    if m: score += int(m.group(1)) + int(m.group(2))
    alt = (tag.get("alt") or "").lower()
    if alt and len(alt) > 5 and "logo" not in alt: score += 50
    return score

def get_imagen(el):
    IMG_ATTRS_LOCAL = ["src","data-src","data-lazy-src","data-original","data-url","data-image"]
    cands = []
    for tag in el.find_all("img"):
        if _es_img_autor(tag): continue
        best = ""
        ss = tag.get("srcset","") or tag.get("data-srcset","")
        if ss:
            sized = []
            for s in ss.split(","):
                p = s.strip().split(" ")
                try: w = int(p[1].rstrip("w")) if len(p)>1 and p[1].endswith("w") else 0
                except: w = 0
                sized.append((w, p[0]))
            for _, u in sorted(sized, reverse=True):
                if u.startswith("http") and not _generic(u) and "1x1" not in u and "pixel" not in u.lower():
                    best = u; break
        if not best:
            for a in IMG_ATTRS_LOCAL:
                s = tag.get(a,"")
                if s and s.startswith("http") and not s.endswith(".gif") and not _generic(s) and "1x1" not in s and "pixel" not in s.lower():
                    best = s; break
        if best: cands.append((_img_score(tag, best), best))
    for tag in el.find_all(style=True):
        m = re.search(r'background(?:-image)?:\s*url\(["\']?(https?://[^"\')\s]+)["\']?\)', tag["style"])
        if m and not _generic(m.group(1)):
            cls = " ".join(tag.get("class",[])).lower()
            bg_score = -9999 if any(b in cls for b in _AUTOR_PATS) else 100
            cands.append((bg_score, m.group(1)))
    if not cands: return ""
    cands.sort(reverse=True)
    sc, src = cands[0]
    return src if sc > -100 else ""

def extraer_lanacion(html: str) -> list:
    noticias, seen = [], set()
    soup = BeautifulSoup(html, "html.parser")
    base = "https://www.lanacion.com.ar"

    CARD_SELS_LN = [
        "article",
        "section[class*='story']",
        "div[class*='mod-type-']",
        "div[class*='story']",
        "[class*='article']",
    ]
    TITLE_SELS_LN = ["h1","h2","h3","[class*='title']","[class*='headline']","[class*='nota-title']"]

    def resolve_ln(href):
        if not href or href.startswith("javascript") or href == "#": return None
        if href.startswith("//"): return "https:" + href
        if href.startswith("/"): return base + href
        if href.startswith("http"): return href
        return None

    for card_sel in CARD_SELS_LN:
        for card in soup.select(card_sel)[:MAX_ITEMS * 2]:
            if len(noticias) >= MAX_ITEMS: break
            tel = None
            for ts in TITLE_SELS_LN:
                tel = card.select_one(ts)
                if tel: break
            if not tel: continue
            t = tel.get_text(strip=True)
            if len(t) < 20 or len(t) > 300 or t in seen: continue
            seen.add(t)

            # Buscar URL: tag <a> que envuelve el título o el más cercano
            url = None
            for candidate in [tel, tel.find_parent("a"), card.find("a", href=True)]:
                if not candidate: continue
                href = candidate.get("href", "") if candidate.name == "a" else ""
                if not href and candidate.name != "a":
                    a = candidate.find("a", href=True)
                    href = a.get("href", "") if a else ""
                resolved = resolve_ln(href)
                if resolved and "/deportes/" in resolved:
                    url = resolved; break
            if not url:
                for a in card.find_all("a", href=True):
                    resolved = resolve_ln(a.get("href", ""))
                    if resolved and "/deportes/" in resolved:
                        url = resolved; break

            img = get_imagen(card)
            noticias.append({"titulo": t, "url": url, "imagen": img})
        if len(noticias) >= MAX_ITEMS: break

    return noticias[:MAX_ITEMS]





def extraer_espn(html: str) -> list:
    """
    Scraper dedicado para ESPN AR (espn.com.ar).
    ESPN es una SPA React: el HTML estático tiene JSON-LD con las URLs reales.
    Las URLs de notas siguen el patrón /_/id/NNNNNN/ — ese es el filtro clave.
    NO escala padres para evitar capturar el 'featured story' global de la página.
    """
    noticias, seen = [], set()
    soup = BeautifulSoup(html, "html.parser")
    BASE = "https://www.espn.com.ar"
    ESPN_SKIP = ["/autor/", "/author/", "/tag/", "/tags/", "/equipo/", "/liga/",
                 "/atletismo/", "javascript:", "mailto:", "#", "/video/"]

    def resolve_espn(href):
        if not href: return None
        if any(s in href for s in ESPN_SKIP): return None
        if href.startswith("//"): return "https:" + href
        if href.startswith("/"): return BASE + href
        if href.startswith("http"): return href
        return None

    def es_url_nota(url):
        """URL de nota ESPN tiene /_/id/NNNNNN/ o /nota/ o /historia/"""
        if not url: return False
        return "/_/id/" in url or "/nota/" in url or "/historia/" in url or "/story/" in url

    # — Estrategia 1: JSON-LD con ItemList (como TyC, muy confiable) —
    urls_json = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            def _walk(obj):
                if isinstance(obj, dict):
                    if obj.get("@type") in ("NewsArticle", "Article", "WebPage"):
                        u = obj.get("url") or obj.get("mainEntityOfPage", {}).get("@id","")
                        if u and es_url_nota(u) and u not in urls_json:
                            urls_json.append(u)
                    if obj.get("@type") == "ItemList":
                        for item in obj.get("itemListElement", []):
                            u = item.get("url") or item.get("item", {}).get("url","")
                            if u and es_url_nota(u) and u not in urls_json:
                                urls_json.append(u)
                    for v in obj.values():
                        _walk(v)
                elif isinstance(obj, list):
                    for v in obj: _walk(v)
            _walk(data)
        except Exception:
            pass

    # — Estrategia 2: buscar <a href="/_/id/..."> directos en el HTML —
    urls_html = []
    for a in soup.find_all("a", href=True):
        href = a.get("href","")
        url = resolve_espn(href)
        if url and es_url_nota(url) and url not in urls_html:
            urls_html.append(url)

    # Combinar: JSON-LD primero (más confiable), luego HTML
    todas_urls = list(dict.fromkeys(urls_json + urls_html))

    # Construir mapa url→titulo buscando el título asociado a cada <a>
    url_to_titulo = {}
    TITLE_SELS_ESPN = ["h1","h2","h3","h4",
                       "[class*=title]","[class*=Title]",
                       "[class*=headline]","[class*=Headline]",
                       "[class*=contentItem__title]"]
    for a in soup.find_all("a", href=True):
        href = a.get("href","")
        url = resolve_espn(href)
        if not url or not es_url_nota(url): continue
        titulo = None
        for sel in TITLE_SELS_ESPN:
            t_el = a.select_one(sel)
            if t_el:
                titulo = t_el.get_text(strip=True); break
        if not titulo:
            titulo = a.get_text(strip=True)
        titulo = " ".join(titulo.split())
        if 20 <= len(titulo) <= 300:
            if url not in url_to_titulo:
                url_to_titulo[url] = titulo

    # Construir noticias en el orden de las URLs encontradas
    for url in todas_urls:
        if len(noticias) >= MAX_ITEMS: break
        titulo = url_to_titulo.get(url)
        if not titulo:
            # Intentar construir título desde el slug de la URL
            slug = url.rstrip("/").split("/")[-1]
            slug = re.sub(r"^\d+-", "", slug)
            titulo = slug.replace("-", " ").title()
            if len(titulo) < 15: continue
        if titulo in seen: continue
        seen.add(titulo)
        noticias.append({"titulo": titulo, "url": url, "imagen": ""})

    return noticias[:MAX_ITEMS]


def extraer_generico(html, fuente):
    if fuente.get("es_rss"): return extraer_rss(html)
    if fuente.get("id") == "tyc": return extraer_tyc(html) # Lógica especial TyC incorporada
    if fuente.get("id") == "lanacion": return extraer_lanacion(html)
    if fuente.get("id") == "espn": return extraer_espn(html)

    if fuente.get("es_wp"):
        feed=fuente["url"].rstrip("/")+"/feed/"
        try:
            r=requests.get(feed,headers=HEADERS,timeout=12)
            if r.status_code==200 and "<rss" in r.text[:500]: return extraer_rss(r.text)
        except: pass

    soup=BeautifulSoup(html,"html.parser")
    bm=re.match(r"https?://[^/]+",fuente["url"]); base=bm.group(0) if bm else ""
    noticias, seen = [], set()

    def resolve(href):
        if not href or href.startswith("javascript") or href=="#": return None
        if href.startswith("//"): return "https:"+href
        if href.startswith("/"): return base.rstrip("/") + href
        if href.startswith("http"): return href
        return None

    # MAGIA PARA ENCONTRAR LINKS EN OLÉ Y CLARÍN (Escalando suavemente el HTML)
    def get_best_link(card_el, titulo_el):
        candidatos = []

        # Agarra links del título y su padre
        if titulo_el:
            if titulo_el.name == "a": candidatos.append(titulo_el)
            p = titulo_el.find_parent("a")
            if p: candidatos.append(p)
            candidatos.extend(titulo_el.find_all("a"))
            if titulo_el.parent:
                candidatos.extend(titulo_el.parent.find_all("a"))

        # Agarra links de la tarjeta y los padres cercanos (Esto captura el "a" escondido de Olé)
        if card_el:
            if card_el.name == "a": candidatos.append(card_el)
            cp = card_el.find_parent("a")
            if cp: candidatos.append(cp)
            candidatos.extend(card_el.find_all("a"))
            if card_el.parent:
                candidatos.extend(card_el.parent.find_all("a"))
                if card_el.parent.parent:
                    candidatos.extend(card_el.parent.parent.find_all("a"))

        valid_urls = []
        for a in candidatos:
            href = a.get("href", "").strip()
            hl = href.lower()
            if not href or href.startswith("javascript") or href == "#": continue
            # Filtramos firmemente todo lo que no sea una nota real
            if any(x in hl for x in ["/autor/", "/author/", "tag=", "/tema/", "/columnistas/"]): continue

            resolved = resolve(href)
            if resolved and resolved != fuente["url"] and resolved != base + "/":
                valid_urls.append(resolved)

        if valid_urls:
            valid_urls = list(set(valid_urls))
            # Clarín/Olé siempre usan .html en sus notas. Le damos el puntaje máximo para elegir esa.
            valid_urls.sort(key=lambda u: len(u) + (1000 if u.endswith('.html') else 0), reverse=True)
            return valid_urls[0]
        return None

    for sel in CARD_SELS:
        for card in soup.select(sel)[:MAX_ITEMS*2]:
            if len(noticias)>=MAX_ITEMS: break
            tel=None
            for ts in TITLE_SELS:
                tel=card.select_one(ts)
                if tel: break
            if not tel: continue
            t=tel.get_text(strip=True)
            if len(t)<20 or len(t)>300 or t in seen: continue
            seen.add(t)

            url = get_best_link(card, tel)
            img = get_imagen(card)
            noticias.append({"titulo":t,"url":url,"imagen":img})

    if len(noticias)<8:
        for sel in ["h2","h3"]:
            for el in soup.select(sel)[:MAX_ITEMS*2]:
                if len(noticias)>=MAX_ITEMS: break
                t=el.get_text(strip=True)
                if len(t)<20 or len(t)>300 or t in seen: continue
                seen.add(t)

                url = get_best_link(el, el)
                noticias.append({"titulo":t,"url":url,"imagen":""})

    return noticias[:MAX_ITEMS]

def fetch_fuente(fuente):
    try:
        r=requests.get(fuente["url"],headers=HEADERS,timeout=18); r.raise_for_status()
        ct=r.headers.get("content-type","").lower()
        if "charset=" in ct: enc=ct.split("charset=")[-1].split(";")[0].strip()
        else:
            sniff=r.content[:4096].decode("ascii",errors="ignore").lower()
            enc="utf-8" if "charset=utf-8" in sniff or 'charset="utf-8"' in sniff else (r.apparent_encoding or "utf-8")
        r.encoding=enc
        return {"id":fuente["id"],"nombre":fuente["nombre"],"color":fuente["color"],"noticias":extraer_generico(r.text,fuente),"error":None}
    except Exception as e:
        return {"id":fuente["id"],"nombre":fuente["nombre"],"color":fuente["color"],"noticias":[],"error":str(e)[:200]}

class ScrapeRequest(BaseModel):
    fuentes: Optional[list[str]] = None
    grupo: str = "todas"
    max_per_site: int = 20
    fetch_og: bool = True

class ArticleRequest(BaseModel):
    url: str

class AIRequest(BaseModel):
    texts: list[str]
    mode: str = "resumen"
    custom: str = ""
    api_key: str


class BatchRequest(BaseModel):
    urls: list[str]

@app.post("/api/batch_scrape")
def batch_scrape(req: BatchRequest):
    """Descarga el texto completo de una lista de URLs en paralelo (la Canasta)."""
    _BODY_SELS_FETCH = [
        "article .article-body","article .nota-cuerpo","article .entry-content",
        "article .article-content","article .post-content","article .content-body",
        "[class*=ln-article]","[class*=body-nota]","[class*=row-body]",
        ".article__body",".nota__cuerpo",".article-text",".news-body",
        "[class*=article-body]","[class*=nota-cuerpo]","[class*=entry-content]",
        "[class*=article-content]","[class*=post-body]","[class*=story-body]",
        "[class*=content-body]","[class*=cuerpo-nota]","[class*=nota-body]",
        "[class*=news-body]","[class*=post-content]","[class*=text-container]",
        "[class*=detail-body]","[class*=detail-content]",
        "article","[role=main]","main",
    ]

    def _fetch_one(url: str) -> dict:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            ct = r.headers.get("content-type", "").lower()
            if "charset=" in ct:
                enc = ct.split("charset=")[-1].split(";")[0].strip()
            else:
                sniff = r.content[:4096].decode("ascii", errors="ignore").lower()
                enc = "utf-8" if "charset=utf-8" in sniff or 'charset="utf-8"' in sniff else (r.apparent_encoding or "utf-8")
            r.encoding = enc
            soup = BeautifulSoup(r.text, "html.parser")
            for t in soup(["script","style","nav","header","footer","aside","form","figure","noscript","iframe"]):
                t.decompose()
            titulo = ""
            og_t = soup.find("meta", property="og:title")
            if og_t and og_t.get("content","").strip(): titulo = og_t["content"].strip()
            if not titulo:
                h1 = soup.find("h1")
                if h1: titulo = h1.get_text(strip=True)
            if not titulo:
                tt = soup.find("title")
                if tt: titulo = tt.get_text(strip=True)
            if not titulo: titulo = url
            texto = ""
            for sel in _BODY_SELS_FETCH:
                el = soup.select_one(sel)
                if el:
                    ps = [p.get_text(" ", strip=True) for p in el.find_all("p") if len(p.get_text(strip=True)) > 40]
                    texto = "\n\n".join(ps)
                    if len(texto) > 200: break
            if not texto:
                ps = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 20]
                texto = "\n\n".join(ps[:12])
            if not texto:
                for meta in [soup.find("meta", property="og:description"),
                             soup.find("meta", attrs={"name":"description"})]:
                    if meta and meta.get("content"):
                        texto = "[Bajada] " + meta["content"]; break
            return {"url": url, "titulo": titulo, "contenido": texto, "ok": bool(texto)}
        except Exception as e:
            return {"url": url, "titulo": url, "contenido": "", "ok": False, "error": str(e)[:120]}
    resultados = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_one, u): u for u in req.urls if u and u.startswith("http")}
        for fut in as_completed(futures):
            resultados.append(fut.result())
    return {"articulos": resultados}

@app.get("/api/fuentes")
def get_fuentes():
    return {
        "nacionales": [{"id":f["id"],"nombre":f["nombre"],"color":f["color"]} for f in FUENTES_NAC],
        "internacionales": [{"id":f["id"],"nombre":f["nombre"],"color":f["color"]} for f in FUENTES_INT],
    }

@app.post("/api/scrape")
def scrape(req: ScrapeRequest):
    global MAX_ITEMS; MAX_ITEMS=req.max_per_site
    if req.fuentes: fuentes=[f for f in TODAS_FUENTES if f["id"] in req.fuentes]
    elif req.grupo=="nacionales": fuentes=FUENTES_NAC
    elif req.grupo=="internacionales": fuentes=FUENTES_INT
    else: fuentes=TODAS_FUENTES
    if not fuentes: raise HTTPException(400,"Sin fuentes")

    res_raw={}; errores=[]
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures={ex.submit(fetch_fuente,f):f for f in fuentes}
        for fut in as_completed(futures):
            r=fut.result(); res_raw[r["id"]]=r["noticias"]
            if r["error"]: errores.append(f'{r["id"]}: {r["error"]}')

    if req.fetch_og:
        sin_img=[n for fid,ns in res_raw.items() for n in ns if not n.get("imagen") and n.get("url")]
        fetch_og_batch(sin_img)
        for fid,ns in res_raw.items():
            for n in ns:
                if not n.get("imagen") and n.get("url"): n["imagen"]=_IMG_CACHE.get(n["url"],"")

    tendencias=calcular_tendencias(res_raw)
    ole_analisis={}
    if any(f["id"] in ("ole","ole_ult") for f in fuentes):
        try: ole_analisis=analizar_ole(res_raw)
        except: ole_analisis={"exclusivos_ole":[],"faltantes_en_ole":[],"cubiertos_por_ambos":[]}

    nac_ids=[f["id"] for f in FUENTES_NAC if f["id"] in res_raw]
    int_ids=[f["id"] for f in FUENTES_INT if f["id"] in res_raw]

    fuentes_result=[{"id":f["id"],"nombre":f["nombre"],"color":f["color"],
                     "items":res_raw.get(f["id"],[]),"status":"ok" if res_raw.get(f["id"]) else "empty"}
                    for f in fuentes]
    total=sum(len(r["items"]) for r in fuentes_result)
    nf=len(fuentes)

    return {
        "fuentes": fuentes_result,
        "total": total,
        "errores": errores,
        "tendencias": tendencias,
        "ole_analisis": ole_analisis,
        "nube_nac": nube_palabras(res_raw, nac_ids, "#00a846"),
        "nube_int": nube_palabras(res_raw, int_ids, "#1a7fc1"),
        "stats": {
            "tendencias": len(tendencias),
            "sin_ole": len([t for t in tendencias if not t["tiene_ole"]]),
            "con_ole": len([t for t in tendencias if t["tiene_ole"]]),
            "hot": len([t for t in tendencias if t["cant_medios"]/max(nf,1)>=0.20]),
        }
    }

@app.post("/api/article")
def get_article(req: ArticleRequest):
    try:
        r=requests.get(req.url,headers=HEADERS,timeout=15)
        ct=r.headers.get("content-type","").lower()
        if "charset=" in ct: enc=ct.split("charset=")[-1].split(";")[0].strip()
        else:
            sniff=r.content[:4096].decode("ascii",errors="ignore").lower()
            enc="utf-8" if "charset=utf-8" in sniff or 'charset="utf-8"' in sniff else (r.apparent_encoding or "utf-8")
        r.encoding=enc
        soup=BeautifulSoup(r.text,"html.parser")
        for t in soup(["script","style","nav","header","footer","aside","form","figure","noscript","iframe"]):
            t.decompose()
        og_t=soup.find("meta",property="og:title")
        h1=soup.find("h1")
        title=(og_t.get("content","").strip() if og_t else "") or (h1.get_text(strip=True) if h1 else "")
        if not title:
            tt=soup.find("title"); title=tt.get_text(strip=True) if tt else ""
        _BODY_SELS_ART=[
            "article .article-body","article .nota-cuerpo","article .entry-content",
            "article .article-content","article .post-content","article .content-body",
            "[class*=ln-article]","[class*=body-nota]","[class*=row-body]",
            ".article__body",".nota__cuerpo",".article-text",".news-body",
            "[class*=article-body]","[class*=nota-cuerpo]","[class*=entry-content]",
            "[class*=article-content]","[class*=post-body]","[class*=story-body]",
            "[class*=content-body]","[class*=cuerpo-nota]","[class*=nota-body]",
            "[class*=news-body]","[class*=post-content]","[class*=text-container]",
            "[class*=detail-body]","[class*=detail-content]",
            "article","[role=main]","main",
        ]
        contenido=""
        for sel in _BODY_SELS_ART:
            el=soup.select_one(sel)
            if el:
                ps=[p.get_text(" ",strip=True) for p in el.find_all("p") if len(p.get_text(strip=True))>40]
                contenido="\n\n".join(ps)
                if len(contenido)>200: break
        if not contenido:
            ps=[p.get_text(" ",strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True))>20]
            contenido="\n\n".join(ps[:12])
        if not contenido:
            for meta in [soup.find("meta",property="og:description"),soup.find("meta",attrs={"name":"description"})]:
                if meta and meta.get("content"):
                    contenido="[Bajada] "+meta["content"]; break
        return {"titulo":title,"contenido":contenido,"imagen":fetch_og(req.url),"url":req.url}
    except Exception as e:
        raise HTTPException(500,str(e))

@app.post("/api/ai")
def ai_generate(req: AIRequest):
    try:
        import anthropic as _ant

        # — Guardrail: calcular cuánto contexto real llegó —
        contexto_formateado = "\n\n---\n\n".join(req.texts)
        chars_totales = len(contexto_formateado)
        # Detectar si el contexto es pobre (solo titulares o muy corto)
        solo_titulares = all(
            len(t.strip()) < 300 or "[Solo titular disponible" in t
            for t in req.texts
        )

        SYSTEM_RAG = (
            "Eres un periodista deportivo argentino experto trabajando como redactor de agencia. "
            "REGLA DE ORO: Cada dato, nombre, fecha, declaración o hecho que escribas DEBE estar "
            "textualmente presente en el CONTEXTO que se te provee. "
            "Si no lo encontrás en el CONTEXTO, no lo escribas bajo ninguna circunstancia. "
            "No uses tu conocimiento previo sobre fútbol, deportistas, clubes ni eventos. "
            "Si el CONTEXTO es insuficiente para un dato, escribí literalmente: "
            "'[dato no disponible en el contexto]' en ese lugar. "
            "Cuando termines, revisá mentalmente cada oración y verificá que cada hecho "
            "tenga respaldo explícito en el CONTEXTO antes de entregarlo."
        )

        PROMPTS = {
            "resumen": (
                "Hacé un resumen periodístico de las noticias del CONTEXTO. "
                "Para cada tema, indicá entre paréntesis de qué fuente/URL tomaste la información. "
                "Si el contexto contiene poco texto, hacé el resumen con lo que hay y aclaralo. "
                "Prohibido agregar datos de tu conocimiento previo."
            ),
            "nota": (
                "Redactá una nota completa para una agencia de noticias deportiva argentina "
                "siguiendo estos DOS PASOS. Solo incluí el resultado del PASO 2.\n\n"
                "PASO 1 — INVENTARIO DE HECHOS (mental, no lo escribas):\n"
                "Extraé ÚNICAMENTE lo que aparece textualmente en el CONTEXTO:\n"
                "¿Qué ocurrió exactamente? ¿Quiénes son nombrados y con qué rol?\n"
                "¿Qué cifras, fechas, lugares aparecen? ¿Hay citas textuales?\n"
                "¿Qué antecedentes o contexto mencionan las fuentes?\n\n"
                "PASO 2 — REDACCIÓN DE LA NOTA (esto es lo que entregás):\n"
                "Estructura obligatoria para agencia de noticias:\n"
                "TITULAR — conciso, informativo, máximo 12 palabras, sin clickbait\n"
                "COPETE — 2-3 oraciones con el núcleo (quién, qué, cuándo, dónde)\n"
                "CUERPO — mínimo 6 párrafos con subtítulos temáticos en negrita:\n"
                "  · Bloque 1: el hecho principal con todos sus detalles disponibles\n"
                "  · Bloque 2: declaraciones o reacciones citadas del CONTEXTO\n"
                "  · Bloque 3: antecedentes o contexto que figuren en las fuentes\n"
                "  · Bloque 4: consecuencias o próximos pasos mencionados\n"
                "  · Bloques adicionales: cualquier otro ángulo con respaldo\n\n"
                "REGLAS CRÍTICAS — NUNCA las violes:\n"
                "• Usá TODOS los datos del CONTEXTO: densidad informativa máxima.\n"
                "• Reordená la información: no sigas el orden de las fuentes, jerarquizá.\n"
                "• Reescribí cada oración con tus propias palabras; prohibido copiar literalmente.\n"
                "• Comillas solo para frases que aparezcan textualmente en el CONTEXTO.\n"
                "• Si un dato no está en el CONTEXTO: escribí [DATO NO DISPONIBLE], no inventes.\n"
                "• Prohibido agregar estadísticas, historial o datos de tu conocimiento previo.\n"
                "• Estilo rioplatense, voseo, tono neutro de agencia (Télam/NA/DyN)."
            ),
            "analisis": (
                "Analizá el contexto editorial de estas noticias: temas dominantes, ángulos editoriales "
                "y qué medios cubren qué. Solo con lo que está en el CONTEXTO. "
                "Citá de qué fuente tomás cada observación."
            ),
            "nota_rapida": (
                "Redactá una nota periodística larga y completa para publicar en una agencia "
                "de noticias deportiva argentina, siguiendo estos DOS PASOS.\n\n"
                "PASO 1 — INVENTARIO DE HECHOS (mental, no lo escribas):\n"
                "Extraé ÚNICAMENTE lo que aparece textualmente en el CONTEXTO:\n"
                "¿Qué ocurrió? ¿Quiénes están involucrados y con qué rol?\n"
                "¿Qué cifras, fechas, lugares, citas textuales hay?\n"
                "¿Qué antecedentes, consecuencias o reacciones mencionan las fuentes?\n\n"
                "PASO 2 — REDACCIÓN (esto es lo que entregás):\n"
                "Estructura obligatoria para una nota de agencia completa:\n"
                "TITULAR — conciso, informativo, máximo 12 palabras, sin clickbait\n"
                "SUBTÍTULO — una oración que amplía el titular\n"
                "COPETE — 2-3 oraciones con el núcleo de la noticia (quién, qué, cuándo, dónde)\n"
                "CUERPO — mínimo 7 párrafos con subtítulos temáticos en negrita:\n"
                "  · Bloque 1: el hecho principal con todos sus detalles\n"
                "  · Bloque 2: citas y declaraciones textuales del CONTEXTO\n"
                "  · Bloque 3: antecedentes o contexto presente en las fuentes\n"
                "  · Bloque 4: consecuencias, impacto o derivaciones mencionadas\n"
                "  · Bloque 5: otros ángulos o detalles relevantes del CONTEXTO\n"
                "  · Bloques adicionales: cualquier dato con respaldo en el CONTEXTO\n\n"
                "REGLAS CRÍTICAS — NUNCA las violes:\n"
                "• Usá TODOS los datos disponibles del CONTEXTO: densidad informativa máxima.\n"
                "• Reordená la información: no sigas el orden de las fuentes, jerarquizá por importancia.\n"
                "• Prohibido copiar oraciones literales: reescribí siempre con tus palabras.\n"
                "• Las comillas solo para frases que aparezcan textualmente en el CONTEXTO.\n"
                "• Si un dato no está en el CONTEXTO: escribí [DATO NO DISPONIBLE], no inventes.\n"
                "• Prohibido agregar estadísticas, historial o datos de tu conocimiento previo.\n"
                "• Estilo rioplatense, voseo, tono neutro de agencia (Télam/NA/DyN).\n"
                "• La nota debe poder publicarse tal cual, sin edición adicional."
            ),
            "custom": req.custom or "Procesá estas notas periodísticas usando SOLO la información del CONTEXTO.",
        }

        # — Advertencia si el contexto es pobre —
        advertencia = ""
        if solo_titulares:
            advertencia = (
                "\n\n⚠️ ADVERTENCIA: El contexto disponible contiene principalmente titulares "
                "(los artículos completos no pudieron extraerse, posiblemente por paywall o JavaScript). "
                "Trabajá SOLO con lo que hay. Si no alcanza para desarrollar la nota, "
                "escribí lo que se puede y aclaralo explícitamente al final."
            )

        user_msg = (
            f"{PROMPTS.get(req.mode, 'Procesá estas notas.')}{advertencia}\n\n"
            f"══════════════════════════════════════════════════════════\n"
            f"CONTEXTO COMPLETO ({chars_totales:,} caracteres — única fuente válida)\n"
            f"══════════════════════════════════════════════════════════\n\n"
            f"{contexto_formateado}\n\n"
            f"══════════════════════════════════════════════════════════\n"
            f"FIN DEL CONTEXTO. No uses información fuera de este bloque.\n"
            f"══════════════════════════════════════════════════════════"
        )

        # — Calcular max_tokens dinámicamente según tamaño del contexto —
        # Para modo nota, se necesitan más tokens (nota larga de agencia)
        es_modo_nota = req.mode in ("nota", "nota_rapida")
        if chars_totales > 8000:
            max_tok = 4500 if es_modo_nota else 2800
        elif chars_totales > 3000:
            max_tok = 3500 if es_modo_nota else 2200
        else:
            max_tok = 2800 if es_modo_nota else 1600

        client = _ant.Anthropic(api_key=req.api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tok,
            system=SYSTEM_RAG,
            messages=[{"role": "user", "content": user_msg}]
        )
        return {
            "resultado": msg.content[0].text,
            "debug": {
                "chars_contexto": chars_totales,
                "articulos": len(req.texts),
                "solo_titulares": solo_titulares,
                "max_tokens_usado": max_tok,
            }
        }
    except Exception as e:
        raise HTTPException(500, str(e))

app.mount("/", StaticFiles(directory="/content/frontend", html=True), name="frontend")
print("✅ Backend listo")

Commented out IPython magic to ensure Python compatibility.
%%writefile /content/frontend/index.html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Monitor Deportivo Pro</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700;900&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">
  <style>
    :root{--ink:#0a0a0a;--paper:#f5f0e8;--cream:#ede8dc;--accent:#c8392b;--accent2:#2c4a7c;--muted:#7a7060;--border:#c8c0b0;--success:#2d6a4f;--ole:#00a846;--mono:'IBM Plex Mono',monospace;--sans:'IBM Plex Sans',sans-serif;--serif:'Playfair Display',Georgia,serif;}
    *{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:var(--sans);background:var(--paper);color:var(--ink);min-height:100vh;overflow-x:hidden;}
    .masthead{background:var(--ink);color:var(--paper);border-bottom:3px solid var(--accent);position:sticky;top:0;z-index:100;}
    .masthead-inner{display:flex;align-items:center;justify-content:space-between;padding:10px 28px;max-width:1600px;margin:0 auto;}
    .logo-title{font-family:var(--serif);font-size:1.6rem;font-weight:900;letter-spacing:-0.5px;line-height:1;color:var(--paper);}
    .logo-title span{color:var(--accent);}
    .logo-sub{font-family:var(--mono);font-size:0.58rem;letter-spacing:3px;text-transform:uppercase;color:var(--muted);}
    .status-bar{font-family:var(--mono);font-size:0.68rem;color:var(--muted);display:flex;gap:16px;align-items:center;}
    .dot{width:7px;height:7px;border-radius:50%;background:var(--muted);display:inline-block;margin-right:5px;}
    .dot.live{background:#4ade80;animation:pulse 2s infinite;}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
    .app-grid{display:grid;grid-template-columns:280px 1fr;min-height:calc(100vh - 60px);}
    .sidebar{background:var(--ink);color:var(--paper);padding:20px 16px;border-right:1px solid #1a1a1a;overflow-y:auto;position:sticky;top:60px;height:calc(100vh - 60px);}
    .sb-label{font-family:var(--mono);font-size:0.58rem;letter-spacing:3px;text-transform:uppercase;color:var(--muted);border-bottom:1px solid #1a1a1a;padding-bottom:6px;margin-bottom:10px;}
    .sb-section{margin-bottom:22px;}
    .group-btns{display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;margin-bottom:8px;}
    .group-btn{padding:7px 4px;border:1px solid #333;background:transparent;color:#888;font-family:var(--mono);font-size:0.62rem;cursor:pointer;transition:all .15s;text-align:center;}
    .group-btn.active{background:var(--accent);border-color:var(--accent);color:white;}
    .group-btn:hover:not(.active){border-color:#555;color:var(--paper);}
    .media-list{display:flex;flex-direction:column;gap:2px;max-height:240px;overflow-y:auto;}
    .media-list::-webkit-scrollbar{width:3px;}
    .media-list::-webkit-scrollbar-thumb{background:#333;}
    .media-item{display:flex;align-items:center;gap:8px;padding:5px 6px;cursor:pointer;border:1px solid transparent;transition:all .1s;}
    .media-item:hover{background:#111;border-color:#333;}
    .media-item input[type=checkbox]{appearance:none;width:13px;height:13px;border:1px solid #444;background:transparent;cursor:pointer;position:relative;flex-shrink:0;}
    .media-item input[type=checkbox]:checked{background:var(--accent);border-color:var(--accent);}
    .media-item input[type=checkbox]:checked::after{content:'✓';position:absolute;color:white;font-size:9px;top:-1px;left:1px;}
    .media-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;}
    .media-name{font-size:0.75rem;color:#ccc;flex:1;}
    .sel-btns{display:flex;gap:5px;margin-bottom:8px;}
    .sel-btn{flex:1;padding:4px;background:transparent;border:1px solid #333;color:#888;font-family:var(--mono);font-size:0.6rem;cursor:pointer;}
    .sel-btn:hover{color:var(--paper);border-color:#555;}
    .slider-row{display:flex;align-items:center;gap:8px;}
    input[type=range]{flex:1;accent-color:var(--accent);}
    .slider-val{font-family:var(--mono);font-size:0.72rem;color:var(--accent);min-width:22px;text-align:right;}
    .og-toggle{display:flex;align-items:center;gap:8px;margin-top:6px;}
    .og-toggle input[type=checkbox]{appearance:none;width:32px;height:17px;border:1px solid #444;background:#222;border-radius:9px;cursor:pointer;position:relative;transition:background .2s;}
    .og-toggle input[type=checkbox]:checked{background:var(--ole);border-color:var(--ole);}
    .og-toggle input[type=checkbox]::after{content:'';position:absolute;width:11px;height:11px;border-radius:50%;background:white;top:2px;left:2px;transition:left .2s;}
    .og-toggle input[type=checkbox]:checked::after{left:17px;}
    .og-toggle span{font-family:var(--mono);font-size:0.62rem;color:#888;}
    .scrape-btn{width:100%;padding:13px;background:var(--accent);color:white;border:none;font-family:var(--serif);font-size:0.95rem;font-weight:700;cursor:pointer;transition:all .2s;margin-top:8px;}
    .scrape-btn:hover{background:#a52d22;}
    .scrape-btn:disabled{background:#333;cursor:not-allowed;}
    .main-content{background:var(--paper);overflow-y:auto;}
    .ticker-bar{background:var(--ink);color:white;padding:0;overflow:hidden;white-space:nowrap;border-bottom:2px solid var(--accent);}
    .ticker-inner{display:inline-block;animation:ticker 120s linear infinite;font-family:var(--mono);font-size:0.65rem;letter-spacing:0.5px;padding:6px 0;}
    .ticker-inner:hover{animation-play-state:paused;}
    .ticker-seg{display:inline-block;padding:0 28px;}
    .ticker-flag{color:var(--accent);font-weight:700;margin-right:6px;}
    .ticker-topic{color:#e0e0e0;margin-right:4px;}
    .ticker-count{color:#888;font-size:0.58rem;margin-right:14px;}
    .ticker-divider{color:#333;margin:0 8px;}
    @keyframes ticker{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
    .tab-nav{display:flex;border-bottom:2px solid var(--ink);background:var(--cream);overflow-x:auto;}
    .tab-nav::-webkit-scrollbar{height:0;}
    .tab-btn{padding:10px 20px;border:none;background:transparent;font-family:var(--mono);font-size:0.7rem;letter-spacing:1px;text-transform:uppercase;cursor:pointer;color:var(--muted);border-bottom:3px solid transparent;margin-bottom:-2px;white-space:nowrap;transition:all .15s;}
    .tab-btn.active{color:var(--ink);border-bottom-color:var(--accent);font-weight:500;}
    .tab-btn:hover:not(.active){color:var(--ink);}
    .tab-content{display:none;}
    .tab-content.active{display:block;}
    .state-area{padding:60px 40px;text-align:center;}
    .state-icon{font-size:3rem;margin-bottom:16px;opacity:.4;}
    .state-title{font-family:var(--serif);font-size:1.4rem;margin-bottom:8px;color:var(--muted);}
    .state-sub{font-family:var(--mono);font-size:0.68rem;color:var(--border);}
    .progress-container{padding:28px 36px;}
    .progress-label{font-family:var(--mono);font-size:0.68rem;color:var(--muted);margin-bottom:6px;display:flex;justify-content:space-between;}
    .progress-bar{height:2px;background:var(--border);overflow:hidden;}
    .progress-fill{height:100%;background:var(--accent);transition:width .3s ease;}
    .scraping-log{padding:12px 36px;font-family:var(--mono);font-size:0.68rem;color:var(--muted);max-height:110px;overflow-y:auto;}
    .log-line{margin-bottom:2px;}
    .log-line::before{content:'▸ ';color:var(--success);}
    .stats-row{display:flex;gap:12px;padding:16px 28px;border-bottom:1px solid var(--border);flex-wrap:wrap;}
    .stat-card{background:white;border:1px solid var(--border);padding:10px 16px;min-width:110px;}
    .stat-num{font-family:var(--serif);font-size:1.5rem;font-weight:900;}
    .stat-label{font-family:var(--mono);font-size:0.58rem;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-top:2px;}
    .results-toolbar{display:flex;align-items:center;justify-content:space-between;padding:12px 28px;flex-wrap:wrap;gap:8px;}
    .results-count{font-family:var(--serif);font-size:1rem;}
    .results-count strong{color:var(--accent);}
    .toolbar-right{display:flex;gap:6px;align-items:center;}
    .tool-btn{padding:5px 12px;border:1px solid var(--border);background:transparent;font-family:var(--mono);font-size:0.63rem;cursor:pointer;color:var(--muted);transition:all .15s;}
    .tool-btn:hover{background:var(--ink);color:var(--paper);border-color:var(--ink);}
    .tool-btn.primary{background:var(--accent2);color:white;border-color:var(--accent2);}
    .search-bar{width:calc(100% - 56px);margin:0 28px 16px;padding:8px 14px;border:1px solid var(--border);background:var(--cream);font-family:var(--mono);font-size:0.74rem;color:var(--ink);outline:none;display:block;}
    .source-section{margin:0 28px 24px;border:1px solid var(--border);background:white;}
    .source-header{display:flex;align-items:center;justify-content:space-between;padding:9px 14px;background:var(--cream);border-bottom:1px solid var(--border);cursor:pointer;user-select:none;}
    .source-name{font-family:var(--serif);font-weight:700;font-size:0.95rem;}
    .source-meta{font-family:var(--mono);font-size:0.62rem;color:var(--muted);display:flex;gap:10px;align-items:center;}
    .source-ok{color:var(--success);}
    .source-err{color:var(--accent);}
    .source-body{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));}
    .source-body.collapsed{display:none;}
    .article-card{border-right:1px solid var(--border);border-bottom:1px solid var(--border);transition:background .15s;}
    .article-card:hover{background:#fafaf8;}
    .article-card.selected{background:#f0f4ff;border-left:3px solid var(--accent2);}
    .card-img-wrap{width:100%;padding-bottom:52%;overflow:hidden;background:var(--cream);position:relative;}
    .card-img-wrap img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;}
    .card-img-placeholder{display:flex;align-items:center;justify-content:center;position:absolute;inset:0;font-size:2rem;opacity:.3;}
    .card-body{padding:10px 12px 12px;}
    .card-source{font-size:10px;font-weight:700;font-family:var(--mono);letter-spacing:.6px;text-transform:uppercase;margin-bottom:4px;}
    .card-title{font-family:var(--serif);font-size:0.87rem;font-weight:700;line-height:1.35;color:var(--ink);text-decoration:none;display:block;}
    .article-card.selected .card-title{color:var(--accent2);}
    .card-title:hover{text-decoration:underline;}
    .card-title-nolink{font-family:var(--serif);font-size:0.87rem;font-weight:700;line-height:1.35;color:var(--ink);}
    .card-actions{display:flex;gap:5px;margin-top:7px;flex-wrap:wrap;}
    .card-btn{font-family:var(--mono);font-size:0.58rem;padding:2px 7px;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;transition:all .15s;}
    .card-btn:hover{background:var(--ink);color:var(--paper);border-color:var(--ink);}
    .tend-area{padding:20px 28px;}
    .tend-filters{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;}
    .tend-filter-btn{padding:5px 14px;border:1px solid var(--border);background:transparent;font-family:var(--mono);font-size:0.65rem;cursor:pointer;color:var(--muted);transition:all .15s;}
    .tend-filter-btn.active{background:var(--ink);color:var(--paper);border-color:var(--ink);}
    .tend-item{margin-bottom:8px;padding:10px 14px;border:1px solid var(--border);border-left:4px solid #888;background:white;}
    .tend-header{display:flex;align-items:center;gap:8px;margin-bottom:5px;flex-wrap:wrap;}
    .tend-count{font-family:var(--mono);font-size:0.65rem;font-weight:700;}
    .tend-bar-wrap{flex:1;height:4px;background:var(--border);min-width:60px;}
    .tend-bar{height:100%;}
    .tend-pct{font-family:var(--mono);font-size:0.6rem;color:var(--muted);}
    .tend-title{font-family:var(--serif);font-size:0.95rem;font-weight:700;line-height:1.3;margin-bottom:6px;}
    .tend-chips{display:flex;flex-wrap:wrap;gap:3px;}
    .chip{font-size:9px;font-weight:700;padding:1px 6px;border-radius:2px;font-family:var(--mono);}
    .tend-expand-btn{font-family:var(--mono);font-size:0.6rem;padding:2px 8px;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;margin-top:6px;}
    .tend-subnoticias{margin-top:8px;display:none;border-top:1px solid var(--border);padding-top:8px;}
    .tend-subnoticias.open{display:block;}
    .tend-sub-item{font-size:0.75rem;margin-bottom:4px;color:var(--muted);}
    .tend-sub-item a{color:var(--accent2);text-decoration:none;}
    .ole-area{padding:20px 28px;}
    .ole-sub-tabs{display:flex;gap:4px;margin-bottom:16px;border-bottom:1px solid var(--border);}
    .ole-sub-btn{padding:7px 16px;border:none;background:transparent;font-family:var(--mono);font-size:0.65rem;cursor:pointer;color:var(--muted);border-bottom:3px solid transparent;margin-bottom:-1px;}
    .ole-sub-btn.active{color:var(--ink);border-bottom-color:var(--ole);font-weight:500;}
    .ole-sub-content{display:none;}
    .ole-sub-content.active{display:block;}
    .ole-item{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);align-items:flex-start;}
    .ole-item-img{width:70px;height:50px;object-fit:cover;flex-shrink:0;background:var(--cream);}
    .ole-item-body{flex:1;}
    .ole-item-badge{font-size:9px;font-weight:700;padding:1px 6px;border-radius:2px;font-family:var(--mono);margin-bottom:4px;display:inline-block;}
    .ole-item-title{font-family:var(--serif);font-size:0.85rem;font-weight:700;line-height:1.3;}
    .ole-item-title a{color:var(--ink);text-decoration:none;}
    .ole-metrics{display:flex;gap:12px;margin-bottom:16px;}
    .ole-metric{background:white;border:1px solid var(--border);padding:12px 18px;text-align:center;flex:1;}
    .ole-metric-num{font-family:var(--serif);font-size:1.6rem;font-weight:900;}
    .ole-metric-label{font-family:var(--mono);font-size:0.58rem;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-top:2px;}
    .nube-area{padding:20px 28px;}
    .nube-container{position:relative;width:100%;height:280px;background:white;border:1px solid var(--border);overflow:hidden;margin-bottom:16px;}
    .nube-word{position:absolute;transform:translate(-50%,-50%);white-space:nowrap;cursor:default;line-height:1;font-family:var(--sans);}
    .nube-tabs{display:flex;gap:6px;margin-bottom:12px;}
    .nube-tab-btn{padding:5px 14px;border:1px solid var(--border);background:transparent;font-family:var(--mono);font-size:0.63rem;cursor:pointer;color:var(--muted);}
    .nube-tab-btn.active{background:var(--ink);color:var(--paper);border-color:var(--ink);}
    .ai-panel{position:fixed;right:0;top:60px;width:680px;height:calc(100vh - 60px);background:var(--ink);color:var(--paper);transform:translateX(100%);transition:transform .3s cubic-bezier(.4,0,.2,1);z-index:200;display:flex;flex-direction:column;border-left:3px solid var(--accent);}
    .ai-panel.open{transform:translateX(0);}
    .ai-header{padding:18px 22px 14px;border-bottom:1px solid #222;display:flex;align-items:center;justify-content:space-between;}
    .ai-title{font-family:var(--serif);font-size:1rem;}
    .ai-title span{color:var(--accent);}
    .close-ai{background:transparent;border:1px solid #333;color:#888;width:26px;height:26px;cursor:pointer;font-size:.9rem;display:flex;align-items:center;justify-content:center;}
    .ai-sel-list{padding:10px 22px;border-bottom:1px solid #222;max-height:130px;overflow-y:auto;}
    .ai-sel-label{font-family:var(--mono);font-size:0.58rem;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:6px;}
    .ai-sel-item{font-size:0.73rem;color:#ccc;padding:2px 0;border-bottom:1px solid #1a1a1a;}
    .ai-sel-item::before{content:'— ';color:var(--accent);}
    .ai-opts{padding:14px 22px;border-bottom:1px solid #222;}
    .ai-op-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:8px;}
    .ai-op-btn{padding:7px;border:1px solid #333;background:transparent;color:#888;font-family:var(--mono);font-size:0.65rem;cursor:pointer;text-align:center;}
    .ai-op-btn.active{background:var(--accent2);border-color:var(--accent2);color:white;}
    .ai-prompt{width:100%;padding:8px 10px;background:#111;border:1px solid #333;color:var(--paper);font-family:var(--mono);font-size:0.72rem;resize:vertical;min-height:70px;outline:none;}
    .ai-gen-btn{margin:10px 22px 0;width:calc(100% - 44px);padding:11px;background:var(--accent);color:white;border:none;font-family:var(--serif);font-size:.9rem;font-weight:700;cursor:pointer;}
    .ai-gen-btn:disabled{background:#333;cursor:not-allowed;}
    .ai-output{flex:1;padding:18px 22px;overflow-y:auto;font-size:.82rem;line-height:1.75;color:#ddd;min-height:200px;}
    .ai-out-label{font-family:var(--mono);font-size:.58rem;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:10px;}
    .ai-result{white-space:pre-wrap;font-family:var(--sans);}
    .ai-textarea-copy{width:100%;min-height:480px;background:#0a0a0a;border:1px solid #2a2a2a;color:#e0e0e0;font-family:var(--sans);font-size:.82rem;line-height:1.75;padding:12px 14px;resize:vertical;outline:none;box-sizing:border-box;margin-top:10px;border-radius:2px;}
    .ai-textarea-copy:focus{border-color:#444;}
    .ai-copy-btn{margin-top:10px;padding:5px 12px;background:transparent;border:1px solid #333;color:#888;font-family:var(--mono);font-size:.62rem;cursor:pointer;}
    .loading-dots span{animation:blink 1.2s infinite;}
    .loading-dots span:nth-child(2){animation-delay:.2s;}
    .loading-dots span:nth-child(3){animation-delay:.4s;}
    @keyframes blink{0%,100%{opacity:.2}50%{opacity:1}}
    .sel-float{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:var(--ink);color:var(--paper);padding:9px 22px;font-family:var(--mono);font-size:.72rem;display:flex;align-items:center;gap:14px;z-index:150;border:1px solid #333;opacity:0;pointer-events:none;transition:opacity .2s;}
    .sel-float.visible{opacity:1;pointer-events:all;}
    .sel-count{color:var(--accent);font-weight:600;}
    .sel-ia-btn{padding:5px 14px;background:var(--accent2);color:white;border:none;font-family:var(--mono);font-size:.68rem;cursor:pointer;}
    .sel-clear-btn{padding:5px 10px;background:transparent;border:1px solid #444;color:#888;font-family:var(--mono);font-size:.68rem;cursor:pointer;}
    .modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:300;display:none;align-items:center;justify-content:center;padding:36px;}
    .modal-overlay.open{display:flex;}
    .modal-box{background:var(--paper);max-width:740px;width:100%;max-height:80vh;overflow-y:auto;padding:32px 36px;position:relative;}
    .modal-close{position:absolute;top:14px;right:14px;background:transparent;border:1px solid var(--border);color:var(--muted);width:30px;height:30px;cursor:pointer;font-size:.9rem;}
    .modal-title{font-family:var(--serif);font-size:1.4rem;font-weight:900;line-height:1.3;margin-bottom:16px;padding-right:36px;}
    .modal-img{width:100%;max-height:300px;object-fit:cover;margin-bottom:16px;}
    .modal-body{font-size:.87rem;line-height:1.8;color:#333;white-space:pre-wrap;}
    .modal-add-btn{margin-top:16px;padding:9px 18px;background:var(--accent2);color:white;border:none;font-family:var(--mono);font-size:.7rem;cursor:pointer;}
  </style>
</head>
<body>
<header class="masthead">
  <div class="masthead-inner">
    <div><div class="logo-title">Monitor <span>Deportivo</span></div><div class="logo-sub">Scraper & AI Studio · Pro</div></div>
    <div class="status-bar"><span><span class="dot" id="sDot"></span><span id="sTxt">Listo</span></span><span id="sCount" style="display:none">— <strong id="sTotalCount">0</strong> noticias</span></div>
  </div>
</header>
<div class="ticker-bar" id="tickerBar" style="display:none" title="Pausar: pasar el mouse encima"><div style="overflow:hidden;width:100%"><div class="ticker-inner" id="tickerInner"></div></div></div>
<div class="app-grid">
  <aside class="sidebar">
    <div class="sb-section">
      <div class="sb-label">Grupo</div>
      <div class="group-btns">
        <button class="group-btn active" onclick="setGrupo('todas',this)">Todos</button>
        <button class="group-btn" onclick="setGrupo('nacionales',this)">AR</button>
        <button class="group-btn" onclick="setGrupo('internacionales',this)">INT</button>
      </div>
    </div>
    <div class="sb-section">
      <div class="sb-label">Fuentes</div>
      <div class="sel-btns"><button class="sel-btn" onclick="selAll()">Todo</button><button class="sel-btn" onclick="selNone()">Ninguno</button></div>
      <div class="media-list" id="mediaList"></div>
    </div>
    <div class="sb-section">
      <div class="sb-label">Noticias por fuente</div>
      <div class="slider-row"><input type="range" min="5" max="35" value="20" id="maxSlider" oninput="document.getElementById('maxVal').textContent=this.value"><div class="slider-val" id="maxVal">20</div></div>
    </div>
    <div class="sb-section">
      <div class="sb-label">Imagenes</div>
      <div class="og-toggle"><input type="checkbox" id="ogToggle" checked><span>Buscar og:image</span></div>
    </div>
    <button class="scrape-btn" id="scrapeBtn" onclick="startScraping()">Scrapear</button>
  </aside>
  <main class="main-content" id="mainContent">
    <div class="state-area"><div class="state-icon">newspaper</div><div class="state-title">Selecciona fuentes y lanza el scraping</div><div class="state-sub">Titulares con imagenes, tendencias y analisis Ole</div></div>
  </main>
</div>
<div class="ai-panel" id="aiPanel">
  <div class="ai-header"><div class="ai-title">&#128240; Generador de <span>Nota</span></div><button class="close-ai" onclick="closeAI()">X</button></div>
  <div class="ai-sel-list"><div class="ai-sel-label">Notas seleccionadas</div><div id="aiSelList"></div></div>
  <div class="ai-opts">
    <div class="ai-sel-label">Transformacion</div>
    <div class="ai-op-grid" style="grid-template-columns:1fr 1fr;">
      <button class="ai-op-btn active" onclick="setAIMode('nota',this)">&#128240; Nueva nota</button>
      <button class="ai-op-btn" onclick="setAIMode('custom',this)">&#9998; Instruccion libre</button>
    </div>
    <div id="aiPromptLabel" class="ai-sel-label" style="display:none;margin-top:8px">Instruccion</div><textarea class="ai-prompt" id="aiPromptTxt" placeholder="Escribi instrucciones para la IA..." style="display:none"></textarea>
  </div>
  <div class="ai-opts" style="margin-top:8px">
    <div class="ai-sel-label">API Key de Claude</div>
    <input type="password" id="claudeApiKey" placeholder="sk-ant-api03-..." style="width:100%;padding:7px 10px;background:#1a1a1a;border:1px solid #333;color:#e0e0e0;font-family:var(--mono);font-size:.72rem;border-radius:4px;box-sizing:border-box"/>
    <div style="font-size:.6rem;color:#555;margin-top:3px;font-family:var(--mono)">Solo se usa localmente, nunca se guarda ni se envía a terceros.</div>
  </div>
  <div style="display:flex;gap:6px;margin:10px 22px 0"><button class="ai-gen-btn" id="aiGenBtn" onclick="generateAI()" style="flex:1;margin:0">&#10003; Generar nota</button></div>
  <div class="ai-output" id="aiOutput"><div class="ai-out-label">Nota generada</div><div style="color:#444;font-family:var(--mono);font-size:.68rem">Carga articulos a la canasta y presiona Generar nota.</div></div>
</div>
<div class="sel-float" id="selFloat">
  <span><span class="sel-count" id="selCount">0</span> seleccionadas</span>
  <button class="sel-ia-btn" onclick="openAI()">Pasar a IA</button>
  <button class="sel-clear-btn" onclick="clearSel()">X</button>
</div>
<div class="modal-overlay" id="articleModal">
  <div class="modal-box"><button class="modal-close" onclick="closeModal()">X</button><div id="modalContent"></div></div>
</div>
<script>
const API='';
let allFuentes={nacionales:[],internacionales:[]},grupo='todas',selectedArticles=[],scrapedData=[],currentArticleFull=null,aiMode='nota',lastResults=null,canasta=[];
async function init(){const r=await fetch(API+'/api/fuentes');const d=await r.json();allFuentes=d;renderMediaList();}
function getDF(){if(grupo==='nacionales')return allFuentes.nacionales;if(grupo==='internacionales')return allFuentes.internacionales;return[...allFuentes.nacionales,...allFuentes.internacionales];}
function renderMediaList(){document.getElementById('mediaList').innerHTML=getDF().map(f=>`<label class="media-item"><input type="checkbox" value="${f.id}" checked><span class="media-dot" style="background:${f.color}"></span><span class="media-name">${f.nombre}</span></label>`).join('');}
function setGrupo(g,btn){grupo=g;document.querySelectorAll('.group-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');renderMediaList();}
function selAll(){document.querySelectorAll('#mediaList input').forEach(i=>i.checked=true);}
function selNone(){document.querySelectorAll('#mediaList input').forEach(i=>i.checked=false);}
function getSelectedIds(){return Array.from(document.querySelectorAll('#mediaList input:checked')).map(i=>i.value);}
async function startScraping(){
  const ids=getSelectedIds();if(!ids.length){alert('Selecciona al menos una fuente');return;}
  const btn=document.getElementById('scrapeBtn');btn.disabled=true;btn.textContent='Scrapeando...';
  selectedArticles=[];updateFloat();
  const main=document.getElementById('mainContent');
  main.innerHTML='<div class="progress-container"><div class="progress-label"><span id="progLbl">Conectando...</span><span id="progPct">0%</span></div><div class="progress-bar"><div class="progress-fill" id="progFill" style="width:0%"></div></div></div><div class="scraping-log" id="scrapLog"></div>';
  setStatus('live','Scrapeando...');
  const fill=document.getElementById('progFill'),pct=document.getElementById('progPct'),lbl=document.getElementById('progLbl'),log=document.getElementById('scrapLog');
  let li=0;const iv=setInterval(()=>{if(li<ids.length){const p=Math.round(li/ids.length*100);fill.style.width=p+'%';pct.textContent=p+'%';lbl.textContent='Procesando: '+ids[li];const d=document.createElement('div');d.className='log-line';d.textContent=ids[li];log.appendChild(d);log.scrollTop=log.scrollHeight;li++;}},700);
  try{
    const res=await fetch(API+'/api/scrape',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fuentes:ids,grupo:grupo,max_per_site:parseInt(document.getElementById('maxSlider').value),fetch_og:document.getElementById('ogToggle').checked})});
    clearInterval(iv);const data=await res.json();lastResults=data;scrapedData=data.fuentes;renderResults(data);setStatus('live','Completado');
  }catch(e){clearInterval(iv);main.innerHTML='<div class="state-area"><div class="state-icon">error</div><div class="state-title">Error de conexion</div></div>';setStatus('','Error');}
  btn.disabled=false;btn.textContent='Scrapear';
}
function buildSmartTicker(fuentes, tendencias, nacIds){
  // Count word frequency per region
  const stopwords=new Set(['de','la','el','en','y','a','los','del','se','las','por','un','para','con','una','su','al','lo','que','no','es','fue','ha','ya','o','si','este','son','como','pero','sus','le','mas','muy','sin','sobre','cuando','me','hay','donde','desde','todo','nos','bien','cada','ser','tiene','era','otro','otras','otra','ante','tras','vs','the','and','for','with','from','this','that','are','was','were','have','has','been']);
  function tokenize(t){return t.toLowerCase().replace(/[^a-záéíóúüñ0-9\s]/gi,' ').split(/\s+/).filter(w=>w.length>3&&!stopwords.has(w));}
  const nacFreq={}, intFreq={};
  fuentes.forEach(f=>{
    const isNac=nacIds.has(f.id);
    (f.items||[]).forEach(n=>{
      tokenize(n.titulo||'').forEach(w=>{
        if(isNac){nacFreq[w]=(nacFreq[w]||0)+1;}
        else{intFreq[w]=(intFreq[w]||0)+1;}
      });
    });
  });
  // Get top topics — sort by freq, deduplicate by first word
  function topTopics(freq, n){
    return Object.entries(freq)
      .sort((a,b)=>b[1]-a[1])
      .slice(0,n)
      .map(([w,c])=>({w,c}));
  }
  const nacTop=topTopics(nacFreq,18);
  const intTop=topTopics(intFreq,18);
  // Also get top tendencias titles for context
  const tends=(tendencias||[]).slice(0,12);
  // Build segments
  let segs=[];
  // Section ARG
  if(nacTop.length){
    segs.push('<span class="ticker-seg"><span class="ticker-flag">🇦🇷 ARGENTINA</span>'
      +nacTop.map(t=>`<span class="ticker-topic">${t.w}</span><span class="ticker-count">(${t.c})</span>`).join('<span class="ticker-divider">·</span>')
      +'</span>');
  }
  // Separator
  segs.push('<span class="ticker-divider" style="color:var(--accent);font-size:1rem;padding:0 20px">◆</span>');
  // Section INT
  if(intTop.length){
    segs.push('<span class="ticker-seg"><span class="ticker-flag">🌍 INTERNACIONAL</span>'
      +intTop.map(t=>`<span class="ticker-topic">${t.w}</span><span class="ticker-count">(${t.c})</span>`).join('<span class="ticker-divider">·</span>')
      +'</span>');
  }
  // Separator
  segs.push('<span class="ticker-divider" style="color:var(--accent);font-size:1rem;padding:0 20px">◆</span>');
  // Trending topics section
  if(tends.length){
    segs.push('<span class="ticker-seg"><span class="ticker-flag">🔥 TENDENCIAS</span>'
      +tends.map(t=>`<span class="ticker-topic">${eh(t.titulo.substring(0,60))}</span><span class="ticker-count">[${t.cant_medios} medios]</span>`).join('<span class="ticker-divider"> — </span>')
      +'</span>');
  }
  const content=segs.join('');
  // Duplicate for seamless loop
  const inner=document.getElementById('tickerInner');
  inner.innerHTML=content+
    '<span class="ticker-divider" style="color:var(--accent);font-size:1rem;padding:0 40px">◆◆◆</span>'
    +content;
  document.getElementById('tickerBar').style.display='';
  // Adjust animation duration based on content length
  const totalChars=inner.textContent.length;
  const dur=Math.max(90, Math.min(180, totalChars*0.18));
  inner.style.animationDuration=dur+'s';
}
function renderResults(data){
  const total=data.total;
  document.getElementById('sCount').style.display='';document.getElementById('sTotalCount').textContent=total;
  const nacIds=new Set(['ole','espn','tyc','infobae','lanacion','tn','clarin','elgrafico','dobleamarilla','bolavip','lavoz','capital','ole_ult','na']);
  buildSmartTicker(data.fuentes, data.tendencias||[], nacIds);
  const stats=data.stats||{},oleA=data.ole_analisis||{},tends=data.tendencias||[],nf=data.fuentes.filter(f=>f.items.length).length;
  const main=document.getElementById('mainContent');
  main.innerHTML=`
    <div class="stats-row">
      <div class="stat-card"><div class="stat-num" style="color:var(--accent)">${total}</div><div class="stat-label">Noticias</div></div>
      <div class="stat-card"><div class="stat-num">${nf}</div><div class="stat-label">Fuentes</div></div>
      <div class="stat-card"><div class="stat-num" style="color:var(--accent2)">${stats.tendencias||0}</div><div class="stat-label">Tendencias</div></div>
      <div class="stat-card"><div class="stat-num" style="color:#dc2626">${stats.hot||0}</div><div class="stat-label">Hot</div></div>
      <div class="stat-card"><div class="stat-num" style="color:var(--ole)">${stats.con_ole||0}</div><div class="stat-label">Con Ole</div></div>
      <div class="stat-card"><div class="stat-num" style="color:var(--accent)">${stats.sin_ole||0}</div><div class="stat-label">Sin Ole</div></div>
    </div>
    <div class="tab-nav" id="tabNav">
      <button class="tab-btn active" onclick="switchTab('noticias',this)">Noticias</button>
      <button class="tab-btn" onclick="switchTab('tendencias',this)">Tendencias (${stats.tendencias||0})</button>
      <button class="tab-btn" onclick="switchTab('ole',this)">Ole vs Todos</button>
      <button class="tab-btn" onclick="switchTab('nube',this)">Nube</button>
    </div>
    <div class="tab-content active" id="tab-noticias">
      <div class="results-toolbar">
        <div class="results-count"><strong>${total}</strong> noticias de <strong>${nf}</strong> fuentes</div>
        <div class="toolbar-right"><button class="tool-btn" onclick="exportCSV()">CSV</button><button class="tool-btn" onclick="exportJSON()">JSON</button><button class="tool-btn primary" onclick="openAI()">IA</button></div>
      </div>
      <input type="text" class="search-bar" placeholder="Buscar..." oninput="filterResults(this.value)">
      <div id="resultsBody">${renderFuentes(data.fuentes)}</div>
    </div>
    <div class="tab-content" id="tab-tendencias"><div class="tend-area">${renderTendencias(tends,data.fuentes.length)}</div></div>
    <div class="tab-content" id="tab-ole"><div class="ole-area">${renderOle(oleA)}</div></div>
    <div class="tab-content" id="tab-nube"><div class="nube-area">${renderNube(data)}</div></div>
  `;
}
function eh(s){if(!s)return'';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
function renderFuentes(fuentes){
  return fuentes.map(src=>{
    if(!src.items.length&&src.status!=='error')return'';
    const sc=src.status==='ok'?'source-ok':'source-err';
    const cards=src.status==='error'
      ?`<div style="padding:14px;font-family:var(--mono);font-size:.68rem;color:var(--accent);grid-column:1/-1">Error al cargar</div>`
      :src.items.map((item,i)=>{
          const aid=`${src.id}__${i}`;
          const imgH=item.imagen?`<div class="card-img-wrap"><img src="${eh(item.imagen)}" onerror="this.parentElement.innerHTML='<div class=card-img-placeholder>S</div>'"></div>`:`<div class="card-img-wrap"><div class="card-img-placeholder">S</div></div>`;
          const titleH=item.url?`<a class="card-title" href="${eh(item.url)}" target="_blank">${eh(item.titulo)}</a>`:`<span class="card-title-nolink">${eh(item.titulo)}</span>`;
          return`<div class="article-card" id="card-${aid}" data-title="${eh(item.titulo)}">${imgH}<div class="card-body"><div class="card-source" style="color:${src.color}">${eh(src.nombre)}</div>${titleH}<div class="card-actions"><button class="card-btn" onclick="toggleSel('${aid}','${eh(item.titulo)}','','${eh(item.url||'')}')">+ Sel.</button>${item.url?`<button class="card-btn" onclick="loadFullArticle('${eh(item.url)}','${eh(item.titulo)}')">Leer</button>`:''}</div></div></div>`;
        }).join('');
    return`<div class="source-section"><div class="source-header" onclick="toggleSource(this)"><div class="source-name" style="border-left:3px solid ${src.color};padding-left:8px">${eh(src.nombre)}</div><div class="source-meta"><span class="${sc}">${src.status==='ok'?'ok':'err'}</span><span>${src.items.length} items</span><span>v</span></div></div><div class="source-body">${cards}</div></div>`;
  }).join('');
}
function renderTendencias(tends,totalF){
  if(!tends.length)return'<div class="state-area"><div class="state-title">Sin tendencias</div></div>';
  const sinOle=tends.filter(t=>!t.tiene_ole),conOle=tends.filter(t=>t.tiene_ole),hot=tends.filter(t=>t.cant_medios/Math.max(totalF,1)>=0.20);
  return`<div class="tend-filters"><button class="tend-filter-btn active" onclick="filtrarTend('todos',this)">Todos (${tends.length})</button><button class="tend-filter-btn" onclick="filtrarTend('sin_ole',this)">Sin Ole (${sinOle.length})</button><button class="tend-filter-btn" onclick="filtrarTend('con_ole',this)">Con Ole (${conOle.length})</button><button class="tend-filter-btn" onclick="filtrarTend('hot',this)">Hot (${hot.length})</button></div><div id="tendList">${renderTendList(tends,totalF)}</div>`;
}
function renderTendList(tends,tf){
  return tends.slice(0,60).map(t=>{
    const pct=Math.round(t.cant_medios/Math.max(tf,1)*100);
    let accent='#3b82f6',emoji='-';
    if(pct>=50){accent='#dc2626';emoji='HOT';}else if(pct>=30){accent='#ea580c';emoji='!';}else if(pct>=15){accent='#ca8a04';emoji='^';}
    const chips=t.noticias.map(n=>`<span class="chip" style="background:${n.fuente_color}22;color:${n.fuente_color};border:1px solid ${n.fuente_color}44">${eh(n.fuente_nombre)}</span>`).join('');
    const subs=t.noticias.map(n=>`<div class="tend-sub-item"><b style="color:${n.fuente_color}">${eh(n.fuente_nombre)}</b> - ${n.url?`<a href="${eh(n.url)}" target="_blank">${eh(n.titulo)}</a>`:eh(n.titulo)}</div>`).join('');
    return`<div class="tend-item" style="border-left-color:${accent}" data-tiene-ole="${t.tiene_ole}" data-pct="${pct}"><div class="tend-header"><span class="tend-count" style="color:${accent}">${emoji} ${t.cant_medios} medios</span><span>${t.tiene_ole?'[OLE]':''}</span><span style="font-family:var(--mono);font-size:.6rem;color:var(--muted)">${t.nac} AR ${t.intl} INT</span><div class="tend-bar-wrap"><div class="tend-bar" style="width:${pct}%;background:${accent}"></div></div><span class="tend-pct">${pct}%</span></div><div class="tend-title">${t.url?`<a href="${eh(t.url)}" target="_blank" style="color:var(--ink);text-decoration:none">${eh(t.titulo)}</a>`:eh(t.titulo)}</div><div class="tend-chips">${chips}</div><div style="display:flex;gap:6px;align-items:center;margin-top:6px">
      <button class="tend-expand-btn" onclick="toggleTendSub(this)">ver notas (${t.noticias.length})</button>
      <button class="tend-expand-btn" style="background:#0a1628;border-color:#2c4a7c;color:#90b4e8" onclick="tendenciaAIA(this)" data-urls='${JSON.stringify(t.noticias.map(n=>n.url).filter(Boolean))}' data-titulos='${JSON.stringify(t.noticias.map(n=>n.titulo))}'>Pasar tendencia a IA</button>
    </div>
    <div class="tend-subnoticias">${subs}</div></div>`;
  }).join('');
}
function filtrarTend(filtro,btn){
  document.querySelectorAll('.tend-filter-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');
  document.querySelectorAll('.tend-item').forEach(el=>{
    const tieneOle=el.dataset.tieneOle==='true',pct=parseInt(el.dataset.pct);
    let show=true;
    if(filtro==='sin_ole')show=!tieneOle;else if(filtro==='con_ole')show=tieneOle;else if(filtro==='hot')show=pct>=20;
    el.style.display=show?'':'none';
  });
}
function toggleTendSub(btn){const sub=btn.nextElementSibling;sub.classList.toggle('open');btn.textContent=sub.classList.contains('open')?'ocultar notas':'ver notas';}
async function tendenciaAIA(btn){
  const urls=JSON.parse(btn.dataset.urls||'[]');
  const titulos=JSON.parse(btn.dataset.titulos||'[]');
  selectedArticles=titulos.map((t,i)=>({id:'tend__'+i,titulo:t,url:urls[i]||null,bajada:''}));
  canasta=[];
  updateFloat();
  await openAI();
}
function renderOle(analisis){
  if(!analisis||(!analisis.exclusivos_ole&&!analisis.faltantes_en_ole))return'<div class="state-area"><div class="state-title">Incluye Ole en el scraping para ver este analisis</div></div>';
  const excl=analisis.exclusivos_ole||[],falt=analisis.faltantes_en_ole||[],comp=analisis.cubiertos_por_ambos||[];
  const exclH=excl.map(n=>`<div class="ole-item"><div class="ole-item-body"><div class="ole-item-title">${n.url?`<a href="${eh(n.url)}" target="_blank">* ${eh(n.titulo)}</a>`:`* ${eh(n.titulo)}`}</div></div></div>`).join('')||'<div style="color:var(--muted);font-family:var(--mono);font-size:.7rem">No se detectaron exclusivos.</div>';
  const faltH=falt.map(n=>`<div class="ole-item">${n.imagen?`<img class="ole-item-img" src="${eh(n.imagen)}" onerror="this.style.display='none'">`:''}<div class="ole-item-body"><div class="ole-item-badge" style="background:${n.fuente_color}22;color:${n.fuente_color}">${eh(n.fuente_nombre)}</div><div class="ole-item-title">${n.url?`<a href="${eh(n.url)}" target="_blank">${eh(n.titulo)}</a>`:eh(n.titulo)}</div></div></div>`).join('')||'<div style="color:var(--success);font-family:var(--mono);font-size:.7rem">Ole cubre todos los temas.</div>';
  const compH=comp.map(c=>`<div style="margin-bottom:12px;padding:10px;border:1px solid var(--border);background:white"><div style="font-family:var(--serif);font-size:.85rem;font-weight:700;margin-bottom:6px">${c.url_ole?`<a href="${eh(c.url_ole)}" target="_blank" style="color:var(--ole);text-decoration:none">OLE: ${eh(c.titulo_ole)}</a>`:`OLE: ${eh(c.titulo_ole)}`}</div>${c.competencia.map(cx=>`<div style="font-size:.75rem;color:var(--muted);padding:2px 0 2px 12px;border-left:2px solid ${cx.fuente_color}"><b style="color:${cx.fuente_color}">${eh(cx.fuente_nombre)}</b> - ${cx.url?`<a href="${eh(cx.url)}" target="_blank" style="color:var(--accent2)">${eh(cx.titulo)}</a>`:eh(cx.titulo)}</div>`).join('')}</div>`).join('')||'<div style="color:var(--muted);font-family:var(--mono);font-size:.7rem">Sin compartidos.</div>';
  return`<div class="ole-metrics"><div class="ole-metric"><div class="ole-metric-num" style="color:var(--ole)">${excl.length}</div><div class="ole-metric-label">Exclusivos Ole</div></div><div class="ole-metric"><div class="ole-metric-num" style="color:var(--accent)">${falt.length}</div><div class="ole-metric-label">Ausentes en Ole</div></div><div class="ole-metric"><div class="ole-metric-num" style="color:var(--accent2)">${comp.length}</div><div class="ole-metric-label">Compartidos</div></div></div><div class="ole-sub-tabs"><button class="ole-sub-btn active" onclick="switchOleSub('excl',this)">Exclusivos (${excl.length})</button><button class="ole-sub-btn" onclick="switchOleSub('falt',this)">Faltantes (${falt.length})</button><button class="ole-sub-btn" onclick="switchOleSub('comp',this)">Compartidos (${comp.length})</button></div><div class="ole-sub-content active" id="ole-excl">${exclH}</div><div class="ole-sub-content" id="ole-falt">${faltH}</div><div class="ole-sub-content" id="ole-comp">${compH}</div>`;
}
function switchOleSub(id,btn){document.querySelectorAll('.ole-sub-btn').forEach(b=>b.classList.remove('active'));document.querySelectorAll('.ole-sub-content').forEach(c=>c.classList.remove('active'));btn.classList.add('active');document.getElementById('ole-'+id).classList.add('active');}
function renderNube(data){
  return`<div class="nube-tabs"><button class="nube-tab-btn active" onclick="switchNube('nac',this)">Nacionales</button><button class="nube-tab-btn" onclick="switchNube('int',this)">Internacionales</button></div><div id="nube-nac">${renderNubeCloud(data.nube_nac||[])}</div><div id="nube-int" style="display:none">${renderNubeCloud(data.nube_int||[])}</div>`;
}
function renderNubeCloud(words){
  if(!words.length)return'<div style="padding:40px;text-align:center;color:var(--muted);font-family:var(--mono);font-size:.7rem">Sin datos</div>';
  const items=words.map(w=>`<span class="nube-word" style="left:${w.x}%;top:${w.y}%;font-size:${w.size}px;color:${w.color};font-weight:${w.weight};opacity:${w.opacity}" title="${w.count} menciones">${eh(w.word)}</span>`).join('');
  const top=words.slice(0,12).map(w=>`<b>${w.word}</b> x${w.count}`).join(' - ');
  return`<div class="nube-container">${items}</div><div style="font-size:.72rem;color:var(--ink);line-height:2">${top}</div>`;
}
function switchNube(id,btn){document.querySelectorAll('.nube-tab-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');document.getElementById('nube-nac').style.display=id==='nac'?'':'none';document.getElementById('nube-int').style.display=id==='int'?'':'none';}
function switchTab(id,btn){document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));btn.classList.add('active');document.getElementById('tab-'+id).classList.add('active');}
function toggleSource(h){const b=h.nextElementSibling;b.classList.toggle('collapsed');}
function filterResults(q){const lq=q.toLowerCase();document.querySelectorAll('.article-card').forEach(c=>{c.style.display=(c.dataset.title||'').toLowerCase().includes(lq)?'':'none';});}
function toggleSel(id,titulo,bajada,url){const card=document.getElementById('card-'+id);const idx=selectedArticles.findIndex(a=>a.id===id);if(idx>-1){selectedArticles.splice(idx,1);card&&card.classList.remove('selected');}else{selectedArticles.push({id,titulo,bajada,url:url||null});card&&card.classList.add('selected');}updateFloat();}
function updateFloat(){const f=document.getElementById('selFloat');document.getElementById('selCount').textContent=selectedArticles.length;f.classList.toggle('visible',selectedArticles.length>0);}
function clearSel(){selectedArticles=[];canasta=[];document.querySelectorAll('.article-card.selected').forEach(c=>c.classList.remove('selected'));updateFloat();}
async function openAI(){
  if(!selectedArticles.length){alert('Selecciona al menos una nota');return;}
  const urls=selectedArticles.map(a=>a.url).filter(Boolean);
  const out=document.getElementById('aiOutput');
  document.getElementById('aiPanel').classList.add('open');
  renderAISelected();
  if(!urls.length){
    canasta=selectedArticles.map(a=>`TITULAR: ${a.titulo}${a.bajada?'\nBAJADA: '+a.bajada:''}`);
    renderCanasta();return;
  }
  out.innerHTML='<div class="ai-out-label">Descargando textos completos...</div><div class="loading-dots" style="color:#888;font-family:var(--mono);font-size:.8rem"><span>.</span><span>.</span><span>.</span></div>';
  try{
    const r=await fetch(API+'/api/batch_scrape',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({urls})});
    const d=await r.json();
    canasta=d.articulos.map(a=>{
      const tiene=a.contenido&&a.contenido.trim().length>80;
      return `FUENTE: ${a.url}\nTITULAR: ${a.titulo}\n\n${tiene?a.contenido:'[Solo titular disponible — posible paywall o sitio con JS]'}`;
    });
    renderCanasta(d.articulos);
  }catch(e){
    canasta=selectedArticles.map(a=>`TITULAR: ${a.titulo}${a.bajada?'\nBAJADA: '+a.bajada:''}`);
    renderCanasta();
  }
}
function renderCanasta(articulos){
  const out=document.getElementById('aiOutput');
  const totalChars=canasta.join('\n\n---\n\n').length;
  const conContenido=articulos?articulos.filter(a=>a.contenido&&a.contenido.trim().length>80).length:canasta.length;
  const sinContenido=articulos?articulos.length-conContenido:0;
  const alertaSin=sinContenido>0
    ?`<div style="background:#1a0a00;border:1px solid #7a3800;padding:6px 10px;font-family:var(--mono);font-size:.62rem;color:#f97316;margin-bottom:8px">&#9888; ${sinContenido} artículo(s) sin texto completo (paywall o JS). Solo se usará el titular para esos.</div>`
    :'';
  const items=canasta.map((t,i)=>{
    const lineas=t.split('\n');
    const tit=(lineas[1]||lineas[0]||'').replace('TITULAR: ','');
    const cuerpo=t.substring(t.indexOf('\n\n')+2).trim();
    const tieneTexto=cuerpo.length>80&&!cuerpo.startsWith('[Solo titular');
    const badge=tieneTexto
      ?`<span style="color:#4ade80;font-size:.55rem;flex-shrink:0">&#10003; ${cuerpo.length.toLocaleString()} chars</span>`
      :`<span style="color:#f97316;font-size:.55rem;flex-shrink:0">&#9888; solo titular</span>`;
    const previewId=`cprev_${i}`;
    const previewBtn=tieneTexto
      ?`<button onclick="togglePreview('${previewId}')" style="font-size:.55rem;padding:1px 5px;border:1px solid #333;background:transparent;color:#666;cursor:pointer;margin-left:4px">ver</button>`
      :'';
    const preview=tieneTexto
      ?`<div id="${previewId}" style="display:none;margin-top:4px;padding:6px 8px;background:#0d0d0d;border-left:2px solid #2d6a4f;font-size:.62rem;color:#888;line-height:1.6;max-height:120px;overflow-y:auto;white-space:pre-wrap">${eh(cuerpo.substring(0,600))}${cuerpo.length>600?'…':''}</div>`
      :'';
    return `<div style="padding:5px 0;border-bottom:1px solid #1a1a1a">
      <div style="display:flex;gap:6px;align-items:baseline">${badge}<span style="flex:1;font-size:.63rem;color:#aaa">${i+1}. ${eh(tit.substring(0,85))}</span>${previewBtn}</div>
      ${preview}
    </div>`;
  }).join('');
  out.innerHTML=`
    <div class="ai-out-label">Canasta — ${canasta.length} art. · ${totalChars.toLocaleString()} chars totales</div>
    ${alertaSin}
    <div style="font-family:var(--mono);margin-bottom:10px">${items}</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="ai-copy-btn" onclick="copyCanasta()" style="flex:1;padding:7px;background:#0a1a0a;border-color:#2d6a4f;color:#4ade80">&#128203; Copiar contexto</button>
    </div>
  `;
}
function togglePreview(id){
  const el=document.getElementById(id);
  if(!el)return;
  el.style.display=el.style.display==='none'?'block':'none';
  const btn=el.previousElementSibling?.querySelector('button');
  if(btn)btn.textContent=el.style.display==='none'?'ver':'ocultar';
}
function copyCanasta(){
  const texto=canasta.join('\n\n---\n\n');
  navigator.clipboard.writeText(texto).then(()=>{
    const btn=document.querySelector('#aiOutput .ai-copy-btn');
    if(!btn)return;const orig=btn.innerHTML;btn.innerHTML='&#10003; Copiado!';setTimeout(()=>btn.innerHTML=orig,2000);
  });
}
function closeAI(){document.getElementById('aiPanel').classList.remove('open');}
function renderAISelected(){const list=document.getElementById('aiSelList');list.innerHTML=selectedArticles.length?selectedArticles.map(a=>`<div class="ai-sel-item">${a.titulo}</div>`).join(''):'<div style="color:#444;font-family:var(--mono);font-size:.68rem">Ninguna nota seleccionada</div>';}
function setAIMode(m,btn){aiMode=m;document.querySelectorAll('.ai-op-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');const ta=document.getElementById('aiPromptTxt');if(m==='custom'){ta.style.display='block';ta.placeholder='Escribi instrucciones para la IA...';document.getElementById('aiPromptLabel').style.display='block';}else{ta.style.display='none';document.getElementById('aiPromptLabel').style.display='none';}}
async function generateAI(){
  if(!canasta.length&&!selectedArticles.length){alert('Primero hace clic en Pasar a IA para cargar la canasta');return;}
  const apiKey=document.getElementById('claudeApiKey').value.trim();
  if(!apiKey){alert('Ingresa tu API Key de Claude');return;}
  const btn=document.getElementById('aiGenBtn');btn.disabled=true;
  const out=document.getElementById('aiOutput');
  out.innerHTML='<div class="ai-out-label">Procesando con IA...</div><div class="loading-dots" style="color:#888;font-family:var(--mono);font-size:.8rem"><span>.</span><span>.</span><span>.</span></div>';
  const texts=canasta.length?canasta:selectedArticles.map(a=>`TITULAR: ${a.titulo}${a.bajada?'\nBAJADA: '+a.bajada:''}`);
  const custom=document.getElementById('aiPromptTxt').value.trim();
  try{
    const r=await fetch(API+'/api/ai',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texts,mode:aiMode,custom,api_key:apiKey})});
    const d=await r.json();
    if(d.detail){out.innerHTML=`<div style="color:var(--accent);font-family:var(--mono)">Error: ${eh(d.detail)}</div>`;btn.disabled=false;return;}
    const text=d.resultado||'Sin respuesta';
    const dbg=d.debug||{};
    const dbgBar=dbg.chars_contexto!=null
      ?`<div style="font-family:var(--mono);font-size:.58rem;color:#444;margin-bottom:8px;padding:4px 6px;border:1px solid #1a1a1a;background:#080808">Contexto enviado: ${(dbg.chars_contexto||0).toLocaleString()} chars · ${dbg.articulos||0} artículos · ${dbg.solo_titulares?'⚠ solo titulares':'✓ texto completo'}</div>`
      :'';
    out.innerHTML=`<div class="ai-out-label">Nota generada</div>${dbgBar}<textarea class="ai-textarea-copy" id="aiTextareaCopy">${escAttr(text)}</textarea><div style="display:flex;gap:5px;margin-top:8px;flex-wrap:wrap"><button class="ai-copy-btn" onclick="copyAI()" style="flex:1;padding:9px 12px;background:#0a1a0a;border-color:#2d6a4f;color:#4ade80;font-size:.7rem">&#128203; Copiar nota</button><button class="ai-copy-btn" onclick="selectAllTextarea()" style="flex:1;padding:9px 12px;font-size:.7rem">&#9638; Seleccionar todo</button><button class="ai-copy-btn" onclick="renderCanasta()" style="padding:9px 12px;background:#0a1028;border-color:#2c4a7c;color:#90b4e8;font-size:.7rem">&#8592; Canasta</button></div>`;
    out.dataset.text=text;
  }catch(e){out.innerHTML=`<div style="color:var(--accent);font-family:var(--mono)">Error: ${e.message}</div>`;}
  btn.disabled=false;
}
function copyAI(){const ta=document.getElementById('aiTextareaCopy');if(ta){navigator.clipboard.writeText(ta.value).catch(()=>{ta.select();document.execCommand('copy');});}}
function selectAllTextarea(){const ta=document.getElementById('aiTextareaCopy');if(ta){ta.select();ta.setSelectionRange(0,99999);}}
function escAttr(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
async function loadFullArticle(url,titulo){
  const modal=document.getElementById('articleModal'),content=document.getElementById('modalContent');
  modal.classList.add('open');content.innerHTML='<div style="padding:40px;text-align:center;font-family:var(--mono);color:var(--muted)">Cargando...</div>';
  try{
    const r=await fetch(API+'/api/article',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const d=await r.json();currentArticleFull=d;
    content.innerHTML=`${d.imagen?`<img class="modal-img" src="${eh(d.imagen)}" onerror="this.style.display='none'">`:''}<div class="modal-title">${eh(d.titulo||titulo)}</div><div class="modal-body">${eh(d.contenido||'Sin contenido.')}</div><button class="modal-add-btn" onclick="addFullToSel()">+ Agregar a IA</button>`;
  }catch(e){content.innerHTML=`<div class="modal-title">${eh(titulo)}</div><div style="color:var(--accent)">Error.</div>`;}
}
function addFullToSel(){if(!currentArticleFull)return;selectedArticles.push({id:'full__'+Date.now(),titulo:currentArticleFull.titulo,bajada:(currentArticleFull.contenido||'').slice(0,300)});updateFloat();closeModal();}
function closeModal(){document.getElementById('articleModal').classList.remove('open');currentArticleFull=null;}
function setStatus(s,t){document.getElementById('sDot').className='dot'+(s?' '+s:'');document.getElementById('sTxt').textContent=t;}
function exportCSV(){if(!scrapedData.length)return;const rows=[['Fuente','Titular','URL','Imagen']];for(const s of scrapedData)for(const n of s.items)rows.push([s.nombre,n.titulo,n.url||'',n.imagen||'']);const csv=rows.map(r=>r.map(c=>`"${(c||'').replace(/"/g,'""')}"`).join(',')).join('\n');dl('monitor.csv','text/csv',csv);}
function exportJSON(){if(!lastResults)return;dl('monitor.json','application/json',JSON.stringify(lastResults,null,2));}
function dl(name,type,content){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([content],{type}));a.download=name;a.click();}
document.getElementById('articleModal').addEventListener('click',function(e){if(e.target===this)closeModal();});
init();
</script>
</body>
</html>

