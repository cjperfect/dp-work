import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { migrateProfile, persistencePaths } from "../src/persistence";

test("development and packaged storage use their respective .dp-work roots", () => {
  assert.equal(
    persistencePaths(false, "/users/test", "/workspace").data,
    path.join("/workspace", ".dp-work/data"),
  );
  const packaged = persistencePaths(true, "/users/test", "/workspace");
  assert.equal(packaged.data, path.join("/users/test", ".dp-work/data"));
  assert.equal(packaged.cache, path.join("/users/test", ".dp-work/cache"));
});

test("migration preserves profiles, existing application data, and the legacy source", () => {
  const temporary = mkdtempSync(path.join(tmpdir(), "dp-profile-"));
  try {
    const legacy = path.join(temporary, "legacy");
    const destination = path.join(temporary, "new/data");
    mkdirSync(path.join(legacy, "Partitions/dp-work/Local Storage"), { recursive: true });
    writeFileSync(path.join(legacy, "Partitions/dp-work/Local Storage/test"), "profile-fixture");
    mkdirSync(destination, { recursive: true });
    writeFileSync(path.join(destination, "business.sqlite"), "existing-data");
    migrateProfile(destination, legacy);
    const copied = path.join(destination, "Partitions/dp-work/Local Storage/test");
    assert.equal(readFileSync(copied, "utf8"), "profile-fixture");
    assert.equal(readFileSync(path.join(destination, "business.sqlite"), "utf8"), "existing-data");
    assert.equal(existsSync(path.join(legacy, "Partitions")), true);
    writeFileSync(copied, "newer-data");
    migrateProfile(destination, legacy);
    assert.equal(readFileSync(copied, "utf8"), "newer-data");
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
});
