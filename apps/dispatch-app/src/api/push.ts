import { apiRequest, getDeviceToken } from "./client";

/** Register an APNs push notification token. POST /register-apns */
export async function registerAPNsToken(
  apnsToken: string,
): Promise<{ status: string; message: string }> {
  const deviceToken = getDeviceToken();
  if (!deviceToken) {
    throw new Error("Device token not set");
  }

  return apiRequest<{ status: string; message: string }>("/register-apns", {
    method: "POST",
    body: {
      device_token: deviceToken,
      apns_token: apnsToken,
    },
  });
}
