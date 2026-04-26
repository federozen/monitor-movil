from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import re, unicodedata, math, random, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

app = FastAPI(title="NewsRoom Scraper API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

from fastapi.responses import FileResponse

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

print("✅ Backend listo")

