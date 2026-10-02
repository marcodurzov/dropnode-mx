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
| VIP → FREE | 60 min, siempre por la cola `cola_free`; las 🔴 exclusivas no pasan (solo salen en el resumen) | `horarios.py` (`EXCLUSIVOS_PASAN_AL_FREE`) |
| Cierre FREE | 6:00–7:00 PM, "Mejores precios de hoy" | `resumenes.py` |
| Cierre VIP | 11:00–11:30 PM, con ahorro del día/semana/mes/total | `resumenes.py` |
| Temporadas | calendario por mes (scraper + score + comunidad) | `temporada_calendario.py` |
| Repeticiones | score < 8: 1 vez por producto cada 14 días; score ≥ 8: hasta 3 veces (mín. 4 h entre ellas); se permite repetir si el precio bajó ≥ 15%; otro vendedor = otro producto | `estado.py` (`REP_*`) |

## Arquitectura
- `bot.yml` (cada 15 min) → `main.py`: cola free, 2 fuentes por corrida, lectura/moderación del grupo, programados.
- `scraper_ml.yml` (cada 30 min) → `github_scraper_ml.py`: Playwright sobre ofertas de ML → VIP directo, free vía cola.
- `estado.py`: Supabase + candados (`eventos_enviados`) — cada corrida es un proceso nuevo, NADA sobrevive en variables globales.
- `scraper_multi.py`: motor para tiendas sin API (JSON-LD, JSON embebido, VTEX, HTML). `diagnostico.py` (workflow manual) dice cuál sirve en cada tienda.
- `community_manager.py` v5: bienvenida, /reglas, /pedir, moderación, reacciones, niveles, top semanal, miembro del mes, quizzes, métricas.
- Tablas nuevas: ver `schema.sql`.

## Secrets de GitHub necesarios
TELEGRAM_TOKEN, CHANNEL_FREE_ID, CHANNEL_VIP_ID, GROUP_ID, SUPABASE_URL, SUPABASE_KEY, LAUNCHPASS_LINK, ML_AFFILIATE_ID, AMAZON_TAG, MAKE_WEBHOOK_URL
Nuevos (opcionales pero recomendados): ML_APP_ID, ML_SECRET (token de la API de ML), ADMIN_CHAT_ID (tu ID; escríbele /id al bot en privado), PROXY_URL (anyIP).

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
