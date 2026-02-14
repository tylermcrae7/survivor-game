import SwiftUI

struct ImmunityView: View {
    @Bindable var viewModel: TribalViewModel
    @State private var showNullifierTarget = false

    var body: some View {
        VStack(spacing: 16) {
            Text("Immunity Phase")
                .font(.headline)

            Image(systemName: "shield.fill")
                .font(.system(size: 40))
                .foregroundStyle(.yellow)

            Text("Players may play Hidden Immunity Idols or Idol Nullifiers now.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            if !viewModel.isEliminated {
                // Immunity Idol button
                if viewModel.hasImmunityIdol {
                    Button {
                        Task { await viewModel.playImmunity() }
                    } label: {
                        Label("Play Immunity Idol", systemImage: "shield.fill")
                    }
                    .buttonStyle(.survivor(color: .yellow))
                    .disabled(viewModel.isPerformingAction)
                }

                // Idol Nullifier button
                if viewModel.hasIdolNullifier {
                    Button {
                        showNullifierTarget = true
                    } label: {
                        Label("Play Idol Nullifier", systemImage: "shield.slash.fill")
                    }
                    .buttonStyle(.survivor(color: .purple))
                    .disabled(viewModel.isPerformingAction)
                }

                if !viewModel.hasImmunityIdol && !viewModel.hasIdolNullifier {
                    Text("You have no immunity cards to play.")
                        .foregroundStyle(.secondary)
                        .padding()
                }
            }

            // Show played immunity
            if let played = viewModel.voteState?.immunityPlayed, !played.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Immunity Played")
                        .font(.subheadline.bold())

                    ForEach(played, id: \.self) { playerId in
                        let name = viewModel.gameState?.players[playerId]?.name ?? "Unknown"
                        HStack(spacing: 8) {
                            Image(systemName: "shield.fill")
                                .foregroundStyle(.yellow)
                            Text("\(name) is protected")
                                .font(.caption)
                        }
                    }
                }
                .padding()
                .background(.yellow.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 10))
            }
        }
        .sheet(isPresented: $showNullifierTarget) {
            TargetPickerSheet(
                title: "Nullify Whose Immunity?",
                players: viewModel.activePlayers
            ) { targetId in
                Task { await viewModel.blockImmunity(targetId: targetId) }
            }
        }
    }
}
