# How RehkopfPilot drives the van

A tour of what happens between the camera and the Odyssey's steering rack, gas and brakes, with the places where this build differs from comma, sunnypilot, MVL and brikowski marked. Diagrams are [Mermaid](https://mermaid.js.org/) and render on GitHub.

## The big picture

```mermaid
flowchart LR
  cam["Road cameras"] --> modeld
  nav["navd<br/>(Mapbox route, 1 Hz)"] -.->|navInstruction| modeld
  maps["mapsd<br/>(offline Georgia map)"] -.->|map frames| ui["comma four screen"]
  nav -.->|next turn, ETA| ui
  modeld["modeld<br/>driving model +<br/>DesireHelper"] -->|modelV2| plannerd
  radar["Odyssey radar<br/>via card"] -->|radarState| plannerd
  plannerd["plannerd<br/>MPC, cruise, e2e,<br/>DEC, highway following"] -->|longitudinalPlan| controlsd
  modeld -->|desired curvature| controlsd
  controlsd["controlsd<br/>torque + accel"] -->|carControl| card
  card["card<br/>opendbc Honda<br/>CarController"] -->|CAN| panda["panda safety<br/>(hondaBosch, 259)"]
  panda --> van(("2022 Odyssey"))
```

mapsd publishes its frames for future navigation-aware driving models; today only the screen reads them. The driving model's only navigation input in this build is the DesireHelper's turn check.

| Piece | Whose code | What this build changes |
|---|---|---|
| Driving model | comma (sunnypilot model store) | nothing |
| DesireHelper (lane changes, turns) | comma + sunnypilot | **turn intent**: braking (Buckhead) or a navigation turn on the blinker side (Fayette) means a turn, not a lane change |
| Planner | comma + sunnypilot (DEC) + MVL | green-light launch (Dahlonega), **lane-change close-gap and catch-up** (Fayette), comma's set-speed fix #39127 |
| Honda CarController | MVL + brikowski | brikowski's Odyssey gas / brake / coast controller, van-load presets, **full 3840 steering range** (Fayette) |
| Panda safety | comma + MVL + brikowski | brikowski's Odyssey longitudinal limits |

## Longitudinal: who gets to decide the acceleration

The planner builds several candidate accelerations and takes the **lowest**. Nothing added in this build can ever ask for more than the most cautious candidate.

```mermaid
flowchart TB
  subgraph inputs[" "]
    direction LR
    lead["Lead car<br/>(radarState)"]
    setspd["Set speed"]
    model["Model plan<br/>(e2e)"]
  end
  lead --> gap["Follow time<br/>personality: 1.25 s aggressive"]
  lcg["Lane-change close-gap<br/>0.75 s while signalling out"] -.->|shorter, ramped| gap
  gap --> mpc["MPC: follow the lead"]
  setspd --> cruise["Cruise: ramp to set speed<br/>(jerk-limited)"]
  catch["Catch-up<br/>+0.3 m/s² ceiling when a<br/>lead pulls away"] -.-> cruise
  model --> e2e["e2e: model's own accel<br/>+ green-light launch"]
  dec{"DEC: ACC or<br/>blended?"}
  dec -->|blended| e2e
  mpc --> min(("min"))
  cruise --> min
  e2e -->|only in blended| min
  min --> plan["aTarget"]
```

- **Dynamic Experimental Control** (sunnypilot) decides whether the model's own acceleration joins the race: "blended" for a stop ahead, slowing traffic, a curve, a standstill or a collision risk, otherwise plain ACC. The comma four shows why in a pill (`STOP AHEAD`, `SLOWING`, `CURVE`, ...).
- **Close-gap** (Fayette, from StarPilot): while the blinker is on for a lane change above 20 mph, the follow time ramps from your personality's gap down to 0.75 s. A car in the blind spot on that side, a lead braking hard, or a stop cancels it.
- **Catch-up** (Fayette, from StarPilot): above 45 mph, below set speed, with a lead in your path that has pulled 0.4-0.7 s beyond the target gap, the cruise candidate may accelerate up to 0.3 m/s² harder. The MPC still holds the gap. With openpilot longitudinal the Odyssey's radar is silenced, so the lead is a vision lead the model is at least 70% sure of. It only matters in ACC mode, because in blended mode the cruise candidate has no ceiling.

