import Foundation
import OSLog
import Security

/// Persists the server-issued HttpOnly island cookie in this app's Keychain.
/// URLSession's shared cookie jar feeds requests and Socket.IO; the Keychain
/// copy makes the 90-day server cookie reliable across immediate app relaunches.
enum IslandAccessCookieStore {
    private static let service = "mctech.SurvivorGame.island-access"
    private static let cookieName = "survivor_access"
    private static let logger = Logger(
        subsystem: "mctech.SurvivorGame",
        category: "IslandAccess"
    )

    @discardableResult
    static func persist(
        for url: URL,
        storage: HTTPCookieStorage = .shared
    ) -> Bool {
        guard let cookie = storage.cookies(for: url)?.first(where: { $0.name == cookieName })
        else { return false }
        return persist(cookie, for: url)
    }

    /// Persist a cookie directly from its Set-Cookie response, avoiding any
    /// timing dependency on the shared jar's read-back path.
    @discardableResult
    static func persist(_ cookie: HTTPCookie, for url: URL) -> Bool {
        guard cookie.name == cookieName,
              let account = account(for: url),
              let data = try? JSONEncoder().encode(StoredCookie(cookie))
        else { return false }

        var query = keychainQuery(account: account)
        SecItemDelete(query as CFDictionary)
        query[kSecValueData as String] = data
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(query as CFDictionary, nil)
        if status != errSecSuccess {
            let description = SecCopyErrorMessageString(status, nil) as String? ?? "Unknown error"
            logger.error(
                "Keychain save failed with status \(status, privacy: .public): \(description, privacy: .public)"
            )
        }
        return status == errSecSuccess
    }

    static func restore(
        for url: URL,
        storage: HTTPCookieStorage = .shared
    ) {
        guard let account = account(for: url) else { return }
        var query = keychainQuery(account: account)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let stored = try? JSONDecoder().decode(StoredCookie.self, from: data),
              stored.expiresDate.map({ $0 > Date() }) != false,
              let cookie = stored.cookie
        else { return }
        storage.setCookie(cookie)
    }

    static func forget(
        for url: URL,
        storage: HTTPCookieStorage = .shared
    ) {
        for cookie in storage.cookies(for: url) ?? [] where cookie.name == cookieName {
            storage.deleteCookie(cookie)
        }
        if let account = account(for: url) {
            SecItemDelete(keychainQuery(account: account) as CFDictionary)
        }
    }

    private static func account(for url: URL) -> String? {
        url.host?.lowercased()
    }

    private static func keychainQuery(account: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }
}

private struct StoredCookie: Codable {
    let name: String
    let value: String
    let domain: String
    let path: String
    let expiresDate: Date?
    let isSecure: Bool

    init(_ cookie: HTTPCookie) {
        name = cookie.name
        value = cookie.value
        domain = cookie.domain
        path = cookie.path
        expiresDate = cookie.expiresDate
        isSecure = cookie.isSecure
    }

    var cookie: HTTPCookie? {
        var properties: [HTTPCookiePropertyKey: Any] = [
            .name: name,
            .value: value,
            .domain: domain,
            .path: path,
        ]
        // HTTPCookie treats the presence of the Secure property as true even
        // when its string value is "FALSE". Omit it for local HTTP servers.
        if isSecure { properties[.secure] = "TRUE" }
        if let expiresDate { properties[.expires] = expiresDate }
        return HTTPCookie(properties: properties)
    }
}
