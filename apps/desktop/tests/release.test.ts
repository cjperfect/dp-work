import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, mkdir, writeFile, readFile, rm } from "node:fs/promises";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import path from "node:path";
import yaml from "js-yaml";
import { mergeRelease, releaseVersion } from "../scripts/merge-release.mjs";

test("release tag must exactly match the stable desktop version", () => {
  assert.equal(releaseVersion("v0.1.0", "0.1.0"), "0.1.0");
  for (const tag of ["v0.2.0", "0.1.0", "v0.1.0-beta.1", "bad"])
    assert.throws(() => releaseVersion(tag, "0.1.0"));
});
async function fixture(root: string) {
  for (const [directory, manifest, extension, arch] of [
    ["mac-arm64", "latest-mac.yml", "zip", "arm64"],
    ["mac-x64", "latest-mac.yml", "zip", "x64"],
    ["win", "latest.yml", "exe", "x64"],
    ["linux", "latest-linux.yml", "AppImage", "x64"],
  ]) {
    const folder = path.join(root, directory);
    await mkdir(folder, { recursive: true });
    const bytes = Buffer.from(directory);
    const name = `DP-Work-0.1.0-${directory}-${arch}.${extension}`;
    await writeFile(path.join(folder, name), bytes);
    await writeFile(
      path.join(folder, manifest),
      yaml.dump({
        version: "0.1.0",
        files: [
          {
            url: name,
            size: bytes.length,
            sha512: createHash("sha512").update(bytes).digest("base64"),
          },
        ],
      }),
    );
  }
}
test("Mac architecture metadata is merged only after every download hash is verified", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "dp-release-"));
  try {
    await fixture(path.join(root, "input"));
    const assets = await mergeRelease(path.join(root, "input"), path.join(root, "output"), "0.1.0");
    const mac = yaml.load(await readFile(path.join(root, "output/latest-mac.yml"), "utf8")) as {
      files: unknown[];
    };
    assert.equal(mac.files.length, 2);
    assert.equal(assets.length, 7);
    const target = assets.find((name: string) => name.endsWith(".exe"))!;
    await writeFile(path.join(root, "input/win", target), "corrupted");
    await assert.rejects(
      mergeRelease(path.join(root, "input"), path.join(root, "bad"), "0.1.0"),
      /大小|SHA-512/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
test("missing platform and incompatible release version cannot produce a published feed", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "dp-release-"));
  try {
    await fixture(path.join(root, "input"));
    await assert.rejects(
      mergeRelease(path.join(root, "input"), path.join(root, "out"), "0.2.0"),
      /版本/,
    );
    await rm(path.join(root, "input/linux"), { recursive: true });
    await assert.rejects(
      mergeRelease(path.join(root, "input"), path.join(root, "out"), "0.1.0"),
      /缺少更新清单/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
