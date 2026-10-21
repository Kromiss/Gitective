# Gitective

Gitective is a desktop application that checks whether the merge requests of
your GitLab repositories follow your team's process. It also detects commits
pushed straight to a branch without any merge request.

It is written in Python using only the standard library: there are no
packages to install.

## Requirements

- Windows (also tested on Linux)
- Python 3.11 or newer, with Tk. Tk is included by default in the python.org
  Windows installer.
- A self-hosted or gitlab.com instance
- A GitLab personal access token with the `read_api` scope only

## Installation

1. Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/windows/)
   if it is not already there (`python --version` in a terminal). In the
   installer, keep **tcl/tk and IDLE** checked (it is by default) and tick
   **Add python.exe to PATH**.
2. Get the code: on GitHub, **Code → Download ZIP** and unzip it, or
   `git clone https://github.com/Kromiss/Gitective.git`.
3. Copy the folder anywhere on your computer (it holds `main.py`).
4. Start the application:
   - on Windows, double-click `main.pyw` (no console window), or
   - run `python main.py` from a terminal.

On first launch, a wizard asks for:

1. the URL of your GitLab instance;
2. your token;
3. a connection test;
4. the repositories to inspect.

You can skip the wizard, and you can run it again later from the **Config**
tab.

### Getting a GitLab token (`read_api`)

Gitective only reads GitLab: give it a personal access token with the
`read_api` scope and nothing else.

1. Sign in to your GitLab instance.
2. Click your avatar (top left on recent versions, top right on older ones),
   then **Edit profile** (or **Preferences**).
3. In the left menu, open **Access tokens** (named **Personal access tokens**
   on recent versions), then **Add new token**.
4. Fill in:
   - **Token name**: e.g. `Gitective`;
   - **Expiration date**: as your instance allows (often one year at most);
   - **Scopes**: tick **`read_api`** only.
5. Click **Create personal access token** and copy the token right away
   (it starts with `glpat-`): GitLab shows it only once.
6. Paste it in the wizard or in the **Config** tab, then click
   **Tester la connexion**.

Direct link: `https://<your-gitlab>/-/user_settings/personal_access_tokens`
(on GitLab before 16.0: `https://<your-gitlab>/-/profile/personal_access_tokens`).

The token sees exactly what your account sees: repositories you cannot read
in GitLab will not appear in Gitective. When it expires, create a new one
and replace it in the **Config** tab. If the **Access tokens** page is missing,
your administrator has disabled personal tokens: ask them.

## Configuration

Every setting is editable in the **Config** tab and saved to `config.json`,
next to `main.py`. The tab has three sub-tabs: **Général** (connection,
repositories, theme, language, notifications, people), **Règles** (custom
rules, ticket matching, weights and thresholds, rule tester) and **Avancé**
(SSL, simultaneous requests, synchronisation, Branches tab, startup, local
database). Hover the ⓘ next to a setting to see what it does and its default
value. Changed sub-tabs show a dot and **Enregistrer** shows the number of
pending changes; leaving the tab with pending changes asks whether to save,
discard or stay.

> The token is stored in plain text in `config.json`. Give it the `read_api`
> scope only, and keep the file private.

