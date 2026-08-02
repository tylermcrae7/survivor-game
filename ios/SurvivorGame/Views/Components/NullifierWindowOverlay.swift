import SwiftUI

/// The beat after an Immunity Idol hits the table.
///
/// An Idol Nullifier can only be played once someone actually holds protection,
/// so it can never be played early — and before this window existed the tally
/// could land at any moment, so it frequently could not be played at all. The
/// idol applies immediately either way; this is the chance to take it back.
///
///  · a NULLIFIER HOLDER gets the blocking choice
///  · the IDOL PLAYER sees that the table is deciding
///  · everyone else sees nothing
///
/// Who is prompted is decided from your own hand, never from the window: the
/// server keeps the holder list under an underscore key and strips it before
/// the state ships, so no client can learn who else can answer.
struct NullifierWindowOverlay: View {
    @Environment(GameClient.self) private var gameClient
    @State private var isActing = false
    @State private var error: ViewModelError?

    private var pending: PendingNullifierState? {
        let window = gameClient.gameState?.pendingNullifier
        return window?.reactiveWindowOpen == true ? window : nil
    }

    private var players: [String: PlayerState] { gameClient.gameState?.players ?? [:] }

    private var holdsNullifier: Bool {
        gameClient.myPlayer?.hand.contains { $0.type == "idol_nullifier" } ?? false
    }

    var body: some View {
        if let pending, !(gameClient.isEliminated) {
            let me = gameClient.playerId
            if holdsNullifier && pending.idolPlayerId != me {
                responderDialog(pending)
            } else if pending.idolPlayerId == me {
                waitingBanner(pending)
            }
        }
    }

    // MARK: - Responder

    private func responderDialog(_ pending: PendingNullifierState) -> some View {
        let idolPlayer = pending.idolPlayerId.flatMap { players[$0]?.name } ?? "Someone"
        let shielded = pending.targetId.flatMap { players[$0]?.name } ?? idolPlayer
        let shieldedAnAlly = pending.targetId != pending.idolPlayerId

        return ZStack {
            Color.black.opacity(0.65).ignoresSafeArea()

            VStack(spacing: 16) {
                Image(systemName: "shield.slash.fill")
                    .font(.system(size: 34))
                    .foregroundStyle(Torch.Color.juryGold)
                    .accessibilityHidden(true)

                Text("An Idol Is Played")
                    .font(Torch.Font.display(Torch.TextSize.displaySM, weight: 700))
                    .foregroundStyle(Torch.Color.parchment)

                Text(shieldedAnAlly
                     ? "\(idolPlayer) played a Hidden Immunity Idol for \(shielded). Every vote against them is about to count for nothing."
                     : "\(idolPlayer) played a Hidden Immunity Idol. Every vote against them is about to count for nothing.")
                    .font(Torch.Font.body(Torch.TextSize.sm))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(Torch.Color.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                Text("You're holding an Idol Nullifier. Play it now and the idol does nothing — or hold your peace and let it stand.")
                    .font(Torch.Font.body(Torch.TextSize.xs))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(Torch.Color.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                Button {
                    Task { await nullify(pending) }
                } label: {
                    if isActing { ProgressView().tint(.white) }
                    else {
                        // A single Text, never a Label: SurvivorButton's style
                        // body adds .isButton and that trait propagates into a
                        // Label's separate parts, publishing each as its own
                        // button element.
                        Text(Image(systemName: "shield.slash.fill"))
                            + Text("  Nullify it")
                    }
                }
                .buttonStyle(.survivor)
                .disabled(isActing)
                .accessibilityLabel("Nullify the idol")
                .accessibilityAddTraits(.isButton)
                .accessibilityHint("Cancels \(shielded)'s immunity")

                Button("Let it stand") {
                    Task { await decline() }
                }
                .buttonStyle(.survivor(color: .gray))
                .disabled(isActing)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Let it stand")
            }
            .padding(24)
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .padding(28)
            .errorAlert($error)
        }
        .transition(.opacity)
    }

    // MARK: - Idol player

    private func waitingBanner(_ pending: PendingNullifierState) -> some View {
        VStack {
            Spacer()
            HStack(spacing: 8) {
                ProgressView()
                Text("Your idol is on the table — waiting to see if it stands…")
                    .font(.caption)
            }
            .padding(12)
            .background(.regularMaterial)
            .clipShape(Capsule())
            .padding(.bottom, 24)
        }
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    // MARK: - Actions

    private func nullify(_ pending: PendingNullifierState) async {
        guard let target = pending.targetId else { return }
        isActing = true
        defer { isActing = false }
        do {
            try await gameClient.blockImmunity(targetId: target)
            HapticEngine.cardPlay()
        } catch {
            self.error = .from(error)
        }
    }

    private func decline() async {
        isActing = true
        defer { isActing = false }
        do {
            try await gameClient.declineNullifier()
        } catch {
            self.error = .from(error)
        }
    }
}
