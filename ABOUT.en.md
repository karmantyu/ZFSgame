# ZFSguru (Revival Module) - user guide

## Introduction

ZFSguru was a specialized FreeBSD-based storage distribution designed to provide an easy-to-use web interface for managing the system and ZFS pools.

This ZFS-oriented storage distribution aimed to bridge the gap between complex command-line administration and a user-friendly GUI. The interface was written largely in PHP and ran on the lighttpd web server. The project was created by submesa and later maintained by CiPHER. For unknown reasons, it was abandoned in 2016, with the final release being 0.3.1.

To pay homage to this great project, I decided to revive it as a 10th Year Anniversary edition—implemented as a module for the Webmin interface. It was a fun project and a solid proof of concept, heavily leveraging coding AI to port the codebase from PHP to Perl.

Please try this module as-is and use it with caution. Do not test it on production systems, as it has only been lightly tested so far. Have fun with it—responsibly.

This document explains the daily usage of the ZFSguru Webmin module.
The goal is to quickly understand which menu does what, and when to use each page.

## Quick start

1. Open the **ZFSguru** module in the left Webmin menu.
2. Main functional areas:
   - **Pool Management**: manage ZFS pools
   - **Dataset Management**: manage filesystems and volumes
   - **Disks & Hardware**: disks, SMART, benchmark tools
   - **Services**: NFS/SMB/SSH related settings
   - **System Status**: health, load, and trends
3. For destructive actions (destroy, wipe, rollback), always verify confirmations first.

## Dashboard (index.cgi)

The dashboard gives a fast overview:

- **Quick Access**: one-click shortcuts to common actions
- **ZFS Pools Summary**: pool state, usage, and capacity

Daily value:

- quick health check
- fast navigation to core admin pages

## Advanced Pool Management (advanced_pools.cgi)

Main tabs:

- **Pools**: list, status, action buttons
- **Create**: create a new pool
- **Import**: import existing/foreign pools
- **Destroy**: remove a pool
- **Benchmark**: run pool benchmark jobs

Common actions:

- **Replace Device**: replace failed/suspect devices
- **Scrub**: start/stop consistency scrub
- **Upgrade Pool**: upgrade pool features
- **Cache/SLOG**: attach or detach cache/log devices

Benchmark area:

- after run: **View Log**, **Kill Job**, **View Results**
- results are shown in visual charts

## Advanced Dataset Management (advanced_datasets.cgi)

Main tabs:

- **Datasets**: dataset list
- **Create Filesystem**
- **Create Volume**

Dataset actions:

- **Details**
- **Snapshots**
- **Quotas**
- **Properties**
- **Rename**
- **Delete Dataset**

Snapshot page:

- **Create Snapshot**
- **Clone**
- **Rollback** 
- **Delete**

Typical daily workflow:

1. Select dataset
2. Create snapshot before change
3. Modify properties/quotas
4. Roll back if needed

## Disks & Hardware (disks.cgi)

Main tabs:

- **Disks**: disk list and device details
- **SMART**: SMART status and health
- **I/O Monitor**
- **Memory Disks**
- **Benchmark**
- **Power & Identify**

Use this area for:

- SMART diagnostics
- performance testing (benchmark)
- partition and label related administration

## Services (services.cgi)

Manage related system services:

- NFS
- SMB/Samba
- SSH
- (environment dependent) iSCSI

Use this area for:

- export/share verification
- service restart after configuration changes

## System Status (status.cgi)

Typical tabs:

- Overview
- CPU
- Memory
- **Live VMStat**
- Hardware
- Pool Status
- Health Report
- System Logs

Live VMStat:

- configurable auto refresh interval
- configurable trend window
- per-device trend lines
- Select all / Clear / Apply filters

Daily value:

- detect load spikes quickly
- identify busy devices

## Access and ACL

- **Access Control**: module permission handling
- **ZFS ACL Manager**: ACL editing and apply operations

Best practices:

- keep a snapshot before major ACL changes
- validate real client access after ACL changes

## Safety guidelines

- Read warning blocks before destructive actions.
- Keep backup before pool/dataset delete.
- Rollback may affect newer snapshots and clones.
- Use write benchmarks only with deliberate confirmation.

## Typical daily checklist

1. Dashboard: any red/yellow warning?
2. Pool Status: all pools ONLINE?
3. SMART: any new errors or degrading values?
4. Snapshot routine: critical datasets protected?
5. Services: NFS/SMB reachable from clients?

## If something fails

- First open **View Log** for the operation.
- Verify return/back links navigate to the expected page.
- Avoid immediate delete actions; collect logs/snapshot, then fix.
