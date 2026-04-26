# 📱 3 FORMAS DE TENER TU MONITOR EN EL CELULAR

PythonAnywhere bloquea los sitios argentinos. Acá tenés **3 alternativas GRATUITAS** que SÍ funcionan con Ole, TyC, Infobae, etc.

---

## 🥇 OPCIÓN 1: RENDER.COM (LA MÁS FÁCIL - 10 minutos)

### ¿Por qué Render?
✅ 100% gratis
✅ Deploy automático
✅ SIN restricciones de URLs
✅ URL permanente
✅ Corre 24/7

### Pasos:

**1. Crear cuenta en GitHub:**
- https://github.com/ → Sign up

**2. Crear repositorio:**
- Click "+" → "New repository"
- Nombre: `monitor-deportivo`
- ✅ Public
- ✅ Add README
- Create repository

**3. Subir archivos:**
- En tu repo: "Add file" → "Upload files"
- Arrastrá estos 4 archivos:
  - `app_render.py`
  - `mobile_fixed.html`
  - `requirements_render.txt`
  - `render.yaml`
- Commit changes

**4. Deploy en Render:**
- https://render.com/ → Sign up with GitHub
- "New +" → "Web Service"
- Conectá tu repo `monitor-deportivo`
- Configurá:
  - Build: `pip install -r requirements_render.txt`
  - Start: `uvicorn app_render:app --host 0.0.0.0 --port $PORT`
  - Instance: **Free**
- Create Web Service

**5. Esperá 3 minutos**
Cuando veas ✓ Live → ¡Listo!

**6. Copiá tu URL**
`https://monitor-deportivo-xxx.onrender.com`

**7. Abrila en tu celular**
Funciona TODO: Ole, TyC, Infobae, tendencias, análisis.

⚠️ **Limitación:** Duerme después de 15 min sin uso. Primer acceso tarda 30-50 seg.

---

## 🥈 OPCIÓN 2: RAILWAY.APP (TAMBIÉN MUY FÁCIL - 10 minutos)

### ¿Por qué Railway?
✅ Gratis ($5 de crédito al mes)
✅ NO duerme (a diferencia de Render)
✅ Más rápido
✅ Deploy desde GitHub

### Pasos:

**1. Mismo repo de GitHub** (del paso anterior)

**2. Deploy en Railway:**
- https://railway.app/ → Start a New Project
- Login with GitHub
- Deploy from GitHub repo
- Seleccioná `monitor-deportivo`

**3. Configurar:**
Railway detecta automáticamente Python y las dependencias.
- Esperá 2-3 minutos
- Click en "Settings" → "Generate Domain"

**4. Abrí tu URL**
`https://monitor-deportivo-production.up.railway.app`

✅ **Ventaja:** NO duerme, siempre rápido

---

## 🥉 OPCIÓN 3: FLY.IO (PARA MÁS CONTROL - 15 minutos)

### ¿Por qué Fly.io?
✅ Gratis para 3 apps
✅ Muy rápido (edge computing)
✅ Más control técnico

### Pasos:

**1. Instalar Fly CLI:**
```bash
# En tu PC (Mac/Linux)
curl -L https://fly.io/install.sh | sh

# Windows (PowerShell)
iwr https://fly.io/install.ps1 -useb | iex
```

**2. Login:**
```bash
fly auth signup
# o si ya tenés cuenta:
fly auth login
```

**3. Crear app:**
```bash
cd /ruta/a/tus/archivos
fly launch
```

Respondé:
- App name: `monitor-deportivo` (o el que quieras)
- Region: `ezeiza` (Buenos Aires) o `gru` (São Paulo)
- Database: **No**
- Deploy: **Yes**

**4. Esperá el deploy**
Tu app queda en: `https://monitor-deportivo.fly.dev`

---

## 🎯 ¿CUÁL ELEGIR?

| Feature | Render | Railway | Fly.io |
|---------|---------|---------|--------|
| Facilidad | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| Velocidad (dormida) | 30-50s | Instant ⚡ | Instant ⚡ |
| Setup | Browser | Browser | Terminal |
| Gratis para siempre | ✅ | ✅ ($5/mes) | ✅ |

**Mi recomendación:**
1. **Render** si querés lo MÁS fácil (todo desde el navegador)
2. **Railway** si querés que sea rápido siempre
3. **Fly.io** si te gusta la terminal y querés más control

---

## 📥 ARCHIVOS QUE NECESITÁS

Ya los descargaste:
- ✅ `app_render.py` - Backend con TODO tu código original
- ✅ `mobile_fixed.html` - Frontend móvil optimizado
- ✅ `requirements_render.txt` - Dependencias Python
- ✅ `render.yaml` - Config automática

**Los mismos archivos sirven para las 3 opciones.**

---

## ✨ LO QUE VAS A TENER

✅ **13 fuentes argentinas**: Ole, ESPN, TyC, Infobae, La Nación, TN, Clarín, El Gráfico, Doble Amarilla, Bolavip, La Voz, La Capital, Ole Últimas

✅ **10 fuentes internacionales**: AS, Marca, Mundo Deportivo, Sport, Globo Esporte, BBC, Goal, L'Equipe, La Tercera, Referí

✅ **~250 noticias** por scraping

✅ **Tendencias** automáticas

✅ **Análisis Olé vs Todos**

✅ **Lector de artículos completos**

---

## 🚀 EMPEZÁ CON RENDER

Es la opción más fácil. **Seguí la guía de arriba** y en 10 minutos lo tenés funcionando.

¿Problemas? Mandame screenshot y te ayudo.
