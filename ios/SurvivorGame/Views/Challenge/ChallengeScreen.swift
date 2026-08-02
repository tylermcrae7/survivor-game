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
        if let challenge {
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

                        if challenge.isComplete {
                            // The server parks a finished Challenge until it is
                            // dismissed, and bots refuse to act while a
                            // human-won one sits parked. Unmounting here (the
                            // old behaviour) both hid the win and wedged the
                            // table — so the winner gets their reveal instead.
                            victoryPanel(challenge)
                        } else {
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
                                // Named, so "someone else is up" cannot be
                                // mistaken for "your move is still sending" —
                                // they used to be the same bare spinner.
                                let waitingOn = challenge.currentPlayerId
                                    .flatMap { players[$0]?.name }
                                HStack(spacing: 8) {
                                    ProgressView().controlSize(.small)
                                    Text(waitingOn.map { "Waiting on \($0)…" }
                                         ?? "Waiting on the tribe…")
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                }
                                .padding(.vertical, 8)
                                .accessibilityElement(children: .combine)
                            }

                            if let scores = challenge.scores, !scores.isEmpty {
                                scoreBoard(scores)
                            }
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

    // MARK: - Victory (complete phase)

    /// The win beat: who took it, the final scores where the Challenge kept
    /// any, the Necklace line, and a Continue that clears the parked Challenge
    /// (survivor_server.py `challenge_action` accepts a dismiss from anyone).
    @ViewBuilder
    private func victoryPanel(_ challenge: ChallengeState) -> some View {
        let winner = challenge.winnerId.flatMap { players[$0] }
        let wonNecklace = challenge.winnerId != nil
            && gameClient.gameState?.necklaceHolder == challenge.winnerId

        VStack(spacing: Torch.Spacing.md) {
            Text("The Challenge Is Won")
                .font(Torch.Font.label(Torch.TextSize.xs))
                .tracking(Torch.Track.wide * Torch.TextSize.xs)
                .foregroundStyle(Torch.Color.textSecondary)

            Text(winner?.name ?? "Nobody")
                .font(Torch.Font.display(Torch.TextSize.displayLG, weight: 900,
                                         relativeTo: .largeTitle))
                .foregroundStyle(Torch.Color.parchment)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .shadow(color: Torch.Color.torch.opacity(0.35), radius: 24)

            // The server's completed prompt is exactly "{name} won the
            // Challenge!", so it would only echo the name above — the reward
            // detail lives in the Necklace line and the fireside log.
            if winner != nil {
                Text("won the Challenge")
                    .font(Torch.Font.body(Torch.TextSize.base))
                    .foregroundStyle(Torch.Color.textSecondary)
            } else if let prompt = challenge.prompt, !prompt.isEmpty {
                Text(prompt)
                    .font(Torch.Font.body(Torch.TextSize.base))
                    .foregroundStyle(Torch.Color.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if wonNecklace {
                Label("Wears the Immunity Necklace — nobody can vote for them at the next Tribal Council",
                      systemImage: "shield.lefthalf.filled")
                    .font(Torch.Font.body(Torch.TextSize.sm, weight: .semibold))
                    .foregroundStyle(Torch.Color.juryGold)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                            .fill(Torch.Color.surfaceSunken)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                            .strokeBorder(Torch.Color.juryGold.opacity(0.45), lineWidth: 1)
                    )
            }

            if let scores = challenge.scores, !scores.isEmpty {
                scoreBoard(scores)
            }

            // Lowercase for the style's SF small caps; the a11y label keeps
            // the readable "Continue".
            Button("continue") { dismiss() }
                .buttonStyle(.torchGlow)
                .disabled(isActing)
                .accessibilityLabel("Continue")

            if isActing { ProgressView().tint(Torch.Color.torch) }
        }
        .padding(Torch.Spacing.md)
        .frame(maxWidth: .infinity)
        .torchCard()
    }

    private func dismiss() {
        isActing = true
        Task {
            defer { isActing = false }
            do {
                try await gameClient.dismissChallenge()
                HapticEngine.impact(.medium)
            } catch {
                // Another player's Continue landing first already cleared it —
                // that is the outcome we wanted, not an error to surface.
                if gameClient.gameState?.challenge != nil {
                    self.error = .from(error)
                }
            }
        }
    }

    // MARK: - Actions

    /// Passing means two different things. In Highest Bidder (challenges.py
    /// `_action_highest_bidder`, phase "bidding") you drop out of the bidding;
    /// in 1 Now or 2 Later (`_begin_one_now_round`, phase "choosing") you
    /// decline the pull and hand the bag on.
    private var passLabel: String {
        switch challenge?.type {
        case "highest_bidder": "Pass on bidding"
        case "one_now_or_two_later": "Pass the bag"
        default: "Pass"
        }
    }

    @ViewBuilder
    private func actionPanel(_ challenge: ChallengeState) -> some View {
        let actions = challenge.actions ?? []
        VStack(spacing: 12) {
            // Sits ABOVE the buttons, not below the steal list — down there it
            // was frequently off-screen, so a tap that had been accepted
            // looked identical to one that had been dropped.
            if isActing {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Sending…")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Sending your move")
            }

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
                Button(passLabel) {
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
                            .accessibilityIdentifier("steal-rock-\(target.name)")
                        }
                    }
                }
            }

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
        // A second tap while the first is in flight is a no-op rather than a
        // queued action. The buttons dim now (SurvivorButton finally honours
        // isEnabled), but an impatient double-tap must be harmless regardless.
        guard !isActing else { return }
        // Confirm the tap in the hand *immediately*. The round trip is only
        // 60–90ms, but with no press feedback at all that was long enough to
        // read as "nothing happened" and invite a second tap.
        HapticEngine.impact(.light)
        isActing = true
        Task {
            defer { isActing = false }
            do {
                try await gameClient.challengeAction(action, value: value)
            } catch {
                self.error = .from(error)
            }
        }
    }
}
