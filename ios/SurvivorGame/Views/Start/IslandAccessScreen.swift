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
                .textFieldStyle(.plain)
                .font(Torch.Font.body(18))
                .tracking(0.18 * 18)
                .multilineTextAlignment(.center)
                .foregroundStyle(Torch.Color.text)
                .tint(Torch.Color.torch)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textContentType(.oneTimeCode)
                .submitLabel(.go)
                .focused($codeFocused)
                .onSubmit { unlock() }
                .frame(minHeight: Torch.Spacing.touchTarget)
                .padding(.horizontal, 14)
                .background(
                    RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                        .fill(Torch.Color.surfaceSunken)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                        .strokeBorder(codeFocused ? Torch.Color.torch : Torch.Color.lineStrong,
                                      lineWidth: 1)
                )
                .torchGlow(codeFocused ? 0.35 : 0)
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

/// The ceremonial wordmark: the flickering flame mark over the Fraunces
/// title, with a small-caps tagline flanked by fading rules.
private struct TorchWordmark: View {
    var subtitle: String

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
