import Foundation

@MainActor
final class LocalStore {
    private let defaults = UserDefaults.standard
    private let encoder = JSONEncoder()
    private let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()

    func saveListings(_ listings: [ListingDTO]) {
        encoder.dateEncodingStrategy = .iso8601
        defaults.set(try? encoder.encode(listings), forKey: "cachedListings")
    }

    func loadListings() -> [ListingDTO] {
        guard let data = defaults.data(forKey: "cachedListings") else { return [] }
        return (try? decoder.decode([ListingDTO].self, from: data)) ?? []
    }

    func saveFlags(_ flags: [Int: FlagDTO]) {
        let values = Array(flags.values)
        defaults.set(try? encoder.encode(values), forKey: "cachedFlags")
    }

    func loadFlags() -> [Int: FlagDTO] {
        guard let data = defaults.data(forKey: "cachedFlags"),
              let values = try? decoder.decode([FlagDTO].self, from: data) else { return [:] }
        return Dictionary(uniqueKeysWithValues: values.map { ($0.listingId, $0) })
    }

    func clear() {
        defaults.removeObject(forKey: "cachedListings")
        defaults.removeObject(forKey: "cachedFlags")
    }
}

