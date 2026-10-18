# RehkopfPilot: sunnypilot for the Honda Odyssey

**RehkopfPilot** is my personal build for a **2022 Honda Odyssey** (`HONDA_ODYSSEY_5G_MMR`, Bosch) on a **comma four**, with openpilot longitudinal control. It combines three people's work:

- [**sunnypilot**](https://github.com/sunnypilot/sunnypilot): the feature set (MADS, Dynamic Experimental Control and the rest).
- [**MVL (mvl-boston)**](https://github.com/mvl-boston/openpilot): his Honda dev branch.
- [**brikowski**](https://github.com/brikowski/openpilot): the `ody-op` Odyssey longitudinal and steering tuning.

All three sit on top of [comma.ai's openpilot](https://github.com/commaai/openpilot).

Almost nothing here is mine. My part is merging the three, the Odyssey-specific fixes needed to make them agree, a few comma four screen features, and the testing. Credit for anything that drives well belongs to the people below.

## Credits

| Who | What this build uses |
|---|---|
| [**brikowski**](https://github.com/brikowski) ([openpilot `ody-op`](https://github.com/brikowski/openpilot/tree/ody-op), [opendbc `ody-op`](https://github.com/brikowski/opendbc/tree/ody-op)) | The Odyssey longitudinal controller: gas, brake and coast handling with grade compensation and gas-response feedback. Also the Odyssey steering authority (`STEER_MAX` 3840) with its torque tune, the panda safety limits for Odyssey longitudinal, the fix that stops the set speed jumping to 65 mph on engage, the `longControlState` ordering fix in controlsd, the low-memory branch switch in `op.sh`, and the Odyssey test suite this build's tests are based on. |
| [**MVL (mvl-boston)**](https://github.com/mvl-boston) ([openpilot](https://github.com/mvl-boston/openpilot), [opendbc](https://github.com/mvl-boston/opendbc)) | The Honda dev branch (`sp-honda-dev-202608`) underneath: Honda tuning across the lineup, Honda button handling with all-speed MADS, the torque-map steering, and the branch switcher. This fork mirrors all MVL branches so the switcher can still reach them. |
| [**sunnypilot**](https://github.com/sunnypilot/sunnypilot) | The base: MADS, Dynamic Experimental Control, the settings UI, the model store, and the October 2026 comma sync. |
| [**comma.ai**](https://github.com/commaai/openpilot) | openpilot itself, opendbc and panda. |

If this build is useful to you, the thanks go to them. If you have an Odyssey and want the pure version, run brikowski's `ody-op` directly.

## Branches

| Branch | Status | Install URL |
|---|---|---|
| `ody-next` | My daily driver. Currently **Atlanta**. | `installer.comma.ai/prehkopf/ody-next` |
| `ody-test` | The next release, on test drives before it moves to `ody-next`. Currently **Dahlonega**. Also has a **van load** setting (Empty / Family / Family + luggage) that adds gas for a heavier van; still being calibrated on loaded drives. | `installer.comma.ai/prehkopf/ody-test` |
| MVL's branches (`sp-honda-*`, …) | Unchanged mirrors of [mvl-boston/openpilot](https://github.com/mvl-boston/openpilot) | through the branch switcher |

The matching car code lives in [prehkopf/opendbc](https://github.com/prehkopf/opendbc) on branches of the same names.

## Releases

Each release is named after a place in Georgia, A to Z, and versioned by its release date (`YYYY.MM.DD`, with `.2`, `.3` for later releases the same day). The comma shows the name on the home screen and startup banner, for example "Buckhead • 5c3aa0d", and shows a short "what's new" card after an update.

### Dahlonega (2026.10.18.5): on `ody-test`

Chattahoochee plus a quicker launch from a stop.

- **Green-light launch.** From a stop, the driving model's plan creeps before it commits to moving. Once it plans to be past 2 m/s (4.5 mph) within 3.5 s, openpilot takes the acceleration from the part of the plan where it is already moving: up to 1.5 m/s², fading out by 2 m/s. It never overrides the car ahead: the planner still takes the lowest of the model, lead-following and cruise targets. Ported from comma's unmerged `better-green-lights` branch, gated on Dynamic Experimental Control's model mode.
  - On my drives the plan asked for only 0.13-0.29 m/s² in the second before moving; this asks for 1.44-1.50. Across all 16 pulled drives it would have fired only at the 3 launches with openpilot longitudinal, 7.2 s in total.
- **MADS brake-pause fix** (sunnypilot PR #2031): with steering-on-brake set to Pause, holding the brake from before MADS engaged no longer ends in "take control immediately".
- **Checked and left out:**
  - comma's gentler final-stop ramp (#38658): my 4 openpilot stops already ended gently (-0.06 to -0.27 m/s²).
  - sunnypilot's Honda Brake Hold disengage (#2039): Brake Hold never turned on in 16 drives.

### Chattahoochee (2026.10.18.4)

Buckhead SP1 plus a reorganized settings menu on the comma four.

- **Settings in five groups, most-used first:** driving, software, screen & alerts, privacy, system. Before, options were spread over Toggles, Device, Developer, Software and the sunnylink web app.
- **Driving** starts with **van load**, then personality, Dynamic Experimental Control, lane change, Experimental mode, MADS and enable RehkopfPilot.
- **MADS on/off and lane change mode** (nudge, nudgeless, 0.5-3 s, off) can now be changed on the comma. Before, only the sunnylink web app had them. MADS only changes with the car off, as in sunnypilot.
- Van load and onroad screen moved off the Device page, so nothing appears twice. The metric units button is gone (the setting stays at mph).
- **Software** holds updates & branch, models and sunnylink. **System** holds device, network, developer and firehose. Pairing still opens straight to the pairing card.
- **Testing:** new tests fail if a stock toggle is lost or appears in two groups. The pre-push checklist now builds and renders every settings page.

### Buckhead SP1 (2026.10.18.3)

A service pack: Buckhead plus fixes picked from upstream on 2026-10-18.

- **More gas when the van needs it** (brikowski 6d4b34f8, from his 2026-10-13 stable release). The gas feedback can now use all the gas headroom the map leaves, not just a fixed amount. This should help on hills and pull-aways.
- **No duplicate MADS "can't engage" alerts** (sunnypilot #1949).
- **Smoother steering on engage.** The model starts from the previous curvature while steering is off (comma #39091).
- **GPS startup fixes** (comma #39071, #39083). comma #39079 (start from the last GPS position) is left out: it stores LastGPSPosition in a binary format that sunnypilot's map features (map Smart Cruise Control, map speed limits) cannot read.
- **Steadier timing after a hiccup.** Control loops resync after a stall instead of running catch-up frames (comma #39095).
- **Offroad alert when uploads are being ignored** (comma #39104).
- **Not taken on purpose:** comma 0.11.3 makes Experimental mode ("Auto-speed") permanent and removes Chill mode, and sunnypilot then removed Dynamic Experimental Control. RehkopfPilot keeps DEC.
- **Tests:** an Odyssey downhill test now checks against the Odyssey's own gas-map floor (-0.2) instead of MVL's generic Bosch value.

### Buckhead (2026.10.18.2)

- **Turn vs lane change.** With the blinker on, braking in the last 2 seconds means a turn, not a lane change, so turning the wheel no longer starts a lane change. On replays of my drives, lane changes started at intersections dropped from 19 to 9, and all 12 real lane changes still worked.
- **Status pills** on the comma four: following gap to the car ahead (seconds while moving, feet when stopped), the van load setting, and why Dynamic Experimental Control switched to Experimental (`STOP AHEAD`, `SLOWING`, `CURVE`, `STOPPED`, `COLLISION`).
- **Steering-wheel bookmark.** Double-tap CANCEL to save a bookmark with a chime, so the moment is easy to find in the logs later without reaching for the screen.
- **Dim at night.** An onroad screen option that follows the light down to 10% brightness.
- **Settings profile.** My chosen settings are re-applied after a reinstall or a sunnylink restore (alpha longitudinal, DEC, personality, MADS, screen, updates on).
- **"What's new" card** after an update.
- **Branch switcher: pick the fork, then the branch** (RehkopfPilot, MVL, brikowski, sunnypilot, comma). It only offers branches that exist, and warns before a one-way switch to another fork.
- **Pre-push checklist** (`tools/ody/prepush.sh`) run before every release.
- **Bug fixes & improvements.** sunnylink settings sync no longer drops a text setting the web app sends unencoded.

### Atlanta (2026.10.17): on `ody-next`

- **Status pills** on the comma four: `OP LONG` / `STOCK ACC` and `EXP` / `DEC•EXP` / `DEC•ACC`.
- **Dynamic Experimental Control toggle** on the comma four.
- Release codenames and release-date versions.
- **Model runtime fix.** tinygrad is pinned to a version that contains comma's pin, so driver monitoring and the driving model load on the device. Without it, setup stuck on "looking for driver".
- RehkopfPilot branding: home screen, boot logo, startup banner and screensaver.

## Roadmap

These are plans in rough order, not promises. Anything that changes how the van drives waits for enough drive data to tune it and to check the result.

- **Chattahoochee**
  - Quicker launches from a stop. Today the van delivers about 60% of the requested acceleration in the first 3 seconds.
  - Smarter DEC on the highway: stay in ACC above about 55 mph unless the model sees a stop.
- **Dahlonega**
  - Uphill compensation. Holds and gentle slowdowns run about 0.2 m/s² short on grades over 1°.
  - Learned behavior kept between drives, stored separately for each van load.
  - Van load that suggests itself from how the van accelerates.
- **Later**
  - A "Georgia traffic" personality: shorter gap at speed, quicker catch-up, earlier resume.
  - Gentler braking and a longer gap when the wipers are on.
- **Investigating**
  - An emergency-braking layer to partly make up for the stock collision braking that openpilot longitudinal turns off. `ody-test` only, with safety tests.
  - Slowing for exit ramps from map data, on off-ramps only.
  - Handling remote start cleanly.

## What's in `ody-next`

The branch is built in this order:

1. sunnypilot's October 2026 comma sync (comma openpilot 2026-10-07).
2. MVL `sp-honda-dev-202608`.
3. comma master 2026-10-11.
4. brikowski's Odyssey controller and fixes, through his 2026-10-12 commits.

Odyssey-specific details:

- **Longitudinal.** brikowski's controller replaces the generic Honda Bosch gas and wind learner for the Odyssey only. Every other Honda keeps MVL's behavior.
- **Actuator delay is 0.5 s** on the Odyssey. brikowski's controller is tuned at 0.5 s. MVL uses 0.25 s for Bosch, but a fit of my own drives also puts the van at 0.5 s.
- **Steering.** STEER_MAX is 3840 with delta 2. Platform flags are `BOSCH_ALT_BRAKE | BOSCH_ALT_RADAR` (safetyParam 259).
- **Experimental mode.** Gas taps add a small, temporary acceleration boost (comma's AccelBoost). This works with Dynamic Experimental Control.
- **comma four screen.** An "onroad screen" picker on the Device page: always on, 15 s or 3 min (Buckhead adds dim at night).
- **Kept from comma:** the block on openpilot sending AEB. Stock emergency braking is not available with openpilot longitudinal on Bosch Hondas. openpilot's forward collision warning and hard braking still work.

## Testing

Every release passes the pre-push checklist (`tools/ody/prepush.sh`): a full PC build, the driving and driver-monitoring models loaded and run on the PC, code scans, the openpilot and sunnypilot unit and UI tests, the Honda car and safety tests, and a replay of a recorded Odyssey drive. Changes to car code also pass opendbc's full suite (panda safety, MISRA, about 10,300 car tests) and process replay against a sunnypilot base. Driving changes are replayed against my own Odyssey drives before they go in the van. The methods and scripts are in [`tools/ody/`](tools/ody/README.md).

## ⚠️ Read this first

- This is a personal build, tested on one 2022 Odyssey with a comma four. brikowski develops on a 2023, but I haven't driven any other year on this build.
- openpilot longitudinal on Bosch Hondas is **alpha**. It disables the stock radar, and with it stock ACC and collision mitigation braking.
- You are the driver. Keep your hands ready and your eyes on the road.

## 📊 User Data

By default, sunnypilot uploads driving data to comma servers. You can also see your data through [comma connect](https://connect.comma.ai/).

sunnypilot is open source software, and you're free to turn off data collection.

sunnypilot logs the road-facing camera, CAN, GPS, IMU, magnetometer, thermal sensors, crashes, and operating system logs. The driver-facing camera and microphone are only logged if you explicitly opt in under settings.

By using this software, you understand that use of this software or its related services will generate certain types of user data, which may be logged and stored at the sole discretion of comma. By accepting this agreement, you grant an irrevocable, perpetual, worldwide right to comma for the use of this data.

## Licensing

This fork, like sunnypilot, is released under the [MIT License](LICENSE). It includes original work by sunnypilot, MVL and brikowski, as well as significant portions of code derived from [openpilot by comma.ai](https://github.com/commaai/openpilot), which is also released under the MIT license with additional disclaimers.

The original openpilot license notice, including comma.ai's indemnification and alpha software disclaimer, is reproduced below as required:

> openpilot is released under the MIT license. Some parts of the software are released under other licenses as specified.
>
> Any user of this software shall indemnify and hold harmless Comma.ai, Inc. and its directors, officers, employees, agents, stockholders, affiliates, subcontractors and customers from and against all allegations, claims, actions, suits, demands, damages, liabilities, obligations, losses, settlements, judgments, costs and expenses (including without limitation attorneys' fees and costs) which arise out of, relate to or result from any use of this software by user.
>
> **THIS IS ALPHA QUALITY SOFTWARE FOR RESEARCH PURPOSES ONLY. THIS IS NOT A PRODUCT.
> YOU ARE RESPONSIBLE FOR COMPLYING WITH LOCAL LAWS AND REGULATIONS.
> NO WARRANTY EXPRESSED OR IMPLIED.**

For full license terms, see the [`LICENSE`](LICENSE) file.

## Supporting the people who made this

- sunnypilot: [GitHub Sponsors](https://github.com/sponsors/sunnyhaibin) and the [community forum](https://community.sunnypilot.ai/)
- comma.ai: [comma.ai/shop](https://comma.ai/shop)
