import SwiftUI
import AVFoundation

// MARK: - Main Content View

struct ContentView: View {
    @StateObject private var recorder = AudioRecorder()
    @StateObject private var appState = AppState.shared
    @StateObject private var conversationStore = ConversationStore.shared

    @State private var showingProfile = false
    @State private var autoReadEnabled = false
    @State private var textInput = ""
    @State private var isKeyboardMode = false
    @State private var isSendingText = false
    @State private var showRecordingSheet = false
    @State private var recordingHasSent = false  // Shared with RecordingSheet to prevent state desync
    @FocusState private var isTextFieldFocused: Bool
    @Environment(\.scenePhase) private var scenePhase

    // Audio player for TTS - use StateObject for stable reference
    @StateObject private var audioPlayerManager = AudioPlayerManager()
    @State private var currentPlayingMessageId: String?

    // Debug logs for UI display
    @State private var debugLogs: [String] = []
    @State private var showDebugLogs = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Error banner
                if let error = conversationStore.error {
                    errorBanner(error)
                }

                // Debug log view (toggle with long press on title)
                if showDebugLogs {
                    debugLogView
                }

                // Messages area
                messagesArea

                // Status area (live transcript or thinking)
                statusArea

                // Input bar
                inputBar
            }
            .navigationTitle("Sven")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    HStack(spacing: 16) {
                        // Auto-read toggle (always visible)
                        Button(action: { autoReadEnabled.toggle() }) {
                            Image(systemName: autoReadEnabled ? "speaker.wave.2.fill" : "speaker.slash.fill")
                                .foregroundColor(autoReadEnabled ? .blue : .secondary)
                        }

                        // Hamburger menu
                        Menu {
                            Button(action: restartSession) {
                                Label("Restart Session", systemImage: "arrow.clockwise")
                            }

                            Button(role: .destructive, action: {
                                Task {
                                    await conversationStore.clearMessages()
                                }
                            }) {
                                Label("Clear Chat", systemImage: "trash")
                            }

                            Divider()

                            Button(action: { showDebugLogs.toggle() }) {
                                Label(showDebugLogs ? "Hide Debug Logs" : "Show Debug Logs", systemImage: "ladybug")
                            }

                            Button(action: { showingProfile = true }) {
                                Label("Settings", systemImage: "gear")
                            }
                        } label: {
                            Image(systemName: "ellipsis.circle")
                                .font(.title3)
                        }
                    }
                }
            }
            .sheet(isPresented: $showingProfile) {
                ProfileView(conversationStore: conversationStore)
            }
            .sheet(isPresented: $showRecordingSheet) {
                RecordingSheet(
                    recorder: recorder,
                    onSend: { transcript in
                        // CRITICAL: Stop recording FIRST (synchronous state change)
                        // This ensures isRecording is false before we dismiss
                        recorder.disableSilenceAutoStop = false

                        // Animate sheet dismissal for smooth transition
                        withAnimation(.easeOut(duration: 0.25)) {
                            showRecordingSheet = false
                        }

                        // Async operations AFTER UI state is updated
                        Task {
                            await recorder.stopRecording()
                            let _ = await conversationStore.sendMessage(transcript)
                        }
                    },
                    onCancel: {
                        recorder.disableSilenceAutoStop = false

                        withAnimation(.easeOut(duration: 0.25)) {
                            showRecordingSheet = false
                        }

                        Task {
                            await recorder.stopRecording()
                        }
                    },
                    hasSent: $recordingHasSent
                )
                .presentationDetents([.fraction(0.4), .fraction(0.55)])
                .presentationDragIndicator(.hidden)
                .interactiveDismissDisabled()
            }
            .task {
                await startupSequence()
            }
            .onChange(of: appState.shouldStartRecording) { _, newValue in
                if newValue {
                    startRecordingFromIntent()
                }
            }
            // NOTE: pendingTranscriptToSend watcher removed - RecordingSheet handles all sending
            // This prevents double-send when both RecordingSheet and AudioRecorder try to send
            .onChange(of: conversationStore.messages) { oldMessages, newMessages in
                // Auto-play TTS for new assistant messages
                if autoReadEnabled,
                   let lastNew = newMessages.last,
                   lastNew.isAssistant,
                   !oldMessages.contains(where: { $0.id == lastNew.id }) {
                    Task {
                        await playAudioForMessage(lastNew)
                    }
                }
            }
            .onChange(of: scenePhase) { _, newPhase in
                // Stop polling when app goes to background
                if newPhase == .background {
                    conversationStore.stopPolling()
                    audioPlayerManager.stop()
                    currentPlayingMessageId = nil
                } else if newPhase == .active {
                    // Reload all messages fresh to avoid showing stale cached data.
                    // Clear messages first so iOS snapshot doesn't flash old content.
                    conversationStore.clearForRefresh()
                    Task {
                        await conversationStore.loadMessages()
                        conversationStore.startPolling()
                    }
                }
            }
        }
    }

    // MARK: - Messages Area

    @ViewBuilder
    private var messagesArea: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 12) {
                    if conversationStore.messages.isEmpty && !conversationStore.isLoading && !showRecordingSheet {
                        emptyState
                    } else {
                        ForEach(Array(conversationStore.messages.enumerated()), id: \.element.id) { index, message in
                            let isLastInUserSequence: Bool = {
                                guard message.isUser else { return false }
                                let nextIndex = index + 1
                                if nextIndex >= conversationStore.messages.count {
                                    return true  // Last message overall
                                }
                                return !conversationStore.messages[nextIndex].isUser  // Next is assistant
                            }()

                            MessageBubble(
                                message: message,
                                isPlaying: currentPlayingMessageId == message.id,
                                isLastInUserSequence: isLastInUserSequence,
                                onPlayAudio: {
                                    Task { await playAudioForMessage(message) }
                                }
                            )
                            .id(message.id)
                        }

                        // Recording placeholder (pulsing coral indicator)
                        if showRecordingSheet {
                            RecordingPlaceholder()
                                .id("recording-placeholder")
                        }

                        // Thinking indicator
                        if conversationStore.isLoading {
                            ThinkingIndicator()
                        }
                    }
                }
                .padding()
            }
            .onChange(of: conversationStore.messages.count) { _, _ in
                // Auto-scroll to bottom
                if let lastId = conversationStore.messages.last?.id {
                    withAnimation {
                        proxy.scrollTo(lastId, anchor: .bottom)
                    }
                }
            }
        }
    }

    // MARK: - Error Banner

    @ViewBuilder
    private func errorBanner(_ message: String) -> some View {
        HStack {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.white)
            Text(message)
                .font(.subheadline)
                .foregroundColor(.white)
                .lineLimit(2)
            Spacer()
            Button(action: { conversationStore.error = nil }) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.white.opacity(0.8))
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
        .background(Color.red.opacity(0.9))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Error: \(message)")
        .accessibilityHint("Tap X to dismiss")
    }

    // MARK: - Empty State

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 16) {
            Spacer()
            Text("Tap the mic below to get started")
                .font(.title3)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.top, 100)
    }

    // MARK: - Debug Log View

    @ViewBuilder
    private var debugLogView: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("Debug Logs")
                    .font(.caption.bold())
                Spacer()
                Button("Clear") {
                    debugLogs.removeAll()
                }
                .font(.caption)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(debugLogs.indices, id: \.self) { index in
                        Text(debugLogs[index])
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(.primary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(height: 150)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color(.systemGray6))
    }

    private func addDebugLog(_ message: String) {
        let timestamp = Date().formatted(date: .omitted, time: .standard)
        debugLogs.append("[\(timestamp)] \(message)")
        // Keep only last 50 logs
        if debugLogs.count > 50 {
            debugLogs.removeFirst()
        }
    }

    // MARK: - Status Area

    @ViewBuilder
    private var statusArea: some View {
        // Completely hidden - RecordingSheet handles all recording UI
        // Previously showed transcript when recording without sheet, but this
        // caused duplicate transcripts and confused UI state
        EmptyView()
    }

    // MARK: - Input Bar

    @ViewBuilder
    private var inputBar: some View {
        VStack(spacing: 0) {
            Divider()

            HStack(spacing: 12) {
                // NOTE: When showRecordingSheet is true, RecordingSheet handles all recording UI
                // The input bar should show idle state (mic button) during sheet recording
                if recorder.isRecording && !showRecordingSheet {
                    // Legacy recording state (non-sheet): Cancel + Waveform + Stop
                    // This path is rarely used now - sheet is the primary recording UI
                    Button(action: cancelRecording) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.title2)
                            .foregroundColor(.secondary)
                    }

                    // Waveform / pulse animation
                    RecordingIndicator(audioLevel: recorder.audioLevel)
                        .frame(maxWidth: .infinity)

                    Button(action: stopRecording) {
                        Image(systemName: "stop.circle.fill")
                            .font(.title)
                            .foregroundColor(.red)
                    }
                } else if isKeyboardMode {
                    // Keyboard mode: Text field + Send
                    TextField("Message Sven...", text: $textInput)
                        .textFieldStyle(.roundedBorder)
                        .focused($isTextFieldFocused)
                        .disabled(isSendingText)
                        .onAppear { isTextFieldFocused = true }
                        .onSubmit { sendTextMessage() }
                        .accessibilityLabel("Message input")

                    if !textInput.isEmpty {
                        Button(action: sendTextMessage) {
                            if isSendingText {
                                ProgressView()
                                    .frame(width: 28, height: 28)
                            } else {
                                Image(systemName: "arrow.up.circle.fill")
                                    .font(.title)
                                    .foregroundColor(.blue)
                            }
                        }
                        .disabled(isSendingText)
                        .accessibilityLabel("Send message")
                    } else {
                        Button(action: {
                            isKeyboardMode = false
                            isTextFieldFocused = false
                        }) {
                            Image(systemName: "mic.fill")
                                .font(.title2)
                                .foregroundColor(.blue)
                        }
                        .accessibilityLabel("Switch to voice input")
                    }
                } else {
                    // Idle state: Keyboard toggle + Placeholder + Mic
                    Button(action: { isKeyboardMode = true }) {
                        Image(systemName: "keyboard")
                            .font(.title3)
                            .foregroundColor(.secondary)
                    }

                    Text("Message Sven...")
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    Button(action: openRecordingSheet) {
                        Image(systemName: "mic.fill")
                            .font(.title)
                            .foregroundColor(.blue)
                    }
                    .disabled(!appState.permissionsGranted)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 12)
            .background(Color(.systemBackground))
        }
    }

    // MARK: - Actions

    private func startupSequence() async {
        // Request permissions first
        let granted = await recorder.requestPermissions()
        appState.setPermissionsGranted(granted)

        if granted {
            // Initialize transcriber before attempting to record
            recorder.initializeTranscriber()

            // Wait a moment for transcriber to initialize
            try? await Task.sleep(nanoseconds: 200_000_000)  // 200ms

            // Now handle intent-triggered recording if requested
            if appState.shouldStartRecording && !recorder.isRecording && recorder.isTranscriberReady {
                startRecordingFromIntent()
            }
        }

        // Load messages and start polling regardless of permissions
        await conversationStore.loadMessages()
        conversationStore.startPolling()
    }

    private func startRecordingFromIntent() {
        guard appState.shouldStartRecording,
              appState.permissionsGranted,
              !recorder.isRecording else { return }

        appState.shouldStartRecording = false
        openRecordingSheet()
    }

    private func openRecordingSheet() {
        let generator = UIImpactFeedbackGenerator(style: .medium)
        generator.impactOccurred()
        // Reset shared state for new recording session
        recordingHasSent = false
        // Disable AudioRecorder's silence auto-stop - RecordingSheet handles it
        recorder.disableSilenceAutoStop = true
        recorder.startRecording()
        showRecordingSheet = true
    }

    private func startRecording() {
        let generator = UIImpactFeedbackGenerator(style: .light)
        generator.impactOccurred()
        recorder.startRecording()
    }

    private func stopRecording() {
        let generator = UIImpactFeedbackGenerator(style: .medium)
        generator.impactOccurred()

        addDebugLog("stopRecording called")

        Task {
            addDebugLog("calling recorder.stopRecording()")
            // Wait for recording to stop and finalize transcript
            await recorder.stopRecording()

            // Send the transcript
            let transcript = recorder.transcript
            let partial = recorder.partialTranscript
            addDebugLog("transcript='\(transcript)'")
            addDebugLog("partial='\(partial)'")

            if !transcript.isEmpty {
                addDebugLog("sending message...")
                let success = await conversationStore.sendMessage(transcript)
                addDebugLog("sendMessage returned \(success)")
            } else {
                addDebugLog("transcript EMPTY, not sending!")
            }
        }
    }

    private func cancelRecording() {
        let generator = UINotificationFeedbackGenerator()
        generator.notificationOccurred(.error)
        Task {
            await recorder.stopRecording()
            // Don't send - just discard
        }
    }

    private func sendTextMessage() {
        let message = textInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !message.isEmpty, !isSendingText else { return }

        let messageToSend = message
        textInput = ""
        isKeyboardMode = false
        isTextFieldFocused = false
        isSendingText = true

        Task {
            await conversationStore.sendMessage(messageToSend)
            isSendingText = false
        }
    }

    private func restartSession() {
        Task {
            await conversationStore.restartSession()
        }
    }

    private func playAudioForMessage(_ message: ChatMessage) async {
        print("[ContentView] playAudioForMessage called for message: \(message.id)")
        guard let audioPath = message.audioUrl else {
            print("[ContentView] No audioUrl for message")
            return
        }
        print("[ContentView] audioUrl: \(audioPath)")

        // Stop current playback
        audioPlayerManager.stop()
        currentPlayingMessageId = nil

        print("[ContentView] Downloading audio...")
        if let audioURL = await conversationStore.downloadAudio(for: message) {
            print("[ContentView] Downloaded to: \(audioURL)")
            currentPlayingMessageId = message.id

            audioPlayerManager.play(url: audioURL) { [self] in
                // Completion callback
                print("[ContentView] Audio playback finished")
                Task { @MainActor in
                    currentPlayingMessageId = nil
                }
            }
        } else {
            print("[ContentView] Failed to download audio")
            currentPlayingMessageId = nil
        }
    }
}

