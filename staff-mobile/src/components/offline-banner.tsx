import NetInfo from "@react-native-community/netinfo";
import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

export function OfflineBanner() {
  const [offline, setOffline] = useState(false);
  useEffect(() => NetInfo.addEventListener((state) => setOffline(state.isConnected === false)), []);
  return offline ? <View accessibilityRole="alert" style={styles.banner}><Text style={styles.text}>You appear to be offline. Data may be out of date.</Text></View> : null;
}
const styles = StyleSheet.create({ banner: { backgroundColor: "#B54708", padding: 8 }, text: { color: "white", textAlign: "center", fontWeight: "600" } });
