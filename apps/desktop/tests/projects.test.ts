import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, mkdir, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { registerProject } from "../src/main/storage/projects";

test("selected folders persist, deduplicate and stay separate for each account", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "dp-project-test-"));
  try {
    const folder = path.join(root, "project"),
      data = path.join(root, "data");
    await mkdir(folder);
    const first = await registerProject(data, folder, 1, "device-one");
    const second = await registerProject(data, folder, 1, "device-one");
    assert.equal(first.id, second.id);
    const other = await registerProject(data, folder, 2, "device-two");
    assert.notEqual(first.id, other.id);
    const registry = JSON.parse(await readFile(path.join(data, "projects.json"), "utf8"));
    assert.equal(registry.projects[first.id].owner_id, 1);
    assert.equal(Object.keys(registry.projects).length, 2);
    assert.equal(first.name, "project");
    await assert.rejects(registerProject(data, path.join(root, "missing"), 1, "device-one"));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
