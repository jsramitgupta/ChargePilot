import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import type { Core } from "@strapi/strapi";

const guideUid = "api::guide.guide" as const;

type GuideInput = {
  title: string;
  slug: string;
  summary: string;
  audience: "all" | "tenant_admin" | "user";
  section: string;
  sortOrder: number;
  readingMinutes: number;
  body: string;
};

const starterGuides: GuideInput[] = [
  {
    title: "Getting started with ChargePilot",
    slug: "getting-started",
    summary:
      "Sign in, understand your workspace, and find the first place to set up your devices.",
    audience: "all",
    section: "Your account",
    sortOrder: 10,
    readingMinutes: 4,
    body: `## What ChargePilot does

ChargePilot collects battery reports from enrolled computers and mobile devices. Tenant administrators can connect switches, make endpoint-to-switch mappings, and review automation activity. The server evaluates the battery rules; the dashboard does not make switching decisions.

## Sign in and find your workspace

Open the ChargePilot address provided by your organization and sign in with your account. The left navigation takes you to endpoints, switches, mappings, events, agent setup, and account administration. The pages you can use depend on your role.

If you are joining for the first time, follow the one-time setup link sent by your administrator. For a new tenant, use the registration flow and verify your email before signing in.

## Choose your next task

- **Users:** ask your tenant administrator for an enrollment token, then follow [Enroll a device](/guides/enroll-a-device).
- **Tenant administrators and managers:** begin with [Invite people](/guides/invite-people), then enroll the devices you manage.
- **Switch administrators:** read [Connect a switch](/guides/connect-a-switch) before creating a battery mapping.

## Keep credentials private

Never paste enrollment tokens, connector credentials, switch local keys, or passwords into a support message. ChargePilot does not need your device serial number for enrollment.`,
  },
  {
    title: "People, roles, and workspaces",
    slug: "people-roles-and-workspaces",
    summary:
      "See what tenant administrators, managers, users, and Super Admins can do.",
    audience: "all",
    section: "Your account",
    sortOrder: 20,
    readingMinutes: 3,
    body: `## Tenant administrator

A tenant administrator manages people and devices in one workspace. They can invite people, issue device enrollment tokens, configure switches and mappings, and review the tenant's activity.

## Manager

A manager can help administer the tenant's devices and users. The pages available to a manager are scoped to that tenant; managers do not gain access to another tenant's devices.

## User

A user can sign in and work with the ChargePilot pages enabled for their account. Ask a tenant administrator when you need an invitation, enrollment token, or a change to the workspace's device setup.

## Super Admin

The Super Admin manages tenants across the installation. This role is intended for the ChargePilot service operator, not for ordinary tenant use.

## Workspace boundaries

People, endpoints, switches, and mappings are scoped to their tenant. If a switch or endpoint is missing, check that you are in the right workspace and ask its administrator to confirm the assignment.`,
  },
  {
    title: "Invite people to your tenant",
    slug: "invite-people",
    summary:
      "Send a secure account invitation and choose the right role for a teammate.",
    audience: "tenant_admin",
    section: "Your account",
    sortOrder: 30,
    readingMinutes: 3,
    body: `## Send an invitation

1. Open **People & invites**.
2. Under **Invite someone**, enter the teammate's username and email address.
3. Choose the **Access level** they need, then select **Send invitation**. The
   invitation is sent for your workspace.

ChargePilot emails a single-use setup link. The invited person chooses a
password from the link. It expires after seven days and cannot be used twice.
Sending a replacement for the same username or email invalidates the earlier
invitation.

## Choose the least access needed

Use a tenant administrator role for someone who will manage workspace membership and setup. Use a manager role for delegated day-to-day administration. Use the standard user role for people who only need the product's user workflows.

## Review or revoke an invitation

The invitation list shows its status and expiry, not the one-time setup code. Revoke an unused invitation if it was sent to the wrong address, then send a new invitation to the correct person.

If the email does not arrive, verify the address and ask the service operator to check email delivery. Do not send passwords or setup links through a shared chat.`,
  },
  {
    title: "Enroll a device",
    slug: "enroll-a-device",
    summary:
      "Create an enrollment token and set up a Windows, macOS, Android, or iOS agent.",
    audience: "all",
    section: "Devices",
    sortOrder: 40,
    readingMinutes: 5,
    body: `## Create an enrollment token

Tenant administrators and managers open **Set up a device**, choose the workspace, and create an enrollment token. A token is valid for 24 hours, can enroll more than one device, and can be used by the supported platforms. Each administrator can have up to five active tokens at a time.

Reveal a token only when you are ready to use it. Share it through a trusted private channel. Revoke it after enrollment if it is no longer needed. Revoking an enrollment token stops new enrollments; use endpoint credential revocation to disconnect a device that is already enrolled.

## Install the agent

Download the current installer from **Set up a device** and follow the platform-specific instructions there:

- **Windows:** run the setup program as an administrator. Enter the enrollment token in its setup window and choose **Save and start service**. The service reports when no user is signed in.
- **macOS:** open the ChargePilot menu-bar app, enter the enrollment token, and allow it to report while the app is running. Reporting pauses while the Mac sleeps.
- **Android:** install the provided APK and enter the enrollment token in the app. Android background work is best-effort; WorkManager cannot run more often than every 15 minutes.
- **iOS:** install the provided IPA where its signing profile permits, then enroll in the app. Shortcuts automations can report on battery and charger events, but iOS may delay or skip them.

The agent uses a device label rather than a hardware serial number. It stores its per-install credential using the platform's protected storage.

## Change or remove an enrollment

Use the agent's own deregister action before handing a device to another person. Administrators can also revoke an endpoint credential from ChargePilot. A revoked device must be enrolled again to report.

If the setup page says a release is unsigned or unnotarized, verify it through
your organization's approved channel before allowing installation. Do not
ignore a platform warning unless your administrator confirms that the release
and installation path are expected.`,
  },
  {
    title: "Review endpoints and reports",
    slug: "review-endpoints",
    summary:
      "Find a reporting device, check its freshness, and understand its battery history.",
    audience: "all",
    section: "Devices",
    sortOrder: 50,
    readingMinutes: 4,
    body: `## Find an endpoint

Open **Endpoints** to search by device label, filter by platform or online state, and move through the endpoint list. The list is sorted by the latest report. An administrator can change the display label without changing the name reported by the agent.

## Read the endpoint details

Select a device label to open its details. The page shows the latest report time, battery level, configured report cadence, automation eligibility, assigned mappings, and recent battery and system-resource readings.

Unsupported CPU, memory, disk, or GPU readings are shown as unavailable. They are not treated as zero. Mobile reporting and operating-system background scheduling can be delayed, so check the report timestamp before assuming a device is disconnected.

## Online status and automation

Online status depends on the workspace's configured reporting cadence. Automation has a separate freshness limit and remains server-controlled. A device can be visible while its latest report is too old to trigger a switch action.

If a device is missing, confirm that it is enrolled in the correct workspace and that the agent can reach the configured ChargePilot API address.`,
  },
  {
    title: "Use a private connector image",
    slug: "private-connector-image-access",
    summary:
      "Get read-only Docker Hub access and authenticate before pulling a private site connector image.",
    audience: "tenant_admin",
    section: "Devices",
    sortOrder: 50,
    readingMinutes: 3,
    body: `## Get access before installing

If your ChargePilot operator has made the site connector image private, ask them to grant your Docker Hub account read access to the connector repository. Use an account authorized by the repository owner. Do not ask for or reuse the CI image-publishing token.

## Sign in on the connector host

On the trusted computer that will run the connector, run \`docker login\` and sign in with your authorized Docker Hub account. Use your Docker Hub access token when prompted for a password. Docker uses this sign-in for image pulls; it is separate from the one-time ChargePilot enrollment code.

Do not put the Docker Hub token in the Compose file, an enrollment code, or a support message. Keep the connector host and its Docker credential store accessible only to trusted operators. Sign in again before a later pull if you have logged out or removed the stored Docker credentials.

## Pull and start the connector

1. In **Site connectors**, create a one-time enrollment code and save the displayed Compose file on the connector host.
2. Run \`docker compose pull\` to fetch the private image, then start the service using the enrollment instructions on the page.
3. Keep the Docker-managed \`connector-data\` volume when updating the image; it stores the enrolled connector credential.

If the connector image is public in your installation, no Docker Hub sign-in is needed. For switch discovery and network requirements, follow [Connect a switch](/guides/connect-a-switch).`,
  },
  {
    title: "Connect a switch",
    slug: "connect-a-switch",
    summary:
      "Choose a site connector, discover a Tuya device, and add it to your workspace.",
    audience: "tenant_admin",
    section: "Devices",
    sortOrder: 60,
    readingMinutes: 5,
    body: `## Prepare the local network

Install a ChargePilot site connector on a computer that can reach the Tuya devices on their local network. In **Site connectors**, create a one-time enrollment code and follow the displayed Docker Compose instructions. The code is shown once and expires after 15 minutes. The connector makes outbound HTTPS requests to ChargePilot and performs discovery and control on its own LAN.

Wait until the connector appears online before using it for a scan. Each switch is assigned to one connector in its tenant.

## Add a device

1. Open **Switches** and find **Scan a switch network**.
2. Under **Scan location**, select the ChargePilot server network or the online site connector for that LAN.
3. Choose **Scan local network**. Use a result when one is found, or choose **Add switch manually**.
4. Confirm the device identity, local access details, protocol, and any available channels before saving.

SmartLife/Tuya pairing can retrieve a local key to match with a device. The pairing result does not establish the device's identity or network address. Use the LAN discovery result or explicit manual entry for the device ID, IP address, and protocol details.

## Protect local keys

Local keys allow access to devices on the LAN. ChargePilot encrypts stored keys, but they should still be handled as credentials. Never put them in a ticket, screenshot, or source-controlled file.

## Connector status

If a connector is offline, switches routed through it cannot receive new commands. Restore its network connection and confirm it is enrolled in the intended tenant. Do not install a second connector on the same device route unless the workspace administrator has reviewed the assignment.`,
  },
  {
    title: "Create a battery mapping",
    slug: "create-a-battery-mapping",
    summary:
      "Link an endpoint to a switch, choose its battery use case, and set the relevant thresholds.",
    audience: "tenant_admin",
    section: "Automation",
    sortOrder: 70,
    readingMinutes: 4,
    body: `## Before you start

The endpoint and switch must belong to the same tenant. Make sure the endpoint is reporting and the switch has an online site connector. Automation rules are evaluated by the ChargePilot server, not by the browser or the endpoint agent.

## Create the mapping

1. Open **Mappings** and choose **Create mapping**.
2. Select the endpoint.
3. Select the switch and, when needed, a channel.
4. Choose what should happen: **Cycle switch power with battery levels**, **Only turn off the smart switch**, or, for an enrolled Windows or macOS endpoint, **Turn off the switch and the Windows or macOS device**.
5. Set the thresholds shown for that use case. Battery cycling uses turn-on and turn-off thresholds; switch-off use cases use the turn-off threshold.
6. If needed, open **More options** for automatic turn-on, a separate charging cutoff, the minimum time between changes, or to pause the mapping.
7. Save the mapping explicitly.

Moving through the setup steps does not save a mapping. Use the final save action to create it.

## Request endpoint shutdown

The shutdown use case is available only for an enrolled, tenant-assigned Windows or macOS endpoint. ChargePilot requests endpoint shutdown only after the mapped switch has successfully turned off. The server sends a fixed shutdown request, not an arbitrary command.

Windows shows a 60-second countdown that a local user can cancel with \`shutdown /a\`. On macOS, the running menu-bar agent asks for confirmation and macOS may request permission to use System Events. The Mac must be awake and the agent running to receive the request. An agent acknowledgement means the request was handled; it does not prove that the operating system completed shutdown.

## Understand hysteresis

The default turn-on threshold is 79%, the default turn-off threshold is 99%, and the default minimum state-change interval is 300 seconds. Use thresholds suited to the device and its purpose.

- When the switch is off and battery is at or below the turn-on threshold, the server may request **On**.
- When the switch is on and battery is at or above the turn-off threshold, the server may request **Off**.
- If the minimum interval has not elapsed, no state change is requested.
- Turn-on can be disabled independently when you only want an automatic turn-off.

The server also requires a fresh report, an enabled endpoint, an allowed platform, and an enabled mapping in the same tenant. These checks cannot be overridden from the UI.
The switch-off-only and shutdown use cases always keep automatic switch turn-on disabled.

## Charging-completion cutoff

An optional charging cutoff can request a turn-off at its selected battery threshold while telemetry says the endpoint is charging. It uses the \`charging\` state, not the separate AC-connected indicator, and does not replace the regular turn-off threshold.

## Review the result

Open **Events** to see the requested state and the connector outcome. A command can be delayed while the connector is offline. Review the endpoint report time, connector status, switch assignment, and event reason before changing thresholds.`,
  },
  {
    title: "Understand events and switch readings",
    slug: "understand-events",
    summary:
      "Read automation outcomes and know when power or energy measurements are fresh.",
    audience: "all",
    section: "Automation",
    sortOrder: 80,
    readingMinutes: 3,
    body: `## Read an automation event

Open **Events** to review the reason for a state change, the previous and requested state, and the connector result. A request is not the same as a confirmed switch state: check the reported result and current device state.

The connector must be online and assigned to the switch. If delivery is delayed, restore the connector connection and review the latest event before making another rule change.

## Power and energy

When a compatible device reports metering data, its switch page can show power and energy readings. Power older than five minutes is not presented as live. Energy reflects readings observed by ChargePilot and may be partial for the current month, especially for cumulative counters first seen after the month began.

An unavailable or unsupported reading is not zero. The guided **Find readings** action needs a recent site connector version; follow the version requirement displayed in ChargePilot.`,
  },
  {
    title: "Troubleshoot reporting and control",
    slug: "troubleshoot-reporting-and-control",
    summary:
      "Check the report, mapping, connector, and device in the order that narrows down a problem.",
    audience: "all",
    section: "Troubleshooting",
    sortOrder: 90,
    readingMinutes: 4,
    body: `## An endpoint is offline

1. Open **Endpoints** and check the last successful report time.
2. Confirm that the device is connected to the network and the agent is running.
3. Check that the agent uses the correct ChargePilot API address.
4. For a mobile device, allow for background scheduling delays and open the app to request a fresh report.
5. Ask an administrator to verify that the endpoint is enrolled in the correct workspace.

## A switch did not change state

1. Confirm the endpoint has a fresh battery report and automation is enabled.
2. Check the endpoint's mapping, threshold, current switch state, and minimum state-change interval.
3. Confirm the endpoint and switch belong to the same tenant.
4. Check that the connector assigned to the switch is online.
5. Open **Events** and read the recorded reason and connector outcome.

## A switch cannot be discovered

Confirm the connector host and switch are on a network that allows local discovery. Check the connector's online status and use the discovered device details or explicit manual entry. SmartLife pairing supplies a key for matching; it does not provide the LAN address.

## Contact support

Sign in and choose **Support** to send a message to your configured support team. Include the affected device label, the time of the issue, and a relevant event ID if available. Do not include passwords, enrollment tokens, local keys, or connector credentials.`,
  },
];

