import SwiftUI

/// The alliance's moment.
///
/// `Let's Form An Alliance` used to happen almost silently: the ally's phone
/// got a normal-priority steal toast, no louder than a vote_cast line, and a
/// card simply appeared in their hand with nothing marking why. Nothing at
/// all durably told either partner what had just happened.
///
///  · the two PARTNERS (initiator and ally) get this blocking overlay
///  · everyone else at the table keeps the ordinary NarrationFeed toast
///
/// Presentation mirrors `ReactiveTheftOverlay`'s single centered card over a
/// black scrim. Unlike that overlay, nothing here is a server round trip
/// waiting on an answer — it's dismissed by a tap of your own, the same
/// "continue" idiom `InteractionScreen`'s reveal panel uses.
struct AllianceOverlay: View {
    @Environment(GameClient.self) private var gameClient

    var body: some View {
        if let alert = gameClient.allianceAlert {
            ZStack {
                Color.black.opacity(0.65).ignoresSafeArea()

                VStack(spacing: 16) {
                    Image(systemName: "person.2.fill")
                        .font(.system(size: 34))
                        .foregroundStyle(Torch.Color.juryGold)
                        .shadow(color: Torch.Color.juryGold.opacity(0.4), radius: 12)
                        .accessibilityHidden(true)

                    Text("An Alliance Is Formed")
                        .font(Torch.Font.display(Torch.TextSize.displaySM, weight: 700))
                        .foregroundStyle(Torch.Color.parchment)
                        .multilineTextAlignment(.center)

                    Text("You and \(alert.partnerName) raid \(alert.victimName)'s camp together.")
                        .font(Torch.Font.body(Torch.TextSize.sm))
                        .multilineTextAlignment(.center)
                        .foregroundStyle(Torch.Color.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)

                    Text("The spoils are in your hand.")
                        .font(Torch.Font.display(Torch.TextSize.sm, weight: 500, italic: true))
                        .foregroundStyle(Torch.Color.juryGold)

                    Button("continue") {
                        gameClient.dismissAllianceAlert()
                    }
                    .buttonStyle(.torchGlow)
                    .accessibilityLabel("Continue")
                }
                .padding(24)
                .background(.regularMaterial)
                .clipShape(RoundedRectangle(cornerRadius: 18))
                .padding(28)
            }
            .transition(.opacity)
            .onAppear {
                // The screen owns this cue itself (same idiom as
                // FinalTribalScreen's onAppear) — the event that fed this
                // overlay was routed away from `narration`, so `NarrationFeed`
                // never got the chance to play `.steal` for it.
                HapticEngine.steal()
                TorchSound.play(.steal)
            }
        }
    }
}
