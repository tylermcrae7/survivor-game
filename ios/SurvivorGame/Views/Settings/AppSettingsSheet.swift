import SwiftData
import SwiftUI
import UIKit

/// Per-device preferences and island connection settings. These mirror the
/// web app's settings where the platform behavior is equivalent; Dynamic Type
/// and Reduce Motion continue to follow the iOS system settings.
struct AppSettingsSheet: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(\.modelContext) private var modelContext
    @Environment(\.dismiss) private var dismiss

    @State private var serverURL = ""
    @State private var playerName = ""
    @State private var preferredColor: String?
    @State private var statusMessage: String?
    @State private var showForgetConfirmation = false
    @State private var loaded = false

    @AppStorage("defaultDeckMode") private var defaultDeckMode = "official"
    @AppStorage("defaultExpansion") private var defaultExpansion = false
    @AppStorage("defaultBotPace") private var defaultBotPace = "normal"
    @AppStorage("defaultTribalPace") private var defaultTribalPace = "normal"
    @AppStorage("defaultBotStyle") private var defaultBotStyle = "normal"
    @AppStorage("confirmVotes") private var confirmVotes = false
    @AppStorage("confirmSteals") private var confirmSteals = false
    @AppStorage("soundEnabled") private var soundEnabled = true // TorchSound gate
    @AppStorage("hapticsEnabled") private var hapticsEnabled = true
    @AppStorage("keepAwake") private var keepAwake = false
    @AppStorage("historyLength") private var historyLength = "30"

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Server URL", text: $serverURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .accessibilityHint("The HTTPS address of the Survivor game server")

                    Button {
                        Task { await applyServer() }
                    } label: {
                        Label("Use This Island", systemImage: "network")
                    }
                    .buttonStyle(.torchGlow)
                    .disabled(gameClient.gameId != nil)
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0))

                    LabeledContent("Access", value: accessDescription)
                        .foregroundStyle(Torch.Color.text, Torch.Color.textSecondary)

                    if let statusMessage {
                        Text(statusMessage)
                            .font(Torch.Font.body(Torch.TextSize.xs))
                            .foregroundStyle(Torch.Color.textSecondary)
                    }
                } header: {
                    sectionLabel("island")
                } footer: {
                    if gameClient.gameId != nil {
                        footerText("Leave the current game before changing islands.")
                    } else {
                        footerText("The public island uses HTTPS. Local development servers can use a private-network HTTP address.")
                    }
                }
                .listRowBackground(Torch.Color.surfaceSunken)
                .listRowSeparatorTint(Torch.Color.line)

                Section {
                    TextField("Your name", text: $playerName)
                        .textInputAutocapitalization(.words)
                    BuffColorPicker(selectedColor: $preferredColor)
                } header: {
                    sectionLabel("you")
                }
                .listRowBackground(Torch.Color.surfaceSunken)
                .listRowSeparatorTint(Torch.Color.line)

                Section {
                    Picker("Deck", selection: $defaultDeckMode) {
                        Text("Official").tag("official")
                        Text("Extended").tag("extended")
                    }
                    Toggle("Add Rocks challenges", isOn: $defaultExpansion)
                    Picker("Computer player speed", selection: $defaultBotPace) {
                        Text("Chill").tag("chill")
                        Text("Normal").tag("normal")
                        Text("Fast").tag("fast")
                    }
                    Picker("Tribal ceremony pace", selection: $defaultTribalPace) {
                        Text("Normal").tag("normal")
                        Text("Relaxed").tag("relaxed")
                        Text("TV drama").tag("tv")
                    }
                    Picker("Computer player style", selection: $defaultBotStyle) {
                        Text("Chill").tag("chill")
                        Text("Normal").tag("normal")
                        Text("Cutthroat").tag("cutthroat")
                    }
                } header: {
                    sectionLabel("defaults for new games")
                }
                .listRowBackground(Torch.Color.surfaceSunken)
                .listRowSeparatorTint(Torch.Color.line)

                Section {
                    Toggle("Confirm before casting a vote", isOn: $confirmVotes)
                    Toggle("Confirm before stealing", isOn: $confirmSteals)
                    Toggle("Sound", isOn: $soundEnabled)
                    Toggle("Vibration", isOn: $hapticsEnabled)
                    Toggle("Keep screen awake during games", isOn: $keepAwake)
                    Picker("Story so far", selection: $historyLength) {
                        Text("Last 30 events").tag("30")
                        Text("Everything").tag("all")
                    }
                } header: {
                    sectionLabel("table & device")
                } footer: {
                    footerText("Text size and Reduce Motion follow your iPhone's Accessibility settings.")
                }
                .listRowBackground(Torch.Color.surfaceSunken)
                .listRowSeparatorTint(Torch.Color.line)

                Section {
                    Button("Forget This Island", role: .destructive) {
                        showForgetConfirmation = true
                    }
                    .foregroundStyle(Torch.Color.danger)

                    Button("Reset Preferences") {
                        resetPreferences()
                    }
                    .foregroundStyle(Torch.Color.torch)
                } header: {
                    sectionLabel("housekeeping")
                }
                .listRowBackground(Torch.Color.surfaceSunken)
                .listRowSeparatorTint(Torch.Color.line)
            }
            .foregroundStyle(Torch.Color.text)
            .scrollContentBackground(.hidden)
            .background(nightBackdrop)
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Text("Settings")
                        .font(Torch.Font.display(Torch.TextSize.displaySM))
                        .foregroundStyle(Torch.Color.parchment)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        saveIdentity()
                        dismiss()
                    }
                }
            }
            .onAppear { loadOnce() }
            .onChange(of: keepAwake) { _, value in
                UIApplication.shared.isIdleTimerDisabled = value && gameClient.gameId != nil
            }
            .confirmationDialog(
                "Forget this island?",
                isPresented: $showForgetConfirmation,
                titleVisibility: .visible
            ) {
                Button("Forget This Island", role: .destructive) {
                    Task {
                        let config = ServerConfig.loadDefault(from: modelContext)
                        config.lastGameId = nil
                        config.lastPlayerId = nil
                        try? modelContext.save()
                        await gameClient.forgetIslandAccess()
                        dismiss()
                    }
                }
            } message: {
                Text("The island code and saved game are removed from this device. Your player name and preferences stay.")
            }
        }
        .tint(Torch.Color.torch)
        .preferredColorScheme(.dark)
    }

    /// Night ground with the torchlight radial anchored above the top edge.
    private var nightBackdrop: some View {
        ZStack {
            LinearGradient(colors: [Torch.Color.background, Torch.Color.backgroundDeep],
                           startPoint: .top, endPoint: .bottom)
            RadialGradient(colors: [Torch.Color.torch.opacity(0.10), .clear],
                           center: UnitPoint(x: 0.5, y: -0.12),
                           startRadius: 0, endRadius: 460)
        }
        .ignoresSafeArea()
    }

    private func sectionLabel(_ title: String) -> some View {
        Text(title)
            .font(Torch.Font.label(Torch.TextSize.xs))
            .tracking(Torch.Track.label * Torch.TextSize.xs)
            .foregroundStyle(Torch.Color.textSecondary)
    }

    private func footerText(_ text: String) -> some View {
        Text(text)
            .font(Torch.Font.body(Torch.TextSize.xs))
            .foregroundStyle(Torch.Color.textFaint)
    }

    private var accessDescription: String {
        switch gameClient.accessState {
        case .checking: return "Checking…"
        case .unlocked: return "Ready"
        case .requiresCode: return "Code required"
        case .unavailable: return "Unavailable"
        }
    }

    private func loadOnce() {
        guard !loaded else { return }
        loaded = true
        let config = ServerConfig.loadDefault(from: modelContext)
        serverURL = config.baseURL.absoluteString
        playerName = config.playerName
        preferredColor = config.preferredColor
    }

    private func applyServer() async {
        guard let url = normalizedServerURL(serverURL) else {
            statusMessage = "Enter a complete http:// or https:// server address."
            return
        }

        let config = ServerConfig.loadDefault(from: modelContext)
        config.baseURL = url
        config.lastGameId = nil
        config.lastPlayerId = nil
        try? modelContext.save()

        serverURL = url.absoluteString
        await gameClient.useServer(url)
        switch gameClient.accessState {
        case .unlocked:
            statusMessage = "Connected to the island."
        case .requiresCode:
            statusMessage = "Connected. This island needs its shared code."
        case .unavailable(let message):
            statusMessage = "Could not connect: \(message)"
        case .checking:
            statusMessage = "Still checking the island."
        }
    }

    private func normalizedServerURL(_ value: String) -> URL? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard var components = URLComponents(string: trimmed),
              let scheme = components.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              components.host != nil
        else { return nil }
        components.scheme = scheme
        components.path = components.path == "/" ? "" : components.path
        components.query = nil
        components.fragment = nil
        return components.url
    }

    private func saveIdentity() {
        let config = ServerConfig.loadDefault(from: modelContext)
        config.playerName = playerName.trimmingCharacters(in: .whitespacesAndNewlines)
        config.preferredColor = preferredColor
        try? modelContext.save()
    }

    private func resetPreferences() {
        defaultDeckMode = "official"
        defaultExpansion = false
        defaultBotPace = "normal"
        defaultTribalPace = "normal"
        defaultBotStyle = "normal"
        confirmVotes = false
        confirmSteals = false
        soundEnabled = true
        hapticsEnabled = true
        keepAwake = false
        historyLength = "30"
        UIApplication.shared.isIdleTimerDisabled = false
        statusMessage = "Preferences are back to normal."
    }
}

