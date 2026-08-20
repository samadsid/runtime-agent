import { useLocalSearchParams } from "expo-router";
import { DeliveryZoneEditor } from "@/features/delivery-zones/zone-editor";
export default function DeliveryZoneDetailsScreen() { const { zoneId } = useLocalSearchParams<{ zoneId: string }>(); return <DeliveryZoneEditor zoneId={zoneId} />; }
