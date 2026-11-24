import { app } from "electron";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import initSqlJs, { type Database as SqlJsDatabase } from "sql.js";

let db: SqlJsDatabase | null = null;
let dbPath = "";

function migrationsDir(): string {
  const packaged = join(process.resourcesPath ?? "", "migrations");
  if (existsSync(packaged)) return packaged;
  // Dev: apps/desktop/resources/migrations
  const dev = join(app.getAppPath(), "resources", "migrations");
  if (existsSync(dev)) return dev;
  return join(process.cwd(), "resources", "migrations");
}

function persist(): void {
  if (!db || !dbPath) return;
  const data = db.export();
  writeFileSync(dbPath, Buffer.from(data));
}

export async function initDb(): Promise<void> {
  if (db) return;
  // Resolve wasm next to the sql.js package entry
  const sqlEntry = fileURLToPath(import.meta.resolve("sql.js"));
  const sqlDist = join(dirname(sqlEntry), "..", "dist");
  const SQL = await initSqlJs({
    locateFile: (file) => join(sqlDist, file),
  });
  const dir = join(app.getPath("userData"), "db");
  mkdirSync(dir, { recursive: true });
  dbPath = join(dir, "audiorestorer.sqlite");
  if (existsSync(dbPath)) {
    db = new SQL.Database(readFileSync(dbPath));
  } else {
    db = new SQL.Database();
  }
  db.run("PRAGMA foreign_keys = ON;");
  migrate();
  seedModels();
  persist();
}

function getDb(): SqlJsDatabase {
  if (!db) throw new Error("DB not initialized — call initDb() first");
  return db;
}

function migrate(): void {
  const database = getDb();
  database.run(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY,
      applied_at TEXT NOT NULL
    );
  `);
  const applied = new Set<number>();
  const res = database.exec("SELECT version FROM schema_migrations");
  if (res[0]) {
    for (const row of res[0].values) applied.add(Number(row[0]));
  }
  const dir = migrationsDir();
  if (!existsSync(dir)) return;
  const files = readdirSync(dir)
    .filter((f) => /^\d+_.*\.sql$/i.test(f))
    .sort();
  for (const file of files) {
    const version = Number(file.split("_")[0]);
    if (applied.has(version)) continue;
    const sql = readFileSync(join(dir, file), "utf8");
    database.run("BEGIN");
    try {
      database.exec(sql);
      database.run("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", [
        version,
        new Date().toISOString(),
      ]);
      database.run("COMMIT");
    } catch (e) {
      database.run("ROLLBACK");
      throw e;
    }
  }
}

function seedModels(): void {
  const database = getDb();
  const rows: Array<[string, string, string, number, string, string, string | null]> = [
    ["deepfilternet3", "DeepFilterNet3", "mvp", 0, "MIT/Apache-2.0 CLI", "installed", "0.5.6"],
    [
      "demucs",
      "Demucs (optional V2)",
      "v2",
      1,
      "Code MIT; weight license unclear — optional download only",
      "notInstalled",
      null,
    ],
    [
      "audiosr",
      "AudioSR (optional V3)",
      "v3",
      1,
      "Reconstruction model; isolated env; research weights",
      "notInstalled",
      null,
    ],
  ];
  for (const r of rows) {
    database.run(
      `INSERT OR IGNORE INTO models
        (id, name, phase, optional, license_notice, state, version, installed_at, error_message)
       VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)`,
      r,
    );
  }
}

function all(sql: string, params: unknown[] = []): Record<string, unknown>[] {
  const stmt = getDb().prepare(sql);
  stmt.bind(params as never[]);
  const out: Record<string, unknown>[] = [];
  while (stmt.step()) out.push(stmt.getAsObject() as Record<string, unknown>);
  stmt.free();
  return out;
}

function get(sql: string, params: unknown[] = []): Record<string, unknown> | undefined {
  return all(sql, params)[0];
}

export function listProjects() {
  return all("SELECT * FROM projects WHERE status='active' ORDER BY updated_at DESC");
}

export function createProject(name: string, rootPath: string) {
  const now = new Date().toISOString();
  const id = randomUUID();
  getDb().run(
    `INSERT INTO projects (id, name, root_path, status, created_at, updated_at)
     VALUES (?, ?, ?, 'active', ?, ?)`,
    [id, name, rootPath, now, now],
  );
  persist();
  return get("SELECT * FROM projects WHERE id=?", [id]);
}

export function listModels() {
  return all("SELECT * FROM models ORDER BY phase, name");
}

export function getSetting(key: string, fallback: unknown = null) {
  const row = get("SELECT value_json FROM app_settings WHERE key=?", [key]);
  if (!row) return fallback;
  try {
    return JSON.parse(String(row.value_json));
  } catch {
    return fallback;
  }
}

export function setSetting(key: string, value: unknown) {
  getDb().run(
    `INSERT INTO app_settings (key, value_json, updated_at) VALUES (?, ?, ?)
     ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at`,
    [key, JSON.stringify(value), new Date().toISOString()],
  );
  persist();
}

export function schemaVersions(): number[] {
  return all("SELECT version FROM schema_migrations ORDER BY version").map((r) => Number(r.version));
}

export function closeDb(): void {
  if (db) {
    persist();
    db.close();
    db = null;
  }
}
