# High-Elo Build / Rune Suggestions — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-06-26-build-rune-suggestions-design.md`
**Date:** 2026-06-26

## Global Constraints

- **Sample floor:** `BUILD_SAMPLE_FLOOR = 30` on `n_samples` (= spell-pair count = games sampled),
  mirroring `BENCHMARK_SAMPLE_FLOOR` in `main.py`.
- **Coherent rune page:** rank the *whole-page signature*, never independent rune popularity. Encode
  exactly `"{primaryStyle}|{keystone},{p1},{p2},{p3}|{subStyle}|{s1},{s2}|{off},{flex},{def}"`.
  Validate selection counts (primary ≥4, sub ≥2, stats present) before encoding; return `None` on
  any malformed page. Match style entries by `description` (`"primaryStyle"`/`"subStyle"`), fall
  back to index order if `description` missing.
- **Spell signature:** order-normalized `f"{min(s1,s2)},{max(s1,s2)}"`; `None` if either missing/0.
- **Items:** record `item0..item5` only (exclude `item6` trinket slot); drop `0`; dedupe per
  participant. Store raw ids; filter at read.
- **Core-item filter (read time, LCU meta):** keep iff `priceTotal >= 1100 AND to == [] AND
  categories contains neither "Consumable" nor "Trinket"`.
- **Icon proxy:** sidecar `/lcu-image?path=...` — reject any `path` not starting with
  `/lol-game-data/assets` (400 / SSRF guard); lowercase the path before requesting; basic auth +
  `verify=False`. Backend emits relative `icon_url` (`/lcu-image?path=<url-encoded>`); renderer
  wraps with `sidecarUrl()`.
- **No new Riot calls, no timeline.** Build data comes from the participant JSON the harvester
  already fetches.
- **DB layer stays pure** (sync, sqlite-testable, no LCU/HTTP). LCU resolution + filtering live in
  the view/endpoint layer.
