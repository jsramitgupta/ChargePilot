# ChargePilot endpoint agents 0.1.8

Windows and macOS agents can now receive an opt-in shutdown request after a mapped switch is confirmed off, with a simpler use-case-led mapping setup.

## What changed

- Tenant administrators can choose battery cycling, switch-off-only, or switch-off followed by endpoint shutdown when creating a mapping.
- Shutdown requests are limited to enrolled Windows and macOS endpoints and are sent only after the switch-off succeeds. The server sends a fixed shutdown request, not an arbitrary command.
- Windows shows a 60-second countdown that a local user can cancel. macOS asks for confirmation in the running menu-bar agent and may request permission to use System Events.
- The mapping wizard shows only the thresholds needed for the selected use case. Less common battery controls are under **More options**.

## What you need to do

No action is needed for existing mappings. To enable the shutdown use case, an administrator must deploy the compatible ChargePilot server and apply the endpoint shutdown database migration in `deploy/migrations/20261028_endpoint_shutdown_commands.sql` using the reviewed backup and upgrade process. Follow the rollback script if the upgrade needs to be reversed.

## Platforms and limitations

Shutdown requests are supported only by enrolled Windows and macOS agents. Windows service runtime acceptance and macOS Apple Events/shutdown interaction still require platform testing. Windows and macOS agents must be running and reporting recently to receive requests. A scheduled or acknowledged request does not prove that the operating system completed shutdown.

This release is unsigned because platform signing credentials were not configured. Windows may show SmartScreen warnings, macOS is not notarized and Gatekeeper may block opening, Android is unsigned, and the iOS IPA requires signing before installation. Physical-device validation for Android and iOS remains outstanding.

## Related help

- [Create a battery mapping](/guides/create-a-battery-mapping)
- [Enroll a device](/guides/enroll-a-device)
