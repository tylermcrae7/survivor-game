import SwiftUI

struct ImmunityView: View {
    @Bindable var viewModel: TribalViewModel
    @State private var showShieldTarget = false

    var body: some View {
        VStack(spacing: 16) {
            CeremonyTitle(text: "Immunity Phase", size: Torch.TextSize.displayMD,
                          glow: Torch.Color.juryGold)

            // The necklace moment wears jury gold.
            Image(systemName: "shield.fill")
                .font(.system(size: 40))
                .foregroundStyle(Torch.Color.juryGold)
                .shadow(color: Torch.Color.juryGold.opacity(0.4), radius: 12) // --glow-gold

            Text("Players may play Hidden Immunity Idols or Idol Nullifiers now.")
                .font(Torch.Font.body(Torch.TextSize.sm))
                .foregroundStyle(Torch.Color.textSecondary)
                .multilineTextAlignment(.center)

            if !viewModel.isEliminated {
                // Immunity Idol button
                if viewModel.hasImmunityIdol {
                    Button {
                        Task { await viewModel.playImmunity() }
                    } label: {
                        Label("Play Immunity Idol", systemImage: "shield.fill")
                    }
                    .buttonStyle(.torchGlow)
                    .disabled(viewModel.isPerformingAction)

                    // Your idol can protect an ally instead of you
                    Button {
                        showShieldTarget = true
                    } label: {
                        Label("Shield an ally instead…", systemImage: "person.2.fill")
                            .font(.subheadline)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Torch.Color.textSecondary)
                    .disabled(viewModel.isPerformingAction)
                }

                // No Nullifier button here. A nullifier answers an idol, and
                // the server refuses one until a target actually holds
                // protection — so offering it alongside the idol was offering a
                // move that could not yet be made. It now arrives by itself,
                // the moment there is something to answer
                // (NullifierWindowOverlay).
                if viewModel.hasIdolNullifier {
                    Label("You hold an Idol Nullifier — you'll be offered it if an idol is played.",
                          systemImage: "shield.slash")
                        .font(Torch.Font.body(Torch.TextSize.xs))
                        .foregroundStyle(Torch.Color.textSecondary)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if !viewModel.hasImmunityIdol && !viewModel.hasIdolNullifier {
                    Text("You have no immunity cards to play.")
                        .foregroundStyle(Torch.Color.textSecondary)
                        .padding()
                }
            }

            // Show played immunity
            if let played = viewModel.voteState?.immunityPlayed, !played.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Immunity Played")
                        .font(Torch.Font.label(Torch.TextSize.sm))
                        .tracking(Torch.Track.label * Torch.TextSize.sm)
                        .foregroundStyle(Torch.Color.juryGold)

                    ForEach(Array(played.enumerated()), id: \.offset) { _, record in
                        let players = viewModel.gameState?.players
                        let holder = record.playerId.flatMap { players?[$0]?.name }
                        let shielded = record.targetId.flatMap { players?[$0]?.name }
                            ?? holder ?? "Someone"
                        // Nullification clears protection immediately; this
                        // durable flag explains why the played idol no longer
                        // shields its target.
                        let nullified = record.targetId.flatMap { players?[$0]?.idolNullified } ?? false
                        HStack(spacing: 8) {
                            Image(systemName: nullified ? "shield.slash" : "shield.fill")
                                .foregroundStyle(nullified ? Torch.Color.danger : Torch.Color.juryGold)
                            // An idol may be played for an ally, so name both
                            // when they differ — that is the whole drama of it.
                            Text(IdolProtectionCopy.line(holder: holder, shielded: shielded,
                                                         nullified: nullified))
                                .font(Torch.Font.body(Torch.TextSize.xs))
                                .foregroundStyle(Torch.Color.text)
                            if nullified {
                                Spacer(minLength: 8)
                                // Same capsule construction as the reveal's
                                // "immune" pill (VoteRevealView), inverted into
                                // the danger palette — this is the opposite
                                // news.
                                Text("IDOL NULLIFIED")
                                    .font(Torch.Font.label(Torch.TextSize.xs))
                                    .tracking(Torch.Track.label * Torch.TextSize.xs)
                                    .foregroundStyle(Torch.Color.danger)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(Capsule().fill(Torch.Color.danger.opacity(0.12)))
                                    .overlay(Capsule().strokeBorder(Torch.Color.danger.opacity(0.4),
                                                                    lineWidth: 1))
                            }
                        }
                        .accessibilityElement(children: .combine)
                    }
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                        .fill(Torch.Color.juryGold.opacity(0.1))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                        .strokeBorder(Torch.Color.juryGold.opacity(0.4), lineWidth: 1)
                )
            }
        }
        .sheet(isPresented: $showShieldTarget) {
            TargetPickerSheet(
                title: "Shield Which Ally?",
                players: viewModel.activePlayers.filter { $0.id != viewModel.myPlayerId }
            ) { targetId in
                Task { await viewModel.playImmunity(targetId: targetId) }
            }
        }
    }
}

/// The "Immunity Played" row's label-flip math, pulled out of the view so
/// it's testable without standing up a `TribalViewModel` — mirrors
/// `VoteBarScale` in `VoteRevealView.swift`.
enum IdolProtectionCopy {
    static func line(holder: String?, shielded: String, nullified: Bool) -> String {
        if nullified {
            return "\(shielded)'s idol is nullified — votes count"
        }
        if let holder, holder != shielded {
            return "\(holder) shielded \(shielded)"
        }
        return "\(shielded) is protected"
    }
}