| Setting | Purpose |
|---|---|
| URL, token, SSL verification | Connection to GitLab. You can disable SSL verification for an instance that uses an internal certificate. |
| Simultaneous requests | Number of GitLab requests sent in parallel for per-commit and per-MR lookups (1–16, default 6). Lower it if your instance answers with HTTP 429. |
| Custom rules | Any number of regex checks (see below). |
| Ticket matching | Regex of the ticket link (searched in the description) and regex of the ticket number, each with a **group to extract** (0 = the whole match, N = capturing group N: with `(#)(\d+)`, group 2 gives `42` for `#42`). The number found in the title must equal the number found in the link. Custom rules have the same group field; the rule tester shows the extracted value. |
| Weights and thresholds | Each rule's weight in the score, and the color thresholds (green ≥ 100 %, orange ≥ 50 % by default). |
| Repositories | The repositories to inspect, with the branch watched for commits pushed without an MR, and a **CI attendue** box for repositories that run a CI (see "Green pipeline"). |
| People | Groups several GitLab accounts and Git identities under one person. |
| Theme | Default, Light, Dark, Windows 95, Matrix or Colour-blind (Daltonien). Default is a dark navy theme with a turquoise accent. Colour-blind is made for deuteranopia and protanopia (blue / yellow / vermilion score levels). Windows 95 uses soft off-white cards and pale level colours; Matrix keeps everything green but readable: bright for good, dimmed for medium, inverse video for low and KO. In every theme each score is also drawn as a 3-bar gauge (3 bars good, 2 medium, 1 low), weekly quality bars are plain / dotted / hatched and chart curves are dashed, so colour is never the only cue. |
| Language | Français (default) or English. Applied at the next start of Gitective. |
| Automatic synchronisation | How often Gitective updates its database from GitLab, in minutes (default 5), even when minimized. |
| Desktop notifications | New merges on the tracked repositories, MRs assigned to you or awaiting your review, your own MR merged, and (off by default) every new MR of the tracked repositories. |
| Merged by the assignee | Tick to count the RC-06 rule (see below) in the score; off by default. |
| Start with Windows | Starts Gitective minimized when you log in to Windows, so the synchronisation and notifications run all day. Stored in your user's registry (`HKCU\...\Run`), no admin rights needed. |

### Custom rules

Each rule has:

- a **name**, which becomes the column title;
- an **inspected field**: title, description, source branch, target branch or
  commit messages;
- a **condition**: *must match* or *must not match*;
- a **regex**;
- a **weight**;
- an **active** switch.

The regex may match anywhere in the field. Use `^` and `$` to anchor it.

A commit-message rule passes only when every commit of the MR satisfies it.
It needs one extra GitLab request per MR; results are kept in the local database.

Examples:

| Name | Field | Condition | Regex |
|---|---|---|---|
| Title format | Title | must match | `^\[[A-Z]+-\d+\] .+` |
| Ticket link | Description | must match | `https://jira\.example\.com/browse/[A-Z]+-\d+` |
| Branch naming | Source branch | must match | `^(feature\|fix)/` |
| No WIP | Title | must not match | `(?i)\bwip\b` |
| Commit prefix | Commit messages | must match | `^[A-Z]+-\d+` |

For ticket matching, if the ticket regex contains a named group `ticket`, only
that group is compared. For example, `#(?P<ticket>\d+)` compares the number
without the `#`.

The **rule tester** in the Config tab checks sample values against your rules
before you save.

### Built-in rules

- **Ticket number**: the ticket number in the title must equal the one in the
  description link.
- **Merger ≠ author**: an MR must not be merged by the person who wrote it,
  whichever of their accounts they use. This rule is N/A for MRs that are not
  merged.
- **Green pipeline**: when the MR was merged, every CI status of its last
  commit had finished successfully. It reads the commit statuses GitLab
  stores, so it covers GitLab CI and external CIs that report to GitLab, such
  as Jenkins with its GitLab plugin (`gitlabCommitStatus` /
  `updateGitlabCommitStatus`). For each status name, only the last one
  created before the merge counts; statuses marked `allow_failure` are
  ignored. A failed, canceled or still running status, or no status at all,
  is KO; hover the cell to see which one. The rule is N/A for MRs that are not
  merged and for repositories whose **CI attendue** box is not ticked.
- **Merged by the assignee** (optional, ticked in the Config tab): the person
  who merged is one of the assignees, whichever of their accounts they used.
  N/A for MRs that are not merged or have no assignee. Even when the rule is
  off, the merger cell shows **≠** in orange when someone else merged.

The score is the weighted share of passing rules among the applicable ones.

## Usage

**Overview tab**

The first tab, shown at launch. It is a dashboard of every tracked
repository, designed to stay on screen; it fits a 1920 × 1080 display.

- **Latest merges**: the most recent merged MRs, grouped by day, with their
  repository, author → merger and score. Today's merges are highlighted. On
  a busy day, each merge takes one line so the whole day fits; long titles
  are cut so the repository and people stay visible. Click a merge to open it
  in the Merge Requests tab, selected with its detail panel.
- **Merges per day**: this week and last week, Monday to Sunday.
- **Average score** of the MRs merged in the last 30 days, with the change
  from the 30 days before.
