import SwiftUI

/// Card sheet: full art-free detail + the play flow. Targeted cards collect
/// their parameters (target, ally+victim, a named card, an RPS throw, a spied
/// card) before the single server call — mirroring the web app's pickers.
/// Chrome is the web's card sheet: 4px category rule, Fraunces title, phase
/// chips, glowing play CTA.
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
        VStack(spacing: 0) {
            // The signature lit edge: full-width category rule at the very top.
            card.cardCategory.torchGradient
                .frame(height: 4)
                .accessibilityHidden(true)

            ScrollView {
                VStack(alignment: .leading, spacing: Torch.Spacing.md) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(card.cardCategory.displayName.lowercased())
                            .font(Torch.Font.label(Torch.TextSize.xs))
                            .tracking(Torch.Track.label * Torch.TextSize.xs)
                            .foregroundStyle(Torch.Color.textFaint)
                        Text(card.displayName)
                            .font(Torch.Font.display(Torch.TextSize.displaySM, weight: 800))
                            .foregroundStyle(Torch.Color.parchment)
                    }
                    .padding(.trailing, 36) // room for the close button

                    if let desc = card.description {
                        Text(desc)
                            .font(Torch.Font.body(Torch.TextSize.base))
                            .foregroundStyle(Torch.Color.text)
                            .lineSpacing(4)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    timingSection

                    stepContent
                        .padding(.top, Torch.Spacing.sm)
                }
                .padding(Torch.Spacing.lg)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(
            // The night ground with the modal's subtle lit top.
            LinearGradient(stops: [
                .init(color: Torch.Color.surfaceRaised, location: 0),
                .init(color: Torch.Color.surface, location: 0.30),
                .init(color: Torch.Color.background, location: 1),
            ], startPoint: .top, endPoint: .bottom)
            .ignoresSafeArea()
        )
        .overlay(alignment: .topTrailing) {
            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark.circle")
                    .font(.system(size: 22))
                    .foregroundStyle(Torch.Color.textSecondary)
            }
            .padding(Torch.Spacing.md)
            .accessibilityLabel("Close")
        }
        .tint(Torch.Color.torch)
        .errorAlert($error)
    }

    // MARK: - Timing ("playable during" phase chips)

    @ViewBuilder
    private var timingSection: some View {
        let phases = (card.playablePhases ?? []).filter { $0 != "reactive_theft" }
        if !phases.isEmpty {
            VStack(alignment: .leading, spacing: Torch.Spacing.sm) {
                Text("playable during")
                    .font(Torch.Font.label(Torch.TextSize.xs))
                    .tracking(Torch.Track.label * Torch.TextSize.xs)
                    .foregroundStyle(Torch.Color.textFaint)
                HStack(spacing: 6) {
                    ForEach(phases, id: \.self) { phase in
                        Text(formatPhase(phase).lowercased())
                            .font(Torch.Font.label(Torch.TextSize.xs))
                            .tracking(Torch.Track.label * Torch.TextSize.xs)
                            .foregroundStyle(Torch.Color.torch)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 2)
                            .overlay(
                                Capsule().strokeBorder(Torch.Color.torch.opacity(0.45),
                                                       lineWidth: 1)
                            )
                    }
                }
            }
        }
    }

    // MARK: - Steps

    @ViewBuilder
    private var stepContent: some View {
        switch step {
        case .detail:
            if card.reactiveOnly == true {
                // Reactive cards never get a play button — they play themselves.
                Text("This card plays itself — when someone tries to raid you, you'll be offered it on the spot.")
                    .font(Torch.Font.body(Torch.TextSize.sm))
                    .foregroundStyle(Torch.Color.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else if isPlayable {
                VStack(spacing: Torch.Spacing.sm) {
                    if card.requiresTarget == true {
                        Text("You'll choose a target next.")
                            .font(Torch.Font.body(Torch.TextSize.xs))
                            .foregroundStyle(Torch.Color.textSecondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    Button {
                        beginPlay()
                    } label: {
                        if isPlaying { ProgressView().tint(Torch.Color.ink) }
                        else { Text("play this card") }
                    }
                    .buttonStyle(.torchGlow)
                    .disabled(isPlaying)
                    .accessibilityHint("Plays \(card.displayName)")
                }
            } else {
                HStack(spacing: 8) {
                    Image(systemName: "hourglass")
                    Text("Not playable right now.")
                }
                .font(Torch.Font.body(Torch.TextSize.sm))
                .foregroundStyle(Torch.Color.textFaint)
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
                Text("Your secret throw")
                    .font(Torch.Font.body(Torch.TextSize.sm, weight: .bold))
                    .foregroundStyle(Torch.Color.parchment)
                HStack(spacing: 12) {
                    ForEach(["rock", "paper", "scissors"], id: \.self) { choice in
                        Button(choice) {
                            Task { await play(params: ["targetId": targetId, "choice": choice]) }
                        }
                        .buttonStyle(.torchSecondary)
                    }
                }
            }
            .frame(maxWidth: .infinity)

        case .pickCardName(let targetId):
            cardNameList { named in
                Task { await play(params: ["targetId": targetId, "cardType": named]) }
            }

        case .pickSpiedCard(let targetId):
            VStack(alignment: .leading, spacing: 10) {
                Text("Their hand, laid bare — take one")
                    .font(Torch.Font.body(Torch.TextSize.sm, weight: .bold))
                    .foregroundStyle(Torch.Color.parchment)
                ForEach(Array(spiedHand.enumerated()), id: \.offset) { i, spied in
                    let resolved = CardCatalog.shared.resolve(spied)
                    let locked = spied.type == "vote"
                    Button {
                        Task { await play(params: ["targetId": targetId, "takeIndex": i]) }
                    } label: {
                        HStack {
                            Text(resolved.displayName)
                                .foregroundStyle(Torch.Color.text)
                            Spacer()
                            if locked {
                                Text("out of reach")
                                    .font(.caption)
                                    .foregroundStyle(Torch.Color.textFaint)
                            }
                        }
                        .torchPickerRow()
                    }
                    .buttonStyle(.plain)
                    .disabled(locked)
                }
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
            Text(prompt)
                .font(Torch.Font.body(Torch.TextSize.sm, weight: .bold))
                .foregroundStyle(Torch.Color.parchment)
            ForEach(eligibleTargets.filter { !excluding.contains($0.id) }) { player in
                Button {
                    onPick(player.id)
                } label: {
                    HStack {
                        Circle().fill(player.swiftUIColor).frame(width: 14, height: 14)
                        Text(player.name)
                            .foregroundStyle(Torch.Color.text)
                        Spacer()
                        Text("\(player.handCount)")
                            .font(.caption)
                            .foregroundStyle(Torch.Color.textSecondary)
                        Image(systemName: "rectangle.portrait.on.rectangle.portrait")
                            .font(.caption2)
                            .foregroundStyle(Torch.Color.textSecondary)
                    }
                    .torchPickerRow()
                }
                .buttonStyle(.plain)
                .disabled(isPlaying)
            }
        }
    }

    @State private var pairSelection: Set<String> = []

    private var pairPicker: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Pick the pair (2 players)")
                .font(Torch.Font.body(Torch.TextSize.sm, weight: .bold))
                .foregroundStyle(Torch.Color.parchment)
            ForEach(eligibleTargets) { player in
                Button {
                    if pairSelection.contains(player.id) { pairSelection.remove(player.id) }
                    else if pairSelection.count < 2 { pairSelection.insert(player.id) }
                } label: {
                    HStack {
                        Image(systemName: pairSelection.contains(player.id)
                              ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(pairSelection.contains(player.id)
                                             ? Torch.Color.torch : Torch.Color.textSecondary)
                        Text(player.name)
                            .foregroundStyle(Torch.Color.text)
                        Spacer()
                    }
                    .torchPickerRow()
                }
                .buttonStyle(.plain)
            }
            Button("call the power pair") {
                Task { await play(params: ["targetIds": Array(pairSelection)]) }
            }
            .buttonStyle(.torchGlow)
            .disabled(pairSelection.count != 2 || isPlaying)
        }
    }

    private func cardNameList(onPick: @escaping (String) -> Void) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Name the card you demand")
                .font(Torch.Font.body(Torch.TextSize.sm, weight: .bold))
                .foregroundStyle(Torch.Color.parchment)
            let nameable = CardCatalog.shared.cards.values
                .filter { $0.cardCategory != .tribalCouncil && $0.type != "vote" }
                .sorted { $0.displayName < $1.displayName }
            ForEach(nameable) { option in
                Button {
                    onPick(option.type)
                } label: {
                    HStack {
                        Text(option.displayName)
                            .foregroundStyle(Torch.Color.text)
                        Spacer()
                        Text(option.cardCategory.displayName)
                            .font(.caption2)
                            .foregroundStyle(Torch.Color.textSecondary)
                    }
                    .torchPickerRow()
                }
                .buttonStyle(.plain)
            }
        }
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

// MARK: - Picker-row chrome

private extension View {
    /// The sheet's picker-row well: white@3% fill, 1px hairline, 48pt target.
    func torchPickerRow() -> some View {
        self
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, minHeight: 48)
            .background(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .fill(Color.white.opacity(0.03))
            )
            .overlay(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .strokeBorder(Torch.Color.line, lineWidth: 1)
            )
            .contentShape(RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous))
    }
}
