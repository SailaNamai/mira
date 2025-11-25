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
  smart_plug1_name    TEXT,                                -- Tasmota Smart Plug Location
  smart_plug1_ip      TEXT,                                -- Tasmota Smart Plug IP
  smart_plug2_name    TEXT,                                -- Tasmota Smart Plug Location
  smart_plug2_ip      TEXT,                                -- Tasmota Smart Plug IP
  smart_plug3_name    TEXT,                                -- Tasmota Smart Plug Location
  smart_plug3_ip      TEXT,                                -- Tasmota Smart Plug IP
  smart_plug4_name    TEXT,                                -- Tasmota Smart Plug Location
  smart_plug4_ip      TEXT,                                -- Tasmota Smart Plug IP
  user_name           TEXT,                                -- User name
  user_birthday       TEXT,                                -- User birthday
  location_city       TEXT,                                -- City
  location_latitude   TEXT,                                -- Latitude
  location_longitude  TEXT,                                -- Longitude
  schedule_monday     TEXT,                                -- Monday
  schedule_tuesday    TEXT,                                -- Tuesday
  schedule_wednesday  TEXT,                                -- Wednesday
  schedule_thursday   TEXT,                                -- Thursday
  schedule_friday     TEXT,                                -- Friday
  schedule_saturday   TEXT,                                -- Saturday
  schedule_sunday     TEXT,                                -- Sunday
  additional_info     TEXT                                 -- Additional Info
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
  energy_kcal_serving       INT,
  carbohydrates_100g        INT,
  carbohydrates_serving     INT,
  fat_100g                  INT,
  fat_serving               INT,
  proteins_100g             INT,
  proteins_serving          INT,

  last_update TEXT DEFAULT (strftime('%Y-%m-%d at %H:%M','now','localtime')) -- timestamp of insertion, so we only query after n amount of days
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
  the_date          TEXT DEFAULT (strftime('%Y-%m-%d', 'now')),
  kcal_total        INT,
  carbs_total       INT,
  fat_total         INT,
  protein_total     INT
);