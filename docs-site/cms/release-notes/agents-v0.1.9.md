# ChargePilot endpoint agents 0.1.9

Windows and macOS agents can now collect a small set of approved, read-only system details for tenant-scoped Smart Groups.

## What changed

- Tenant administrators and managers can create Smart Groups that target selected or rule-matched enrolled Windows and macOS devices.
- Groups can collect operating system version, system uptime, and system-disk free space. Agents receive sensor identifiers, not uploaded scripts or arbitrary shell commands.
- Windows collection runs through its service, including when no user is signed in. macOS collection requires the menu-bar app or CLI to be running in a signed-in user session.

## What you need to do

Deploy the compatible ChargePilot server and apply `deploy/migrations/20261028_smart_groups_sensors.sql` using the documented backup and upgrade process before creating groups. No action is needed if you do not use Smart Groups.

## Platforms and limitations

Sensor collection is supported by Windows and macOS agents only. Runs include enabled, enrolled devices in the workspace with fresh reports; offline or stale endpoints do not receive new work until they report again. macOS collection does not run while the user is logged out. The catalog is fixed and read-only; arbitrary scripts are not supported. Check `agent-release-manifest.json` for each platform's signing status. Android and iOS physical-device validation remains outstanding.

## Related help

- [Use Smart Groups and Sensors](/guides/manage-smart-groups-and-sensors)
- [Enroll a device](/guides/enroll-a-device)
