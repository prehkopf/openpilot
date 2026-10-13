# Odyssey build: how it's tested

Everything here runs on a PC (Ubuntu 24.04, or WSL2 on Windows). Nothing in this folder runs on the comma.
A change goes onto the comma only after every layer below passes. Then it gets a few real drives, and those drives go through the drive report.

| Layer | Script | What it proves |
|---|---|---|
| 1. opendbc suite | `opendbc_test.sh [branch]` | Panda safety C tests, MISRA, lint, and every car test, including `test_odyssey_port.py` |
| 2. Full build | `build_pc.sh [branch]` | The whole tree compiles. Prints the Honda tuning it builds (delay, ki) |
| 3. A/B replay | `replay_ab.sh [base]` | Replays comma's Honda test routes on a sunnypilot base and on this build. Every difference must trace to a deliberate change |
| 4. Own-route replay | `replay_segments.py <segment>` | card and controlsd from this build run cleanly on my own Odyssey drives |
| 5. Van model + sims | `fit_plant.py`, opendbc `odyssey_load_sim.py` | Closed-loop check of gas changes against a van model fitted from real drives |
| 6. Freshness | `freshness.sh` | How far behind comma, sunnypilot, MVL and brikowski this build is |
| 7. Drive report | `drive_report/` | What actually happened on the road |

## Setup (once)

```bash
# Windows: wsl --install -d Ubuntu-24.04
curl -LsSf https://astral.sh/uv/install.sh | sh
tools/ody/build_pc.sh ody-next          # clones to ~/odynext and builds (first run ~15 min, rebuilds ~2 min)
cd ~/odynext && source .venv/bin/activate
```

Logs come off the comma with `pull_comma_logs.ps1` on the laptop, which copies `rlog.zst` and `qlog.zst` for every segment into `Documents\openpilot\rlogs\<route>--<seg>\`. The stock uploader only sends qlogs, so full rlogs have to come this way. From WSL that folder is `/mnt/c/Users/<you>/Documents/openpilot/rlogs`.

## 1. opendbc suite

```bash
tools/ody/opendbc_test.sh ody-next      # or ody-test
```

This is opendbc's own `test.sh`, about 10,300 tests. The safety tests need the compiled safety library, so they run on Linux only. Two Odyssey-specific points:

- The MVL Honda controller imports `openpilot.common.params`. `opendbc_shim/` stands in for it so opendbc tests run standalone.
- **Mutation check.** After changing the Odyssey safety limits (`max_gas` 2000, `min_gas` -60, `STEER_MAX` 3840, delta 2), loosen one on purpose and confirm the safety tests fail. Then put it back. This proves the tests actually guard the limits.

## 2. Full build

`build_pc.sh` builds the whole tree (`scons`, about 80 s on a 20-thread laptop) and then runs `check_params.py`, which prints what this build hands the car:

```
HONDA_ODYSSEY_5G_MMR op long: delay 0.5 ...
```

`check_params.py <segment>` also prints what a recorded drive ran with: fork, branch and delay. This is how the delay mismatch was caught. brikowski's controller is tuned at 0.5 s, MVL sets 0.25 s for Bosch, and the Odyssey now stays at 0.5 s.

## 3. A/B process replay

```bash
tools/ody/replay_ab.sh                  # base = sunnypilot master; ody-next was checked against PR #2047 (18aa89b49)
```

This builds the base in `~/spbase`, records its outputs on comma's Honda test routes, and replays this build against them. On ody-next every difference traced to one of three changes:

- MVL Honda tuning: ki 0 on Nidec, Bosch delay 0.25.
- brikowski's `longControlState` ordering fix in controlsd.
- The Odyssey controller.

## 4. Replay on my own drives

```bash
python tools/ody/replay_segments.py ~/rlogs/00000008--83edc4fea4--10
```

This runs card and controlsd from this build on a recorded segment. It checks for crashes, valid messages, the fingerprint, the safety param (`hondaBosch` 259), sendcan output, and accel compared with what the car actually ran.

**Known quirk:** the replay harness drops a random number of card frames each run (3 to 725 seen, on any branch). Compare values, not message counts.

## 5. Van model and load sims

```bash
python tools/ody/fit_plant.py ~/rlogs/00000007--509a7563e5--* ~/rlogs/00000008--83edc4fea4--*
```

This fits the van's response to the gas command over engaged, pedal-free samples:

`aEgo(t+0.5) = 0.00111·gas + 0.183 − 0.000345·v² − 0.88·g·sin(pitch)`

The fit uses routes 7 and 8 (empty van, rmse 0.11 m/s²), and its best delay is 0.5 s.

On `ody-test`, `opendbc/car/honda/tests/odyssey_load_sim.py` runs the real Honda CarController in closed loop against this model. It covers each true load against each preset setting, over level pull-aways, 4% climbs and cruise.

To calibrate the load presets: run `fit_plant.py` on a loaded drive and compare `c_gas` and `b` with the empty fit. If needed, update `ODYSSEY_LOAD_FACTORS` and the sim's plant.

## 6. Freshness

```bash
tools/ody/freshness.sh
```

This shows how many upstream commits aren't in this build yet, and lists any MVL branches the fork is missing. The fork mirrors all MVL branches so the built-in branch switcher can reach them.

## 7. Drive report

```bash
python tools/ody/drive_report/extract.py ~/rlogs/00000008--83edc4fea4 /tmp/r8.json
python tools/ody/drive_report/engagements.py /tmp/r8.json   # engagements, why each one ended, events, errors
python tools/ody/drive_report/tracking.py /tmp/r8.json      # accel tracking by request band, gas overrides, lateral error by speed, saturation
python tools/ody/drive_report/uphill.py /tmp/r8.json [...]  # shortfall against grade (the known ~0.2 m/s² uphill gap)
```

What to look at after a drive:

- **Long tracking rms.** brikowski ody-op routes ran 0.18 to 0.21.
- **Uphill shortfall.**
- **Steer saturation** and the share of time above 2560 steer counts.
- **Disengage causes.** Brake disengages should be driver choice.
- **Panda TX blocks.** They're benign when they happen only at engage and disengage edges.

## Updating from upstream

1. Run `freshness.sh` to see what's new.
2. Merge, in this order: sunnypilot sync, then MVL dev, then comma master, then brikowski's Odyssey commits.
3. Run layers 1 through 4.
4. Push code only: `GIT_LFS_SKIP_PUSH=1 git push origin <branch>`. In my clone this is the `git push-code` alias. Models come from sunnypilot's Hugging Face store, so they never need to go to GitHub.
