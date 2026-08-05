import Foundation
import Observation

/// Paces the server's commentary so it reads like a narrator rather than a log.
///
/// The web app renders its queue strictly serially with no cap, so a burst
/// falls permanently behind real time. On a phone that is worse than useless —
/// a toast describing a steal that happened four turns ago is actively
/// misleading. This drops what has gone stale, collapses repeats, and always
/// lets the dramatic beats through.
@Observable
@MainActor
final class NarrationFeed {
    /// What the toast is showing, if anything.
    private(set) var current: NarrationEvent?

    /// Bounded on purpose: a double elimination plus a flurry of bot turns can
    /// deliver a dozen events between two frames, and nobody reads twelve
    /// toasts. Beyond this the lowest-priority oldest entry is dropped.
    private let capacity = 3
    private let minDwell: Duration
    private let gap: Duration

    private var queue: [NarrationEvent] = []
    private var isDraining = false
    private var lastCue: (cue: TorchCue, at: ContinuousClock.Instant)?
    private let clock = ContinuousClock()

    init(minDwell: Duration = .milliseconds(2400), gap: Duration = .milliseconds(350)) {
        self.minDwell = minDwell
        self.gap = gap
    }

    /// True from the first toast until the last one clears. The host reserves
    /// its strip of screen against this rather than against `current`, which
    /// blinks to nil between toasts and would bounce the whole layout.
    var isNarrating: Bool { current != nil || !queue.isEmpty }

    /// Queue inspection, for tests only — the pacing rules are the whole point
    /// of this type and they are invisible from `current` alone.
    var queueDepthForTesting: Int { queue.count }
    var pendingForTesting: [NarrationEvent] { queue }

    func enqueue(_ event: NarrationEvent) {
        // Collapse a repeat of the same chatter — three ballots in a row are
        // one piece of news, not three.
        if let key = event.coalescingKey,
           let idx = queue.lastIndex(where: { $0.coalescingKey == key }) {
            queue[idx] = event
            drain()
            return
        }

        if queue.count >= capacity {
            // Evict the least important thing waiting; if this event is the
            // least important thing, it is the one that gets dropped.
            guard let victim = queue.enumerated()
                    .filter({ $0.element.priority <= event.priority })
                    .min(by: { $0.element.priority < $1.element.priority })?.offset
            else { return }
            queue.remove(at: victim)
        }
        queue.append(event)
        drain()
    }

    /// Clears everything — a game reset or a wipe must not narrate the corpse
    /// of the previous game onto the start screen.
    func reset() {
        queue.removeAll()
        current = nil
    }

    private func drain() {
        guard !isDraining else { return }
        isDraining = true
        Task { @MainActor in
            defer { isDraining = false }
            while !queue.isEmpty {
                let event = queue.removeFirst()
                current = event
                play(event.cue)
                try? await Task.sleep(for: dwell(for: event))
                current = nil
                try? await Task.sleep(for: gap)
            }
        }
    }

    /// Long enough to actually read: a floor for short lines, ~60ms per
    /// character for longer ones, capped so a wordy event can't dam the queue.
    /// Internal rather than private, matching `queueDepthForTesting` and
    /// `pendingForTesting` above — this is the whole pacing rule and the
    /// tests need to see its math directly, not just infer it from timing.
    func dwell(for event: NarrationEvent) -> Duration {
        let byLength = Duration.milliseconds(event.message.count * 60)
        return max(minDwell, min(byLength, .milliseconds(4200)))
    }

    /// Never the same cue twice inside a beat. TorchSound deliberately layers
    /// overlapping cues — several call sites rely on that — so the de-duping
    /// belongs here, not there.
    private func play(_ cue: TorchCue?) {
        guard let cue else { return }
        let now = clock.now
        if let last = lastCue, last.cue == cue, now - last.at < .milliseconds(250) {
            return
        }
        lastCue = (cue, now)
        TorchSound.play(cue)
    }
}
