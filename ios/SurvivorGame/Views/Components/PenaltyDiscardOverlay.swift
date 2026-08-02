import SwiftUI

/// Paying for a raid that got blocked.
///
/// "…they get nothing from you and must discard 1 card." A discard is chosen by
/// the player making it. The engine used to take the last takeable card in the
/// raider's hand without asking, which is why a card seemed to vanish — and
/// which made the Survival Guide's own advice impossible to follow: hold an
/// Inheritance for a colour nobody is playing and feed it to a Sorry For You.
///
///  · a RAIDER who owes the penalty picks the card
///  · everyone else sees who the table is waiting on
///
/// Only raiders with a real choice arrive here. One discardable card is not a
/// decision, and the server resolves that without opening a window at all.
struct PenaltyDiscardOverlay: View {
    @Environment(GameClient.self) private var gameClient
    @State private var isActing = false
    @State private var error: ViewModelError?

    private var pending: PendingDiscardsState? {
        let window = gameClient.gameState?.pendingDiscards
        return (window?.awaiting.isEmpty == false) ? window : nil
    }

    private var players: [String: PlayerState] { gameClient.gameState?.players ?? [:] }

    var body: some View {
        if let pending {
            if let me = gameClient.playerId, pending.awaiting.contains(me) {
                picker(pending)
            } else {
                waitingBanner(pending)
            }
        }
    }

    // MARK: - The raider's choice

    private func picker(_ pending: PendingDiscardsState) -> some View {
        // The Vote Card is not part of the economy a penalty can touch, so it
        // is not on the menu at all — the server would refuse it anyway.
        let hand = gameClient.myPlayer?.hand ?? []
        let offerable = hand.enumerated().filter { $0.element.type != "vote" }
        let defender = pending.defenderId.flatMap { players[$0]?.name }

        return ZStack {
            Color.black.opacity(0.65).ignoresSafeArea()

            VStack(spacing: 14) {
                Text("Sorry For You")
                    .font(Torch.Font.display(Torch.TextSize.displaySM, weight: 700))
                    .foregroundStyle(Torch.Color.parchment)

                Text(defender.map { "\($0) blocked your raid — you get nothing, and you owe a card." }
                     ?? "Your raid was blocked — you get nothing, and you owe a card.")
                    .font(Torch.Font.body(Torch.TextSize.sm))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(Torch.Color.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                Text("Choose the card you give up.")
                    .font(Torch.Font.label(Torch.TextSize.xs))
                    .tracking(Torch.Track.label * Torch.TextSize.xs)
                    .foregroundStyle(Torch.Color.torch)

                // A ScrollView is greedy along its scroll axis, so a fixed
                // maxHeight reserved all 260pt for three rows and left the
                // dialog mostly empty. Take the natural height when it fits;
                // scroll only when a big hand genuinely overflows.
                ViewThatFits(in: .vertical) {
                    cardList(offerable)
                    ScrollView { cardList(offerable) }.frame(maxHeight: 300)
                }

                if isActing { ProgressView().tint(Torch.Color.torch) }
            }
            .padding(24)
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .padding(28)
            .errorAlert($error)
        }
        .transition(.opacity)
    }

    @ViewBuilder
    private func cardList(
        _ offerable: [(offset: Int, element: CardInstance)]
    ) -> some View {
        VStack(spacing: 8) {
            ForEach(offerable, id: \.offset) { index, card in
                            let resolved = CardCatalog.shared.resolve(card)
                            Button {
                                Task { await pay(index: index) }
                            } label: {
                                HStack {
                                    Text(resolved.displayName)
                                        .font(Torch.Font.body(Torch.TextSize.base, weight: .semibold))
                                        .foregroundStyle(Torch.Color.text)
                                    Spacer()
                                    Image(systemName: "arrow.down.circle")
                                        .foregroundStyle(Torch.Color.textSecondary)
                                }
                                .padding(12)
                                .frame(maxWidth: .infinity)
                                .background(
                                    RoundedRectangle(cornerRadius: Torch.Radius.md,
                                                     style: .continuous)
                                        .fill(Torch.Color.surfaceSunken)
                                )
                            }
                            .buttonStyle(.plain)
                            .disabled(isActing)
                            .accessibilityElement(children: .combine)
                            .accessibilityLabel("Discard \(resolved.displayName)")
                            .accessibilityAddTraits(.isButton)
            }
        }
    }

    // MARK: - Everyone else

    private func waitingBanner(_ pending: PendingDiscardsState) -> some View {
        let names = pending.awaiting
            .compactMap { players[$0]?.name }
            .joined(separator: " and ")
        return VStack {
            Spacer()
            HStack(spacing: 8) {
                ProgressView()
                Text(names.isEmpty
                     ? "Waiting on the penalty…"
                     : "Waiting on \(names) to pay for the raid…")
                    .font(.caption)
            }
            .padding(12)
            .background(.regularMaterial)
            .clipShape(Capsule())
            .padding(.bottom, 24)
        }
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    private func pay(index: Int) async {
        isActing = true
        defer { isActing = false }
        do {
            try await gameClient.choosePenaltyDiscard(at: index)
            HapticEngine.cardPlay()
        } catch {
            self.error = .from(error)
        }
    }
}
