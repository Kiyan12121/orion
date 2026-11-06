# ORION 6.0 — Personal Intelligence System

## New in 6.0
**Smarter brain**
- **Plan cards:** for any job with 3+ steps, ORION puts up a live holographic checklist and ticks each step off as it goes. The plan shows on your phone too.
- **"How I did it":** while ORION works you see what it's doing in the chat ("🔎 Searching the web…", "📅 Adding to your plan…"). Afterwards it folds into a "3 steps · how I did it" line you can open.
- **Total recall:** every conversation is now archived on your PC, so ORION can look back weeks or months ("what did I say about my mocks?"), not just the last 60 messages. The Brain page shows how much it remembers.
- **Knows your day:** ORION knows whether it's a school day, the weekend or late at night, what's next on your plan, and what homework is due, and answers with that in mind.

**Jarvis voice & presence**
- **Instant replies:** ORION says "Right away, sir." / "Let me look that up, sir." the moment it starts a job, so it never feels like it's ignoring you. Short phrases are saved after the first time, so they play instantly.
- **Welcome back:** after 45+ minutes away, ORION greets you out loud with what's next and anything it finished while you were gone (at most every 2 hours, never late at night).
- Both can be switched off in ⚙.

**Phone 6.0**
- **📍 Local Intel on your phone** (More › Local):
  - Desford's map with pinch-to-zoom, crime dots and your house.
  - ORION's summary, every crime sorted nearest-to-you, stop & search with exact times, plus air, moon, aurora and floods.

**Speed & polish**
- **Smooth mode by itself:** if a machine runs the interface below ~28 fps, ORION switches itself into smooth mode and remembers it. Change it in ⚙ Visuals.
- **Bug fixes:**
  - Habits and suggestions were broken: two features were fighting over the same file.
  - Local Intel crashed when you were offline; it now remembers your area.
  - A duplicate weather field.
  - A chat-display crash with the new activity trail.

**+346 skills (now 851)**
- **67 new instant tools:**
  - Maths: averages, fractions, ratios, nth term, straight lines, bounds, trig, standard form, area and volume.
  - Science: physics equations, moles & Mr, resistors, half-life.
  - Money: loans, margins, best value, wages, subscriptions.
  - Dates and time: sleep cycles, timestamps.
  - Text and code tools, plus gaming: K/D, win rate, eDPI.
  - Fun: 8-ball, teams, would-you-rather…
- **8 new study tasks for every GCSE subject (216 skills):** 6-mark plans, teach-me-back, stretch questions, 60-second summaries, spec checks…
- **63 new playbooks** for school, writing, content, business, coding, life and gaming.

## 5.7: Local Intel — smoother, smarter, and centred on you
- **Much smoother on laptops:**
  - The map is now drawn in two layers. The heavy part (roads and buildings) is only redrawn when you move the camera, and it uses a lighter version while you're dragging.
  - Orbit is now off by default.
  - There's a quality switch (⚙ Fast, Balanced, Max), and ORION drops the quality itself if your machine struggles.
- **🏠 Your house:** press "your house" and type your address. It's saved only on your PC, never uploaded.
  - You get a glowing YOU beacon with a 250 m ring.
  - Every crime shows its distance from you.
  - ORION's brief tells you what happened near you.
- **BRIEF tab:** a plain-English summary first (quieter or busier than usual, what kind of crime, anything near you). Then how many cases were charged, closed with no suspect, or still open, plus clickable hotspots that fly the camera there.
- **LOG tab:** every crime as a list, sorted by nearest to you or newest. Each one shows the type, street, distance, month, and the latest outcome with the month it was updated. Click one to fly to it on the map.
- **Dates and times:** the police only publish crimes by month (never the day or time) to protect victims, and the app now explains that. **Stop & search** records do have exact dates and times, so they're shown as a new layer and in the log.