private struct BuffColorPicker: View {
    @Binding var selectedColor: String?

    private let columns = Array(repeating: GridItem(.flexible()), count: 5)

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Your buff")
                .font(Torch.Font.label(Torch.TextSize.xs))
                .tracking(Torch.Track.label * Torch.TextSize.xs)
                .foregroundStyle(Torch.Color.textSecondary)
            LazyVGrid(columns: columns, spacing: 12) {
                colorButton(color: .gray, value: nil, label: "Any")
                ForEach(PlayerColor.allCases, id: \.rawValue) { choice in
                    colorButton(
                        color: choice.color,
                        value: choice.rawValue,
                        label: choice.displayName
                    )
                }
            }
            // The web toggle-thumb spring, reused for swatch selection.
            .animation(.spring(response: 0.3, dampingFraction: 0.62), value: selectedColor)
        }
        .padding(.vertical, 4)
    }

    private func colorButton(color: Color, value: String?, label: String) -> some View {
        let selected = selectedColor == value
        return Button {
            selectedColor = value
            HapticEngine.selection()
        } label: {
            Circle()
                .fill(color)
                .frame(width: 38, height: 38)
                .overlay {
                    if selected {
                        Image(systemName: "checkmark")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundStyle(.white)
                            .shadow(color: .black.opacity(0.4), radius: 1, y: 1)
                    }
                }
                .overlay {
                    if selected {
                        // Web double ring: 3px bg gap, then the torch ring.
                        Circle().inset(by: -1.5).stroke(Torch.Color.background, lineWidth: 3)
                        Circle().inset(by: -4).stroke(Torch.Color.torch, lineWidth: 2)
                    }
                }
                .shadow(color: Torch.Color.torch.opacity(selected ? 0.35 : 0), radius: 11)
                .scaleEffect(selected ? 1.1 : 1)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}
