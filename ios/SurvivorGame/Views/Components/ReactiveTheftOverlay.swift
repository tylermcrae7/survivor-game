import SwiftUI

/// The Sorry-For-You window. When a steal targets a player holding Sorry For
/// You, the server pauses the theft until the defender answers — and if no UI
/// resolves the window, the whole game wedges. The web app learned that the
/// hard way; this is its native twin.
///
///  · the DEFENDER gets a blocking raid dialog: play the card, or let it happen
///  · the THIEF sees a waiting banner naming who they're waiting on
///  · everyone else sees nothing
struct ReactiveTheftOverlay: View {
    @Environment(GameClient.self) private var gameClient
    @State private var isActing = false
    @State private var error: ViewModelError?

    private var pending: PendingTheftState? {
        let theft = gameClient.gameState?.pendingTheft
        return theft?.reactiveWindowOpen == true ? theft : nil
    }

    private var players: [String: PlayerState] { gameClient.gameState?.players ?? [:] }

    private var thiefNames: String {
        (pending?.allThiefIds ?? [])
            .compactMap { players[$0]?.name }
            .joined(separator: " and ")
    }

    var body: some View {
        if let pending {
            let me = gameClient.playerId
            if pending.targetId == me {
                defenderDialog(pending)
            } else if pending.allThiefIds.contains(me ?? "") {
                thiefBanner(pending)
            }
        }
    }

    // MARK: - Defender

    private func defenderDialog(_ pending: PendingTheftState) -> some View {
        let holdsSorry = gameClient.myPlayer?.hand.contains { $0.type == "sorry_for_you" } ?? false
        let source = pending.source ?? "A raid"

        return ZStack {
            Color.black.opacity(0.65).ignoresSafeArea()

            VStack(spacing: 16) {
                Text("A Raid On Your Camp")
                    .font(.title2.bold())
                    .fontDesign(.serif)

                Text("\(thiefNames.isEmpty ? "Someone" : thiefNames) is raiding your camp — \(source).")
                    .font(.subheadline)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)

                if holdsSorry {
                    Text("You're holding Sorry For You — play it and they get nothing (each raider must discard a card), or let them take their prize.")
                        .font(.caption)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)

                    Button {
                        Task { await playSorry() }
                    } label: {
                        if isActing { ProgressView().tint(.white) }
                        else { Label("Sorry for you!", systemImage: "hand.raised.fill") }
                    }
                    .buttonStyle(.survivor)
                    .disabled(isActing)

                    Button("Let them take it") {
                        Task { await letThemTakeIt() }
                    }
                    .buttonStyle(.survivor(color: .gray))
                    .disabled(isActing)
                } else {
                    // No answer to give — acknowledge and the theft resolves
                    Button("Let them take it") {
                        Task { await letThemTakeIt() }
                    }
                    .buttonStyle(.survivor(color: .gray))
                    .disabled(isActing)
                }
            }
            .padding(24)
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .padding(28)
            .errorAlert($error)
        }
        .transition(.opacity)
    }

    // MARK: - Thief

    private func thiefBanner(_ pending: PendingTheftState) -> some View {
        let targetName = pending.targetId.flatMap { players[$0]?.name } ?? "them"
        return VStack {
            Spacer()
            HStack(spacing: 8) {
                ProgressView()
                Text("Waiting on \(targetName) — they may have an answer to your raid…")
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

    private func playSorry() async {
        guard let idx = gameClient.myPlayer?.hand.firstIndex(where: { $0.type == "sorry_for_you" })
        else { return }
        isActing = true
        defer { isActing = false }
        do {
            try await gameClient.playReactiveCard(at: idx, theftContext: [:])
            HapticEngine.cardPlay()
        } catch {
            self.error = .from(error)
        }
    }

    private func letThemTakeIt() async {
        isActing = true
        defer { isActing = false }
        do {
            try await gameClient.completeTheft()
        } catch {
            self.error = .from(error)
        }
    }
}