## 5.6: Local Intel in 3D
- **It actually looks like Desford.** The map uses real OpenStreetMap data: every road and close with its name, all ~1,500 buildings at their real size and height, plus fields, woods, rivers, the old railway line, and places like Bosworth Academy, the library, the post office and the pubs.
- **Holographic 3D city view:**
  - Buildings rise out of the ground as glowing blocks.
  - Crimes stand up as coloured light pillars; more crimes means a taller pillar.
  - Planes fly above the map with shadows below them.
  - The parish boundary is a glowing fence.
  - The map builds itself outward in a scan wave, and the camera slowly orbits.
- **Controls:** right-drag (or Shift-drag) to rotate and tilt. Use **3D** to switch to a flat map and **Orbit** to stop the spin. There's a compass, so you always know where north is.
- **Live conditions:** at night the map goes dark and windows light up. When it's raining in Desford, it rains on the map.
- Labels no longer pile on top of each other.

## 5.5.1
- **Local Intel is now just Desford, not Leicester.**
  - It was falling back to Leicester city centre because no home place was set; it now defaults to Desford.
  - It pulls Desford's actual parish boundary from OpenStreetMap, draws it, darkens everything outside it, and asks police.uk only for crimes inside it.
  - The map fits the village.
  - Press "📍 change area" to point it somewhere else.

## New in 5.5: Globe mode, levelled up
- **◎ LOCAL INTEL:** click HOME on the globe (or say "how much crime is there in Desford?") and ORION dives in to a holographic map of your village. It's built from real OpenStreetMap roads, buildings, rivers, railways and places.
  - **Crime (police.uk):** every reported crime within 1 mile, as glowing dots coloured by type. Hover a dot for the street, crime type and outcome so far.
    - Latest month or the last 6 months, plus a heatmap.
    - A 6-month trend and how many crimes of each type (click a type to hide or show it).
    - The hotspot streets, outcomes so far, and your neighbourhood police team's current priorities.
    - Police data runs about 2 months behind, and locations are anonymised to nearby streets.
  - **Area:** temperature, air quality, UV and pollen, sunrise and sunset, moon phase, aurora chance (live Kp), and Environment Agency flood warnings within 20 km.
  - **Sky:** live aircraft overhead with callsign, height and speed, drawn moving on the map. Click one to track it.
  - Drag to pan, scroll from street level out to the whole county, and press Esc to go back to the globe.
- **The globe itself:**
  - NASA world events: wildfires, storms with their tracks, volcanoes and icebergs.
  - Aurora ovals sized by the live Kp, and city lights on the night side.
  - Hover tooltips and click-to-fly on every marker.
  - Layer switches to show or hide each layer.

## New in 5.4: ORION's Eyes
- **Your phone is now ORION's webcam. No Iriun needed.**
  1. On the phone, open **PC › ORION'S EYES** and tap **START CAMERA** (allow the camera once).
  2. Prop the phone up facing you.
  - Frames go straight to your PC over your own link and are never saved.
  - The screen stays on while it's running, and the camera stops the moment you leave the app.
- With Hand gestures switched on, the PC now **waits for a camera** instead of giving up. It uses the phone the moment it starts streaming, falls back to a webcam or Iriun if you have one, and your phone gives you a nudge when the PC is waiting for it.

## 5.3.1
- **Hand gestures now work with phone-as-webcam apps** (Iriun, DroidCam, OBS Virtual Camera). ORION tries every camera and Windows camera driver until one gives a real picture, then remembers it. Large phone video is shrunk first so it stays fast.

## New in 5.3: Stark Protocols
- **Globe mode:** a full-screen holographic Earth.
  - Live day and night, with your home pinned.
  - Earthquakes from the last day as pulsing rings, sized by magnitude.
  - The International Space Station live, with its orbit.
  - Drag to spin, scroll to zoom, or type any place to fly there. Say "show me Tokyo on the globe".
- **Holograms:** rotating 3D wireframes ORION puts up to explain things.
  - Atoms with the right number of electrons in each shell.
  - Molecules: water, CO₂, methane, ammonia, ethanol, salt and more.
  - DNA, a cell, the heart, the brain, a galaxy, the Sun, a ringed planet, a rocket and 3D shapes.
  - Ask "show me a carbon atom" or "hologram of DNA".
