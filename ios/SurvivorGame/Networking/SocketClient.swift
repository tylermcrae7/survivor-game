import Foundation
import SocketIO

@MainActor
@Observable
final class SocketClient {
    private var manager: SocketManager?
    private var socket: SocketIOClient?
    private var heartbeatTimer: Timer?
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 10

    private(set) var connectionState: ConnectionState = .disconnected {
        didSet {
            connectionContinuation?.yield(connectionState)
        }
    }

    // Streams for broadcasting events to consumers
    private var gameStateContinuation: AsyncStream<GameState>.Continuation?
    private(set) var gameStateStream: AsyncStream<GameState>!

    private var gameEventContinuation: AsyncStream<GameEvent>.Continuation?
    private(set) var gameEventStream: AsyncStream<GameEvent>!

    private var connectionContinuation: AsyncStream<ConnectionState>.Continuation?
    private(set) var connectionStream: AsyncStream<ConnectionState>!

    init() {
        gameStateStream = AsyncStream { continuation in
            self.gameStateContinuation = continuation
        }
        gameEventStream = AsyncStream { continuation in
            self.gameEventContinuation = continuation
        }
        connectionStream = AsyncStream { continuation in
            self.connectionContinuation = continuation
        }
    }

    func connect(to url: URL) {
        disconnect()

        connectionState = .connecting

        manager = SocketManager(socketURL: url, config: [
            .log(false),
            .compress,
            .forceWebsockets(true),
            .reconnects(true),
            .reconnectAttempts(maxReconnectAttempts),
            .reconnectWait(1),
            .reconnectWaitMax(30)
        ])

        socket = manager?.defaultSocket

        setupEventHandlers()
        socket?.connect()
    }

    func disconnect() {
        heartbeatTimer?.invalidate()
        heartbeatTimer = nil
        socket?.disconnect()
        socket = nil
        manager?.disconnect()
        manager = nil
        connectionState = .disconnected
        reconnectAttempts = 0
    }

    func joinGame(_ gameId: String) {
        socket?.emit("join", ["gameId": gameId])
    }

    func sendHeartbeat() {
        socket?.emit("heartbeat", ["t": Date().timeIntervalSince1970])
    }

    // MARK: - Private

    private func setupEventHandlers() {
        guard let socket else { return }

        socket.on(clientEvent: .connect) { [weak self] _, _ in
            Task { @MainActor in
                self?.connectionState = .connected
                self?.reconnectAttempts = 0
                self?.startHeartbeat()
            }
        }

        socket.on(clientEvent: .disconnect) { [weak self] _, _ in
            Task { @MainActor in
                self?.connectionState = .disconnected
                self?.heartbeatTimer?.invalidate()
            }
        }

        socket.on(clientEvent: .reconnect) { [weak self] _, _ in
            Task { @MainActor in
                self?.connectionState = .connected
                self?.reconnectAttempts = 0
            }
        }

        socket.on(clientEvent: .reconnectAttempt) { [weak self] _, _ in
            Task { @MainActor in
                self?.connectionState = .reconnecting
                self?.reconnectAttempts += 1
            }
        }

        socket.on(clientEvent: .error) { [weak self] data, _ in
            Task { @MainActor in
                let msg = (data.first as? String) ?? "Unknown error"
                self?.connectionState = .failed(msg)
            }
        }

        // Game state updates
        socket.on("state_update") { [weak self] data, _ in
            Task { @MainActor in
                self?.handleStateUpdate(data)
            }
        }

        socket.on("game_updated") { [weak self] data, _ in
            Task { @MainActor in
                self?.handleStateUpdate(data)
            }
        }

        // Game events
        socket.on("game_event") { [weak self] data, _ in
            Task { @MainActor in
                self?.handleGameEvent(data)
            }
        }

        socket.on("game_reset") { [weak self] _, _ in
            Task { @MainActor in
                self?.gameEventContinuation?.yield(.reset)
            }
        }

        socket.on("global_reset") { [weak self] _, _ in
            Task { @MainActor in
                self?.gameEventContinuation?.yield(.reset)
            }
        }

        socket.on("error") { [weak self] data, _ in
            Task { @MainActor in
                let msg = (data.first as? [String: Any])?["message"] as? String ?? "Server error"
                self?.gameEventContinuation?.yield(.error(msg))
            }
        }
    }

    private func handleStateUpdate(_ data: [Any]) {
        guard let dict = data.first else { return }

        do {
            let jsonData: Data
            if let d = dict as? Data {
                jsonData = d
            } else {
                jsonData = try JSONSerialization.data(withJSONObject: dict)
            }
            let state = try JSONDecoder().decode(GameState.self, from: jsonData)
            gameStateContinuation?.yield(state)
        } catch {
            print("[SocketClient] Failed to decode game state: \(error)")
        }
    }

    private func handleGameEvent(_ data: [Any]) {
        guard let dict = data.first as? [String: Any],
              let type = dict["type"] as? String
        else { return }

        let event = GameEvent.custom(type: type, data: dict)
        gameEventContinuation?.yield(event)
    }

    private func startHeartbeat() {
        heartbeatTimer?.invalidate()
        heartbeatTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.sendHeartbeat()
            }
        }
    }
}

// MARK: - Game Event

enum GameEvent {
    case custom(type: String, data: [String: Any])
    case reset
    case error(String)
}
