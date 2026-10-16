import http from "k6/http";
import { check, sleep } from "k6";

const apiUrl = __ENV.CHARGEPILOT_API_URL || "http://localhost:8000";
const endpointToken = __ENV.CHARGEPILOT_ENDPOINT_TOKEN;
const cadenceSeconds = Number(__ENV.TELEMETRY_CADENCE_SECONDS || 60);

if (!endpointToken) {
  throw new Error("Set CHARGEPILOT_ENDPOINT_TOKEN to a test-tenant token.");
}

export const options = {
  vus: Number(__ENV.ACTIVE_DEVICE_VUS || 1000),
  duration: __ENV.TEST_DURATION || "10m",
  thresholds: {
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  const payload = JSON.stringify({
    hostname: `scale-${__VU}`,
    ip_address: "192.0.2.1",
    battery_percentage: (__VU + __ITER) % 101,
    charging: false,
    ac_connected: false,
    switch_state: null,
    timestamp: new Date().toISOString(),
    agent_version: "scale-test",
  });
  const response = http.post(`${apiUrl}/api/v1/telemetry`, payload, {
    headers: {
      Authorization: `Bearer ${endpointToken}`,
      "Content-Type": "application/json",
    },
    tags: { route: "telemetry_ingest" },
  });

  check(response, {
    "telemetry accepted": (result) => result.status === 200,
  });
  sleep(cadenceSeconds);
}
