import SwiftUI
import SwiftData
import UIKit

@main
struct SurvivorGameApp: App {
    let modelContainer: ModelContainer
    
    @State private var gameClient: GameClient
    @State private var modelContainerError: Error?
    /// Which player's card is open, if any. Owned at the root so the sheet is
    /// mounted once and cannot be torn down by the screen underneath it.
    @State private var playerInspector = PlayerInspector()
    @AppStorage("keepAwake") private var keepAwake = false

    init() {
        let schema = Schema([
            CardDefinition.self,
            GameRecord.self,
            ServerConfig.self
        ])
        let config = ModelConfiguration(schema: schema, isStoredInMemoryOnly: false)
        
        // Try to create persistent storage, fall back to in-memory if it fails
        var container: ModelContainer
        var initError: Error?
        
        do {
            container = try ModelContainer(for: schema, configurations: [config])
        } catch {
            // Fallback to in-memory storage if persistent storage fails
            print("⚠️ Failed to create persistent ModelContainer: \(error)")
            print("⚠️ Falling back to in-memory storage")
            initError = error
            
            let memoryConfig = ModelConfiguration(schema: schema, isStoredInMemoryOnly: true)
            container = try! ModelContainer(for: schema, configurations: [memoryConfig])
        }
        
        modelContainer = container
        _modelContainerError = State(initialValue: initError)

        let serverConfig = ServerConfig.loadDefault(from: modelContainer.mainContext)

        // Dev/test override: SURVIVOR_SERVER_URL in the launch environment
        // points the whole app (API + socket) at a scratch server — the sim
        // smoke harness relies on this to never touch the live island.
        var baseURL = serverConfig.baseURL
        if let override = ProcessInfo.processInfo.environment["SURVIVOR_SERVER_URL"],
           let url = URL(string: override) {
            baseURL = url
            serverConfig.baseURL = url
        }
        if let name = ProcessInfo.processInfo.environment["SURVIVOR_PLAYER_NAME"],
           !name.isEmpty {
            serverConfig.playerName = name
        }
#if DEBUG
        // UI tests request a clean first launch, then remove this flag before
        // relaunching to verify that the server-issued access cookie persists.
        if let resetToken = ProcessInfo.processInfo.environment["SURVIVOR_RESET_ACCESS"],
           !resetToken.isEmpty,
           UserDefaults.standard.string(forKey: "lastAccessResetToken") != resetToken {
            // XCUI may carry launch environment across an in-test relaunch.
            // A per-run token makes this destructive test hook strictly once.
            UserDefaults.standard.set(resetToken, forKey: "lastAccessResetToken")
            serverConfig.lastGameId = nil
            serverConfig.lastPlayerId = nil
            try? modelContainer.mainContext.save()
            IslandAccessCookieStore.forget(for: baseURL)
        }
#endif
        _gameClient = State(initialValue: GameClient(
            baseURL: baseURL,
            clearSavedSession: {
                serverConfig.lastGameId = nil
                serverConfig.lastPlayerId = nil
                try? container.mainContext.save()
            }
        ))
        
        // Prepare haptic generators for optimal performance
        HapticEngine.prepare()
    }

    var body: some Scene {
        WindowGroup {
            ZStack {
                ContentView()
                    .environment(gameClient)
                    .environment(playerInspector)
                    .environment(gameClient.narration)
                    .survivorScreen()
                
                // Show non-blocking warning if storage is in-memory only
                if modelContainerError != nil {
                    VStack {
                        Spacer()
                        StorageWarningBanner()
                            .padding()
                    }
                }
            }
            .preferredColorScheme(.dark)
            .tint(Torch.Color.torch)
            .onAppear { updateIdleTimer() }
            .onChange(of: keepAwake) { _, _ in updateIdleTimer() }
            .onChange(of: gameClient.gameId) { _, _ in updateIdleTimer() }
        }
        .modelContainer(modelContainer)
    }

    private func updateIdleTimer() {
        UIApplication.shared.isIdleTimerDisabled = keepAwake && gameClient.gameId != nil
    }
}

extension SurvivorGameApp {
    // The island is dark by design — the whole app runs torchlit.
}

/// Warning banner shown when app is using in-memory storage
private struct StorageWarningBanner: View {
    @State private var isDismissed = false
    
    var body: some View {
        if !isDismissed {
            HStack(spacing: 12) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                
                VStack(alignment: .leading, spacing: 4) {
                    Text("Storage Warning")
                        .font(.headline)
                    Text("Game data will not be saved")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                
                Spacer()
                
                Button {
                    isDismissed = true
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
            }
            .padding()
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .shadow(radius: 4)
            .transition(.move(edge: .bottom).combined(with: .opacity))
        }
    }
}
