import React from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { Tabs } from "expo-router";
import type { BottomTabBarProps } from "@react-navigation/bottom-tabs";
import { SymbolView } from "expo-symbols";
import { branding } from "@/src/config/branding";
import { useUnreadChatCount } from "@/src/hooks/useUnreadChatCount";

const isWeb = Platform.OS === "web";

/** Custom top tab bar for web — replaces the bottom tab bar */
function WebTopTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
  return (
    <View style={topStyles.bar}>
      {state.routes.map((route, index) => {
        const { options } = descriptors[route.key];
        if ((options as any).href === null) return null; // hidden tabs

        const label = (options.title ?? route.name) as string;
        const isFocused = state.index === index;

        return (
          <Pressable
            key={route.key}
            onPress={() => {
              const event = navigation.emit({
                type: "tabPress",
                target: route.key,
                canPreventDefault: true,
              });
              if (!isFocused && !event.defaultPrevented) {
                navigation.navigate(route.name);
              }
            }}
            style={[topStyles.tab, isFocused && topStyles.tabActive]}
          >
            <Text
              style={[
                topStyles.tabLabel,
                { color: isFocused ? branding.accentColor : "#71717a" },
              ]}
            >
              {label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const topStyles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    backgroundColor: "#09090b",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#27272a",
    paddingHorizontal: 16,
    gap: 4,
  },
  tab: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 2,
    borderBottomColor: "transparent",
  },
  tabActive: {
    borderBottomColor: branding.accentColor,
  },
  tabLabel: {
    fontSize: 14,
    fontWeight: "600",
  },
});

export default function TabLayout() {
  const unreadChatCount = useUnreadChatCount();

  return (
    <Tabs
      tabBar={isWeb ? (props) => <WebTopTabBar {...props} /> : undefined}
      screenOptions={{
        tabBarActiveTintColor: branding.accentColor,
        tabBarInactiveTintColor: "#71717a",
        tabBarStyle: {
          backgroundColor: "#09090b",
          borderTopColor: "#27272a",
          zIndex: 10,
          position: "relative",
        },
        headerShown: !isWeb, // Hide header on web — top tabs replace it
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
          headerShown: false,
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
        name="voice"
        options={{
          href: null, // Hidden — voice mode is now inline in each chat's InputBar
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
