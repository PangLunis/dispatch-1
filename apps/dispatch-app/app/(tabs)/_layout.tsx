import React from "react";
import { Tabs } from "expo-router";
import { SymbolView } from "expo-symbols";
import { branding } from "@/src/config/branding";
import { useUnreadChatCount } from "@/src/hooks/useUnreadChatCount";

export default function TabLayout() {
  const unreadChatCount = useUnreadChatCount();

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: branding.accentColor,
        tabBarInactiveTintColor: "#71717a",
        tabBarStyle: {
          backgroundColor: "#09090b",
          borderTopColor: "#27272a",
          zIndex: 10,
          position: "relative",
        },
        headerStyle: {
          backgroundColor: "#09090b",
        },
        headerTintColor: "#fafafa",
        headerShadowVisible: false,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Chats",
          tabBarBadge: unreadChatCount > 0 ? unreadChatCount : undefined,
          tabBarBadgeStyle: {
            backgroundColor: "#007AFF",
            color: "#ffffff",
            fontSize: 11,
            fontWeight: "600",
            minWidth: 18,
            height: 18,
            lineHeight: 18,
            borderRadius: 9,
          },
          tabBarIcon: ({ color }) => (
            <SymbolView
              name={{
                ios: "bubble.left.and.bubble.right",
                android: "chat",
                web: "chat",
              }}
              tintColor={color}
              size={24}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="agents"
        options={{
          title: "Agent Sessions",
          tabBarIcon: ({ color }) => (
            <SymbolView
              name={{
                ios: "terminal",
                android: "code",
                web: "code",
              }}
              tintColor={color}
              size={24}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="dashboard"
        options={{
          title: "Dashboard",
          tabBarIcon: ({ color }) => (
            <SymbolView
              name={{
                ios: "gauge.with.dots.needle.bottom.50percent",
                android: "dashboard",
                web: "dashboard",
              }}
              tintColor={color}
              size={24}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: "Settings",
          tabBarIcon: ({ color }) => (
            <SymbolView
              name={{
                ios: "gearshape",
                android: "settings",
                web: "settings",
              }}
              tintColor={color}
              size={24}
            />
          ),
        }}
      />
    </Tabs>
  );
}
