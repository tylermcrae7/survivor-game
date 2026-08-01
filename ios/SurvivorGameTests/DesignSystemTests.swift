import Testing
import SwiftUI
import UIKit
import CoreHaptics
import AVFoundation
@testable import SurvivorGame

struct DesignSystemTests {

    // MARK: - Theme palette

    private func rgba(_ color: Color) -> (r: Double, g: Double, b: Double, a: Double)? {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        guard UIColor(color).getRed(&r, green: &g, blue: &b, alpha: &a) else { return nil }
        return (Double(r), Double(g), Double(b), Double(a))
    }

    @Test func themeColorsMatchTheResearchPalette() throws {
        let expectations: [(Color, String)] = [
            (Torch.Color.torch, "#E68100"),
            (Torch.Color.flame, "#F9AD26"),
            (Torch.Color.ember, "#BF4306"),
            (Torch.Color.emberDeep, "#7C1403"),
            (Torch.Color.torchDeep, "#C75E00"),
            (Torch.Color.torchBorder, "#B0540E"),
            (Torch.Color.background, "#020604"),
            (Torch.Color.backgroundDeep, "#010302"),
            (Torch.Color.surface, "#050F0A"),
            (Torch.Color.surfaceRaised, "#0B1710"),
            (Torch.Color.surfaceSunken, "#030906"),
            (Torch.Color.parchment, "#EEE0C4"),
            (Torch.Color.parchmentDim, "#D9C8AA"),
            (Torch.Color.ink, "#2A1C10"),
            (Torch.Color.inkSoft, "#4C382B"),
            (Torch.Color.text, "#EEE7D9"),
            (Torch.Color.textSecondary, "#9F9481"),
            (Torch.Color.textFaint, "#6B6253"),
            (Torch.Color.danger, "#D33C33"),
            (Torch.Color.success, "#429C5A"),
            (Torch.Color.warning, "#DFA635"),
            (Torch.Color.info, "#4AA7B7"),
            (Torch.Color.juryGold, "#D8B349"),
        ]
        for (color, hex) in expectations {
            let reference = try #require(Color(hex: hex), "invalid reference hex \(hex)")
            let got = try #require(rgba(color), "could not resolve token for \(hex)")
            let want = try #require(rgba(reference))
            #expect(abs(got.r - want.r) < 0.005, "red mismatch for \(hex)")
            #expect(abs(got.g - want.g) < 0.005, "green mismatch for \(hex)")
            #expect(abs(got.b - want.b) < 0.005, "blue mismatch for \(hex)")
            #expect(got.a == 1.0, "token for \(hex) should be opaque")
        }
        #expect(Torch.Color.emberConfetti.count == 6)
    }

    @Test func hairlinesCarryTheWebAlphas() throws {
        let line = try #require(rgba(Torch.Color.line))
        let strong = try #require(rgba(Torch.Color.lineStrong))
        #expect(abs(line.a - 0.09) < 0.005)
        #expect(abs(strong.a - 0.16) < 0.005)
    }

    // MARK: - Layout scale

    @Test func radiiAndSpacingMatchTheWebScale() {
        #expect(Torch.Radius.sm == 6)
        #expect(Torch.Radius.md == 10)
        #expect(Torch.Radius.lg == 16)
        #expect(Torch.Radius.xl == 22)
        #expect(Torch.Spacing.xs == 4)
        #expect(Torch.Spacing.sm == 8)
        #expect(Torch.Spacing.md == 16)
        #expect(Torch.Spacing.lg == 24)
        #expect(Torch.Spacing.xl == 36)
        #expect(Torch.Spacing.touchTarget == 48)
        #expect(Torch.Track.label == 0.14)
        #expect(Torch.Track.wide == 0.22)
    }

    // MARK: - Fonts

    @Test func bundledFrauncesIsRegistered() {
        // UIAppFonts registration happens in the host app bundle.
        #expect(!UIFont.fontNames(forFamilyName: "Fraunces").isEmpty)
        #expect(Torch.Font.frauncesAvailable)
    }

    @Test func displayFontResolvesRomanAndItalicFraunces() throws {
        let roman = try #require(Torch.Font.displayUIFont(33, weight: 850, soft: 40))
        #expect(roman.familyName == "Fraunces")
        let italic = try #require(Torch.Font.displayUIFont(33, weight: 900, soft: 60, italic: true))
        #expect(italic.familyName == "Fraunces")
        #expect(roman.fontName != italic.fontName)
    }

    @Test func bodyAndLabelFontsResolve() {
        // SF-based fonts are non-optional; exercise every recipe entry point.
        _ = Torch.Font.display(56, weight: 900, soft: 30) // wordmark
        _ = Torch.Font.body(Torch.TextSize.base)
        _ = Torch.Font.label(Torch.TextSize.sm)
        _ = Torch.Font.label(Torch.TextSize.xs)
        #expect(Torch.TextSize.sm == 13.4)
        #expect(Torch.TextSize.xs == 11.5)
    }

