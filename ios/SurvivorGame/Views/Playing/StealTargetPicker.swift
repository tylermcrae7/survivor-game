import SwiftUI

struct StealTargetPicker: View {
    let targets: [PlayerState]
    let onSelect: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List(targets) { player in
                Button {
                    HapticEngine.steal()
                    onSelect(player.id)
                    dismiss()
                } label: {
                    HStack(spacing: 12) {
                        PlayerAvatarView(player: player, size: 36, showName: false)

                        VStack(alignment: .leading) {
                            Text(player.name)
                                .font(.body.bold())
                            Text("\(player.handCount) cards")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        Spacer()

                        Image(systemName: "hand.raised.fill")
                            .foregroundStyle(.red)
                    }
                    .padding(.vertical, 4)
                }
                // A stable handle for the row. Matching on "label contains the
                // player's name" is ambiguous now that the camp strip's status
                // cards are buttons carrying the same name — and the strip sits
                // behind this sheet, so the wrong match is unhittable.
                .accessibilityIdentifier("steal-target-\(player.name)")
            }
            .navigationTitle("Steal From")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}
