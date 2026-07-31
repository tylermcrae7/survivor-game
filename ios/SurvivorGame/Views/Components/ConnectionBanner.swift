import SwiftUI

struct ConnectionBanner: View {
    @Environment(GameClient.self) private var gameClient

    // The 3s REST poll keeps the table breathing while the socket is down,
    // so a lost connection lags — it doesn't stop the game.
    private var bannerText: String {
        gameClient.connectionState == .disconnected
            ? "Connection lost — updates may lag"
            : gameClient.connectionState.statusText
    }

    var body: some View {
        VStack {
            HStack(spacing: 8) {
                ProgressView()
                    .tint(.white)
                Text(bannerText)
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
