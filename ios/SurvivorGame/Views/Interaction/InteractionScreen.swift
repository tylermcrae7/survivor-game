import SwiftUI

/// A Reward Challenge interaction — real multiplayer minigames: Do Or Die's
/// rock-paper-scissors, Power Pair / Numbers Game finger counts. The server
/// referees; participants each submit one secret pick per round.
struct InteractionScreen: View {
    @Environment(GameClient.self) private var gameClient
    @State private var isActing = false
    @State private var error: ViewModelError?

    private var interaction: InteractionState? { gameClient.gameState?.interaction }
    private var players: [String: PlayerState] { gameClient.gameState?.players ?? [:] }
    private var awaitingMe: Bool {
        (interaction?.awaiting ?? []).contains(gameClient.playerId ?? "")
    }

    private var title: String {
        switch interaction?.type {
        case "do_or_die": return "Do Or Die"
        case "power_pair": return "Power Pair"
        case "numbers_game": return "It's a Numbers Game"
        default:
            return (interaction?.type ?? "Reward Challenge")
                .replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    var body: some View {
        if let interaction {
            ZStack {
                SurvivorTheme.Background()

                ScrollView {
                    VStack(spacing: 18) {
                        VStack(spacing: 4) {
                            Text("Reward Challenge")
                                .font(.caption.weight(.semibold))
                                .tracking(3)
                                .foregroundStyle(SurvivorTheme.ember)
                            Text(title)
                                .font(.title.weight(.black))
                                .fontDesign(.serif)
                            if let round = interaction.round, round > 1 {
                                Text("Round \(round)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(.top, 8)

                        if let prompt = interaction.prompt {
                            Text(prompt)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal)
                        }

                        if awaitingMe {
                            pickPanel(interaction)
                        } else {
                            waitingPanel(interaction)
                        }
                    }
                    .padding(20)
                }
            }
            .errorAlert($error)
        }
    }

    // MARK: - Panels

    @ViewBuilder
    private func pickPanel(_ interaction: InteractionState) -> some View {
        switch interaction.phase {
        case "give":
            givePanel
        case "choose_victim":
            chooseVictimPanel
        default:
            typedPickPanel(interaction)
        }
        if isActing { ProgressView() }
    }

    /// A tie / all-match round: hand over one card of your choice. The Vote
    /// Card is never yours to give — the server refuses it, so it's disabled.
    private var givePanel: some View {
        let hand = (gameClient.myPlayer?.hand ?? []).map { CardCatalog.shared.resolve($0) }
        return VStack(alignment: .leading, spacing: 10) {
            Text("Hand over one card").font(.headline)
            ForEach(Array(hand.enumerated()), id: \.offset) { index, card in
                let locked = card.type == "vote"
                Button {
                    act("give", value: index)
                } label: {
                    HStack {
                        Text(card.displayName)
                        Spacer()
                        if locked {
                            Text("stays with you").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .padding(10)
                    .background(.regularMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
                .disabled(locked || isActing)
            }
        }
    }

    /// The Numbers Game winner picks whose camp to raid.
    private var chooseVictimPanel: some View {
        let victims = (gameClient.gameState?.activePlayers ?? [])
            .filter { $0.id != gameClient.playerId }
        return VStack(alignment: .leading, spacing: 10) {
            Text("Steal 2 cards from…").font(.headline)
            ForEach(victims) { player in
                Button {
                    act("steal_from", value: player.id)
                } label: {
                    HStack {
                        Circle().fill(player.swiftUIColor).frame(width: 12, height: 12)
                        Text(player.name)
                        Spacer()
                        Text("\(player.handCount)")
                            .font(.caption).foregroundStyle(.secondary)
                        Image(systemName: "rectangle.portrait.on.rectangle.portrait")
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                    .padding(10)
                    .background(.regularMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
                .disabled(isActing)
            }
        }
    }

    @ViewBuilder
    private func typedPickPanel(_ interaction: InteractionState) -> some View {
        switch interaction.type {
        case "do_or_die":
            VStack(spacing: 10) {
                Text("Your secret throw").font(.headline)
                HStack(spacing: 14) {
                    throwButton("rock", symbol: "mountain.2.fill")
                    throwButton("paper", symbol: "doc.fill")
                    throwButton("scissors", symbol: "scissors")
                }
            }
        case "power_pair":
            fingerPanel(range: 1...3, label: "Show your fingers (1–3)")
        case "numbers_game":
            fingerPanel(range: 1...5, label: "Show your fingers (1–5)")
        default:
            // A future interaction type: give the numbers 1-5 and let the
            // server referee — presence must never strand the player.
            fingerPanel(range: 1...5, label: "Make your pick")
        }
        if isActing { ProgressView() }
    }

    private func throwButton(_ choice: String, symbol: String) -> some View {
        Button {
            act("pick", value: choice)
        } label: {
            VStack(spacing: 6) {
                Image(systemName: symbol).font(.title2)
                Text(choice.capitalized).font(.caption.bold())
            }
            .frame(width: 84, height: 74)
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 14))
        }
        .buttonStyle(.plain)
        .disabled(isActing)
    }

    private func fingerPanel(range: ClosedRange<Int>, label: String) -> some View {
        VStack(spacing: 10) {
            Text(label).font(.headline)
            HStack(spacing: 10) {
                ForEach(Array(range), id: \.self) { number in
                    Button {
                        act("pick", value: number)
                    } label: {
                        Text("\(number)")
                            .font(.title2.bold().monospacedDigit())
                            .frame(width: 54, height: 54)
                            .background(.regularMaterial)
                            .clipShape(Circle())
                    }
                    .buttonStyle(.plain)
                    .disabled(isActing)
                }
            }
        }
    }

    private func waitingPanel(_ interaction: InteractionState) -> some View {
        let waitingNames = (interaction.awaiting ?? [])
            .compactMap { players[$0]?.name }
        return VStack(spacing: 10) {
            ProgressView()
            Text(waitingNames.isEmpty
                 ? "The reveal is coming…"
                 : "Waiting on \(waitingNames.joined(separator: ", "))…")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 12)
    }

    private func act(_ action: String, value: (any Sendable)?) {
        isActing = true
        Task {
            defer { isActing = false }
            do {
                try await gameClient.interactionAct(action, value: value)
                HapticEngine.impact(.medium)
            } catch {
                self.error = .from(error)
            }
        }
    }
}
