/**
 * Web fallback for push notifications — no-op.
 * Web Push could be added later but is not needed for MVP.
 */
export function usePushNotifications(): { isRegistered: boolean } {
  return { isRegistered: false };
}

/** No-op on web. */
export function setActiveChatId(_chatId: string | null) {
  // no-op
}

/** No-op on web. */
export async function dismissNotificationsForChat(_chatId: string | null) {
  // no-op
}
