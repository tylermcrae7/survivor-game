import SwiftUI

/// The native counterpart to the web app's "This Island Is Hidden" gate.
/// It appears before create/join whenever the server says an access code is
/// required, so authentication is never buried in Settings.
struct IslandAccessScreen: View {
    @Environment(GameClient.self) private var gameClient
    @State private var code = ""
    @State private var errorMessage: String?
    @State private var showSettings = false
    @FocusState private var codeFocused: Bool

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 28) {
                    StaggeredRise(index: 0) {
                        TorchWordmark(subtitle: "This Island Is Hidden")
                            .padding(.top, 52)
                    }

                    StaggeredRise(index: 1) {
                        Text("Speak the code to come ashore. Ask your host if you don't have it.")
                            .font(Torch.Font.body())
                            .foregroundStyle(Torch.Color.textSecondary)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: 360)
                    }

                    StaggeredRise(index: 2) {
                        accessPanel
                    }
                }
            }
            .background(TorchNightBackground())
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                            .foregroundStyle(Torch.Color.textSecondary)
                    }
                    .accessibilityLabel("Island settings")
                }
            }
            .sheet(isPresented: $showSettings) {
                AppSettingsSheet()
            }
            .onAppear { codeFocused = true }
        }
        .tint(Torch.Color.torch)
    }

    private var accessPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("island code")
                .font(Torch.Font.label(Torch.TextSize.xs))
                .tracking(Torch.Track.label * Torch.TextSize.xs)
                .foregroundStyle(Torch.Color.textSecondary)

            // The access-gate input: centered, wide-tracked, lowercase.
            TextField("Island code", text: $code,
                      prompt: Text("the island code")
                          .foregroundStyle(Torch.Color.textFaint))
                .font(Torch.Font.body(18))
                .tracking(0.18 * 18)
                .multilineTextAlignment(.center)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textContentType(.oneTimeCode)
                .submitLabel(.go)
                .focused($codeFocused)
                .onSubmit { unlock() }
                .torchField(focused: codeFocused)
                .accessibilityLabel("Island code")
                .accessibilityIdentifier("island-access-code")

            Button {
                unlock()
            } label: {
                if gameClient.isLoading {
                    ProgressView()
                        .tint(Torch.Color.ink)
                        .frame(maxWidth: .infinity)
                } else {
                    Label("Come Ashore", systemImage: "flame.fill")
                        .frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(.torchGlow)
            .disabled(code.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || gameClient.isLoading)
            .accessibilityIdentifier("island-come-ashore")

            if let errorMessage {
                Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                    .font(Torch.Font.body(Torch.TextSize.xs))
                    .foregroundStyle(Torch.Color.danger)
                    .accessibilityLabel("Access error: \(errorMessage)")
                    .accessibilityIdentifier("island-access-error")
            }
        }
        .padding(20)
        .torchCard()
        .padding(.horizontal, 24)
    }

    private func unlock() {
        Task {
            do {
                try await gameClient.unlockIsland(with: code)
                code = ""
                errorMessage = nil
                // The gate lifts — the ceremonial arrival, felt and heard at
                // the view layer as the screen transitions to unlocked.
                HapticEngine.unlock()
                TorchSound.play(.tribalGong)
            } catch {
                errorMessage = error.localizedDescription
                HapticEngine.notification(.error)
                codeFocused = true
            }
        }
    }
}

struct IslandUnavailableScreen: View {
    @Environment(GameClient.self) private var gameClient
    let message: String
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            ContentUnavailableView {
                Label("The island is out of reach", systemImage: "wifi.exclamationmark")
                    .font(Torch.Font.display(Torch.TextSize.displaySM))
                    .foregroundStyle(Torch.Color.parchment)
            } description: {
                Text(message)
                    .font(Torch.Font.body())
                    .foregroundStyle(Torch.Color.textSecondary)
            } actions: {
                Button("Try Again") {
                    Task { await gameClient.checkIslandAccess() }
                }
                .buttonStyle(.torchGlow)

                Button("Island Settings") {
                    showSettings = true
                }
                .buttonStyle(.torchSecondary)
            }
            .background(TorchNightBackground())
            .navigationTitle("Survivor")
            .sheet(isPresented: $showSettings) {
                AppSettingsSheet()
            }
        }
        .tint(Torch.Color.torch)
    }
}
