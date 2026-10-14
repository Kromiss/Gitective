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

1. Copy the `gitective` folder anywhere on your computer.
2. Start the application:
   - on Windows, double-click `main.pyw` (no console window), or
   - run `python main.py` from a terminal.

On first launch, a wizard asks for:

1. the URL of your GitLab instance;
2. your token;
3. a connection test;
4. the repositories to inspect.

You can skip the wizard, and you can run it again later from the **Config**
tab.

## Configuration

Every setting is editable in the **Config** tab and saved to `config.json`,
next to `main.py`.

> The token is stored in plain text in `config.json`. Give it the `read_api`
> scope only, and keep the file private.

| Setting | Purpose |
|---|---|
| URL, token, SSL verification | Connection to GitLab. You can disable SSL verification for an instance that uses an internal certificate. |
| Simultaneous requests | Number of GitLab requests sent in parallel for per-commit and per-MR lookups (1–16, default 6). Lower it if your instance answers with HTTP 429. |
| Custom rules | Any number of regex checks (see below). |
| Ticket matching | Regex of the ticket link (searched in the description) and regex of the ticket number. The number found in the title must equal the number found in the link. |
| Weights and thresholds | Each rule's weight in the score, and the color thresholds (green ≥ 100 %, orange ≥ 50 % by default). |
| Repositories | The repositories to inspect, with the branch watched for commits pushed without an MR, and a **CI attendue** box for repositories that run a CI (see "Green pipeline"). |
| People | Groups several GitLab accounts and Git identities under one person. |
| Theme | Default, Light, Dark, Windows 95 or Matrix. Default is a dark navy theme with a turquoise accent. |
| Overview refresh | How often the Overview tab reloads the data on its own, in minutes (default 5). |

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

The score is the weighted share of passing rules among the applicable ones.

## Usage

**Overview tab**

The first tab, shown at launch. It is a read-only dashboard of every tracked
repository, designed to stay on screen; it fits a 1920 × 1080 display.

- **Latest merges**: the 20 most recent merged MRs, grouped by day, with
  their repository, author → merger and score. Today's merges are
  highlighted.
- **Merges per day**: this week and last week, Monday to Sunday.
- **Average score** of the MRs merged in the last 30 days, with the change
  from the 30 days before.
- **Merged MR quality per week**: the last 12 complete weeks, split by score
  color.
- **Repository ranking** by average score over 30 days, on two columns.
- **Broken rules**: KO count per rule over 30 days.
- **Created / merged MRs per week** over the last 12 complete weeks.

The tab reloads the data every few minutes (see Configuration). If another
tab is open at that moment, the reload waits until you come back to the
overview. Press **F11** to toggle full screen.

**Merge Requests tab**

- Filter by state (Merged, Open, Closed or Direct commits), dates
  (`DD/MM/YYYY`), "Since yesterday", repositories, authors and, for merged
  MRs, mergers.
- Type in **Search** to filter as you type, case-insensitive. It looks in the
  title, description, author, merger, repository and branches. In the Direct
  commits state, it looks in the message, SHA, author and repository.
- Click a title to open the MR in your browser.
- Hover a red **KO** cell to see why the rule failed.
- Click a column header to sort the whole list.
- Columns fit their title when the window opens. Drag a header border to
  resize a column and double-click the border to fit it again. Widths are
  saved in `config.json`; this works in every table.

**Direct commits** (a state of the Merge Requests tab)

Lists the commits on each watched branch that are not linked to any MR, for
the chosen dates.

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

- At launch and with **F5** or the Refresh button, Gitective asks GitLab only
  for what changed since the last synchronisation, and downloads the avatars
  again.
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
gitective/reporting           statistics and Overview figures
gitective/shared              dates, people mapping, text search, parallel requests, avatars
gitective/settings            config.json loading and saving
gitective/ui                  Tkinter window, themes, background tasks, first-launch wizard
gitective/ui/tabs             one module per tab
gitective/ui/components       grid, pagination, chart, filter bar, dialogs, small widgets
gitective/ui/alerts           error banner
gitective/assets              logo (svg, png, ico)
tests                         unit tests, same folders as gitective/
```

Run the tests with:

```
python -m unittest discover -s tests -t .
```

## Roadmap

- Standalone Windows executable that does not need a Python installation.
