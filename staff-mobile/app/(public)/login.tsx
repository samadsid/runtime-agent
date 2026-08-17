import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from "react-native";
import { z } from "zod";

import { StaffApiError } from "@/api/errors";
import { useAuth } from "@/auth/auth-context";
import { AppText, Button, Card, IconButton, Screen, TextField, spacing, useResponsiveLayout, useTheme } from "@/design-system";
import { recordEvent } from "@/observability/events";

export const loginSchema = z.object({ email: z.string().trim().email("Enter a valid email address."), password: z.string().min(1, "Enter your password.") });
type LoginValues = z.infer<typeof loginSchema>;

export default function LoginScreen() {
  const theme = useTheme();
  const { compact } = useResponsiveLayout();
  const auth = useAuth();
  const [visible, setVisible] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { control, handleSubmit, formState: { errors, isSubmitting }, resetField } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" },
  });
  const submit = handleSubmit(async ({ email, password }) => {
    setSubmitError(null);
    try { await auth.login(email.trim(), password); }
    catch (error) {
      resetField("password");
      const code = error instanceof StaffApiError ? error.code : "unexpected_response";
      recordEvent("login_failed_category", { category: code });
      setSubmitError(code === "invalid_credentials" ? "The email or password is invalid."
        : code === "rate_limit_exceeded" ? "Too many attempts. Try again later."
        : "Login could not be completed. Check your connection and retry.");
    }
  });
  return <Screen><KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={styles.flex}>
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.page}>
      {!compact ? <View style={[styles.brandPane, { backgroundColor: theme.colors.brand }]}><AppText variant="display" color="onBrand" weight="bold">MeatUncle</AppText><AppText variant="bodyLarge" color="onBrand">Clear, dependable tools for daily operations.</AppText></View> : null}
      <View style={styles.formPane}><View><AppText variant="titleLarge" weight="bold">Staff sign in</AppText><AppText variant="bodyLarge" color="secondary">Manage fulfilment, catalog, and inventory securely.</AppText></View>
      <Card variant="outlined">
        <Controller control={control} name="email" render={({ field }) => <TextField label="Email" required autoCapitalize="none" autoComplete="email" keyboardType="email-address" returnKeyType="next" value={field.value} onBlur={field.onBlur} onChangeText={field.onChange} error={errors.email?.message} />} />
        <Controller control={control} name="password" render={({ field }) => <TextField label="Password" required secureTextEntry={!visible} autoComplete="current-password" returnKeyType="done" value={field.value} onBlur={field.onBlur} onChangeText={field.onChange} error={errors.password?.message} trailing={<IconButton name={visible ? "eye-off-outline" : "eye-outline"} label={visible ? "Hide password" : "Show password"} onPress={() => setVisible((value) => !value)} />} />} />
        {submitError ? <AppText color="danger" accessibilityRole="alert">{submitError}</AppText> : null}
        <Button testID="login-submit" label="Sign in" loading={isSubmitting} onPress={() => void submit()} />
      </Card></View>
    </ScrollView>
  </KeyboardAvoidingView></Screen>;
}
const styles = StyleSheet.create({ flex: { flex: 1 }, page: { flexGrow: 1, flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "center", padding: spacing[6], gap: spacing[8] }, brandPane: { flex: 1, minWidth: 300, maxWidth: 560, minHeight: 360, justifyContent: "center", padding: spacing[8], borderRadius: 24, gap: spacing[4] }, formPane: { flex: 1, width: "100%", maxWidth: 560, minWidth: 280, gap: spacing[6] } });
