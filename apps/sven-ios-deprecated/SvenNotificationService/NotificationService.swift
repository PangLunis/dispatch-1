import UserNotifications
import MobileCoreServices

class NotificationService: UNNotificationServiceExtension {

    var contentHandler: ((UNNotificationContent) -> Void)?
    var bestAttemptContent: UNMutableNotificationContent?

    override func didReceive(_ request: UNNotificationRequest,
                          withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void) {
        self.contentHandler = contentHandler
        bestAttemptContent = (request.content.mutableCopy() as? UNMutableNotificationContent)

        guard let bestAttemptContent = bestAttemptContent else {
            contentHandler(request.content)
            return
        }

        // Check for image URL
        if let imageURLString = bestAttemptContent.userInfo["image_url"] as? String,
           let imageURL = URL(string: imageURLString) {
            downloadAndAttach(url: imageURL, type: .image, to: bestAttemptContent) { content in
                contentHandler(content)
            }
            return
        }

        // Check for audio URL (for audio thumbnail/preview)
        if let audioURLString = bestAttemptContent.userInfo["audio_url"] as? String,
           let audioURL = URL(string: audioURLString) {
            // For audio, we still show the notification but add audio icon
            // The actual playback happens via action button
            downloadAndAttach(url: audioURL, type: .audio, to: bestAttemptContent) { content in
                contentHandler(content)
            }
            return
        }

        // No media to attach
        contentHandler(bestAttemptContent)
    }

    override func serviceExtensionTimeWillExpire() {
        // Called if service extension exceeds 30 seconds
        if let contentHandler = contentHandler,
           let bestAttemptContent = bestAttemptContent {
            contentHandler(bestAttemptContent)
        }
    }

    // MARK: - Media Download & Attachment

    enum MediaType {
        case image
        case audio
        case video
    }

    private func downloadAndAttach(url: URL,
                                   type: MediaType,
                                   to content: UNMutableNotificationContent,
                                   completion: @escaping (UNNotificationContent) -> Void) {
        let session = URLSession(configuration: .default)

        session.downloadTask(with: url) { tempURL, response, error in
            guard let tempURL = tempURL, error == nil else {
                print("Failed to download media: \(error?.localizedDescription ?? "unknown")")
                completion(content)
                return
            }

            // Determine file extension
            let fileExtension: String
            switch type {
            case .image:
                fileExtension = self.getImageExtension(from: response) ?? "jpg"
            case .audio:
                fileExtension = "wav"
            case .video:
                fileExtension = "mp4"
            }

            // Create unique filename
            let fileName = UUID().uuidString + "." + fileExtension
            let targetURL = FileManager.default.temporaryDirectory.appendingPathComponent(fileName)

            do {
                // Move to target location
                try FileManager.default.moveItem(at: tempURL, to: targetURL)

                // Create attachment
                let options: [String: Any]?
                switch type {
                case .image:
                    options = [UNNotificationAttachmentOptionsThumbnailHiddenKey: false]
                case .audio:
                    options = [UNNotificationAttachmentOptionsThumbnailHiddenKey: true]
                case .video:
                    options = [UNNotificationAttachmentOptionsThumbnailTimeKey: 0]
                }

                let attachment = try UNNotificationAttachment(
                    identifier: type == .image ? "image" : "audio",
                    url: targetURL,
                    options: options
                )

                content.attachments = [attachment]
                print("Successfully attached \(type) to notification")
            } catch {
                print("Failed to attach media: \(error)")
            }

            completion(content)
        }.resume()
    }

    private func getImageExtension(from response: URLResponse?) -> String? {
        guard let mimeType = response?.mimeType else { return nil }

        switch mimeType {
        case "image/jpeg":
            return "jpg"
        case "image/png":
            return "png"
        case "image/gif":
            return "gif"
        case "image/webp":
            return "webp"
        default:
            return "jpg"
        }
    }
}
