import SwiftUI

struct PlayerSetupView: View {
    @Binding var playerName: String
    @Binding var selectedColor: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Player Setup")
                .font(.headline)

            TextField("Your Name", text: $playerName)
                .textFieldStyle(.roundedBorder)
                .textInputAutocapitalization(.words)

            VStack(alignment: .leading, spacing: 8) {
                Text("Choose Color")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                HStack(spacing: 12) {
                    // "Auto" option
                    ColorCircle(
                        color: .gray,
                        isSelected: selectedColor == nil,
                        label: "Auto"
                    ) {
                        selectedColor = nil
                        HapticEngine.selection()
                    }

                    ForEach(PlayerColor.allCases, id: \.rawValue) { playerColor in
                        ColorCircle(
                            color: playerColor.color,
                            isSelected: selectedColor == playerColor.rawValue,
                            label: playerColor.displayName
                        ) {
                            selectedColor = playerColor.rawValue
                            HapticEngine.selection()
                        }
                    }
                }
            }
        }
        .padding(16)
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

private struct ColorCircle: View {
    let color: Color
    let isSelected: Bool
    let label: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Circle()
                    .fill(color)
                    .frame(width: 36, height: 36)
                    .overlay {
                        if isSelected {
                            Circle()
                                .strokeBorder(.white, lineWidth: 3)
                        }
                    }
                    .shadow(color: isSelected ? color.opacity(0.5) : .clear, radius: 4)

                Text(label)
                    .font(.caption2)
                    .foregroundStyle(isSelected ? .primary : .secondary)
            }
        }
        .buttonStyle(.plain)
    }
}
