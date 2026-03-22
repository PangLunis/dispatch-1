import SwiftUI
import AVFoundation

// MARK: - Recording Sheet View
// Simple flow: auto-start → stop → review transcript → send/cancel

struct RecordingSheet: View {
    @ObservedObject var recorder: AudioRecorder
    let onSend: (String) -> Void
    let onCancel: () -> Void
    @Binding var hasSent: Bool  // Shared with parent to prevent state desync

    @State private var recordingDuration: TimeInterval = 0
    @State private var durationTimer: Timer?
    @State private var showCancelConfirmation = false
    @State private var isStopped = false  // True after user taps stop, before send/cancel
    @State private var frozenTranscript = ""  // Transcript captured at stop time

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    // Design tokens
    private let breathingDuration: TimeInterval = 1.2
    private let maxRecordingDuration: TimeInterval = 120  // 2 minutes
    private let warningTime: TimeInterval = 105  // 1:45
    private let cancelConfirmationThreshold: TimeInterval = 30

    var body: some View {
        VStack(spacing: 16) {
            // Drag indicator
            Capsule()
                .fill(Color(.systemGray4))
                .frame(width: 36, height: 5)
                .padding(.top, 8)

            // Mic/checkmark icon with waveform ring
            ZStack {
                // Waveform ring (only animates while recording)
                WaveformRing(audioLevel: isStopped ? -160 : recorder.audioLevel, isSilent: isStopped)
                    .frame(width: 72, height: 72)

                // Icon changes based on state
                Image(systemName: isStopped ? "checkmark" : "mic.fill")
                    .font(.system(size: 32))
                    .foregroundColor(isStopped ? .green : .blue)
                    .scaleEffect(isStopped ? 1.0 : 1.0)
            }
            .padding(.bottom, 8)

            // Duration timer / "Ready to send" label
            if isStopped {
                Text("Ready to send")
                    .font(.system(size: 18, weight: .medium))
                    .foregroundColor(.green)
            } else {
                Text(formatDuration(recordingDuration))
                    .font(.system(size: 18, weight: .medium, design: .monospaced))
                    .foregroundColor(durationColor)
            }

            // Transcription area
            ScrollView {
                TranscriptionView(text: isStopped ? frozenTranscript : recorder.partialTranscript)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(minHeight: 60, maxHeight: 120)
            .padding(.horizontal)

            Spacer(minLength: 8)

            // Action buttons - different based on state
            if isStopped {
                // After stop: Cancel / Send
                HStack(spacing: 40) {
                    Button(action: {
                        attemptCancel()
                    }) {
                        VStack(spacing: 4) {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 44))
                                .foregroundColor(.red.opacity(0.8))
                            Text("Discard")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .disabled(hasSent)
                    .accessibilityLabel("Discard recording")

                    Button(action: {
                        sendNow()
                    }) {
                        VStack(spacing: 4) {
                            Image(systemName: "arrow.up.circle.fill")
                                .font(.system(size: 44))
                                .foregroundColor(hasSent ? .gray : .blue)
                            Text("Send")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .disabled(hasSent || frozenTranscript.isEmpty)
                    .accessibilityLabel("Send message")
                }
            } else {
                // While recording: Cancel / Stop
                HStack(spacing: 40) {
                    Button(action: {
                        attemptCancel()
                    }) {
                        VStack(spacing: 4) {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 44))
                                .foregroundColor(.red.opacity(0.8))
                            Text("Cancel")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .accessibilityLabel("Cancel recording")

                    Button(action: {
                        stopRecording()
                    }) {
                        VStack(spacing: 4) {
                            Image(systemName: "stop.circle.fill")
                                .font(.system(size: 44))
                                .foregroundColor(.blue)
                            Text("Stop")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .accessibilityLabel("Stop recording")
                }
            }
        }
        .padding(.bottom, 30)
        .background(.ultraThinMaterial)
        .alert("Discard Recording?", isPresented: $showCancelConfirmation) {
            Button("Keep", role: .cancel) { }
            Button("Discard", role: .destructive) {
                let generator = UINotificationFeedbackGenerator()
                generator.notificationOccurred(.error)
                onCancel()
            }
        } message: {
            Text("You have \(formatDurationShort(recordingDuration)) of recording. Are you sure you want to discard it?")
        }
        .onAppear {
            startTimers()
            // Medium haptic on start
            let generator = UIImpactFeedbackGenerator(style: .medium)
            generator.impactOccurred()
        }
        .onDisappear {
            stopTimers()
        }
        .onChange(of: hasSent) { _, sent in
            if sent {
                stopTimers()
            }
        }
        .gesture(
            DragGesture()
                .onEnded { value in
                    // Swipe down to dismiss (only if not stopped with content)
                    if value.translation.height > 100 {
                        attemptCancel()
                    }
                }
        )
    }

    // MARK: - Timer Management

    private func startTimers() {
        durationTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [self] timer in
            guard !hasSent, !isStopped else {
                timer.invalidate()
                return
            }

            recordingDuration += 0.1

            // Auto-stop at max duration (but don't auto-send)
            if recordingDuration >= maxRecordingDuration {
                let generator = UINotificationFeedbackGenerator()
                generator.notificationOccurred(.warning)
                stopRecording()
            }
        }
    }

    private func stopTimers() {
        durationTimer?.invalidate()
        durationTimer = nil
    }

    // MARK: - Actions

    private func stopRecording() {
        guard !isStopped else { return }

        // Capture transcript before stopping
        frozenTranscript = recorder.transcript.isEmpty ? recorder.partialTranscript : recorder.transcript

        // Light haptic for stop
        let generator = UIImpactFeedbackGenerator(style: .light)
        generator.impactOccurred()

        isStopped = true
        stopTimers()

        // Stop the actual recorder
        Task {
            await recorder.stopRecording()
            // Update frozen transcript with final result if better
            if !recorder.transcript.isEmpty {
                frozenTranscript = recorder.transcript
            }
        }
    }

    private func sendNow() {
        guard !hasSent else { return }
        guard !frozenTranscript.isEmpty else { return }

        hasSent = true

        // Success haptic
        let generator = UINotificationFeedbackGenerator()
        generator.notificationOccurred(.success)

        onSend(frozenTranscript)
    }

    // MARK: - Helpers

    private var durationColor: Color {
        if recordingDuration >= maxRecordingDuration - 5 {
            return .red
        } else if recordingDuration >= warningTime {
            return .yellow
        } else {
            return .secondary
        }
    }

    private func attemptCancel() {
        // For recordings over 30 seconds, show confirmation
        if recordingDuration >= cancelConfirmationThreshold && !frozenTranscript.isEmpty {
            showCancelConfirmation = true
        } else {
            let generator = UINotificationFeedbackGenerator()
            generator.notificationOccurred(.error)
            onCancel()
        }
    }

    private func formatDuration(_ duration: TimeInterval) -> String {
        let minutes = Int(duration) / 60
        let seconds = Int(duration) % 60
        let tenths = Int((duration.truncatingRemainder(dividingBy: 1)) * 10)
        return String(format: "%d:%02d.%d", minutes, seconds, tenths)
    }

    private func formatDurationShort(_ duration: TimeInterval) -> String {
        let minutes = Int(duration) / 60
        let seconds = Int(duration) % 60
        if minutes > 0 {
            return "\(minutes)m \(seconds)s"
        } else {
            return "\(seconds)s"
        }
    }
}

// MARK: - Waveform Ring

struct WaveformRing: View {
    let audioLevel: Float
    let isSilent: Bool

    @State private var breathing = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var normalizedLevel: CGFloat {
        CGFloat(max(0, min(1, (audioLevel + 60) / 50)))
    }

    var body: some View {
        ZStack {
            // Base ring
            Circle()
                .stroke(isSilent ? Color.green.opacity(0.3) : Color.blue.opacity(0.2), lineWidth: 3)

            // Active ring segments (only show while recording)
            if !isSilent {
                ForEach(0..<12, id: \.self) { i in
                    WaveformSegment(
                        index: i,
                        level: normalizedLevel,
                        isSilent: isSilent
                    )
                }
            }
        }
        .scaleEffect(isSilent ? 1.0 : 1.0 + (breathing ? 0.03 : 0))
        .animation(reduceMotion ? .none : .easeInOut(duration: 1.2).repeatForever(autoreverses: true), value: breathing)
        .onAppear {
            breathing = true
        }
    }
}

struct WaveformSegment: View {
    let index: Int
    let level: CGFloat
    let isSilent: Bool

    private var segmentLevel: CGFloat {
        // Vary height based on index for organic feel
        let variance = CGFloat(abs(sin(Double(index) * 0.5))) * 0.5 + 0.5
        return level * variance
    }

    var body: some View {
        RoundedRectangle(cornerRadius: 2)
            .fill(isSilent ? Color.gray.opacity(0.4) : Color.blue.opacity(0.7 + segmentLevel * 0.3))
            .frame(width: 4, height: 8 + segmentLevel * 12)
            .offset(y: -28)  // Position on ring edge
            .rotationEffect(.degrees(Double(index) * 30))
            .animation(.easeOut(duration: 0.1), value: level)
    }
}

// MARK: - Transcription View

struct TranscriptionView: View {
    let text: String

    @State private var displayedWords: [String] = []
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        if text.isEmpty {
            Text("Listening...")
                .foregroundColor(.secondary)
                .italic()
        } else {
            // Word-by-word display with animations
            WrappingHStack(alignment: .leading, spacing: 4) {
                ForEach(Array(text.split(separator: " ").enumerated()), id: \.offset) { index, word in
                    Text(String(word))
                        .font(.body)
                        .foregroundColor(.primary)
                        .transition(reduceMotion ? .opacity : .asymmetric(
                            insertion: .scale(scale: 0.8).combined(with: .opacity),
                            removal: .opacity
                        ))
                }
            }
            .animation(reduceMotion ? .none : .spring(response: 0.25, dampingFraction: 0.7), value: text)
        }
    }
}

// Simple wrapping HStack
struct WrappingHStack: Layout {
    var alignment: HorizontalAlignment = .leading
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = FlowResult(in: proposal.width ?? 0, subviews: subviews, spacing: spacing)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = FlowResult(in: bounds.width, subviews: subviews, spacing: spacing)
        for (index, subview) in subviews.enumerated() {
            subview.place(at: CGPoint(x: bounds.minX + result.positions[index].x,
                                      y: bounds.minY + result.positions[index].y),
                         proposal: .unspecified)
        }
    }

    struct FlowResult {
        var size: CGSize = .zero
        var positions: [CGPoint] = []

        init(in maxWidth: CGFloat, subviews: Subviews, spacing: CGFloat) {
            var x: CGFloat = 0
            var y: CGFloat = 0
            var lineHeight: CGFloat = 0

            for subview in subviews {
                let size = subview.sizeThatFits(.unspecified)

                if x + size.width > maxWidth && x > 0 {
                    x = 0
                    y += lineHeight + spacing
                    lineHeight = 0
                }

                positions.append(CGPoint(x: x, y: y))
                lineHeight = max(lineHeight, size.height)
                x += size.width + spacing

                self.size.width = max(self.size.width, x)
            }

            self.size.height = y + lineHeight
        }
    }
}

// MARK: - Recording Placeholder (for chat)

struct RecordingPlaceholder: View {
    @State private var isPulsing = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack {
            Spacer(minLength: 60)

            HStack(spacing: 8) {
                Circle()
                    .fill(Color(red: 1.0, green: 0.4, blue: 0.4))
                    .frame(width: 10, height: 10)
                    .scaleEffect(isPulsing ? 1.2 : 0.8)
                    .opacity(isPulsing ? 1.0 : 0.6)
                    .animation(reduceMotion ? .none : .easeInOut(duration: 0.6).repeatForever(autoreverses: true), value: isPulsing)

                Text("Recording...")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color(red: 1.0, green: 0.4, blue: 0.4, opacity: 0.15))
            .cornerRadius(16)
        }
        .onAppear {
            isPulsing = true
        }
    }
}

// MARK: - Preview

#Preview {
    @Previewable @State var hasSent = false
    RecordingSheet(
        recorder: AudioRecorder(),
        onSend: { _ in },
        onCancel: { },
        hasSent: $hasSent
    )
    .presentationDetents([.fraction(0.4)])
}
