import AVFoundation
import UIKit

/// The seven procedural cues from the web's `SoundManager` (narrator.js).
enum TorchCue: String, CaseIterable, Sendable {
    case tribalGong    // game start / tribal announcement — deep gong
    case torchSnuff    // elimination — sizzle closing to a hiss
    case voteReveal    // "I'll read the votes…" — drum hit
    case cardPlay      // any card — paper whoosh
    case victory       // winner — C5-E5-G5-C6 fanfare
    case steal         // steal — descending zip
    case notification  // vote cast — soft 880Hz ping

    var duration: Double {
        switch self {
        case .tribalGong: 2.0
        case .torchSnuff: 1.5
        case .voteReveal: 0.3
        case .cardPlay: 0.3
        case .victory: 0.95
        case .steal: 0.15
        case .notification: 0.2
        }
    }
}

/// Procedural sound engine: each cue is synthesized once (the exact Web
/// Audio recipes) into a cached PCM buffer and played through a single
/// AVAudioEngine. `.ambient` + `.mixWithOthers` — the silent switch mutes
/// the game and the player's own music keeps playing. The engine starts
/// lazily on the first cue and suspends when the app backgrounds.
actor TorchSound {
    static let shared = TorchSound()

    private init() {}

    // MARK: - Public API

    /// Both of the web's gates: the sound setting and the narrator mute.
    nonisolated static var isSoundOn: Bool {
        UserDefaults.standard.object(forKey: "soundEnabled") as? Bool ?? true
    }

    nonisolated static var isNarratorMuted: Bool {
        UserDefaults.standard.bool(forKey: "narratorMuted")
    }

    /// Fire-and-forget playback. Overlapping cues just layer.
    nonisolated static func play(_ cue: TorchCue) {
        guard isSoundOn, !isNarratorMuted else { return }
        Task { await shared.schedule(cue) }
    }

    /// Pause the engine and release the audio session (call on background;
    /// also self-triggered via UIApplication.didEnterBackgroundNotification).
    nonisolated static func suspend() {
        Task { await shared.suspendEngine() }
    }

    // MARK: - Engine lifecycle

    private static let sampleRate: Double = 44_100

    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    private var cache: [TorchCue: AVAudioPCMBuffer] = [:]
    private var started = false
    private var attached = false
    private var observing = false

    private func schedule(_ cue: TorchCue) {
        do {
            try startIfNeeded()
            let buffer: AVAudioPCMBuffer
            if let cached = cache[cue] {
                buffer = cached
            } else {
                buffer = try Self.renderBuffer(for: cue)
                cache[cue] = buffer
            }
            player.scheduleBuffer(buffer, at: nil, options: [], completionHandler: nil)
            if !player.isPlaying { player.play() }
        } catch {
            started = false // rebuild cleanly on the next cue
        }
    }

    private func startIfNeeded() throws {
        guard !started else { return }
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.ambient, mode: .default, options: [.mixWithOthers])
        try session.setActive(true)
        if !attached {
            engine.attach(player)
            let format = AVAudioFormat(standardFormatWithSampleRate: Self.sampleRate, channels: 1)
            engine.connect(player, to: engine.mainMixerNode, format: format)
            attached = true
        }
        engine.prepare()
        try engine.start()
        player.play()
        started = true
        installObserversIfNeeded()
    }

    private func suspendEngine() {
        player.stop()
        engine.pause()
        try? AVAudioSession.sharedInstance().setActive(false, options: [.notifyOthersOnDeactivation])
        started = false
    }

    /// Route changes and media-server resets invalidate the running graph;
    /// the next cue rebuilds it.
    private func invalidateEngine() {
        engine.stop()
        started = false
    }

    private func installObserversIfNeeded() {
        guard !observing else { return }
        observing = true
        let center = NotificationCenter.default
        for name in [AVAudioSession.routeChangeNotification,
                     AVAudioSession.mediaServicesWereResetNotification] {
            _ = center.addObserver(forName: name, object: nil, queue: nil) { _ in
                Task { await TorchSound.shared.invalidateEngine() }
            }
        }
        _ = center.addObserver(forName: UIApplication.didEnterBackgroundNotification,
                               object: nil, queue: nil) { _ in
            Task { await TorchSound.shared.suspendEngine() }
        }
    }

    // MARK: - Synthesis (exact Web Audio recipes, rendered offline)

    /// Web Audio's exponentialRampToValueAtTime: v(t) = v0 · (v1/v0)^(t/T).
    @inline(__always)
    private static func expRamp(_ v0: Float, _ v1: Float, _ t: Float, over T: Float) -> Float {
        v0 * powf(v1 / v0, min(max(t, 0) / T, 1))
    }

    /// Render one cue into a mono float32 buffer. Pure DSP — touches no
    /// audio session or hardware, so it is directly testable.
    static func renderBuffer(for cue: TorchCue,
                             sampleRate: Double = 44_100) throws -> AVAudioPCMBuffer {
        let sr = Float(sampleRate)
        let frames = AVAudioFrameCount(cue.duration * sampleRate)
        guard let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames) else {
            throw CocoaError(.coderInvalidValue)
        }
        buffer.frameLength = frames
        let out = buffer.floatChannelData![0]
        let n = Int(frames)

        switch cue {
        case .tribalGong:
            // Sine 80 → 40 Hz exp over 2s; gain 0.5 → 0.01 exp over 2s.
            var phase: Float = 0
            for i in 0..<n {
                let t = Float(i) / sr
                phase += 2 * .pi * expRamp(80, 40, t, over: 2.0) / sr
                out[i] = sinf(phase) * expRamp(0.5, 0.01, t, over: 2.0)
            }

        case .torchSnuff:
            // White noise with a baked 300ms exp decay, through a one-pole
            // lowpass sweeping 3000 → 200 Hz exp over 1.5s; gain 0.4.
            var y: Float = 0
            for i in 0..<n {
                let t = Float(i) / sr
                let x = Float.random(in: -1...1) * expf(-Float(i) / (sr * 0.3))
                let a = expf(-2 * .pi * expRamp(3000, 200, t, over: 1.5) / sr)
                y = (1 - a) * x + a * y
                out[i] = y * 0.4
            }

        case .voteReveal:
            // Kick-drum pitch drop: sine 150 → 50 Hz exp over 0.2s;
            // gain 0.6 → 0.01 exp over 0.3s (the loudest cue).
            var phase: Float = 0
            for i in 0..<n {
                let t = Float(i) / sr
                phase += 2 * .pi * expRamp(150, 50, t, over: 0.2) / sr
                out[i] = sinf(phase) * expRamp(0.6, 0.01, t, over: 0.3)
            }

        case .cardPlay:
            // Noise with a sin(t·π) × 0.5 swell, through an RBJ bandpass
            // (constant 0 dB peak) at 1000 Hz, Q = 1.
            let omega = 2 * Float.pi * 1000 / sr
            let alpha = sinf(omega) / 2 // sin(ω)/(2Q), Q = 1
            let a0 = 1 + alpha
            let b0 = alpha / a0, b2 = -alpha / a0
            let a1 = -2 * cosf(omega) / a0, a2 = (1 - alpha) / a0
            var x1: Float = 0, x2: Float = 0, y1: Float = 0, y2: Float = 0
            for i in 0..<n {
                let t = Float(i) / sr
                let x = Float.random(in: -1...1) * sinf(t / 0.3 * .pi) * 0.5
                let y = b0 * x + b2 * x2 - a1 * y1 - a2 * y2
                x2 = x1; x1 = x
                y2 = y1; y1 = y
                out[i] = y
            }

        case .victory:
            // Four triangle notes (C5 E5 G5 C6), one every 150ms; each
            // 50ms linear attack to 0.3, exp decay to 0.01 by +0.5s.
            // Band-limited triangle: (8/π²) Σ (-1)^k sin((2k+1)ωt)/(2k+1)².
            let notes: [Float] = [523.25, 659.25, 783.99, 1046.50]
            for i in 0..<n {
                let t = Float(i) / sr
                var sample: Float = 0
                for (index, freq) in notes.enumerated() {
                    let nt = t - Float(index) * 0.15
                    guard nt >= 0, nt <= 0.5 else { continue }
                    let env: Float = nt < 0.05
                        ? 0.3 * (nt / 0.05)
                        : expRamp(0.3, 0.01, nt - 0.05, over: 0.45)
                    var tri: Float = 0
                    for k in 0..<8 {
                        let harmonic = Float(2 * k + 1)
                        let sign: Float = k.isMultiple(of: 2) ? 1 : -1
                        tri += sign * sinf(harmonic * 2 * .pi * freq * nt) / (harmonic * harmonic)
                    }
                    sample += (8 / (Float.pi * Float.pi)) * tri * env
                }
                out[i] = sample
            }

        case .steal:
            // Sawtooth 800 → 200 Hz exp over 0.15s; gain 0.2 → 0.01.
            var phase: Float = 0
            for i in 0..<n {
                let t = Float(i) / sr
                phase += expRamp(800, 200, t, over: 0.15) / sr
                phase -= floorf(phase)
                out[i] = (2 * phase - 1) * expRamp(0.2, 0.01, t, over: 0.15)
            }

        case .notification:
            // Constant 880 Hz (A5) sine; gain 0.2 → 0.01 exp over 0.2s.
            for i in 0..<n {
                let t = Float(i) / sr
                out[i] = sinf(2 * .pi * 880 * t) * expRamp(0.2, 0.01, t, over: 0.2)
            }
        }

        return buffer
    }
}
