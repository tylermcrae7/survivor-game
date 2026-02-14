import SwiftUI

struct PhaseProgressView: View {
    let phases: [String]
    let currentIndex: Int

    var body: some View {
        HStack(spacing: 4) {
            ForEach(Array(phases.enumerated()), id: \.offset) { index, phase in
                VStack(spacing: 4) {
                    Circle()
                        .fill(index <= currentIndex ? Color.orange : Color.secondary.opacity(0.3))
                        .frame(width: 8, height: 8)

                    Text(phase)
                        .font(.caption2)
                        .foregroundStyle(index <= currentIndex ? .primary : .secondary)
                }

                if index < phases.count - 1 {
                    Rectangle()
                        .fill(index < currentIndex ? Color.orange : Color.secondary.opacity(0.3))
                        .frame(height: 2)
                        .frame(maxWidth: .infinity)
                        .padding(.bottom, 16)
                }
            }
        }
        .padding(.horizontal)
    }
}
