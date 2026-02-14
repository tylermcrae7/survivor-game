import SwiftUI
import SwiftData

struct StartScreen: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(\.modelContext) private var modelContext
    @State private var viewModel: StartViewModel?
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            if let vm = viewModel {
                StartContent(viewModel: vm)
                    .navigationTitle("Survivor")
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button {
                                showSettings = true
                            } label: {
                                Image(systemName: "gearshape")
                            }
                            .accessibilityLabel("Settings")
                            .accessibilityHint("Open server settings")
                        }
                    }
                    .sheet(isPresented: $showSettings) {
                        ServerSettingsSheet(viewModel: vm)
                    }
            } else {
                ProgressView()
            }
        }
        .onAppear {
            if viewModel == nil {
                let vm = StartViewModel(gameClient: gameClient)
                vm.loadSavedConfig(from: modelContext)
                viewModel = vm
            }
        }
    }
}

private struct StartContent: View {
    @Bindable var viewModel: StartViewModel

    var body: some View {
        ScrollView {
            VStack(spacing: 32) {
                // Logo area
                VStack(spacing: 8) {
                    Image(systemName: "flame.fill")
                        .font(.system(size: 64))
                        .foregroundStyle(.orange)
                    Text("Survivor")
                        .font(.largeTitle.bold())
                    Text("The Board Game")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 20)

                // Player setup
                PlayerSetupView(
                    playerName: $viewModel.playerName,
                    selectedColor: $viewModel.preferredColor
                )

                // Actions
                VStack(spacing: 12) {
                    Button("Create Game") {
                        Task { await viewModel.createGame() }
                    }
                    .buttonStyle(.survivor)
                    .disabled(viewModel.loadingState.isLoading)
                    .accessibilityLabel("Create new game")
                    .accessibilityHint("Creates a new game and generates a code for other players to join")

                    HStack {
                        Rectangle()
                            .frame(height: 1)
                            .foregroundStyle(.secondary.opacity(0.3))
                        Text("OR")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Rectangle()
                            .frame(height: 1)
                            .foregroundStyle(.secondary.opacity(0.3))
                    }

                    HStack(spacing: 12) {
                        TextField("Game Code", text: $viewModel.joinCode)
                            .textFieldStyle(.roundedBorder)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled()
                            .accessibilityLabel("Game code")
                            .accessibilityHint("Enter the game code provided by the host")

                        Button("Join") {
                            Task { await viewModel.joinGame() }
                        }
                        .buttonStyle(.survivor(color: .teal))
                        .disabled(viewModel.loadingState.isLoading)
                        .accessibilityLabel("Join game")
                        .accessibilityHint("Join an existing game using the code above")
                    }
                }

                if viewModel.loadingState.isLoading {
                    ProgressView("Connecting...")
                }
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 40)
        }
        .errorAlert($viewModel.error)
    }
}

private struct ServerSettingsSheet: View {
    @Bindable var viewModel: StartViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var connectionOk: Bool?

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("Server URL", text: $viewModel.serverURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)

                    Button("Test Connection") {
                        Task {
                            connectionOk = await viewModel.testConnection()
                        }
                    }

                    if let ok = connectionOk {
                        Label(
                            ok ? "Connected" : "Failed",
                            systemImage: ok ? "checkmark.circle.fill" : "xmark.circle.fill"
                        )
                        .foregroundStyle(ok ? .green : .red)
                    }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

// Color extension for named colors
private extension Color {
    static let teal = Color(hex: "#4ECDC4")
}
