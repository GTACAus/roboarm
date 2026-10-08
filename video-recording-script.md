# Robot arm: video re-recording script

Seven short videos replace the old Mindstorms videos on three web pages. The pages already have the new written
steps; each video appears on its card automatically as soon as a file with the exact name below is uploaded to the
website folder (next to the `.html` files). Until then the card simply shows its steps.

## What changed (why we are re-recording)

- The hub runs the official **SPIKE App 3** with the arm program in **slot 0** (no Mindstorms app).
- The LMS-ESP32 board makes its own Wi-Fi, named after the board, for example **GTAC 12** (password **robotarm**).
- Joining that Wi-Fi pops up a page with **Open the remote**; the remote is at **10.10.10.10**.
- The muscle sensor connects to **IO32**, **GND** and **3V3** (not IO33).
- Students can code the arm with blocks in the remote's **Advanced (code)** mode.

## The videos

| # | File name (exact) | Page and card | Length |
|---|---|---|---|
| 1 | `arm-start-hub.mp4` (optional: a 3D hub model now shows these steps on the cards) | arm-instructions 03/05 and connecting-myosensors 07/08 | 30–45 s |
| 2 | `arm-join-wifi.mp4` | arm-instructions 04/05 | 45–60 s |
| 3 | `arm-remote.mp4` | arm-instructions 05/05 | about 60 s |
| 4 | `myo-wiring-io32.mp4` | connecting-myosensors 05/08 | about 45 s |
| 5 | `myo-use.mp4` | connecting-myosensors 08/08 | about 60 s |
| 6 | `code-canvas.mp4` | codecontrol 02/03 | about 45 s |
| 7 | `code-change.mp4` | codecontrol 03/03 | 60–75 s |

## Before you record

**Hardware**
- One assembled arm: board in **port A**; motors in **B**, **C** and **E** (the starting remote uses these three).
- The board has the latest firmware and its Wi-Fi name set (`python roboarm_access_point/tools/upload.py COMx --name "GTAC 12"`).
- The hub has `roboarm_access_point/hub/arm-spike-app3.py` saved in **slot 0**, and is charged.
- For videos 4 and 5: a muscle sensor with one of the three cable colour sets, and electrodes.

**iPad**
- Turn on **Do Not Disturb** and set the brightness high.
- For the pop-up in video 2 to appear, the iPad must not have had the remote open in the last 15 seconds:
  close Safari, wait 20 seconds, then **forget** the board's network in Settings before recording.
- For video 6 to show the starting program: Settings → Safari → Advanced → Website Data → remove **10.10.10.10**.
- Screen recordings: Control Centre → **Screen Recording**. Use Settings → Camera → Formats → **Most Compatible**
  so videos save as H.264 `.mp4`.

**Filming hardware**
- Landscape, 1080p, a plain light background, filmed from above or at 45°. Keep hands out of the way of the hub's display.

**Narration**
- Optional. If you narrate, read the lines in *italics*; otherwise add them as captions.

## 1. `arm-start-hub.mp4` — Start the arm program on the hub (camera)

| Shot | What to show | Line |
|---|---|---|
| 1 | Close-up of the blue GTAC board's cable in **port A**, motors in B, C and E | *"Plug the blue GTAC board into port A, and check the motors are in ports B, C and E."* |
| 2 | Press the hub's centre button; the hub lights up | *"Press the centre button to turn the hub on."* |
| 3 | Press right until the display shows **0** | *"Press left or right until you see program zero."* |
| 4 | Press the centre button | *"Press the centre button to start it."* |
| 5 | Hold on the display: **?** for a few seconds, then a motor letter (B) | *"The hub shows a question mark while it finds the board, then a motor letter. If you are wearing the muscle sensor, keep your arm relaxed until the letter appears."* |

## 2. `arm-join-wifi.mp4` — Connect the iPad to the arm (screen recording)

| Shot | What to show | Line |
|---|---|---|
| 1 | Settings → Wi-Fi; the list shows **GTAC 12** | *"Open Settings, then Wi-Fi, and find your board's name."* |
| 2 | Tap it, type **robotarm**, tap Join | *"The password is robotarm."* |
| 3 | The pop-up page appears; tap **Open the remote** | *"A page pops up. Tap Open the remote."* |
| 4 | The remote loads; tap **Done** at the top right | *"Tap Done, not Cancel, so the iPad stays on this Wi-Fi."* |
| 5 | Home screen: tap the **Robot arm** app; the remote loads | *"If no page pops up, open the Robot arm app on the home screen."* |

## 3. `arm-remote.mp4` — Drive the arm with the remote (screen recording plus a camera shot of the arm)

