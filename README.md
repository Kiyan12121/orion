# ORION 2.0 — Personal Intelligence System

## Install / update
- **New PC:** unzip, then double-click **`1_SETUP.bat`**. It installs Python if needed, the packages, ffmpeg (video) and Tesseract (screen reading), and adds a Desktop shortcut.
- **Updating from 1.x:** unzip over your old ORION folder and run `1_SETUP.bat` again. Your settings, memory, schedule, projects and skills are kept.
- **Optional:** `2_INSTALL_LOCAL_BRAIN.bat` (offline AI), `4_INSTALL_VOICE_EXTRAS.bat` (wake word + Voice ID).

## The left dock
| Page | What it does |
|---|---|
| **Comms** | Chat, with quick buttons. Replies stream in and are spoken aloud. |
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
