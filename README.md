# ZFSguru Webmin Module

Webmin module for FreeBSD ZFS administration: pools, datasets, disks, services, ACL, system status, and benchmark workflows.

## Status

- Module name: `ZFSguru`
- OS support: FreeBSD (`os_support=freebsd`)
- Version: `0.1.1 beta`
- Author: `karmantyu` (`https://github.com/karmantyu/ZFSgame`)

## Main Features

- Advanced pool management (`advanced_pools.cgi`)
  - list/create/import/destroy pools
  - add/replace devices
  - scrub/history/properties
  - benchmark jobs with `View Log`, `Kill Job`, `View Results`
- Advanced dataset management (`advanced_datasets.cgi`)
  - list/create filesystem or volume
  - snapshots, clone, rollback (with confirmation)
  - quotas, properties, rename, delete
- Disk and hardware management (`disks.cgi`)
  - disk list, SMART, partition tools
  - disk benchmark jobs with log/results views
- Services (`services.cgi`)
  - NFS/SMB/SSH and related service helpers
- System status (`status.cgi`)
  - overview/cpu/memory/hardware/pool status/logs
  - Live VMStat tab with trend chart and selectable devices
- ACL manager (`acl.cgi`, `zfsaclmanager*.cgi`)

## Live VMStat (status.cgi)

Current behavior:

- Auto refresh default: `10s`
- Trend window default: `120s`
- Device trend selection supports up to `24` devices
- `Select all`, `Clear`, and `Apply` controls
- Colored device cards with current Busy% labels
- Server-side history/trend state stored in `/tmp` by `state_id`

Performance protections implemented:

- Auto-refresh minimum interval enforced
- Server-side sampling throttling/caching for heavy commands
- Trend rendering can use stored history even when no fresh iostat sample is taken in that tick

## Navigation and xnavigation

Many action links preserve `xnavigation=1` to keep the full Webmin frame UI. If you open URLs manually, prefer using links that already include `xnavigation=1`.

## Requirements

- FreeBSD with ZFS
- Webmin (module metadata requires >= 1.700)
- Root privileges for most operations
- Recommended tools (depending on features used):
  - `smartctl`
  - `gpart`, `camcontrol`, `diskinfo`, `dd`, `swapctl`

## Installation

1. Copy module folder into Webmin modules directory.
2. Ensure executable permissions on CGI files.
3. Reload/restart Webmin.
4. Open `Webmin -> Hardware -> ZFSguru` (menu placement may vary by theme/category).

## Configuration

Primary files:

- `module.info` - module metadata
- `config.txt` - command paths and feature toggles
- `acl.txt` - ACL feature flags
- `lang/en` - language strings

Notable `config.txt` options:

- command path overrides (`zpool_cmd`, `zfs_cmd`, `gpart_cmd`, etc.)
- feature toggles (`enable_benchmarking`, `enable_smart_monitoring`)
- safety confirmations (`require_confirmation_*`)
- cache/monitor settings (`cache_duration`, `monitor_*`)

## Project Structure

- `index.cgi` - dashboard
- `advanced_pools.cgi` - advanced pool workflows
- `advanced_datasets.cgi` - advanced dataset workflows
- `disks.cgi` - disk and benchmark workflows
- `services.cgi` - service management
- `status.cgi` - system status pages (includes Live VMStat)
- `system.cgi` - system/update pages
- `network.cgi`, `files.cgi`, `access.cgi`, `uefi.cgi`, `about.cgi`
- `zfsguru-lib.pl` - shared backend utilities
- `zfsguru_i18n.pl`, `zfsguru.css`, `zfsguru.js`
- `zfsaclmanager-lib.pl`, `zfsaclmanager*.cgi`

## Security Notes

- Inputs are validated and most user-visible values are HTML-escaped.
- Device/pool/dataset identifiers are validated/whitelisted before command execution.
- Destructive operations require confirmations in UI flows.

## Troubleshooting

### High CPU while using Live VMStat

- Increase `Auto Refresh Interval`.
- Reduce selected trend devices.
- Lower `Trend window` if rendering overhead is high.
- Verify no extra browser tabs keep the page auto-refreshing.

### No benchmark results shown

- Open `View Log` first and confirm benchmark summary lines exist.
- Ensure job status is `ok` and not `stale`/`failed`.

### Pool rename errors

Some systems/OpenZFS versions do not support `zpool rename` directly. Use export/import workflow if required by your platform.

## Development Notes

- Shebangs use `#!/usr/bin/env perl` for portability.
- Target runtime environment is Webmin on FreeBSD.
- For local linting outside Webmin, missing `WebminCore.pm` is expected unless Webmin libs are in `@INC`.

## Changelog (high level)

### 0.1.0 beta

- Webmin-native ZFSguru module structure finalized
- Advanced pool/dataset/disk workflows
- Job log/result actions (`View Log`, `Kill Job`, `View Results`)
- Live VMStat trend page with device selection and auto-refresh controls
- UI/navigation refinements and return-link consistency improvements
