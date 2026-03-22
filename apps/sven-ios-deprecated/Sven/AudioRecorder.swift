import Foundation
import AVFoundation
import UIKit
import Speech

struct Recording: Identifiable, Codable {
    let id: UUID
    let date: Date
    let fileName: String
    var transcript: String

    var audioURL: URL {
        let documentsPath = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return documentsPath.appendingPathComponent(fileName)
    }

    var formattedDate: String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }
}

@MainActor
class AudioRecorder: ObservableObject {
    @Published var isRecording = false
    @Published var transcript = ""
    @Published var partialTranscript = ""
    @Published var audioLevel: Float = -160
    @Published var savedRecordings: [Recording] = []
    @Published var errorMessage: String?
    @Published var recordingTimeRemaining: TimeInterval = 600
    @Published var isSendingToAPI = false
    @Published var apiSendSuccess: Bool?
    @Published var isTranscriberReady = false
    @Published var pendingTranscriptToSend: String?  // Set when auto-stop happens with content

    /// When true, AudioRecorder will NOT auto-stop on silence - the UI handles it
    var disableSilenceAutoStop = false

    // Apple SpeechAnalyzer (iOS 26+)
    private var speechAnalyzer: SpeechAnalyzer?
    private var speechTranscriber: SpeechTranscriber?
    private var inputBuilder: AsyncStream<AnalyzerInput>.Continuation?
    private var analyzerFormat: AVAudioFormat?
    private var audioConverter: AVAudioConverter?
    private var recognizerTask: Task<Void, Never>?
    private var appleTranscriberReady = false

    // Audio recording
    private var audioEngine: AVAudioEngine?
    private var audioFile: AVAudioFile?

    private let silenceQueue = DispatchQueue(label: "com.sven.silenceDetection")
    private var _lastSpeechTime: Date?
    private var lastSpeechTime: Date? {
        get { silenceQueue.sync { _lastSpeechTime } }
        set { silenceQueue.sync { _lastSpeechTime = newValue } }
    }

    private var silenceTimer: Timer?
    private var recordingStartTime: Date?
    private var isSilenceTriggered = false  // Prevent multiple silence triggers

    private let silenceThreshold: TimeInterval = 4.0  // Match RecordingSheet
    private let audioThreshold: Float = -50.0
    private let maxRecordingDuration: TimeInterval = 600.0  // 10 minutes
    private let minRecordingDuration: TimeInterval = 1.0

    private var currentRecordingURL: URL?

    init() {
        loadRecordings()
    }

    /// Initialize Apple SpeechAnalyzer - call this in viewDidAppear
    func initializeTranscriber() {
        Task {
            await initializeAppleSpeechAnalyzer()
        }
    }

    // MARK: - Apple SpeechAnalyzer Initialization (iOS 26+)

    private func initializeAppleSpeechAnalyzer() async {
        print("[AudioRecorder] Initializing Apple SpeechAnalyzer...")

        // Reset state
        appleTranscriberReady = false
        isTranscriberReady = false

        do {
            // Request speech recognition permission
            let status = await withCheckedContinuation { continuation in
                SFSpeechRecognizer.requestAuthorization { status in
                    continuation.resume(returning: status)
                }
            }

            guard status == .authorized else {
                print("[AudioRecorder] Speech recognition not authorized: \(status)")
                errorMessage = "Speech recognition not authorized"
                return
            }

            // Create transcriber for live transcription with volatile results
            let transcriber = SpeechTranscriber(
                locale: Locale(identifier: "en-US"),
                transcriptionOptions: [],
                reportingOptions: [.volatileResults],
                attributeOptions: []
            )
            speechTranscriber = transcriber

            // Create analyzer with transcriber module
            let analyzer = SpeechAnalyzer(modules: [transcriber])
            speechAnalyzer = analyzer

            // Get best available audio format
            analyzerFormat = await SpeechAnalyzer.bestAvailableAudioFormat(
                compatibleWith: [transcriber]
            )

            guard analyzerFormat != nil else {
                print("[AudioRecorder] Failed to get audio format for SpeechAnalyzer")
                errorMessage = "Failed to initialize audio format"
                return
            }

            appleTranscriberReady = true
            isTranscriberReady = true
            print("[AudioRecorder] Apple SpeechAnalyzer ready")

        } catch {
            print("[AudioRecorder] Failed to initialize Apple SpeechAnalyzer: \(error)")
            errorMessage = "Failed to initialize speech recognition: \(error.localizedDescription)"
            appleTranscriberReady = false
            isTranscriberReady = false
        }
    }

