# Coding for Dummies

A from-zero guide to running and tinkering with this project. No prior coding experience
assumed. If a word is unfamiliar, check the [glossary](#glossary) at the bottom.

---

## 1. The 30-second picture

This project is a small program that runs **on your own computer**. It:

1. Connects to your bank and Robinhood (through a service called **Plaid**),
2. Saves what it learns into a file on your computer (a **database**),
3. Shows it all in a web page at `http://localhost:4000` — a page only *your* computer can see.

You don't need to understand the code to use it. You only need to type a few commands.

---

## 2. One-time setup

### Step 1 — Install Node.js

Node.js is the engine that runs this program (it's written in JavaScript).

- Go to [nodejs.org](https://nodejs.org) and download the **LTS** version.
- Run the installer and click "Next" through everything.

### Step 2 — Open a terminal

The terminal is a window where you type commands instead of clicking.

| Computer | How to open it |
|---|---|
| **Mac** | Press `Cmd + Space`, type `Terminal`, press Enter |
| **Windows** | Press the Windows key, type `PowerShell`, press Enter |

Check Node installed correctly by typing this and pressing Enter:

```bash
node --version
```

You should see something like `v22.11.0`. If you see "command not found", restart the
terminal (or your computer) and try again.

### Step 3 — Get the project onto your computer

**Easiest:** on the GitHub page, click the green **Code** button → **Download ZIP**, then
unzip it somewhere you'll remember, like your Desktop.

**If you have git:**

```bash
git clone https://github.com/rgsennett05/Finance-Coding.git
```

### Step 4 — Move the terminal into the project folder

The terminal is always "standing in" one folder. `cd` ("change directory") moves it.

```bash
cd Desktop/Finance-Coding
```

> Tip: type `cd ` (with a space), then drag the project folder from Finder/Explorer into the
> terminal window — it fills in the path for you. Press Enter.

Type `ls` (Mac) or `dir` (Windows) — you should see files like `README.md` and `package.json`.
If you do, you're in the right place.

### Step 5 — Install and start

```bash
npm install
npm start
```

- `npm install` downloads the building blocks this project depends on. Only needed once
  (or after you download a newer version of the project).
- `npm start` runs the app. The first time, it asks three questions — **you can press Enter
  to skip any of them**. Then your browser opens the dashboard.

**To stop the app:** click the terminal window and press `Ctrl + C`.

**To start it again tomorrow:** open a terminal, `cd` into the folder, `npm start`. That's it.

---

## 3. The commands, in plain English

Every command starts with `npm run` (except `npm start` and `npm test`, which are shortcuts).

| Type this | What it does |
|---|---|
| `npm start` | Runs the app and opens the dashboard |
| `npm run setup` | Asks the three setup questions again |
| `npm run sync` | Pulls fresh numbers from your linked bank/brokerage |
| `npm run signals` | Fetches the latest disclosed trades from investors you follow |
| `npm run follow -- list` | Shows who you're following |
| `npm run follow -- search "berkshire"` | Looks up a fund by name |
| `npm run snapshot -- --redact` | Makes a shareable page with dollar amounts hidden |
| `npm test` | Checks the code still works (safe to run any time) |

The `--` in `npm run follow -- list` just means "pass the rest to the program." Leave it in.

---

## 4. Trying it with fake money first

Out of the box the app uses Plaid's **sandbox** — pretend banks with pretend money. When the
"Link" window asks you to log in, use:

- Username: `user_good`
- Password: `pass_good`
- Code (if asked): `1234`

Nothing real is touched. Play around freely.

---

## 5. Where everything lives

Think of the project like a restaurant:

| Folder / file | Restaurant analogy | What it actually is |
|---|---|---|
| `public/` | The dining room | The web page you look at (`index.html`, `styles.css`, `app.js`) |
| `src/server.js` | The waiter | Takes requests from the page, fetches answers, brings them back |
| `src/analytics.js` | The kitchen | Does the math — net worth, diversification, dividends |
| `src/plaid/` | The supplier | Talks to your bank and Robinhood through Plaid |
| `src/signals/` | The newspaper | Reads public SEC and Congress filings |
| `src/db.js` | The pantry | Stores everything in a local database file |
| `scripts/` | The front door | The commands you type (`start`, `sync`, `follow`…) |
| `test/` | The health inspector | Automatic checks that the code still behaves |
| `.env` | The safe | Your private keys and settings. **Never share or upload this file.** |
| `package.json` | The menu | Lists the commands and the building blocks the project uses |

---

## 6. Your first code change

The safest place to start is the look of the dashboard.

1. Open the project folder in a code editor. [VS Code](https://code.visualstudio.com) is free
   and the most common choice: **File → Open Folder…** and pick `Finance-Coding`.
2. Open `public/styles.css`. This file controls colors, sizes, and spacing.
3. Change a color value (they look like `#161b24`) to something else, like `#3a1d24`.
4. Save the file (`Cmd + S` / `Ctrl + S`).
5. Refresh the browser tab. You'll see the change.

Changes to files in `public/` show up on refresh. Changes to files in `src/` need a restart:
press `Ctrl + C` in the terminal, then `npm start` again.

**Broke something?** If you downloaded with git, this undoes every change you've made:

```bash
git checkout .
```

If you used the ZIP, just download it again.

After any change, run `npm test`. If it ends with `fail 0`, you're fine.

---

## 7. When things go wrong

| You see | What it means | Fix |
|---|---|---|
| `command not found: npm` or `node` | Node isn't installed, or the terminal opened before it was | Install Node, then close and reopen the terminal |
| `ENOENT ... package.json` | The terminal isn't in the project folder | `cd` into the folder (Step 4) |
| `EADDRINUSE ... 4000` | The app is already running in another window | Find that window and press `Ctrl + C`, or just use the one that's running |
| Browser says "can't connect" | The app isn't running | Run `npm start` and leave that terminal open |
| `Cannot find module ...` | Building blocks weren't installed | Run `npm install` |
| A section of the dashboard is empty | That feature's key was skipped during setup | Run `npm run setup` and fill it in, or ignore it — everything else still works |

Stuck on something else? Copy the **entire** red error message and paste it into Claude or a
search engine. The first line and the last line usually say the most.

---

## Glossary

- **Terminal / command line** — a text window for typing commands to your computer.
- **Command** — a line you type and run by pressing Enter.
- **Folder / directory** — the same thing.
- **Node.js** — the program that runs JavaScript code outside a web browser.
- **npm** — comes with Node. Installs building blocks ("packages") and runs project commands.
- **Package / dependency** — code someone else wrote that this project reuses.
- **`localhost`** — your own computer. `localhost:4000` means "this computer, door number 4000."
- **Server** — a program that waits for requests and answers them. Here, it serves the dashboard.
- **Database** — a file that stores data in organized tables. This project's is `data/finance.db`.
- **API** — a way for one program to ask another for data (e.g. the app asking Plaid for balances).
- **API key** — a password that identifies you to an API. Keep it private.
- **`.env` file** — where this project keeps your keys and settings.
- **Sandbox** — a fake practice environment with pretend data.
- **git** — a tool that tracks every version of the code, so you can undo changes.
- **GitHub** — a website that hosts git projects online.
- **Bug** — anything the code does that it shouldn't.
