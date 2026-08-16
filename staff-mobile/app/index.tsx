import { Redirect } from "expo-router";
import { useAuth } from "@/auth/auth-context";

export default function Index() {
  return <Redirect href={useAuth().state === "authenticated" ? "/(protected)/dashboard" : "/(public)/login"} />;
}