- **Threat scan:** a full-screen radar sweep with real checks.
  - Windows Defender, the firewall, drive health, disk space, memory and CPU.
  - Programs running from Temp or Downloads, open network ports, startup apps and uptime.
  - Ends with a verdict. Say "run a threat scan".
- **Suit up:** a cinematic power-up sequence. Systems come online, ORION reads a spoken status report, and it opens your suit-up apps (set them in ⚙). Say "suit up".
- **Hand gestures (opt-in, off by default):**
  - Wave to make ORION listen.
  - Swipe to change page.
  - Open palm to stop.
  - Pinch to close a pop-up.
  - Turn it on in the new **Stark Protocols** tile on the Dashboard. A red CAMERA light shows whenever the webcam is on, and no frames are ever saved.
  - It needs a one-time INSTALL (OpenCV + MediaPipe) and is paused while gaming.

## New in 5.2
- **Fixed:** the same pop-up showing several times, such as one search popping up 6 times. Identical pop-ups are never repeated within 3 minutes, and repeats refresh the card that's already up instead of stacking.
- **New pop-up types, each with its own colour and entrance:**
  - **Search results** with site icons. Click one to open it in ORION's browser window.
  - **Countdown** for events, with a live minutes ring.
  - **Weather** with a 3-day strip.
  - **Progress ring** for goals.
  - **Big number** for stats.
  - **Tickable checklists** and **numbered steps**.
  - ORION can use all of these when it talks to you.
- **Phone:**
  - **Pop-ups from the PC now appear on your phone too.** They slide down from the top (swipe up to dismiss) and collect in a new **From ORION** feed on Home.
  - All cards in chat are redesigned with the new types and buttons.
  - Repeat cards are skipped.
- **Ride mode removed:** the card, the quick-settings tile and the "ride mode" command. Reading messages and replying by voice now works during any call with ORION. "When will I get to school?" still works.

## New in 5.1: pop-ups, rebuilt
- **New holographic pop-ups:**
  - They unfold in 3D with a beam firing from the reactor.
  - Each has an icon, title and time, and charts animate in.
  - They stack neatly on either side of the reactor without covering each other.
- **Buttons on pop-ups:** "Snooze 10 min", "Plan tonight", "Focus 25", "Read it to me", "Quiz me on this"… ORION adds follow-up buttons to its own cards too.
- **Hover to keep it:** hovering pauses it, a countdown line shows how long it'll stay, 📌 pins it, and clicking it opens it big.
- **Today's feed:** the 🔔 drawer lists every pop-up from today, and you can click one to reopen it.
- **New toasts:** icons and a countdown line, click to dismiss, and at most 4 at once.

## New in 5.0: the PC interface, rebuilt
- **Two styles:** the upgraded **Jarvis HUD** (default), or **Aurora**: soft glass, rounded panels, a glowing orb and moving colour behind it. Switch with the ◐ button in the top bar or in Settings.
- **Bigger, calmer text,** with a text-size setting (Small, Normal, Large, Extra large).
- **Less clutter:** *Simple layout* hides the telemetry column. The ◧ button in the top bar brings it back.
- **More alive:**
  - Light runs round the panel edges.
  - The reactor tilts towards your mouse and breathes faster while thinking.
  - Dashboard tiles fly in one after another.
  - Each message arrives with a scan-line.
- **New chat look:** ORION speaks from a holographic panel with a spinning mini-reactor avatar. Your messages sit on the right, the "thinking" indicator is a waveform, and the input bar is bigger.
- **Every page has its own identity:** Scholar purple, CEO gold, Gaming red, Schedule teal, Health green… each with a big animated banner.
- **ORION pops things up by itself** (with a gold ◆ ORION tag):
  - A greeting card with weather, today and homework when you sit down.
  - "While you were away" when you come back: what it did, jobs finished, DMs.
  - Events starting in 15 minutes and homework due tomorrow.
  - Rain coming in the next couple of hours.
  - A nudge when YouTube or TikTok passes 90 minutes in the evening.
  - Money-goal milestones.
  - Each one shows once, never while you're gaming or the screensaver is on, and they can be turned off in Settings.

