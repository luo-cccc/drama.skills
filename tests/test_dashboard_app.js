"use strict";

const assert = require("node:assert/strict");
const app = require("../skills/short-drama/assets/dashboard/app.js");

assert.equal(app.creatorTitle("  测试项目  "), "测试项目");
assert.equal(app.creatorTitle("  "), "未命名短剧");
assert.equal(app.creatorSection("剧集/EP001/screenplay.md"), "story");
assert.equal(app.creatorSection("剧集/EP001/storyboard/shots.jsonl"), "storyboard");
assert.equal(app.creatorSection(".short-drama/state.json"), null);
assert.equal(app.creatorEditable({ path: "notes.json", writable: true }), true);
assert.equal(app.creatorEditable({ path: "clip.mp4", writable: true }), false);
assert.equal(app.savedContentIsCurrent("same", "same"), true);
assert.equal(app.savedContentIsCurrent("old", "new"), false);
assert.equal(
  app.friendlyFailure("file changed since it was opened"),
  "这份内容在别处已经更新，请重新打开后再修改。",
);

const rows = app.readJsonLines('{"id":1}\n{"value":NaN}\n');
assert.deepEqual(rows[0].record, { id: 1 });
assert.equal(rows[1].line, 2);
assert.equal(typeof rows[1].error, "string");

const episodes = app.collectEpisodes([
  { path: "剧集/EP010/screenplay.md" },
  { path: "剧集/EP002/beats.jsonl" },
]);
assert.deepEqual(episodes.map((episode) => episode.id), ["EP002", "EP010"]);

console.log("dashboard app tests passed");
