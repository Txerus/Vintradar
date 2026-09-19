import Foundation

actor APIClient {
    enum APIError: LocalizedError {
        case notConfigured
        case invalidURL
        case badResponse(Int)
        case invalidResponse

        var errorDescription: String? {
            switch self {
            case .notConfigured: "Le serveur n’est pas configuré."
            case .invalidURL: "L’adresse du serveur est invalide."
            case .badResponse(let code): "Le serveur a répondu avec le code HTTP \(code)."
            case .invalidResponse: "La réponse du serveur est invalide."
            }
        }
    }

    private let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()

    private let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()

    func get<T: Decodable & Sendable>(_ path: String, as: T.Type = T.self) async throws -> T {
        try await perform(path: path, method: "GET", body: nil, as: T.self)
    }

    func send<Body: Encodable & Sendable, Response: Decodable & Sendable>(
        _ path: String,
        method: String,
        body: Body,
        as: Response.Type = Response.self
    ) async throws -> Response {
        try await perform(path: path, method: method, body: encoder.encode(body), as: Response.self)
    }

    func delete(_ path: String) async throws {
        let request = try configuredRequest(path: path, method: "DELETE", body: nil)
        let (_, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard 200..<300 ~= status else { throw APIError.badResponse(status) }
    }

    func health(url: String, token: String) async throws {
        guard let base = URL(string: url) else {
            throw APIError.invalidURL
        }
        let healthURL = base.appendingPathComponent("auth/check")
        var request = URLRequest(url: healthURL)
        request.timeoutInterval = 12
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (_, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard status == 200 else { throw APIError.badResponse(status) }
    }

    private func perform<T: Decodable & Sendable>(path: String, method: String, body: Data?, as: T.Type) async throws -> T {
        let request = try configuredRequest(path: path, method: method, body: body)
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard 200..<300 ~= status else { throw APIError.badResponse(status) }
        return try decoder.decode(T.self, from: data)
    }

    private func configuredRequest(path: String, method: String, body: Data?) throws -> URLRequest {
        guard let raw = UserDefaults.standard.string(forKey: "serverURL"),
              let base = URL(string: raw),
              let token = UserDefaults.standard.string(forKey: "apiToken") else {
            throw APIError.notConfigured
        }
        let url = base.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.httpBody = body
        request.timeoutInterval = 20
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        return request
    }
}