## New in 4.5 (PC)
- **Holographic screensaver:** when you're away (same time as autonomous mode, 30 min by default), ORION goes full-screen with a rotating wireframe globe, orbit rings, data arcs, a big clock, weather, what's coming up, money and homework, live CPU/RAM, and a running feed of what it's doing on its own. Move the mouse and it's gone. It never appears while you're gaming, watching a video or playing music, or when another app is full-screen. Elements drift slowly so nothing burns in. Settings › screensaver; "show the screensaver" or the button on the Dashboard shows it any time.
- **PC tools** (Dashboard, or just ask):
  - Tidy Downloads into folders, which can be undone.
  - Biggest files, duplicate finder (report only), copy all the text on screen (OCR) and a colour picker.
  - Internet speed test and startup apps.
  - Window layouts ("put Discord and Chrome side by side", quarters, thirds, focus).
  - Per-app volume ("turn Discord down", "mute Chrome").
- **Ambient sounds for focus:** rain, brown noise, white noise, waves, café or space, generated live ("play rain for 45 minutes").
- **Habits:** track habits with streaks and a 7-day strip on the Dashboard ("done revise 30 min").
- **Break reminders:** after 50 minutes of non-stop PC use you get a stretch, water or eyes reminder. Never while gaming, and you can turn on voice in Settings.

## New in 4.4: the Skill Library (505 skills)
- **505 ready-made skills.** ORION finds and uses the right one by itself. You can also browse them (PC: Skills page · phone: More › Skills), or type **/name** in chat, e.g. `/convert 5 miles to km`, `/quadratic 1 -5 6`, `/essayplan How is ambition presented in Macbeth?`.
- **41 instant tools (no AI, no internet):** unit converter, percentages, VAT, discounts, savings growth, savings goals, split the bill, £/hour, break-even, days until, age, time zones, password generator, decide-for-me, dice, word counter, text case, base64, hashes, JSON check, colour codes, number bases, regex tester, Roman numerals, prime factors, HCF/LCM, quadratic and simultaneous equation solvers, Pythagoras, speed/distance/time, Ohm's law, energy cost, density, score → grade, pomodoro plans, revision time splits, bike ride time and more.
- **School:** essay plans (PEEL), quote banks, poem and unseen poetry analysis, creative writing, SPaG fixer, command words, mnemonics, mind maps, revision sheets, exam questions with mark schemes, required practicals, maths step-by-step, history sources and interpretations, geography case studies, MFL translation and speaking, trace tables, pseudocode → Python, RE arguments.
- **27 GCSE subjects × 12 helpers each:** explain, quiz, exam question, common mistakes, memory tricks, revision sheet, key words, worked example, flashcards, grade 9 tips, 20-minute session, topic checklist.
- **Money & content:** idea check, cold emails/DMs, follow-ups, sales pages, product descriptions, brand names, slogans, pricing, customer and review replies, negotiation, SWOT, lean canvas, gig listings, automation ideas, budgets, payment reminders, hooks, video scripts, YouTube titles, thumbnails, content calendars, stream plans, captions, sponsor pitches.
- **Code:** explain, debug, refactor, tests, review, README, commit messages, regex, SQL, Roblox Luau, Discord bots, PowerShell, git rescue, APIs, Minecraft plugins.
- **Gaming:** low-end PC settings (tuned for an i5-2400 + GT 710), loadouts, strategy plans, team names, brackets, patch notes.
- **Life:** reply drafts, apologies, birthday messages, gifts, days out, packing, cheap meals, decisions, disagreements, habits, pep talks, journal prompts, claim checking, both sides of a debate, bike fixes, formal emails, letters to school, complaints, thank-yous, news explained, wind-down plans.
- **Rewrite in 20 tones and turn text into 20 formats:** JARVIS butler, formal, funny, Gen Z, Shakespeare… · bullets, table, thread, TikTok script, quiz, timeline, FAQ, speech, revision notes…
- **Future:** college applications, a first CV, part-time job applications, interview prep, work experience emails.