// MARK: - Message Bubble

struct MessageBubble: View {
    let message: ChatMessage
    let isPlaying: Bool
    let isLastInUserSequence: Bool  // Only show "Delivered" on last user message in sequence
    let onPlayAudio: () -> Void

    @State private var isExpanded = false

    private let maxCollapsedLength = 840

    var body: some View {
        HStack {
            if message.isUser { Spacer(minLength: 60) }

            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 4) {
                // Message content
                let shouldTruncate = message.content.count > maxCollapsedLength && !isExpanded

                Text(shouldTruncate
                     ? String(message.content.prefix(maxCollapsedLength)) + "..."
                     : message.content)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(message.isUser ? Color.blue.opacity(message.isPending ? 0.7 : 1.0) : Color(.systemGray5))
                    .foregroundColor(message.isUser ? .white : .primary)
                    .cornerRadius(16)

                // Show more / less
                if message.content.count > maxCollapsedLength {
                    Button(action: { isExpanded.toggle() }) {
                        Text(isExpanded ? "Show less" : "Show more")
                            .font(.caption)
                            .foregroundColor(.blue)
                    }
                }

                // iMessage-style status for user messages (only show on last in sequence)
                if message.isUser && (message.isPending || isLastInUserSequence) {
                    Text(message.isPending ? "Sending..." : "Delivered")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }

                // Audio play button (assistant only)
                if message.isAssistant && message.audioUrl != nil {
                    Button(action: onPlayAudio) {
                        HStack(spacing: 4) {
                            Image(systemName: isPlaying ? "speaker.wave.2.fill" : "play.circle.fill")
                            Text(isPlaying ? "Playing..." : "Play")
                                .font(.caption)
                        }
                        .foregroundColor(.blue)
                    }
                }
            }

            if message.isAssistant { Spacer(minLength: 60) }
        }
    }
}

