import * as SecureStore from "expo-secure-store";

/** Get a value from secure storage (Keychain on iOS) */
export async function getItem(key: string): Promise<string | null> {
  return SecureStore.getItemAsync(key);
}

/** Set a value in secure storage */
export async function setItem(key: string, value: string): Promise<void> {
  await SecureStore.setItemAsync(key, value);
}

/** Delete a value from secure storage */
export async function deleteItem(key: string): Promise<void> {
  await SecureStore.deleteItemAsync(key);
}
