import { apiRequest, getDeviceToken } from "./client";
import { generateUUID } from "../utils/uuid";
import type {
  ChatsResponse,
  Conversation,
  MessagesResponse,
  PromptResponse,
} from "./types";

/** List all chats with last message previews. GET /chats */
export async function getChats(): Promise<Conversation[]> {
  const res = await apiRequest<ChatsResponse>("/chats");
  return res.chats;
}

/** Create a new chat. POST /chats */
export async function createChat(
  title?: string,
): Promise<Conversation> {
  return apiRequest<Conversation>("/chats", {
    method: "POST",
    body: { token: getDeviceToken() ?? "", title },
  });
}

/** Rename a chat. PATCH /chats/:chatId */
export async function updateChat(
  chatId: string,
  title: string,
): Promise<Conversation> {
  return apiRequest<Conversation>(`/chats/${chatId}`, {
    method: "PATCH",
    body: { token: getDeviceToken() ?? "", title },
  });
}

/** Delete a chat and its messages. DELETE /chats/:chatId */
export async function deleteChat(chatId: string): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>(`/chats/${chatId}`, {
    method: "DELETE",
  });
}

/** Get messages for a chat. GET /messages */
export async function getMessages(
  chatId: string,
  since?: string,
): Promise<MessagesResponse> {
  return apiRequest<MessagesResponse>("/messages", {
    params: { chat_id: chatId, since: since ?? undefined },
  });
}

/** Send a text prompt. POST /prompt */
export async function sendPrompt(
  transcript: string,
  chatId: string = "voice",
  messageId?: string,
): Promise<PromptResponse> {
  return apiRequest<PromptResponse>("/prompt", {
    method: "POST",
    body: {
      transcript,
      token: getDeviceToken() ?? "",
      chat_id: chatId,
      message_id: messageId ?? generateUUID(),
    },
  });
}

/** Send a prompt with an image attachment. POST /prompt-with-image */
export async function sendPromptWithImage(
  transcript: string,
  imageUri: string,
  chatId: string = "voice",
  messageId?: string,
): Promise<PromptResponse> {
  const formData = new FormData();
  formData.append("transcript", transcript);
  formData.append("token", getDeviceToken() ?? "");
  formData.append("chat_id", chatId);
  formData.append("message_id", messageId ?? generateUUID());

  // For React Native, we need to pass the file as a file-like object
  const filename = imageUri.split("/").pop() || "image.jpg";
  const match = /\.(\w+)$/.exec(filename);
  const ext = match ? match[1].toLowerCase() : "jpg";
  const videoExts = ["mp4", "mov", "m4v", "avi", "mkv"];
  const audioExts = ["mp3", "m4a", "wav", "aac", "ogg", "flac", "opus", "wma", "caf"];
  const mimeType = videoExts.includes(ext)
    ? `video/${ext}`
    : audioExts.includes(ext)
      ? `audio/${ext === "mp3" ? "mpeg" : ext}`
      : `image/${ext}`;

  formData.append("image", {
    uri: imageUri,
    name: filename,
    type: mimeType,
  } as unknown as Blob);

  return apiRequest<PromptResponse>("/prompt-with-image", {
    method: "POST",
    body: formData,
  });
}

/** Generate a cover image for a chat by summarizing its conversation. POST /generate-image */
export async function generateChatImage(
  chatId: string,
): Promise<{ chat_id: string; status: string }> {
  return apiRequest<{ chat_id: string; status: string }>("/generate-image", {
    method: "POST",
    body: { chat_id: chatId },
  });
}

/** Fork a chat. POST /chats/:chatId/fork */
export async function forkChat(
  chatId: string,
  title: string,
): Promise<Conversation> {
  return apiRequest<Conversation>(`/chats/${chatId}/fork`, {
    method: "POST",
    body: { token: getDeviceToken() ?? "", title },
  });
}

/** Mark a chat as manually unread. POST /chats/:chatId/unread */
export async function markChatAsUnread(
  chatId: string,
): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>(`/chats/${chatId}/unread`, {
    method: "POST",
  });
}

/** Mark a chat as opened (for unread tracking). POST /chats/:chatId/open */
export async function markChatAsOpened(
  chatId: string,
): Promise<{ status: string }> {
  return apiRequest<{ status: string }>(`/chats/${chatId}/open`, {
    method: "POST",
  });
}

/** Clear all messages for a chat. DELETE /messages */
export async function clearMessages(
  chatId: string,
): Promise<{ status: string; message: string }> {
  return apiRequest<{ status: string; message: string }>("/messages", {
    method: "DELETE",
    params: { chat_id: chatId },
  });
}

/** Restart the Claude session for a chat. POST /restart-session */
export async function restartSession(
  chatId: string = "voice",
): Promise<{ status: string; message: string }> {
  return apiRequest<{ status: string; message: string }>(
    "/restart-session",
    {
      method: "POST",
      params: { chat_id: chatId },
    },
  );
}