- **Merged MR quality per week**: the last 12 complete weeks, split by score
  color.
- **Repository ranking** by average score over 30 days, on two columns.
- **Broken rules**: KO count per rule over 30 days.
- **Created / merged MRs per week** over the last 12 complete weeks.

The tab is redrawn after each automatic synchronisation (see Configuration).
Press **F11** to toggle full screen, on the screen holding the window.

**Merge Requests tab**

- Filter by state (Merged, Open, Closed, All or Direct commits), dates
  (`DD/MM/YYYY`), "Since yesterday", repositories, authors, assignees and
  reviewers and, for merged MRs, mergers.
- **All** lists merged, open and closed MRs together, with a State column;
  its dates filter on the creation date.
- **Total** (Merged, All and Direct commits) removes the date limit: only the part
  of the history missing from the local database is read from GitLab, with a
  progress bar.
- **Réinitialiser les filtres**, next to Refresh, sets every filter back to
  "all", the dates to "Since yesterday" and empties the search. The state,
  page size and sort are kept.
- Drafts are shown for open and closed MRs with a **BROUILLON** label; the
  **Brouillons** filter includes, excludes or shows only them. They never
  count in the average score, the statistics or the overview.
- Click a row (not its title) to open the **detail panel** on the right:
  whether the MR is ready to merge (conflicts, pipeline, discussions,
  approvals, commits behind the target), people, score with the reason of
  each KO, failed jobs with the end of their log, open discussions and
  changed files. Up / Down arrows move to the previous / next MR, Escape
  closes the panel. Drag its border to resize it; the width is remembered.
- Type in **Search** to filter as you type, case-insensitive. It looks in the
  title, description, author, merger, repository and branches, and finds an
  MR by the start of a SHA, from the first character: merge, squash or head
  commit, or any commit of the MR already in the local database. The matching
  SHA is shown before the title. In the Direct commits state, it looks in the
  message, SHA, author and repository.
- Click a title to open the MR in your browser.
- Hover a red **KO** cell to see why the rule failed.
- Click a column header to sort the whole list.
- Columns fit their title when the window opens. Drag a header border to
  resize a column and double-click the border to fit it again. Widths are
  saved in `config.json`; this works in every table.

**Your MRs: badges and notifications**

Gitective reads who owns the token (shown in the Config tab) and gives everyone:

- three **badges** at the top right, **Assignee**, **Reviewer** and
  **Author**: open MRs where you have that role, drafts apart. Assignee and
  Reviewer show a red dot counting the new ones and cover every repository
  you can read, tracked or not ("(not tracked)"); Author covers your open MRs
  of the tracked repositories. Click a badge to see those MRs in the Open
  state. The window title shows the number of new MRs, e.g. "Gitective (3)";
- a **New** column on the open MRs;
- **desktop notifications** in the bottom-right corner of the screen, even
  when Gitective is minimized: new merges, MRs assigned to you or awaiting
  your review, your own MR merged by someone else, and, if you tick it,
  every new MR of the tracked repositories (checked at each automatic
  synchronisation). Each one shows the people, the repository and the MR's
  score, its left stripe in the score's color. Click one to open the MR;
  its gear icon (⚙, under the close cross) opens the Config tab with the
  notification switches highlighted. The taskbar button also flashes for
  assigned MRs. Notifications only appear while Gitective is running.

**Direct commits** (a state of the Merge Requests tab)

Lists the commits on each watched branch that are not linked to any MR, for
the chosen dates.

**Branches tab**

Lists the branches of the tracked repositories, to remind their authors to
open an MR or delete them. Each branch shows its last commit (`12/09/2026 (34 j)`),
the author of that commit, every MR whose source branch it is (click one to
open it) and a single state: **Supprimée** (gone from GitLab, dimmed),
**Mergée non supprimée** (merged, or one of its MRs is merged), **Morte**
(no commit for more than 30 days, set in the Config tab) or **Active**.
The default branch, protected branches and names matching the exclusion
regex (Config tab, `^(main|master|develop.*)$` by default) are hidden.
Filter by name, author, repository and state; **Copier la liste** copies the
filtered branches, grouped by author, as Markdown.

**Tags tab**

