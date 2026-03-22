import Foundation

/// A message in the conversation
struct ChatMessage: Identifiable, Codable, Equatable {
    let id: String
    let role: String  // "user" or "assistant"
    let content: String
    let audioUrl: String?
    let createdAt: String
    var isPending: Bool = false  // For optimistic UI - true until confirmed by server

    var isUser: Bool { role == "user" }
    var isAssistant: Bool { role == "assistant" }

    enum CodingKeys: String, CodingKey {
        case id, role, content
        case audioUrl = "audio_url"
        case createdAt = "created_at"
        // isPending is not encoded - it's local state only
    }

    init(id: String, role: String, content: String, audioUrl: String? = nil, createdAt: String, isPending: Bool = false) {
        self.id = id
        self.role = role
        self.content = content
        self.audioUrl = audioUrl
        self.createdAt = createdAt
        self.isPending = isPending
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        role = try container.decode(String.self, forKey: .role)
        content = try container.decode(String.self, forKey: .content)
        audioUrl = try container.decodeIfPresent(String.self, forKey: .audioUrl)
        createdAt = try container.decode(String.self, forKey: .createdAt)
        isPending = false  // Server messages are never pending
    }
}

/// Response from GET /messages
struct MessagesResponse: Codable {
    let messages: [ChatMessage]
}

/// Response from POST /prompt
struct PromptResponse: Codable {
    let status: String
    let message: String
    let requestId: String

    enum CodingKeys: String, CodingKey {
        case status, message
        case requestId = "request_id"
    }
}

/// App-wide state for the conversation
@MainActor
class ConversationStore: ObservableObject {
    static let shared = ConversationStore()

    @Published var messages: [ChatMessage] = []
    @Published var isLoading = false
    @Published var error: String?
    @Published var isPolling = false

    private var pollTask: Task<Void, Never>?
    private var lastMessageTimestamp: String?
    private var isFetching = false  // Prevent concurrent fetches
    private var consecutiveErrors = 0
    private let maxConsecutiveErrors = 5

    private init() {}

    /// Start polling for new messages
    func startPolling() {
        guard pollTask == nil else { return }
        isPolling = true
        consecutiveErrors = 0

        pollTask = Task {
            while !Task.isCancelled {
                await fetchNewMessages()

                // Exponential backoff on errors
                let delay: UInt64 = consecutiveErrors > 0
                    ? min(UInt64(pow(2.0, Double(consecutiveErrors))) * 1_000_000_000, 30_000_000_000)
                    : 1_000_000_000

                try? await Task.sleep(nanoseconds: delay)
            }
        }
    }

    /// Stop polling
    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
        isPolling = false
        isFetching = false
    }

    /// Clear messages for a fresh reload (prevents stale data flash on foreground)
    func clearForRefresh() {
        messages = []
        lastMessageTimestamp = nil
        isLoading = true
    }

    /// Fetch all messages (initial load)
    func loadMessages() async {
        isLoading = true
        error = nil

        do {
            let newMessages = try await SvenAPIClient.shared.getMessages()
            messages = newMessages
            lastMessageTimestamp = newMessages.last?.createdAt
        } catch {
            self.error = "Failed to load messages: \(error.localizedDescription)"
        }

        isLoading = false
    }

    /// Fetch new messages since last poll
    func fetchNewMessages() async {
        // Prevent concurrent fetches
        guard !isFetching else { return }
        isFetching = true
        defer { isFetching = false }

        do {
            let newMessages = try await SvenAPIClient.shared.getMessages(since: lastMessageTimestamp)
            consecutiveErrors = 0  // Reset on success

            if !newMessages.isEmpty {
                // Process all new messages atomically
                var updatedMessages = messages

                for msg in newMessages {
                    // Check if we already have this message by ID
                    if updatedMessages.contains(where: { $0.id == msg.id }) {
                        continue
                    }

                    // For user messages, also check if we have an optimistic version with same content
                    // (the server's user message will have a different ID than our temp ID)
                    if msg.isUser {
                        if let existingIndex = updatedMessages.firstIndex(where: {
                            $0.content == msg.content && $0.isPending
                        }) {
                            // Replace optimistic message with server-confirmed one
                            updatedMessages[existingIndex] = msg
                            continue
                        }
                    }

                    updatedMessages.append(msg)
                }

                // Update atomically
                messages = updatedMessages
                lastMessageTimestamp = newMessages.last?.createdAt
            }
        } catch {
            consecutiveErrors += 1
            print("Polling error (\(consecutiveErrors)): \(error)")

            // Show error to user if persistent
            if consecutiveErrors >= maxConsecutiveErrors {
                self.error = "Connection issues. Retrying..."
            }
        }
    }

    /// Send a message (user transcript)
    func sendMessage(_ content: String) async -> Bool {
        print("[ConversationStore] sendMessage called with: '\(content)'")

        // Create optimistic message immediately
        let tempId = UUID().uuidString
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let timestamp = formatter.string(from: Date())

        let optimisticMessage = ChatMessage(
            id: tempId,
            role: "user",
            content: content,
            audioUrl: nil,
            createdAt: timestamp,
            isPending: true
        )

        // Show message immediately
        messages.append(optimisticMessage)
        isLoading = true
        error = nil

        do {
            print("[ConversationStore] Calling API sendTranscript...")
            let response = try await SvenAPIClient.shared.sendTranscript(content)
            print("[ConversationStore] API returned requestId: \(response.requestId)")
            // Replace optimistic message with confirmed one when it arrives via polling
            // For now, just mark as confirmed by removing pending flag
            if let index = messages.firstIndex(where: { $0.id == tempId }) {
                messages[index].isPending = false
                // Update ID to match server's ID
                messages[index] = ChatMessage(
                    id: response.requestId,
                    role: "user",
                    content: content,
                    audioUrl: nil,
                    createdAt: timestamp,
                    isPending: false
                )
            }
            isLoading = false
            return true
        } catch {
            print("[ConversationStore] API error: \(error)")
            // Remove optimistic message on failure
            messages.removeAll { $0.id == tempId }
            self.error = "Failed to send: \(error.localizedDescription)"
            isLoading = false
            return false
        }
    }

    /// Clear all messages
    func clearMessages() async {
        do {
            try await SvenAPIClient.shared.clearMessages()
            messages = []
            lastMessageTimestamp = nil
        } catch {
            self.error = "Failed to clear: \(error.localizedDescription)"
        }
    }

    /// Download audio for a message
    func downloadAudio(for message: ChatMessage) async -> URL? {
        guard let audioUrl = message.audioUrl else {
            print("[ConversationStore] downloadAudio: no audioUrl for message \(message.id)")
            return nil
        }
        do {
            let url = try await SvenAPIClient.shared.downloadAudio(path: audioUrl, messageId: message.id)
            print("[ConversationStore] downloadAudio: downloaded to \(url)")
            return url
        } catch {
            print("[ConversationStore] downloadAudio: failed - \(error)")
            return nil
        }
    }

    /// Restart the Claude session
    func restartSession() async {
        do {
            try await SvenAPIClient.shared.restartSession()
            // Session restarted - context is fresh now
        } catch {
            self.error = "Failed to restart session: \(error.localizedDescription)"
        }
    }
}
