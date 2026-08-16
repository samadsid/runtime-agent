# AI Commerce Staff Mobile

Android-first Expo application for fulfilment staff and administrators. It calls only the authenticated `/api/staff/v1` API and never persists order or delivery data.

## Local development

Node 20.19.4 or newer is required by Expo SDK 57 / React Native 0.86. Copy `.env.example` to `.env`, use the computer's LAN address for a physical device or `http://10.0.2.2:8000` for the Android emulator, then run:

```bash
npm install
npm run typecheck
npm test
npm run android
```

Android API 24 is the configured minimum. HTTP is permitted only by the development build profile; staging and production configuration require HTTPS.

## Builds and tests

`eas build --profile preview --platform android` creates the signed internal-testing APK after EAS credentials and the staging API URL are configured. Production produces an AAB but Play Store publication is outside this milestone.

Maestro flows require a seeded staging backend and `STAFF_EMAIL`, `STAFF_PASSWORD`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD`. Run `npm run test:e2e` against the installed preview APK. Concurrency, ambiguous-response, and token-expiry scenarios require staging test controls or a second actor and are documented acceptance exercises when those external controls are available.

Do not add access tokens, passwords, signing credentials, customer PII, real API payloads, or environment secrets to logs, tests, EAS configuration committed to source, or persisted query storage.


• From the repository root:

  cd staff-mobile
  cp .env.example .env
  npm install

  Edit staff-mobile/.env:

  For an Android emulator:

  EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000
  EXPO_PUBLIC_APP_ENV=development
  EXPO_PUBLIC_REQUEST_TIMEOUT_MS=15000

  For a physical Android device, use your computer’s LAN IP instead of localhost:

  EXPO_PUBLIC_API_BASE_URL=http://192.168.1.100:8000
  EXPO_PUBLIC_APP_ENV=development
  EXPO_PUBLIC_REQUEST_TIMEOUT_MS=15000

  Start the backend so devices can reach it:

  cd /home/samad/Documents/commerce-agent
  source .venv/bin/activate
  uvicorn app.main:app --host 0.0.0.0 --port 8000

  Ensure STAFF_AUTH_ENABLED=true and staff JWT/database settings are configured.

  Then start the mobile app:

  cd staff-mobile
  npm run android

  This opens the Android emulator. Alternatively, start Expo:

  npm start

  Then scan the QR code with Expo Go on a physical Android device. The phone and computer must be on the same network.

  Before running, verify everything:

  npm run typecheck
  npm test
  npx expo install --check

  If Expo keeps an old .env value, restart with a cleared cache:

  npx expo start --clear

  You’ll need a bootstrapped ADMIN or FULFILMENT_STAFF account to log in. Setup details are in staff-mobile/README.md.