## New in 4.3: the phone, redesigned
- **Portrait, "Aurora":** a new look with a living orb, glass cards, big type, slowly moving colour in the background and a floating dock. The **orb button** in the middle opens chat. Tap it again to talk, or press and hold it from anywhere to talk straight away. PC moved into More.
- **Landscape, "Cockpit":** a completely different layout. It has an angular HUD with a side rail, plus an instrument cluster showing a big clock, CPU, RAM and battery gauges, next event, homework, ride, mode and jobs. Everything else is laid out in two columns, and calls/rides become a dashboard.
- **Now Bar (S23, One UI 8 / Android 16):** Ride mode shows a live ETA on the lock screen Now Bar and status-bar chip ("School in 6 min · arrive 08:31 · before the bell"), with a progress bar. Calls with ORION show there too. On older software it's a normal ongoing notification.

## New in 4.2
**Phone**
- **Messages read out on rides:** Snapchat, WhatsApp, Instagram, Discord and texts are read out in Ride mode. Say "ORION, reply …", and ORION reads it back and only sends when you say yes. Turn it on in ⚙ › Hands-free and allow message access. It never reads messages at school, and @everyone/@here pings are ignored.
- **Quiz me on the ride:** "ORION, quiz me" asks 10 flashcards through your earbuds. Answer out loud with no need to say the name, and the results go back to your PC.
- **Quick Settings tiles:** pull down from the top of the screen, tap ✏️ and add *Ask ORION*, *Ride mode* and *Skip song*.
- **Today strip** on Home: next event, homework, rain at home time, your usual ride. Plus a rain warning 20 minutes before school ends.
- Pull down to refresh, swipe left/right to change tabs, search your chat, and vibration on taps.
- Study on the phone: predicted grades, **mark my essay / maths working** (or a photo of it), and **flashcards from photos of your notes**.
- Money on the phone: Money Wrapped, goals and a quote calculator. Gaming Wrapped is on the Games page.

**PC**
- **Predicted grades** per subject, plus exactly how far off the next grade you are and what to focus on.
- **Mark my work:** an essay marked like a GCSE examiner (grade, fixes, model paragraph), or maths working checked line by line.
- **Photo → flashcards** in Study › New deck.
- **Quote calculator** (never undercharge), **Money Wrapped** and **Gaming Wrapped**.
- **Bedtime nudge:** 10 minutes before the PC usually goes off, ORION reminds you, saves and syncs your phone.

## New in 4.1: the Jarvis interface
- **Boot-up sequence:** the arc reactor assembles, real system checks run (brains, memory, voice, mic, phone link, sync, homework, jobs) and ORION comes online. Click or press Esc to skip (Settings › skip boot gives a quick version).
- **Power-down sequence:** the power button now powers ORION down properly: it saves, syncs your phone and laptop, says goodbye, and the screen collapses like an old TV.
- **Pop-up browser windows:** when ORION uses its hidden browser, a holographic window pops out showing it live, then shows what it **found**. Drag it around, pin it, make it full size, minimise it to the dock, or close it (✕ or Esc). You can also drive it yourself: click the page to click, scroll to scroll, type an address, type into the page, or open it in Chrome.
- Say **"close that"** or **"tuck those away"** and ORION closes or minimises its pop-ups.
- Web searches pop up as result cards, plus a HUD frame, scan line and click ripples.
- **Fixed:** the live view from 4.0 never appeared because of a bug. It works now.

## New in 4.0
**One brain, everywhere**
- Your PC, laptop and phone share one conversation. Start on the phone, carry on at the PC. Link the laptop in Devices › Link to gaming PC; it uses the PC's brain when the PC is on and its own when it's off.

