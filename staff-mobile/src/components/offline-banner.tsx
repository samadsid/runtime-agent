import NetInfo from "@react-native-community/netinfo";
import { useEffect, useState } from "react";
import { Banner } from "@/design-system";

export function OfflineBanner() {
  const [offline, setOffline] = useState(false);
  useEffect(() => NetInfo.addEventListener((state) => setOffline(state.isConnected === false)), []);
  return offline ? <Banner tone="warning" message="You appear to be offline. Displayed data may be out of date." /> : null;
}
