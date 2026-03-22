/** Get a value from localStorage (web fallback for expo-secure-store) */
export async function getItem(key: string): Promise<string | null> {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

/** Set a value in localStorage */
export async function setItem(key: string, value: string): Promise<void> {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage full or unavailable — silently fail
  }
}

/** Delete a value from localStorage */
export async function deleteItem(key: string): Promise<void> {
  try {
    localStorage.removeItem(key);
  } catch {
    // Silently fail
  }
}
