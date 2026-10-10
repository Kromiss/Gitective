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
| Custom rules | Any number of regex checks (see below). |
| Ticket matching | Regex of the ticket link (searched in the description) and regex of the ticket number. The number found in the title must equal the number found in the link. |
| Weights and thresholds | Each rule's weight in the score, and the color thresholds (green ≥ 100 %, orange ≥ 50 % by default). |
| Repositories | The repositories to inspect, with the branch watched for commits pushed without an MR. |
| People | Groups several GitLab accounts and Git identities under one person. |
| Theme | Light, Dark, Windows 95 or Matrix. |

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
It needs one extra GitLab request per MR; results are cached for the session.

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

The score is the weighted share of passing rules among the applicable ones.

## Usage

**Merge Requests tab**

- Filter by state (Merged, Open or Closed), merge dates (`DD/MM/YYYY`), "Since
  yesterday", repositories and authors.
- Type in **Search** to filter as you type, case-insensitive. It looks in the
  title, description, author, merger, repository and branches. The Commits
  without MR tab has the same field, which looks in the message, SHA, author
  and repository.
- Click a title to open the MR in your browser.
- Hover a red **KO** cell to see why the rule failed.
- Click a column header to sort the whole list.
- Columns fit their title when the window opens. Drag a header border to
  resize a column and double-click the border to fit it again. Widths are
  saved in `config.json`; this works in every table.

**Commits without MR tab**

Lists the commits on each watched branch that are not linked to any MR, for
the same dates as the Merge Requests tab.

**Statistics tab**

Shows, for each person: MR count, average score, KO count per rule and
average time from creation to merge. A weekly score chart is shown below:
one global curve, plus one curve per selected person.

**Refresh**

**F5** or the Refresh button clears the session cache, including avatars, and
reloads the data.

Errors are shown in a banner at the top of the window: invalid token, network,
SSL, missing branch, and so on. Rate limiting (HTTP 429) and timeouts (30 s)
are retried automatically after 2, 4 and 8 seconds before an error is shown.

## Project layout

```
main.py / main.pyw     entry points
gitective/api          generic GitLab REST client (GitLabClient), models, errors
gitective/core         rules, statistics, people mapping, caching, dates
gitective/config       config.json loading and saving
gitective/ui           Tkinter interface (one module per tab or widget)
gitective/assets       logo (svg, png, ico)
tests                  unit tests
```

Run the tests with:

```
python -m unittest discover -s tests -t .
```

## Roadmap

- Standalone Windows executable that does not need a Python installation.
