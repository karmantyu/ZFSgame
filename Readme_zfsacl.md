# ZFS ACL Manager for ZFSguru (Webmin)

## Overview
`ZFS ACL Manager` is integrated into the `ZFSguru` Webmin module and provides a UI-driven way to manage NFSv4 ACL policy on ZFS datasets, filesystems, directories, and files.

It is a Webmin/Perl port of the same core logic used by the original `acl_manager.sh` (https://github.com/karmantyu/acl_manager; https://github.com/karmantyu/zfsACLmanager) workflow, with focus on:
- policy-based ACL normalization,
- user ACE add/remove,
- POSIX + ACL audit,
- profile-driven defaults (`MEDIA` / `EXEC`),
- safe operation with dry-run and optional snapshot.

## Where to open it
- Quick Access -> Storage -> `ZFS ACL Manager`
- Direct URL: `.../ZFSguru/zfsaclmanager.cgi`

## Permission model summary
In mixed Samba + ZFS environments:
1. Samba mask/create settings influence requested mode bits.
2. ZFS dataset ACL properties (`acltype`, `aclinherit`, `aclmode`, `xattr`, `atime`) determine ACL behavior.
3. NFSv4 ACL entries are authoritative for effective access.
4. POSIX mode (`ls -l`) is often a derived view, not the primary source of truth.

## What the Web UI does
The page supports target selection with two inputs:
- `Dataset / Filesystem` dropdown (mountpoint-based)
- `Directory / File path` manual/browse field

Rule: manual path overrides dropdown when both are filled.

After `Select`, the module detects:
- target type (`FILESYSTEM`, `DIRECTORY`, `FILE`, `OTHER`),
- owning dataset and mountpoint,
- profile and ACL user property,
- base POSIX uid/gid context.

## Profiles
Two policy profiles are supported:
- `MEDIA`: directory `755`, file `644`
- `EXEC`: directory `755`, file `755`

Profiles affect default ACL baseline and POSIX mode expectations during audit/repair.

## ZFS user properties used
- `org.zfsguru:profile`
- `org.zfsguru:acl_users`

These are read and updated by the module as part of policy handling.

## Supported operation modes
From the Run section (`mode`):
1. `reset` - Reset ACL baseline only (destructive for custom extra ACEs).
2. `add` - Add selected user ACE(s), avoids duplicates.
3. `remove` - Remove selected user ACE(s).
4. `audit_acl` - ACL-only normalization against policy.
5. `audit_posix` - POSIX (`chown/chmod`) + ACL audit/repair.
6. `user_rights` - Add/revoke selected rights (`write`, `delete`, `execute`) for selected users.

## Important behavior details
- Duplicate user ACEs are normalized.
- Unknown/foreign user ACEs can be removed during strict policy normalization modes.
- `Create missing user ACE` is available in `user_rights` mode.
- Recursive processing is supported.
- Dry-run mode simulates changes without writing ACL/owner/mode changes.
- Optional dataset snapshot can be taken before changes for filesystem targets.

## Runtime and logs
Execution is handled asynchronously in `zfsaclmanager_apply.cgi` with polling.

Runtime artifacts:
- temporary run logs under module config directory `run_logs/`
- optional keep/cleanup behavior controlled by `Keep logs`

Summary output includes counts for:
- scanned objects,
- dirs/files modified,
- users added/removed,
- duplicates removed,
- ACL read errors,
- modification mask summary.

## Requirements
- FreeBSD with ZFS and NFSv4 ACL support
- Webmin environment
- Required commands available in PATH:
  - `zfs`, `getfacl`, `setfacl`, `find`, `xargs`
  - for user discovery: `pdbedit` or `samba-tool` (fallbacks exist)
- Elevated privileges for actual ACL/chown/chmod modifications

## Safety recommendations
- Start with `Dry run = Yes` for first pass.
- Use `snapshot = Yes` on filesystem targets before large recursive updates.
- Use `reset` carefully: it rebuilds baseline ACL and may remove custom ACE layout.
- Apply `audit_posix` only when ownership/mode policy is intentional for the whole target scope.

## Scope notes
This README documents the Webmin module behavior (`zfsaclmanager.cgi`, `zfsaclmanager_apply.cgi`, `zfsaclmanager-lib.pl`) as integrated into `ZFSguru`.

It is not a CLI manual for direct shell-script invocation.
