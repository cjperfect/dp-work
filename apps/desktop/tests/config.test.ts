import assert from "node:assert/strict";
import { test } from "node:test";
import { desktopPort, developmentUrl, isAppUrl } from "../src/config";

test("development windows only load local HTTP pages", () => {
  assert.equal(developmentUrl("http://localhost:3000"), "http://localhost:3000/");
  assert.equal(
    developmentUrl("http://127.0.0.1:3000/knowledge"),
    "http://127.0.0.1:3000/knowledge",
  );
  for (const url of [
    "https://example.com",
    "file:///tmp/index.html",
    "http://localhost.evil.test",
    "http://user:pass@localhost:3000",
  ])
    assert.throws(() => developmentUrl(url));
});

test("navigation and IPC require the exact app origin", () => {
  assert.equal(isAppUrl("http://localhost:3000/knowledge", "http://localhost:3000"), true);
  for (const url of [
    "http://localhost:3001",
    "http://localhost.evil.test:3000",
    "javascript:alert(1)",
    "invalid",
  ])
    assert.equal(isAppUrl(url, "http://localhost:3000"), false);
});

test("desktop origin uses a stable valid port", () => {
  assert.equal(desktopPort(), 34731);
  assert.equal(desktopPort("34732"), 34732);
  for (const value of ["0", "80", "65536", "abc", "1234.5"])
    assert.throws(() => desktopPort(value));
});
