import SwiftUI
import SwiftData

struct StartScreen: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(\.modelContext) private var modelContext
    @State private var viewModel: StartViewModel?
    @State private var showSettings = false
    @State private var showCreateOptions = false

    var body: some View {
        NavigationStack {
            if let vm = viewModel {
                StartContent(viewModel: vm)
                    .navigationTitle("")
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
            if let code = gameClient.pendingJoinCode {
                viewModel?.joinCode = code
                gameClient.pendingJoinCode = nil
            }
        }
        .onChange(of: gameClient.pendingJoinCode) { _, code in
            if let code {
                viewModel?.joinCode = code
                gameClient.pendingJoinCode = nil
            }
        }
    }
}

private struct StartContent: View {
    @Bindable var viewModel: StartViewModel

    var body: some View {
        ScrollView {
            VStack(spacing: 32) {
                // The wordmark — same ceremony as the web app
                SurvivorWordmark()
                    .padding(.top, 20)

                // Player setup
                PlayerSetupView(
                    playerName: $viewModel.playerName,
                    selectedColor: $viewModel.preferredColor
                )

                // Actions
                VStack(spacing: 12) {
                    Button("Light the Fire") {
                        showCreateOptions = true
                    }
                    .buttonStyle(.survivor)
                    .disabled(viewModel.loadingState.isLoading)
                    .accessibilityLabel("Create new game")
                    .accessibilityHint("Choose the deck, then create a game with a code others can join")

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
        .sheet(isPresented: $showCreateOptions) {
            CreateGameSheet(viewModel: viewModel)
                .presentationDetents([.medium, .large])
        }
    }

    @State private var showCreateOptions = false
}

/// Choose your deck — the create-time options from the web start screen:
/// Official vs Extended house deck, the Rocks expansion, and the pace this
/// device prefers for its games.
private struct CreateGameSheet: View {
    @Bindable var viewModel: StartViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Deck", selection: $viewModel.deckMode) {
                        Text("Official — the 67-card box").tag("official")
                        Text("Extended — +7 house cards").tag("extended")
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()

                    Toggle("Add Let's Go To Rocks Challenges", isOn: $viewModel.expansion)
                } header: {
                    Text("Choose your deck")
                } footer: {
                    Text("Extended adds Idol Nullifier, Steal A Vote, Block A Vote and Grant Immunity. Rocks adds the 5 Orange Challenge Cards.")
                }

                Section("Pace") {
                    Picker("Computer player speed", selection: $viewModel.botPace) {
                        Text("Chill").tag("chill"); Text("Normal").tag("normal"); Text("Fast").tag("fast")
                    }
                    Picker("Tribal ceremony pace", selection: $viewModel.tribalPace) {
                        Text("Normal").tag("normal"); Text("Relaxed").tag("relaxed"); Text("TV drama").tag("tv")
                    }
                    Picker("Computer player style", selection: $viewModel.botStyle) {
                        Text("Chill").tag("chill"); Text("Normal").tag("normal"); Text("Cutthroat").tag("cutthroat")
                    }
                }

                Section {
                    Button {
                        dismiss()
                        Task { await viewModel.createGame() }
                    } label: {
                        Label("Light the Fire", systemImage: "flame.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.survivor)
                    .listRowBackground(Color.clear)
                }
            }
            .navigationTitle("New Game")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

private struct ServerSettingsSheet: View {
    @Bindable var viewModel: StartViewModel
    @Environment(GameClient.self) private var gameClient
    @Environment(\.dismiss) private var dismiss
    @State private var connectionOk: Bool?
    @State private var islandCode = ""
    @State private var accessResult: String?
    @AppStorage("confirmVotes") private var confirmVotes = false
    @AppStorage("confirmSteals") private var confirmSteals = false
    @AppStorage("hapticsEnabled") private var hapticsEnabled = true

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

                Section {
                    TextField("Island code", text: $islandCode)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Button("Unlock the island") {
                        Task {
                            do {
                                let response = try await gameClient.apiClient.submitAccess(code: islandCode)
                                accessResult = response.success
                                    ? "The island knows you now"
                                    : (response.message ?? "That code was refused")
                            } catch {
                                accessResult = error.localizedDescription
                            }
                        }
                    }
                    .disabled(islandCode.isEmpty)

                    if let accessResult {
                        Text(accessResult)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } header: {
                    Text("Access")
                } footer: {
                    Text("The public island is code-locked. Enter the shared code once; this phone keeps the key.")
                }

                Section {
                    Toggle("Confirm before casting a vote", isOn: $confirmVotes)
                    Toggle("Confirm before stealing", isOn: $confirmSteals)
                    Toggle("Vibration", isOn: $hapticsEnabled)
                } header: {
                    Text("Table manners")
                } footer: {
                    Text("Mistap guards for party tables. A vote can't be taken back once the parchment is in the box.")
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
