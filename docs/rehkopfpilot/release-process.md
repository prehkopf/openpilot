# How a RehkopfPilot release is made

## Where the code comes from

```mermaid
flowchart BT
  comma["comma.ai openpilot<br/>(+ opendbc, panda)"]
  sp["sunnypilot<br/>MADS, DEC, settings, model store"]
  mvl["MVL sp-honda-dev<br/>Honda tuning, buttons, torque maps"]
  bri["brikowski ody-op<br/>Odyssey gas/brake/coast + steering"]
  star["StarPilot · FrogPilot · dragonpilot<br/>(ideas, ported by hand)"]
  rp(["RehkopfPilot<br/>ody-test → ody-next"])
  comma --> sp --> mvl --> rp
  comma -.->|cherry-picks| rp
  bri --> rp
  star -.->|ideas| rp
```

Merge order when updating: sunnypilot sync, then MVL dev, then comma master, then brikowski's Odyssey commits (`tools/ody/README.md`, "Updating from upstream"). Since comma 0.11.3 made Auto-speed permanent and sunnypilot removed Dynamic Experimental Control, upstream changes come in as **cherry-picks**, not whole merges.

## From idea to the van

```mermaid
flowchart LR
  drive(("drive")) --> pull["pull logs<br/>pull_comma_logs.ps1"]
  pull --> qa["drive reports<br/>tools/ody/drive_report"]
  qa --> finding{"finding"}
  finding -->|bug or idea| code["change on a branch<br/>+ tests"]
  finding -->|new failure mode| lesson["Lessons learned<br/>+ a prepush check"]
  lesson --> prepush
  code --> replay["replay on my drives<br/>(card, controlsd, plannerd,<br/>planner A/B, turns)"]
  replay --> prepush["prepush.sh"]
  prepush --> test["ody-test"]
  test --> drive
  test -->|a few good drives| next["ody-next<br/>(daily driver)"]
```

Every Q/A finding becomes a line in `tools/ody/README.md` → Lessons learned, and a prepush check when it can be one. A new check has to be able to fail: break the thing on purpose once and watch it go red.

## Branches

```mermaid
gitGraph
  commit id: "sunnypilot sync"
  commit id: "MVL dev"
  commit id: "comma 10-11"
  commit id: "brikowski 10-13"
  branch ody-test
  commit id: "Buckhead"
  commit id: "Chattahoochee"
  commit id: "Dahlonega"
  commit id: "Etowah"
  checkout main
  merge ody-test id: "ody-next = Etowah"
  checkout ody-test
  commit id: "Fayette"
```

(`main` stands in for `ody-next` here.) `ody-test` gets each release first. After a few clean drives it is promoted to `ody-next`, the daily driver. The car code lives in [prehkopf/opendbc](https://github.com/prehkopf/opendbc) on branches of the same names, pinned as the `opendbc_repo` submodule.

## Names and versions

Releases are named after places in Georgia, A to Z, and versioned by release date (`YYYY.MM.DD`, `.2`, `.3` for later releases the same day).

```mermaid
timeline
  title RehkopfPilot releases, October 2026
  10-17 : Atlanta : status pills, DEC toggle, branding
  10-18 : Buckhead : turn vs lane change, wheel bookmark, settings profile
        : Chattahoochee : settings in 5 groups, van load first
        : Dahlonega : green-light launch, MADS brake-pause fix
        : Etowah : navigation without prime, offline map
  10-24 : Fayette : full-range steering, nav-aware turns, StarPilot gap, sleep after 1 h
        : Fayette SP1 : sunnypilot's new model loader, model store works again
```

A release touches four places:

| File | What |
|---|---|
| `BUILD_NAME` | the codename, shown on the home screen and startup banner |
| `openpilot/sunnypilot/common/version.h` | the release-date version |
| `RELEASE_NOTES.md` | 3-4 lines of at most 30 characters for the comma's "what's new" card |
| `README.md` | the full release notes and the roadmap |

## The prepush checklist

```mermaid
flowchart TB
  b["build (scons)"] --> m["models: driving +<br/>driver monitoring on PC"]
  m --> s["scans: imports, params,<br/>services, lint"]
  s --> t["pytest: openpilot +<br/>sunnypilot + UI"]
  t --> h["Honda car + safety tests<br/>(serial and parallel)"]
  h --> r["replay a recorded drive:<br/>card, controlsd, plannerd"]
  r --> tl["recorded turns vs<br/>lane changes"]
  tl --> a["release audit vs<br/>the published branch"]
  a --> ok(["PRE-PUSH: OK"])
```

`tools/ody/prepush.sh` runs all of this in a few minutes; `--full` adds opendbc's whole suite and an A/B process replay against a sunnypilot base. Details and the reason for each step are in [`tools/ody/README.md`](../../tools/ody/README.md).
