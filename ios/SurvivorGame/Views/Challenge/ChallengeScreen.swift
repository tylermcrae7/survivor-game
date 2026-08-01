import SwiftUI

/// A running Let's Go To Rocks Challenge — the orange-card minigames. The
/// server drives the whole state machine; this screen renders the public
/// challenge state and sends one action at a time, exactly like the web panel.
struct ChallengeScreen: View {
    @Environment(GameClient.self) private var gameClient
    @State private var pullCount = 1
    @State private var bidAmount = 1
    @State private var isActing = false
    @State private var error: ViewModelError?

    private var challenge: ChallengeState? { gameClient.gameState?.challenge }
    private var players: [String: PlayerState] { gameClient.gameState?.players ?? [:] }
    private var isMyMove: Bool { challenge?.currentPlayerId == gameClient.playerId }

    private var title: String {
        switch challenge?.type {
        case "lowest_score_loses": return "Lowest Score Loses"
        case "highest_bidder": return "Highest Bidder"
        case "one_now_or_two_later": return "1 Now or 2 Later"
        case "pull_or_steal": return "Pull or Steal"
        default:
            return (challenge?.type ?? "Challenge")
                .replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    var body: some View {
        if let challenge, !challenge.isComplete {
            ZStack {
                SurvivorTheme.Background()

                ScrollView {
                    VStack(spacing: 18) {
                        VStack(spacing: 4) {
                            Text("The Challenge")
                                .font(.caption.weight(.semibold))
                                .tracking(3)
                                .foregroundStyle(SurvivorTheme.ember)
                            Text(title)
                                .font(.title.weight(.black))
                                .fontDesign(.serif)
                        }
                        .padding(.top, 8)

                        if let prompt = challenge.prompt {
                            Text(prompt)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal)
                        }

                        if let currentId = challenge.currentPlayerId,
                           let current = players[currentId] {
                            SurvivorChip {
                                Circle().fill(current.swiftUIColor).frame(width: 10, height: 10)
                                Text(isMyMove ? "Your move" : "\(current.name) is up")
                            }
                        }

                        if isMyMove {
                            actionPanel(challenge)
                        } else {
                            ProgressView()
                                .padding(.vertical, 8)
                        }

                        if let scores = challenge.scores, !scores.isEmpty {
                            scoreBoard(scores)
                        }

                        if let log = challenge.log, !log.isEmpty {
                            logPanel(log)
                        }
                    }
                    .padding(20)
                }
            }
            .errorAlert($error)
        }
    }

    // MARK: - Actions

    @ViewBuilder
    private func actionPanel(_ challenge: ChallengeState) -> some View {
        let actions = challenge.actions ?? []
        VStack(spacing: 12) {
            if actions.contains("pull") {
                if challenge.type == "lowest_score_loses" {
                    // Secret pull 0…maxPull (an empty bag is a legal pretend-pull)
                    let ceiling = max(0, challenge.maxPull ?? 2)
                    Stepper(value: $pullCount, in: 0...max(0, ceiling)) {
                        Text("Pull \(pullCount) rock\(pullCount == 1 ? "" : "s")")
                            .font(.headline)
                    }
                    .onAppear { pullCount = min(pullCount, ceiling) }
                    Button("Reach into the bag") {
                        act("pull", value: .int(pullCount))
                    }
                    .buttonStyle(.survivor)
                } else {
                    Button("Pull from the bag") {
                        act("pull", value: nil)
                    }
                    .buttonStyle(.survivor)
                }
            }

            if actions.contains("bid") {
                Stepper(value: $bidAmount, in: 1...20) {
                    Text("Bid \(bidAmount)").font(.headline)
                }
                Button("Place the bid") {
                    act("bid", value: .int(bidAmount))
                }
                .buttonStyle(.survivor)
            }

            if actions.contains("pass") {
                Button("Pass the bag") {
                    act("pass", value: nil)
                }
                .buttonStyle(.survivorSecondary)
            }

            if actions.contains("steal"), let targets = challenge.stealTargets,
               !targets.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("…or steal a rock")
                        .font(.subheadline.bold())
                    ForEach(targets, id: \.self) { targetId in
                        if let target = players[targetId] {
                            Button {
                                act("steal", value: .string(targetId))
                            } label: {
                                HStack {
                                    Circle().fill(target.swiftUIColor)
                                        .frame(width: 12, height: 12)
                                    Text(target.name)
                                    Spacer()
                                    Image(systemName: "hand.raised.fill")
                                        .foregroundStyle(.red)
                                }
                                .padding(10)
                                .background(.regularMaterial)
                                .clipShape(RoundedRectangle(cornerRadius: 10))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }

            if isActing { ProgressView() }
        }
        .disabled(isActing)
    }

    private func scoreBoard(_ scores: [String: Int]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("The Reveal")
                .font(.subheadline.bold())
            ForEach(scores.sorted { $0.value > $1.value }, id: \.key) { id, score in
                HStack {
                    Text(players[id]?.name ?? "?")
                    Spacer()
                    Text("\(score >= 0 ? "+" : "")\(score)")
                        .font(.body.monospacedDigit().bold())
                        .foregroundStyle(score >= 0 ? SurvivorTheme.ember : .red)
                }
                .font(.subheadline)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func logPanel(_ log: [String]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Around the fire")
                .font(.caption.bold())
                .foregroundStyle(.secondary)
            ForEach(Array(log.suffix(6).enumerated()), id: \.offset) { _, line in
                Text(line)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(SurvivorTheme.inkRaised.opacity(0.7))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func act(_ action: String, value: ChallengeValue?) {
        isActing = true
        Task {
            defer { isActing = false }
            do {
                try await gameClient.challengeAction(action, value: value)
                HapticEngine.impact(.medium)
            } catch {
                self.error = .from(error)
            }
        }
    }
}