    // MARK: - Place icons

    /// A place whose glyph doesn't exist on this OS renders as a silent blank,
    /// which reads as a bug rather than a missing symbol. Every place must
    /// resolve — including the beach, whose umbrella is an SF Symbols 4 glyph
    /// and falls back to `water.waves` when absent.
    @Test func everyPlaceIconResolvesOnThisOS() {
        for place in Place.allCases {
            #expect(UIImage(systemName: place.symbolName) != nil,
                    "\(place.key) has no glyph for \(place.symbolName)")
        }
        #expect(UIImage(systemName: Place.symbolName(for: "an_unknown_place")) != nil)
        #expect(["beach.umbrella.fill", "water.waves"].contains(Place.beachSymbol))
    }

    // MARK: - Haptic patterns

    @MainActor @Test func hapticPatternsCompileWithoutThrowing() throws {
        let voteSlam = try HapticEngine.voteSlamPattern()
        #expect(voteSlam.duration > 0)

        let torchSnuff = try HapticEngine.torchSnuffPattern()
        #expect(abs(torchSnuff.duration - 1.4) < 0.01)

        let turnPulse = try HapticEngine.turnPulsePattern()
        #expect(turnPulse.duration > 1.6) // second swell starts at 1.6s

        let unlock = try HapticEngine.unlockPattern()
        #expect(unlock.duration > 0)

        let winner = try HapticEngine.winnerPattern()
        #expect(abs(winner.duration - 0.95) < 0.01)
    }

    // MARK: - Audio cue rendering (pure DSP — no session, no playback)

    @Test func everyAudioCueRendersAFiniteNonSilentBuffer() throws {
        for cue in TorchCue.allCases {
            let buffer = try TorchSound.renderBuffer(for: cue)
            let frames = Int(buffer.frameLength)
            #expect(frames == Int(cue.duration * 44_100), "wrong length for \(cue)")

            let samples = try #require(buffer.floatChannelData?[0])
            var peak: Float = 0
            var allFinite = true
            for i in 0..<frames {
                let s = samples[i]
                if !s.isFinite { allFinite = false; break }
                peak = max(peak, abs(s))
            }
            #expect(allFinite, "\(cue) rendered a non-finite sample")
            #expect(peak > 0.005, "\(cue) rendered silence")
            #expect(peak <= 1.0, "\(cue) clips at \(peak)")
        }
    }

    @Test func audioCueTimingsMatchTheWebRecipes() {
        #expect(TorchCue.tribalGong.duration == 2.0)
        #expect(TorchCue.torchSnuff.duration == 1.5)
        #expect(TorchCue.voteReveal.duration == 0.3)
        #expect(TorchCue.cardPlay.duration == 0.3)
        #expect(TorchCue.victory.duration == 0.95)
        #expect(TorchCue.steal.duration == 0.15)
        #expect(TorchCue.notification.duration == 0.2)
    }

    /// Regression: a phone call interrupts the session, the system stops the
    /// engine, but `started` stays true — every later cue is silently eaten.
    /// Interruptions must invalidate the engine exactly like route changes
    /// and media-server resets already do.
    @Test func interruptionsInvalidateTheEngineLikeRouteChanges() {
        let invalidating = Set(TorchSound.engineInvalidatingNotifications)
        #expect(invalidating.contains(AVAudioSession.interruptionNotification))
        #expect(invalidating.contains(AVAudioSession.routeChangeNotification))
        #expect(invalidating.contains(AVAudioSession.mediaServicesWereResetNotification))
    }

    /// The cues survive an interruption: posting one must not trap, and the
    /// buffers the engine replays afterwards still render.
    @Test func aCueStillRendersAfterAnInterruptionIsPosted() throws {
        TorchSound.play(.notification)
        for name in TorchSound.engineInvalidatingNotifications {
            NotificationCenter.default.post(name: name, object: nil)
        }
        let buffer = try TorchSound.renderBuffer(for: .notification)
        #expect(buffer.frameLength > 0)
    }
}

/// Regression: a variation-axis font descriptor silently broke SwiftUI's
/// Font bridge (rendered 12pt regardless of requested size). Render the
/// display face and measure — not just inspect pointSize.
@Suite struct DisplayFontRenderTests {
    @Test @MainActor func displayFaceRendersAtRequestedSize() throws {
        let renderer = ImageRenderer(content:
            Text("Survivor").font(Torch.Font.display(56, weight: 900, soft: 30)))
        let size = try #require(renderer.uiImage?.size)
        #expect(size.width > 150 && size.height > 40)
    }
}
