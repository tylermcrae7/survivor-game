import SwiftUI

struct ConnectionBanner: View {
    @Environment(GameClient.self) private var gameClient

    var body: some View {
        VStack {
            HStack(spacing: 8) {
                ProgressView()
                    .tint(.white)
                Text(gameClient.connectionState.statusText)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.white)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(.red.opacity(0.9))
            .clipShape(Capsule())
            .shadow(radius: 4)

            Spacer()
        }
        .padding(.top, 8)
        .transition(.move(edge: .top).combined(with: .opacity))
    }
}
