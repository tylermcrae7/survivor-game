import SwiftUI

/// Who is that, and what are they holding?
///
/// A coloured disc with initials in it identifies a castaway only as long as no
/// two of them start with the same letter, and the camp strip truncates names
/// at 60pt anyway. Tapping a player opens this: their full name, the torches
/// they have left, how many cards they're holding, and where they wandered off
/// to. Nothing here is secret — every field is already on every screen
/// somewhere; this just puts them in one place, attached to the face.
@Observable
@MainActor
final class PlayerInspector {
    /// The id, deliberately not a snapshot: the sheet re-reads live state, so
    /// lives and hand counts move while it's open, and it closes itself if the
    /// player leaves the game.
    var playerId: String?
}

struct PlayerDetailSheet: View {
    let playerId: String
    @Environment(GameClient.self) private var gameClient
    @Environment(\.dismiss) private var dismiss

    private var player: PlayerState? { gameClient.gameState?.players[playerId] }

    var body: some View {
        Group {
            if let player {
                content(player)
            } else {
                // They left, or the game reset out from under the sheet.
                ContentUnavailableView("They've left the island",
                                       systemImage: "person.slash")
            }
        }
        .presentationDetents([.height(360), .medium])
        .presentationDragIndicator(.visible)
    }

    private func content(_ player: PlayerState) -> some View {
        let isMe = player.id == gameClient.playerId
        let hasNecklace = gameClient.gameState?.necklaceHolder == player.id
        let isJury = gameClient.gameState?.jury?.contains(player.id) ?? false

        return ScrollView {
            VStack(spacing: Torch.Spacing.md) {
                PlayerAvatarView(player: player, size: 76, showName: false)
                    .padding(.top, 8)

                VStack(spacing: 2) {
                    Text(player.name)
                        .font(Torch.Font.display(Torch.TextSize.displaySM, weight: 700))
                        .foregroundStyle(Torch.Color.parchment)
                        .multilineTextAlignment(.center)
                    if isMe {
                        Text("that's you")
                            .font(Torch.Font.label(Torch.TextSize.xs))
                            .tracking(Torch.Track.label * Torch.TextSize.xs)
                            .foregroundStyle(Torch.Color.torch)
                    } else if player.isBot {
                        Text("a computer castaway")
                            .font(Torch.Font.body(Torch.TextSize.xs))
                            .foregroundStyle(Torch.Color.textSecondary)
                    }
                }

                VStack(spacing: 0) {
                    detailRow("Torches", systemImage: "flame.fill") {
                        TorchLivesView(lives: player.characterCards)
                    }
                    Divider().overlay(Torch.Color.line)
                    detailRow("Cards in hand", systemImage: "rectangle.stack") {
                        Text("\(player.handCount)")
                            .font(Torch.Font.body(Torch.TextSize.base, weight: .bold).monospacedDigit())
                            .foregroundStyle(Torch.Color.text)
                    }
                    if let place = Place(rawValue: player.placeKey) {
                        Divider().overlay(Torch.Color.line)
                        detailRow("Standing at", systemImage: place.symbolName) {
                            Text(place.label)
                                .font(Torch.Font.body(Torch.TextSize.base))
                                .foregroundStyle(Torch.Color.text)
                        }
                    }
                }
                .padding(.vertical, 4)
                .background(
                    RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                        .fill(Torch.Color.surfaceSunken)
                )

                if !badges(player, hasNecklace: hasNecklace, isJury: isJury).isEmpty {
                    FlowRow(badges(player, hasNecklace: hasNecklace, isJury: isJury))
                }
            }
            .padding(Torch.Spacing.md)
        }
        // The camp's night, not the council's red. This sheet opens from every
        // screen, and CouncilBackground's low red fire made it look like a
        // tribal council had leaked into the middle of an ordinary turn.
        .background(TorchNightBackground(radialColor: Torch.Color.torch.opacity(0.14),
                                         showEmbers: false)
            .ignoresSafeArea())
    }

    /// Internal rather than private so `IdolNullificationTests` can pin the
    /// label flip directly, the same way `VoteBarScale`/`IdolProtectionCopy`
    /// are tested — without standing up the whole sheet.
    func badges(_ player: PlayerState,
                hasNecklace: Bool, isJury: Bool) -> [(String, String, Color)] {
        var out: [(String, String, Color)] = []
        if player.isCouncilLeader {
            out.append(("Council Leader", "crown.fill", Torch.Color.juryGold))
        }
        if hasNecklace {
            out.append(("Wears the Necklace", "shield.lefthalf.filled", Torch.Color.juryGold))
        }
        if player.immunityIdolProtection {
            // The flag itself never clears once a nullifier answers it —
            // idolNullified is the only signal this badge would otherwise be
            // advertising a protection that no longer exists.
            if player.idolNullified {
                out.append(("Idol Nullified — Votes Count", "shield.slash", Torch.Color.danger))
            } else {
                out.append(("Protected by an Idol", "shield.fill", Torch.Color.juryGold))
            }
        }
        if player.isEliminated {
            out.append((isJury ? "On the jury" : "Torch snuffed",
                        "flame", Torch.Color.danger))
        }
        return out
    }

    @ViewBuilder
    private func detailRow<Trailing: View>(
        _ title: String, systemImage: String,
        @ViewBuilder trailing: () -> Trailing
    ) -> some View {
        HStack(spacing: 10) {
            Image(systemName: systemImage)
                .font(.caption)
                .foregroundStyle(Torch.Color.textSecondary)
                .frame(width: 18)
                .accessibilityHidden(true)
            Text(title)
                .font(Torch.Font.body(Torch.TextSize.sm))
                .foregroundStyle(Torch.Color.textSecondary)
            Spacer()
            trailing()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }
}

/// Badges wrap rather than truncate — a player can hold several at once.
private struct FlowRow: View {
    let items: [(String, String, Color)]

    init(_ items: [(String, String, Color)]) { self.items = items }

    var body: some View {
        VStack(spacing: 8) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(spacing: 8) {
                    Image(systemName: item.1)
                        .font(.caption)
                        .accessibilityHidden(true)
                    Text(item.0)
                        .font(Torch.Font.body(Torch.TextSize.xs, weight: .semibold))
                    Spacer()
                }
                .foregroundStyle(item.2)
                .padding(.horizontal, 12)
                .padding(.vertical, 9)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                        .fill(item.2.opacity(0.10))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                        .strokeBorder(item.2.opacity(0.35), lineWidth: 1)
                )
                .accessibilityElement(children: .combine)
                .accessibilityLabel(item.0)
            }
        }
    }
}
