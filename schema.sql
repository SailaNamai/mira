-- schema.sql

-- ACTION
CREATE TABLE IF NOT EXISTS intent_action (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,   -- unique identifier
  user_msg            TEXT,                                -- what the user entered
  assistant_resp      TEXT,                                -- raw assistant response
  command             TEXT,                                -- what mira determined should be done
  created_at TEXT DEFAULT (strftime('%Y-%m-%d at %H:%M','now','localtime')) -- timestamp of insertion
);

-- CHAT
CREATE TABLE IF NOT EXISTS intent_chat (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,   -- unique identifier
  conv_id             INTEGER,                             -- unique chat id
  user_msg            TEXT,                                -- the user query
  response            TEXT,                                -- mira's response
  think               TEXT,                                -- reasoning process
  token_cost          INTEGER,                             -- token cost query+response
  created_at TEXT DEFAULT (strftime('%Y-%m-%d at %H:%M','now','localtime')) -- timestamp of insertion
);

-- Wikipedia
CREATE TABLE IF NOT EXISTS wikipedia (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,   -- unique identifier
  user_msg            TEXT,                                -- the user query
  search_term         TEXT,                                -- mira's response
  title               TEXT,                                -- matched title
  description         TEXT,                                -- short description
  url                 TEXT,                                -- feeling lucky URL
  created_at TEXT DEFAULT (strftime('%Y-%m-%d at %H:%M','now','localtime')) -- timestamp of insertion
);

-- Settings
CREATE TABLE IF NOT EXISTS settings (
  id                  INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton row
  stt                 TEXT,
  stt_mode            TEXT,
  llm                 TEXT,
  llm_mode            TEXT,
  llm_vl              TEXT,
  llm_vl_mode         TEXT,
  tts                 TEXT,
  tts_mode            TEXT,
  smart_plug1_name    TEXT,
  smart_plug1_ip      TEXT,
  smart_plug2_name    TEXT,
  smart_plug2_ip      TEXT,
  smart_plug3_name    TEXT,
  smart_plug3_ip      TEXT,
  smart_plug4_name    TEXT,
  smart_plug4_ip      TEXT,
  user_name           TEXT,
  user_birthday       TEXT,
  location_city       TEXT,
  location_latitude   TEXT,
  location_longitude  TEXT,
  schedule_monday     TEXT,
  schedule_tuesday    TEXT,
  schedule_wednesday  TEXT,
  schedule_thursday   TEXT,
  schedule_friday     TEXT,
  schedule_saturday   TEXT,
  schedule_sunday     TEXT,
  additional_info     TEXT
);

-- Nutrition Items
CREATE TABLE IF NOT EXISTS nutrition_items (
  id                        INTEGER PRIMARY KEY AUTOINCREMENT,
  barcode                   TEXT,
  product_name              TEXT,
  quantity                  TEXT,                                -- how much product
  product_quantity          INT,                                 -- how many single items
  serving_size              TEXT,
  energy_kcal_100g          INT,
  carbohydrates_100g        INT,
  fat_100g                  INT,
  proteins_100g             INT,
  last_update TEXT DEFAULT (strftime('%Y-%m-%d at %H:%M','now','localtime')) -- timestamp of insertion
);

-- Nutrition user values
CREATE TABLE IF NOT EXISTS nutrition_user_values (
  id                  INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton row
  kcal_allowed        INT,
  carbs_allowed       INT,
  fat_allowed         INT,
  protein_allowed     INT
);

-- nutrition intake per day
CREATE TABLE IF NOT EXISTS nutrition_intake (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  product_name      TEXT,
  the_date          TEXT DEFAULT (strftime('%Y-%m-%d', 'now')),
  quantity_consumed INT,
  kcal_consumed     INT,
  carbs_consumed    INT,
  fat_consumed      INT,
  protein_consumed  INT
);