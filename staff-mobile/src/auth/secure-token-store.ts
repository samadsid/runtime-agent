import * as SecureStore from "expo-secure-store";

const TOKEN_KEY = "staff-access-token";

export const secureTokenStore = {
  read: () => SecureStore.getItemAsync(TOKEN_KEY),
  write: (token: string) => SecureStore.setItemAsync(TOKEN_KEY, token, {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  }),
  clear: () => SecureStore.deleteItemAsync(TOKEN_KEY),
};
