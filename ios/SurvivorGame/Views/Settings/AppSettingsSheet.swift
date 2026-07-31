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
                    .disabled(gameClient.gameId != nil)

                    LabeledContent("Access", value: accessDescription)

                    if let statusMessage {
                        Text(statusMessage)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } header: {
                    Text("Island")
                } footer: {
                    if gameClient.gameId != nil {
                        Text("Leave the current game before changing islands.")
                    } else {
                        Text("The public island uses HTTPS. Local development servers can use a private-network HTTP address.")
                    }
                }

                Section("You") {
                    TextField("Your name", text: $playerName)
                        .textInputAutocapitalization(.words)
                    BuffColorPicker(selectedColor: $preferredColor)
                }

                Section("Defaults for New Games") {
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
                }

                Section {
                    Toggle("Confirm before casting a vote", isOn: $confirmVotes)
                    Toggle("Confirm before stealing", isOn: $confirmSteals)
                    Toggle("Vibration", isOn: $hapticsEnabled)
                    Toggle("Keep screen awake during games", isOn: $keepAwake)
                    Picker("Story so far", selection: $historyLength) {
                        Text("Last 30 events").tag("30")
                        Text("Everything").tag("all")
                    }
                } header: {
                    Text("Table & Device")
                } footer: {
                    Text("Text size and Reduce Motion follow your iPhone's Accessibility settings.")
                }

                Section("Housekeeping") {
                    Button("Forget This Island", role: .destructive) {
                        showForgetConfirmation = true
                    }

                    Button("Reset Preferences") {
                        resetPreferences()
                    }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
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
        }
        .padding(.vertical, 4)
    }

    private func colorButton(color: Color, value: String?, label: String) -> some View {
        Button {
            selectedColor = value
            HapticEngine.selection()
        } label: {
            Circle()
                .fill(color)
                .frame(width: 38, height: 38)
                .overlay {
                    if selectedColor == value {
                        Circle().strokeBorder(.white, lineWidth: 3)
                    }
                }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityAddTraits(selectedColor == value ? .isSelected : [])
    }
}
