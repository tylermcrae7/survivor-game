import SwiftUI

// MARK: - Loading State

enum LoadingState: Equatable {
    case idle
    case loading
    case loaded
    case error(ViewModelError)

    var isLoading: Bool { self == .loading }

    var isError: Bool {
        if case .error = self { return true }
        return false
    }

    var error: ViewModelError? {
        if case .error(let e) = self { return e }
        return nil
    }
}

// MARK: - ViewModel Error

struct ViewModelError: Equatable, Identifiable {
    let id: UUID
    let title: String
    let message: String
    let isRetryable: Bool

    init(title: String, message: String, isRetryable: Bool = true) {
        self.id = UUID()
        self.title = title
        self.message = message
        self.isRetryable = isRetryable
    }

    static func networkError(_ message: String = "Unable to connect to server") -> ViewModelError {
        ViewModelError(title: "Connection Error", message: message)
    }

    static func gameError(_ message: String) -> ViewModelError {
        ViewModelError(title: "Game Error", message: message, isRetryable: false)
    }

    static func from(_ error: Error) -> ViewModelError {
        if let gameError = error as? GameClientError {
            return ViewModelError(title: "Error", message: gameError.localizedDescription)
        }
        if let apiError = error as? APIError {
            return ViewModelError(title: "Server Error", message: apiError.localizedDescription)
        }
        return ViewModelError(title: "Error", message: error.localizedDescription)
    }
}

// MARK: - Error Alert Modifier

struct ErrorAlertModifier: ViewModifier {
    @Binding var error: ViewModelError?
    var onRetry: (() -> Void)?

    func body(content: Content) -> some View {
        content
            .alert(
                error?.title ?? "Error",
                isPresented: Binding(
                    get: { error != nil },
                    set: { if !$0 { error = nil } }
                )
            ) {
                if let error, error.isRetryable, let onRetry {
                    Button("Retry", action: onRetry)
                }
                Button("OK", role: .cancel) {}
            } message: {
                if let error {
                    Text(error.message)
                }
            }
    }
}

extension View {
    func errorAlert(_ error: Binding<ViewModelError?>, onRetry: (() -> Void)? = nil) -> some View {
        modifier(ErrorAlertModifier(error: error, onRetry: onRetry))
    }
}
