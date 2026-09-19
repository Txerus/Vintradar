import Foundation
import SwiftData

@Model
final class CachedPayload {
    @Attribute(.unique) var key: String
    var data: Data

    init(key: String, data: Data) {
        self.key = key
        self.data = data
    }
}

@MainActor
final class LocalStore {
    private enum Key {
        static let listings = "listings"
        static let flags = "flags"
    }

    private let defaults = UserDefaults.standard
    private let container: ModelContainer
    private let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()
    private let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()

    init(inMemory: Bool = false) {
        let configuration = ModelConfiguration(isStoredInMemoryOnly: inMemory)
        do {
            container = try ModelContainer(for: CachedPayload.self, configurations: configuration)
        } catch {
            let fallback = ModelConfiguration(isStoredInMemoryOnly: true)
            container = try! ModelContainer(for: CachedPayload.self, configurations: fallback)
        }
    }

    func saveListings(_ listings: [ListingDTO]) {
        guard let data = try? encoder.encode(listings) else { return }
        save(data, key: Key.listings)
        defaults.removeObject(forKey: "cachedListings")
    }

    func loadListings() -> [ListingDTO] {
        if let data = data(for: Key.listings),
           let listings = try? decoder.decode([ListingDTO].self, from: data) {
            return listings
        }
        guard let legacy = defaults.data(forKey: "cachedListings"),
              let listings = try? decoder.decode([ListingDTO].self, from: legacy) else { return [] }
        saveListings(listings)
        return listings
    }

    func saveFlags(_ flags: [Int: FlagDTO]) {
        guard let data = try? encoder.encode(Array(flags.values)) else { return }
        save(data, key: Key.flags)
        defaults.removeObject(forKey: "cachedFlags")
    }

    func loadFlags() -> [Int: FlagDTO] {
        let storedData = data(for: Key.flags) ?? defaults.data(forKey: "cachedFlags")
        guard let storedData,
              let values = try? decoder.decode([FlagDTO].self, from: storedData) else { return [:] }
        if data(for: Key.flags) == nil { saveFlags(Dictionary(uniqueKeysWithValues: values.map { ($0.listingId, $0) })) }
        return Dictionary(uniqueKeysWithValues: values.map { ($0.listingId, $0) })
    }

    func clear() {
        let context = ModelContext(container)
        for record in records(context: context) {
            context.delete(record)
        }
        try? context.save()
        defaults.removeObject(forKey: "cachedListings")
        defaults.removeObject(forKey: "cachedFlags")
    }

    private func save(_ data: Data, key: String) {
        let context = ModelContext(container)
        if let record = records(context: context).first(where: { $0.key == key }) {
            record.data = data
        } else {
            context.insert(CachedPayload(key: key, data: data))
        }
        try? context.save()
    }

    private func data(for key: String) -> Data? {
        let context = ModelContext(container)
        return records(context: context).first(where: { $0.key == key })?.data
    }

    private func records(context: ModelContext) -> [CachedPayload] {
        (try? context.fetch(FetchDescriptor<CachedPayload>())) ?? []
    }
}
