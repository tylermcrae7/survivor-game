import SwiftUI

struct PlayerSetupView: View {
    @Binding var playerName: String
    @Binding var selectedColor: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Eyebrow: torch small caps trailed by a fading rule.
            HStack(spacing: 10) {
                Text("player setup")
                    .font(Torch.Font.label(Torch.TextSize.xs))
                    .tracking(Torch.Track.wide * Torch.TextSize.xs)
                    .foregroundStyle(Torch.Color.torch)
                    .fixedSize()
                LinearGradient(colors: [Torch.Color.torch.opacity(0.5), .clear],
                               startPoint: .leading, endPoint: .trailing)
                    .frame(height: 1)
            }

            TextField("Your Name", text: $playerName,
                      prompt: Text("Your Name")
                          .foregroundStyle(Torch.Color.textFaint))
                .textFieldStyle(.plain)
                .font(Torch.Font.body())
                .foregroundStyle(Torch.Color.text)
                .tint(Torch.Color.torch)
                .textInputAutocapitalization(.words)
                .frame(minHeight: Torch.Spacing.touchTarget)
                .padding(.horizontal, 14)
                .background(
                    RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                        .fill(Torch.Color.surfaceSunken)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                        .strokeBorder(Torch.Color.lineStrong, lineWidth: 1)
                )
                .accessibilityIdentifier("player-name")

            VStack(alignment: .leading, spacing: 8) {
                Text("choose color")
                    .font(Torch.Font.label(Torch.TextSize.xs))
                    .tracking(Torch.Track.label * Torch.TextSize.xs)
                    .foregroundStyle(Torch.Color.textSecondary)

                LazyVGrid(
                    columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 5),
                    spacing: 12
                ) {
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
        .torchCard()
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
                    // Bottom-shaded sphere, like the web swatches.
                    .fill(color.shadow(.inner(color: .black.opacity(0.3), radius: 6, y: -3)))
                    .frame(width: 36, height: 36)
                    .overlay {
                        Circle()
                            .strokeBorder(.black.opacity(0.4), lineWidth: 2)
                    }
                    .overlay {
                        if isSelected {
                            Image(systemName: "checkmark")
                                .font(.system(size: 13, weight: .heavy))
                                .foregroundStyle(.white)
                                .shadow(color: .black.opacity(0.5), radius: 1)
                        }
                    }
                    .background {
                        if isSelected {
                            // The offset torch ring around the selected swatch.
                            Circle()
                                .stroke(Torch.Color.torch, lineWidth: 2)
                                .frame(width: 46, height: 46)
                        }
                    }
                    .scaleEffect(isSelected ? 1.1 : 1)
                    .torchGlow(isSelected ? 0.5 : 0, radius: 6)

                Text(label)
                    .font(Torch.Font.label(10, weight: isSelected ? .bold : .medium))
                    .foregroundStyle(isSelected ? Torch.Color.parchment : Torch.Color.textSecondary)
            }
        }
        .buttonStyle(.plain)
    }
}
