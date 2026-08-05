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
                    .navigationTitle("")
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button {
                                showSettings = true
                            } label: {
                                Image(systemName: "gearshape")
                                    .foregroundStyle(Torch.Color.textSecondary)
                            }
                            .accessibilityLabel("Settings")
                            .accessibilityHint("Open server settings")
                        }
                    }
                    .sheet(isPresented: $showSettings) {
                        AppSettingsSheet()
                    }
            } else {
                ProgressView()
                    .tint(Torch.Color.torch)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(TorchNightBackground())
            }
        }
        .tint(Torch.Color.torch)
        .onAppear {
            if viewModel == nil {
                let vm = StartViewModel(gameClient: gameClient)
                vm.loadSavedConfig(from: modelContext)
                viewModel = vm
                if gameClient.accessState == .unlocked {
                    Task { await vm.restoreSavedGameIfNeeded() }
                }
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
        .onChange(of: gameClient.accessState) { _, state in
            if state == .unlocked {
                Task { await viewModel?.restoreSavedGameIfNeeded() }
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
                StaggeredRise(index: 0) {
                    TorchWordmark()
                        .padding(.top, 20)
                }

                // Player setup
                StaggeredRise(index: 1) {
                    PlayerSetupView(
                        playerName: $viewModel.playerName,
                        selectedColor: $viewModel.preferredColor
                    )
                }

                // Actions
                StaggeredRise(index: 2) {
                    VStack(spacing: 12) {
                        Button("Light the Fire") {
                            showCreateOptions = true
                        }
                        .buttonStyle(.torchGlow)
                        .disabled(viewModel.loadingState.isLoading)
                        .accessibilityLabel("Create new game")
                        .accessibilityHint("Choose the deck, then create a game with a code others can join")
                        .accessibilityIdentifier("create-game-button")

                        HStack {
                            Rectangle()
                                .frame(height: 1)
                                .foregroundStyle(Torch.Color.line)
                            Text("or")
                                .font(Torch.Font.label(Torch.TextSize.xs))
                                .tracking(Torch.Track.label * Torch.TextSize.xs)
                                .foregroundStyle(Torch.Color.textFaint)
                            Rectangle()
                                .frame(height: 1)
                                .foregroundStyle(Torch.Color.line)
                        }

                        HStack(spacing: 12) {
                            // The game-code input: small caps, wide-tracked.
                            TextField("Game Code", text: $viewModel.joinCode,
                                      prompt: Text("game code")
                                          .foregroundStyle(Torch.Color.textFaint))
                                .font(Torch.Font.label(Torch.TextSize.sm))
                                .tracking(0.3 * Torch.TextSize.sm)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .torchField()
                                .accessibilityLabel("Game code")
                                .accessibilityHint("Enter the game code provided by the host")

                            Button("Join") {
                                Task { await viewModel.joinGame() }
                            }
                            .buttonStyle(.torchGlow)
                            .frame(width: 108)
                            .disabled(viewModel.loadingState.isLoading)
                            .accessibilityLabel("Join game")
                            .accessibilityHint("Join an existing game using the code above")
                        }

                        Button {
                            showHallOfFame = true
                        } label: {
                            Label("Hall of Fame", systemImage: "crown")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.torchSecondary)
                    }
                }

                if viewModel.loadingState.isLoading {
                    ProgressView("Connecting...")
                        .tint(Torch.Color.torch)
                        .font(Torch.Font.label(Torch.TextSize.xs))
                        .tracking(Torch.Track.wide * Torch.TextSize.xs)
                        .foregroundStyle(Torch.Color.textSecondary)
                }
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 40)
        }
        .background(TorchNightBackground())
        .errorAlert($viewModel.error)
        .sheet(isPresented: $showCreateOptions) {
            CreateGameSheet(viewModel: viewModel)
                .presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showHallOfFame) {
            HallOfFameView()
        }
    }

    @State private var showCreateOptions = false
    @State private var showHallOfFame = false
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
                        Text("Extended — +6 house cards").tag("extended")
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()

                    Toggle("Add Let's Go To Rocks Challenges", isOn: $viewModel.expansion)
                        .tint(Torch.Color.emberDeep)
                } header: {
                    Text("choose your deck")
                        .font(Torch.Font.label(Torch.TextSize.xs))
                        .tracking(Torch.Track.wide * Torch.TextSize.xs)
                        .foregroundStyle(Torch.Color.torch)
                        .textCase(nil)
                } footer: {
                    Text("Extended adds Idol Nullifier, Steal A Vote and Block A Vote. Rocks adds the 5 Orange Challenge Cards.")
                        .font(Torch.Font.body(Torch.TextSize.xs))
                        .foregroundStyle(Torch.Color.textSecondary)
                }
                .listRowBackground(Torch.Color.surfaceRaised)

                Section {
                    Picker("Computer player speed", selection: $viewModel.botPace) {
                        Text("Chill").tag("chill"); Text("Normal").tag("normal"); Text("Fast").tag("fast")
                    }
                    Picker("Tribal ceremony pace", selection: $viewModel.tribalPace) {
                        Text("Normal").tag("normal"); Text("Relaxed").tag("relaxed"); Text("TV drama").tag("tv")
                    }
                    Picker("Computer player style", selection: $viewModel.botStyle) {
                        Text("Chill").tag("chill"); Text("Normal").tag("normal"); Text("Cutthroat").tag("cutthroat")
                    }
                } header: {
                    Text("pace")
                        .font(Torch.Font.label(Torch.TextSize.xs))
                        .tracking(Torch.Track.wide * Torch.TextSize.xs)
                        .foregroundStyle(Torch.Color.torch)
                        .textCase(nil)
                }
                .listRowBackground(Torch.Color.surfaceRaised)

                Section {
                    Button {
                        dismiss()
                        Task { await viewModel.createGame() }
                    } label: {
                        Label("Light the Fire", systemImage: "flame.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.torchGlow)
                    .listRowBackground(Color.clear)
                    .accessibilityIdentifier("create-game-submit")
                }
            }
            .scrollContentBackground(.hidden)
            .background(Torch.Color.background.ignoresSafeArea())
            .tint(Torch.Color.torch)
            .navigationTitle("New Game")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}
