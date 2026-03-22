import React, { useMemo } from "react";
import { StyleSheet, View } from "react-native";
import { getApiBaseUrl } from "@/src/config/constants";

export default function DashboardScreen() {
  const dashboardUrl = useMemo(() => {
    const base = getApiBaseUrl();
    return base ? `${base}/dashboard` : "/dashboard";
  }, []);

  return (
    <View style={styles.container}>
      <iframe
        src={dashboardUrl}
        style={{
          flex: 1,
          width: "100%",
          height: "100%",
          border: "none",
          backgroundColor: "#09090b",
        }}
        allowFullScreen
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#09090b",
  },
});