**Seeing what ORION does**
- **Holographic cards** pop up around the core while ORION talks: weather, steps, key points, charts, code. They show on the phone too.
- **Live view:** watch ORION's hidden browser, or your PC, while it works.

**Modes that do their job**
- **Butler** (everyday), **Serious** (getting real things done), **CEO** (money: goals, idea scorer, client CRM, £/hour, invoices, Monday money meeting), **Scholar** (school), **Hacker**, **Stealth**. Each mode has its own voice and tools. ORION switches mode by itself (Settings › Auto mode), and you can make your own modes.
- **Scholar: Exam Hall** writes practice papers, marks them (type your answers or photograph them), and remembers your weak topics. Mistakes come back a week later. It also has a **Tutor** and builds a **revision timetable** in your free time.

**Root, fixed properly**
- Root is now read through Windows accessibility (the system screen readers use), so ORION reads the real names and messages and presses the real buttons. It only reads Direct Messages: @everyone and @here pings in servers are ignored. A sent message is only reported as sent once ORION can see it in the chat. If anything's off, Health › Root diagnostic saves a report for fixing it.

**ORION on its own** (Devices › Autonomous mode)
- If you've been away for 30 minutes and aren't gaming, ORION gets on with useful jobs by itself (within hard safety limits) and messages or calls your phone if something matters.

**Gaming & schedule**
- Per-game profiles (apps to open and close), auto Stealth while gaming, a game doctor that calms CPU/RAM hogs, a wrap-up when you finish, and hold the controller's Back button to talk.
- A full week calendar: drag events to move them, see clashes and your school day.

**Your day**
- Built around your routine: wake 8:00, school 8:40–15:10, PC off about 20:30. Jobs run after school. At 20:00 the evening wind-down recaps your day, plans tomorrow and hands the **morning briefing to your phone**.

**Phone 4.0**
- Modes, the shared brain and cards on the phone.
- **Wake-up call** at 8:00 on school days, with weather, homework and the plan, plus "15 minutes" and "leave now" reminders based on how long your ride takes.
- **Ride mode:** hands-free chat on the bike. It pauses your music, times your ride and learns how long it usually takes. Ask "when will I get to school?".
- **Music control:** "skip", "pause", "louder" work with Amazon Music or any app.
- **School mode:** silent from 8:40 to 15:10.
- **Hands-free (beta):** "Hey ORION" offline wake word, and set ORION as your digital assistant to use it by holding your earbud.
- Exam Hall on the phone: sit papers and photograph your answers.
- Battery care: it checks in less often when the screen's off or the battery's low.

**Setup on the phone:** Settings › Hands-free: allow location, tap "Stop Samsung putting ORION to sleep" (choose Unrestricted), allow full-screen notifications, then optionally turn on "Hey ORION" and choose ORION as your assistant.

## New in 3.2
- **Fixed:** listening didn't stop when music was playing. ORION now turns music, videos and games down while you talk and puts them back afterwards (Settings › Listening). Its voice detection now tells your voice apart from steady music, and it stops listening if all it's hearing is music.
- **Dictation:** say "dictation mode" or press ✍ Dictate, and everything you say is typed into whatever window you're in. Say "new line" or "new paragraph" for line breaks, and "stop dictation" to finish.
- **Voice memos:** say "take a voice memo" and talk for as long as you like. It's saved to your notes.
- **Homework tracker:** "add maths homework due friday". It's on the Dashboard, the Study page and the phone, and it's in your morning report.
- **Weather:** "do I need a coat?". Free, no key. Set your town in Settings.
- **News:** BBC headlines for top stories, UK, tech, sport, football, Leicester and more.
- **Notes & ideas:** "note: video idea — …". Shown on the Brain page and the phone.
- **Clipboard history:** "what did I copy earlier?". Anything that looks like a password or key is never saved.
- **Screen time:** how long you spent in each app or site today, shown on the Dashboard.
- **File finder:** "find my Macbeth essay".
- **Ready-made scenes:** "goodnight", "good morning", "study time", "gaming time" and "what did I miss" (edit them on the Brain page).