## Lane changes and turns

The DesireHelper turns the blinker into a lane change, or deliberately doesn't. Comma's version can't tell a lane change from an intersection turn, so steering into a turn counted as the "nudge" that starts a lane change.

```mermaid
stateDiagram-v2
  direction LR
  [*] --> off
  off --> preLaneChange: blinker on, ≥ 20 mph,<br/>no turn intent
  off --> held: blinker on with turn intent
  held --> preLaneChange: turn intent cleared,<br/>blinker still on
  preLaneChange --> off: blinker off or < 20 mph
  preLaneChange --> held: turn intent
  preLaneChange --> laneChangeStarting: nudge (or auto),<br/>no blind-spot car
  laneChangeStarting --> preLaneChange: done, blinker still on
  laneChangeStarting --> off: done
  held --> off: blinker off
  note right of held
    turn intent =
    braked in the last 2 s (Buckhead)
    or a navigation turn on that side
    within 12 s of travel (Fayette)
  end note
```

On the 2026-10-23 drives, 4 of 34 lane changes still started in a real turn: taken on the gas, with no braking. The navigation check catches those when you're on a route. Without a route it's still possible, so the prepush check `turn_lane_change` replays every recorded turn to make sure no new build makes it worse.

## Steering

```mermaid
flowchart LR
  c["controlsd<br/>torque request<br/>-1 … 1"] --> clip["clip to ±1"]
  clip --> scale["× 3840 counts"]
  scale --> slew["slew limit<br/>2 × 3840 counts/s<br/>= stock 7680"]
  slew --> can["STEERING_CONTROL<br/>on CAN"]
  can --> eps["Odyssey EPS"]
```

- The Odyssey's camera uses up to **2560** counts for lane keeping. Above that the steering response stops being proportional and the van adds some brake drag (comma's note, from Road Departure Mitigation).
- brikowski's tune rescales `latAccelFactor` (× 1.5) and `friction` (÷ 1.5), so a given lateral acceleration asks for the **same counts** as the stock 2560 range. The extra range only comes into play when the request saturates.
- Atlanta through Etowah opened 2560 → 3840 only between 34 and 74 mph after 0.2 s of missing the curve. On the 2026-10-23 drives the van sat at 2560 about 7% of the time below 55 mph. Fayette follows brikowski's newer `ody-op-test` (cef93020): the full range at every speed.

## Gas and brakes (brikowski's Odyssey controller)

openpilot asks for an acceleration; the Odyssey wants a gas count or a brake command. brikowski's controller decides which domain each request belongs to (`odyssey_command_domains`) and keeps the hand-offs smooth. Above 5 m/s (11 mph):

```mermaid
flowchart LR
  a["aTarget (m/s²)"] --> dom{"domain"}
  dom -->|"> 0"| gas["gas: map + grade<br/>+ response feedback<br/>× van-load preset"]
  dom -->|"-0.10 … 0"| bridge["light gas 'bridge'<br/>(stays ready to pull)"]
  dom -->|"-0.30 … -0.10"| coast["coast:<br/>no gas, no brake"]
  dom -->|"< -0.30"| brake["friction brake<br/>(held until the request<br/>is no longer negative)"]
```

Below 5 m/s any request at or below zero goes to the brakes, so the van always has stop authority. Gas and brake are never commanded together.

- Grade compensation from the pitch estimate, gas-response feedback that learns how the van answers, and a coast observer.
- Van load (Empty / Family / Family + luggage) scales only the positive gas map input, bounded by the panda's gas limit.
- The actuator delay is 0.5 s, from brikowski's tuning and a fit of my own drives.

## Where to read the code

| Topic | File |
|---|---|
| Turn intent, navigation check | `openpilot/selfdrive/controls/lib/desire_helper.py` |
| Close-gap, catch-up | `openpilot/selfdrive/controls/lib/highway_following.py` |
| Planner candidates | `openpilot/selfdrive/controls/lib/longitudinal_planner.py` |
| DEC | `openpilot/sunnypilot/selfdrive/controls/lib/dec/dec.py` |
| Odyssey car code | `opendbc_repo/opendbc/car/honda/carcontroller.py`, `interface.py`, `values.py` |
| Navigation | `openpilot/selfdrive/navigation/` (see [navigation.md](navigation.md)) |
