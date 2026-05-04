import Foundation

// Change this to your GCP server URL
let SERVER_BASE = "http://136.111.42.191"

class APIService: ObservableObject {
    static let shared = APIService()

    func fetch<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        guard let url = URL(string: SERVER_BASE + path) else {
            throw URLError(.badURL)
        }
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode(T.self, from: data)
    }

    func post<T: Decodable>(_ path: String, body: [String: Any], as type: T.Type) async throws -> T {
        guard let url = URL(string: SERVER_BASE + path) else {
            throw URLError(.badURL)
        }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, _) = try await URLSession.shared.data(for: req)
        return try JSONDecoder().decode(T.self, from: data)
    }

    func delete(_ path: String) async throws {
        guard let url = URL(string: SERVER_BASE + path) else {
            throw URLError(.badURL)
        }
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        _ = try await URLSession.shared.data(for: req)
    }
}
