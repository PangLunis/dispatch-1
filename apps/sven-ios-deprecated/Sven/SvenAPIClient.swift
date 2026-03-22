import Foundation
import Security

/// Client for communicating with the Sven API server on the Mac
class SvenAPIClient {
    static let shared = SvenAPIClient()

    // Server URL key for UserDefaults
    private static let serverURLKey = "sven_server_url"

    // Default URLs for different environments
    #if targetEnvironment(simulator)
    private static let defaultURL = "http://localhost:9091"
    #else
    private static let defaultURL = "http://localhost:9091"  // User must configure via settings
    #endif

    // Get the configured server URL (or default)
    var baseURL: String {
        UserDefaults.standard.string(forKey: SvenAPIClient.serverURLKey) ?? SvenAPIClient.defaultURL
    }

    // Get/set the server URL
    static var serverURL: String {
        get {
            UserDefaults.standard.string(forKey: serverURLKey) ?? defaultURL
        }
        set {
            var url = newValue.trimmingCharacters(in: .whitespacesAndNewlines)
            // Ensure it has http:// prefix
            if !url.hasPrefix("http://") && !url.hasPrefix("https://") {
                url = "http://" + url
            }
            // Remove trailing slash
            if url.hasSuffix("/") {
                url = String(url.dropLast())
            }
            UserDefaults.standard.set(url, forKey: serverURLKey)
        }
    }

    // Check if server URL has been configured
    static var isServerConfigured: Bool {
        UserDefaults.standard.string(forKey: serverURLKey) != nil
    }

    // Keychain key for device token
    private let tokenKeychainKey = "com.sven.deviceToken"

    // Cache directory for audio files
    private let audioCacheDir: URL

    private init() {
        let cacheDir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        audioCacheDir = cacheDir.appendingPathComponent("sven-audio")
        try? FileManager.default.createDirectory(at: audioCacheDir, withIntermediateDirectories: true)
    }

    // MARK: - API Methods

    /// Send transcript to the Mac API server
    func sendTranscript(_ transcript: String) async throws -> PromptResponse {
        guard !transcript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw APIError.emptyTranscript
        }

        let token = getOrCreateDeviceToken()
        guard let url = URL(string: "\(baseURL)/prompt") else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30

        let body: [String: Any] = [
            "transcript": transcript,
            "token": token
        ]

        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        guard httpResponse.statusCode == 200 else {
            let errorBody = String(data: data, encoding: .utf8) ?? "unknown"
            throw APIError.serverError(statusCode: httpResponse.statusCode, message: errorBody)
        }

        return try JSONDecoder().decode(PromptResponse.self, from: data)
    }

    /// Get messages from the conversation
    func getMessages(since: String? = nil) async throws -> [ChatMessage] {
        var urlString = "\(baseURL)/messages"
        if let since = since {
            urlString += "?since=\(since.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? since)"
        }

        guard let url = URL(string: urlString) else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = 10

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        guard httpResponse.statusCode == 200 else {
            throw APIError.serverError(statusCode: httpResponse.statusCode, message: "Failed to get messages")
        }

        let messagesResponse = try JSONDecoder().decode(MessagesResponse.self, from: data)
        return messagesResponse.messages
    }

    /// Download audio file for a message
    func downloadAudio(path: String, messageId: String) async throws -> URL {
        // Check cache first
        let cachedFile = audioCacheDir.appendingPathComponent("\(messageId).wav")
        if FileManager.default.fileExists(atPath: cachedFile.path) {
            return cachedFile
        }

        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw APIError.invalidURL
        }

        let (tempURL, response) = try await URLSession.shared.download(from: url)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.audioDownloadFailed
        }

        // Move to cache
        try? FileManager.default.removeItem(at: cachedFile)
        try FileManager.default.moveItem(at: tempURL, to: cachedFile)

        return cachedFile
    }

    /// Clear all messages
    func clearMessages() async throws {
        guard let url = URL(string: "\(baseURL)/messages") else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.timeoutInterval = 10

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.serverError(statusCode: 0, message: "Failed to clear messages")
        }
    }

    /// Restart the Claude session
    func restartSession() async throws {
        let token = getOrCreateDeviceToken()
        guard let url = URL(string: "\(baseURL)/restart-session?token=\(token)") else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 30

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.serverError(statusCode: 0, message: "Failed to restart session")
        }
    }

    /// Register APNs device token with the backend
    func registerAPNsToken(_ apnsToken: String) async throws {
        let deviceToken = getOrCreateDeviceToken()
        guard let url = URL(string: "\(baseURL)/register-apns") else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 10

        let body: [String: String] = [
            "device_token": deviceToken,
            "apns_token": apnsToken
        ]

        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.serverError(statusCode: 0, message: "Failed to register APNs token")
        }
    }

    /// Send feedback (like/dislike) for a message
    func sendFeedback(messageId: String, type: String) async throws {
        guard let url = URL(string: "\(baseURL)/feedback") else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 10

        let body: [String: String] = [
            "message_id": messageId,
            "feedback_type": type,
            "token": getOrCreateDeviceToken()
        ]

        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.serverError(statusCode: 0, message: "Failed to send feedback")
        }
    }

    // MARK: - Token Management

    private func getOrCreateDeviceToken() -> String {
        if let existingToken = getTokenFromKeychain() {
            return existingToken
        }

        let newToken = UUID().uuidString
        saveTokenToKeychain(newToken)
        return newToken
    }

    private func getTokenFromKeychain() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: tokenKeychainKey,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        if status == errSecSuccess, let data = result as? Data {
            return String(data: data, encoding: .utf8)
        }

        return nil
    }

    private func saveTokenToKeychain(_ token: String) {
        let data = token.data(using: .utf8)!

        let deleteQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: tokenKeychainKey
        ]
        SecItemDelete(deleteQuery as CFDictionary)

        let addQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: tokenKeychainKey,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock
        ]

        SecItemAdd(addQuery as CFDictionary, nil)
    }
}

// MARK: - Error Types

enum APIError: LocalizedError {
    case emptyTranscript
    case invalidURL
    case invalidResponse
    case serverError(statusCode: Int, message: String)
    case audioDownloadFailed

    var errorDescription: String? {
        switch self {
        case .emptyTranscript:
            return "Empty transcript"
        case .invalidURL:
            return "Invalid URL"
        case .invalidResponse:
            return "Invalid response"
        case .serverError(let code, let message):
            return "Server error (\(code)): \(message)"
        case .audioDownloadFailed:
            return "Failed to download audio"
        }
    }
}
