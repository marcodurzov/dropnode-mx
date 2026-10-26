[HANDOFF.md](https://github.com/user-attachments/files/33979797/HANDOFF.md)
# DropNode MX — HANDOFF (pega este archivo al inicio de una conversación nueva)

> Mantén este archivo en la raíz del repo `marcodurzov/dropnode-mx` y en los archivos del Proyecto de Claude.
> Al cerrar cada sesión, pídele a Claude: "actualiza HANDOFF.md con lo que cambiamos".

## Qué es
Negocio de alertas de ofertas para México en Telegram: canal FREE (@DropNodeMX), canal VIP ($299/mes, LaunchPass) y grupo de COMUNIDAD.
Regla no negociable: NUNCA mencionar automatización en público. Todo es "el equipo de DropNode".

## Reglas de operación (v3.7)
| Regla | Valor | Dónde vive |
|---|---|---|
| VIP | 6:30 AM–11:30 PM; de 11:31 PM a 6:29 AM solo score ≥ 8 | `horarios.py` |
| FREE | 8:00 AM–7:00 PM; nada de 7:01 PM a 7:59 AM | `horarios.py` |
| VIP → FREE | 60 min, siempre por la cola `cola_free`; al free solo pasan ofertas con descuento ≤ 40 % y score < 8; lo demás es solo del VIP. Free: fotos en ~40 % de las alertas; VIP: todas con foto | `horarios.py` (`FREE_MAX_DESCUENTO`, `FREE_BLOQUEA_SCORE`) |
| Cierre FREE | 6:00–7:00 PM, "Mejores precios de hoy" | `resumenes.py` |
| Cierre VIP | 11:00–11:30 PM, con ahorro del día/semana/mes/total | `resumenes.py` |
| Temporadas | calendario por mes (scraper + score + comunidad) | `temporada_calendario.py` |
| Repeticiones | score < 8: 1 vez por producto cada 14 días; score ≥ 8: hasta 3 veces (mín. 4 h entre ellas); se permite repetir si el precio bajó ≥ 15%; otro vendedor = otro producto | `estado.py` (`REP_*`) |

## Hallazgos clave (oct-2026)
- 19-oct-2026: con PROXY_URL (DataImpulse, México) el navegador SÍ lee `/ofertas` (48 tarjetas por página) aunque el HTTP simple por proxy sigue topando con el muro. El scraper de ML usa el proxy solo cuando el intento directo falla; con proxy carga 3 páginas por corrida. Tope: 3 alertas VIP por corrida y 36 por día (`MAX_VIP`, `MAX_VIP_DIA`).
- 15-oct-2026: Mercado Libre bloquea la IP de GitHub incluso con HTTP simple y con navegador sigiloso (Scrapling): todo termina en `/gz/account-verification`. Sin `PROXY_URL` (residencial, México) ML da 0 productos. No hay arreglo solo con código.
- GitHub NO respeta `*/15`: en la práctica corre unas 7 veces al día. Por eso todas las tareas programadas usan VENTANAS de horas (con reintento), y se recomienda un disparador externo (cron-job.org -> workflow_dispatch) cada 15 min.
- Mercado Libre: el navegador de GitHub recibe `/gz/account-verification`. Un repo público (Joharjbe/mercadolibre-mx-scraper) muestra que `/ofertas` se sirve renderizado y se puede leer con HTTP simple (UA de escritorio, pasar por la portada, ritmo lento, parar si hay muro). Implementado en `scraper_ml_http.py`; el navegador queda como respaldo.
- Costco muestra el AHORRO ("-$9,000"), no el precio; Sam's/Costco usan mensualidades: la heurística HTML exige un % visible que cuadre.
- Selectores de Liverpool (de CesarYamadaX/Scrapping): `li.m-product__card`, `p.a-card-price`, `p.a-card-discount` -> `extraer_liverpool` en `scraper_multi.py`.
- Amazon Associates cerró la cuenta `dropnodemx-20` (3 ventas en 180 días no cumplidas, oct-2026): los enlaces de Amazon ya no pagan comisión hasta reaplicar.
- Comunidad con IA (Claude Haiku) opcional: secret `ANTHROPIC_API_KEY`; voz "el equipo"; si preguntan si es persona, responde que es el asistente virtual del equipo.
- Comandos del dueño en privado con el bot: `/status`, `/oferta URL precio_ahora precio_antes nombre`.

## Reglas añadidas el 21-oct-2026
- Plata Card: 1ª promo diaria del free siempre Plata; 2ª Plata 3 de cada 4 días; Nu solo ocasional (`contenido._elegir`).
- Free: descuento ≤ 40 %; "los descuentos de más del 40% son solo del VIP" aparece en alertas y recordatorios.
- Cierres: el resumen FREE/VIP solo se publica si hubo ≥ 3 alertas (o un error de precio / ahorro ≥ $5,000 en el VIP) — `resumenes.MIN_ALERTAS_RESUMEN`. Balance mensual VIP los primeros días del mes.
- ML: verificación contra historial propio (descuento falso si el precio es igual al promedio rastreado de ≥ 7 días; error de precio verificado si ≤ 50 % del promedio; insignia ✅ en el VIP).
- Tiendas bloqueadas: navegador + proxy con tope de 16 páginas/día (`scraper_multi.PROXY_PAGINAS_DIA`). Candidatas nuevas: Best Buy, Office Depot, Home Depot, Cyberpuerta, Suburbia, Sanborns, Claro Shop (el diagnóstico dice cuáles sirven).
- Disparadores externos (cron-job.org, POST a `.../actions/workflows/<archivo>.yml/dispatches` con `{"ref":"main"}`): uno para `bot.yml` cada 15 min y otro para `scraper_ml.yml` cada 30 min de 6:00 a 23:59 (hora México). El token vence el 16-oct-2027.

## Hallazgos con muestras reales (22-oct-2026)
- Coppel: `__NEXT_DATA__` con `price.discountedPrice/salesPrice` (29 ofertas reales en la muestra). Bodega/Walmart: `priceInfo.currentPrice/wasPrice`. Sam's: tarjetas con "precio actual $X · Antes $Y · Ahorra $Z" (se valida precio + ahorro = antes). Elektra renderizado: tarjetas con % visible. Estos extractores ya viven en `scraper_multi.py`.
- Sin datos útiles aún: Costco, Liverpool, Suburbia, Amazon, Sears (las muestras guardan solo la primera página; hace falta una página de listado/ofertas de cada una).
- ML por proxy: `/ofertas?page=1` a veces llega vacía (0), las páginas 2 y 3 traen 48 tarjetas cada una. El filtro de historial descarta ~40 % de lo leído (precio igual al de siempre) y es lo esperado.
- Proxy de tiendas: máx. 2 páginas por tienda por corrida y 16 por día; no se gasta en tiendas con 2+ corridas sin productos.

## Arquitectura
- `bot.yml` (cada 15 min) → `main.py`: cola free, 2 fuentes por corrida, lectura/moderación del grupo, programados.
- `scraper_ml.yml` (cada 30 min) → `github_scraper_ml.py`: Playwright sobre ofertas de ML → VIP directo, free vía cola.
- `estado.py`: Supabase + candados (`eventos_enviados`) — cada corrida es un proceso nuevo, NADA sobrevive en variables globales.
- `scraper_multi.py`: motor para tiendas sin API (JSON-LD, JSON embebido, VTEX, HTML). `diagnostico.py` (workflow manual) dice cuál sirve en cada tienda.
- `scraper_ml_http.py`: ofertas de ML por HTTP (sin navegador); cookies cacheadas entre corridas; proxy solo si hay muro.
- `contenido.py`: promos de Plata Card/Nu (con aviso de referido), temporada, `/oferta` manual. `ia.py`: respuestas con Claude.
- `community_manager.py` v5: bienvenida, /reglas, /pedir, moderación, reacciones, niveles, top semanal, miembro del mes, quizzes, métricas.
- Tablas nuevas: ver `schema.sql`.

## Secrets de GitHub necesarios
TELEGRAM_TOKEN, CHANNEL_FREE_ID, CHANNEL_VIP_ID, GROUP_ID, SUPABASE_URL, SUPABASE_KEY, LAUNCHPASS_LINK, ML_AFFILIATE_ID, AMAZON_TAG, MAKE_WEBHOOK_URL
Nuevos (opcionales pero recomendados): ML_APP_ID, ML_SECRET (token de la API de ML), ADMIN_CHAT_ID (tu ID; escríbele /id al bot en privado), PROXY_URL (anyIP).

## Estado real de las fuentes (diagnósticos del 08 y 09-oct-2026, desde GitHub Actions)
| Fuente | Resultado | Nota |
|---|---|---|
| API de búsqueda de Mercado Libre | 403 aun con token de aplicación | `/sites/MLM/search` no sirve. Sí responden 200 con token: `products/search`, `highlights`, `trends`, `categories`. Ruta nueva: `scraper_ml_catalogo.py` (highlights -> producto -> /items). |
| ML con navegador (Playwright) | 10-oct-2026: ML redirige a `/gz/account-verification` ("ingresa a tu cuenta") a las IPs de GitHub; antes mostraba "Hubo un error accediendo" (1 de 6 corridas sacaba productos) | v4.1: huella de navegador realista (`navegador.py`), 2 intentos directos + 1 con proxy, corre cada 15 min. Solución estable: proxy residencial de pago por GB (PROXY_URL); con proxy solo se cargan 4 páginas y se bloquean imágenes/CSS para gastar poco. |
| ML API catálogo | `highlights` da ids, pero `/products/{id}` y `/sites/MLM/search` dan 403 | Ruta descartada; se quitaron las fuentes que dependían de ella. |
| Sam's, Costco, Liverpool, HEB | los "descuentos" eran mensualidades o montos de ahorro (Costco muestra "-$9,000") | v4.2: la heurística HTML solo acepta un producto si la tarjeta muestra un % de descuento que coincide con los precios; rechaza razones ≈ 4, 6, 9, 10, 12, 18, 24. Puede quedar en 0 hasta afinar selectores con las muestras. |
| Palacio, Elektra, Walmart, Bodega | bloqueadas (403 / reto anti-bot) | Requieren proxy residencial (`PROXY_URL`); aun así no está garantizado. |
| Coppel | timeout (descarta IPs de datacenter) | Igual: proxy. |
| Liverpool | `shoppingapi.liverpool.com.mx` ya no existe; la web carga | Falta afinar selectores con las muestras HTML. |
| Costco, HEB, Sears, Amazon | cargan, 0 productos | Se prueba render con JavaScript; afinar con las muestras HTML (artefacto `muestras`). |

## Verificación antes de cobrar
Corre Actions → "DropNode Diagnóstico". La sección "0) ¿LISTO PARA OPERAR?" (`chequeo.py`) revisa token, permisos del bot, tablas, secrets y lo publicado en 24 h. Debe terminar en "LISTO: sin fallas críticas".
Nota: Playwright debe ser >= 1.49 (en Ubuntu 24.04 la 1.40 no instala navegadores); la instalación del navegador en bot.yml es opcional (`continue-on-error`).

## Pendientes / riesgos conocidos
1. SEGURIDAD: `config.py` v2.0 ya no tiene secretos (lee variables de entorno), pero los valores viejos siguen en el historial de git del repo público. Deben estar revocados: token de Telegram (BotFather), clave anon de Supabase (RLS activado + clave service_role en secrets) y webhook de Make. Marcar aquí cuándo se hizo.
1b. NO hacer el repo privado sin revisar: Actions en repos privados tiene tope de minutos gratis (~2,000/mes) y el bot corre cada 15 min.
2. Confirmar que Railway/Procfile está apagado (si no, doble publicación y conflicto con getUpdates).
3. El bot debe ser ADMIN del grupo (ver mensajes, borrar, silenciar).
4. Correr `diagnostico.yml` y revisar qué tiendas necesitan proxy.
5. Monitor de cupones apagado (`ENABLE_CUPONES=0`): detección poco fiable y menciona "sistema".
6. Fechas de `temporadas.py` (Buen Fin, Hot Sale…) revisarlas cada año.
7. Suscripción VIP pausada: revisar antes de abrir al público.

8. Ideas por evaluar: TikTok Shop, AliExpress (existe un scraper no oficial en `scraper_otros.py`, probablemente bloqueado) y Alibaba (mayoreo B2B, poco compatible con alertas de oferta).
