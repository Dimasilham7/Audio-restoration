import initSqlJs from "sql.js";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const desktop = join(__dirname, "..");
const migrations = join(desktop, "resources", "migrations");
const sqlEntry = fileURLToPath(import.meta.resolve("sql.js"));
const sqlDist = join(dirname(sqlEntry), "..", "dist");

const SQL = await initSqlJs({
  locateFile: (f) => join(sqlDist, f),
});
const db = new SQL.Database();
db.run("PRAGMA foreign_keys = ON;");

const files = readdirSync(migrations)
  .filter((f) => /^\d+_.*\.sql$/i.test(f))
  .sort();
if (!files.length) throw new Error("no migrations");

for (const file of files) {
  const sql = readFileSync(join(migrations, file), "utf8");
  db.exec(sql);
  const version = Number(file.split("_")[0]);
  db.run("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", [
    version,
    new Date().toISOString(),
  ]);
}

db.run(
  `INSERT INTO projects (id, name, root_path, status, created_at, updated_at)
   VALUES ('p1', 'Test', 'D:/tmp/ar', 'active', '2026-01-01', '2026-01-01')`,
);
const rows = db.exec("SELECT name FROM projects");
const versions = db.exec("SELECT version FROM schema_migrations");
console.log(
  JSON.stringify(
    {
      ok: true,
      migrationFiles: files,
      versions: versions[0]?.values?.flat() ?? [],
      project: rows[0]?.values?.[0]?.[0],
      wasm: existsSync(join(sqlDist, "sql-wasm.wasm")),
    },
    null,
    2,
  ),
);
