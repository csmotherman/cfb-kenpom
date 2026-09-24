// Run: npm test   (node's built-in runner with native TypeScript stripping)
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {
  computeSample, verifyParity, parseExclusions, serializeExclusions, CUSTOM_ADJUSTED_KEYS,
} from "../lib/custom-sample.ts";

const fixture = JSON.parse(fs.readFileSync(new URL("./fixtures/custom-sample-2026.json", import.meta.url), "utf8"));
const { official, teams, meta } = fixture;
const bySlug = (slug) => {
  const team = Object.values(teams).find((t) => t.slug === slug);
  return { meta, team: structuredClone(team) };
};
const gameId = (data, opponent) => data.team.games.find((g) => g.o === opponent).g;
const ids = (data) => data.team.games.map((g) => g.g);
const without = (data, ...excluded) => new Set(ids(data).filter((id) => !excluded.includes(id)));

test("all games selected reproduces every official adjusted value (2026 Michigan, Iowa, Northwestern)", () => {
  for (const slug of ["michigan", "iowa", "northwestern"]) {
    const data = bySlug(slug);
    const result = computeSample(data, null);
    const row = official[slug].row;
    let checked = 0;
    for (const key of CUSTOM_ADJUSTED_KEYS) {
      const tolerance = key === "offFin" || key === "defFin" ? 0.0101 : 0.000101;
      if (result.adjusted[key] === null || result.adjusted[key] === undefined) {
        assert.ok(row[key] === null || row[key] === undefined, `${slug} ${key}: expected null`);
        continue;
      }
      assert.ok(Math.abs(result.adjusted[key] - row[key]) <= tolerance, `${slug} ${key}: ${result.adjusted[key]} vs ${row[key]}`);
      checked += 1;
    }
    assert.ok(checked >= 30, `${slug}: only ${checked} adjusted keys compared`);
    assert.equal(verifyParity(data, row).ok, true);
  }
});

test("all games selected reproduces every official raw count exactly", () => {
  for (const slug of ["michigan", "iowa", "northwestern"]) {
    const data = bySlug(slug);
    const raw = computeSample(data, null).raw;
    const expected = official[slug].rawSums;
    let compared = 0;
    for (const [field, value] of Object.entries(raw)) {
      if (!(field in expected)) continue;
      assert.ok(Math.abs(value - expected[field]) < 1e-6, `${slug} ${field}: ${value} vs ${expected[field]}`);
      compared += 1;
    }
    assert.ok(compared >= 35, `${slug}: only ${compared} raw fields compared`);
  }
});

test("removing a game changes the numbers; adding it back restores the original exactly", () => {
  const data = bySlug("michigan");
  const all = computeSample(data, null);
  const wmu = gameId(data, "Western Michigan");
  const trimmed = computeSample(data, without(data, wmu));
  assert.equal(trimmed.included, 2);
  assert.notDeepEqual(trimmed.raw, all.raw);
  assert.notEqual(trimmed.adjusted.epaAdj, all.adjusted.epaAdj);
  assert.notEqual(trimmed.adjusted.offExp, all.adjusted.offExp);
  const restored = computeSample(data, new Set(ids(data)));
  assert.deepEqual(restored, all);
});

test("Michigan without Western Michigan and Iowa without Northern Iowa are independent", () => {
  const michigan = bySlug("michigan");
  const iowa = bySlug("iowa");
  const wmu = gameId(michigan, "Western Michigan");
  const uni = gameId(iowa, "Northern Iowa");
  const excluded = { michigan: [wmu], iowa: [uni] };
  const pick = (slug, data) => computeSample(data, without(data, ...(excluded[slug] ?? [])));
  const first = { michigan: pick("michigan", michigan), iowa: pick("iowa", iowa) };
  // Recompute in the opposite order and with the other team's sample changed: nothing leaks.
  const iowaOnlyAll = computeSample(iowa, null);
  const michiganAgain = pick("michigan", michigan);
  assert.deepEqual(michiganAgain, first.michigan);
  assert.equal(first.michigan.included, 2);
  assert.equal(first.iowa.included, 2);
  assert.notDeepEqual(first.iowa, iowaOnlyAll);
  assert.equal(first.michigan.raw.yppDen < computeSample(michigan, null).raw.yppDen, true);
  assert.equal(first.iowa.raw.yppDen < iowaOnlyAll.raw.yppDen, true);
});

test("selection is by game, not week: both excluded games in the same site-week still work independently", () => {
  const michigan = bySlug("michigan");
  const iowa = bySlug("iowa");
  const wmu = michigan.team.games.find((g) => g.o === "Western Michigan");
  const uni = iowa.team.games.find((g) => g.o === "Northern Iowa");
  const baseline = {
    michigan: computeSample(michigan, without(michigan, wmu.g)),
    iowa: computeSample(iowa, without(iowa, uni.g)),
  };
  // Force both games into Week 1 -- the same week as Iowa's other week-1 game.
  wmu.w = 1;
  uni.w = 1;
  assert.equal(wmu.w, uni.w);
  const sameWeek = {
    michigan: computeSample(michigan, without(michigan, wmu.g)),
    iowa: computeSample(iowa, without(iowa, uni.g)),
  };
  assert.deepEqual(sameWeek, baseline);
  // Michigan drops its Week 1 game while Iowa KEEPS its Week 1 games (only Northern Iowa goes).
  const iowaWeek1 = iowa.team.games.filter((g) => g.w === 1).map((g) => g.g);
  assert.ok(iowaWeek1.length >= 2, "Iowa should have two games labelled Week 1 now");
  const iowaKept = computeSample(iowa, without(iowa, uni.g));
  assert.equal(iowaKept.included, iowa.team.games.length - 1);
  assert.equal(sameWeek.michigan.included, michigan.team.games.length - 1);
});

test("excluding an FCS opponent leaves the ridge-fit edges alone but changes raw stats and the blend's games played", () => {
  const iowa = bySlug("iowa");
  const all = computeSample(iowa, null);
  const uni = gameId(iowa, "Northern Iowa");
  const noFcs = computeSample(iowa, without(iowa, uni));
  assert.equal(noFcs.adjusted.offExp, all.adjusted.offExp);
  assert.equal(noFcs.adjusted.defHavoc, all.adjusted.defHavoc);
  assert.notEqual(noFcs.raw.yppDen, all.raw.yppDen);
  assert.notEqual(noFcs.adjusted.epaAdj, all.adjusted.epaAdj);
});

test("an empty selection is safe", () => {
  const data = bySlug("michigan");
  const none = computeSample(data, new Set());
  assert.equal(none.included, 0);
  assert.equal(none.total, 3);
  assert.ok(Object.values(none.adjusted).every((v) => v === null));
});

test("verifyParity fails closed when the artifact disagrees with the official row", () => {
  const data = bySlug("michigan");
  const row = { ...official.michigan.row, epaAdj: official.michigan.row.epaAdj + 0.5 };
  assert.equal(verifyParity(data, row).ok, false);
});

test("exclusion URL round trip", () => {
  const value = serializeExclusions({ michigan: ["401856700"], iowa: ["401856800", "401856801"], empty: [] });
  assert.equal(value, "michigan:401856700;iowa:401856800.401856801");
  assert.deepEqual(parseExclusions(value), { michigan: ["401856700"], iowa: ["401856800", "401856801"] });
  assert.deepEqual(parseExclusions("bad slug:1;ohio-state:notanid;texas:401856900"), { texas: ["401856900"] });
});
