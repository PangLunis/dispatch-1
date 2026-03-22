import SwiftUI

@MainActor
class AppState: ObservableObject {
    static let shared = AppState()
    @Published var shouldStartRecording = false

    /// Cached permission state - avoids re-checking on every launch
    @Published var permissionsGranted: Bool = false

    /// Key for UserDefaults permission cache
    private let permissionsCacheKey = "com.sven.permissionsGranted"

    private init() {
        // Load cached permission state for instant startup
        permissionsGranted = UserDefaults.standard.bool(forKey: permissionsCacheKey)
    }

    /// Update and persist permission state
    func setPermissionsGranted(_ granted: Bool) {
        permissionsGranted = granted
        UserDefaults.standard.set(granted, forKey: permissionsCacheKey)
    }
}
