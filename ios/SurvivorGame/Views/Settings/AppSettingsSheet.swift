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
    @State private var discordUserId = ""
    @State private var statusMessage: String?
    @State private var showForgetConfirmation = false
    @State private var loaded = false

    /// One focus binding for the whole sheet: a SwiftUI keyboard toolbar is
    /// scoped to the form, not to the field it is written next to, so the
    /// Done button has to be able to let go of whichever field is up.
    private enum Field: Hashable { case server, name, discord }
    @FocusState private var focusedField: Field?
    private var discordFieldFocused: Bool { focusedField == .discord }

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
                        .focused($focusedField, equals: .server)
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
                        .focused($focusedField, equals: .name)
                    BuffColorPicker(selectedColor: $preferredColor)
                    VStack(alignment: .leading, spacing: 10) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Discord user ID")
                                .font(Torch.Font.label(Torch.TextSize.xs))
                                .tracking(Torch.Track.label * Torch.TextSize.xs)
                                .foregroundStyle(Torch.Color.textSecondary)
                            // The server refuses a malformed ID outright — and
                            // it does so on JOIN, where the failure would read
                            // as "the island turned me away". Say it here
                            // instead, ABOVE the field: the number pad covers
                            // everything below it, which is exactly where this
                            // warning used to sit and never be read.
                            if showsDiscordHint {
                                Text("A Discord user ID is a long run of digits — usually 18.")
                                    .font(Torch.Font.body(Torch.TextSize.xs))
                                    .foregroundStyle(Torch.Color.warning)
                                    .fixedSize(horizontal: false, vertical: true)
                                    .transition(.opacity)
                            }
                        }
                        TextField("000000000000000000", text: $discordUserId)
                            .keyboardType(.numberPad)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .torchField()
                            .focused($focusedField, equals: .discord)
                            .accessibilityLabel("Discord user ID")
                            .accessibilityValue(showsDiscordHint
                                ? "That doesn't look like a Discord user ID — it is a long run of digits, usually 18."
                                : "")
                            // A pasted ID often arrives wrapped in spaces or
                            // angle brackets; keep only what the server accepts.
                            .onChange(of: discordUserId) { _, value in
                                let digits = value.filter(\.isNumber)
                                if digits != value { discordUserId = digits }
                            }
                    }
                    .padding(.vertical, 4)
                    .animation(.easeOut(duration: 0.15), value: showsDiscordHint)
                } header: {
                    sectionLabel("you")
                } footer: {
                    footerText("Optional. Lets the camp's Discord bot move you between voice channels as you change places. In Discord: Settings → Advanced → turn on Developer Mode, then press and hold your own name and tap Copy User ID.")
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
            .background(TorchNightBackground(radialColor: Torch.Color.torch.opacity(0.10),
                                             showEmbers: false, startRadius: 0, endRadius: 460))
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
                // The Discord ID field takes a number pad, which has no return
                // key: without this the only ways out are the nav-bar Done
                // (which saves) or dragging the sheet away. It rides above
                // every keyboard in the sheet, so it lets go of whichever
                // field is up rather than one particular one.
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") { focusedField = nil }
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

    /// Empty (not linked) or a plausible snowflake. Mirrors the server's own
    /// 15–25 digit guard so the complaint lands next to the field, not on join.
    private var discordIdLooksRight: Bool {
        let trimmed = discordUserId.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty
            || trimmed.range(of: "^[0-9]{15,25}$", options: .regularExpression) != nil
    }

    /// Whether to actually complain yet. A real 18-digit ID is "too short" for
    /// its first fourteen keystrokes, and an amber warning that fires on every
    /// one of them is a warning people learn to ignore. So: judge on blur,
    /// where the answer is final — and immediately while typing only once the
    /// value has run past any plausible snowflake, which is unambiguous.
    private var showsDiscordHint: Bool {
        guard !discordIdLooksRight else { return false }
        return !discordFieldFocused || discordUserId.count > 25
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
        discordUserId = config.discordUserId ?? ""
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
        let trimmedDiscordId = discordUserId.trimmingCharacters(in: .whitespacesAndNewlines)
        config.discordUserId = trimmedDiscordId.isEmpty ? nil : trimmedDiscordId
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