## New in 3.1: talking to ORION
- **Talk for as long as you like** (up to 5 minutes). Tap the mic, Ctrl+Space or the hotkey once and just speak. No need to tap again.
- **ORION knows when you've finished.** When you pause, it quietly checks what you've said so far. If you sound mid-sentence ("…and", "um", "because"), it waits. If you sound finished, it sends. Say **"send it"** to send straight away, tap the mic to send early, or press **Esc** to cancel.
- **Live captions** show your words in the command bar as you talk.
- **Conversation mode:** after answering you by voice, ORION listens for your reply without needing the wake word. Say "thanks" or "that's all" to finish.
- **Interrupt by talking** (optional, best with headphones): start speaking while ORION talks and it stops to listen.
- **Better accuracy:** silence is trimmed, quiet mics are boosted, and Whisper is told the names you use (Root, Hatchlands, your mates).
- Settings › Listening has **Quick / Normal / Relaxed** pause handling and mic sensitivity. The phone app (chat mic and calls) works the same way.

## New in 3.0
- **Dashboard:** your PC, today's plan, jobs, revision, money, gaming and health on one screen.
- **Study:** flashcards with spaced repetition, "quiz me" out loud, focus sessions that block games and distractions, and exam countdowns.
- **Gaming:** hours played per game, a booster, "clip that" (Ctrl+Alt+C), break reminders, and a party planner that books games and invites friends on Root.
- **Ventures:** an earnings tracker, a Hatchlands dev queue built overnight, a lead finder for automation clients, and a content pipeline.
- **Brain & Memory:** ORION learns about you from your chats, sorts what it knows, picks the memories that matter for each message, notices things you ask a lot and turns them into **shortcuts**, and handles **missions** (big multi-step jobs in the background).
- **Health check:** every part of ORION is checked, each with a FIX button. Cloud backup and restore are included.
- **Calls:** ORION rings your phone when a job finishes or a reminder is due, even with the app closed. It respects quiet hours and stays silent while you're gaming. It also has **Find my phone** (rings loudly even on silent), plus clipboard and file sharing between your phone and PC.
- **Hidden browser by default:** web research happens out of sight, and pages only open on your screen when you ask to see them.
- **No hand-over:** if every AI is out of allowance, ORION queues the request and retries it automatically.
- **Mini mode:** a small always-on-top orb (click it to talk, double-click it to open ORION).
- **Lite profile** for 4 GB laptops, and the local brain now picks the best installed model automatically.


## Install / update
- **New PC:** unzip, then double-click **`1_SETUP.bat`**. It installs Python if needed, the packages, ffmpeg (video) and Tesseract (screen reading), and adds a Desktop shortcut.
- **Updating from 1.x:** unzip over your old ORION folder and run `1_SETUP.bat` again. Your settings, memory, schedule, projects and skills are kept.
- **Optional:** `2_INSTALL_LOCAL_BRAIN.bat` (offline AI), `4_INSTALL_VOICE_EXTRAS.bat` (wake word + Voice ID).

## The left dock
| Page | What it does |
|---|---|
| **Comms** | Chat, with quick buttons. Replies stream in and are spoken aloud. |
| **Dashboard** | Everything at a glance. |
| **Study / Gaming / Ventures** | See "New in 3.0". |
| **Brain** | Memories, shortcuts and habits. |
| **Health** | Checks, fixes and cloud backup. |
| **Autopilot** | Give it a goal and it plans, builds, tests and fixes on its own. You can also say "autopilot: …". |
| **Schedule** | Bookings, repeats, reminders, busy/DND blocks and a daily briefing. |
| **Root** | Your Root DMs: check messages, AFK mode, in-game replies and an activity log. |
| **Studio** | The video editor: auto-cut, captions, Shorts and titles/tags. |
| **Skills** | Abilities ORION has taught itself. |
| **Devices** | Phone/laptop access, phone notifications, sync, wake word, Voice ID and updates. |

