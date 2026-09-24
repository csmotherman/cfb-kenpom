import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { sumExploratory, verifyExploratoryParity } from "../lib/exploratory-sample.ts";

const fixture = JSON.parse(fs.readFileSync(new URL("./fixtures/exploratory-sample-2025.json", import.meta.url), "utf8"));
const get = (slug) => ({ meta: fixture.meta, team: structuredClone(Object.values(fixture.teams).find((t) => t.slug === slug)) });
const id = (data, opp) => data.team.games.find((g) => g.o === opp).g;
const without = (data, ...drop) => new Set(data.team.games.map((g) => g.g).filter((x) => !drop.includes(x)));

test("all games selected reproduces the official Exploratory counts (2025 Michigan, Iowa)", () => {
  for (const slug of ["michigan", "iowa"]) {
    const data = get(slug);
    const { counts, included, total } = sumExploratory(data, null);
    assert.equal(included, total);
    assert.ok(data.meta.fields.length >= 70);
    for (const field of data.meta.fields) {
      assert.ok(Math.abs(counts[field] - (fixture.official[slug][field] ?? 0)) < 1e-4, `${slug} ${field}`);
    }
    assert.equal(verifyExploratoryParity(data, fixture.official[slug]), true);
  }
});

test("dropping a game changes only that team's counts; restoring it is exact", () => {
  const michigan = get("michigan");
  const iowa = get("iowa");
  const all = sumExploratory(michigan, null);
  const noNM = sumExploratory(michigan, without(michigan, id(michigan, "New Mexico")));
  assert.equal(noNM.included, all.total - 1);
  assert.ok(noNM.counts.seriesOpportunities < all.counts.seriesOpportunities);
  assert.deepEqual(sumExploratory(michigan, new Set(michigan.team.games.map((g) => g.g))), all);
  // Iowa's sample is computed from Iowa's games only and is unaffected by Michigan's choice.
  const iowaAll = sumExploratory(iowa, null);
  const iowaDrop = sumExploratory(iowa, without(iowa, iowa.team.games[0].g));
  assert.deepEqual(sumExploratory(iowa, null), iowaAll);
  assert.ok(iowaDrop.included === iowaAll.total - 1);
});

test("games are selected by game id, not week; empty selection is safe; parity fails closed", () => {
  const michigan = get("michigan");
  michigan.team.games.forEach((g) => { g.w = 5; }); // every game in one site-week
  const a = sumExploratory(michigan, without(michigan, michigan.team.games[0].g, michigan.team.games[3].g));
  assert.equal(a.included, michigan.team.games.length - 2);
  assert.equal(sumExploratory(michigan, new Set()).included, 0);
  assert.equal(verifyExploratoryParity(michigan, { ...fixture.official.michigan, seriesOpportunities: 1 }), false);
});
