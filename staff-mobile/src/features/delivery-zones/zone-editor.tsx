import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Alert, StyleSheet, View } from "react-native";
import MapView, { Marker, Polygon, type MapPressEvent } from "react-native-maps";

import type { DeliveryZoneInput } from "@/api/staff-api";
import { staffApi } from "@/app-services";
import { AppText, Banner, Button, Card, Confirmation, FilterChip, Inline, Loading, ResponsiveContainer, SectionHeader, Stack, TextField, spacing, useTheme } from "@/design-system";
import { queryKeys } from "@/query/query-keys";

import { boundaryPoints, circlePolygon, polygonBoundary, type Coordinate } from "./geometry";

const initialRegion = { latitude: 28.6139, longitude: 77.209, latitudeDelta: 0.18, longitudeDelta: 0.18 };
const key = () => `zone-${Date.now()}-${Math.random().toString(16).slice(2)}`;

export function DeliveryZoneEditor({ zoneId }: { zoneId?: string }) {
  const theme = useTheme(); const router = useRouter(); const queryClient = useQueryClient();
  const query = useQuery({ queryKey: queryKeys.deliveryZone(zoneId ?? "new"), queryFn: ({ signal }) => staffApi.deliveryZone(zoneId!, signal), enabled: Boolean(zoneId) });
  const [name, setName] = useState(""); const [priority, setPriority] = useState("100"); const [points, setPoints] = useState<Coordinate[]>([]);
  const [mode, setMode] = useState<"polygon" | "circle">("polygon"); const [radius, setRadius] = useState("1000"); const [dirty, setDirty] = useState(false);
  const [testPoint, setTestPoint] = useState<Coordinate>(); const [confirmAction, setConfirmAction] = useState<"activate" | "deactivate">();
  useEffect(() => { if (query.data) { setName(query.data.name); setPriority(String(query.data.priority)); if (query.data.boundary) setPoints(boundaryPoints(query.data.boundary)); setDirty(false); } }, [query.data]);
  const boundary = useMemo(() => points.length >= 3 ? polygonBoundary(points) : undefined, [points]);
  const save = useMutation({ mutationFn: async () => { if (!boundary) throw new Error("Draw at least three vertices."); const body: DeliveryZoneInput = { name: name.trim(), priority: Number(priority), boundary }; return zoneId && query.data ? staffApi.updateDeliveryZone(zoneId, body, query.data.version, key()) : staffApi.createDeliveryZone(body, key()); }, onSuccess: async (zone) => { setDirty(false); await queryClient.invalidateQueries({ queryKey: ["staff", "delivery-zones"] }); if (!zoneId) router.replace(`/(protected)/delivery-zones/${zone.id}` as never); else await query.refetch(); }, onError: (error) => Alert.alert("Zone not saved", error instanceof Error ? error.message : "Check the boundary and retry.") });
  const statusMutation = useMutation({ mutationFn: (action: "activate" | "deactivate") => staffApi.changeDeliveryZoneStatus(zoneId!, action, query.data!.version, key()), onSuccess: async () => { setConfirmAction(undefined); await query.refetch(); await queryClient.invalidateQueries({ queryKey: ["staff", "delivery-zones"] }); } });
  const pointMutation = useMutation({ mutationFn: () => staffApi.checkDeliveryPoint(testPoint!.latitude, testPoint!.longitude) });
  const addPoint = (event: MapPressEvent) => { const coordinate = event.nativeEvent.coordinate; setTestPoint(coordinate); if (mode === "circle") setPoints(circlePolygon(coordinate, Number(radius))); else setPoints((current) => [...current, coordinate]); setDirty(true); };
  if (zoneId && query.isPending) return <Loading label="Loading delivery zone" />;
  const status = query.data?.status;
  return <ResponsiveContainer scroll contentStyle={styles.page}><Stack gap={4}>
    <SectionHeader title={zoneId ? "Edit delivery zone" : "New delivery zone"} action={<Button variant="tertiary" label="Back" onPress={() => dirty ? Alert.alert("Discard edits?", "Unsaved boundary changes will be lost.", [{ text: "Keep editing" }, { text: "Discard", style: "destructive", onPress: () => router.back() }]) : router.back()} />} />
    {query.error ? <Banner tone="danger" message="The current zone could not be loaded." /> : null}{save.error ? <Banner tone="danger" message="The zone changed or the geometry was rejected. Reload before retrying a version conflict." /> : null}
    <Card><TextField label="Zone name" required value={name} maxLength={120} onChangeText={(value) => { setName(value); setDirty(true); }} /><TextField label="Priority (lower wins)" required keyboardType="number-pad" value={priority} onChangeText={(value) => { setPriority(value); setDirty(true); }} /><Inline gap={2} wrap><FilterChip label="Draw polygon" selected={mode === "polygon"} onPress={() => setMode("polygon")} /><FilterChip label="Centre + radius" selected={mode === "circle"} onPress={() => setMode("circle")} /></Inline>{mode === "circle" ? <TextField label="Radius metres" keyboardType="number-pad" value={radius} onChangeText={setRadius} help="Tap the centre on the map; the app creates a 64-vertex polygon." /> : <AppText color="secondary">Tap to add vertices. Drag markers to refine the boundary. Coordinates are sent longitude-first.</AppText>}</Card>
    <View style={[styles.mapFrame, { borderColor: theme.colors.borderStrong }]}><MapView style={styles.map} initialRegion={initialRegion} onPress={addPoint} onLongPress={(event) => setTestPoint(event.nativeEvent.coordinate)}>{points.length >= 3 ? <Polygon coordinates={points} fillColor={`${theme.colors.brand}33`} strokeColor={theme.colors.brand} strokeWidth={2} /> : null}{points.map((point, index) => <Marker key={index} coordinate={point} draggable title={`Vertex ${index + 1}`} onDragEnd={(event) => { setPoints((current) => current.map((item, itemIndex) => itemIndex === index ? event.nativeEvent.coordinate : item)); setDirty(true); }} />)}{testPoint ? <Marker coordinate={testPoint} pinColor={theme.colors.info} title="Test point" /> : null}</MapView></View>
    <Inline gap={2} wrap><Button variant="secondary" label="Undo vertex" disabled={!points.length || mode === "circle"} onPress={() => { setPoints((current) => current.slice(0, -1)); setDirty(true); }} /><Button variant="secondary" label="Clear boundary" disabled={!points.length} onPress={() => { setPoints([]); setDirty(true); }} /><Button label="Test selected point" disabled={!testPoint} loading={pointMutation.isPending} onPress={() => pointMutation.mutate()} /></Inline>
    {pointMutation.data ? <Banner tone={pointMutation.data.serviceable ? "success" : "warning"} message={pointMutation.data.serviceable ? `Covered by ${pointMutation.data.zone_name}.` : "This point is outside all active zones."} /> : null}
    <Button label={zoneId ? "Save changes" : "Create draft zone"} loading={save.isPending} disabled={!name.trim() || !boundary || !Number.isInteger(Number(priority)) || Number(priority) < 0} onPress={() => save.mutate()} />
    {zoneId && status ? <Card><AppText weight="bold">Status: {status}</AppText><Button variant={status === "ACTIVE" ? "danger" : "secondary"} label={status === "ACTIVE" ? "Deactivate zone" : "Activate zone"} onPress={() => setConfirmAction(status === "ACTIVE" ? "deactivate" : "activate")} /></Card> : null}
  </Stack><Confirmation visible={Boolean(confirmAction)} title={`${confirmAction === "activate" ? "Activate" : "Deactivate"} zone?`} message="This immediately changes authoritative customer serviceability." confirmLabel={confirmAction === "activate" ? "Activate" : "Deactivate"} danger={confirmAction === "deactivate"} busy={statusMutation.isPending} onCancel={() => setConfirmAction(undefined)} onConfirm={() => confirmAction && statusMutation.mutate(confirmAction)} /></ResponsiveContainer>;
}

const styles = StyleSheet.create({ page: { paddingBottom: spacing[8] }, mapFrame: { height: 420, borderWidth: 1, borderRadius: 12, overflow: "hidden" }, map: { flex: 1 } });
