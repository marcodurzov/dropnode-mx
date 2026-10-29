-- =============================================================
-- DROPNODE MX — schema.sql (v3.6)
-- Ejecutar UNA VEZ en Supabase -> SQL Editor. Es seguro repetirlo.
-- =============================================================

-- Candados anti-duplicado y memoria entre corridas de GitHub Actions
create table if not exists eventos_enviados (
  clave   text primary key,
  detalle text,
  ts      timestamptz default now()
);

-- Histórico de cierres diarios (ahorro acumulado semana/mes/total)
create table if not exists resumenes_hist (
  fecha     text primary key,          -- YYYY-MM-DD
  ahorro    numeric default 0,
  n_alertas int default 0,
  errores   int default 0,
  mejor     text,
  ts        timestamptz default now()
);

-- Qué fuentes (tiendas) traen productos y cuáles están muertas
create table if not exists fuentes_log (
  id     bigserial primary key,
  fuente text,
  items  int default 0,
  error  text,
  ts     timestamptz default now()
);
create index if not exists fuentes_log_ts on fuentes_log (ts);

-- Comunidad
create table if not exists comunidad_posts (
  message_id bigint primary key,
  tipo       text,
  ts         timestamptz default now()
);
create table if not exists comunidad_msgs (
  id         bigserial primary key,
  ts         timestamp,
  user_id    bigint,
  username   text,
  nombre     text,
  tipo       text,        -- msg | aporte | reply_bot | peticion | nuevo | moderacion
  puntos     int default 0,
  reply_tipo text,
  hora       int,
  dow        int
);
create index if not exists comunidad_msgs_ts   on comunidad_msgs (ts);
create index if not exists comunidad_msgs_user on comunidad_msgs (user_id, tipo);
create table if not exists comunidad_advertencias (
  user_id bigint primary key,
  cuenta  int default 0,
  ultima  timestamptz
);

-- Tablas que ya deberían existir (por si falta alguna)
create table if not exists cola_free (
  id         bigserial primary key,
  item       jsonb,
  score      numeric,
  n_vip      int default 0,
  send_after timestamp,
  enviado    boolean default false,
  created_at timestamptz default now()
);
create table if not exists peticiones (
  id bigserial primary key, texto text not null, user_id bigint, username text, semana int,
  timestamp timestamptz default now(), procesada boolean default false,
  encontrada boolean default false, producto text, producto_url text
);
create table if not exists alertas_temporada (id bigserial primary key, tipo text not null, timestamp timestamptz default now());
create table if not exists cupones_publicados (id bigserial primary key, codigo text unique not null,
  descuento int default 0, origen text, timestamp timestamptz default now());

-- Cola de alertas VIP (salen en ráfagas durante el día)
create table if not exists cola_vip (
  id         bigserial primary key,
  payload    jsonb,
  score      numeric,
  enviado    boolean default false,
  created_at timestamptz default now()
);
create index if not exists cola_vip_pend on cola_vip (enviado, score desc);
alter table cola_vip enable row level security;

-- SEGURIDAD: activa RLS en tablas nuevas y usa la clave service_role
-- (guardada SOLO como secret de GitHub) en lugar de la clave anon.
alter table eventos_enviados enable row level security;
alter table resumenes_hist enable row level security;
alter table fuentes_log enable row level security;
alter table comunidad_posts enable row level security;
alter table comunidad_msgs enable row level security;
alter table comunidad_advertencias enable row level security;
