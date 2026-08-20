/**
 * PACOTE DS — markdownToHtml helper.
 * Run with: node --test frontend/src/utils/markdown.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { markdownToHtml } from "./markdown.js";

describe("markdownToHtml", () => {
  it("returns empty string for blank input", () => {
    assert.equal(markdownToHtml(""), "");
    assert.equal(markdownToHtml(null), "");
  });

  it("renders headings and bold", () => {
    const html = markdownToHtml("# Título\n\n**negrito**");
    assert.match(html, /<h1/);
    assert.match(html, /<strong>negrito<\/strong>/);
  });
});
