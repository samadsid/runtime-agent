import { readEnvironment } from "./environment";

test("accepts configured development environment", () => {
  expect(readEnvironment({ EXPO_PUBLIC_API_BASE_URL: "http://10.0.2.2:8000/", EXPO_PUBLIC_APP_ENV: "development", EXPO_PUBLIC_REQUEST_TIMEOUT_MS: "5000" }).apiBaseUrl).toBe("http://10.0.2.2:8000");
});

test("rejects insecure staging and production localhost", () => {
  expect(() => readEnvironment({ EXPO_PUBLIC_API_BASE_URL: "http://staging.example.com", EXPO_PUBLIC_APP_ENV: "staging" })).toThrow("HTTPS");
  expect(() => readEnvironment({ EXPO_PUBLIC_API_BASE_URL: "https://localhost:8000", EXPO_PUBLIC_APP_ENV: "production" })).toThrow("local API");
});
