import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from "react-native";
import { z } from "zod";

import { StaffApiError } from "@/api/errors";
import { useAuth } from "@/auth/auth-context";
import { Button, Card, Field, Screen, dsStyles } from "@/components/design-system";
import { spacing, useTheme } from "@/components/design-system/theme";
import { recordEvent } from "@/observability/events";

export const loginSchema = z.object({ email: z.string().trim().email("Enter a valid email address."), password: z.string().min(1, "Enter your password.") });
type LoginValues = z.infer<typeof loginSchema>;

export default function LoginScreen() {
  const theme = useTheme();
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
  return <Screen><KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.page}>
      <View><Text style={[dsStyles.title, { color: theme.text }]}>Staff operations</Text><Text style={[dsStyles.body, { color: theme.muted }]}>Sign in to manage fulfilment orders.</Text></View>
      <Card>
        <Controller control={control} name="email" render={({ field }) => <Field label="Email" autoCapitalize="none" autoComplete="email" keyboardType="email-address" value={field.value} onBlur={field.onBlur} onChangeText={field.onChange} error={errors.email?.message} />} />
        <Controller control={control} name="password" render={({ field }) => <Field label="Password" secureTextEntry={!visible} autoComplete="current-password" value={field.value} onBlur={field.onBlur} onChangeText={field.onChange} error={errors.password?.message} />} />
        <Button variant="secondary" label={visible ? "Hide password" : "Show password"} onPress={() => setVisible((value) => !value)} />
        {submitError ? <Text accessibilityRole="alert" style={{ color: theme.danger }}>{submitError}</Text> : null}
        <Button testID="login-submit" label={isSubmitting ? "Signing in…" : "Sign in"} disabled={isSubmitting} onPress={() => void submit()} />
      </Card>
    </ScrollView>
  </KeyboardAvoidingView></Screen>;
}
const styles = StyleSheet.create({ page: { flexGrow: 1, justifyContent: "center", padding: spacing.lg, gap: spacing.lg } });