// MARK: - Thinking Indicator

struct ThinkingIndicator: View {
    @State private var dotCount = 0
    @State private var timer: Timer?

    var body: some View {
        HStack {
            HStack(spacing: 4) {
                Text("Thinking")
                    .foregroundColor(.secondary)
                ForEach(0..<3) { i in
                    Circle()
                        .fill(Color.secondary)
                        .frame(width: 6, height: 6)
                        .opacity(dotCount > i ? 1 : 0.3)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color(.systemGray5))
            .cornerRadius(16)
            .accessibilityLabel("Thinking")
            .accessibilityHint("Assistant is processing your message")

            Spacer()
        }
        .onAppear {
            timer = Timer.scheduledTimer(withTimeInterval: 0.4, repeats: true) { _ in
                dotCount = (dotCount + 1) % 4
            }
        }
        .onDisappear {
            timer?.invalidate()
            timer = nil
        }
    }
}

// MARK: - Recording Indicator

struct RecordingIndicator: View {
    let audioLevel: Float

    private var normalizedLevel: CGFloat {
        CGFloat(max(0, min(1, (audioLevel + 60) / 60)))
    }

    var body: some View {
        HStack(spacing: 2) {
            ForEach(0..<20, id: \.self) { i in
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.red.opacity(0.7))
                    .frame(width: 3, height: 8 + normalizedLevel * 16 * CGFloat.random(in: 0.5...1.5))
                    .animation(.easeInOut(duration: 0.1), value: audioLevel)
            }
        }
        .accessibilityLabel("Audio level indicator")
        .accessibilityValue("Recording in progress")
    }
}