- **Never 500 the champ-select poll:** wrap the suggested-build assembly in try/except → `status:
  "insufficient"` on any LCU hiccup (mirrors `_process_session`'s defensive `except`).
- **Reuse `BenchmarkHarvestedMatch` dedup** — record builds + metrics in the same `_accumulate_match`
  pass.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## Tasks

### Task 1 — Schema + DB helpers
**Files:** `sidecar/database.py`, `sidecar/tests/test_build_db.py`.
Add `BuildSample` model (mirror `Benchmark`, lines 73-82). Add:
- `record_build_samples(db, champion, role, target_tier, patch, build: dict)` — query-or-create +
  increment `count`, single commit (mirror `record_benchmark_samples`). Bumps one row per item id,
  one per rune_page signature, one per spells signature.
- `get_build_suggestions(db, champion, role, target_tier) -> dict` — cross-patch `Counter` sum
  (mirror `get_benchmarks`); returns `{n_samples, items: [(id:int, count)] desc raw, rune_page:
  (sig, count)|None, spells: (sig, count)|None}`. `n_samples` = sum of spells counts (fallback to
  rune_page counts if spells empty).
- `most_sampled_role(db, champion, target_tier) -> str|None` — role with max `kind="spells"` count.

**Tests:** per-element counts; cross-patch sum; champion/role/tier isolation; `n_samples` == spell
count; `most_sampled_role` picks max; empty → `n_samples==0`, `rune_page is None`.

### Task 2 — Extractor + signatures
**Files:** new `sidecar/build_extractor.py`, `sidecar/tests/test_build_extractor.py`.
- `extract_participant_build(p) -> {"items": list[int], "rune_page": str|None, "spells": str|None}`.
- `encode_rune_signature(p)` / `decode_rune_signature(sig) -> {primary_style, primary_perks[4],
  sub_style, sub_perks[2], stat_shards[3]}` (note: primary_perks includes the keystone as [0]).
- `encode_spell_signature(p)` / `decode_spell_signature(sig) -> [int, int]`.
All decoders pure/total. Defensive perks read per Global Constraints.

**Tests:** rune signature round-trips; spell pair order-normalized (`(14,4)→"4,14"`); item0..5
captured, item6 + zeros excluded, dupes deduped; malformed perks (missing styles, short selections)
→ `rune_page None`; missing spells → `spells None`.

### Task 3 — Harvester wiring
**Files:** `sidecar/benchmark_harvester.py`, `sidecar/tests/test_build_harvester.py`.
In `_accumulate_match` (lines 40-47) read `champion = p["championName"]` and call
`record_build_samples(db, champion, role, target_tier, patch, extract_participant_build(p))` inside
the existing `for p in info["participants"]` loop, after the benchmark call. Keep the
`if not role: continue` guard.

**Tests** (extend the `_match` helper with `championName`, `item0..6`, `perks`, `summoner1Id/2Id`):
run_harvest → both benchmark and build rows exist; re-harvest same match id → counts unchanged
(dedup); unknown-role participant skipped for builds too.

### Task 4 — LcuClient asset methods + bytes fetch
**Files:** `sidecar/lcu_client.py`, `sidecar/tests/test_lcu_assets.py`.
Mirror `get_champion_name` (lines 50-75). Lazy id→meta caches:
- `get_items()` → `dict[int, {name, iconPath, priceTotal, to, categories}]`
  (`/lol-game-data/assets/v1/items.json`)
- `get_perks()` → `dict[int, {name, iconPath}]` (`/lol-game-data/assets/v1/perks.json`; covers
  keystones, minor runes, and stat shards)
- `get_perk_styles()` → `dict[int, {name, iconPath}]` (`/lol-game-data/assets/v1/perkstyles.json`;
  payload is `{styles:[...]}`)
- `get_summoner_spells()` → `dict[int, {name, iconPath}]`
  (`/lol-game-data/assets/v1/summoner-spells.json`)
- `get_asset_bytes(path) -> (bytes, str)|None` — lowercase path, basic auth, `verify=False`, returns
  `(content, content_type)`.

Defensive: skip entries missing `id`/`name`; default missing `iconPath`→`None`,
`priceTotal`→`0`, `to`/`categories`→`[]`.

**Tests** (httpx mock like `test_lcu_client.py`): each builds id→meta map; cache populated once
(second call no new HTTP); missing-name entries skipped; `get_asset_bytes` returns
`(content, content_type)` and lowercases path; no-lockfile → `None`.

### Task 5 — Build view + item filter
**Files:** new `sidecar/build_view.py`, `sidecar/tests/test_build_view.py`.
- `is_core_item(meta) -> bool` per the core-item filter constraint.
- `_icon_url(icon_path) -> str` — `"/lcu-image?path=" + urllib.parse.quote(icon_path)`.
- `async _assemble_suggested_build(lcu, raw, role, target_tier) -> dict` — if `raw["n_samples"] <
  BUILD_SAMPLE_FLOOR` → `{status:"insufficient", role, target_tier, n_samples, items:[], runes:None,
  spells:[]}`. Else resolve items (filter core, top 6, `{id,name,icon_url,count}`), the single rune
  page (decode → resolve keystone+primary+sub+styles+shards), spells (decode → resolve pair).
  `status:"ready"`. Wrap whole body in try/except → `insufficient` on any LCU error.
  (`BUILD_SAMPLE_FLOOR` may live in `build_view.py` and be imported by `main.py`, or vice-versa —
  implementer's choice, single definition.)

**Tests:** `is_core_item` keeps a completed item + Berserker's Greaves, drops basic Boots /
component / pot / trinket; below floor → `insufficient`; above floor with mock LCU → resolved
names/icon_urls, items truncated to 6, runes nested correctly, `icon_url` URL-encoded and
`/lcu-image?path=` prefixed; LCU exception → `insufficient`.

### Task 6 — Endpoint + monitor role capture + image proxy
**Files:** `sidecar/main.py`, `sidecar/champ_select_monitor.py`, `sidecar/tests/test_build_api.py`,
update `sidecar/tests/test_champ_select_monitor.py`.
- Monitor: in `_process_session` read `player_entry.get("assignedPosition")`, store on
  `self._assigned_position`, expose in `get_state()`.
- `main.py`: `LCU_ROLE = {"top":"TOP","jungle":"JUNGLE","middle":"MIDDLE","bottom":"BOTTOM",
  "utility":"UTILITY"}`; `BUILD_SAMPLE_FLOOR = 30`. Make `get_champ_select` **async**; after the
  matchups block (lines 218-225), resolve role (`LCU_ROLE.get(assigned.lower())` →
  `most_sampled_role` → skip) and `target_tier = get_app_state(db, "benchmark_target_tier")`; attach
  `state["champ_data"]["suggested_build"] = await _assemble_suggested_build(lcu, raw, role,
  target_tier)`.
- Add `GET /lcu-image` proxy per the icon-proxy constraint.

**Tests** (import-main + `monkeypatch.setattr(main, "db", db)`, stub `main.lcu` with `AsyncMock`,
like `test_benchmarks_api.py`): ≥30 build samples + `benchmark_target_tier` → `/champ-select`
returns `suggested_build.status=="ready"` with role from assigned_position; assigned `""` falls back
to most-sampled role; `/lcu-image` rejects non-`/lol-game-data` path (400) and proxies bytes;
monitor `get_state()` exposes `assigned_position`.

### Task 7 — Frontend types + render
**Files:** `src/shared/types.ts`, `src/champ-select/App.tsx`, (extend a component test if the harness
fits).
- Types: `BuildIcon {id,name,icon_url}`, `BuildItem extends BuildIcon {count}`,
  `BuildRunePage {primary_style, keystone, primary_runes[3], sub_style, sub_runes[2],
  stat_shards[3]}` (all `BuildIcon`), `SuggestedBuild {status:'ready'|'insufficient', role,
  target_tier, n_samples, items: BuildItem[], runes: BuildRunePage|null, spells: BuildIcon[]}`. Add
  `suggested_build?: SuggestedBuild` to `ChampData`.
- Render block after the matchups block (App.tsx ~line 138), gated `status==='ready'`: section
  header, items row, runes row (keystone larger + trees + shard dots), spells row — all `<img
  src={sidecarUrl(it.icon_url)} title/alt>`. `insufficient` → small "gathering high-elo data" line
  matching the "No history yet" tone. Keep `pointer-events-none`. No new fetch.

**Gate:** `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`.

## Verification

- Backend: `cd sidecar && python -m pytest` green after each task and at the end.
- Frontend: typecheck + lint + test + build green.
- Manual (optional): with League in champ select and a populated `build_samples` table, confirm
  `/champ-select` returns `suggested_build.status=="ready"` and the overlay renders icons via
  `/lcu-image`.