    // MARK: - Post-processing for "Sven" Recognition

    /// Common misrecognitions of "Sven" and their corrections
    private static let svenCorrections: [(pattern: String, replacement: String)] = [
        // Case-insensitive word boundary matches
        ("\\bspin\\b", "Sven"),
        ("\\bsin\\b", "Sven"),
        ("\\bFinn\\b", "Sven"),
        ("\\bfinn\\b", "Sven"),
        ("\\bSpan\\b", "Sven"),
        ("\\bspan\\b", "Sven"),
        ("\\bsven\\b", "Sven"),  // Capitalize properly
        ("\\bSven's\\b", "Sven's"),  // Keep possessive
    ]

    /// Apply post-processing to fix common "Sven" misrecognitions
    private func correctSvenMisrecognitions(_ text: String) -> String {
        var result = text
        for (pattern, replacement) in Self.svenCorrections {
            if let regex = try? NSRegularExpression(pattern: pattern, options: []) {
                result = regex.stringByReplacingMatches(
                    in: result,
                    options: [],
                    range: NSRange(result.startIndex..., in: result),
                    withTemplate: replacement
                )
            }
        }
        return result
    }

    // MARK: - Apple SpeechAnalyzer Audio Processing

    private func processAudioForApple(_ buffer: AVAudioPCMBuffer) {
        guard let builder = inputBuilder,
              let targetFormat = analyzerFormat else { return }

        // Convert to analyzer format if needed
        if let converter = getAudioConverter(from: buffer.format, to: targetFormat) {
            let frameCapacity = AVAudioFrameCount(
                Double(buffer.frameLength) * targetFormat.sampleRate / buffer.format.sampleRate
            )
            guard let convertedBuffer = AVAudioPCMBuffer(
                pcmFormat: targetFormat,
                frameCapacity: frameCapacity
            ) else { return }

            var error: NSError?
            let inputBlock: AVAudioConverterInputBlock = { _, outStatus in
                outStatus.pointee = .haveData
                return buffer
            }

            converter.convert(to: convertedBuffer, error: &error, withInputFrom: inputBlock)

            if error == nil {
                builder.yield(AnalyzerInput(buffer: convertedBuffer))
            }
        } else {
            // Format matches, use directly
            builder.yield(AnalyzerInput(buffer: buffer))
        }
    }

    private func getAudioConverter(from sourceFormat: AVAudioFormat, to targetFormat: AVAudioFormat) -> AVAudioConverter? {
        if sourceFormat.sampleRate == targetFormat.sampleRate &&
           sourceFormat.channelCount == targetFormat.channelCount {
            return nil
        }

        if audioConverter == nil {
            audioConverter = AVAudioConverter(from: sourceFormat, to: targetFormat)
        }
        return audioConverter
    }

    // MARK: - Recording Control

    func requestPermissions() async -> Bool {
        let micStatus = await withCheckedContinuation { continuation in
            AVAudioApplication.requestRecordPermission { granted in
                continuation.resume(returning: granted)
            }
        }

        guard micStatus else {
            errorMessage = "Microphone access denied"
            return false
        }

        return true
    }

