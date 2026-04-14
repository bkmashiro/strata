# Strata

**Environment Archaeology Tool** — Snapshot, diff, and debug your development environment state.

When your dev environment breaks and "it worked yesterday," the culprit is almost always something that changed beneath your code: an environment variable was overwritten, a port got hijacked by another process, a config file was silently modified, a Docker container died, or a package version drifted. Today, developers manually check each of these things one by one, wasting valuable debugging time on what should be an instant lookup.

Strata takes point-in-time snapshots of your entire environment state — environment variables, running processes, open network ports, config file checksums, disk usage, Docker containers, and installed package versions — and stores them in a local SQLite database. When something breaks, you diff any two snapshots and see exactly what changed. Think `git diff` but for your operating environment rather than your source code.

The tool is designed to be lightweight and non-intrusive. Snapshots take under a second, the database stays local, and sensitive values (API keys, passwords, tokens) are automatically masked. Run `strata snap` before deploying, after lunch, or on a cron job. When things go wrong, run `strata diff` and get your answer in seconds instead of minutes.

## Features

- **8 environment collectors**: env vars, processes, network ports, config files, disk usage, system info, Docker containers, package versions
- **Automatic sensitive value masking**: API keys, passwords, tokens, and secrets are detected and masked before storage
- **Label-based organization**: Tag snapshots with labels like `baseline`, `pre-deploy`, `friday-eod` for easy reference
- **Rich terminal output**: Color-coded diffs with change type indicators (+/~/-)
- **Doctor mode**: One-command comparison against a known-good baseline
- **Search across history**: Find when an environment variable or config changed across all snapshots
- **Collector filtering**: Snapshot or diff only the specific collectors you care about
- **SQLite storage**: All data in a single local file, easy to back up or share

## Installation

Requires Python 3.9+.

```bash
# From source
git clone https://github.com/bkmashiro/strata.git
cd strata
pip install -e .

# Verify installation
strata --version
```

## Quick Start

```bash
# Take your first snapshot
strata snap -l "morning"

# ... do some work, install packages, change configs ...

# Take another snapshot
strata snap -l "afternoon"

# See what changed
strata diff morning afternoon
```

The diff output will show you every environment change between the two snapshots, grouped by category and color-coded by change type.

## Usage

### Taking Snapshots

Capture the current environment state:

```bash
# Basic snapshot
strata snap

# With a label for easy reference
strata snap -l "pre-deploy"

# Only specific collectors
strata snap -c envvars -c network -c docker

# Specify root directory for config file scanning
strata snap --root /path/to/project
```

### Listing Snapshots

```bash
# List recent snapshots
strata ls

# Show more
strata ls -n 50
```

Output:
```
                    Snapshots
┌────┬────────────┬─────────────────────────┬──────┐
│ ID │ Label      │ Time                    │ Age  │
├────┼────────────┼─────────────────────────┼──────┤
│  3 │ post-fix   │ 2026-04-14 15:30:00 UTC │ 2m   │
│  2 │ pre-deploy │ 2026-04-14 14:00:00 UTC │ 1.5h │
│  1 │ baseline   │ 2026-04-14 09:00:00 UTC │ 6.5h │
└────┴────────────┴─────────────────────────┴──────┘
```

### Viewing Snapshot Details

```bash
# By ID
strata show 1

# By label
strata show pre-deploy

# The latest snapshot
strata show latest

# Drill into a specific collector
strata show latest -c envvars
strata show 1 -c network
```

### Diffing Snapshots

The core feature. Compare any two snapshots to see what changed:

```bash
# By IDs
strata diff 1 3

# By labels
strata diff baseline post-fix

# Compare to latest (default for second argument)
strata diff pre-deploy

# Filter to specific collectors
strata diff 1 2 -c envvars -c network
```

Output:
```
╭─ Environment Diff ───────────────────────────────────╮
│ baseline -> post-fix  (6.5h apart)                   │
│ Total changes: 5                                     │
│ envvars: +1 ~1 | network: +1 -1 | packages: ~1      │
╰──────────────────────────────────────────────────────╯

envvars
  + STRATA_DEMO_VAR: 'hello-world' (added)
  ~ PATH: '/usr/bin' -> '/usr/local/bin:/usr/bin'

network
  + Port 3000 now listening (tcp)
  - Port 8080 no longer listening

packages
  ~ node: v18.17.0 -> v20.11.0
```

### Doctor Mode

Compare the current environment against a saved baseline in one command:

```bash
# First run creates the baseline
strata doctor
# => "No baseline found. Creating one now..."

# Later runs compare against it
strata doctor
# => Shows diff against baseline

# Use a custom baseline label
strata doctor -l "prod-config"
```

### Searching History

Find when a specific key appeared or changed across all snapshots:

```bash
# When did DATABASE_URL change?
strata search envvars DATABASE_URL

# What ports have been listened on?
strata search network 3000

# Track package versions over time
strata search packages node
```

### Status

Quick overview of the Strata installation:

```bash
strata status
```

Shows database location, snapshot count, latest snapshot info, and which collectors are available on the current system.

### Deleting Snapshots

```bash
strata rm 5
strata rm old-baseline
```

### Custom Database Location

By default, Strata stores data in `~/.strata/strata.db`. Override with:

```bash
strata --db /path/to/custom.db snap
strata --db /path/to/custom.db diff 1 2
```

## Architecture

```
src/strata/
├── cli.py              # Click-based CLI with all commands
├── snapshot.py         # Snapshot creation orchestrator
├── storage.py          # SQLite storage layer
├── diff.py             # Snapshot comparison engine
├── display.py          # Rich terminal output formatting
└── collectors/
    ├── base.py         # Abstract collector interface
    ├── envvars.py      # Environment variables (with masking)
    ├── processes.py    # Running processes via /proc
    ├── network.py      # TCP listeners via /proc/net/tcp
    ├── files.py        # Config file checksums
    ├── disk.py         # Disk usage per mount point
    ├── system.py       # System info, memory, load average
    ├── docker.py       # Docker containers via CLI
    └── packages.py     # Runtime/tool versions
```

**Collectors** are the data-gathering layer. Each collector implements a `collect()` method that returns a flat dictionary of key-value pairs, plus a `diff_entry()` class method for human-readable diff formatting. Collectors declare availability via `is_available()` so missing tools (like Docker) are gracefully skipped.

**Storage** uses SQLite with two tables: `snapshots` (metadata) and `snapshot_data` (collector output as JSON blobs). This keeps the schema simple while allowing flexible collector data.

**Diff** operates on two snapshot dictionaries, comparing collector-by-collector. It produces a structured diff result that can be formatted for display or consumed programmatically.

**Display** uses the Rich library for color-coded, structured terminal output. Each collector type has its own color, and change types (added/removed/changed) use consistent symbols and colors.

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## Running the Demo

```bash
bash demo/demo.sh
```

The demo takes two snapshots with simulated environment changes between them, then shows the diff, search, and status features.

## License

MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