// MARK: - Profile View

struct ProfileView: View {
    @ObservedObject var conversationStore: ConversationStore
    @Environment(\.dismiss) private var dismiss
    @State private var serverURL: String = SvenAPIClient.serverURL
    @State private var showingConnectionTest = false
    @State private var connectionTestResult: String?
    @State private var isTestingConnection = false

    var body: some View {
        NavigationStack {
            List {
                Section(header: Text("Server Configuration")) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Server URL")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        TextField("e.g. 100.91.58.120:9091", text: $serverURL)
                            .textFieldStyle(.roundedBorder)
                            .autocapitalization(.none)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                            .onChange(of: serverURL) { _, newValue in
                                SvenAPIClient.serverURL = newValue
                            }
                    }
                    .padding(.vertical, 4)

                    Button(action: testConnection) {
                        HStack {
                            if isTestingConnection {
                                ProgressView()
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "antenna.radiowaves.left.and.right")
                            }
                            Text("Test Connection")
                        }
                    }
                    .disabled(isTestingConnection)

                    if let result = connectionTestResult {
                        Text(result)
                            .font(.caption)
                            .foregroundColor(result.contains("✓") ? .green : .red)
                    }
                }

                Section {
                    Button(role: .destructive) {
                        Task {
                            await conversationStore.clearMessages()
                            dismiss()
                        }
                    } label: {
                        Label("Clear Conversation", systemImage: "trash")
                    }
                }

