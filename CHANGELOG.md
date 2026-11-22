# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-22

### Added

- Alarm journal CSV reader with automatic column, delimiter, encoding and time-format
  detection, state maps and an Ignition preset.
- ISA-18.2 / EEMUA 191 metrics: alarm rates per operator, peak 10-minute rate, floods,
  bad actors, chattering, fleeting, stale and standing alarms, priority mix, time to acknowledge.
- `alarmkpi report` with text, HTML (single file, no JavaScript), Markdown and JSON output,
  and `--fail-on` for scheduled checks.
- `alarmkpi demo`: a realistic one-week sample journal.
