import { apiRequest } from "./client";
import type { ChatNotes } from "./types";

/** Get notes for a chat. GET /chats/:chatId/notes */
export async function getChatNotes(chatId: string): Promise<ChatNotes> {
  return apiRequest<ChatNotes>(`/chats/${chatId}/notes`);
}

/** Create or update notes for a chat (upsert). PUT /chats/:chatId/notes */
export async function updateChatNotes(
  chatId: string,
  content: string,
): Promise<ChatNotes> {
  return apiRequest<ChatNotes>(`/chats/${chatId}/notes`, {
    method: "PUT",
    body: { content },
  });
}
