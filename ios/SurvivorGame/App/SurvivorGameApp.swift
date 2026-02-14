import SwiftUI
import SwiftData

@main
struct SurvivorGameApp: App {
    let modelContainer: ModelContainer
    
    @State private var gameClient: GameClient
    @State private var modelContainerError: Error?

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
        _gameClient = State(initialValue: GameClient(baseURL: serverConfig.baseURL))
        
        // Prepare haptic generators for optimal performance
        HapticEngine.prepare()
    }

    var body: some Scene {
        WindowGroup {
            ZStack {
                ContentView()
                    .environment(gameClient)
                
                // Show non-blocking warning if storage is in-memory only
                if modelContainerError != nil {
                    VStack {
                        Spacer()
                        StorageWarningBanner()
                            .padding()
                    }
                }
            }
        }
        .modelContainer(modelContainer)
    }
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
