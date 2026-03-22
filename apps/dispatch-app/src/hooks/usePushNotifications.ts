import { useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import type { EventSubscription } from "expo-modules-core";
import { router } from "expo-router";
import { registerAPNsToken } from "../api/push";

// Track the currently open chat ID so we can suppress push banners for it
let _activeChatId: string | null = null;

/**
 * Set the currently active/visible chat. Call with null when leaving a chat.
 * Push notifications for the active chat are silently suppressed.
 */
export function setActiveChatId(chatId: string | null) {
  _activeChatId = chatId;
  console.warn("[push] Active chat set to:", chatId);
}

// Configure how notifications are handled when app is in foreground
Notifications.setNotificationHandler({
  handleNotification: async (notification) => {
    // Suppress banner/sound for the chat the user currently has open
    const data = notification.request.content.data;
    const notifChatId = data && typeof data.chat_id === "string" ? data.chat_id : null;

    console.warn("[push] handleNotification — notifChatId:", notifChatId, "activeChatId:", _activeChatId);

    if (notifChatId && notifChatId === _activeChatId) {
      console.warn("[push] Suppressing notification for active chat:", notifChatId);
      return {
        shouldShowBanner: false,
        shouldShowList: false,
        shouldPlaySound: false,
        shouldSetBadge: false,
      };
    }

    return {
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    };
  },
});

/**
 * Extract chat_id and chat_title from a notification's data payload.
 */
function getNotificationData(
  notification: Notifications.Notification,
): { chatId: string | null; chatTitle: string | null } {
  const data = notification.request.content.data;
  const chatId = data && typeof data.chat_id === "string" ? data.chat_id : null;
  const chatTitle = data && typeof data.chat_title === "string" ? data.chat_title : null;
  return { chatId, chatTitle };
}

/**
 * Dismiss all notifications in the notification center that belong to a specific chat.
 */
export async function dismissNotificationsForChat(chatId: string | null) {
  if (!chatId) return;
  try {
    const delivered = await Notifications.getPresentedNotificationsAsync();
    for (const notif of delivered) {
      const data = notif.request.content.data;
      const notifChatId = data && typeof data.chat_id === "string" ? data.chat_id : null;
      if (notifChatId === chatId) {
        await Notifications.dismissNotificationAsync(notif.request.identifier);
      }
    }
  } catch {
    // Silently handle errors
  }
}

/**
 * Navigate to a chat from a notification tap.
 * Deduplicates by notification identifier.
 */
const _processedIds = new Set<string>();

function navigateToChat(notification: Notifications.Notification, source: string) {
  const responseId = notification.request.identifier;
  if (_processedIds.has(responseId)) return;
  _processedIds.add(responseId);

  // Log full content for debugging
  const content = notification.request.content;
  console.warn(`[push] Notification tapped (${source}), full content:`, JSON.stringify({
    title: content.title,
    body: content.body,
    data: content.data,
    // Check if data is nested differently
    contentKeys: Object.keys(content),
    requestKeys: Object.keys(notification.request),
  }));

  const { chatId, chatTitle } = getNotificationData(notification);
  console.warn(`[push] Notification tapped (${source}), data:`, JSON.stringify(notification.request.content.data));

  // Dismiss all notifications for this chat
  dismissNotificationsForChat(chatId).catch(() => {});

  if (chatId) {
    console.warn(`[push] Navigating to chat: ${chatId}, title: ${chatTitle}`);
    // Delay to ensure router is mounted (cold start scenario)
    setTimeout(() => {
      try {
        // Reset stack to tabs first, then push chat on top.
        // This ensures stack is always [tabs, chat] so back() works
        // with native slide animation, and multiple notification taps
        // don't pile up stack entries.
        router.replace("/(tabs)");
        setTimeout(() => {
          router.push({
            pathname: "/chat/[id]",
            params: { id: chatId, ...(chatTitle ? { chatTitle } : {}) },
          });
          console.warn("[push] navigation complete: tabs -> chat");
        }, 50);
      } catch (err) {
        console.error("[push] navigation failed:", err);
      }
    }, 500);
  } else {
    console.warn("[push] No chat_id in notification data, skipping navigation");
  }
}

/**
 * Hook that registers for push notifications on app launch (iOS only).
 *
 * Uses both approaches for notification tap handling:
 * 1. useLastNotificationResponse (hook) — works for cold starts
 * 2. addNotificationResponseReceivedListener — works for background/foreground
 * Both are deduplicated by notification ID.
 */
export function usePushNotifications(): { isRegistered: boolean } {
  const [isRegistered, setIsRegistered] = useState(false);
  const notificationListener = useRef<EventSubscription | null>(null);
  const responseListener = useRef<EventSubscription | null>(null);

  // Hook-based approach: catches cold start notification taps
  const lastResponse = Notifications.useLastNotificationResponse();

  useEffect(() => {
    if (!lastResponse) return;
    navigateToChat(lastResponse.notification, "hook");
  }, [lastResponse]);

  useEffect(() => {
    if (Platform.OS !== "ios") {
      return;
    }

    let mounted = true;

    async function registerForPush() {
      try {
        const { status: existingStatus } =
          await Notifications.getPermissionsAsync();
        let finalStatus = existingStatus;

        if (existingStatus !== "granted") {
          const { status } = await Notifications.requestPermissionsAsync();
          finalStatus = status;
        }

        if (finalStatus !== "granted") {
          console.warn("[push] Notification permissions not granted:", finalStatus);
          return;
        }

        const tokenData = await Notifications.getDevicePushTokenAsync();
        const apnsToken = tokenData.data as string;

        try {
          await registerAPNsToken(apnsToken);
          if (mounted) setIsRegistered(true);
          console.warn("[push] APNs token registered with backend");
        } catch (error) {
          console.error("[push] Failed to register APNs token:", error);
        }
      } catch (error) {
        console.error("[push] Error during push registration:", error);
      }
    }

    registerForPush();

    // Foreground notification listener — log for debugging
    notificationListener.current =
      Notifications.addNotificationReceivedListener((notification) => {
        const { chatId } = getNotificationData(notification);
        console.warn("[push] Foreground notification received, chat_id:", chatId, "active:", _activeChatId);
      });

    // Listener-based approach: catches background/foreground notification taps
    responseListener.current =
      Notifications.addNotificationResponseReceivedListener((response) => {
        console.warn("[push] Notification response received (listener)");
        navigateToChat(response.notification, "listener");
      });

    return () => {
      mounted = false;
      if (notificationListener.current) {
        notificationListener.current.remove();
      }
      if (responseListener.current) {
        responseListener.current.remove();
      }
    };
  }, []);

  return { isRegistered };
}