export default {
  async bootstrap({ strapi }: { strapi: Core.Strapi }) {
    const existingEntries = await strapi.documents(guideUid).findMany({
      status: "draft",
      fields: ["documentId", "slug", "body"],
    });
    const existingBySlug = new Map<
      string,
      { documentId: string; slug: string; body?: string | null }
    >();
    for (const entry of existingEntries) {
      if (!entry.slug || !entry.documentId) {
        throw new Error("A stored ChargePilot guide has no document ID or slug.");
      }
      existingBySlug.set(entry.slug, {
        documentId: entry.documentId,
        slug: entry.slug,
        body: entry.body,
      });
    }

    for (const guide of starterGuides) {
      if (!existingBySlug.has(guide.slug)) {
        await strapi.documents(guideUid).create({
          data: guide,
          status: "published",
        });
      }
    }

    await syncReleaseNotes(strapi, existingBySlug);
  },
};

async function syncReleaseNotes(
  strapi: Core.Strapi,
  existingBySlug: Map<
    string,
    { documentId: string; slug: string; body?: string | null }
  >,
) {
  const releaseDirectory = path.join(process.cwd(), "release-notes");
  let filenames: string[];
  try {
    filenames = await readdir(releaseDirectory);
  } catch (error) {
    if (isMissingDirectory(error)) {
      return;
    }
    throw error;
  }

  for (const filename of filenames.sort()) {
    if (!/^agents-v\d+\.\d+\.\d+\.md$/.test(filename)) {
      continue;
    }

    const body = (await readFile(path.join(releaseDirectory, filename), "utf8"))
      .trim();
    const title = body.match(/^#\s+(.+)$/m)?.[1]?.trim();
    const summary = body
      .split(/\r?\n/)
      .find((line) => line.trim() && !line.startsWith("#"))?.trim();
    if (!title || !summary) {
      throw new Error(
        `Release note ${filename} must contain a title and summary.`,
      );
    }

    const slug = filename.slice(0, -".md".length);
    const [major, minor, patch] = slug
      .replace(/^agents-v/, "")
      .split(".")
      .map(Number);
    const guide: GuideInput = {
      title,
      slug,
      summary,
      audience: "all",
      section: "Release notes",
      sortOrder: -(major * 1_000_000 + minor * 1_000 + patch),
      readingMinutes: Math.max(1, Math.ceil(body.split(/\s+/).length / 220)),
      body,
    };
    const existing = existingBySlug.get(slug);
    if (existing) {
      if (existing.body !== body) {
        await strapi.documents(guideUid).update({
          documentId: existing.documentId,
          data: guide,
          status: "published",
        });
      }
      continue;
    }
    await strapi.documents(guideUid).create({
      data: guide,
      status: "published",
    });
  }
}

function isMissingDirectory(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    error.code === "ENOENT"
  );
}
