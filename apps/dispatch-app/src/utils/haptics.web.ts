// No-op haptics for web — vibration is annoying on desktop

export async function impactLight(): Promise<void> {}
export async function impactMedium(): Promise<void> {}
export async function impactHeavy(): Promise<void> {}
export async function selectionFeedback(): Promise<void> {}
export async function notificationSuccess(): Promise<void> {}
export async function notificationWarning(): Promise<void> {}
export async function notificationError(): Promise<void> {}