Lists the tags of the tracked repositories with their message, GitLab release
notes, date, commit and commit author. Filter by repository, text (name,
message, notes, start of the SHA) and period. Click a row to open the
**detail panel**: full message, pointed commit and its MR when known, release
notes and the latest pipeline of the tag with the end of the first failed
job's log. Tags deleted from GitLab stay listed, labelled **SUPPRIMÉ**.

The **Comparer** sub-tab lists the MRs delivered between two versions. Add a
line per repository, then choose **Current** (a tag or a branch) and
**Référence** (a tag): the line is computed at once from the Git history, not
from the dates, and shows the number of MRs, commits without MR, their average
score and a warning when the reference holds commits missing from Current.
Click a line to see its MRs, commits without MR and that divergence in the side
panel; **Copier en Markdown** copies every line for release notes. Lines are
remembered, and a comparison already computed needs no GitLab request.
A cherry-picked commit is not linked to its original MR.

Branches and tags are read again at each synchronisation.

**Choosing repositories**

The list of projects visible to your token is kept in the local database,
so the picker opens instantly. Click **Recharger la liste** to read it again from
GitLab. Ticked repositories are listed first.

**Statistics tab**

Switch between **Par personne** and **Par dépôt**; the choice is remembered.

Per person: MRs created and merged, average score, KO count per rule,
commits pushed without an MR, time from creation to merge, and, for mergers,
time from the last commit to the merge. Delays are medians in business days; hover them for
the average, minimum and maximum. The **Rôle** column says whether the person can
merge (Mergeur) or not (Dev); hover "Mergeur" to see the repositories. It is
computed from the project members and the protection rules of the watched
branch. A weekly score chart is shown below:
one global curve, plus one curve per selected person.

Per repository: the same figures for each tracked repository, with one chart
curve per repository selected in the repository filter. Click a repository to
see its per-person statistics. The people filter restricts the MRs and
commits counted.

The direct commits of the period are searched like in the Merge Requests tab;
a progress bar is shown the first time.

**Local database and refresh**

Everything read from GitLab is kept in `gitective.db` (SQLite), next to
`main.py`. Changing page, sort or filter reads the database; GitLab is only
asked for what is missing.

- At launch, every few minutes (automatic synchronisation) and with **F5** or
  the Refresh button, Gitective asks GitLab only for what changed since the
  last synchronisation. The Refresh button also downloads the avatars again.
- Data that can no longer change is never read twice: the commits and CI
  statuses of merged MRs, and whether a commit belongs to an MR.
- Changing a rule, a weight or a person mapping recomputes the display
  without any GitLab request.
- When the instance cannot be reached, the stored data is shown and a banner
  gives the date of the last synchronisation.
- **Vider la base locale** in the Config tab deletes every stored row. The
  database belongs to one instance: changing the URL empties it, after
  confirmation.
- If the file is unreadable or corrupted, Gitective offers to recreate it and
  reads everything again from GitLab.

You can delete `gitective.db` at any time; it is rebuilt from GitLab.

Errors are shown in a banner at the top of the window: invalid token, network,
SSL, missing branch, and so on. Rate limiting (HTTP 429) and timeouts (30 s)
are retried automatically after 2, 4 and 8 seconds before an error is shown.

## Project layout

```
main.py / main.pyw            entry points
gitective/forge               GitLab requests, isolated: ForgeClient interface, GitLabClient, models, errors
gitective/database            local SQLite store, synchronisation, accessible projects list
gitective/review              MR control: rules and score, MR evaluation, direct commits, merge rights
gitective/repository          Branches and Tags tabs logic
gitective/reporting           statistics and Overview figures
gitective/shared              dates, people mapping, text search, parallel requests, avatars
gitective/settings            config.json loading and saving
gitective/ui                  Tkinter window, themes, background tasks, first-launch wizard
gitective/ui/tabs             one module per tab
gitective/ui/components       grid, pagination, chart, filter bar, tab bar, side panel, dialogs, small widgets
gitective/ui/alerts           error banner, desktop notifications, badges
gitective/assets              logo (svg, png, ico)
tests                         unit tests, same folders as gitective/
```

Run the tests with:

```
python -m unittest discover -s tests -t .
```

## Roadmap

- Standalone Windows executable that does not need a Python installation.
