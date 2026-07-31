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
                                .textFieldStyle(.plain)
                                .font(Torch.Font.label(Torch.TextSize.sm))
                                .tracking(0.3 * Torch.TextSize.sm)
                                .foregroundStyle(Torch.Color.text)
                                .tint(Torch.Color.torch)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
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
                        Text("Extended — +7 house cards").tag("extended")
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
                    Text("Extended adds Idol Nullifier, Steal A Vote, Block A Vote and Grant Immunity. Rocks adds the 5 Orange Challenge Cards.")
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

/// The ceremonial wordmark: the flickering flame mark over the Fraunces
/// title, with a small-caps tagline flanked by fading rules.
private struct TorchWordmark: View {
    var subtitle: String = "The Tribe Has Spoken"

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "flame.fill")
                .font(.system(size: 44))
                .foregroundStyle(Torch.Color.torch)
                .flameFlicker(glowRadius: 7, glowOpacity: 0.7)
            Text("Survivor")
                .font(Torch.Font.display(Torch.TextSize.displayXL, weight: 900, soft: 30,
                                         relativeTo: .largeTitle))
                .foregroundStyle(Torch.Color.parchment)
                .shadow(color: Torch.Color.torch.opacity(0.35), radius: 30)
                .shadow(color: .black.opacity(0.7), radius: 15, y: 4)
            HStack(spacing: 10) {
                taglineRule(fadeIn: true)
                Text(subtitle)
                    .font(Torch.Font.label(Torch.TextSize.xs))
                    .tracking(Torch.Track.wide * Torch.TextSize.xs)
                    .foregroundStyle(Torch.Color.textSecondary)
                taglineRule(fadeIn: false)
            }
        }
        .multilineTextAlignment(.center)
    }

    private func taglineRule(fadeIn: Bool) -> some View {
        LinearGradient(colors: fadeIn ? [.clear, Torch.Color.torch.opacity(0.5)]
                                      : [Torch.Color.torch.opacity(0.5), .clear],
                       startPoint: .leading, endPoint: .trailing)
            .frame(width: 38, height: 1)
    }
}

/// The night scene: bg → bg-deep, the torchlight radial pressing in from
/// above (web `--torchlight`), and ambient embers rising off the fire.
private struct TorchNightBackground: View {
    var body: some View {
        ZStack {
            LinearGradient(colors: [Torch.Color.background, Torch.Color.backgroundDeep],
                           startPoint: .top, endPoint: .bottom)
            RadialGradient(
                colors: [(Color(hex: "#753B07") ?? Torch.Color.torch).opacity(0.42), .clear],
                center: UnitPoint(x: 0.5, y: -0.12),
                startRadius: 10, endRadius: 480)
            EmberFieldView()
        }
        .ignoresSafeArea()
    }
}
