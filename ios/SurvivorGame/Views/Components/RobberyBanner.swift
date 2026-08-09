import SwiftUI

/// The victim's own moment: what got taken, and by whom.
///
/// A steal happens on nearly every turn — `AllianceOverlay`'s blocking scrim
/// is right for an alliance because an alliance is rare; a blocking modal on
/// every theft would be intolerable. This is a banner instead: bigger and
/// longer-lived than the narration ticker (which is `lineLimit(1)` and
/// structurally cannot carry a card name), auto-dismissing, tap-to-dismiss,
/// and — deliberately unlike `AllianceOverlay` — never blocking. It reuses
/// AllianceOverlay's card-on-material look, not its full-screen scrim.
///
/// Mounted as a `Color.clear` base with `allowsHitTesting(false)`, with the
/// visible card drawn only inside its own `.overlay` — the same reasoning
/// `NarrationHost` documents (ToastView.swift): a floating strip is a
/// perfect way to eat a tap meant for a button underneath if its invisible
/// bounds reach further than its paint does. Here the card itself SHOULD
/// capture a tap (that's the dismiss gesture); the base underneath it must
/// never capture one, and only the base spans the screen.
struct RobberyBanner: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// Long enough to read "Coconut took 2 of your cards — Hidden Immunity
    /// Idol and Vote", short enough to be gone before the next couple of
    /// turns bury it.
    private static let dismissAfter: Duration = .seconds(5)

    var body: some View {
        Color.clear
            .allowsHitTesting(false)
            .overlay(alignment: .top) {
                if let alert = gameClient.robberyAlert {
                    RobberyBannerCard(alert: alert)
                        // A fresh view identity per STAGING, not per content:
                        // the same thief taking the same card twice produces
                        // equal content back to back, and content-keyed
                        // identity would neither run the hand-off transition,
                        // restart the five-second clock, nor buzz again — the
                        // second robbery would ride out the first one's
                        // remaining seconds in silence.
                        .id(gameClient.robberySequence)
                        .padding(.horizontal, 20)
                        // Clears the camp strip / FIRE pill the same way
                        // ConnectionBanner does.
                        .padding(.top, 52)
                        .transition(reduceMotion
                                    ? .opacity
                                    : .move(edge: .top).combined(with: .opacity))
                        // A tap advances to the next queued robbery, if any —
                        // an alliance raid delivers two, and dismissing the
                        // first must not eat the second.
                        .onTapGesture { gameClient.dismissRobberyAlert() }
                        .task {
                            HapticEngine.notification(.warning)
                            try? await Task.sleep(for: Self.dismissAfter)
                            gameClient.dismissRobberyAlert()
                        }
                }
            }
            // Two triggers, one look: sequence animates the banner-to-banner
            // hand-off; the nil flip animates the last one's exit.
            .animation(reduceMotion ? .none : .torchEaseOut(duration: 0.26),
                       value: gameClient.robberySequence)
            .animation(reduceMotion ? .none : .torchEaseOut(duration: 0.26),
                       value: gameClient.robberyAlert == nil)
    }
}

/// The card itself, split out so its accent colour lookup reads cleanly.
private struct RobberyBannerCard: View {
    @Environment(GameClient.self) private var gameClient
    let alert: RobberyBannerContent

    /// The thief's own seat colour — the same identity cue `PlayerAvatarView`
    /// uses at the table — so the banner reads as "who did this to you" at a
    /// glance. Falls back to danger red when the thief isn't in the roster
    /// this client currently holds.
    private var accent: Color {
        alert.thiefId.flatMap { gameClient.gameState?.players[$0]?.swiftUIColor } ?? Torch.Color.danger
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "hand.raised.slash.fill")
                .font(.system(size: 20))
                .foregroundStyle(accent)
                .accessibilityHidden(true)

            Text(alert.message)
                .font(Torch.Font.display(Torch.TextSize.sm, weight: 700))
                .foregroundStyle(Torch.Color.parchment)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)

            Spacer(minLength: 0)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(
            RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
                .fill(Torch.Color.surfaceRaised)
        )
        .overlay(
            RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
                .strokeBorder(accent.opacity(0.7), lineWidth: 2)
        )
        .overlay(alignment: .leading) {
            // The seat-colour accent, made unmissable: a solid bar down the
            // leading edge, not just a hairline stroke.
            RoundedRectangle(cornerRadius: Torch.Radius.sm)
                .fill(accent)
                .frame(width: 4)
                .padding(.vertical, 8)
                .padding(.leading, 3)
        }
        .shadow(color: .black.opacity(0.45), radius: 14, y: 6)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .accessibilityHint("Dismiss")
    }
}