                Section {
                    HStack {
                        Text("Messages")
                        Spacer()
                        Text("\(conversationStore.messages.count)")
                            .foregroundColor(.secondary)
                    }
                }

                Section {
                    Text("About Sven")
                        .foregroundColor(.secondary)
                    Text("Voice assistant powered by Claude")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private func testConnection() {
        isTestingConnection = true
        connectionTestResult = nil

        Task {
            do {
                var urlString = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
                if !urlString.hasPrefix("http://") && !urlString.hasPrefix("https://") {
                    urlString = "http://" + urlString
                }
                if urlString.hasSuffix("/") {
                    urlString = String(urlString.dropLast())
                }

                guard let url = URL(string: "\(urlString)/health") else {
                    await MainActor.run {
                        connectionTestResult = "✗ Invalid URL"
                        isTestingConnection = false
                    }
                    return
                }

                var request = URLRequest(url: url)
                request.timeoutInterval = 5

                let (_, response) = try await URLSession.shared.data(for: request)

                await MainActor.run {
                    if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                        connectionTestResult = "✓ Connected successfully!"
                    } else {
                        connectionTestResult = "✗ Server returned error"
                    }
                    isTestingConnection = false
                }
            } catch {
                await MainActor.run {
                    connectionTestResult = "✗ \(error.localizedDescription)"
                    isTestingConnection = false
                }
            }
        }
    }
}