Record the iPad screen and film the arm at the same time; edit them side by side, or cut between them.

| Shot | What to show | Line |
|---|---|---|
| 1 | The remote on **Remote** and **Basic** | *"This is your remote. Each control has a yellow number."* |
| 2 | Hold the D-pad up, then right; cut to the arm moving | *"Hold the D-pad to move the motors."* |
| 3 | Push the slider up and down; the arm moves | *"Push the slider further to go faster."* |
| 4 | Watch the motor tiles at the bottom change | *"The tiles at the bottom show where each motor is."* |
| 5 | Tap **✎ Change remote**, add a button, tap ⚙ and choose Motor C, tap ✎ to finish | *"Change remote lets you add controls and choose which motor each one moves."* |

## 4. `myo-wiring-io32.mp4` — Connect the sensor cables (camera, close-up)

| Shot | What to show | Line |
|---|---|---|
| 1 | The board's pin row, with the IO32, GND and 3V3 labels readable | *"These are the pins we use: IO32, GND and 3V3."* |
| 2 | Hold up the sensor's three cables; name the colours | *"Your cables are one of three colour sets. Check the picture on the card."* |
| 3 | Point at the **USB-C** socket and the pair of pins next to it | *"GND and 3V3 are the two pins right next to the USB-C socket."* |
| 4 | Push the **ground** (black) plug onto **GND**, the inner pin of that pair | *"Ground goes on GND, the inner pin."* |
| 5 | Push the **power** (red) plug onto **3V3**, the outer pin of that pair | *"Power goes on 3V3, beside it."* |
| 6 | Count four pins along the inner row from GND; push the **signal** (blue) plug onto **IO32** | *"The signal goes on IO32, four pins along from GND."* |
| 7 | Slow pan across all three, pushed fully down | *"Check each one is pushed all the way down."* |

## 5. `myo-use.mp4` — Move the arm with your muscle (camera plus a screen recording)

| Shot | What to show | Line |
|---|---|---|
| 1 | Forearm with the sensor attached, relaxed; the hub shows **B** | *"With the program running, squeeze your muscle."* |
| 2 | Squeeze; motor B turns; relax, it returns | *"The harder you squeeze, the further it turns. Relax and it goes home."* |
| 3 | Press the hub's right button; the display shows the next letter; squeeze again | *"Press left or right on the hub to choose another motor."* |
| 4 | iPad on the arm's Wi-Fi: **Muscle sensor** tab; squeeze and show the graph rising | *"On the iPad, the Muscle sensor tab shows your signal over the last 30 seconds."* |
| 5 | Tap a motor tile (E); squeeze; motor E moves | *"Tap a motor to choose which one your muscle moves."* |
| 6 | Drag **Amplify** up; the same squeeze moves further | *"If the arm barely moves, turn up Amplify."* |

## 6. `code-canvas.mp4` — Open the code canvas (screen recording)

| Shot | What to show | Line |
|---|---|---|
| 1 | Remote tab → tap **Advanced (code)** | *"To code your arm, choose Advanced."* |
| 2 | Tap **</> Code**; the canvas opens with the starting program | *"Tap Code. The starting program is already here."* |
| 3 | Point at a block "when remote 1 up → turn Motor E forward 5 degrees" | *"Each control turns its motor five degrees. The numbers match the live remote on the right."* |
| 4 | Tap **▶ Run**; press D-pad 1 up in the live remote; the block glows and motor E moves (cut to the arm) | *"Tap Run, then use the remote on the right to test it."* |

## 7. `code-change.mp4` — Change your code (screen recording, with a camera cut-in)

| Shot | What to show | Line |
|---|---|---|
| 1 | Tap the **5** in "turn Motor E forward" and change it to **45** | *"Change the number to turn further."* |
| 2 | Motors → drag **set Motor E speed to slow** under "when remote 1 up", above the turn block | *"Set the speed to make it slower or faster."* |
| 3 | Tap **■ Stop** then **▶ Run**; press up; motor E turns 45° slowly (camera cut-in) | *"Stop and run again to try your changes."* |
| 4 | Drag in **go Motor B to position 90 shortest path** under "when remote 1 right", run, press right | *"Go to position sends a motor to an exact angle."* |
| 5 | Close with **Done**; mention the code is saved | *"Your code is saved on the iPad."* |

## When you are done

1. Check each file name matches the table exactly (lower case, `.mp4`).
2. Keep each file under about 20 MB: trim the start and end, 1080p is plenty.
3. Put the files in the website folder next to `arm-instructions.html` and commit them, or send them to whoever looks after the website.
4. Open each page on an iPad and check the video appears on its card.