    func startRecording() {
        guard !isRecording else { return }
        guard appleTranscriberReady else {
            errorMessage = "Speech recognition not ready. Please wait..."
            // Try to reinitialize
            Task {
                await initializeAppleSpeechAnalyzer()
            }
            return
        }

        let startTime = CFAbsoluteTimeGetCurrent()
        print("[AudioRecorder] startRecording() called")

        errorMessage = nil
        partialTranscript = ""
        transcript = ""
        recordingTimeRemaining = maxRecordingDuration
        isSilenceTriggered = false  // Reset for new recording

        do {
            let audioSession = AVAudioSession.sharedInstance()
            try audioSession.setCategory(.playAndRecord, mode: .measurement, options: [.defaultToSpeaker])
            try audioSession.setActive(true)

            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "yyyy-MM-dd_HH-mm-ss"
            let filename = "sven_\(dateFormatter.string(from: Date())).caf"
            let documentsPath = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            currentRecordingURL = documentsPath.appendingPathComponent(filename)

            audioEngine = AVAudioEngine()
            guard let audioEngine = audioEngine, let recordingURL = currentRecordingURL else { return }

            let inputNode = audioEngine.inputNode
            let recordingFormat = inputNode.outputFormat(forBus: 0)

            audioFile = try AVAudioFile(forWriting: recordingURL, settings: recordingFormat.settings)

            // Install tap for level monitoring, file recording, and Apple transcriber
            inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { [weak self] buffer, _ in
                guard let self = self else { return }

                // Write to file
                do {
                    try self.audioFile?.write(from: buffer)
                } catch {
                    print("Error writing audio buffer: \(error)")
                }

                // Update audio level
                let level = self.calculateAudioLevel(buffer: buffer)
                Task { @MainActor in
                    self.audioLevel = level
                }

                if level > self.audioThreshold {
                    self.lastSpeechTime = Date()
                }

                // Feed to Apple SpeechAnalyzer
                Task { @MainActor in
                    self.processAudioForApple(buffer)
                }
            }

            try audioEngine.start()

            // Start Apple SpeechAnalyzer
            Task {
                await startAppleSpeechAnalyzer()
            }

            isRecording = true
            recordingStartTime = Date()
            lastSpeechTime = Date()

            let engineStartTime = CFAbsoluteTimeGetCurrent()
            print("[AudioRecorder] Recording started in \((engineStartTime - startTime) * 1000)ms")

            setupInterruptionObservers()

            silenceTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    self?.checkSilenceAndDuration()
                }
            }

        } catch {
            print("Failed to start recording: \(error)")
            errorMessage = "Failed to start recording: \(error.localizedDescription)"
        }
    }

    private func startAppleSpeechAnalyzer() async {
        guard let analyzer = speechAnalyzer,
              let transcriber = speechTranscriber,
              appleTranscriberReady else {
            print("[AudioRecorder] Apple SpeechAnalyzer not ready")
            return
        }

        do {
            // Create async stream for audio input
            let (inputSequence, builder) = AsyncStream<AnalyzerInput>.makeStream()
            inputBuilder = builder

            // Start the analyzer
            try await analyzer.start(inputSequence: inputSequence)

            // Start listening for results
            recognizerTask = Task {
                var accumulatedText = ""
                do {
                    for try await result in transcriber.results {
                        let text = String(result.text.characters)
                        if result.isFinal {
                            accumulatedText += text + " "
                            let corrected = correctSvenMisrecognitions(accumulatedText.trimmingCharacters(in: .whitespaces))
                            transcript = corrected
                            partialTranscript = corrected
                        } else {
                            // Show volatile (interim) results too for real-time feedback
                            let corrected = correctSvenMisrecognitions(accumulatedText + text)
                            partialTranscript = corrected
                        }
                    }
                } catch {
                    print("[AudioRecorder] Apple result stream error: \(error)")
                }
            }

            print("[AudioRecorder] Apple SpeechAnalyzer started")
        } catch {
            print("[AudioRecorder] Failed to start Apple SpeechAnalyzer: \(error)")
        }
    }

    func stopRecording() async {
        guard isRecording else { return }

        silenceTimer?.invalidate()
        silenceTimer = nil

        audioEngine?.stop()
        audioEngine?.inputNode.removeTap(onBus: 0)
        audioEngine = nil
        audioFile = nil

        // Stop Apple SpeechAnalyzer and wait for final transcript
        await stopAppleSpeechAnalyzer()

        print("[AudioRecorder] After stopAppleSpeechAnalyzer: transcript='\(transcript)', partialTranscript='\(partialTranscript)'")

        // CRITICAL: If transcript is empty but partialTranscript has content,
        // use partialTranscript (final results may not have arrived yet)
        if transcript.isEmpty && !partialTranscript.isEmpty {
            transcript = partialTranscript
            print("[AudioRecorder] Using partialTranscript as final: \(transcript)")
        }

        print("[AudioRecorder] Final transcript to return: '\(transcript)'")

        isRecording = false
        removeInterruptionObservers()

        // Deactivate the recording audio session so playback can work
        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            print("[AudioRecorder] Audio session deactivated")
        } catch {
            print("[AudioRecorder] Failed to deactivate audio session: \(error)")
        }

        if let recordingURL = currentRecordingURL {
            let recordingDuration = recordingStartTime.map { Date().timeIntervalSince($0) } ?? 0

            if recordingDuration >= minRecordingDuration {
                let fileName = recordingURL.lastPathComponent
                let finalTranscript = transcript
                let recording = Recording(
                    id: UUID(),
                    date: Date(),
                    fileName: fileName,
                    transcript: finalTranscript
                )
                savedRecordings.insert(recording, at: 0)
                saveRecordings()

                // Note: API send is now handled by ConversationStore in ContentView
                // The transcript is available via self.transcript after stopRecording()
            } else {
                try? FileManager.default.removeItem(at: recordingURL)
            }
        }

        currentRecordingURL = nil
        recordingStartTime = nil
    }

    private func stopAppleSpeechAnalyzer() async {
        print("[AudioRecorder] stopAppleSpeechAnalyzer: START, transcript='\(transcript)', partial='\(partialTranscript)'")

        // STEP 1: Capture what we have BEFORE any cleanup
        // This is our fallback if anything goes wrong
        let capturedTranscript = transcript
        let capturedPartial = partialTranscript

        // STEP 2: Stop sending audio to the analyzer
        inputBuilder?.finish()
        inputBuilder = nil

        // STEP 3: Finalize the analyzer - this should flush all pending results
        do {
            try await speechAnalyzer?.finalizeAndFinishThroughEndOfInput()
            print("[AudioRecorder] finalizeAndFinishThroughEndOfInput completed")
        } catch {
            print("[AudioRecorder] Error stopping Apple SpeechAnalyzer: \(error)")
        }

        // STEP 4: Wait for the recognizerTask to complete naturally
        // After finalize, the results stream should close and the task will exit
        if let task = recognizerTask {
            print("[AudioRecorder] Waiting for recognizerTask to complete...")
            // Wait with timeout - the task should complete quickly after finalize
            let deadline = Date().addingTimeInterval(1.0)  // 1 second timeout
            while !task.isCancelled && Date() < deadline {
                // Give the task a chance to process any remaining results
                try? await Task.sleep(nanoseconds: 50_000_000)  // 50ms
                // Check if task completed by seeing if we're past the async iteration
            }
            // Force cancel if still running
            task.cancel()
        }
        recognizerTask = nil

        print("[AudioRecorder] After waiting: transcript='\(transcript)', partial='\(partialTranscript)'")

        // STEP 5: Use the best available transcript
        // Priority: transcript > partialTranscript > captured values
        if transcript.isEmpty {
            if !partialTranscript.isEmpty {
                transcript = partialTranscript
                print("[AudioRecorder] Using partialTranscript: \(transcript)")
            } else if !capturedTranscript.isEmpty {
                transcript = capturedTranscript
                print("[AudioRecorder] Restored captured transcript: \(transcript)")
            } else if !capturedPartial.isEmpty {
                transcript = capturedPartial
                print("[AudioRecorder] Restored captured partial: \(transcript)")
            }
        }

        print("[AudioRecorder] FINAL transcript to use: '\(transcript)'")

        // STEP 6: Clean up - SpeechAnalyzer cannot be reused after finalize
        audioConverter = nil
        speechAnalyzer = nil
        speechTranscriber = nil
        appleTranscriberReady = false
        isTranscriberReady = false

        // STEP 7: Recreate for next recording (in background, don't block)
        Task {
            await initializeAppleSpeechAnalyzer()
        }
    }

    func deleteRecording(_ recording: Recording) {
        do {
            try FileManager.default.removeItem(at: recording.audioURL)
        } catch {
            print("Failed to delete audio file: \(error)")
        }

        savedRecordings.removeAll { $0.id == recording.id }
        saveRecordings()
    }

    private func calculateAudioLevel(buffer: AVAudioPCMBuffer) -> Float {
        guard let channelData = buffer.floatChannelData?[0] else { return -160 }
        let frameLength = Int(buffer.frameLength)

        guard frameLength > 0 else { return -160 }

        var sum: Float = 0
        for i in 0..<frameLength {
            let sample = channelData[i]
            sum += sample * sample
        }

        let rms = sqrt(sum / Float(frameLength))
        guard rms > 0 else { return -160 }

        let db = 20 * log10(rms)
        return max(-160, min(0, db))
    }

    private func checkSilenceAndDuration() {
        guard isRecording, !isSilenceTriggered, let startTime = recordingStartTime else { return }

        let elapsed = Date().timeIntervalSince(startTime)
        recordingTimeRemaining = max(0, maxRecordingDuration - elapsed)

        if elapsed >= maxRecordingDuration {
            // CRITICAL: Set flag FIRST to prevent multiple triggers
            isSilenceTriggered = true

            // Capture transcript BEFORE any async work
            let transcriptToSend = transcript.isEmpty ? partialTranscript : transcript
            print("[AudioRecorder] Max duration reached, captured: '\(transcriptToSend)'")

            // Set pendingTranscriptToSend BEFORE stopping (so UI can respond)
            if !transcriptToSend.isEmpty {
                pendingTranscriptToSend = transcriptToSend
            }

            Task {
                await stopRecording()
            }
            return
        }

        // Only do silence-based auto-stop if NOT managed by RecordingSheet
        // RecordingSheet has its own silence detection that triggers auto-send
        if !disableSilenceAutoStop, let lastSpeech = lastSpeechTime {
            let silenceDuration = Date().timeIntervalSince(lastSpeech)
            // Check BOTH transcript and partialTranscript - partial may have content before final arrives
            let hasContent = !transcript.isEmpty || !partialTranscript.isEmpty

            if silenceDuration >= silenceThreshold && hasContent && elapsed >= minRecordingDuration {
                // CRITICAL: Set flag FIRST to prevent multiple triggers from timer
                isSilenceTriggered = true

                // Capture transcript BEFORE any async work - this is the REAL value
                let transcriptToSend = transcript.isEmpty ? partialTranscript : transcript
                print("[AudioRecorder] Silence detected, captured: '\(transcriptToSend)'")

                // Set pendingTranscriptToSend BEFORE stopping (so UI picks it up reliably)
                if !transcriptToSend.isEmpty {
                    pendingTranscriptToSend = transcriptToSend
                    print("[AudioRecorder] pendingTranscriptToSend = '\(transcriptToSend)'")
                }

                // Now stop recording (this may clear transcript, but we already captured it)
                Task {
                    await stopRecording()
                }
            }
        }
    }

    private func setupInterruptionObservers() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleInterruption),
            name: AVAudioSession.interruptionNotification,
            object: nil
        )

        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleAppBackground),
            name: UIApplication.willResignActiveNotification,
            object: nil
        )
    }

    private func removeInterruptionObservers() {
        NotificationCenter.default.removeObserver(self, name: AVAudioSession.interruptionNotification, object: nil)
        NotificationCenter.default.removeObserver(self, name: UIApplication.willResignActiveNotification, object: nil)
    }

    @objc private func handleInterruption(_ notification: Notification) {
        Task { @MainActor in
            if self.isRecording {
                await self.stopRecording()
            }
        }
    }

    @objc private func handleAppBackground() {
        Task { @MainActor in
            if self.isRecording {
                await self.stopRecording()
            }
        }
    }

    private func loadRecordings() {
        let documentsPath = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let recordingsFile = documentsPath.appendingPathComponent("recordings.json")

        guard FileManager.default.fileExists(atPath: recordingsFile.path) else { return }

        do {
            let data = try Data(contentsOf: recordingsFile)
            savedRecordings = try JSONDecoder().decode([Recording].self, from: data)
        } catch {
            print("Failed to load recordings: \(error)")
        }
    }

    private func saveRecordings() {
        let documentsPath = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let recordingsFile = documentsPath.appendingPathComponent("recordings.json")

        do {
            let data = try JSONEncoder().encode(savedRecordings)
            try data.write(to: recordingsFile)
        } catch {
            print("Failed to save recordings: \(error)")
        }
    }

    // Note: sendTranscriptToAPI removed - handled by ConversationStore in ContentView
}
