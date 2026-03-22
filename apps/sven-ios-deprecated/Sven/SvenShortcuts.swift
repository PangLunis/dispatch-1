import AppIntents

struct AskSvenIntent: AppIntent {
    static var title: LocalizedStringResource = "Ask Sven"
    static var description = IntentDescription("Start a voice recording with Sven")
    static var openAppWhenRun: Bool = true

    @MainActor
    func perform() async throws -> some IntentResult {
        AppState.shared.shouldStartRecording = true
        return .result()
    }
}

struct SvenShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: AskSvenIntent(),
            phrases: [
                "Ask \(.applicationName)",
                "Record with \(.applicationName)",
                "Start \(.applicationName)"
            ],
            shortTitle: "Ask Sven",
            systemImageName: "mic.fill"
        )
    }
}
