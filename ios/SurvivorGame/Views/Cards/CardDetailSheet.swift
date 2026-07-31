import SwiftUI

/// Card sheet: full art-free detail + the play flow. Targeted cards collect
/// their parameters (target, ally+victim, a named card, an RPS throw, a spied
/// card) before the single server call — mirroring the web app's pickers.
struct CardDetailSheet: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(\.dismiss) private var dismiss
    let card: CardInstance
    let index: Int
    let isPlayable: Bool

    @State private var isPlaying = false
    @State private var error: ViewModelError?
    @State private var step: PlayStep = .detail
    @State private var chosenTarget: String?
    @State private var spiedHand: [CardInstance] = []

    private enum PlayStep: Equatable {
        case detail
        case pickTarget(prompt: String)
        case pickAlly(victimId: String)
        case pickThrow(targetId: String)
        case pickCardName(targetId: String)
        case pickSpiedCard(targetId: String)
        case pickPair
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Text(card.cardCategory.displayName.uppercased())
                    .font(.caption.bold())
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
                    .background(card.cardCategory.color)
                    .clipShape(Capsule())

                Text(card.displayName)
                    .font(.title2.bold())
                    .fontDesign(.serif)

                if let desc = card.description {
                    Text(desc)
                        .font(.body)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                }

                VStack(spacing: 8) {
                    if let phases = card.playablePhases, !phases.isEmpty {
                        DetailRow(label: "Playable During",
                                  value: phases.map { formatPhase($0) }.joined(separator: ", "))
                    }
                    if card.reactiveOnly == true {
                        DetailRow(label: "Reactive Only", value: "Yes")
                    }
                }
                .padding()
                .background(.regularMaterial)
                .clipShape(RoundedRectangle(cornerRadius: 12))

                Spacer()

                stepContent
            }
            .padding(24)
            .navigationTitle("Card")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .errorAlert($error)
        }
    }

    // MARK: - Steps

    @ViewBuilder
    private var stepContent: some View {
        switch step {
        case .detail:
            if isPlayable {
                Button {
                    beginPlay()
                } label: {
                    if isPlaying { ProgressView().tint(.white) }
                    else { Text("Play This Card") }
                }
                .buttonStyle(.survivor)
                .disabled(isPlaying)
            } else {
                Text("This card can't be played right now")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

        case .pickTarget(let prompt):
            targetList(prompt: prompt) { target in
                Task { await finishPlayForTarget(target) }
            }

        case .pickAlly(let victimId):
            targetList(prompt: "Choose your ally", excluding: [victimId]) { ally in
                Task { await play(params: ["allyId": ally, "victimId": victimId]) }
            }

        case .pickThrow(let targetId):
            VStack(spacing: 10) {
                Text("Your secret throw").font(.subheadline.bold())
                HStack(spacing: 12) {
                    ForEach(["rock", "paper", "scissors"], id: \.self) { choice in
                        Button(choice.capitalized) {
                            Task { await play(params: ["targetId": targetId, "choice": choice]) }
                        }
                        .buttonStyle(.survivor(color: .teal))
                    }
                }
            }

        case .pickCardName(let targetId):
            cardNameList { named in
                Task { await play(params: ["targetId": targetId, "cardType": named]) }
            }

        case .pickSpiedCard(let targetId):
            VStack(alignment: .leading, spacing: 10) {
                Text("Their hand, laid bare — take one")
                    .font(.subheadline.bold())
                ScrollView {
                    ForEach(Array(spiedHand.enumerated()), id: \.offset) { i, spied in
                        let resolved = CardCatalog.shared.resolve(spied)
                        let locked = spied.type == "vote"
                        Button {
                            Task { await play(params: ["targetId": targetId, "takeIndex": i]) }
                        } label: {
                            HStack {
                                Text(resolved.displayName)
                                Spacer()
                                if locked {
                                    Text("out of reach").font(.caption).foregroundStyle(.secondary)
                                }
                            }
                            .padding(10)
                            .background(.regularMaterial)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                        }
                        .buttonStyle(.plain)
                        .disabled(locked)
                    }
                }
                .frame(maxHeight: 260)
            }

        case .pickPair:
            pairPicker
        }
    }

    private func targetList(
        prompt: String, excluding: [String] = [],
        onPick: @escaping (String) -> Void
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(prompt).font(.subheadline.bold())
            ForEach(eligibleTargets.filter { !excluding.contains($0.id) }) { player in
                Button {
                    onPick(player.id)
                } label: {
                    HStack {
                        Circle().fill(player.swiftUIColor).frame(width: 14, height: 14)
                        Text(player.name)
                        Spacer()
                        Text("\(player.handCount)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Image(systemName: "rectangle.portrait.on.rectangle.portrait")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .padding(10)
                    .background(.regularMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
                .disabled(isPlaying)
            }
        }
    }

    @State private var pairSelection: Set<String> = []

    private var pairPicker: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Pick the pair (2 players)").font(.subheadline.bold())
            ForEach(eligibleTargets) { player in
                Button {
                    if pairSelection.contains(player.id) { pairSelection.remove(player.id) }
                    else if pairSelection.count < 2 { pairSelection.insert(player.id) }
                } label: {
                    HStack {
                        Image(systemName: pairSelection.contains(player.id)
                              ? "checkmark.circle.fill" : "circle")
                        Text(player.name)
                        Spacer()
                    }
                    .padding(10)
                    .background(.regularMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
            }
            Button("Call the Power Pair") {
                Task { await play(params: ["targetIds": Array(pairSelection)]) }
            }
            .buttonStyle(.survivor)
            .disabled(pairSelection.count != 2 || isPlaying)
        }
    }

    private func cardNameList(onPick: @escaping (String) -> Void) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Text("Name the card you demand").font(.subheadline.bold())
                let nameable = CardCatalog.shared.cards.values
                    .filter { $0.cardCategory != .tribalCouncil && $0.type != "vote" }
                    .sorted { $0.displayName < $1.displayName }
                ForEach(nameable) { option in
                    Button {
                        onPick(option.type)
                    } label: {
                        HStack {
                            Text(option.displayName)
                            Spacer()
                            Text(option.cardCategory.displayName)
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                        .padding(8)
                        .background(.regularMaterial)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .frame(maxHeight: 280)
    }

    // MARK: - Flow control

    private var eligibleTargets: [PlayerState] {
        let me = gameClient.playerId
        return gameClient.gameState?.activePlayers.filter { $0.id != me } ?? []
    }

    private func beginPlay() {
        switch card.type {
        case "camp_raid":
            step = .pickTarget(prompt: "Set the trap on whose camp?")
        case "inheritance":
            step = .pickTarget(prompt: "When THEY are eliminated, you inherit")
        case "the_spy_shack":
            step = .pickTarget(prompt: "Spy on whose camp?")
        case "knowledge_is_power":
            step = .pickTarget(prompt: "Demand a card from…")
        case "lets_form_an_alliance":
            step = .pickTarget(prompt: "Raid whose camp? (your victim)")
        case "reward_challenge_do_or_die":
            step = .pickTarget(prompt: "Challenge who to Do Or Die?")
        case "reward_challenge_power_pair":
            step = .pickPair
        case "control_the_vote", "goodwill_gamble", "grant_immunity",
             "idol_nullifier", "steal_vote", "block_vote":
            step = .pickTarget(prompt: "Choose a player")
        default:
            // No parameters — play straight away (numbers game, challenges,
            // extra vote at tribal, leader-now, immunity idol via its screen…)
            Task { await play(params: [:]) }
        }
    }

    private func finishPlayForTarget(_ target: String) async {
        switch card.type {
        case "the_spy_shack":
            await spyOn(target)
        case "knowledge_is_power":
            step = .pickCardName(targetId: target)
        case "lets_form_an_alliance":
            step = .pickAlly(victimId: target)
        case "reward_challenge_do_or_die":
            step = .pickThrow(targetId: target)
        default:
            await play(params: ["targetId": target])
        }
    }

    /// You see everything — that is the card. The target's hand is already in
    /// the state every phone receives, so the picker reads it directly and the
    /// play happens as ONE call with the chosen takeIndex (mirrors the web).
    private func spyOn(_ target: String) async {
        let hand = gameClient.gameState?.players[target]?.hand ?? []
        guard !hand.isEmpty else {
            await play(params: ["targetId": target])   // server words the refusal
            return
        }
        spiedHand = hand
        step = .pickSpiedCard(targetId: target)
    }

    private func play(params: [String: Any]) async {
        isPlaying = true
        defer { isPlaying = false }
        do {
            nonisolated(unsafe) let paramsCopy = params
            let response = try await gameClient.playCard(at: index, params: paramsCopy)
            guard response.success else {
                // A refusal is the server enforcing the rules — say why, stay open
                self.error = .gameError(response.message ?? "The island refused that play")
                step = .detail
                return
            }
            HapticEngine.cardPlay()
            dismiss()
        } catch {
            self.error = .from(error)
            step = .detail
        }
    }

    private func formatPhase(_ phase: String) -> String {
        phase.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

private struct DetailRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.caption.bold())
        }
    }
}