**Ctrl+K** opens the command palette, **Ctrl+Space** is push-to-talk, **Ctrl+Alt+Space** is push-to-talk inside games, and **Esc** stops.

## Built-in browser (2.0.1)
ORION has its own hidden web browser. It can read sites that need JavaScript, search, click and fill in forms. Say things like "go on Vinted and find the cheapest Nike tech fleece", or "show the browser" to watch it, or to log in to a site yourself. It never types passwords or card details, and never presses buy/pay buttons.

## Root (your account)
ORION uses the Root desktop app the way you would: it looks at the window and clicks and types. It never uses tokens or hacks, and never changes Root's code, which keeps it within what Root's team approved.
- "check my messages" reads your DMs **in the background**, without interrupting you.
- "tell Sam I'm on in 10" opens the DM, sends it, and snaps back to what you were doing (about 1 second).
- **AFK mode** ("I'm afk until 8"): ORION answers friends as *your assistant*, tells them when you're back, and books games into your schedule. Friends **cannot** make it do anything else. Their messages are never treated as commands.
- **Gaming:** while you're in a game, ORION replies to DMs and tells you what happened when you finish.
- The first time it uses Root, it learns where the buttons are, then remembers (`data/root_layout.json`). If Root updates its layout, delete that file.
- Reading DMs needs a **vision brain**. Groq's vision models are tried first; adding a free **Gemini** key in Settings makes it much more reliable.

## Studio
Pick a video, or leave it blank to use your newest video in Videos/Downloads. Renders use the CPU, so a 10-minute 1080p video takes about 10–20 minutes, and STOP cancels. Shorts come out at 1080×1920 with big captions. Captions need the Groq key (for Whisper).

## Devices
- **Calls:** in the phone app's ⚙ settings, leave *Stay linked in the background* on. Android may ask you to allow notifications and *full-screen notifications*. Allow both so ORION can ring you.
- **Phone and laptop access:** turn it on, install **Tailscale** (free) on this PC and your phone with the same account, then open the shown address on your phone and enter the PIN. If Windows asks about the firewall, allow *Private networks*.
- **Phone notifications:** install the free **ntfy** app and subscribe to the topic shown.
- **Sync:** paste a GitHub token with the `gist` scope. Memory and schedule are then shared across your PC, laptop and phone through a private Gist.
- **Wake word:** say "Hey Jarvis" (built-in, offline). A custom "Hey ORION" model can be added later in `data/wakeword/`.
- **Voice ID:** read 3 sentences and ORION ignores other voices.
- **Updates:** ORION checks `Kiyan12121/orion` releases and installs new versions in one click.

## The phone app (APK)
The code lives in `mobile-app/`, and `.github/workflows/release.yml` builds it. Push a tag like `v2.0.0` to the GitHub repo, or press **Run workflow** under Actions. GitHub then builds **ORION.apk** and the desktop update zip and attaches both to a Release. On your S23, download the APK and allow "install unknown apps" for your browser the first time. When your PC is off, the app still chats using its own Groq key, and PC jobs are queued until the PC is back.

## Safety
- There's a blocklist of commands that could wreck Windows or your drives, which ORION always refuses.
- File changes are backed up, and **UNDO** restores them.
- Every action is logged in `data/activity.log`.
- Safe mode (optional) asks before risky actions.
- Remote access requires a PIN and locks out after 8 wrong guesses.
- **Emergency stop for mouse automation:** slam the mouse into a screen corner.

## Troubleshooting
- **Crash or blank window:** check `data/orion.log`, and install the Microsoft Edge WebView2 Runtime.
- **Root reading fails:** add a Gemini key, make sure Root is open (not minimised to the tray), and delete `data/root_layout.json` if clicks miss.
- **No voice:** check the speaker icon, make sure you're not in Stealth mode, or switch Settings → Engine to Offline.
