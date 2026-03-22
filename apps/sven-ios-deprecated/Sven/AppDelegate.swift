import UIKit
import UserNotifications
import AVFoundation

class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    // Audio player for notification sounds
    private var audioPlayer: AVAudioPlayer?

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        registerNotificationCategories()
        registerForPushNotifications()
        return true
    }

    // MARK: - Notification Categories with Action Buttons

    func registerNotificationCategories() {
        // Action: Like response
        let likeAction = UNNotificationAction(
            identifier: "LIKE_ACTION",
            title: "👍 Like",
            options: []
        )

        // Action: Dislike response
        let dislikeAction = UNNotificationAction(
            identifier: "DISLIKE_ACTION",
            title: "👎",
            options: [.destructive]
        )

        // Action: Reply (opens app)
        let replyAction = UNNotificationAction(
            identifier: "REPLY_ACTION",
            title: "Reply",
            options: [.foreground]
        )

        // Action: Play audio
        let playAudioAction = UNNotificationAction(
            identifier: "PLAY_AUDIO_ACTION",
            title: "🔊 Play",
            options: []
        )

        // Action: View report
        let viewReportAction = UNNotificationAction(
            identifier: "VIEW_REPORT_ACTION",
            title: "📄 View",
            options: [.foreground]
        )

        // Category: Standard message (like, dislike, reply)
        let messageCategory = UNNotificationCategory(
            identifier: "MESSAGE_CATEGORY",
            actions: [likeAction, replyAction, dislikeAction],
            intentIdentifiers: [],
            hiddenPreviewsBodyPlaceholder: "New message from Sven",
            options: [.customDismissAction]
        )

        // Category: Audio message (play audio, like, reply)
        let audioCategory = UNNotificationCategory(
            identifier: "AUDIO_CATEGORY",
            actions: [playAudioAction, likeAction, replyAction],
            intentIdentifiers: [],
            hiddenPreviewsBodyPlaceholder: "Audio message from Sven",
            options: []
        )

        // Category: Report/PDF (view, like)
        let reportCategory = UNNotificationCategory(
            identifier: "REPORT_CATEGORY",
            actions: [viewReportAction, likeAction],
            intentIdentifiers: [],
            hiddenPreviewsBodyPlaceholder: "Report from Sven",
            options: []
        )

        // Category: Image notification
        let imageCategory = UNNotificationCategory(
            identifier: "IMAGE_CATEGORY",
            actions: [likeAction, replyAction],
            intentIdentifiers: [],
            hiddenPreviewsBodyPlaceholder: "Image from Sven",
            options: []
        )

        // Register all categories
        UNUserNotificationCenter.current().setNotificationCategories([
            messageCategory,
            audioCategory,
            reportCategory,
            imageCategory
        ])

        print("Notification categories registered")
    }

    func registerForPushNotifications() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            if let error = error {
                print("Push notification authorization error: \(error)")
                return
            }
            guard granted else {
                print("Push notification permission denied")
                return
            }
            DispatchQueue.main.async {
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
    }

    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        print("APNs device token: \(token)")

        // Send token to backend
        Task {
            do {
                try await SvenAPIClient.shared.registerAPNsToken(token)
                print("APNs token registered with backend")
            } catch {
                print("Failed to register APNs token: \(error)")
            }
        }
    }

    func application(_ application: UIApplication,
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("Failed to register for APNs: \(error)")
    }

    // Handle notification when app is in foreground
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        // Show banner and play sound even when app is in foreground
        completionHandler([.banner, .sound, .badge])
    }

    // Handle notification tap and action buttons
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        let userInfo = response.notification.request.content.userInfo
        let messageId = userInfo["message_id"] as? String

        switch response.actionIdentifier {
        case "LIKE_ACTION":
            print("User liked message: \(messageId ?? "unknown")")
            sendFeedback(messageId: messageId, type: "like")

        case "DISLIKE_ACTION":
            print("User disliked message: \(messageId ?? "unknown")")
            sendFeedback(messageId: messageId, type: "dislike")

        case "REPLY_ACTION":
            print("User wants to reply to: \(messageId ?? "unknown")")
            // App will open and focus on reply - handled by foreground option
            NotificationCenter.default.post(name: .focusReply, object: nil)

        case "PLAY_AUDIO_ACTION":
            print("User wants to play audio for: \(messageId ?? "unknown")")
            if let audioUrl = userInfo["audio_url"] as? String {
                playAudioInBackground(audioUrl: audioUrl)
            }

        case "VIEW_REPORT_ACTION":
            print("User wants to view report: \(messageId ?? "unknown")")
            if let reportUrl = userInfo["report_url"] as? String {
                NotificationCenter.default.post(name: .viewReport, object: reportUrl)
            }

        case UNNotificationDefaultActionIdentifier:
            // User tapped the notification banner (default action)
            if let messageId = messageId {
                print("Opening app for message: \(messageId)")
            }

        default:
            break
        }

        // Post notification to trigger message refresh
        NotificationCenter.default.post(name: .refreshMessages, object: nil)
        completionHandler()
    }

    // MARK: - Feedback & Audio Helpers

    private func sendFeedback(messageId: String?, type: String) {
        guard let messageId = messageId else { return }
        Task {
            do {
                try await SvenAPIClient.shared.sendFeedback(messageId: messageId, type: type)
                print("Feedback sent: \(type) for \(messageId)")
            } catch {
                print("Failed to send feedback: \(error)")
            }
        }
    }

    private func playAudioInBackground(audioUrl: String) {
        // Download and play audio
        Task {
            do {
                // Construct full URL
                let baseURL = "http://10.10.10.59:9091"
                guard let url = URL(string: "\(baseURL)\(audioUrl)") else { return }

                // Download audio
                let (tempURL, _) = try await URLSession.shared.download(from: url)

                // Play on main thread
                await MainActor.run {
                    do {
                        try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
                        try AVAudioSession.sharedInstance().setActive(true)
                        audioPlayer = try AVAudioPlayer(contentsOf: tempURL)
                        audioPlayer?.play()
                        print("Playing audio from notification")
                    } catch {
                        print("Failed to play audio: \(error)")
                    }
                }
            } catch {
                print("Failed to download audio: \(error)")
            }
        }
    }
}

// Notification names
extension Notification.Name {
    static let refreshMessages = Notification.Name("refreshMessages")
    static let focusReply = Notification.Name("focusReply")
    static let viewReport = Notification.Name("viewReport")
}
