---
name: docs-content-maintenance
description: "Use when updating ChargePilot user guides, tenant admin instructions, product release notes, or validating that a release has matching documentation."
---

# ChargePilot documentation maintenance

Use this workflow for customer-facing product changes and before publishing
an `agents-vMAJOR.MINOR.PATCH` release.

1. Read `.github/instructions/CURRENT_STATE.md`,
   `.github/instructions/API_SPEC.md`, and the relevant frontend, agent, or
   deployment reference. Verify the UI labels and behavior in the source.
2. Identify whether the change affects users, tenant administrators/managers,
   platform setup, permissions, automation behavior, troubleshooting, or a
   documented limitation.
3. Update the task-based guide in Strapi for procedural behavior. Keep actions
   in the same order and with the same names as the product. Do not promise
   exact Android/iOS scheduling, bypass server automation rules, or imply that
   SmartLife pairing supplies LAN device identity.
4. For an agent release tag, add
   `docs-site/cms/release-notes/agents-vMAJOR.MINOR.PATCH.md` using the local
   release-note example. Explain what changed, who is affected, required user
   action, supported platforms, known limits, and related guide links. Never
   include credentials, local keys, enrollment tokens, or customer data.
5. Keep release notes source-controlled; keep editable how-to guides in
   Strapi. The CMS synchronizes release notes on startup and leaves edited
   procedural guides intact.
6. Run the docs frontend lint and both app builds from `docs-site/README.md`.
   Confirm the release-gate check recognizes the exact tag/version filename.
7. Report any user-visible change without an updated guide, unsupported claim,
   or release-note mismatch as an unresolved issue. Do not silently skip the
   documentation change.