// MARK: - Audio Player Manager

class AudioPlayerManager: NSObject, ObservableObject, AVAudioPlayerDelegate {
    @Published var isPlaying = false
    private var audioPlayer: AVAudioPlayer?
    private var onFinish: (() -> Void)?

    func play(url: URL, completion: @escaping () -> Void) {
        print("[AudioPlayerManager] play() called with URL: \(url)")

        // Verify file exists
        guard FileManager.default.fileExists(atPath: url.path) else {
            print("[AudioPlayerManager] ERROR: File does not exist at \(url.path)")
            completion()
            return
        }

        stop()  // Stop any existing playback

        do {
            // Configure audio session for playback - like Spotify, play through speaker even on silent
            print("[AudioPlayerManager] Setting audio session...")
            let session = AVAudioSession.sharedInstance()
            // .playback ignores silent switch; .duckOthers lowers other audio
            try session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
            try session.setActive(true, options: .notifyOthersOnDeactivation)

            print("[AudioPlayerManager] Creating AVAudioPlayer...")
            audioPlayer = try AVAudioPlayer(contentsOf: url)
            audioPlayer?.delegate = self
            audioPlayer?.volume = 1.0
            audioPlayer?.prepareToPlay()
            onFinish = completion

            print("[AudioPlayerManager] Calling play()... duration=\(audioPlayer?.duration ?? 0)")
            if audioPlayer?.play() == true {
                isPlaying = true
                print("[AudioPlayerManager] Playback started successfully")
            } else {
                print("[AudioPlayerManager] play() returned false")
                completion()
            }
        } catch {
            print("[AudioPlayerManager] Failed to play - \(error)")
            completion()
        }
    }

    func stop() {
        audioPlayer?.stop()
        audioPlayer = nil
        isPlaying = false
        deactivateAudioSession()
    }

    private func deactivateAudioSession() {
        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        } catch {
            print("AudioPlayerManager: Failed to deactivate session - \(error)")
        }
    }

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        DispatchQueue.main.async { [weak self] in
            self?.isPlaying = false
            self?.deactivateAudioSession()
            self?.onFinish?()
            self?.onFinish = nil
        }
    }

    func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        DispatchQueue.main.async { [weak self] in
            self?.isPlaying = false
            self?.deactivateAudioSession()
            self?.onFinish?()
            self?.onFinish = nil
        }
    }
}

// MARK: - Preview

#Preview {
    ContentView()
}
